"""Push alerts: Slack, Discord, generic webhook, SMTP email.

Configured purely by environment variables (GitHub/Streamlit secrets):
  SLACK_WEBHOOK_URL, DISCORD_WEBHOOK_URL, ALERT_WEBHOOK_URL,
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO, ALERT_EMAIL_FROM,
  ALERT_MIN_SEVERITY (info|low|medium|high, default medium).
With nothing configured, alerts are written to data/out/alerts.log (dry run).
Alerts notify *you*; they never contact agencies or officials.
"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage

from .analyze import SEV_RANK
from .util import data_dir, now_iso

ICON = {"silent_edit": "🚨", "watchlist_hit": "🔎", "trend_flag": "📈", "sentiment_shift": "💬",
        "blocked_source": "⛔", "llm_flag": "🧠"}
LABEL = {"silent_edit": "Silent Edit Detected", "watchlist_hit": "Watchlist Hit",
         "trend_flag": "Trend Flag", "sentiment_shift": "Sentiment Shift",
         "blocked_source": "Blocked Source → Records Request", "llm_flag": "AI Red Flag (quote-verified)"}


def format_text(ev: dict) -> str:
    lines = [f"{ICON.get(ev['kind'], '•')} [{ev['jurisdiction']}] {LABEL.get(ev['kind'], ev['kind'])} ({ev['severity']})",
             ev["title"]]
    if ev.get("quote"):
        lines.append(f"> {ev['quote']}")
    if ev.get("source_url"):
        lines.append(f"Source: {ev['source_url']}")
    lines.append(f"Fetched: {ev.get('fetched_at') or ev.get('created_at')} | method={ev.get('method')}")
    return "\n".join(lines)


def _post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "WindyCityReaper-alerts/1.0"})
    urllib.request.urlopen(req, timeout=20).read()


def channels() -> list[str]:
    ch = []
    if os.getenv("SLACK_WEBHOOK_URL"):
        ch.append("slack")
    if os.getenv("DISCORD_WEBHOOK_URL"):
        ch.append("discord")
    if os.getenv("ALERT_WEBHOOK_URL"):
        ch.append("webhook")
    if os.getenv("SMTP_HOST") and os.getenv("ALERT_EMAIL_TO"):
        ch.append("email")
    return ch


def send(events: list[dict], dry_run: bool = False) -> dict:
    counts = {} if dry_run else {c: 0 for c in channels()}
    errors = []
    if not events:
        return {"sent": counts, "errors": errors, "dry_run": not counts}
    if not counts:
        out = data_dir() / "out"
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "alerts.log", "a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(f"--- {now_iso()} (dry run: no channel configured)\n{format_text(ev)}\n")
        return {"sent": {"log": len(events)}, "errors": errors, "dry_run": True}
    for ev in events:
        text = format_text(ev)
        for ch, fn in (("slack", lambda: _post_json(os.environ["SLACK_WEBHOOK_URL"], {"text": text})),
                       ("discord", lambda: _post_json(os.environ["DISCORD_WEBHOOK_URL"], {"content": text[:1990]})),
                       ("webhook", lambda: _post_json(os.environ["ALERT_WEBHOOK_URL"], {"event": ev, "text": text}))):
            if ch in counts:
                try:
                    fn()
                    counts[ch] += 1
                except Exception as e:  # never let one channel kill the cycle
                    errors.append(f"{ch}: {e}")
    if "email" in counts:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Windy City Reaper: {len(events)} new alert(s)"
            msg["From"] = os.getenv("ALERT_EMAIL_FROM", os.getenv("SMTP_USER", "reaper@localhost"))
            msg["To"] = os.environ["ALERT_EMAIL_TO"]
            msg.set_content("\n\n".join(format_text(e) for e in events))
            with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
                s.starttls()
                if os.getenv("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
                s.send_message(msg)
            counts["email"] = 1
        except Exception as e:
            errors.append(f"email: {e}")
    return {"sent": counts, "errors": errors, "dry_run": False}


def dispatch(conn, dry_run: bool = False) -> dict:
    min_rank = SEV_RANK.get(os.getenv("ALERT_MIN_SEVERITY", "medium"), 2)
    rows = conn.execute("SELECT * FROM events WHERE alerted=0 ORDER BY created_at, id").fetchall()
    from .db import event_dict
    due = [event_dict(r) for r in rows if SEV_RANK.get(r["severity"], 0) >= min_rank]
    result = send(due, dry_run=dry_run)
    conn.execute("UPDATE events SET alerted=1 WHERE alerted=0")
    conn.commit()
    result["count"] = len(due)
    return result
