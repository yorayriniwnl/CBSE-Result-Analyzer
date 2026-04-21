"""
Normalizer: converts list of Student objects into a wide pandas DataFrame.
One column per unique subject code found across the entire dataset.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from parser.gazette_parser import Student


def load_subject_master(path: str) -> Dict[str, str]:
    with open(path, 'r') as f:
        return json.load(f)


def build_normalized_table(
    students: List[Student],
    subject_master: Dict[str, str]
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Returns:
        df         — wide DataFrame, one row per student
        all_codes  — ordered list of subject codes (column order)
    """
    # Discover all unique codes
    all_codes_set = set()
    for s in students:
        all_codes_set.update(s.subjects.keys())

    # Sort: languages first, then math, then science, then rest
    LANG_CODES  = {'101', '184', '002', '001', '085', '021', '003'}
    MATH_CODES  = {'041', '241', '040'}
    SCI_CODES   = {'042', '043', '044', '086'}

    def sort_key(code: str):
        if code in LANG_CODES:  return (0, code)
        if code in MATH_CODES:  return (1, code)
        if code in SCI_CODES:   return (2, code)
        return (3, code)

    all_codes = sorted(all_codes_set, key=sort_key)

    rows = []
    for s in students:
        row: Dict = {
            'Roll No': s.roll,
            'Name': s.name,
            'Gender': s.gender,
        }
        total = 0
        count = 0
        for code in all_codes:
            label = subject_master.get(code, f'Sub-{code}')
            col = f'{label} ({code})'
            val = s.subjects.get(code)  # None if student didn't take this subject
            row[col] = val
            if val is not None:
                total += val
                count += 1

        row['Total Marks'] = total if count > 0 else None
        row['Subjects Appeared'] = count
        row['Percentage'] = round(total / count, 2) if count > 0 else None
        row['Result'] = s.result
        rows.append(row)

    df = pd.DataFrame(rows)
    return df, all_codes
