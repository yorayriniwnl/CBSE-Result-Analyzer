"""Normalize parsed students into tabular forms used by the app and tests."""

import re
from typing import Dict, List, Tuple

import pandas as pd

from parser.gazette_parser import Student


def _sorted_subject_codes(students: List[Student]) -> List[str]:
    all_codes_set = set()
    for student in students:
        all_codes_set.update(student.subjects.keys())

    lang_codes = {"101", "184", "002", "001", "085", "021", "003"}
    math_codes = {"041", "241", "040"}
    science_codes = {"042", "043", "044", "086"}

    def sort_key(code: str) -> Tuple[int, str]:
        if code in lang_codes:
            return (0, code)
        if code in math_codes:
            return (1, code)
        if code in science_codes:
            return (2, code)
        return (3, code)

    return sorted(all_codes_set, key=sort_key)


def build_normalized_table(
    students: List[Student],
    subject_master: Dict[str, str],
) -> Tuple[pd.DataFrame, List[str]]:
    """Return a wide DataFrame for workbook export."""
    all_codes = _sorted_subject_codes(students)
    rows = []

    for student in students:
        row: Dict[str, object] = {
            "Roll No": student.roll,
            "Name": student.name,
            "Gender": student.gender,
        }

        total = 0
        count = 0
        for code in all_codes:
            label = subject_master.get(code, f"Sub-{code}")
            column_name = f"{label} ({code})"
            mark = student.subjects.get(code)
            row[column_name] = mark
            if mark is not None:
                total += mark
                count += 1

        row["Total Marks"] = total if count > 0 else None
        row["Subjects Appeared"] = count
        row["Percentage"] = round(total / count, 2) if count > 0 else None
        row["Result"] = student.result
        rows.append(row)

    return pd.DataFrame(rows), all_codes


def build_student_dataframe(
    students: List[Student],
    subject_master: Dict[str, str],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Backward-compatible wrapper expected by the tests.

    Subjects a student did not take are rendered as blank strings rather than
    null values so direct row comparisons stay simple.
    """
    dataframe, all_codes = build_normalized_table(students, subject_master)
    display_df = dataframe.copy()

    subject_columns = [
        column
        for column in display_df.columns
        if re.search(r"\(\d{3}\)$", str(column))
    ]
    if subject_columns:
        display_df[subject_columns] = display_df[subject_columns].fillna("")

    return display_df, all_codes
