"""Premium Streamlit UI for the CBSE Analyzer."""

import hashlib
import html
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from exporter.excel_writer import export_excel_bytes
from services.analyzer_service import (
    DEFAULT_OUTPUT_NAME,
    DEFAULT_SCHOOL_NAME,
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


def inject_styles() -> None:
    st.markdown(
        """
        <style>

        :root {
            --canvas: #f3efe8;
            --canvas-soft: #faf6f0;
            --surface: rgba(255, 255, 255, 0.74);
            --surface-strong: rgba(255, 255, 255, 0.9);
            --ink: #161719;
            --muted: #686158;
            --line: rgba(22, 23, 25, 0.08);
            --gold: #b48a56;
            --gold-deep: #7b5a32;
            --forest: #233933;
            --forest-soft: rgba(35, 57, 51, 0.12);
            --rose-soft: rgba(166, 96, 80, 0.12);
            --stone: #ece7df;
            --shadow: 0 24px 60px rgba(32, 26, 20, 0.08);
        }

        html, body, [class*="css"] {
            font-family: "Manrope", sans-serif;
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 12% 10%, rgba(180, 138, 86, 0.16), transparent 20%),
                radial-gradient(circle at 86% 14%, rgba(35, 57, 51, 0.11), transparent 18%),
                radial-gradient(circle at 78% 82%, rgba(125, 95, 63, 0.12), transparent 16%),
                linear-gradient(180deg, #ece6dc 0%, #f7f2eb 38%, #f4f0ea 100%);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stToolbar"] {
            right: 1rem;
        }

        .block-container {
            max-width: 1220px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3, h4 {
            font-family: "Cormorant Garamond", serif;
            letter-spacing: -0.03em;
            color: var(--ink);
        }

        .lux-label {
            margin: 0 0 0.55rem;
            color: var(--gold-deep);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }

        .hero-shell {
            position: relative;
            overflow: hidden;
            padding: 2.1rem 2.2rem;
            border-radius: 32px;
            background:
                radial-gradient(circle at top right, rgba(180, 138, 86, 0.22), transparent 28%),
                linear-gradient(145deg, rgba(14, 17, 19, 0.98), rgba(30, 34, 38, 0.95));
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 34px 80px rgba(21, 18, 15, 0.22);
            margin-bottom: 1.4rem;
        }

        .hero-shell::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(120deg, transparent 0%, rgba(255, 255, 255, 0.03) 32%, transparent 60%);
            pointer-events: none;
        }

        .hero-shell::after {
            content: "";
            position: absolute;
            right: -70px;
            bottom: -120px;
            width: 280px;
            height: 280px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(180, 138, 86, 0.14), transparent 66%);
            pointer-events: none;
        }

        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.46rem 0.82rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: rgba(255, 244, 226, 0.92);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .hero-title {
            margin: 1rem 0 0.65rem;
            font-size: clamp(3rem, 7vw, 5.4rem);
            line-height: 0.9;
            letter-spacing: -0.05em;
            color: #f8f1e6;
            max-width: 8.5ch;
        }

        .hero-copy {
            margin: 0;
            max-width: 56ch;
            color: rgba(245, 239, 231, 0.76);
            font-size: 1rem;
            line-height: 1.75;
        }

        .hero-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            margin-top: 1.25rem;
        }

        .hero-pill {
            padding: 0.52rem 0.88rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: rgba(248, 241, 230, 0.88);
            font-size: 0.84rem;
            font-weight: 700;
        }

        .hero-stat-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.85rem;
            margin-top: 1.6rem;
        }

        .hero-stat {
            padding: 0.95rem 1rem;
            border-radius: 22px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(12px);
        }

        .hero-stat-label {
            color: rgba(245, 239, 231, 0.56);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }

        .hero-stat-value {
            color: #fcf7ef;
            font-family: "Cormorant Garamond", serif;
            font-size: 1.48rem;
            line-height: 1;
            margin-bottom: 0.22rem;
        }

        .hero-stat-copy {
            color: rgba(245, 239, 231, 0.64);
            font-size: 0.84rem;
            line-height: 1.45;
        }

        .panel-card {
            padding: 1.2rem 1.25rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(255,255,255,0.78), rgba(255,255,255,0.68));
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
        }

        .panel-card-dark {
            padding: 1.2rem 1.25rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(27, 30, 34, 0.97), rgba(20, 23, 27, 0.95));
            border: 1px solid rgba(255, 255, 255, 0.06);
            box-shadow: 0 22px 48px rgba(18, 17, 15, 0.16);
        }

        .panel-title {
            margin: 0 0 0.25rem;
            font-family: "Cormorant Garamond", serif;
            font-size: 1.85rem;
            color: var(--ink);
        }

        .panel-title-dark {
            margin: 0 0 0.25rem;
            font-family: "Cormorant Garamond", serif;
            font-size: 1.85rem;
            color: #f7efe5;
        }

        .panel-copy {
            color: var(--muted);
            font-size: 0.95rem;
            line-height: 1.65;
            margin: 0;
        }

        .panel-copy-dark {
            color: rgba(247, 239, 229, 0.72);
            font-size: 0.95rem;
            line-height: 1.65;
            margin: 0;
        }

        .mini-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.95rem;
        }

        .mini-chip {
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            background: rgba(180, 138, 86, 0.11);
            color: var(--gold-deep);
            font-size: 0.8rem;
            font-weight: 800;
        }

        .metric-card {
            position: relative;
            overflow: hidden;
            min-height: 100%;
            padding: 1.05rem 1.1rem 1.1rem;
            border-radius: 24px;
            background: var(--surface);
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
        }

        .metric-card::before {
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--gold), rgba(180, 138, 86, 0.18));
        }

        .metric-card.forest::before {
            background: linear-gradient(90deg, #2b584d, rgba(43, 88, 77, 0.18));
        }

        .metric-card.ink::before {
            background: linear-gradient(90deg, #20252b, rgba(32, 37, 43, 0.18));
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }

        .metric-value {
            font-family: "Cormorant Garamond", serif;
            font-size: 2.2rem;
            line-height: 0.96;
            color: var(--ink);
            margin-bottom: 0.35rem;
        }

        .metric-note {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.55;
        }

        .spotlight-card {
            min-height: 100%;
            padding: 1.15rem 1.18rem;
            border-radius: 24px;
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
            background: linear-gradient(180deg, rgba(255,255,255,0.82), rgba(255,255,255,0.72));
        }

        .spotlight-card.tone-forest {
            background: linear-gradient(180deg, rgba(231, 239, 236, 0.9), rgba(245, 249, 247, 0.82));
        }

        .spotlight-card.tone-gold {
            background: linear-gradient(180deg, rgba(249, 241, 231, 0.94), rgba(255, 251, 245, 0.82));
        }

        .spotlight-card.tone-ink {
            background: linear-gradient(180deg, rgba(28, 31, 35, 0.98), rgba(20, 23, 27, 0.95));
            border: 1px solid rgba(255, 255, 255, 0.06);
            box-shadow: 0 22px 48px rgba(18, 17, 15, 0.18);
        }

        .spotlight-brow {
            color: var(--gold-deep);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }

        .spotlight-card.tone-ink .spotlight-brow {
            color: rgba(244, 226, 197, 0.8);
        }

        .spotlight-title {
            margin: 0 0 0.28rem;
            font-family: "Cormorant Garamond", serif;
            font-size: 1.72rem;
            color: var(--ink);
        }

        .spotlight-card.tone-ink .spotlight-title {
            color: #f8f1e6;
        }

        .spotlight-copy {
            margin: 0 0 0.9rem;
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.6;
        }

        .spotlight-card.tone-ink .spotlight-copy {
            color: rgba(247, 239, 229, 0.72);
        }

        .spotlight-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }

        .spotlight-chip {
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            background: rgba(35, 57, 51, 0.1);
            color: var(--forest);
            font-size: 0.8rem;
            font-weight: 800;
        }

        .spotlight-card.tone-gold .spotlight-chip {
            background: rgba(180, 138, 86, 0.14);
            color: var(--gold-deep);
        }

        .spotlight-card.tone-ink .spotlight-chip {
            background: rgba(255, 255, 255, 0.08);
            color: rgba(248, 241, 230, 0.86);
        }

        .student-card {
            min-height: 100%;
            padding: 1.15rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(255,255,255,0.88), rgba(255,255,255,0.76));
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .student-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 28px 60px rgba(32, 26, 20, 0.12);
        }

        .student-rank {
            width: 2.4rem;
            height: 2.4rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: linear-gradient(135deg, #d0ab76, #8c6540);
            color: white;
            font-family: "Manrope", sans-serif;
            font-weight: 800;
            margin-bottom: 0.95rem;
        }

        .student-name {
            font-family: "Cormorant Garamond", serif;
            font-size: 1.7rem;
            line-height: 1;
            color: var(--ink);
            margin-bottom: 0.28rem;
        }

        .student-meta {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.5;
            margin-bottom: 0.9rem;
        }

        .student-score-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.7rem;
        }

        .student-score {
            color: var(--gold-deep);
            font-size: 1.5rem;
            font-weight: 800;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.38rem 0.72rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.06em;
        }

        .badge-pass {
            background: rgba(35, 57, 51, 0.12);
            color: #244b41;
        }

        .badge-fail {
            background: rgba(166, 96, 80, 0.14);
            color: #9d4638;
        }

        .badge-comp {
            background: rgba(180, 138, 86, 0.16);
            color: #8a6338;
        }

        .badge-absent {
            background: rgba(46, 52, 60, 0.1);
            color: #4f5a64;
        }

        .badge-neutral {
            background: rgba(22, 23, 25, 0.08);
            color: var(--ink);
        }

        .empty-shell {
            padding: 1.9rem 1.5rem;
            border-radius: 28px;
            background: rgba(255, 255, 255, 0.64);
            border: 1px dashed rgba(22, 23, 25, 0.16);
            text-align: center;
            color: var(--muted);
        }

        .empty-shell h3 {
            margin: 0 0 0.45rem;
            font-family: "Cormorant Garamond", serif;
            font-size: 2rem;
        }

        .status-line {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin-top: 0.9rem;
        }

        .status-chip {
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            color: rgba(248, 241, 230, 0.86);
            font-size: 0.8rem;
            font-weight: 700;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1.6px dashed rgba(22, 23, 25, 0.16);
            border-radius: 24px;
            padding: 1.15rem;
        }

        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: rgba(180, 138, 86, 0.7);
            background: rgba(255, 255, 255, 0.9);
        }

        .stTextInput > div > div > input,
        .stTextArea textarea {
            min-height: 3rem;
            border-radius: 18px;
            border: 1px solid rgba(22, 23, 25, 0.1);
            background: rgba(255, 255, 255, 0.84);
        }

        .stButton > button,
        .stDownloadButton > button {
            width: 100%;
            min-height: 3.15rem;
            border: 0;
            border-radius: 999px;
            color: #fbf5ed;
            font-weight: 800;
            letter-spacing: 0.02em;
            background: linear-gradient(135deg, #1f2629, #85643d);
            box-shadow: 0 16px 28px rgba(35, 31, 26, 0.16);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
            filter: brightness(1.02);
        }

        button[data-baseweb="tab"] {
            font-family: "Manrope", sans-serif;
            font-size: 0.92rem;
            font-weight: 800;
            letter-spacing: 0.03em;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--gold-deep);
        }

        [data-testid="stDataFrame"] {
            overflow: hidden;
            border-radius: 20px;
            border: 1px solid var(--line);
            box-shadow: 0 18px 40px rgba(32, 26, 20, 0.05);
        }

        .tab-note {
            margin: -0.1rem 0 0.9rem;
            color: var(--muted);
            font-size: 0.94rem;
        }

        @media (max-width: 980px) {
            .hero-stat-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 640px) {
            .block-container {
                padding-top: 1.2rem;
            }

            .hero-shell {
                padding: 1.6rem 1.35rem;
            }

            .hero-title {
                font-size: 2.9rem;
            }

            .hero-stat-grid {
                grid-template-columns: 1fr;
            }
        }
        /* YOR // Visual Framework Lock */
        :root {
            --yor-void: #000000;
            --yor-graphite: #050505;
            --yor-crimson: #e84b4b;
            --yor-deep-crimson: #671515;
            --yor-signal: #ff8a7f;
            --yor-warm-white: #f5eaea;
            --yor-muted: #c4c4c4;
            --yor-field: linear-gradient(135deg, #671515, #8c1616, #2a0505);
            --canvas: var(--yor-void);
            --canvas-soft: var(--yor-graphite);
            --surface: rgba(5, 5, 5, 0.86);
            --surface-strong: rgba(10, 10, 10, 0.96);
            --ink: var(--yor-warm-white);
            --muted: var(--yor-muted);
            --line: rgba(245, 234, 234, 0.16);
            --gold: var(--yor-crimson);
            --gold-deep: var(--yor-deep-crimson);
            --forest: var(--yor-signal);
            --stone: var(--yor-graphite);
            --shadow: 0 24px 70px rgba(103, 21, 21, 0.16);
        }

        html, body, [class*="css"] { font-family: Arial, "Helvetica Neue", sans-serif; color: var(--yor-warm-white); }
        [data-testid="stAppViewContainer"] {
            background-color: var(--yor-void) !important;
            background-image:
                linear-gradient(rgba(232, 75, 75, 0.055) 1px, transparent 1px),
                linear-gradient(90deg, rgba(232, 75, 75, 0.055) 1px, transparent 1px),
                radial-gradient(circle at 86% 0%, rgba(103, 21, 21, 0.3), transparent 36rem) !important;
            background-size: 32px 32px, 32px 32px, 100% 100% !important;
        }
        [data-testid="stHeader"] { background: transparent !important; }
        .block-container { max-width: 1280px; padding-top: 2rem; }
        h1, h2, h3, h4, .hero-title, .panel-title, .spotlight-title { font-family: Arial, "Helvetica Neue", sans-serif; color: var(--yor-warm-white) !important; letter-spacing: -0.04em; }
        .hero-shell, .panel-card, .panel-card-dark, .metric-card, .spotlight-card, .student-card, .empty-shell, .terminal-card { border-radius: 0 !important; border-color: rgba(245, 234, 234, 0.16) !important; box-shadow: var(--shadow) !important; }
        .hero-shell, .panel-card-dark { background: var(--yor-field) !important; }
        .panel-card, .metric-card, .spotlight-card, .student-card, .empty-shell, .terminal-card { background: linear-gradient(145deg, rgba(5, 5, 5, 0.96), rgba(26, 5, 5, 0.72)) !important; }
        .hero-kicker, .lux-label, .status-chip, .mini-chip, .hero-pill, .spotlight-chip { border-radius: 0 !important; border-color: rgba(255, 138, 127, 0.3) !important; background: rgba(0, 0, 0, 0.32) !important; color: var(--yor-signal) !important; }
        .hero-copy, .panel-copy, .panel-copy-dark, .spotlight-copy, .metric-note, .tab-note, .helper-note, .footer-copy, p, label, caption { color: var(--yor-muted); }
        button, [data-testid="stFileUploaderDropzone"] { border-radius: 0 !important; }
        button[kind="primary"], .stDownloadButton button { border-color: var(--yor-crimson) !important; background: var(--yor-crimson) !important; color: #000 !important; }
        button[kind="secondary"] { border-color: rgba(245, 234, 234, 0.28) !important; background: transparent !important; color: var(--yor-warm-white) !important; }
        input, textarea, [data-baseweb="select"] > div { border-radius: 0 !important; background: var(--yor-graphite) !important; color: var(--yor-warm-white) !important; border-color: rgba(245, 234, 234, 0.24) !important; }
        [data-testid="stDataFrame"] { border: 1px solid rgba(245, 234, 234, 0.16); }
        @media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition-duration: .001ms !important; animation-duration: .001ms !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero_stat(label: str, value: str, copy: str) -> str:
    return f"""
    <div class="hero-stat">
        <div class="hero-stat-label">{html.escape(label)}</div>
        <div class="hero-stat-value">{html.escape(value)}</div>
        <div class="hero-stat-copy">{html.escape(copy)}</div>
    </div>
    """


def hero_html(
    source_name: Optional[str],
    school_name: str,
    summary: Optional[Dict[str, object]] = None,
    subject_count: Optional[int] = None,
    error_count: Optional[int] = None,
) -> str:
    source_value = source_name or "Awaiting upload"
    error_total = 0 if error_count is None else error_count

    stat_cards = [
        hero_stat("Active source", source_value, "TXT gazette intake"),
        hero_stat("Workbook title", school_name or "CBSE Results 2026", "Excel cover line"),
    ]

    if summary:
        stat_cards.extend(
            [
                hero_stat(
                    "Candidates",
                    str(summary["Total Candidates"]),
                    f'{summary["Male"]} boys and {summary["Female"]} girls',
                ),
                hero_stat(
                    "Pass rate",
                    f'{summary["Pass %"]:.2f}%',
                    f'{error_total} parser notes and {subject_count or 0} mapped subjects',
                ),
            ]
        )
    else:
        stat_cards.extend(
            [
                hero_stat("Workbook sheets", "4", "Student, subject, summary, and notes"),
                hero_stat("Parser posture", "Ready", "Upload a file to light up the analysis"),
            ]
        )

    pill_items = [
        "Refined upload workflow",
        "Live class intelligence",
        "One-click workbook export",
    ]
    pill_html = "".join(f'<span class="hero-pill">{html.escape(item)}</span>' for item in pill_items)

    status_items = []
    if summary:
        status_items = [
            f"{summary['Passed']} pass",
            f"{summary['Failed']} fail",
            f"{summary['Compartment']} compartment",
            f"{error_total} parse notes",
        ]
    else:
        status_items = ["Upload a CBSE TXT gazette", "Use the sample for a quick tour"]

    status_html = "".join(
        f'<span class="status-chip">{html.escape(item)}</span>' for item in status_items
    )
    stats_html = "".join(stat_cards)

    return f"""
    <section class="hero-shell">
        <div class="hero-kicker">YOR // CBSE Result Analyzer</div>
        <h1 class="hero-title">Board-result intelligence, grounded in evidence.</h1>
        <p class="hero-copy">
            Clean intake, elegant reporting, and serious analysis in one space. Upload the gazette,
            inspect the batch pulse, and leave with a workbook that is ready to hand over.
        </p>
        <div class="hero-pill-row">{pill_html}</div>
        <div class="status-line">{status_html}</div>
        <div class="hero-stat-grid">{stats_html}</div>
    </section>
    """


def metric_card(label: str, value: str, note: str, tone: str = "gold") -> str:
    return f"""
    <div class="metric-card {html.escape(tone)}">
        <div class="metric-label">{html.escape(label)}</div>
        <div class="metric-value">{html.escape(value)}</div>
        <div class="metric-note">{html.escape(note)}</div>
    </div>
    """


def spotlight_card(
    eyebrow: str,
    title: str,
    copy: str,
    chips: List[str],
    tone: str = "forest",
) -> str:
    chips_html = "".join(
        f'<span class="spotlight-chip">{html.escape(chip)}</span>' for chip in chips if chip
    )
    return f"""
    <div class="spotlight-card tone-{html.escape(tone)}">
        <div class="spotlight-brow">{html.escape(eyebrow)}</div>
        <h3 class="spotlight-title">{html.escape(title)}</h3>
        <p class="spotlight-copy">{html.escape(copy)}</p>
        <div class="spotlight-chip-row">{chips_html}</div>
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
    total_text = f"{int(total_marks)} total marks" if pd.notna(total_marks) else "Total pending"
    return f"""
    <div class="student-card">
        <div class="student-rank">{rank:02d}</div>
        <div class="student-name">{html.escape(str(row.get("Name", "Unknown")))}</div>
        <div class="student-meta">
            Roll {html.escape(str(row.get("Roll No", "-")))} and {html.escape(total_text)}
        </div>
        <div class="student-score-row">
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


def build_source_signature(source_name: str, raw_bytes: bytes) -> str:
    digest = hashlib.sha1(raw_bytes).hexdigest()[:12]
    return f"{source_name}:{len(raw_bytes)}:{digest}"


def init_state() -> None:
    defaults = {
        "use_sample": False,
        "school_name": DEFAULT_SCHOOL_NAME,
        "output_name": DEFAULT_OUTPUT_NAME,
        "active_source": "",
        "active_source_name": "",
        "uploader_nonce": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def main() -> None:
    st.set_page_config(
        page_title="YOR // CBSE Result Analyzer",
        page_icon="C",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    inject_styles()
    init_state()

    hero_slot = st.empty()

    st.markdown('<p class="lux-label">Control desk</p>', unsafe_allow_html=True)
    left_col, right_col = st.columns([1.08, 0.92], gap="large")

    uploader_key = f"gazette_file_{st.session_state['uploader_nonce']}"

    with left_col:
        st.markdown(
            """
            <div class="panel-card">
                <h3 class="panel-title">Bring in the raw board gazette.</h3>
                <p class="panel-copy">
                    Drop the CBSE TXT export here. The studio will parse the file, build the batch
                    analytics, and prepare a polished Excel workbook for download.
                </p>
                <div class="mini-chip-row">
                    <span class="mini-chip">TXT in</span>
                    <span class="mini-chip">Analysis live</span>
                    <span class="mini-chip">Workbook out</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        uploaded_file = st.file_uploader(
            "Upload CBSE gazette text",
            type=["txt"],
            label_visibility="collapsed",
            key=uploader_key,
            help="Upload the school or roll-wise CBSE gazette text export.",
        )
        sample_col, reset_col = st.columns(2, gap="medium")
        with sample_col:
            if st.button("Use sample file", key="load_sample"):
                st.session_state["use_sample"] = True
        with reset_col:
            if st.button("Reset studio", key="reset_canvas"):
                st.session_state["use_sample"] = False
                st.session_state["active_source"] = ""
                st.session_state["active_source_name"] = ""
                st.session_state["school_name"] = DEFAULT_SCHOOL_NAME
                st.session_state["output_name"] = DEFAULT_OUTPUT_NAME
                st.session_state["uploader_nonce"] += 1
                st.rerun()

    with right_col:
        st.markdown(
            """
            <div class="panel-card-dark">
                <h3 class="panel-title-dark">Style the export before it leaves.</h3>
                <p class="panel-copy-dark">
                    Set the workbook headline and output filename. These details travel directly into the
                    final Excel report.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        school_name = st.text_input(
            "Workbook title",
            key="school_name",
            help="This appears on the title rows inside the workbook.",
        )
        st.text_input(
            "Download filename",
            key="output_name",
            help="The workbook download will use this filename.",
        )

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
            st.session_state["active_source_name"] = source_name
            suggested_school = detect_school_name(raw_text) or DEFAULT_SCHOOL_NAME
            st.session_state["school_name"] = suggested_school
            st.session_state["output_name"] = f"{Path(source_name).stem}_analysis.xlsx"
            school_name = st.session_state["school_name"]

    active_hero_source = source_name or st.session_state.get("active_source_name") or None
    hero_slot.markdown(hero_html(active_hero_source, school_name), unsafe_allow_html=True)

    if not source_name:
        empty_state(
            "A clean studio needs one file.",
            "Upload a CBSE gazette TXT file or tap the sample button to explore the premium workflow.",
        )
        return

    settings = get_settings()
    subject_master = get_subject_master()

    with st.spinner("Reading the gazette and shaping the workbook..."):
        analysis = analyze_gazette_text(
            raw_text,
            subject_master=subject_master,
            settings=settings,
        )

    if not analysis.students:
        hero_slot.markdown(
            hero_html(source_name, school_name, None, None, len(analysis.errors)),
            unsafe_allow_html=True,
        )
        st.error("The file was read, but no student rows could be parsed.")
        if analysis.errors:
            error_df = pd.DataFrame(serialize_error_rows(analysis.errors))
            st.dataframe(error_df, use_container_width=True, height=260)
        st.code(raw_text[:5000], language="text")
        return

    student_df = analysis.student_df
    subject_df = analysis.subject_df
    summary = analysis.summary
    workbook_bytes = export_excel_bytes(
        analysis.students,
        analysis.errors,
        subject_master,
        school_name,
    )
    download_name = ensure_output_name(st.session_state["output_name"])

    hero_slot.markdown(
        hero_html(
            source_name,
            school_name,
            summary,
            len(analysis.all_codes),
            len(analysis.errors),
        ),
        unsafe_allow_html=True,
    )

    result_df = pd.DataFrame(result_breakdown_rows(summary))
    toppers = select_topper_rows(student_df)

    strongest = None
    weakest = None
    if not subject_df.empty:
        strongest = subject_df.sort_values("Average Marks", ascending=False).iloc[0]
        weakest = subject_df.sort_values("Average Marks", ascending=True).iloc[0]

    st.markdown('<p class="lux-label">Batch pulse</p>', unsafe_allow_html=True)
    metric_columns = st.columns(4, gap="medium")
    metric_payload = [
        (
            "Candidates",
            str(summary["Total Candidates"]),
            f'{summary["Male"]} boys and {summary["Female"]} girls in the parsed batch.',
            "gold",
        ),
        (
            "Pass rate",
            f'{summary["Pass %"]:.2f}%',
            pass_rate_note(summary),
            "forest",
        ),
        (
            "Subjects",
            str(len(analysis.all_codes)),
            "Unique subjects discovered straight from the uploaded gazette.",
            "ink",
        ),
        (
            "Parser notes",
            str(len(analysis.errors)),
            "Warnings and hard parser issues surfaced during intake.",
            "gold",
        ),
    ]

    for column, payload in zip(metric_columns, metric_payload):
        with column:
            st.markdown(metric_card(*payload), unsafe_allow_html=True)

    action_left, action_right = st.columns([1.1, 0.9], gap="large")
    with action_left:
        st.markdown(
            spotlight_card(
                "Export ready",
                school_name,
                f"The workbook is ready to leave the studio. Source file: {source_name}.",
                [
                    f"{summary['Total Candidates']} students parsed",
                    f"{len(analysis.all_codes)} mapped subjects",
                    f"{len(analysis.errors)} parser notes",
                ],
                tone="ink",
            ),
            unsafe_allow_html=True,
        )
    with action_right:
        st.markdown(
            spotlight_card(
                "Delivery details",
                download_name,
                "One click exports the complete Excel workbook with student sheets, subject analytics, and parser notes.",
                [
                    "Excel download",
                    "Title synced",
                    "No extra setup",
                ],
                tone="gold",
            ),
            unsafe_allow_html=True,
        )
        st.download_button(
            "Download premium workbook",
            data=workbook_bytes,
            file_name=download_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    tabs = st.tabs(
        ["Overview", "Student Ledger", "Subject Pulse", "Parse Notes", "Raw Gazette"]
    )

    with tabs[0]:
        st.markdown("### Overview")
        st.markdown(
            '<p class="tab-note">A clean first read of the batch: toppers, result posture, and the subjects that need attention.</p>',
            unsafe_allow_html=True,
        )

        st.markdown('<p class="lux-label">Top performers</p>', unsafe_allow_html=True)
        topper_columns = st.columns(3, gap="medium")
        topper_rows = list(toppers.iterrows())
        for index, column in enumerate(topper_columns, start=1):
            with column:
                if index <= len(topper_rows):
                    _, row = topper_rows[index - 1]
                    st.markdown(topper_card(index, row), unsafe_allow_html=True)
                else:
                    empty_state("Awaiting rank", "Additional performers will appear here when data is available.")

        insight_left, insight_right, insight_extra = st.columns(3, gap="medium")
        with insight_left:
            if strongest is not None:
                st.markdown(
                    spotlight_card(
                        "Strongest subject",
                        str(strongest["Subject Name"]),
                        "The batch is performing best here, based on average marks.",
                        [
                            f'Avg {strongest["Average Marks"]:.2f}',
                            f'Highest {int(strongest["Highest"])}',
                            f'Pass {strongest["Pass %"]:.2f}%',
                        ],
                        tone="forest",
                    ),
                    unsafe_allow_html=True,
                )
        with insight_right:
            if weakest is not None:
                st.markdown(
                    spotlight_card(
                        "Closest review point",
                        str(weakest["Subject Name"]),
                        "This is the softest subject average in the uploaded batch.",
                        [
                            f'Avg {weakest["Average Marks"]:.2f}',
                            f'Lowest {int(weakest["Lowest"])}',
                            f'Pass {weakest["Pass %"]:.2f}%',
                        ],
                        tone="gold",
                    ),
                    unsafe_allow_html=True,
                )
        with insight_extra:
            st.markdown(
                spotlight_card(
                    "Result posture",
                    f"{summary['Passed']} of {summary['Total Candidates']} passed",
                    "A quick read on the class outcome before you open the detailed ledgers.",
                    [
                        f"{summary['Failed']} fail",
                        f"{summary['Compartment']} compartment",
                        f"{summary['Absent']} absent",
                    ],
                    tone="ink",
                ),
                unsafe_allow_html=True,
            )

        st.markdown('<p class="lux-label">Distribution</p>', unsafe_allow_html=True)
        st.bar_chart(result_df.set_index("Result"))

    with tabs[1]:
        st.markdown("### Student ledger")
        st.markdown(
            '<p class="tab-note">Search by name or roll number, then open the full subject matrix when you need the row-level detail.</p>',
            unsafe_allow_html=True,
        )

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
        st.markdown(
            '<p class="tab-note">Average marks first, then the full table for highest, lowest, and pass-rate context.</p>',
            unsafe_allow_html=True,
        )

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
        st.markdown(
            '<p class="tab-note">Use this when the intake looks suspicious or when you need a precise trail of parser warnings and errors.</p>',
            unsafe_allow_html=True,
        )

        if not analysis.errors:
            empty_state(
                "Clean parse.",
                "No warnings or hard parser errors were generated for this gazette.",
            )
        else:
            error_df = pd.DataFrame(serialize_error_rows(analysis.errors))
            st.dataframe(error_df, use_container_width=True, height=320)

    with tabs[4]:
        st.markdown("### Raw gazette preview")
        st.markdown(
            '<p class="tab-note">The first part of the uploaded text file, shown directly inside the studio for fast sanity checks.</p>',
            unsafe_allow_html=True,
        )
        st.code(raw_text[:12000], language="text")
        if len(raw_text) > 12000:
            st.caption("Preview truncated to the first 12,000 characters for readability.")


if __name__ == "__main__":
    main()
