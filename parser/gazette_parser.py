"""
CBSE Gazette parser.

Expected format:
  29172045   F ADITI KUMARI      184    002    241    086    087    417    PASS
                                 078    096    070    079    096    084
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_ABSENT_MARKERS = {"AA", "AB", "---", "XX"}


@dataclass
class Student:
    roll: str
    name: str
    gender: str  # M / F / T
    result: str
    comp_subject: Optional[str]
    subjects: Dict[str, Optional[int]]  # {code: mark}
    line_no: int

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class ParseError:
    level: str  # WARNING / ERROR
    roll: str
    line_no: int
    message: str

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


STUDENT_LINE_RE = re.compile(
    r"^(\d{7,8})\s+"                         # Roll number
    r"([FMT])\s+"                            # Gender
    r"([A-Z][A-Z .'/-]+?)\s{3,}"             # Name
    r"((?:\d{3}\s+){2,7}\d{3})"              # Subject codes
    r"\s+"
    r"(PASS|FAIL|COMP|ABSENT|UFM|RWH|XXX|ESSENTIAL\s+REPEAT)",
    re.IGNORECASE,
)

MARKS_LINE_RE = re.compile(r"^\s{10,}([A-Z0-9\-\s]+)$", re.IGNORECASE)
SUMMARY_LINE_RE = re.compile(r"TOTAL\s+CANDIDATES", re.IGNORECASE)


def _extract_codes(raw: str) -> List[str]:
    """Extract 3-digit subject codes from codes section."""
    return re.findall(r"\b(\d{3})\b", raw)


def _extract_marks(
    line: str,
    absent_markers: Optional[List[str]] = None,
) -> List[Optional[int]]:
    """Extract numeric marks and absent markers from a marks line."""
    markers = {marker.upper() for marker in (absent_markers or DEFAULT_ABSENT_MARKERS)}
    marks: List[Optional[int]] = []

    for token in re.findall(r"[A-Z]+|\d{1,3}|---", line.upper()):
        if token in markers:
            marks.append(None)
        elif re.fullmatch(r"\d{1,3}", token):
            marks.append(int(token))

    return marks


def _normalized_lines(raw_text: str) -> List[str]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return normalized.split("\n")


def _parse_lines(
    lines: List[str],
    settings: Optional[Dict[str, Any]] = None,
) -> tuple[List[Student], List[ParseError]]:
    students: List[Student] = []
    errors: List[ParseError] = []
    settings = settings or {}
    absent_markers = settings.get("absent_markers", list(DEFAULT_ABSENT_MARKERS))

    i = 0
    while i < len(lines):
        line1 = lines[i]

        if not line1.strip() or SUMMARY_LINE_RE.search(line1):
            i += 1
            continue

        student_match = STUDENT_LINE_RE.match(line1)
        if not student_match:
            i += 1
            continue

        roll = student_match.group(1).strip()
        gender = student_match.group(2).strip().upper()
        name = student_match.group(3).strip()
        codes_raw = student_match.group(4).strip()
        result = re.sub(r"\s+", " ", student_match.group(5).strip().upper())

        subject_codes = _extract_codes(codes_raw)

        marks_line_idx = None
        for j in range(i + 1, min(i + 4, len(lines))):
            candidate = lines[j]
            if MARKS_LINE_RE.match(candidate):
                marks_line_idx = j
                break
            if candidate.strip() == "":
                continue
            break

        if marks_line_idx is None:
            errors.append(
                ParseError("ERROR", roll, i + 1, "No marks line found after student line")
            )
            i += 1
            continue

        marks = _extract_marks(lines[marks_line_idx], absent_markers=absent_markers)

        if len(subject_codes) != len(marks):
            errors.append(
                ParseError(
                    "ERROR",
                    roll,
                    i + 1,
                    f"Code/mark count mismatch: {len(subject_codes)} codes vs {len(marks)} "
                    f"marks. Codes={subject_codes} Marks={marks}",
                )
            )
            i = marks_line_idx + 1
            continue

        subject_marks = dict(zip(subject_codes, marks))

        for code, mark in subject_marks.items():
            if mark is not None and not (0 <= mark <= 100):
                errors.append(
                    ParseError(
                        "WARNING",
                        roll,
                        i + 1,
                        f"Mark {mark} for code {code} out of range 0-100",
                    )
                )

        students.append(
            Student(
                roll=roll,
                name=name,
                gender=gender,
                result=result,
                comp_subject=None,
                subjects=subject_marks,
                line_no=i + 1,
            )
        )

        i = marks_line_idx + 1

    seen: Dict[str, int] = {}
    for student in students:
        if student.roll in seen:
            errors.append(
                ParseError(
                    "ERROR",
                    student.roll,
                    student.line_no,
                    f"Duplicate roll (first at line {seen[student.roll]})",
                )
            )
        else:
            seen[student.roll] = student.line_no

    return students, errors


def parse_gazette(
    filepath: str,
    settings: Optional[Dict[str, Any]] = None,
) -> tuple[List[Student], List[ParseError]]:
    """
    Parse a CBSE Gazette TXT file and return (students, errors).

    The optional settings dictionary currently supports `absent_markers`.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as handle:
        raw = handle.read()

    return parse_gazette_text(raw, settings)


def parse_gazette_text(
    raw_text: str,
    settings: Optional[Dict[str, Any]] = None,
) -> tuple[List[Student], List[ParseError]]:
    """Parse gazette content that is already loaded in memory."""
    return _parse_lines(_normalized_lines(raw_text), settings)
