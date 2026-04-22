"""Shared service layer for analyzer entrypoints."""

from .analyzer_service import (
    DEFAULT_OUTPUT_NAME,
    DEFAULT_SCHOOL_NAME,
    AnalysisBundle,
    analyze_gazette_text,
    coerce_display_table,
    detect_school_name,
    ensure_output_name,
    get_sample_text,
    get_settings,
    get_subject_master,
    pass_rate_note,
    result_breakdown_rows,
    select_topper_rows,
    serialize_error_rows,
)

__all__ = [
    "AnalysisBundle",
    "DEFAULT_OUTPUT_NAME",
    "DEFAULT_SCHOOL_NAME",
    "analyze_gazette_text",
    "coerce_display_table",
    "detect_school_name",
    "ensure_output_name",
    "get_sample_text",
    "get_settings",
    "get_subject_master",
    "pass_rate_note",
    "result_breakdown_rows",
    "select_topper_rows",
    "serialize_error_rows",
]
