"""Subject and class-level aggregations."""

from typing import Any, Dict, List, Union

import pandas as pd

from parser.gazette_parser import Student


StudentLike = Union[Student, Dict[str, Any]]


def _field(student: StudentLike, name: str, default: Any = None) -> Any:
    if isinstance(student, dict):
        return student.get(name, default)
    return getattr(student, name, default)


def compute_subject_analysis(
    students: List[StudentLike],
    all_codes: List[str],
    subject_master: Dict[str, str],
) -> pd.DataFrame:
    rows = []
    for code in all_codes:
        marks = []
        for student in students:
            subjects = _field(student, "subjects", {}) or {}
            mark = subjects.get(code)
            if mark is not None:
                marks.append(mark)

        if not marks:
            continue

        pass_count = sum(1 for mark in marks if mark >= 33)
        rows.append(
            {
                "Subject Code": code,
                "Subject Name": subject_master.get(code, f"Unknown ({code})"),
                "Students Appeared": len(marks),
                "Average Marks": round(sum(marks) / len(marks), 2),
                "Highest": max(marks),
                "Lowest": min(marks),
                "Pass Count": pass_count,
                "Pass %": round(pass_count / len(marks) * 100, 2),
            }
        )

    return pd.DataFrame(rows)


def compute_summary(students: List[StudentLike]) -> Dict[str, Any]:
    total = len(students)
    passed = sum(1 for student in students if _field(student, "result") == "PASS")
    failed = sum(1 for student in students if _field(student, "result") == "FAIL")
    comp = sum(1 for student in students if _field(student, "result") == "COMP")
    absent = sum(1 for student in students if _field(student, "result") == "ABSENT")
    male = sum(1 for student in students if _field(student, "gender") == "M")
    female = sum(1 for student in students if _field(student, "gender") == "F")

    return {
        "Total Candidates": total,
        "Passed": passed,
        "Failed": failed,
        "Compartment": comp,
        "Absent": absent,
        "Male": male,
        "Female": female,
        "Pass %": round(passed / total * 100, 2) if total else 0,
    }


def compute_class_summary(students: List[StudentLike]) -> Dict[str, Any]:
    """Backward-compatible summary layout used by the tests."""
    summary = compute_summary(students)
    return {
        "Total Students": summary["Total Candidates"],
        "Passed": summary["Passed"],
        "Failed": summary["Failed"],
        "Compartment": summary["Compartment"],
        "Absent": summary["Absent"],
        "Pass %": summary["Pass %"],
    }
