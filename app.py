"""Primary Flask entrypoint for local runs and Vercel deployments."""

from __future__ import annotations

import base64
import logging
import os
import re
import sys
import tempfile
import zlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import Flask, abort, has_request_context, render_template, request, send_file
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config.loader import load_settings, load_subject_master
from exporter.excel_writer import export_excel_bytes
from parser.gazette_parser import ParseError, Student, parse_gazette
from transformer.calculator import compute_subject_analysis, compute_summary
from transformer.normalizer import build_student_dataframe


BASE_DIR = Path(__file__).parent
SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"
SUBJECTS_PATH = BASE_DIR / "config" / "subjects.json"
SAMPLE_PATH = BASE_DIR / "sample_gazette.txt"
RAW_PREVIEW_LIMIT = 12000
STUDENT_PREVIEW_LIMIT = 18
SUBJECT_PREVIEW_LIMIT = 18
PAYLOAD_ENCODING_PREFIX = "z1:"
VERCEL_FUNCTION_BODY_LIMIT_BYTES = 4_500_000
DEFAULT_MAX_UPLOAD_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_ROUNDTRIP_PAYLOAD_BYTES = 3_500_000
PUBLIC_GITHUB_URL = os.getenv(
    "PUBLIC_GITHUB_URL",
    "https://github.com/yorayriniwnl/CBSE-Result-Analyzer",
)
PUBLIC_GITHUB_LABEL = os.getenv("PUBLIC_GITHUB_LABEL", "View on GitHub")
PUBLIC_VERCEL_URL = os.getenv(
    "PUBLIC_VERCEL_URL",
    "https://cbse-result-analyzer.vercel.app/",
)
PUBLIC_VERCEL_LABEL = os.getenv("PUBLIC_VERCEL_LABEL", "Open Live Demo")
PUBLIC_BASE_PATH = os.getenv("PUBLIC_BASE_PATH", "/cbse-result-analyzer")
PUBLIC_BASE_PATH_HOSTS = os.getenv(
    "PUBLIC_BASE_PATH_HOSTS",
    "yorayriniwnl.in,www.yorayriniwnl.in",
)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)))
MAX_ROUNDTRIP_PAYLOAD_BYTES = int(
    os.getenv(
        "MAX_ROUNDTRIP_PAYLOAD_BYTES",
        str(DEFAULT_MAX_ROUNDTRIP_PAYLOAD_BYTES),
    )
)


def _configured_log_level() -> int:
    requested = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    return logging.getLevelNamesMapping().get(requested, logging.INFO)


logging.basicConfig(level=_configured_log_level())
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
app.logger.setLevel(_configured_log_level())
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


@lru_cache(maxsize=1)
def _settings() -> Dict:
    return load_settings(str(SETTINGS_PATH))


@lru_cache(maxsize=1)
def _subject_master() -> Dict[str, str]:
    return load_subject_master(str(SUBJECTS_PATH))


@lru_cache(maxsize=1)
def _sample_text() -> str:
    return SAMPLE_PATH.read_text(encoding="utf-8")


def _error_page(message: str) -> Dict[str, object]:
    page = _default_context()
    page["error_message"] = message
    return page


def _format_mib(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MiB"


def _size_limit_message() -> str:
    return (
        f"Upload a CBSE gazette under {_format_mib(MAX_UPLOAD_BYTES)}. "
        f"Vercel Functions reject request or response bodies above "
        f"{VERCEL_FUNCTION_BODY_LIMIT_BYTES / 1_000_000:.1f} MB."
    )


def _normalize_public_base_path(path: str) -> str:
    cleaned = (path or "").strip()
    if not cleaned or cleaned == "/":
        return ""
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned.rstrip("/")


@lru_cache(maxsize=1)
def _configured_public_base_path_hosts() -> set[str]:
    return {
        host.strip().lower()
        for host in PUBLIC_BASE_PATH_HOSTS.split(",")
        if host.strip()
    }


def _header_public_base_path() -> str:
    if not has_request_context():
        return ""

    candidate = _normalize_public_base_path(
        request.headers.get("X-Forwarded-Prefix", "")
    )
    if not candidate:
        return ""
    if any(token in candidate for token in ("//", "://", "?", "#", " ")):
        return ""
    return candidate


def _request_public_base_path() -> str:
    proxied_prefix = _header_public_base_path()
    if proxied_prefix:
        return proxied_prefix

    if not has_request_context():
        return ""

    configured_prefix = _normalize_public_base_path(PUBLIC_BASE_PATH)
    if not configured_prefix:
        return ""

    request_host = (request.headers.get("X-Forwarded-Host") or request.host).split(
        ":", 1
    )[0].lower()
    if request_host in _configured_public_base_path_hosts():
        return configured_prefix
    return ""


def _public_route(path: str) -> str:
    prefix = _request_public_base_path()
    if path == "/":
        return prefix or "/"
    return f"{prefix}{path}" if prefix else path


def _running_inside_streamlit() -> bool:
    if not any(module_name.startswith("streamlit") for module_name in sys.modules):
        return False

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return True

    return get_script_run_ctx() is not None


def _render_streamlit_entrypoint_notice() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="Use streamlit_app.py",
        page_icon="C",
        layout="centered",
    )
    st.error("`app.py` is the Flask/Vercel entrypoint, not the Streamlit app.")
    st.code("python -m streamlit run streamlit_app.py", language="bash")
    st.caption(
        "Use `python app.py` for local Flask runs, or `streamlit run streamlit_app.py` "
        "for the Streamlit studio."
    )


def _run_dev_entrypoint() -> None:
    if _running_inside_streamlit():
        _render_streamlit_entrypoint_notice()
        return

    app.run(debug=True)


def _resource_report() -> Dict[str, object]:
    report: Dict[str, object] = {
        "base_dir": str(BASE_DIR),
        "settings_path": str(SETTINGS_PATH),
        "subjects_path": str(SUBJECTS_PATH),
        "sample_path": str(SAMPLE_PATH),
        "templates_path": str(BASE_DIR / "templates"),
        "settings_exists": SETTINGS_PATH.exists(),
        "subjects_exists": SUBJECTS_PATH.exists(),
        "sample_exists": SAMPLE_PATH.exists(),
        "templates_exists": (BASE_DIR / "templates" / "index.html").exists(),
    }

    try:
        report["settings_loaded"] = bool(_settings())
    except Exception as exc:  # pragma: no cover - diagnostic path
        report["settings_loaded"] = False
        report["settings_error"] = str(exc)

    try:
        report["subjects_loaded"] = bool(_subject_master())
    except Exception as exc:  # pragma: no cover - diagnostic path
        report["subjects_loaded"] = False
        report["subjects_error"] = str(exc)

    try:
        report["sample_loaded"] = bool(_sample_text())
    except Exception as exc:  # pragma: no cover - diagnostic path
        report["sample_loaded"] = False
        report["sample_error"] = str(exc)

    return report


def _detect_school_name(raw_text: str) -> Optional[str]:
    match = re.search(r"^SCHOOL\s*:\s*-\s*\d+\s+(.*)$", raw_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def _ensure_output_name(name: str) -> str:
    clean_name = (name or "").strip() or "CBSE_Result_Analysis.xlsx"
    if not clean_name.lower().endswith(".xlsx"):
        clean_name = f"{clean_name}.xlsx"
    return clean_name


def _encode_payload(raw_text: str) -> str:
    compressed = zlib.compress(raw_text.encode("utf-8"), level=9)
    return f"{PAYLOAD_ENCODING_PREFIX}{base64.b64encode(compressed).decode('ascii')}"


def _decode_payload(payload: str) -> str:
    try:
        is_compressed = payload.startswith(PAYLOAD_ENCODING_PREFIX)
        encoded_payload = payload[len(PAYLOAD_ENCODING_PREFIX) :] if is_compressed else payload
        decoded = base64.b64decode(encoded_payload.encode("ascii"), validate=True)
        if is_compressed:
            return zlib.decompress(decoded).decode("utf-8")
        return decoded.decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive path
        raise ValueError("Invalid workbook payload.") from exc


def _parse_gazette_text(raw_text: str) -> Tuple[List[Student], List[ParseError]]:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(raw_text)
            temp_path = handle.name
        return parse_gazette(temp_path, _settings())
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _coerce_student_preview(student_df: pd.DataFrame) -> List[Dict[str, str]]:
    preview = student_df.loc[
        :,
        [
            "Roll No",
            "Name",
            "Gender",
            "Total Marks",
            "Percentage",
            "Subjects Appeared",
            "Result",
        ],
    ].copy()
    preview["Percentage"] = pd.to_numeric(preview["Percentage"], errors="coerce").map(
        lambda value: f"{value:.2f}%" if pd.notna(value) else ""
    )
    preview["Total Marks"] = pd.to_numeric(preview["Total Marks"], errors="coerce").map(
        lambda value: f"{int(value)}" if pd.notna(value) else ""
    )
    preview["Subjects Appeared"] = pd.to_numeric(
        preview["Subjects Appeared"], errors="coerce"
    ).map(lambda value: f"{int(value)}" if pd.notna(value) else "")
    return preview.head(STUDENT_PREVIEW_LIMIT).to_dict("records")


def _prepare_toppers(student_df: pd.DataFrame) -> List[Dict[str, str]]:
    sortable = student_df.copy()
    sortable["Percentage"] = pd.to_numeric(sortable["Percentage"], errors="coerce")
    sortable["Total Marks"] = pd.to_numeric(sortable["Total Marks"], errors="coerce")
    sortable["Result"] = sortable["Result"].astype(str).str.upper()

    eligible = sortable[sortable["Result"] == "PASS"]
    if eligible.empty:
        eligible = sortable[sortable["Percentage"].notna()]

    toppers = eligible.sort_values(
        ["Percentage", "Total Marks"],
        ascending=[False, False],
        na_position="last",
    ).head(3)

    items: List[Dict[str, str]] = []
    for rank, (_, row) in enumerate(toppers.iterrows(), start=1):
        result_label = str(row.get("Result", "") or "NA").upper()
        items.append(
            {
                "rank": f"{rank:02d}",
                "name": str(row.get("Name", "Unknown")),
                "roll": str(row.get("Roll No", "-")),
                "total_marks": f"{int(row['Total Marks'])}" if pd.notna(row.get("Total Marks")) else "-",
                "percentage": (
                    f"{float(row['Percentage']):.2f}%"
                    if pd.notna(row.get("Percentage"))
                    else "NA"
                ),
                "result_label": result_label,
                "result_class": f"badge-{result_label.lower()}" if result_label in {"PASS", "FAIL", "COMP", "ABSENT"} else "badge-neutral",
            }
        )
    return items


def _prepare_subject_rows(subject_df: pd.DataFrame) -> List[Dict[str, str]]:
    if subject_df.empty:
        return []

    ordered = subject_df.sort_values("Average Marks", ascending=False).copy()
    ordered["Average Marks"] = ordered["Average Marks"].map(lambda value: f"{value:.2f}")
    ordered["Pass %"] = ordered["Pass %"].map(lambda value: f"{value:.2f}%")
    ordered["Highest"] = ordered["Highest"].map(lambda value: f"{int(value)}")
    ordered["Lowest"] = ordered["Lowest"].map(lambda value: f"{int(value)}")
    ordered["Students Appeared"] = ordered["Students Appeared"].map(lambda value: f"{int(value)}")
    ordered["Pass Count"] = ordered["Pass Count"].map(lambda value: f"{int(value)}")
    return ordered.head(SUBJECT_PREVIEW_LIMIT).to_dict("records")


def _prepare_error_rows(errors: List[ParseError]) -> List[Dict[str, str]]:
    return [
        {
            "level": error.level,
            "roll": error.roll,
            "line_no": str(error.line_no),
            "message": error.message,
        }
        for error in errors
    ]


def _result_breakdown(summary: Dict[str, object]) -> List[Dict[str, str]]:
    total = max(int(summary["Total Candidates"]), 1)
    payload = [
        ("Pass", int(summary["Passed"])),
        ("Fail", int(summary["Failed"])),
        ("Compartment", int(summary["Compartment"])),
        ("Absent", int(summary["Absent"])),
    ]
    other_results = int(summary.get("Other Results", 0) or 0)
    if other_results:
        payload.append(("Other", other_results))

    items = []
    for label, count in payload:
        ratio = round((count / total) * 100, 2)
        items.append(
            {
                "label": label,
                "count": str(count),
                "ratio": f"{ratio:.2f}%",
                "width": str(max(ratio, 4 if count else 0)),
            }
        )
    return items


def _pass_rate_note(summary: Dict[str, object]) -> str:
    note = (
        f'{summary["Passed"]} pass, {summary["Failed"]} fail, '
        f'{summary["Compartment"]} compartment'
    )
    other_results = int(summary.get("Other Results", 0) or 0)
    if other_results:
        note += f", {other_results} other"
    return f"{note}."


def _subject_spotlight(subject_df: pd.DataFrame, strongest: bool) -> Optional[Dict[str, str]]:
    if subject_df.empty:
        return None

    ordered = subject_df.sort_values("Average Marks", ascending=not strongest)
    row = ordered.iloc[0]
    return {
        "subject_name": str(row["Subject Name"]),
        "subject_code": str(row["Subject Code"]),
        "average_marks": f"{float(row['Average Marks']):.2f}",
        "highest": f"{int(row['Highest'])}",
        "lowest": f"{int(row['Lowest'])}",
        "pass_percent": f"{float(row['Pass %']):.2f}%",
    }


def _default_context() -> Dict[str, object]:
    return {
        "has_analysis": False,
        "source_name": None,
        "school_name": "CBSE Results 2026",
        "output_name": "CBSE_Result_Analysis.xlsx",
        "github_url": PUBLIC_GITHUB_URL,
        "github_label": PUBLIC_GITHUB_LABEL,
        "vercel_url": PUBLIC_VERCEL_URL,
        "vercel_label": PUBLIC_VERCEL_LABEL,
        "home_url": _public_route("/"),
        "download_url": _public_route("/download"),
        "error_message": None,
        "download_ready": False,
        "metrics": [],
        "toppers": [],
        "result_breakdown": [],
        "strongest_subject": None,
        "weakest_subject": None,
        "student_rows": [],
        "subject_rows": [],
        "error_rows": [],
        "raw_preview": "",
        "raw_payload": "",
    }


def _guard_roundtrip_payload(payload: str) -> None:
    if len(payload.encode("utf-8")) <= MAX_ROUNDTRIP_PAYLOAD_BYTES:
        return

    raise ValueError(
        "The uploaded gazette is too large to safely round-trip through the "
        "browser download flow on Vercel. Split the TXT file into smaller "
        f"batches or lower it below about {_format_mib(MAX_UPLOAD_BYTES)}."
    )


def _build_analysis_context(raw_text: str, source_name: str, school_name: str, output_name: str) -> Dict[str, object]:
    context = _default_context()
    subject_master = _subject_master()
    raw_payload = _encode_payload(raw_text)
    _guard_roundtrip_payload(raw_payload)
    context.update(
        {
            "source_name": source_name,
            "school_name": school_name,
            "output_name": output_name,
            "raw_preview": raw_text[:RAW_PREVIEW_LIMIT],
            "raw_payload": raw_payload,
        }
    )

    students, errors = _parse_gazette_text(raw_text)
    context["error_rows"] = _prepare_error_rows(errors)

    if not students:
        context["error_message"] = "The file was read, but no student rows could be parsed."
        return context

    student_df, all_codes = build_student_dataframe(students, subject_master)
    subject_df = compute_subject_analysis(students, all_codes, subject_master)
    summary = compute_summary(students)

    context["has_analysis"] = True
    context["download_ready"] = True
    context["summary"] = summary
    context["metrics"] = [
        {
            "label": "Candidates",
            "value": str(summary["Total Candidates"]),
            "note": f'{summary["Male"]} boys and {summary["Female"]} girls in the parsed batch.',
            "tone": "gold",
        },
        {
            "label": "Pass Rate",
            "value": f'{summary["Pass %"]:.2f}%',
            "note": _pass_rate_note(summary),
            "tone": "forest",
        },
        {
            "label": "Subjects",
            "value": str(len(all_codes)),
            "note": "Unique subjects discovered directly from the uploaded gazette.",
            "tone": "ink",
        },
        {
            "label": "Parser Notes",
            "value": str(len(errors)),
            "note": "Warnings and hard parser issues surfaced during intake.",
            "tone": "gold",
        },
    ]
    context["toppers"] = _prepare_toppers(student_df)
    context["result_breakdown"] = _result_breakdown(summary)
    context["strongest_subject"] = _subject_spotlight(subject_df, strongest=True)
    context["weakest_subject"] = _subject_spotlight(subject_df, strongest=False)
    context["student_rows"] = _coerce_student_preview(student_df)
    context["subject_rows"] = _prepare_subject_rows(subject_df)
    return context


def _submitted_payload() -> Tuple[str, str, str, str]:
    action = request.form.get("action", "analyze")

    if action == "sample":
        try:
            raw_text = _sample_text()
        except FileNotFoundError as exc:
            raise ValueError("The bundled sample gazette file is unavailable.") from exc
        source_name = "sample_gazette.txt"
    else:
        uploaded_file = request.files.get("gazette_file")
        if uploaded_file is None or not uploaded_file.filename:
            raise ValueError("Upload a CBSE gazette TXT file or use the sample mode.")
        raw_text = uploaded_file.read().decode("utf-8", errors="replace")
        source_name = uploaded_file.filename

    suggested_school = _detect_school_name(raw_text) or "CBSE Results 2026"
    school_name = (request.form.get("school_name") or "").strip() or suggested_school
    suggested_output = f"{Path(source_name).stem}_analysis.xlsx"
    output_name = _ensure_output_name((request.form.get("output_name") or "").strip() or suggested_output)
    return raw_text, source_name, school_name, output_name


@app.get("/")
@app.get("/cbse-result-analyzer")
def home():
    try:
        return render_template("index.html", page=_default_context())
    except Exception:
        app.logger.exception("Failed to render home page.")
        raise


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "resource_report": _resource_report(),
    }


@app.get("/favicon.ico")
@app.get("/cbse-result-analyzer/favicon.ico")
def favicon():
    return ("", 204)


@app.post("/")
@app.post("/cbse-result-analyzer")
def analyze():
    status_code = 200
    try:
        raw_text, source_name, school_name, output_name = _submitted_payload()
        page = _build_analysis_context(raw_text, source_name, school_name, output_name)
    except RequestEntityTooLarge:
        page = _error_page(_size_limit_message())
        status_code = 413
    except ValueError as exc:
        page = _error_page(str(exc))
    except Exception:
        app.logger.exception("Unexpected failure while analyzing gazette input.")
        page = _error_page("The analyzer hit an unexpected error while processing the file.")

    return render_template("index.html", page=page), status_code


@app.post("/download")
@app.post("/cbse-result-analyzer/download")
def download_workbook():
    try:
        raw_payload = request.form.get("raw_payload", "")
        if not raw_payload:
            abort(400, "Missing workbook payload.")

        raw_text = _decode_payload(raw_payload)
        school_name = (request.form.get("school_name") or "").strip() or _detect_school_name(raw_text) or "CBSE Results 2026"
        output_name = _ensure_output_name(request.form.get("output_name", "CBSE_Result_Analysis.xlsx"))

        students, errors = _parse_gazette_text(raw_text)
        if not students:
            abort(400, "No students could be parsed from the submitted payload.")

        workbook_bytes = export_excel_bytes(students, errors, _subject_master(), school_name)
        return send_file(
            BytesIO(workbook_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=output_name,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        abort(400, str(exc))
    except Exception:
        app.logger.exception("Unexpected failure while building workbook download.")
        abort(500, "Workbook generation failed.")


@app.errorhandler(RequestEntityTooLarge)
def payload_too_large(_: RequestEntityTooLarge):
    return render_template("index.html", page=_error_page(_size_limit_message())), 413


if __name__ == "__main__":
    _run_dev_entrypoint()
