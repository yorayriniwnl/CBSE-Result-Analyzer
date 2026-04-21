"""Primary Flask entrypoint for local runs and Vercel deployments."""

from __future__ import annotations

import base64
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import Flask, abort, render_template, request, send_file

from config.loader import load_settings, load_subject_master
from exporter.excel_writer import export_excel_bytes
from parser.gazette_parser import ParseError, Student, parse_gazette
from transformer.calculator import compute_subject_analysis, compute_summary
from transformer.normalizer import build_student_dataframe


BASE_DIR = Path(__file__).parent
SETTINGS = load_settings(str(BASE_DIR / "config" / "settings.yaml"))
SUBJECT_MASTER = load_subject_master(str(BASE_DIR / "config" / "subjects.json"))
SAMPLE_TEXT = (BASE_DIR / "sample_gazette.txt").read_text(encoding="utf-8")
RAW_PREVIEW_LIMIT = 12000
STUDENT_PREVIEW_LIMIT = 18
SUBJECT_PREVIEW_LIMIT = 18

app = Flask(__name__)


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
    return base64.b64encode(raw_text.encode("utf-8")).decode("ascii")


def _decode_payload(payload: str) -> str:
    try:
        return base64.b64decode(payload.encode("ascii")).decode("utf-8")
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
        return parse_gazette(temp_path, SETTINGS)
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
    toppers = sortable.sort_values(
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


def _build_analysis_context(raw_text: str, source_name: str, school_name: str, output_name: str) -> Dict[str, object]:
    context = _default_context()
    context.update(
        {
            "source_name": source_name,
            "school_name": school_name,
            "output_name": output_name,
            "raw_preview": raw_text[:RAW_PREVIEW_LIMIT],
            "raw_payload": _encode_payload(raw_text),
        }
    )

    students, errors = _parse_gazette_text(raw_text)
    context["error_rows"] = _prepare_error_rows(errors)

    if not students:
        context["error_message"] = "The file was read, but no student rows could be parsed."
        return context

    student_df, all_codes = build_student_dataframe(students, SUBJECT_MASTER)
    subject_df = compute_subject_analysis(students, all_codes, SUBJECT_MASTER)
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
            "note": f'{summary["Passed"]} pass, {summary["Failed"]} fail, {summary["Compartment"]} compartment.',
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
        raw_text = SAMPLE_TEXT
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
def home():
    return render_template("index.html", page=_default_context())


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


@app.post("/")
def analyze():
    try:
        raw_text, source_name, school_name, output_name = _submitted_payload()
        page = _build_analysis_context(raw_text, source_name, school_name, output_name)
    except ValueError as exc:
        page = _default_context()
        page["error_message"] = str(exc)

    return render_template("index.html", page=page)


@app.post("/download")
def download_workbook():
    raw_payload = request.form.get("raw_payload", "")
    if not raw_payload:
        abort(400, "Missing workbook payload.")

    try:
        raw_text = _decode_payload(raw_payload)
    except ValueError as exc:
        abort(400, str(exc))

    school_name = (request.form.get("school_name") or "").strip() or _detect_school_name(raw_text) or "CBSE Results 2026"
    output_name = _ensure_output_name(request.form.get("output_name", "CBSE_Result_Analysis.xlsx"))

    students, errors = _parse_gazette_text(raw_text)
    if not students:
        abort(400, "No students could be parsed from the submitted payload.")

    workbook_bytes = export_excel_bytes(students, errors, SUBJECT_MASTER, school_name)
    return send_file(
        BytesIO(workbook_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=output_name,
    )


if __name__ == "__main__":
    app.run(debug=True)
