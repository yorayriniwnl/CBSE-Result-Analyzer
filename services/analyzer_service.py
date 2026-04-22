"""Shared analyzer services used by Flask, Streamlit, and CLI entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from config.loader import load_settings, load_subject_master
from parser.gazette_parser import ParseError, Student, parse_gazette_text
from transformer.calculator import compute_subject_analysis, compute_summary
from transformer.normalizer import build_normalized_table, to_display_table


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"
SUBJECTS_PATH = BASE_DIR / "config" / "subjects.json"
SAMPLE_PATH = BASE_DIR / "sample_gazette.txt"
DEFAULT_REPORT_YEAR = 2026
DEFAULT_SCHOOL_NAME = f"CBSE Results {DEFAULT_REPORT_YEAR}"
DEFAULT_OUTPUT_NAME = "CBSE_Result_Analysis.xlsx"


@dataclass(frozen=True)
class AnalysisBundle:
    students: List[Student]
    errors: List[ParseError]
    workbook_student_df: pd.DataFrame
    student_df: pd.DataFrame
    subject_df: pd.DataFrame
    summary: Dict[str, Any]
    all_codes: List[str]


@lru_cache(maxsize=1)
def get_settings() -> Dict[str, Any]:
    return load_settings(str(SETTINGS_PATH))


@lru_cache(maxsize=1)
def get_subject_master() -> Dict[str, str]:
    return load_subject_master(str(SUBJECTS_PATH))


@lru_cache(maxsize=1)
def get_sample_text() -> str:
    return SAMPLE_PATH.read_text(encoding="utf-8")


def detect_school_name(raw_text: str) -> Optional[str]:
    match = re.search(r"^SCHOOL\s*:\s*-\s*\d+\s+(.*)$", raw_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def ensure_output_name(name: str) -> str:
    clean_name = (name or "").strip() or DEFAULT_OUTPUT_NAME
    if not clean_name.lower().endswith(".xlsx"):
        clean_name = f"{clean_name}.xlsx"
    return clean_name


def pass_rate_note(summary: Dict[str, object]) -> str:
    note = (
        f'{summary["Passed"]} pass, {summary["Failed"]} fail, '
        f'{summary["Compartment"]} compartment'
    )
    other_results = int(summary.get("Other Results", 0) or 0)
    if other_results:
        note += f", {other_results} other"
    return f"{note}."


def result_breakdown_rows(summary: Dict[str, object]) -> List[Dict[str, int]]:
    rows = [
        {"Result": "PASS", "Count": int(summary["Passed"])},
        {"Result": "FAIL", "Count": int(summary["Failed"])},
        {"Result": "COMP", "Count": int(summary["Compartment"])},
        {"Result": "ABSENT", "Count": int(summary["Absent"])},
    ]
    other_results = int(summary.get("Other Results", 0) or 0)
    if other_results:
        rows.append({"Result": "OTHER", "Count": other_results})
    return rows


def select_topper_rows(student_df: pd.DataFrame) -> pd.DataFrame:
    sortable = student_df.copy()
    sortable["Percentage"] = pd.to_numeric(sortable["Percentage"], errors="coerce")
    sortable["Total Marks"] = pd.to_numeric(sortable["Total Marks"], errors="coerce")
    sortable["Result"] = sortable["Result"].astype(str).str.upper()

    eligible = sortable[sortable["Result"] == "PASS"]
    if eligible.empty:
        eligible = sortable[sortable["Percentage"].notna()]

    return eligible.sort_values(
        ["Percentage", "Total Marks"],
        ascending=[False, False],
        na_position="last",
    ).head(3)


def coerce_display_table(dataframe: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    view = dataframe.loc[:, [column for column in columns if column in dataframe.columns]].copy()
    if "Percentage" in view.columns:
        view["Percentage"] = pd.to_numeric(view["Percentage"], errors="coerce").map(
            lambda value: f"{value:.2f}%" if pd.notna(value) else ""
        )
    return view


def serialize_error_rows(errors: List[ParseError]) -> List[Dict[str, object]]:
    return [
        {
            "Level": error.level,
            "Roll No": error.roll,
            "Line No": error.line_no,
            "Message": error.message,
        }
        for error in errors
    ]


def analyze_gazette_text(
    raw_text: str,
    subject_master: Optional[Dict[str, str]] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> AnalysisBundle:
    resolved_settings = settings or get_settings()
    resolved_subject_master = subject_master or get_subject_master()

    students, errors = parse_gazette_text(raw_text, resolved_settings)
    summary = compute_summary(students)
    if not students:
        empty = pd.DataFrame()
        return AnalysisBundle(
            students=students,
            errors=errors,
            workbook_student_df=empty,
            student_df=empty,
            subject_df=empty,
            summary=summary,
            all_codes=[],
        )

    workbook_student_df, all_codes = build_normalized_table(
        students,
        resolved_subject_master,
    )
    student_df = to_display_table(workbook_student_df)
    subject_df = compute_subject_analysis(students, all_codes, resolved_subject_master)
    return AnalysisBundle(
        students=students,
        errors=errors,
        workbook_student_df=workbook_student_df,
        student_df=student_df,
        subject_df=subject_df,
        summary=summary,
        all_codes=all_codes,
    )
