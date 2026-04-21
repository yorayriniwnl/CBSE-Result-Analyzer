"""
Calculator: builds subject-wise analysis DataFrame.
Key rule: denominator = only students who appeared in that subject (mark is not None).
"""

from typing import Dict, List

import pandas as pd

from parser.gazette_parser import Student


def compute_subject_analysis(
    students: List[Student],
    all_codes: List[str],
    subject_master: Dict[str, str]
) -> pd.DataFrame:
    rows = []
    for code in all_codes:
        marks = [
            s.subjects[code]
            for s in students
            if code in s.subjects and s.subjects[code] is not None
        ]
        if not marks:
            continue

        pass_count = sum(1 for m in marks if m >= 33)
        rows.append({
            'Subject Code': code,
            'Subject Name': subject_master.get(code, f'Unknown ({code})'),
            'Students Appeared': len(marks),
            'Average Marks': round(sum(marks) / len(marks), 2),
            'Highest': max(marks),
            'Lowest': min(marks),
            'Pass Count': pass_count,
            'Pass %': round(pass_count / len(marks) * 100, 2),
        })
    return pd.DataFrame(rows)


def compute_summary(students: List[Student]) -> Dict:
    total   = len(students)
    passed  = sum(1 for s in students if s.result == 'PASS')
    failed  = sum(1 for s in students if s.result == 'FAIL')
    comp    = sum(1 for s in students if s.result == 'COMP')
    absent  = sum(1 for s in students if s.result == 'ABSENT')
    male    = sum(1 for s in students if s.gender == 'M')
    female  = sum(1 for s in students if s.gender == 'F')
    return {
        'Total Candidates': total,
        'Passed': passed,
        'Failed': failed,
        'Compartment': comp,
        'Absent': absent,
        'Male': male,
        'Female': female,
        'Pass %': round(passed / total * 100, 2) if total else 0,
    }
