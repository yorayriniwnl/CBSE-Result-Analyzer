"""Streamlit UI for the CBSE Analyzer."""

import hashlib
import html
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from config.loader import load_settings, load_subject_master
from exporter.excel_writer import export_excel_bytes
from parser.gazette_parser import ParseError, Student, parse_gazette
from transformer.calculator import compute_subject_analysis, compute_summary
from transformer.normalizer import build_student_dataframe


BASE_DIR = Path(__file__).parent


@st.cache_data(show_spinner=False)
def get_subject_master() -> Dict[str, str]:
    return load_subject_master(str(BASE_DIR / "config" / "subjects.json"))


@st.cache_data(show_spinner=False)
def get_settings() -> Dict:
    return load_settings(str(BASE_DIR / "config" / "settings.yaml"))


@st.cache_data(show_spinner=False)
def get_sample_text() -> str:
    return (BASE_DIR / "sample_gazette.txt").read_text(encoding="utf-8")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Manrope:wght@400;500;700;800&display=swap');

        :root {
            --paper: #fff9f2;
            --paper-strong: rgba(255, 252, 247, 0.88);
            --ink: #13202b;
            --muted: #5f6e7a;
            --line: rgba(19, 32, 43, 0.12);
            --accent: #d66546;
            --accent-deep: #9b3a27;
            --teal: #167a71;
            --teal-soft: #dcf2ee;
            --rose-soft: #fde7df;
            --gold-soft: #fff1cb;
        }

        html, body, [class*="css"]  {
            font-family: "Manrope", sans-serif;
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 12% 12%, rgba(214, 101, 70, 0.18), transparent 22%),
                radial-gradient(circle at 84% 8%, rgba(22, 122, 113, 0.16), transparent 20%),
                radial-gradient(circle at 92% 82%, rgba(255, 206, 102, 0.18), transparent 18%),
                linear-gradient(180deg, #f8efe4 0%, #fffaf5 42%, #edf8f3 100%);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stToolbar"] {
            right: 1rem;
        }

        .block-container {
            max-width: 1180px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3, h4 {
            font-family: "Space Grotesk", sans-serif;
            letter-spacing: -0.03em;
            color: var(--ink);
        }

        .hero-shell {
            position: relative;
            overflow: hidden;
            padding: 2rem 2rem 1.75rem;
            border-radius: 30px;
            background:
                linear-gradient(135deg, rgba(255, 248, 241, 0.96), rgba(244, 253, 251, 0.92)),
                linear-gradient(180deg, rgba(255,255,255,0.7), rgba(255,255,255,0.4));
            border: 1px solid rgba(19, 32, 43, 0.08);
            box-shadow: 0 28px 60px rgba(73, 52, 36, 0.12);
            margin-bottom: 1.25rem;
        }

        .hero-shell::after {
            content: "";
            position: absolute;
            inset: auto -8% -30% auto;
            width: 280px;
            height: 280px;
            background: radial-gradient(circle, rgba(22, 122, 113, 0.22), transparent 64%);
            pointer-events: none;
        }

        .eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.42rem 0.8rem;
            border-radius: 999px;
            background: rgba(19, 32, 43, 0.06);
            color: var(--accent-deep);
            font-size: 0.8rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .hero-title {
            margin: 1rem 0 0.6rem;
            font-size: clamp(2.3rem, 5vw, 4.3rem);
            line-height: 0.94;
            max-width: 10ch;
        }

        .hero-copy {
            max-width: 58ch;
            margin: 0;
            color: var(--muted);
            font-size: 1.03rem;
            line-height: 1.7;
        }

        .pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin-top: 1.15rem;
        }

        .pill-row span {
            padding: 0.48rem 0.8rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.74);
            border: 1px solid rgba(19, 32, 43, 0.08);
            color: var(--ink);
            font-size: 0.88rem;
            font-weight: 700;
        }

        .insight-panel {
            padding: 1.15rem 1.2rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(20, 33, 44, 0.96), rgba(12, 21, 30, 0.92));
            color: #f6f7f8;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
            min-height: 100%;
        }

        .insight-kicker {
            color: rgba(255,255,255,0.68);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.7rem;
        }

        .insight-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 2.25rem;
            line-height: 1;
            margin-bottom: 0.4rem;
        }

        .insight-copy {
            color: rgba(255,255,255,0.72);
            font-size: 0.93rem;
            line-height: 1.6;
        }

        .section-kicker {
            margin: 0.1rem 0 0.45rem;
            color: var(--accent-deep);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .metric-card {
            background: var(--paper-strong);
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 1rem 1.05rem;
            box-shadow: 0 16px 40px rgba(95, 73, 58, 0.08);
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }

        .metric-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 2rem;
            line-height: 1;
            color: var(--ink);
            margin-bottom: 0.3rem;
        }

        .metric-note {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }

        .spotlight-card {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid var(--line);
            border-radius: 24px;
            padding: 1.2rem;
            min-height: 100%;
        }

        .spotlight-title {
            margin: 0 0 0.3rem;
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.28rem;
            color: var(--ink);
        }

        .spotlight-subtitle {
            margin: 0 0 0.9rem;
            color: var(--muted);
            font-size: 0.92rem;
        }

        .spotlight-stat {
            display: inline-block;
            padding: 0.45rem 0.72rem;
            border-radius: 999px;
            background: var(--teal-soft);
            color: var(--teal);
            font-weight: 800;
            font-size: 0.85rem;
            margin-right: 0.45rem;
            margin-bottom: 0.45rem;
        }

        .student-card {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 1rem;
            margin-bottom: 0.85rem;
        }

        .student-rank {
            width: 2.2rem;
            height: 2.2rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--accent), #f0a05f);
            color: white;
            font-family: "Space Grotesk", sans-serif;
            font-weight: 700;
            margin-bottom: 0.85rem;
        }

        .student-name {
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.05rem;
            color: var(--ink);
            margin-bottom: 0.2rem;
        }

        .student-meta {
            color: var(--muted);
            font-size: 0.9rem;
            margin-bottom: 0.7rem;
        }

        .student-score {
            font-size: 1.35rem;
            font-weight: 800;
            color: var(--accent-deep);
        }

        .badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 800;
            letter-spacing: 0.04em;
        }

        .badge-pass {
            background: #e0f3ea;
            color: #1d6a4e;
        }

        .badge-fail {
            background: #fde4e0;
            color: #ac2f28;
        }

        .badge-comp {
            background: #fff1cb;
            color: #9a6200;
        }

        .badge-absent {
            background: #eceef1;
            color: #54616c;
        }

        .badge-neutral {
            background: rgba(19, 32, 43, 0.08);
            color: var(--ink);
        }

        .empty-shell {
            padding: 1.7rem;
            border-radius: 28px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px dashed rgba(19, 32, 43, 0.16);
            text-align: center;
            color: var(--muted);
        }

        .empty-shell h3 {
            margin-bottom: 0.5rem;
        }

        .mini-note {
            padding: 0.9rem 1rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid var(--line);
            color: var(--muted);
        }

        [data-testid="stFileUploaderDropzone"] {
            background: rgba(255, 255, 255, 0.66);
            border: 1.5px dashed rgba(19, 32, 43, 0.16);
            border-radius: 22px;
            padding: 1rem;
        }

        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: rgba(214, 101, 70, 0.62);
            background: rgba(255, 255, 255, 0.88);
        }

        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stTextArea textarea {
            border-radius: 16px;
        }

        .stButton > button,
        .stDownloadButton > button {
            width: 100%;
            min-height: 3rem;
            border-radius: 999px;
            border: none;
            color: white;
            font-weight: 800;
            letter-spacing: 0.01em;
            background: linear-gradient(135deg, #d66546, #1d8076);
            box-shadow: 0 12px 24px rgba(22, 122, 113, 0.18);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            filter: brightness(1.02);
            transform: translateY(-1px);
        }

        button[data-baseweb="tab"] {
            font-family: "Space Grotesk", sans-serif;
            font-size: 0.95rem;
            font-weight: 700;
        }

        [data-testid="stDataFrame"] {
            border-radius: 20px;
            overflow: hidden;
            border: 1px solid var(--line);
        }

        @media (max-width: 768px) {
            .hero-shell {
                padding: 1.45rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-shell">
            <span class="eyebrow">CBSE Analyzer Studio</span>
            <div style="display:flex; gap:1.2rem; flex-wrap:wrap; margin-top:1rem;">
                <div style="flex:2 1 520px;">
                    <h1 class="hero-title">Turn dry gazettes into a sharp results room.</h1>
                    <p class="hero-copy">
                        Upload the board text file, pressure-test the parse, preview the class pulse,
                        and leave with a ready-to-share Excel workbook. The UI stays warm and polished;
                        the backend stays exact.
                    </p>
                    <div class="pill-row">
                        <span>TXT upload to workbook</span>
                        <span>Live toppers and subject pulse</span>
                        <span>Parse issues surfaced clearly</span>
                    </div>
                </div>
                <div style="flex:1 1 260px;">
                    <div class="insight-panel">
                        <div class="insight-kicker">Why this screen exists</div>
                        <div class="insight-value">1 file in.</div>
                        <div class="insight-copy">
                            4 polished sheets out. Student data, subject analysis, school summary,
                            and parse notes stay wired to the same analyzer you already debugged.
                        </div>
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, note: str) -> str:
    return f"""
    <div class="metric-card">
        <div class="metric-label">{html.escape(label)}</div>
        <div class="metric-value">{html.escape(value)}</div>
        <div class="metric-note">{html.escape(note)}</div>
    </div>
    """


def spotlight_card(title: str, subtitle: str, stats: List[str]) -> str:
    stats_html = "".join(
        f'<span class="spotlight-stat">{html.escape(stat)}</span>'
        for stat in stats
        if stat
    )
    return f"""
    <div class="spotlight-card">
        <h3 class="spotlight-title">{html.escape(title)}</h3>
        <p class="spotlight-subtitle">{html.escape(subtitle)}</p>
        {stats_html}
    </div>
    """


def result_badge(result: str) -> str:
    normalized = (result or "").upper()
    badge_class = {
        "PASS": "badge badge-pass",
        "FAIL": "badge badge-fail",
        "COMP": "badge badge-comp",
        "ABSENT": "badge badge-absent",
    }.get(normalized, "badge badge-neutral")
    return f'<span class="{badge_class}">{html.escape(normalized or "NA")}</span>'


def topper_card(rank: int, row: pd.Series) -> str:
    percentage = row.get("Percentage")
    total_marks = row.get("Total Marks")
    percentage_text = f"{float(percentage):.2f}%" if pd.notna(percentage) else "NA"
    total_text = f"{int(total_marks)} total" if pd.notna(total_marks) else "Total pending"
    return f"""
    <div class="student-card">
        <div class="student-rank">{rank:02d}</div>
        <div class="student-name">{html.escape(str(row.get("Name", "Unknown")))}</div>
        <div class="student-meta">
            Roll {html.escape(str(row.get("Roll No", "-")))} and {html.escape(total_text)}
        </div>
        <div style="display:flex; align-items:center; justify-content:space-between; gap:0.8rem;">
            <div class="student-score">{html.escape(percentage_text)}</div>
            <div>{result_badge(str(row.get("Result", "")))}</div>
        </div>
    </div>
    """


def empty_state(title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="empty-shell">
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(copy)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def detect_school_name(raw_text: str) -> Optional[str]:
    match = re.search(r"^SCHOOL\s*:\s*-\s*\d+\s+(.*)$", raw_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def parse_gazette_text(raw_text: str, settings: Dict) -> Tuple[List[Student], List[ParseError]]:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(raw_text)
            temp_path = handle.name
        return parse_gazette(temp_path, settings)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def coerce_display_table(dataframe: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    view = dataframe.loc[:, [col for col in columns if col in dataframe.columns]].copy()
    if "Percentage" in view.columns:
        view["Percentage"] = pd.to_numeric(view["Percentage"], errors="coerce").map(
            lambda value: f"{value:.2f}%" if pd.notna(value) else ""
        )
    return view


def ensure_download_name(name: str) -> str:
    clean_name = (name or "").strip() or "CBSE_Result_Analysis.xlsx"
    if not clean_name.lower().endswith(".xlsx"):
        clean_name = f"{clean_name}.xlsx"
    return clean_name


def build_source_signature(source_name: str, raw_bytes: bytes) -> str:
    digest = hashlib.sha1(raw_bytes).hexdigest()[:12]
    return f"{source_name}:{len(raw_bytes)}:{digest}"


def main() -> None:
    st.set_page_config(
        page_title="CBSE Analyzer Studio",
        page_icon="A",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_styles()
    render_hero()

    if "use_sample" not in st.session_state:
        st.session_state["use_sample"] = False
    if "school_name" not in st.session_state:
        st.session_state["school_name"] = "CBSE Results 2026"
    if "output_name" not in st.session_state:
        st.session_state["output_name"] = "CBSE_Result_Analysis.xlsx"

    st.markdown('<p class="section-kicker">Input Deck</p>', unsafe_allow_html=True)
    controls_left, controls_right = st.columns([1.2, 0.8], gap="large")

    with controls_left:
        uploaded_file = st.file_uploader(
            "Drop a CBSE gazette TXT file here",
            type=["txt"],
            help="Upload the raw school or roll-wise gazette text exported from CBSE.",
        )

    with controls_right:
        st.markdown(
            """
            <div class="mini-note">
                <strong>Fast lane</strong><br>
                Use the bundled sample if you want to tour the interface first, then swap in your own gazette.
            </div>
            """,
            unsafe_allow_html=True,
        )
        sample_col, reset_col = st.columns(2)
        with sample_col:
            if st.button("Load sample", key="load_sample"):
                st.session_state["use_sample"] = True
        with reset_col:
            if st.button("Reset canvas", key="reset_canvas"):
                st.session_state["use_sample"] = False
                st.session_state["active_source"] = ""
                st.session_state["school_name"] = "CBSE Results 2026"
                st.session_state["output_name"] = "CBSE_Result_Analysis.xlsx"

    source_name = None
    raw_bytes = b""

    if uploaded_file is not None:
        raw_bytes = uploaded_file.getvalue()
        source_name = uploaded_file.name
        st.session_state["use_sample"] = False
    elif st.session_state.get("use_sample"):
        sample_text = get_sample_text()
        raw_bytes = sample_text.encode("utf-8")
        source_name = "sample_gazette.txt"

    raw_text = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
    if source_name:
        source_signature = build_source_signature(source_name, raw_bytes)
        if st.session_state.get("active_source") != source_signature:
            st.session_state["active_source"] = source_signature
            suggested_school = detect_school_name(raw_text) or "CBSE Results 2026"
            st.session_state["school_name"] = suggested_school
            st.session_state["output_name"] = f"{Path(source_name).stem}_analysis.xlsx"

    config_col, file_col = st.columns([1, 1], gap="large")
    with config_col:
        school_name = st.text_input(
            "Workbook title",
            key="school_name",
            help="This appears on the Excel title rows.",
        )
    with file_col:
        st.text_input(
            "Download filename",
            key="output_name",
            help="The workbook will download with this name.",
        )

    if not source_name:
        empty_state(
            "Bring in a gazette to wake the studio up.",
            "Upload a TXT file or tap Load sample to see the parser, analytics, and workbook download in action.",
        )
        return

    settings = get_settings()
    subject_master = get_subject_master()

    with st.spinner("Reading the gazette and shaping the workbook..."):
        students, errors = parse_gazette_text(raw_text, settings)

    if not students:
        st.error("The file was read, but no student rows could be parsed.")
        if errors:
            error_df = pd.DataFrame(
                [
                    {
                        "Level": error.level,
                        "Roll No": error.roll,
                        "Line No": error.line_no,
                        "Message": error.message,
                    }
                    for error in errors
                ]
            )
            st.dataframe(error_df, use_container_width=True, height=260)
        st.code(raw_text[:5000], language="text")
        return

    student_df, all_codes = build_student_dataframe(students, subject_master)
    subject_df = compute_subject_analysis(students, all_codes, subject_master)
    summary = compute_summary(students)
    workbook_bytes = export_excel_bytes(students, errors, subject_master, school_name)
    download_name = ensure_download_name(st.session_state["output_name"])

    result_df = pd.DataFrame(
        {
            "Result": ["PASS", "FAIL", "COMP", "ABSENT"],
            "Count": [
                summary["Passed"],
                summary["Failed"],
                summary["Compartment"],
                summary["Absent"],
            ],
        }
    )

    sortable_students = student_df.copy()
    sortable_students["Percentage"] = pd.to_numeric(sortable_students["Percentage"], errors="coerce")
    sortable_students["Total Marks"] = pd.to_numeric(sortable_students["Total Marks"], errors="coerce")
    toppers = sortable_students.sort_values(
        ["Percentage", "Total Marks"],
        ascending=[False, False],
        na_position="last",
    ).head(3)

    st.markdown('<p class="section-kicker">Class Pulse</p>', unsafe_allow_html=True)
    metric_columns = st.columns(4, gap="medium")
    metric_payload = [
        (
            "Candidates",
            str(summary["Total Candidates"]),
            f'{summary["Male"]} boys and {summary["Female"]} girls in the parsed batch.',
        ),
        (
            "Pass Rate",
            f'{summary["Pass %"]:.2f}%',
            f'{summary["Passed"]} pass, {summary["Failed"]} fail, {summary["Compartment"]} compartment.',
        ),
        (
            "Subjects",
            str(len(all_codes)),
            "Unique subjects discovered directly from the uploaded gazette.",
        ),
        (
            "Parse Notes",
            str(len(errors)),
            "Warnings and hard errors surfaced from the parser pipeline.",
        ),
    ]
    for column, payload in zip(metric_columns, metric_payload):
        with column:
            st.markdown(metric_card(*payload), unsafe_allow_html=True)

    action_left, action_right = st.columns([1.15, 0.85], gap="large")
    with action_left:
        st.markdown(
            spotlight_card(
                "Workbook ready for export",
                f"Source: {source_name}",
                [
                    f"{summary['Total Candidates']} students parsed",
                    f"{len(errors)} parse notes",
                    f"{len(all_codes)} subjects mapped",
                ],
            ),
            unsafe_allow_html=True,
        )
    with action_right:
        st.download_button(
            "Download Excel workbook",
            data=workbook_bytes,
            file_name=download_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    tabs = st.tabs(
        ["Overview", "Student Ledger", "Subject Pulse", "Parse Notes", "Raw Gazette"]
    )

    with tabs[0]:
        overview_left, overview_right = st.columns([1.08, 0.92], gap="large")

        with overview_left:
            st.markdown("### Top performers")
            if toppers.empty:
                empty_state("No toppers yet", "The parsed data did not produce any rankable percentages.")
            else:
                for rank, (_, row) in enumerate(toppers.iterrows(), start=1):
                    st.markdown(topper_card(rank, row), unsafe_allow_html=True)

        with overview_right:
            st.markdown("### Result distribution")
            st.bar_chart(result_df.set_index("Result"))

            if not subject_df.empty:
                strongest = subject_df.sort_values("Average Marks", ascending=False).iloc[0]
                weakest = subject_df.sort_values("Average Marks", ascending=True).iloc[0]
                spot_a, spot_b = st.columns(2, gap="medium")
                with spot_a:
                    st.markdown(
                        spotlight_card(
                            str(strongest["Subject Name"]),
                            "Strongest average score in the batch.",
                            [
                                f'Avg {strongest["Average Marks"]:.2f}',
                                f'Highest {int(strongest["Highest"])}',
                                f'Pass {strongest["Pass %"]:.2f}%',
                            ],
                        ),
                        unsafe_allow_html=True,
                    )
                with spot_b:
                    st.markdown(
                        spotlight_card(
                            str(weakest["Subject Name"]),
                            "Lowest average score and the first place to review.",
                            [
                                f'Avg {weakest["Average Marks"]:.2f}',
                                f'Lowest {int(weakest["Lowest"])}',
                                f'Pass {weakest["Pass %"]:.2f}%',
                            ],
                        ),
                        unsafe_allow_html=True,
                    )

    with tabs[1]:
        st.markdown("### Student ledger")
        search_text = st.text_input(
            "Filter by name or roll number",
            key="student_search",
            placeholder="Type a roll number or a student name",
        )
        filtered_students = student_df.copy()
        if search_text:
            mask = (
                filtered_students["Roll No"].astype(str).str.contains(search_text, case=False, na=False)
                | filtered_students["Name"].astype(str).str.contains(search_text, case=False, na=False)
            )
            filtered_students = filtered_students[mask]

        preview = coerce_display_table(
            filtered_students,
            ["Roll No", "Name", "Gender", "Total Marks", "Percentage", "Subjects Appeared", "Result"],
        )
        st.dataframe(preview, use_container_width=True, height=420)

        with st.expander("Open the full subject matrix"):
            st.dataframe(filtered_students, use_container_width=True, height=480)

    with tabs[2]:
        st.markdown("### Subject pulse")
        if subject_df.empty:
            empty_state("No subject view available", "The parser did not produce any subject marks to analyze.")
        else:
            chart_df = subject_df.sort_values("Average Marks", ascending=False).set_index("Subject Name")
            st.bar_chart(chart_df["Average Marks"])

            subject_view = subject_df.sort_values("Average Marks", ascending=False).copy()
            subject_view["Average Marks"] = subject_view["Average Marks"].map(lambda value: f"{value:.2f}")
            subject_view["Pass %"] = subject_view["Pass %"].map(lambda value: f"{value:.2f}%")
            st.dataframe(subject_view, use_container_width=True, height=420)

    with tabs[3]:
        st.markdown("### Parse notes")
        if not errors:
            empty_state(
                "Clean parse.",
                "No warnings or hard parser errors were generated for this gazette.",
            )
        else:
            error_df = pd.DataFrame(
                [
                    {
                        "Level": error.level,
                        "Roll No": error.roll,
                        "Line No": error.line_no,
                        "Message": error.message,
                    }
                    for error in errors
                ]
            )
            st.dataframe(error_df, use_container_width=True, height=320)

    with tabs[4]:
        st.markdown("### Raw gazette preview")
        st.code(raw_text[:12000], language="text")
        if len(raw_text) > 12000:
            st.caption("Preview truncated to the first 12,000 characters for readability.")


if __name__ == "__main__":
    main()
