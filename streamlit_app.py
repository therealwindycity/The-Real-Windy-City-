"""Windy City Reaper — Civic Accountability Command Center (Streamlit)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import __version__, db, ledger, pipeline, records
from engine.alerts import LABEL
from engine.analyze import SEV_RANK
from engine.util import ROOT, load_config, now

st.set_page_config(page_title="Windy City Reaper", page_icon="🌪️", layout="wide")

SECRET_KEYS = ("SLACK_WEBHOOK_URL", "DISCORD_WEBHOOK_URL", "ALERT_WEBHOOK_URL", "SMTP_HOST", "SMTP_PORT",
               "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO", "ALERT_EMAIL_FROM", "ALERT_MIN_SEVERITY",
               "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "REQUESTER_NAME", "REQUESTER_CONTACT")
try:  # Streamlit Community Cloud: App settings -> Secrets
    for _k in SECRET_KEYS:
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # no secrets.toml locally
    pass

KIND_COLOR = {  # RGBA hex for st.map
    "silent_edit": "#e5383bdd", "watchlist_hit": "#f4a261dd", "trend_flag": "#4ea8dedd",
    "sentiment_shift": "#48cae4dd", "llm_flag": "#b388ebdd", "blocked_source": "#adb5bddd",
}
KIND_EMOJI = {"silent_edit": "🚨", "watchlist_hit": "🔎", "trend_flag": "📈",
              "sentiment_shift": "💬", "llm_flag": "🧠", "blocked_source": "⛔"}
SEV_BADGE = {"high": "🔴 high", "medium": "🟠 medium", "low": "🟡 low", "info": "⚪ info"}
STATUSES = ["draft", "reviewed", "sent", "answered", "denied", "overdue"]

st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.reaper-quote {border-left: 4px solid #e4572e; padding: .4rem .8rem; background: rgba(228,87,46,.08);
               font-family: Georgia, serif; margin: .3rem 0 .6rem 0;}
.reaper-meta {color: #8b949e; font-size: .82rem;}
.reaper-banner {background: repeating-linear-gradient(45deg,#3a2a00,#3a2a00 12px,#2a2000 12px,#2a2000 24px);
                color:#ffd166; padding:.5rem .9rem; border-radius:6px; font-weight:600; margin-bottom:.8rem;}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ data access
LIVE_DIR = ROOT / "data"
DEMO_DIR = ROOT / "data" / "demo"


@st.cache_resource(show_spinner=False)
def get_conn(path: str):
    return db.connect(path)


def build_demo():
    from engine.selftest import run_fixture_world
    logs: list[str] = []
    conn, checks = run_fixture_world(DEMO_DIR, log=logs.append)
    conn.close()
    get_conn.clear()
    return logs, checks


def events_df(conn, days: int, jur: list[str], kinds: list[str], min_sev: str) -> pd.DataFrame:
    since = (now() - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")
    rows = db.list_events(conn, since=since, limit=5000)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if jur:
        df = df[df["jurisdiction"].isin(jur)]
    if kinds:
        df = df[df["kind"].isin(kinds)]
    df = df[df["severity"].map(lambda s: SEV_RANK.get(s, 0)) >= SEV_RANK[min_sev]]
    return df.reset_index(drop=True)


def with_coords(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Events without coordinates are pinned near their jurisdiction's center (deterministic jitter)."""
    out = df.copy()
    lat, lon = [], []
    for _, r in out.iterrows():
        if pd.notna(r.get("lat")) and pd.notna(r.get("lon")):
            lat.append(r["lat"]); lon.append(r["lon"]); continue
        c = cfg["jurisdictions"].get(r["jurisdiction"], {}).get("center", [39.8, -98.6])
        h = hashlib.sha256(r["id"].encode()).digest()
        lat.append(c[0] + (h[0] - 128) / 128 * 0.035)
        lon.append(c[1] + (h[1] - 128) / 128 * 0.05)
    out["lat"], out["lon"] = lat, lon
    out["color"] = out["kind"].map(lambda k: KIND_COLOR.get(k, "#ffffffaa"))
    out["size"] = out["severity"].map({"high": 260, "medium": 180, "low": 120, "info": 90}).fillna(90)
    return out


def live_event_count() -> int:
    if not live_db.exists():
        return 0
    try:
        return get_conn(str(live_db)).execute("SELECT count(*) FROM events").fetchone()[0]
    except Exception:
        return 0


# ------------------------------------------------------------------ sidebar
base_cfg = load_config()
live_db = LIVE_DIR / "engine.db"
demo_db = DEMO_DIR / "engine.db"

with st.sidebar:
    st.markdown("## 🌪️ Windy City Reaper")
    st.caption(f"Civic Accountability Edition · v{__version__}")
    default_mode = 0 if live_event_count() > 0 else 1
    mode = st.radio("Dataset", ["Live ledger", "Demo (synthetic)"], index=default_mode, horizontal=True)
    is_demo = mode.startswith("Demo")

if is_demo:
    from engine.fixtures import demo_config
    cfg = demo_config(base_cfg)
    if not demo_db.exists():
        with st.spinner("Building the offline demo (runs the real pipeline against local fixtures)…"):
            build_demo()
    conn = get_conn(str(demo_db))
    data_root = DEMO_DIR
else:
    cfg = base_cfg
    conn = get_conn(str(live_db))
    data_root = LIVE_DIR
    for jkey, src in pipeline.iter_sources(cfg, include_disabled=True):
        db.upsert_source(conn, jkey, src)
    conn.commit()

jlabels = {k: v.get("label", k) for k, v in cfg["jurisdictions"].items()}
with st.sidebar:
    home = cfg.get("default_jurisdiction")
    home = [home] if home in jlabels else []
    jur = st.multiselect("Jurisdictions", list(jlabels), default=home, format_func=jlabels.get,
                         help="Opens on the home jurisdiction (`default_jurisdiction` in config/jurisdictions.json). "
                              "Clear it to see every city.")
    kinds = st.multiselect("Event types", list(LABEL), format_func=lambda k: f"{KIND_EMOJI.get(k, '')} {LABEL[k]}")
    min_sev = st.select_slider("Minimum severity", ["info", "low", "medium", "high"], value="info")
    days = st.slider("Window (days)", 1, 365, 90)
    st.divider()
    if is_demo:
        if st.button("↻ Rebuild demo", width="stretch"):
            with st.spinner("Re-running two civic cycles against fixtures…"):
                logs, checks = build_demo()
            st.session_state["demo_log"] = logs
            st.rerun()
    st.caption("Every event carries a verbatim quote, a source URL and a fetch timestamp. "
               "If it isn't quotable, it isn't asserted.")

if is_demo:
    st.markdown('<div class="reaper-banner">DEMO MODE — synthetic fixture data produced by running the real '
                'pipeline against a local test server. Nothing here describes a real agency.</div>',
                unsafe_allow_html=True)

st.title("🌪️ Windy City Reaper")
st.caption("Tiered, robots-aware civic intelligence: official APIs → RSS → HTML → rendered HTML → "
           "statutory records requests when a door is closed.")

df = events_df(conn, days, jur, kinds, min_sev)
open_reqs = conn.execute("SELECT count(*) FROM requests WHERE status IN ('draft','reviewed','sent','overdue')").fetchone()[0]
overdue = conn.execute("SELECT count(*) FROM requests WHERE status='overdue'").fetchone()[0]
src_rows = conn.execute("SELECT last_status, count(*) n FROM sources WHERE enabled=1 GROUP BY last_status").fetchall()
src_stat = {r["last_status"] or "never run": r["n"] for r in src_rows}

c = st.columns(5)
c[0].metric("Events in window", len(df))
c[1].metric("High severity", int((df["severity"] == "high").sum()) if not df.empty else 0)
c[2].metric("Silent edits", int((df["kind"] == "silent_edit").sum()) if not df.empty else 0)
c[3].metric("Open records requests", open_reqs, delta=f"{overdue} overdue" if overdue else None,
            delta_color="inverse")
c[4].metric("Sources OK / blocked", f"{src_stat.get('ok', 0)} / {src_stat.get('blocked', 0) + src_stat.get('legal_channel', 0)}")

tabs = st.tabs(["🗺️ Live Intel", "🔎 Search", "📈 Trends", "⚖️ Records Requests", "🛰️ Sources", "🔗 Ledger"])


def show_captured_copy(e: dict, key_prefix: str):
    """The engine's own archived copy: evidence survives even if the agency edits or deletes the page."""
    if not e.get("source_url"):
        return
    doc = conn.execute("SELECT id, version_count FROM documents WHERE url=?", (e["source_url"],)).fetchone()
    if not doc:
        return
    versions = conn.execute("SELECT hash, fetched_at, text FROM versions WHERE document_id=? ORDER BY id DESC",
                            (doc["id"],)).fetchall()
    if not versions:
        return
    if st.toggle(f"📄 Captured copy ({len(versions)} version{'s' if len(versions) != 1 else ''})",
                 key=f"{key_prefix}-cap-{e['id']}"):
        labels = [f"{v['fetched_at']} · sha256 {v['hash'][:12]}…" for v in versions]
        i = st.selectbox("Version", range(len(versions)), format_func=labels.__getitem__,
                         key=f"{key_prefix}-ver-{e['id']}") if len(versions) > 1 else 0
        st.text_area("Stored text", versions[i]["text"] or "", height=220, disabled=True,
                     key=f"{key_prefix}-txt-{e['id']}-{i}")


def render_event(e: dict, key_prefix: str):
    st.markdown(f"**{SEV_BADGE.get(e['severity'], e['severity'])} · {LABEL.get(e['kind'], e['kind'])}** · "
                f"{jlabels.get(e['jurisdiction'], e['jurisdiction'])}")
    if e.get("quote"):
        st.markdown(f'<div class="reaper-quote">“{e["quote"]}”</div>', unsafe_allow_html=True)
    meta = f"fetched {e.get('fetched_at') or e.get('created_at')} · method `{e.get('method')}` · id `{e['id']}`"
    if e.get("hash"):
        meta += f" · sha256 `{str(e['hash'])[:12]}…`"
    st.markdown(f'<div class="reaper-meta">{meta}</div>', unsafe_allow_html=True)
    if e.get("source_url"):
        if is_demo:
            st.caption("Source is a synthetic fixture URL (local test server), so there is no public link. "
                       "The captured copy below is exactly what the engine stored.")
        else:
            st.markdown(f"[Open source ↗]({e['source_url']})")
    data = e.get("data") or {}
    show_captured_copy(e, key_prefix)
    if e["kind"] == "silent_edit" and data.get("unified_diff"):
        st.code(data["unified_diff"], language="diff")
    if e["kind"] == "watchlist_hit" and data.get("hits"):
        st.dataframe(pd.DataFrame(data["hits"])[["label", "severity", "count", "quote"]],
                     hide_index=True, width="stretch")
    if e["kind"] in ("trend_flag", "sentiment_shift") and data.get("values"):
        st.line_chart(pd.DataFrame({"value": data["values"]}, index=data.get("buckets")))
    if e["kind"] == "llm_flag" and data.get("why"):
        st.caption(f"Model rationale (quote verified verbatim against source): {data['why']}")
    jcfg = cfg["jurisdictions"].get(e["jurisdiction"])
    if jcfg and e["kind"] != "blocked_source":
        if st.button("⚖️ Draft records request about this", key=f"{key_prefix}-pra-{e['id']}"):
            desc = (f"All records, including communications, staff reports, bids, contracts and drafts, "
                    f"relating to: {e['title']} (source: {e.get('source_url') or 'n/a'})")
            rid, created = records.save_request(conn, jurisdiction=e["jurisdiction"], jcfg=jcfg, kind="pra",
                                                records_description=desc, source_url=e.get("source_url") or "",
                                                dedupe_key=f"pra:event:{e['id']}", identity=cfg.get("identity"))
            st.success(f"{'Drafted' if created else 'Already drafted'} request #{rid} — see ⚖️ Records Requests.")


with tabs[0]:
    if df.empty:
        st.info("No events in this window yet. " + (
            "Run a cycle from 🛰️ Sources (or `python run.py cycle`), or switch to the demo dataset."
            if not is_demo else "Rebuild the demo from the sidebar."))
    else:
        m = with_coords(df, cfg)
        left, right = st.columns([3, 2])
        with left:
            st.map(m, latitude="lat", longitude="lon", color="color", size="size", height=430)
            st.caption("🔴 silent edit · 🟠 watchlist hit · 🔵 trend / sentiment · 🟣 AI flag (quote-verified) · "
                       "⚪ blocked → records request. Pins without coordinates sit near the city center.")
        with right:
            counts = df.groupby("kind").size().rename(lambda k: f"{KIND_EMOJI.get(k, '')} {LABEL.get(k, k)}")
            st.bar_chart(counts, horizontal=True, height=200)
            by_j = df.groupby("jurisdiction").size().rename(lambda k: jlabels.get(k, k))
            st.bar_chart(by_j, horizontal=True, height=200)

        table = df.assign(
            type=df["kind"].map(lambda k: f"{KIND_EMOJI.get(k, '')} {LABEL.get(k, k)}"),
            sev=df["severity"].map(SEV_BADGE),
            place=df["jurisdiction"].map(jlabels),
        )[["created_at", "sev", "type", "place", "title", "quote", "source_url"]]
        st.dataframe(table, hide_index=True, width="stretch", height=320,
                     column_config={
                         "created_at": st.column_config.DatetimeColumn("When", format="YYYY-MM-DD HH:mm"),
                         "sev": "Severity", "type": "Type", "place": "Jurisdiction", "title": "Title",
                         "quote": st.column_config.TextColumn("Verbatim quote", width="large"),
                         "source_url": (st.column_config.TextColumn("Source (synthetic)") if is_demo
                                        else st.column_config.LinkColumn("Source", display_text="open ↗")),
                     })
        st.subheader("Event detail")
        ranked = sorted(df.to_dict("records"), key=lambda e: (-SEV_RANK.get(e["severity"], 0), e["created_at"]))
        for e in ranked[:60]:
            with st.expander(f"{KIND_EMOJI.get(e['kind'], '•')} {e['title']}"):
                render_event(e, "feed")
        if len(ranked) > 60:
            st.caption(f"Showing 60 of {len(ranked)} — narrow the filters or use the API for the rest.")


with tabs[1]:
    q = st.text_input("Full-text search across every captured document version",
                      placeholder='e.g. variance, "no-bid", annexation, change order')
    if q:
        hits = db.search(conn, q, jur[0] if len(jur) == 1 else None, limit=100)
        st.caption(f"{len(hits)} result(s) · SQLite FTS5 with porter stemming")
        for h in hits:
            snippet = (h.get("snippet") or "").replace("[[", "**").replace("]]", "**")
            head = f"**{h['title'] or h['url']}**" if is_demo else f"**[{h['title'] or h['url']}]({h['url']})**"
            st.markdown(f"{head} · {jlabels.get(h['jurisdiction'], h['jurisdiction'])} "
                        f"· `{h['method']}` · fetched {h['last_fetched']}\n\n> …{snippet}…")


with tabs[2]:
    series_rows = conn.execute("SELECT DISTINCT jurisdiction, series FROM metrics ORDER BY 1, 2").fetchall()
    if not series_rows:
        st.info("No metric series yet. Socrata sources with a `group_field` and RSS sources with "
                "`sentiment: true` populate this after a cycle.")
    else:
        opts = [f"{r['jurisdiction']} · {r['series']}" for r in series_rows]
        pick = st.selectbox("Series", opts)
        jkey, series = pick.split(" · ", 1)
        mdf = pd.DataFrame(db.get_series(conn, jkey, series))
        pivot = mdf.pivot_table(index="bucket", columns="grp", values="value").sort_index()
        flagged = {e["data"].get("group") for e in db.list_events(conn, jurisdiction=jkey, kind="trend_flag", limit=500)
                   if e["data"].get("series") == series}
        spark = pd.DataFrame({
            "group": pivot.columns,
            "trend": [pivot[c].dropna().tolist() for c in pivot.columns],
            "latest": [pivot[c].dropna().iloc[-1] if pivot[c].notna().any() else None for c in pivot.columns],
            "flag": ["📈 FLAG" if c in flagged else "" for c in pivot.columns],
        }).sort_values(["flag", "latest"], ascending=[False, False])
        a, b = st.columns([2, 3])
        with a:
            st.dataframe(spark, hide_index=True, width="stretch", height=420, column_config={
                "group": "Group", "latest": st.column_config.NumberColumn("Latest", format="%.2f"),
                "trend": st.column_config.LineChartColumn("Trend (all buckets)"), "flag": "Flag"})
        with b:
            default = [g for g in spark["group"].tolist() if g in flagged][:5] or spark["group"].tolist()[:5]
            chosen = st.multiselect("Plot groups", spark["group"].tolist(), default=default)
            if chosen:
                st.line_chart(pivot[chosen], height=380)
            if series == "sentiment":
                st.caption("Lexicon polarity (−1…+1) of sentences mentioning each topic in local news feeds, per ISO week.")
            else:
                st.caption("The current month is partial and excluded from trend flags.")


with tabs[3]:
    st.markdown("Every request is a **draft**. Review it, sign it and send it yourself. Mark it *sent* here and "
                "the engine computes the statutory response deadline and flags it overdue when that passes.")
    with st.expander("➕ New public-records request", expanded=False):
        with st.form("new_pra"):
            j = st.selectbox("Jurisdiction", list(jlabels), format_func=jlabels.get,
                             index=list(jlabels).index(home[0]) if home else 0)
            desc = st.text_area("Records sought", placeholder="e.g. All emails between the City Manager and "
                                "Project Latigo representatives regarding water allocation")
            rng = st.text_input("Date range", "January 1, 2025 to present")
            fee = st.text_input("Fee ceiling before estimate required", "$50")
            if st.form_submit_button("Draft request") and desc.strip():
                rid, _ = records.save_request(conn, jurisdiction=j, jcfg=cfg["jurisdictions"][j], kind="pra",
                                              records_description=desc.strip(), date_range=rng, fee_limit=fee,
                                              identity=cfg.get("identity"))
                st.success(f"Draft #{rid} created.")
    records.refresh_overdue(conn)
    rq = pd.read_sql_query("SELECT id, jurisdiction, state, kind, status, subject, created_at, sent_at, due_at, notes "
                           "FROM requests ORDER BY id DESC", conn)
    if rq.empty:
        st.info("No requests yet. Blocked sources draft them automatically; you can also draft one above "
                "or from any event.")
    else:
        edited = st.data_editor(
            rq, hide_index=True, width="stretch", key="req_editor",
            disabled=["id", "jurisdiction", "state", "kind", "subject", "created_at", "sent_at", "due_at"],
            column_config={"status": st.column_config.SelectboxColumn("Status", options=STATUSES, required=True),
                           "notes": st.column_config.TextColumn("Notes", width="medium"),
                           "subject": st.column_config.TextColumn("Subject", width="large")})
        if st.button("💾 Save status / notes"):
            for old, new in zip(rq.to_dict("records"), edited.to_dict("records")):
                if new["status"] == "sent" and old["status"] != "sent":
                    records.mark_sent(conn, int(new["id"]))
                elif new["status"] != old["status"]:
                    conn.execute("UPDATE requests SET status=? WHERE id=?", (new["status"], int(new["id"])))
                if (new.get("notes") or "") != (old.get("notes") or ""):
                    conn.execute("UPDATE requests SET notes=? WHERE id=?", (new.get("notes"), int(new["id"])))
            conn.commit()
            st.success("Saved.")
            st.rerun()

        rid = st.selectbox("Open request", rq["id"].tolist(),
                           format_func=lambda i: f"#{i} · {rq.set_index('id').loc[i, 'subject'][:100]}")
        row = conn.execute("SELECT * FROM requests WHERE id=?", (int(rid),)).fetchone()
        body = st.text_area("Letter (edit freely before sending)", row["body"], height=460, key=f"body-{rid}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Save edits to letter", key=f"save-{rid}"):
            conn.execute("UPDATE requests SET body=? WHERE id=?", (body, int(rid)))
            conn.commit()
            st.success("Letter saved.")
        c2.download_button("⬇️ Download .txt", body, file_name=f"records-request-{rid}.txt", key=f"dl-{rid}")
        mailto = "mailto:?" + urllib.parse.urlencode({"subject": row["subject"], "body": body[:1800]},
                                                     quote_via=urllib.parse.quote)
        c3.link_button("✉️ Open in my email client", mailto)
        s = records.statute(row["state"])
        st.caption(f"Statute: {s['name']} — {s['cite']}. {s.get('note', '')} Verify before sending; not legal advice.")


with tabs[4]:
    sdf = pd.read_sql_query("SELECT key, method, enabled, last_status, last_run, items_last_run, last_detail, url "
                            "FROM sources ORDER BY key", conn)
    icon = {"ok": "🟢 ok", "blocked": "⛔ blocked → PRA", "legal_channel": "⚖️ legal channel",
            "error": "🔴 error", None: "⚫ never run"}
    sdf["last_status"] = sdf["last_status"].map(lambda s: icon.get(s, s))
    sdf["enabled"] = sdf["enabled"].astype(bool)
    st.dataframe(sdf, hide_index=True, width="stretch", column_config={
        "key": "Source", "method": "Tier", "enabled": "Enabled", "last_status": "Status",
        "last_run": "Last run", "items_last_run": "Items", "last_detail": st.column_config.TextColumn("Detail", width="large"),
        "url": st.column_config.TextColumn("URL") if is_demo else st.column_config.LinkColumn("URL", display_text="open ↗")})
    st.markdown("""
**Tier order:** `api` (Socrata) → `legistar` / `elms` (official legislation APIs) → `rss` → `html` → `playwright` (rendered, robots-gated) → `pra_only`.
Every networked tier checks `robots.txt` with an honest, identifying User-Agent. A refusal (robots disallow, 401/403/451)
is logged as a ⛔ event and becomes a drafted bulk-access request under that state's public-records law.
Add cities or sources in `config/jurisdictions.json`.""")
    if not is_demo:
        st.divider()
        jsel = st.multiselect("Run a live cycle for", list(jlabels), format_func=jlabels.get, key="cycle_j")
        if st.button("▶️ Run civic cycle now", type="primary"):
            logs: list[str] = []
            with st.status("Running civic cycle (polite: ≥3s between hits per host)…", expanded=True) as box:
                try:
                    pipeline.cycle(conn, cfg, jurisdictions=jsel or None, log=lambda m: (logs.append(m), box.write(m)))
                    box.update(label="Cycle complete", state="complete")
                except Exception as ex:
                    box.update(label=f"Cycle failed: {ex}", state="error")
            st.session_state["last_cycle_log"] = logs
        if st.session_state.get("last_cycle_log"):
            st.code("\n".join(st.session_state["last_cycle_log"]), language="text")
    elif st.session_state.get("demo_log"):
        st.code("\n".join(st.session_state["demo_log"]), language="text")


with tabs[5]:
    lpath = data_root / "ledger" / "events.jsonl"
    ok, n, msg = ledger.verify(lpath)
    (st.success if ok else st.error)(f"{'✅ Chain intact' if ok else '❌ CHAIN BROKEN'} — {msg}")
    st.markdown("Each ledger line stores `prev_hash` and `entry_hash = sha256(prev_hash + entry)`. Editing or deleting "
                "any past entry breaks every hash after it, so the watchdog is held to the same silent-edit standard it "
                "applies to governments. The GitHub Action commits this file every cycle, so git history is a second witness.")
    if lpath.exists():
        lines = lpath.read_text(encoding="utf-8").splitlines()
        tail = [json.loads(x) for x in lines[-50:] if x.strip()]
        st.dataframe(pd.DataFrame(tail)[["created_at", "kind", "severity", "title", "entry_hash", "prev_hash"]][::-1],
                     hide_index=True, width="stretch")
        st.download_button("⬇️ Download full ledger (JSONL)", "\n".join(lines), file_name="events.jsonl")

st.divider()
st.caption("Windy City Reaper · public records, politely collected, relentlessly cross-checked · "
           "[Legal & ethics contract](https://github.com/therealwindycity/The-Real-Windy-City-/blob/main/LEGAL.md)")
