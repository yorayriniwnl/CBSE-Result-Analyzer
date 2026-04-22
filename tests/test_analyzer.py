"""
Unit tests for CBSE Gazette Analyzer.
Run:
    python -m pytest tests/ -v
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.loader import load_settings, load_subject_master
from parser.gazette_parser import _extract_codes, _extract_marks, parse_gazette, parse_gazette_text
from services.analyzer_service import analyze_gazette_text, get_sample_text
from transformer.calculator import compute_class_summary, compute_subject_analysis, compute_summary
from transformer.normalizer import build_student_dataframe


SUBJECT_MASTER = load_subject_master()
SETTINGS = load_settings()


def test_extract_codes_basic():
    raw = "  184  002  086  087  041  417  "
    codes = _extract_codes(raw)
    assert codes == ["184", "002", "086", "087", "041", "417"]


def test_extract_codes_ignores_non_3digit():
    raw = "184 02 86 087"
    codes = _extract_codes(raw)
    assert "02" not in codes
    assert "86" not in codes
    assert "184" in codes
    assert "087" in codes


def test_extract_marks_numeric():
    raw = "   078  065  072  081  059  088  "
    marks = _extract_marks(raw)
    assert marks == [78, 65, 72, 81, 59, 88]


def test_extract_marks_with_absent():
    raw = "   078  AA  072  AB  059  088  "
    marks = _extract_marks(raw)
    assert marks[0] == 78
    assert marks[1] is None
    assert marks[3] is None
    assert marks[4] == 59


def test_parse_full_file():
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, errors = parse_gazette(sample, SETTINGS)
    assert len(students) == 12
    assert len(errors) == 0
    assert students[0]["roll"] == "29200001"
    assert students[0]["name"] == "AARAV KUMAR SHARMA"
    assert students[0]["result"] == "PASS"
    assert "184" in students[0]["subjects"]
    assert students[0]["subjects"]["184"] == 78


def test_parse_code_mark_mapping():
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, _ = parse_gazette(sample, SETTINGS)

    student = students[0]
    assert student["subjects"]["184"] == 78
    assert student["subjects"]["002"] == 65
    assert student["subjects"]["041"] == 59
    assert student["subjects"]["417"] == 88


def test_parse_text_matches_file_parser():
    sample = Path(os.path.dirname(__file__)) / ".." / "sample_gazette.txt"
    raw_text = sample.read_text(encoding="utf-8")

    file_students, file_errors = parse_gazette(str(sample), SETTINGS)
    text_students, text_errors = parse_gazette_text(raw_text, SETTINGS)

    assert text_students == file_students
    assert text_errors == file_errors


def test_shared_analysis_bundle_smoke():
    bundle = analyze_gazette_text(get_sample_text())

    assert len(bundle.students) == 12
    assert len(bundle.errors) == 0
    assert bundle.summary["Total Candidates"] == 12
    assert len(bundle.all_codes) == 10
    assert "Roll No" in bundle.student_df.columns
    assert "Average Marks" in bundle.subject_df.columns


def test_normalizer_columns_present():
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, _ = parse_gazette(sample, SETTINGS)
    dataframe, codes = build_student_dataframe(students, SUBJECT_MASTER)

    assert "Roll No" in dataframe.columns
    assert "Name" in dataframe.columns
    assert "Result" in dataframe.columns
    assert len(codes) > 0


def test_normalizer_no_position_bleed():
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, _ = parse_gazette(sample, SETTINGS)
    dataframe, _ = build_student_dataframe(students, SUBJECT_MASTER)

    row0 = dataframe[dataframe["Roll No"] == "29200001"].iloc[0]
    row1 = dataframe[dataframe["Roll No"] == "29200002"].iloc[0]

    math_col = next((column for column in dataframe.columns if "(041)" in column), None)
    mathb_col = next((column for column in dataframe.columns if "(241)" in column), None)

    if math_col:
        assert row1[math_col] == ""
    if mathb_col:
        assert row0[mathb_col] == ""


def test_average_excludes_absent():
    students = [
        {"roll": "001", "name": "A", "result": "PASS", "subjects": {"041": 80}, "line_no": 1},
        {"roll": "002", "name": "B", "result": "PASS", "subjects": {"041": 60}, "line_no": 3},
        {"roll": "003", "name": "C", "result": "ABSENT", "subjects": {"041": None}, "line_no": 5},
    ]
    dataframe = compute_subject_analysis(students, ["041"], SUBJECT_MASTER)
    row = dataframe[dataframe["Subject Code"] == "041"].iloc[0]

    assert row["Students Appeared"] == 2
    assert row["Average Marks"] == 70.0


def test_average_correct_denominator():
    students = [
        {
            "roll": "001",
            "name": "A",
            "result": "PASS",
            "subjects": {"041": 90, "184": 80},
            "line_no": 1,
        },
        {
            "roll": "002",
            "name": "B",
            "result": "PASS",
            "subjects": {"241": 70, "184": 60},
            "line_no": 3,
        },
    ]
    dataframe = compute_subject_analysis(students, ["041", "241", "184"], SUBJECT_MASTER)

    math_row = dataframe[dataframe["Subject Code"] == "041"].iloc[0]
    mathb_row = dataframe[dataframe["Subject Code"] == "241"].iloc[0]
    eng_row = dataframe[dataframe["Subject Code"] == "184"].iloc[0]

    assert math_row["Students Appeared"] == 1
    assert math_row["Average Marks"] == 90.0
    assert mathb_row["Students Appeared"] == 1
    assert mathb_row["Average Marks"] == 70.0
    assert eng_row["Students Appeared"] == 2
    assert eng_row["Average Marks"] == 70.0


def test_class_summary():
    students = [
        {"roll": "001", "name": "A", "result": "PASS", "subjects": {}, "line_no": 1},
        {"roll": "002", "name": "B", "result": "FAIL", "subjects": {}, "line_no": 3},
        {"roll": "003", "name": "C", "result": "COMP", "subjects": {}, "line_no": 5},
        {"roll": "004", "name": "D", "result": "ABSENT", "subjects": {}, "line_no": 7},
    ]
    summary = compute_class_summary(students)
    assert summary["Total Students"] == 4
    assert summary["Passed"] == 1
    assert summary["Failed"] == 1
    assert summary["Compartment"] == 1
    assert summary["Pass %"] == 25.0


def test_summary_tracks_other_result_buckets():
    students = [
        {"roll": "001", "name": "A", "result": "PASS", "gender": "M", "subjects": {}, "line_no": 1},
        {"roll": "002", "name": "B", "result": "UFM", "gender": "F", "subjects": {}, "line_no": 3},
        {"roll": "003", "name": "C", "result": "RWH", "gender": "F", "subjects": {}, "line_no": 5},
    ]

    summary = compute_summary(students)
    class_summary = compute_class_summary(students)

    assert summary["Total Candidates"] == 3
    assert summary["Passed"] == 1
    assert summary["Other Results"] == 2
    assert class_summary["Other Results"] == 2
    assert summary["Pass %"] == 33.33
