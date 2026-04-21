"""
Unit tests for CBSE Gazette Analyzer
Run: python -m pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parser.gazette_parser import _extract_codes, _extract_marks, parse_gazette
from transformer.normalizer import build_student_dataframe
from transformer.calculator import compute_subject_analysis, compute_class_summary
from config.loader import load_subject_master, load_settings


SUBJECT_MASTER = load_subject_master()
SETTINGS = load_settings()


# ─── Parser Tests ─────────────────────────────────────────────────────────────

def test_extract_codes_basic():
    raw = "  184  002  086  087  041  417  "
    codes = _extract_codes(raw)
    assert codes == ["184", "002", "086", "087", "041", "417"]

def test_extract_codes_ignores_non_3digit():
    raw = "184 02 86 087"   # 02 and 86 are NOT 3-digit codes
    codes = _extract_codes(raw)
    assert "02"  not in codes
    assert "86"  not in codes
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
    assert marks[1] is None   # AA → absent
    assert marks[3] is None   # AB → absent
    assert marks[4] == 59

def test_parse_full_file():
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, errors = parse_gazette(sample, SETTINGS)
    assert len(students) == 12
    assert students[0]["roll"] == "2600001"
    assert students[0]["name"] == "AARAV KUMAR SHARMA"
    assert students[0]["result"] == "PASS"
    assert "184" in students[0]["subjects"]
    assert students[0]["subjects"]["184"] == 78

def test_parse_code_mark_mapping():
    """Verify subject codes map correctly to marks — not position-based."""
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, _ = parse_gazette(sample, SETTINGS)

    # Student 0: 184=078, 002=065, 086=072, 087=081, 041=059, 417=088
    s = students[0]
    assert s["subjects"]["184"] == 78
    assert s["subjects"]["002"] == 65
    assert s["subjects"]["041"] == 59
    assert s["subjects"]["417"] == 88


# ─── Normalizer Tests ─────────────────────────────────────────────────────────

def test_normalizer_columns_present():
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, _ = parse_gazette(sample, SETTINGS)
    df, codes = build_student_dataframe(students, SUBJECT_MASTER)

    assert "Roll No" in df.columns
    assert "Name"    in df.columns
    assert "Result"  in df.columns
    assert len(codes) > 0

def test_normalizer_no_position_bleed():
    """Student with different subject set must not get marks from another student."""
    sample = os.path.join(os.path.dirname(__file__), "..", "sample_gazette.txt")
    students, _ = parse_gazette(sample, SETTINGS)
    df, codes = build_student_dataframe(students, SUBJECT_MASTER)

    # Students 0 has 041, students 1 has 241 — they must not overlap
    row0 = df[df["Roll No"] == "2600001"].iloc[0]
    row1 = df[df["Roll No"] == "2600002"].iloc[0]

    math_col   = next((c for c in df.columns if "(041)" in c), None)
    mathb_col  = next((c for c in df.columns if "(241)" in c), None)

    if math_col:
        assert row1[math_col] == ""   # Student 2 has 241 not 041
    if mathb_col:
        assert row0[mathb_col] == ""  # Student 1 has 041 not 241


# ─── Calculator Tests ─────────────────────────────────────────────────────────

def test_average_excludes_absent():
    students = [
        {"roll": "001", "name": "A", "result": "PASS",
         "subjects": {"041": 80}, "line_no": 1},
        {"roll": "002", "name": "B", "result": "PASS",
         "subjects": {"041": 60}, "line_no": 3},
        {"roll": "003", "name": "C", "result": "ABSENT",
         "subjects": {"041": None}, "line_no": 5},   # Absent
    ]
    df = compute_subject_analysis(students, ["041"], SUBJECT_MASTER)
    row = df[df["Subject Code"] == "041"].iloc[0]

    # Average must be (80+60)/2 = 70.0 — NOT (80+60+0)/3 = 46.67
    assert row["Students Appeared"] == 2
    assert row["Average Marks"] == 70.0

def test_average_correct_denominator():
    """Only students who HAVE the subject should be in denominator."""
    students = [
        {"roll": "001", "name": "A", "result": "PASS",
         "subjects": {"041": 90, "184": 80}, "line_no": 1},
        {"roll": "002", "name": "B", "result": "PASS",
         "subjects": {"241": 70, "184": 60}, "line_no": 3},
    ]
    df = compute_subject_analysis(students, ["041", "241", "184"], SUBJECT_MASTER)

    math_row  = df[df["Subject Code"] == "041"].iloc[0]
    mathb_row = df[df["Subject Code"] == "241"].iloc[0]
    eng_row   = df[df["Subject Code"] == "184"].iloc[0]

    assert math_row["Students Appeared"]  == 1
    assert math_row["Average Marks"]      == 90.0
    assert mathb_row["Students Appeared"] == 1
    assert mathb_row["Average Marks"]     == 70.0
    assert eng_row["Students Appeared"]   == 2
    assert eng_row["Average Marks"]       == 70.0   # (80+60)/2

def test_class_summary():
    students = [
        {"roll": "001", "name": "A", "result": "PASS",   "subjects": {}, "line_no": 1},
        {"roll": "002", "name": "B", "result": "FAIL",   "subjects": {}, "line_no": 3},
        {"roll": "003", "name": "C", "result": "COMP",   "subjects": {}, "line_no": 5},
        {"roll": "004", "name": "D", "result": "ABSENT", "subjects": {}, "line_no": 7},
    ]
    s = compute_class_summary(students)
    assert s["Total Students"] == 4
    assert s["Passed"]         == 1
    assert s["Failed"]         == 1
    assert s["Compartment"]    == 1
    assert s["Pass %"]         == 25.0


if __name__ == "__main__":
    # Run all tests manually if pytest not available
    tests = [
        test_extract_codes_basic,
        test_extract_codes_ignores_non_3digit,
        test_extract_marks_numeric,
        test_extract_marks_with_absent,
        test_parse_full_file,
        test_parse_code_mark_mapping,
        test_normalizer_columns_present,
        test_normalizer_no_position_bleed,
        test_average_excludes_absent,
        test_average_correct_denominator,
        test_class_summary,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌  {t.__name__}: {e}")
            failed += 1

    print(f"\n  Results: {passed} passed, {failed} failed")
