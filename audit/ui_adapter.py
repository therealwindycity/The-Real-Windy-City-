"""
STREAMLIT AUDIT DISPLAY ADAPTER
===============================

Shows the JSONL produced by ``audit_ingest_node.py`` as a filterable
compliance-review matrix.

Two ways to use it:

* Standalone:  ``streamlit run audit/app.py``
* Inside the TheReelWindyCity multipage app: copy ``audit/`` next to
  ``streamlit_app.py`` and add ``audit/streamlit_page.py`` as
  ``pages/21_Compliance_Matrix.py`` (it already calls ``set_page_config``).

Data location, first match wins:
``render_compliance_dashboard(data_path=...)``, then ``$AUDIT_RECORDS_PATH``,
then ``audit/output/audit_records.jsonl``.

Works with Streamlit 1.35 and later; the multipage app pins ``streamlit>=1.35``.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "output" / "audit_records.jsonl"
DEFAULT_TRANSCRIPTS = HERE.parent / "cheyenne-2026-transcripts"
STATUS_REVIEW = "Eligible for Administrative Review"
_PLACEHOLDERS = {"None identified", "Standard review", "Routine/Informational"}

_ST_VER = tuple(int(x) for x in st.__version__.split(".")[:2] if x.isdigit())
_STRETCH = {"width": "stretch"} if _ST_VER >= (1, 50) else {"use_container_width": True}

DISCLAIMER = (
    "Scores count keyword hits from a fixed lexicon (`audit/lexicon.json`). A high score means "
    "a passage deserves a human read. It is **not** a finding that anything improper happened. "
    "The transcripts come from auto-generated captions and get names wrong, so check every quote "
    "against the timestamped video. Remediation pathways are general procedural references, "
    "not legal advice."
)


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
def resolve_data_path(data_path: Optional[str | os.PathLike] = None) -> Path:
    if data_path:
        return Path(data_path)
    if os.environ.get("AUDIT_RECORDS_PATH"):
        return Path(os.environ["AUDIT_RECORDS_PATH"])
    return DEFAULT_DATA


def _clean(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    return [str(v) for v in values if str(v) not in _PLACEHOLDERS]


def flatten_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """One JSONL entry becomes one table row. Older entries that predate the
    four-part schema (no ``entity_mapping`` dict and so on) still load."""
    c = entry.get("audit_classification", {}) or {}
    raw = entry.get("raw_source", {}) or {}
    src = entry.get("source", {}) or {}
    em = c.get("entity_mapping") if isinstance(c.get("entity_mapping"), dict) else {}
    rh = c.get("rhetorical_alignment_profile") if isinstance(c.get("rhetorical_alignment_profile"), dict) else {}
    paths = c.get("remediation_pathway") if isinstance(c.get("remediation_pathway"), list) else []
    text = raw.get("text") if isinstance(raw, dict) and raw.get("text") else str(raw)
    return {
        "record_id": entry.get("record_id", ""),
        "date": raw.get("date", "") if isinstance(raw, dict) else "",
        "body": (raw.get("body") if isinstance(raw, dict) else None) or src.get("type", ""),
        "start": raw.get("start", "") if isinstance(raw, dict) else "",
        "url": raw.get("url", "") if isinstance(raw, dict) else "",
        "source_ref": src.get("youtube_id") or src.get("file") or src.get("dataset") or src.get("layer") or "",
        "compliance_friction_score": float(c.get("compliance_friction_score", 0) or 0),
        "remediation_status": c.get("remediation_status", "Nominal"),
        "procedural_deviations": ", ".join(_clean(c.get("procedural_deviations"))),
        "statutory_reference_points": ", ".join(_clean(c.get("statutory_reference_points"))),
        "enforcement_classification": ", ".join(_clean(c.get("enforcement_classification"))),
        "agencies": ", ".join(em.get("agencies", [])),
        "officials": ", ".join(em.get("officials", [])),
        "statutory_citations": ", ".join(em.get("statutory_citations", [])),
        "instruments": ", ".join(em.get("instruments", [])),
        "rhetorical_mode": rh.get("dominant_mode", ""),
        "objectivity_ratio": rh.get("objectivity_ratio"),
        "remediation_pathway": " | ".join(p.get("pathway", "") for p in paths if isinstance(p, dict)),
        "raw_preview": text[:150],
        "_text": text,
    }


@st.cache_data(show_spinner="Loading audit records…")
def _load(path_str: str, mtime: float) -> tuple[pd.DataFrame, Dict[str, Dict[str, Any]], int]:
    rows, entries, bad = [], {}, 0
    with open(path_str, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            row = flatten_entry(entry)
            rows.append(row)
            entries[row["record_id"]] = entry
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "body", "start"], kind="stable").reset_index(drop=True)
    return df, entries, bad


def load_audit_data(filepath: Optional[str | os.PathLike] = None) -> pd.DataFrame:
    """Same entry point as the original adapter: returns the flattened table,
    or an empty frame if the file is missing."""
    df, _, _ = _load_with_entries(filepath)
    return df


def _load_with_entries(filepath=None):
    path = resolve_data_path(filepath)
    if not path.exists():
        return pd.DataFrame(), {}, 0
    return _load(str(path), path.stat().st_mtime)


def _build_index(path: Path) -> Optional[str]:
    """Run the ingest node over this repo's transcripts. Returns an error message, or None on success."""
    try:
        from audit_ingest_node import RegulatoryAuditPipeline, iter_transcripts  # type: ignore
    except ImportError:
        import sys
        sys.path.insert(0, str(HERE))
        from audit_ingest_node import RegulatoryAuditPipeline, iter_transcripts  # type: ignore
    if not (DEFAULT_TRANSCRIPTS / "meetings.json").exists():
        return f"No transcript catalog at {DEFAULT_TRANSCRIPTS}; point AUDIT_RECORDS_PATH at a built JSONL instead."
    RegulatoryAuditPipeline(output_path=path).process_and_persist(
        iter_transcripts(DEFAULT_TRANSCRIPTS), "text",
        source={"type": "transcript", "collection": DEFAULT_TRANSCRIPTS.name}, mode="rebuild")
    st.cache_data.clear()
    return None


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
def _terms(series: pd.Series) -> pd.Series:
    s = series[series.astype(bool)].str.split(", ").explode()
    return s[s.astype(bool)]


def _filters(df: pd.DataFrame, key: str) -> pd.DataFrame:
    with st.expander("Filters", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bodies = sorted(b for b in df["body"].unique() if b)
        sel_bodies = c1.multiselect("Body", bodies, key=f"{key}-body")
        term_opts = sorted(set(_terms(df["procedural_deviations"])) | set(_terms(df["statutory_reference_points"]))
                           | set(_terms(df["enforcement_classification"])))
        sel_terms = c2.multiselect("Marker (any of)", term_opts, key=f"{key}-terms")
        review_only = c3.toggle("Review queue only", value=True, key=f"{key}-review")

        c4, c5 = st.columns([3, 2])
        query = c4.text_input("Search agency, official, citation or text", key=f"{key}-q",
                              placeholder="e.g. executive session, Board of Adjustment, 16-4-405")
        max_score = float(df["compliance_friction_score"].max() or 0)
        min_score = c5.slider("Minimum friction score", 0.0, max(max_score, 1.0), 0.0, 0.5, key=f"{key}-min")

        dates = sorted(d for d in df["date"].unique() if d)
        if len(dates) > 1:
            d0, d1 = st.select_slider("Date range", options=dates, value=(dates[0], dates[-1]), key=f"{key}-dates")
        else:
            d0 = d1 = None

    out = df
    if sel_bodies:
        out = out[out["body"].isin(sel_bodies)]
    if review_only:
        out = out[out["remediation_status"] == STATUS_REVIEW]
    if min_score:
        out = out[out["compliance_friction_score"] >= min_score]
    if d0 and d1:
        out = out[(out["date"] >= d0) & (out["date"] <= d1)]
    if sel_terms:
        hay = (out["procedural_deviations"] + ", " + out["statutory_reference_points"] + ", "
               + out["enforcement_classification"]).str.split(", ")
        wanted = set(sel_terms)
        out = out[hay.apply(lambda xs: bool(wanted.intersection(xs)))]
    if query:
        cols = ["agencies", "officials", "statutory_citations", "instruments", "procedural_deviations",
                "statutory_reference_points", "_text"]
        mask = pd.Series(False, index=out.index)
        for col in cols:
            mask |= out[col].astype(str).str.contains(query, case=False, regex=False, na=False)
        out = out[mask]
    return out


def _detail(entry: Dict[str, Any]) -> None:
    c = entry.get("audit_classification", {})
    raw = entry.get("raw_source", {}) or {}
    head = f"**{raw.get('date', '')} · {raw.get('body', '')} · {raw.get('start', '')}**"
    if raw.get("url"):
        head += f" — [▶ open video at this moment]({raw['url']})"
    st.markdown(head)
    m1, m2, m3 = st.columns(3)
    m1.metric("Friction score", c.get("compliance_friction_score", 0))
    m2.metric("Status", "Review" if c.get("remediation_status") == STATUS_REVIEW else "Nominal")
    rh = c.get("rhetorical_alignment_profile", {}) if isinstance(c.get("rhetorical_alignment_profile"), dict) else {}
    m3.metric("Rhetorical mode", rh.get("dominant_mode", "—"))

    tabs = st.tabs(["Evidence", "Entities", "Remediation pathway", "Rhetoric", "Passage", "Raw JSON"])
    with tabs[0]:
        ev = c.get("evidence") or []
        if ev:
            for e in ev:
                st.markdown(f"- `{e.get('category')}` **{e.get('term')}** ×{e.get('count', 1)} — {e.get('snippet', '')}")
        else:
            st.caption("No marker hits.")
    with tabs[1]:
        em = c.get("entity_mapping")
        st.json(em if isinstance(em, dict) else {"entity_mapping": em})
    with tabs[2]:
        paths = c.get("remediation_pathway") or []
        if paths:
            st.dataframe(pd.DataFrame(paths), hide_index=True, **_STRETCH)
            st.caption("General procedural references keyed to the markers that fired. Not legal advice; "
                       "check the current statute text and deadlines.")
        else:
            st.caption("No pathway triggered.")
    with tabs[3]:
        st.json(rh)
    with tabs[4]:
        st.write(raw.get("text") or raw)
    with tabs[5]:
        st.json(entry)


def render_compliance_dashboard(data_path: Optional[str | os.PathLike] = None, key: str = "audit") -> None:
    st.title("Administrative Record & Compliance Verification Matrix")
    st.caption("Civic Transparency Infrastructure & Statutory Audit Node")

    path = resolve_data_path(data_path)
    df, entries, bad = _load_with_entries(path)
    if df.empty:
        st.info(f"No records loaded from `{path}`. Run "
                "`python audit/audit_ingest_node.py transcripts` or build the index here.")
        if st.button("Build index from meeting transcripts", type="primary", key=f"{key}-build"):
            with st.spinner("Classifying transcripts…"):
                err = _build_index(path)
            if err:
                st.error(err)
            else:
                st.rerun()
        return
    if bad:
        st.warning(f"{bad} malformed line(s) skipped in {path.name}.")
    st.info(DISCLAIMER, icon="ℹ️")

    review = df[df["remediation_status"] == STATUS_REVIEW]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Indexed passages", f"{len(df):,}")
    c2.metric("Compliance action items", f"{len(review):,}")
    c3.metric("Avg friction metric", f"{df['compliance_friction_score'].mean():.2f}")
    c4.metric("Meetings / sources", f"{df['source_ref'].replace('', pd.NA).nunique():,}")

    filtered = _filters(df, key)

    left, right = st.columns(2)
    with left:
        st.markdown("**Top markers in current view**")
        terms = pd.concat([_terms(filtered["procedural_deviations"]), _terms(filtered["statutory_reference_points"])])
        if not terms.empty:
            st.bar_chart(terms.value_counts().head(15))
    with right:
        st.markdown("**Review items by body**")
        by_body = filtered[filtered["remediation_status"] == STATUS_REVIEW]["body"].value_counts()
        if not by_body.empty:
            st.bar_chart(by_body)

    st.markdown(f"**{len(filtered):,} passage(s)**, highest score first")
    show = filtered.sort_values(["compliance_friction_score", "date"], ascending=[False, True])
    cols = ["date", "body", "start", "compliance_friction_score", "procedural_deviations",
            "statutory_reference_points", "enforcement_classification", "agencies", "statutory_citations",
            "rhetorical_mode", "remediation_pathway", "raw_preview", "url", "record_id"]
    st.dataframe(
        show[cols], hide_index=True, height=420, **_STRETCH,
        column_config={
            "url": st.column_config.LinkColumn("video", display_text="▶ open"),
            "compliance_friction_score": st.column_config.ProgressColumn(
                "friction", min_value=0.0, max_value=max(float(df["compliance_friction_score"].max()), 1.0),
                format="%.1f"),
            "raw_preview": st.column_config.TextColumn("preview", width="large"),
        },
    )

    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Download CSV", show.drop(columns=["_text"]).to_csv(index=False).encode(),
                       "audit_view.csv", "text/csv", key=f"{key}-csv")
    buf = io.StringIO()
    for rid in show["record_id"]:
        buf.write(json.dumps(entries[rid], ensure_ascii=False) + "\n")
    d2.download_button("Download JSONL", buf.getvalue().encode(), "audit_view.jsonl",
                       "application/json", key=f"{key}-jsonl")

    st.divider()
    st.subheader("Inspect a passage")
    if show.empty:
        st.caption("Nothing matches the current filters.")
        return
    options = show["record_id"].head(500).tolist()
    labels = {r.record_id: f"{r.compliance_friction_score:>4.1f} · {r.date} · {r.body} · {r.start} · "
                           f"{r.procedural_deviations or r.statutory_reference_points or '—'}"
              for r in show.head(500).itertuples()}
    rid = st.selectbox("Passage", options, format_func=lambda r: labels.get(r, r), key=f"{key}-pick")
    if rid:
        _detail(entries[rid])
