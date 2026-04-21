"""Create the Excel workbook used by the analyzer."""

from io import BytesIO
import re
from typing import Dict, List

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from parser.gazette_parser import ParseError, Student
from transformer.calculator import compute_subject_analysis, compute_summary
from transformer.normalizer import build_normalized_table


CLR_HEADER_BG = "1F4E79"
CLR_HEADER_FG = "FFFFFF"
CLR_PASS = "1A5C38"
CLR_FAIL = "C00000"
CLR_COMP = "7F4C00"
CLR_ALT_ROW = "EBF2FF"
CLR_EMPTY_CELL = "F2F2F2"
CLR_GOOD_AVG = "C6EFCE"
CLR_BAD_AVG = "FFC7CE"
CLR_MID_AVG = "FFEB9C"

THIN = Side(style="thin", color="B0B0B0")
THIN_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _hdr_fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _font(bold: bool = False, color: str = "000000", size: int = 11) -> Font:
    return Font(name="Calibri", bold=bold, color=color, size=size)


def _auto_width(ws, min_width: int = 10, max_width: int = 40) -> None:
    for column in ws.columns:
        width = min_width
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            value = "" if cell.value is None else str(cell.value)
            width = max(width, len(value) + 2)
        ws.column_dimensions[column_letter].width = min(width, max_width)


def _write_student_sheet(wb: Workbook, dataframe: pd.DataFrame, title: str) -> None:
    ws = wb.active
    ws.title = "Student Data"

    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(dataframe.columns))
    ws["A1"].font = Font(name="Calibri", bold=True, size=13, color=CLR_HEADER_FG)
    ws["A1"].fill = _hdr_fill(CLR_HEADER_BG)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    headers = list(dataframe.columns)
    ws.append(headers)
    for index, _ in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=index)
        cell.font = _font(bold=True, color=CLR_HEADER_FG, size=10)
        cell.fill = _hdr_fill(CLR_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[2].height = 32

    result_column = headers.index("Result") + 1 if "Result" in headers else None
    mark_columns = [
        index + 1
        for index, header in enumerate(headers)
        if re.search(r"\(\d{3}\)$", str(header))
    ]

    for row_index, (_, row) in enumerate(dataframe.iterrows(), start=3):
        alternate = row_index % 2 == 0
        for column_index, column_name in enumerate(headers, start=1):
            value = row[column_name]
            cell = ws.cell(row=row_index, column=column_index)

            if value is None or (isinstance(value, float) and pd.isna(value)):
                cell.value = None
                if column_index in mark_columns:
                    cell.fill = _hdr_fill(CLR_EMPTY_CELL)
            else:
                cell.value = value

            cell.border = THIN_BORDER
            cell.font = _font(size=10)
            cell.alignment = Alignment(horizontal="center", vertical="center")

            if alternate and cell.fill.fgColor.rgb in ("00000000", "FFFFFFFF", "00FFFFFF"):
                cell.fill = _hdr_fill(CLR_ALT_ROW)

        if result_column:
            result_cell = ws.cell(row=row_index, column=result_column)
            result_value = str(row.get("Result", "")).upper()
            if result_value == "PASS":
                result_cell.font = _font(bold=True, color=CLR_PASS, size=10)
            elif result_value == "FAIL":
                result_cell.font = _font(bold=True, color=CLR_FAIL, size=10)
            elif result_value == "COMP":
                result_cell.font = _font(bold=True, color=CLR_COMP, size=10)

    ws.freeze_panes = "B3"
    ws.auto_filter.ref = ws.dimensions
    _auto_width(ws)

    if "Name" in headers:
        ws.column_dimensions[get_column_letter(headers.index("Name") + 1)].width = 28


def _write_analysis_sheet(wb: Workbook, dataframe: pd.DataFrame) -> None:
    ws = wb.create_sheet("Subject Analysis")
    headers = list(dataframe.columns)
    ws.append(headers)

    for index, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=index)
        cell.font = _font(bold=True, color=CLR_HEADER_FG)
        cell.fill = _hdr_fill(CLR_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 22

    average_column = headers.index("Average Marks") + 1 if "Average Marks" in headers else None

    for row_index, (_, row) in enumerate(dataframe.iterrows(), start=2):
        for column_index, column_name in enumerate(headers, start=1):
            value = row[column_name]
            cell = ws.cell(row=row_index, column=column_index)
            cell.value = value if not (isinstance(value, float) and pd.isna(value)) else None
            cell.border = THIN_BORDER
            cell.font = _font(size=10)
            cell.alignment = Alignment(horizontal="center")

        if average_column:
            average = row.get("Average Marks")
            average_cell = ws.cell(row=row_index, column=average_column)
            if average is not None and not (isinstance(average, float) and pd.isna(average)):
                if average >= 75:
                    average_cell.fill = _hdr_fill(CLR_GOOD_AVG)
                elif average < 40:
                    average_cell.fill = _hdr_fill(CLR_BAD_AVG)
                else:
                    average_cell.fill = _hdr_fill(CLR_MID_AVG)

    ws.freeze_panes = "A2"
    _auto_width(ws)


def _write_summary_sheet(wb: Workbook, summary: Dict, title: str) -> None:
    ws = wb.create_sheet("School Summary")

    ws.append([title])
    ws.merge_cells("A1:C1")
    ws["A1"].font = Font(name="Calibri", bold=True, size=13, color=CLR_HEADER_FG)
    ws["A1"].fill = _hdr_fill(CLR_HEADER_BG)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 22

    ws.append(["Metric", "Value"])
    for column_index in range(1, 3):
        cell = ws.cell(row=2, column=column_index)
        cell.font = _font(bold=True, color=CLR_HEADER_FG)
        cell.fill = _hdr_fill(CLR_HEADER_BG)
        cell.border = THIN_BORDER

    for row_index, (key, value) in enumerate(summary.items(), start=3):
        label_cell = ws.cell(row=row_index, column=1, value=key)
        label_cell.border = THIN_BORDER
        label_cell.font = _font(bold=True)

        value_cell = ws.cell(row=row_index, column=2, value=value)
        value_cell.border = THIN_BORDER
        value_cell.alignment = Alignment(horizontal="center")

    _auto_width(ws, min_width=18)


def _write_errors_sheet(wb: Workbook, errors: List[ParseError]) -> None:
    ws = wb.create_sheet("Parse Errors")
    headers = ["Level", "Roll No", "Line No", "Message"]
    ws.append(headers)

    for index, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=index)
        cell.font = _font(bold=True, color=CLR_HEADER_FG)
        cell.fill = _hdr_fill("7F0000" if errors else "1F4E79")
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="center")

    if not errors:
        ws.append(["No parse errors detected", "", "", ""])
    else:
        for row_index, error in enumerate(errors, start=2):
            row_data = [error.level, error.roll, error.line_no, error.message]
            for column_index, value in enumerate(row_data, start=1):
                cell = ws.cell(row=row_index, column=column_index, value=value)
                cell.border = THIN_BORDER
                if error.level == "ERROR":
                    cell.fill = _hdr_fill(CLR_BAD_AVG)
                elif error.level == "WARNING":
                    cell.fill = _hdr_fill(CLR_MID_AVG)

    _auto_width(ws)


def build_workbook(
    students: List[Student],
    errors: List[ParseError],
    subject_master: Dict,
    school_name: str = "CBSE Results 2026",
) -> Workbook:
    dataframe_students, all_codes = build_normalized_table(students, subject_master)
    dataframe_analysis = compute_subject_analysis(students, all_codes, subject_master)
    summary = compute_summary(students)

    workbook = Workbook()
    _write_student_sheet(workbook, dataframe_students, school_name)
    _write_analysis_sheet(workbook, dataframe_analysis)
    _write_summary_sheet(workbook, summary, school_name)
    _write_errors_sheet(workbook, errors)

    return workbook


def workbook_to_bytes(workbook: Workbook) -> bytes:
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export_excel_bytes(
    students: List[Student],
    errors: List[ParseError],
    subject_master: Dict,
    school_name: str = "CBSE Results 2026",
) -> bytes:
    workbook = build_workbook(students, errors, subject_master, school_name)
    return workbook_to_bytes(workbook)


def write_excel(
    students: List[Student],
    errors: List[ParseError],
    subject_master: Dict,
    output_path: str,
    school_name: str = "CBSE Results 2026",
) -> None:
    workbook = build_workbook(students, errors, subject_master, school_name)
    _, all_codes = build_normalized_table(students, subject_master)
    workbook.save(output_path)
    print(f"Saved: {output_path}")
    print(f"   Students : {len(students)}")
    print(f"   Subjects : {len(all_codes)}")
    print(f"   Errors   : {len(errors)}")
