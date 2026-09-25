"""Multi-state public-records request drafts.

Two kinds:
  pra          — targeted request for specific records.
  bulk_access  — auto-drafted when a source blocks automated retrieval; asks the
                 custodian for the same public records through the statutory
                 channel instead.

Everything is a DRAFT. A human reviews, signs and sends (LEGAL.md). There is
deliberately no auto-submission.
"""
from __future__ import annotations

import datetime as dt
import os

from .util import load_json, now, now_iso

PRA_TEMPLATE = """\
{requester_name}
{requester_contact}

{date}

Records Custodian
{custodian}

RE: Public Records Request — {law_name}, {cite}

Dear Records Custodian:

Pursuant to the {law_name} ({cite}), I request copies of the following public records:

RECORDS SOUGHT:
{records_description}

DATE RANGE: {date_range}

I prefer electronic copies (email or download link) in the format in which the
records are currently maintained. If any portion is withheld, please release all
reasonably segregable portions and cite the specific statutory exemption relied
upon for each withholding.

If fees are expected to exceed {fee_limit}, please send a written estimate before
proceeding so that I can narrow or confirm the request.
{deadline_line}
Thank you for your help.

Sincerely,
{requester_name}

---
Drafted by Windy City Reaper on {drafted_at}. REVIEW, EDIT AND SIGN BEFORE SENDING.
Statute citation and deadline: verify against current law. Not legal advice.
"""

BULK_TEMPLATE = """\
{requester_name}
{requester_contact}

{date}

Records Custodian
{custodian}

RE: Bulk Electronic Records Request — {law_name}, {cite}

Dear Records Custodian:

Pursuant to the {law_name} ({cite}), I request bulk electronic copies of:

{records_description}

for the period {date_range}, in the format currently maintained by the agency
(PDF/HTML acceptable). These records are published at:
{source_url}

I am submitting this request because automated retrieval of these specific
pages is restricted at the platform level ({block_reason}); I am seeking the
same public records through the statutory request process rather than working
around that restriction.

If feasible, I would also welcome a standing arrangement (e.g. a shared folder
or periodic export) for future agendas, packets and minutes, which may reduce
staff time for repeat requests.

If fees are expected to exceed {fee_limit}, please send a written estimate first.
{deadline_line}
Thank you,
{requester_name}

---
Drafted by Windy City Reaper on {drafted_at}. REVIEW, EDIT AND SIGN BEFORE SENDING.
Statute citation and deadline: verify against current law. Not legal advice.
"""


def statute(state: str) -> dict:
    table = load_json("statutes.json")
    s = table.get(state.upper())
    if s:
        return s
    return {"name": f"{state.upper()} public records law", "cite": f"[VERIFY: {state.upper()} public records statute]",
            "response_days": None, "business": False}


def add_days(start: dt.datetime, days: int, business: bool) -> dt.datetime:
    d = start
    if not business:
        return d + dt.timedelta(days=days)
    added = 0
    while added < days:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:  # weekends skipped; holidays are not modeled
            added += 1
    return d


def _requester(identity: dict | None = None) -> tuple[str, str]:
    identity = identity or {}
    name = os.getenv("REQUESTER_NAME") or identity.get("requester_name") or "[YOUR NAME]"
    contact = os.getenv("REQUESTER_CONTACT") or identity.get("contact") or "[YOUR EMAIL / PHONE]"
    return name, contact


def _deadline_line(s: dict) -> str:
    if s.get("response_days"):
        unit = "business days" if s.get("business") else "calendar days"
        note = f" {s['note'].rstrip('.')}." if s.get("note") else ""
        return f"\nI understand the law provides for a response within {s['response_days']} {unit}.{note}\n"
    return "\nI look forward to your prompt response as the law requires.\n"


def draft(kind: str, *, state: str, custodian: str, records_description: str,
          date_range: str = "January 1, 2025 to present", source_url: str = "",
          block_reason: str = "robots.txt disallow", fee_limit: str = "$50",
          identity: dict | None = None) -> tuple[str, str]:
    """Return (subject, body)."""
    s = statute(state)
    name, contact = _requester(identity)
    fields = dict(
        requester_name=name, requester_contact=contact, date=now().strftime("%B %d, %Y"),
        custodian=custodian, law_name=s["name"], cite=s["cite"],
        records_description=records_description, date_range=date_range,
        source_url=source_url or "(n/a)", block_reason=block_reason, fee_limit=fee_limit,
        deadline_line=_deadline_line(s), drafted_at=now_iso())
    tpl = BULK_TEMPLATE if kind == "bulk_access" else PRA_TEMPLATE
    prefix = "Bulk electronic records request" if kind == "bulk_access" else "Public records request"
    subject = f"{prefix} — {s['cite']} — {records_description[:80]}"
    return subject, tpl.format(**fields)


def save_request(conn, *, jurisdiction: str, jcfg: dict, kind: str, records_description: str,
                 source_url: str = "", dedupe_key: str | None = None, identity: dict | None = None,
                 **kw) -> tuple[int, bool]:
    """Insert a draft (idempotent on dedupe_key). Returns (request_id, created)."""
    if dedupe_key:
        row = conn.execute("SELECT id FROM requests WHERE dedupe_key=?", (dedupe_key,)).fetchone()
        if row:
            return row["id"], False
    subject, body = draft(kind, state=jcfg["state"], custodian=jcfg.get("custodian", jcfg.get("agency", "")),
                          records_description=records_description, source_url=source_url,
                          identity=identity, **kw)
    cur = conn.execute(
        """INSERT INTO requests(dedupe_key, jurisdiction, state, kind, agency, subject, body,
               source_url, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (dedupe_key, jurisdiction, jcfg["state"], kind, jcfg.get("agency"), subject, body,
         source_url, "draft", now_iso()))
    conn.commit()
    return cur.lastrowid, True


def mark_sent(conn, request_id: int, sent_at: dt.datetime | None = None):
    """Human marks a request as sent -> engine computes the statutory due date."""
    row = conn.execute("SELECT state FROM requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise KeyError(request_id)
    sent = sent_at or now()
    s = statute(row["state"])
    due = add_days(sent, s["response_days"], s.get("business", False)).date().isoformat() if s.get("response_days") else None
    conn.execute("UPDATE requests SET status='sent', sent_at=?, due_at=? WHERE id=?",
                 (sent.isoformat(), due, request_id))
    conn.commit()
    return due


def refresh_overdue(conn) -> int:
    today = now().date().isoformat()
    cur = conn.execute(
        "UPDATE requests SET status='overdue' WHERE status='sent' AND due_at IS NOT NULL AND due_at < ?",
        (today,))
    conn.commit()
    return cur.rowcount
