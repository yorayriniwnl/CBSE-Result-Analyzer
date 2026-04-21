import json
import os
from typing import Dict

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


_BASE = os.path.dirname(__file__)


def load_subject_master(subjects_file: str = None) -> Dict[str, str]:
    path = subjects_file or os.path.join(_BASE, "subjects.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_settings(settings_file: str = None) -> Dict:
    path = settings_file or os.path.join(_BASE, "settings.yaml")

    defaults = {
        "year": 2026,
        "grading_enabled": False,
        "performance_index_enabled": False,
        "absent_markers": ["AA", "AB", "---", "XX"],
        "result_keywords": ["PASS", "FAIL", "COMP", "ABSENT", "UFM", "RWH"],
        "min_subjects_per_student": 4,
        "max_subjects_per_student": 8,
    }

    if not os.path.exists(path):
        return defaults

    if _HAS_YAML:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        defaults.update(loaded)
    else:
        # Fallback if pyyaml not installed
        pass

    return defaults
