"""Primary Flask entrypoint for local runs and Vercel deployments."""

from __future__ import annotations

import base64
import html
import logging
import os
import sys
import threading
import zlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import Flask, abort, has_request_context, render_template, request, send_file
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from exporter.excel_writer import export_excel_bytes
from parser.gazette_parser import ParseError
from services.analyzer_service import (
    DEFAULT_OUTPUT_NAME,
    DEFAULT_SCHOOL_NAME,
    analyze_gazette_text,
    detect_school_name,
    ensure_output_name,
    get_sample_text,
    get_settings,
    get_subject_master,
    pass_rate_note,
    select_topper_rows,
    serialize_error_rows,
)


BASE_DIR = Path(__file__).parent
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


def _settings() -> Dict:
    return get_settings()


def _subject_master() -> Dict[str, str]:
    return get_subject_master()


def _sample_text() -> str:
    return get_sample_text()


def _error_page(message: str) -> Dict[str, object]:
    page = _default_context()
    page["error_message"] = message
    return page


def _render_page(page: Dict[str, object], status_code: int = 200):
    try:
        return render_template("index.html", page=page), status_code
    except Exception:
        app.logger.exception("Failed to render HTML page.")
        message = html.escape(
            str(
                page.get("error_message")
                or "The analyzer interface is temporarily unavailable."
            )
        )
        fallback_html = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CBSE Analyzer</title>
</head>
<body style="margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f8f3ed;color:#101522;">
    <main style="max-width:720px;margin:8vh auto;padding:24px;">
        <h1 style="margin:0 0 12px;">CBSE Analyzer</h1>
        <p style="margin:0 0 10px;line-height:1.6;">{message}</p>
        <p style="margin:0;line-height:1.6;">Refresh the page or check <code>/healthz</code> for a quick runtime status check.</p>
    </main>
</body>
</html>"""
        fallback_status = status_code if status_code >= 400 else 500
        return fallback_html, fallback_status, {"Content-Type": "text/html; charset=utf-8"}


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


def _can_use_dev_reloader() -> bool:
    return threading.current_thread() is threading.main_thread()


def _env_flag(name: str) -> Optional[bool]:
    value = (os.getenv(name) or "").strip().lower()
    if not value:
        return None
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _should_use_dev_reloader() -> bool:
    configured = _env_flag("FLASK_DEV_USE_RELOADER")
    if configured is not None:
        return configured

    return os.name != "nt"


def _configured_dev_reloader_type() -> Optional[str]:
    configured = (os.getenv("FLASK_DEV_RELOADER_TYPE") or "").strip().lower()
    if configured in {"auto", "stat", "watchdog"}:
        return configured

    return None


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

    run_options = {"debug": True}
    if not _can_use_dev_reloader():
        app.logger.info(
            "Flask dev reloader disabled because app.py is running outside the main thread."
        )
        run_options["use_reloader"] = False
    elif not _should_use_dev_reloader():
        app.logger.info(
            "Flask dev reloader disabled for this environment. "
            "Set FLASK_DEV_USE_RELOADER=1 to opt in."
        )
        run_options["use_reloader"] = False
    else:
        reloader_type = _configured_dev_reloader_type()
        if reloader_type:
            run_options["reloader_type"] = reloader_type

    app.run(**run_options)


def _resource_report() -> Dict[str, object]:
    report: Dict[str, object] = {
        "base_dir": str(BASE_DIR),
        "settings_path": str(BASE_DIR / "config" / "settings.yaml"),
        "subjects_path": str(BASE_DIR / "config" / "subjects.json"),
        "sample_path": str(BASE_DIR / "sample_gazette.txt"),
        "templates_path": str(BASE_DIR / "templates"),
        "settings_exists": (BASE_DIR / "config" / "settings.yaml").exists(),
        "subjects_exists": (BASE_DIR / "config" / "subjects.json").exists(),
        "sample_exists": (BASE_DIR / "sample_gazette.txt").exists(),
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
    return detect_school_name(raw_text)


def _ensure_output_name(name: str) -> str:
    return ensure_output_name(name)


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
    toppers = select_topper_rows(student_df)

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
    rows = serialize_error_rows(errors)
    return [
        {
            "level": str(row["Level"]),
            "roll": str(row["Roll No"]),
            "line_no": str(row["Line No"]),
            "message": str(row["Message"]),
        }
        for row in rows
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
    return pass_rate_note(summary)


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
        "school_name": DEFAULT_SCHOOL_NAME,
        "output_name": DEFAULT_OUTPUT_NAME,
        "github_url": PUBLIC_GITHUB_URL,
        "github_label": PUBLIC_GITHUB_LABEL,
        "vercel_url": PUBLIC_VERCEL_URL,
        "vercel_label": PUBLIC_VERCEL_LABEL,
        "home_url": _public_route("/"),
        "download_url": _public_route("/download"),
        "error_message": None,
        "download_ready": False,
        "summary": {
            "Total Candidates": 0,
            "Male": 0,
            "Female": 0,
            "Passed": 0,
            "Failed": 0,
            "Compartment": 0,
            "Absent": 0,
            "Other Results": 0,
            "Pass %": 0.0,
        },
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

    analysis = analyze_gazette_text(
        raw_text,
        subject_master=_subject_master(),
        settings=_settings(),
    )
    context["error_rows"] = _prepare_error_rows(analysis.errors)

    if not analysis.students:
        context["error_message"] = "The file was read, but no student rows could be parsed."
        return context

    student_df = analysis.student_df
    subject_df = analysis.subject_df
    summary = analysis.summary

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
            "value": str(len(analysis.all_codes)),
            "note": "Unique subjects discovered directly from the uploaded gazette.",
            "tone": "ink",
        },
        {
            "label": "Parser Notes",
            "value": str(len(analysis.errors)),
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

    suggested_school = _detect_school_name(raw_text) or DEFAULT_SCHOOL_NAME
    school_name = (request.form.get("school_name") or "").strip() or suggested_school
    suggested_output = f"{Path(source_name).stem}_analysis.xlsx"
    output_name = _ensure_output_name((request.form.get("output_name") or "").strip() or suggested_output)
    return raw_text, source_name, school_name, output_name


@app.get("/")
@app.get("/cbse-result-analyzer")
def home():
    return _render_page(_default_context())


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

    return _render_page(page, status_code)


@app.post("/download")
@app.post("/cbse-result-analyzer/download")
def download_workbook():
    try:
        raw_payload = request.form.get("raw_payload", "")
        if not raw_payload:
            abort(400, "Missing workbook payload.")

        raw_text = _decode_payload(raw_payload)
        school_name = (
            (request.form.get("school_name") or "").strip()
            or _detect_school_name(raw_text)
            or DEFAULT_SCHOOL_NAME
        )
        output_name = _ensure_output_name(request.form.get("output_name", DEFAULT_OUTPUT_NAME))

        analysis = analyze_gazette_text(
            raw_text,
            subject_master=_subject_master(),
            settings=_settings(),
        )
        if not analysis.students:
            abort(400, "No students could be parsed from the submitted payload.")

        workbook_bytes = export_excel_bytes(
            analysis.students,
            analysis.errors,
            _subject_master(),
            school_name,
        )
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
    return _render_page(_error_page(_size_limit_message()), 413)


if __name__ == "__main__":
    _run_dev_entrypoint()
