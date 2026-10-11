"""Standalone entry point:  streamlit run audit/app.py"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
st.set_page_config(page_title="Compliance Verification Matrix", page_icon="⚖️", layout="wide")

from ui_adapter import render_compliance_dashboard  # noqa: E402
from analysis_ui import render_analysis_dashboard  # noqa: E402

view = st.sidebar.radio("View", ["Multi-source analysis (v2)", "Passage matrix (v1)"], key="audit_view")
if view.startswith("Multi"):
    render_analysis_dashboard()
else:
    render_compliance_dashboard()
