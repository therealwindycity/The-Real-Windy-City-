"""⚖️ Compliance Matrix — drop-in page for the TheReelWindyCity multipage app.

Install (in bartimoussmith-oss/therealwindycity):
    1. copy this repo's audit/ directory next to streamlit_app.py
    2. copy this file to pages/21_Compliance_Matrix.py
    3. ship a built audit/output/audit_records.jsonl, or set AUDIT_RECORDS_PATH
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "audit", Path(__file__).resolve().parent):
    if (candidate / "ui_adapter.py").exists():
        sys.path.insert(0, str(candidate))
        break

st.set_page_config(page_title="⚖️ Compliance Matrix", page_icon="⚖️", layout="wide")

from ui_adapter import render_compliance_dashboard  # noqa: E402

render_compliance_dashboard()
