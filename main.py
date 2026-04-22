"""
CBSE Gazette to Excel Analyzer
Usage:
    python main.py <gazette.txt> [output.xlsx] [--school "School Name"]
"""

from pathlib import Path

from exporter.excel_writer import write_excel
from services.analyzer_service import (
    DEFAULT_SCHOOL_NAME,
    analyze_gazette_text,
    get_subject_master,
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CBSE Gazette TXT to Excel Analyzer")
    parser.add_argument("input", help="Path to CBSE gazette .txt file")
    parser.add_argument(
        "output",
        nargs="?",
        default="CBSE_Result_Analysis.xlsx",
        help="Output Excel file path",
    )
    parser.add_argument(
        "--school",
        default=DEFAULT_SCHOOL_NAME,
        help="School name for title row",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    raw_text = input_path.read_text(encoding="utf-8", errors="replace")
    subject_master = get_subject_master()

    print(f"Parsing: {args.input}")
    analysis = analyze_gazette_text(raw_text, subject_master=subject_master)

    if not analysis.students:
        print("ERROR: No students parsed. Check the file format.")
        raise SystemExit(1)

    print(f"   Found {len(analysis.students)} students, {len(analysis.errors)} parse issues")
    print(f"Generating Excel: {args.output}")
    write_excel(
        students=analysis.students,
        errors=analysis.errors,
        subject_master=subject_master,
        output_path=args.output,
        school_name=args.school,
    )


if __name__ == "__main__":
    main()
