"""Streamlit views for the v2 multi-source analysis (audit/output/analysis/).

render_analysis_dashboard() is called from app.py and from the drop-in page. It is read-only:
it never modifies the official records or the transcripts.
"""

from __future__ import annotations

import json
import re
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

_ST_VER = tuple(int(x) for x in re.findall(r"\d+", st.__version__)[:2])
_STRETCH = {"width": "stretch"} if _ST_VER >= (1, 46) else {"use_container_width": True}

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = Path(os.environ.get("AUDIT_ANALYSIS_DIR", HERE / "output" / "analysis"))
SUMMARY = HERE / "reports" / "analysis_summary.json"
BODY = {"city-council": "City Council", "public-services-committee": "Public Services", "finance-committee": "Finance"}
FILES = ["claims.jsonl", "items.jsonl", "exceptions.jsonl", "lifecycles.json", "voting.json", "meetings.json",
         "passages_v2.jsonl"]


def _read(path: Path):
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def _load(dir_str: str, stamp: float) -> Dict[str, object]:
    d = Path(dir_str)
    out = {f.split(".")[0]: _read(d / f) for f in FILES}
    out["summary"] = json.loads(SUMMARY.read_text()) if SUMMARY.exists() else {}
    return out


def _stamp(d: Path) -> float:
    return max((d / f).stat().st_mtime for f in FILES if (d / f).exists())


def _link(url: Optional[str], label: str = "▶") -> str:
    return f"[{label}]({url})" if url else ""


def _build_controls(d: Path) -> None:
    st.info("The analysis outputs have not been built yet. The build reads the transcripts and "
            "`audit/reference/official_records.json` and takes about 30 seconds.")
    if st.button("Build analysis now", type="primary"):
        import build_analysis
        with st.spinner("Building…"):
            build_analysis.main([])
        st.cache_data.clear()
        st.rerun()


def render_analysis_dashboard(analysis_dir: Optional[str | os.PathLike] = None, key: str = "analysis") -> None:
    d = Path(analysis_dir) if analysis_dir else DEFAULT_DIR
    st.title("Cheyenne governing body: multi-source analysis")
    st.caption("Captions × official agendas × approved minutes. Every row is a lead for human review, linked to its "
               "source. Legal claims are speakers' allegations, not findings. Captions contain transcription errors.")
    if not all((d / f).exists() for f in FILES):
        _build_controls(d)
        return
    data = _load(str(d), _stamp(d))
    tabs = st.tabs(["Overview", "Claims", "Reconciliation", "Ordinance lifecycles", "Votes", "Meetings", "Passages v2"])
    with tabs[0]:
        _overview(data)
    with tabs[1]:
        _claims(data["claims"], key)
    with tabs[2]:
        _reconciliation(data["exceptions"], key)
    with tabs[3]:
        _lifecycles(data["lifecycles"], key)
    with tabs[4]:
        _votes(data["voting"], key)
    with tabs[5]:
        _meetings(data["meetings"], data["items"], key)
    with tabs[6]:
        _passages(data["passages_v2"], key)


def _overview(data: Dict) -> None:
    s = data["summary"]
    h = s.get("headline", {})
    c = st.columns(5)
    c[0].metric("Agenda items located in video", h.get("agenda_items_aligned"))
    c[1].metric("Joined to minutes outcome", h.get("items_joined_to_minutes"))
    c[2].metric("Strong legal claims", h.get("claims_strong_asserted"))
    c[3].metric("Reconciliation leads", h.get("reconciliation_exceptions"))
    c[4].metric("Contested votes (2026)", h.get("contested_votes_2026"))
    st.subheader("Reconciliation checks")
    rows = [{"check": k, "run": v, "exceptions": s.get("exceptions_by_check", {}).get(k, 0)}
            for k, v in s.get("checks_run_by_check", {}).items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, **_STRETCH)
    st.subheader("Validation")
    st.json(s.get("validation", {}))
    st.caption("The full written report is in audit/reports/ANALYSIS_2026.md.")


def _claims(claims: List[Dict], key: str) -> None:
    df = pd.DataFrame(claims)
    if df.empty:
        st.write("No claims.")
        return
    c = st.columns(4)
    role = c[0].multiselect("Speaker role", sorted(df.role.unique()), default=["public_comment"], key=f"{key}_cr")
    strength = c[1].multiselect("Strength", ["strong", "weak"], default=["strong"], key=f"{key}_cs")
    pol = c[2].multiselect("Polarity", ["assert", "deny"], default=["assert"], key=f"{key}_cp")
    q = c[3].text_input("Search text", key=f"{key}_cq")
    f = df[df.role.isin(role) & df.strength.isin(strength) & df.polarity.isin(pol)]
    if q:
        f = f[f.sentence.str.contains(q, case=False) | f.context.str.contains(q, case=False)]
    view = pd.DataFrame({
        "date": f.date, "body": f.body.map(lambda b: BODY.get(b, b)), "time": f.ts,
        "types": f.assertion_types.map(", ".join),
        "authorities": f.authorities.map(lambda a: ", ".join(x["value"] for x in a)),
        "claim": f.sentence, "item": f.item_title.fillna(""), "item outcome": f.item_outcome.fillna(""),
        "response": f.response.map(lambda r: r["ts"] if isinstance(r, dict) else ""), "video": f.url,
    })
    st.caption(f"{len(view)} of {len(df)} claims. 'Response' is a candidate official statement later in the same item "
               "that names counsel or legal review, or repeats the claim's terms. A human needs to check it.")
    st.dataframe(view, hide_index=True, **_STRETCH,
                 column_config={"video": st.column_config.LinkColumn("video", display_text="▶ open")})


def _reconciliation(exc: List[Dict], key: str) -> None:
    checks = sorted({e["check"] for e in exc})
    c = st.columns(2)
    sel = c[0].selectbox("Check", checks, key=f"{key}_rc",
                         format_func=lambda k: {"R1": "R1 postponement continuity", "R2": "R2 ordinance lifecycle",
                                                "R3": "R3 agenda ↔ minutes coverage", "R4": "R4 minutes integrity",
                                                "R5": "R5 public commenters", "R6": "R6 attendance",
                                                "R7": "R7 citation grounding", "R8": "R8 executive sessions"}.get(k, k))
    only = c[1].toggle("Exceptions only", value=True, key=f"{key}_ro")
    rows = [e for e in exc if e["check"] == sel and (e.get("exception") or not only)]
    if not rows:
        st.success("No rows for this selection.")
        return
    df = pd.DataFrame(rows).drop(columns=["evidence_minutes", "steps"], errors="ignore")
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, (list, dict))).any():
            df[col] = df[col].map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
    cfg = {"url": st.column_config.LinkColumn("video", display_text="▶ open")} if "url" in df else {}
    st.dataframe(df, hide_index=True, **_STRETCH, column_config=cfg)
    if sel == "R8":
        st.caption("W.S. 16-4-405(a)(ix) is 'to consider or receive any information classified as confidential by law'. "
                   "(vii) is site selection or real-estate purchase, (x) is wage and benefit negotiations, and (iii) is "
                   "litigation. Under subsection (c), the motion's stated reason is the notice.")


def _lifecycles(lc: List[Dict], key: str) -> None:
    only = st.toggle("Flagged only", value=True, key=f"{key}_lo")
    rows = [l for l in lc if l["exception"] or not only]
    df = pd.DataFrame([{"first": l["first"], "last": l["last"], "ordinance": l["title"],
                        "readings": "→".join(map(str, l["readings"])), "adopted": l["adopted"],
                        "number": l["ordinance_number"], "flags": "; ".join(l["flags"])} for l in rows])
    st.dataframe(df, hide_index=True, **_STRETCH)
    pick = st.selectbox("Steps for", [r["title"][:120] for r in rows], key=f"{key}_ls") if rows else None
    if pick:
        l = next(r for r in rows if r["title"][:120] == pick)
        st.dataframe(pd.DataFrame([{k: (", ".join(v) if isinstance(v, list) else v) for k, v in s.items() if k != "title"}
                                   for s in l["steps"]]), hide_index=True, **_STRETCH)


def _votes(v: Dict, key: str) -> None:
    w = st.radio("Window", ["window_2026", "window_2025_2026"], horizontal=True, key=f"{key}_vw",
                 format_func=lambda x: "2026" if x == "window_2026" else "2025–2026")
    data = v[w]
    m = pd.DataFrame(data["members"])
    st.dataframe(m, hide_index=True, **_STRETCH)
    pa = pd.DataFrame(data["pairwise_agreement"])
    if not pa.empty:
        st.subheader("Pairwise agreement on contested votes")
        grid = pa.pivot_table(index="a", columns="b", values="agreement")
        st.dataframe(grid.style.background_gradient(cmap="RdYlGn", vmin=0, vmax=1).format("{:.2f}", na_rep=""),
                     **_STRETCH)
    st.subheader("Contested votes")
    cv = pd.DataFrame(data["contested"])
    if not cv.empty:
        cv["yes"] = cv["yes"].map(len).astype(str) + "–" + cv["no"].map(len).astype(str)
        cv["no"] = cv["no"].map(", ".join)
        st.dataframe(cv.rename(columns={"yes": "yes–no", "no": "voting no"}), hide_index=True, **_STRETCH)


def _meetings(meetings: List[Dict], items: List[Dict], key: str) -> None:
    df = pd.DataFrame(meetings)
    df["hours"] = (df.duration_s / 3600).round(2)
    df["public comment %"] = (df.public_comment_share.fillna(0) * 100).round()
    st.dataframe(df[["date", "body", "hours", "public comment %", "aligned_items", "claims", "minutes_available", "url"]],
                 hide_index=True, **_STRETCH,
                 column_config={"url": st.column_config.LinkColumn("video", display_text="▶ open")})
    st.caption("Public-comment share is an upper bound. It runs from an invitation to speak until the chair closes "
               "comment or calls for a motion.")
    dates = sorted({i["date"] for i in items})
    if dates:
        d = st.selectbox("Agenda items for", dates, index=len(dates) - 1, key=f"{key}_md")
        it = pd.DataFrame([i for i in items if i["date"] == d])
        it["minutes"] = (it.seconds.fillna(0) / 60).round(1)
        it["vote"] = it.vote.map(lambda v: f"{v['yes']}–{v['no']}" + (f" (no: {', '.join(v['dissent'])})" if v["dissent"] else "")
                                 if isinstance(v, dict) else "")
        st.dataframe(it[["item_no", "title", "start", "minutes", "outcome", "vote", "number", "claims",
                         "transcript_speaker_intros", "url"]], hide_index=True, **_STRETCH,
                     column_config={"url": st.column_config.LinkColumn("video", display_text="▶ open")})


def _passages(p: List[Dict], key: str) -> None:
    df = pd.DataFrame(p)
    c = st.columns(3)
    mode = c[0].radio("Show", ["v2 flagged", "dropped by v2", "added by v2", "all"], key=f"{key}_pm")
    q = c[1].text_input("Search preview", key=f"{key}_pq")
    if mode == "v2 flagged":
        df = df[df.v2_flag]
    elif mode == "dropped by v2":
        df = df[df.v1_flag & ~df.v2_flag]
    elif mode == "added by v2":
        df = df[df.v2_flag & ~df.v1_flag]
    if q:
        df = df[df.preview.str.contains(q, case=False)]
    df = df.sort_values("v2_score", ascending=False)
    c[2].metric("Passages", len(df))
    st.dataframe(df[["date", "body", "start", "v1_score", "v2_score", "strong_claims", "dominant_role",
                     "topical_terms_discounted", "deviations", "statutory", "preview", "url"]],
                 hide_index=True, **_STRETCH,
                 column_config={"url": st.column_config.LinkColumn("video", display_text="▶ open")})
