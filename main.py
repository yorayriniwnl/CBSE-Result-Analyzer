"""
CBSE Gazette to Excel Analyzer
Usage:
    python main.py <gazette.txt> [output.xlsx] [--school "School Name"]
"""

import sys
from pathlib import Path

# Make sure sub-packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from config.loader import load_settings, load_subject_master
from exporter.excel_writer import write_excel
from parser.gazette_parser import parse_gazette


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
        default="CBSE Results 2026",
        help="School name for title row",
    )
    args = parser.parse_args()

    config_dir = Path(__file__).parent / "config"
    subject_master = load_subject_master(str(config_dir / "subjects.json"))
    settings = load_settings(str(config_dir / "settings.yaml"))

    print(f"Parsing: {args.input}")
    students, errors = parse_gazette(args.input, settings)

    if not students:
        print("ERROR: No students parsed. Check the file format.")
        sys.exit(1)

    print(f"   Found {len(students)} students, {len(errors)} parse issues")
    print(f"Generating Excel: {args.output}")
    write_excel(
        students=students,
        errors=errors,
        subject_master=subject_master,
        output_path=args.output,
        school_name=args.school,
    )


if __name__ == "__main__":
    main()
