"""
CBSE Gazette → Excel Analyzer
Usage:
    python main.py <gazette.txt> [output.xlsx] [--school "School Name"]
"""

import json
import sys
from pathlib import Path

# Make sure sub-packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from parser.gazette_parser import parse_gazette
from exporter.excel_writer import write_excel


def main():
    import argparse
    ap = argparse.ArgumentParser(description="CBSE Gazette TXT → Excel Analyzer")
    ap.add_argument("input",  help="Path to CBSE gazette .txt file")
    ap.add_argument("output", nargs="?", default="CBSE_Result_Analysis.xlsx",
                    help="Output Excel file path")
    ap.add_argument("--school", default="CBSE Results 2026",
                    help="School name for title row")
    args = ap.parse_args()

    # Load subject master
    config_path = Path(__file__).parent / "config" / "subjects.json"
    with open(config_path) as f:
        subject_master = json.load(f)

    print(f"📂 Parsing: {args.input}")
    students, errors = parse_gazette(args.input)

    if not students:
        print("❌ No students parsed. Check the file format.")
        sys.exit(1)

    print(f"   Found {len(students)} students, {len(errors)} parse issues")

    print(f"📊 Generating Excel: {args.output}")
    write_excel(
        students=students,
        errors=errors,
        subject_master=subject_master,
        output_path=args.output,
        school_name=args.school
    )


if __name__ == "__main__":
    main()
