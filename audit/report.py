"""Render audit/reports/ANALYSIS_2026.md from the build_analysis outputs.

Private members of the public are never named here. Public comment is identified
by its role and timestamp only, so a reader can go to the record and check it.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

BODY = {"city-council": "CC", "public-services-committee": "PSC", "finance-committee": "Finance"}
OUTCOME = {"carried": "carried", "failed": "failed", "postponed": "postponed", "referred": "referred",
           "died_no_second": "died (no second)", "withdrawn": "withdrawn", None: "—"}


_REDACT: List = []


def set_redactions(full_names, surnames_keep) -> None:
    """Names of members of the public (from the minutes' public-comment lists) to strip from quoted text."""
    _REDACT.clear()
    pats = []
    for full in sorted(full_names, key=len, reverse=True):
        parts = full.split()
        if len(parts) >= 2 and parts[-1] not in surnames_keep:
            pats.append(re.escape(full))
            pats.append(r"(?:Mr|Ms|Mrs|Miss|Dr)\.? " + re.escape(parts[-1]))
    if pats:
        _REDACT.append(re.compile(r"\b(?:" + "|".join(pats) + r")\b"))
    _REDACT.append(re.compile(r"\b(?:my name is|this is|name's)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z']+){0,2}", re.I))
    _REDACT.append(re.compile(r"(?<=record, )[A-Z][a-z]+(?: [A-Z][a-z']+){1,2}"))


def _redact(s: str) -> str:
    for rx in _REDACT:
        s = rx.sub("[member of the public]", s)
    return s


def _t(s: str, n: int = 90) -> str:
    s = _redact(s or "")
    s = re.sub(r"\s+", " ", s or "").strip().replace("|", "/")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _hm(sec) -> str:
    if not sec:
        return "—"
    return f"{sec // 3600}:{sec % 3600 // 60:02d}"


def _vote(v) -> str:
    if not v:
        return "—"
    s = f"{v['yes']}–{v['no']}"
    if v["dissent"]:
        s += " (no: " + ", ".join(v["dissent"]) + ")"
    return s


def write_report(path: Path, summary: Dict, meetings: List[Dict], items: List[Dict], claims: List[Dict],
                 exceptions: List[Dict], lifecycles: List[Dict], voting: Dict, aliases: List[Dict],
                 passages: List[Dict] = ()) -> None:
    h, v = summary["headline"], summary["validation"]
    L: List[str] = []
    w = L.append
    w("# Cheyenne Governing Body: Multi-Source Analysis, 2026")
    w("")
    w(f"_Generated {summary['generated_at']} by `audit/build_analysis.py`. Deterministic; rerun to reproduce._")
    w("")
    w("> **Read this first.** This report cross-checks three independent records of the same meetings: "
      "the YouTube caption transcripts, the official agendas, and the approved minutes. Captions are machine-generated "
      "and misspell names and statute numbers. Minutes text is PDF extraction and has spacing artifacts. Every finding "
      "below is a **lead for human review**, linked to its source, and not a conclusion. **Legal claims made by speakers "
      "are their allegations**; this report records that they were made, not whether they are correct.")
    w("")
    s = summary["sources"]
    w("## 1. What changed from v1")
    w("")
    w("v1 was a keyword classifier that read one transcript passage at a time. v2 adds four layers on top of it:")
    w("")
    w("| Layer | v1 | v2 |")
    w("|---|---|---|")
    w(f"| Sources | Captions only | Captions + {s['official_meetings']} official meetings ({s['official_agenda_items']:,} agenda items, {s['official_minutes']} minutes documents) |")
    w("| Unit of analysis | 1,200-character passage | Agenda item, with start/end time, outcome, vote and ordinance number |")
    w("| Who is speaking | Unknown | Each segment labelled as agenda reading, public comment or official |")
    w("| Legal language | Keyword hit | Claim: assertion type, polarity (asserted or denied), cited authority, item, outcome, candidate official response |")
    w("| Procedure | Keyword hit | Eight reconciliation checks (R1–R8) between the records |")
    w("| Votes | Not measured | Member-level voting record, contested votes, pairwise agreement |")
    w("| False positives | Stormwater 'detention', verb 'warrant' | Context exclusions in the lexicon (v2026.10.2); clerk readings of agenda titles down-weighted |")
    w("")
    w("## 2. Headline numbers")
    w("")
    w("| Measure | Value |")
    w("|---|---|")
    rows = [
        ("Council meetings aligned to their official agenda", h["council_meetings_aligned"]),
        ("Agenda items located in the video (start/end)", h["agenda_items_aligned"]),
        ("…of which joined to a minutes entry (outcome + vote)", h["items_joined_to_minutes"]),
        ("Legal-claim sentences detected", h["claims_total"]),
        ("…asserted (not denied)", h["claims_asserted"]),
        ("…strong (cites an authority, makes more than one kind of allegation, says 'unconstitutional', or alleges preemption or action without authority)", h["claims_strong_asserted"]),
        ("…made during public comment", h["claims_public_comment"]),
        ("…made by officials or staff", h["claims_official"]),
        ("Denials (e.g. \"this is not a violation\")", h["official_denials"]),
        ("Public-comment claims with a candidate official response in the same item", h["public_claims_with_candidate_response"]),
        ("Reconciliation checks run", h["reconciliation_checks_run"]),
        ("Reconciliation exceptions (leads)", h["reconciliation_exceptions"]),
        ("Contested roll-call votes in 2026 minutes", h["contested_votes_2026"]),
        ("Tie votes", h["tie_votes_2026"]),
        ("Passages flagged: v1 → v2", f"{h['passages_flagged_v1']} → {h['passages_flagged_v2']}"),
    ]
    for k, val in rows:
        w(f"| {k} | {val} |")
    w("")

    # ---------------------------------------------------------------- lifecycles
    w("## 3. Ordinance lifecycles (R2)")
    w("")
    lc = summary["lifecycles"]
    w(f"{lc['ordinances_tracked']} ordinances were traced across readings in the 2025–2026 minutes. {lc['adopted']} reached "
      f"adoption at third reading in the window, and {lc['flagged']} have a feature worth a look: a failed reading, "
      "repeated postponement, a substitute at third reading, or a reading with no recorded predecessor (usually because "
      "the earlier reading falls before January 2025).")
    w("")
    w("| First | Last | Ordinance | Readings | Adopted | Flags |")
    w("|---|---|---|---|---|---|")
    for l in [x for x in lifecycles if x["exception"] and any(k in f for k in ("failed", "substitute", "postponed", "pending") for f in x["flags"])]:
        w(f"| {l['first']} | {l['last']} | {_t(l['title'], 80)} | {'→'.join(map(str, l['readings']))} | "
          f"{('yes ' + (l['ordinance_number'] or '')).strip() if l['adopted'] else 'no'} | {_t('; '.join(l['flags']), 120)} |")
    w("")

    # ---------------------------------------------------------------- reconciliation
    exc = [e for e in exceptions if e.get("exception")]
    by = Counter(e["check"] for e in exc)
    run = summary["checks_run_by_check"]
    w("## 4. Reconciliation between the records (R1–R8)")
    w("")
    w("| Check | What it compares | Run | Exceptions |")
    w("|---|---|---|---|")
    desc = {"R1": "A postponement in the minutes vs the agenda of the target date",
            "R2": "Ordinance reading order across meetings (see §3)",
            "R3": "Substantive agenda items vs minutes entries, and minutes availability",
            "R4": "Internal consistency of minutes: motion without outcome, vote count vs roster",
            "R5": "Public commenters listed in minutes vs speaker introductions in the captions, per item",
            "R6": "Roll call heard in the captions vs attendance in the minutes",
            "R7": "Wyoming statute numbers spoken vs numbers in the official agenda and minutes",
            "R8": "Executive-session statutory basis: agenda vs minutes vs spoken"}
    for c in ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
        w(f"| {c} | {desc[c]} | {run.get(c, 0)} | {by.get(c, 0)} |")
    w("")
    w("R1 and R2 report every row, including the ones that pass. R3–R8 report a row only when there is something to compare.")
    w("")
    r1 = [e for e in exceptions if e["check"] == "R1"]
    if r1:
        ok = sum(1 for e in r1 if not e["exception"])
        w(f"**R1 postponement continuity.** {ok} of {len(r1)} postponements reappeared on the agenda of the date they were postponed to.")
        for e in [e for e in r1 if e["exception"]]:
            w(f"- {e.get('date')}: {_t(e.get('title', ''), 100)}: postponed to {e.get('postponed_to')}, not found on that agenda.")
        w("")
    for title, check in [("R3 agenda and minutes coverage", "R3"), ("R4 record integrity", "R4")]:
        rows = [e for e in exc if e["check"] == check]
        if rows:
            w(f"**{title}.**")
            seen = set()
            for e in rows:
                key = (e["date"], e.get("type"), e.get("title"))
                if key in seen:
                    continue
                seen.add(key)
                detail = e.get("type", "").replace("_", " ") or "agenda item with no matching minutes entry"
                extra = f" ({e['recorded']} recorded vs {e['roster']} present)" if "recorded" in e else ""
                extra += f" ({e['text_chars']} characters of text; probably a scanned PDF)" if "text_chars" in e else ""
                w(f"- {e['date']} {e.get('kind', '')}: {detail}{extra}" + (f": {_t(e['title'], 110)}" if e.get("title") else ""))
            w("")
    r5 = [e for e in exceptions if e["check"] == "R5"]
    if r5:
        w(f"**R5 public comment.** Compared on {len(r5)} items where the minutes list speakers or the captions show speaker "
          f"introductions. The correlation between the two counts is {v['public_comment_count_correlation_minutes_vs_captions']}. "
          "Large gaps usually mean the captions did not record the introduction (remote speakers, or the clerk calling names "
          "off-mic). They can also mean the minutes list is incomplete. Largest gaps:")
        w("")
        w("| Date | Item | Minutes list | Caption intros | Link |")
        w("|---|---|---|---|---|")
        for e in sorted([e for e in r5 if e["exception"]], key=lambda e: -abs(e["minutes_listed"] - e["transcript_intros"]))[:10]:
            w(f"| {e['date']} | {_t(e['title'], 70)} | {e['minutes_listed']} | {e['transcript_intros']} | [video]({e['url']}) |")
        w("")
    r6 = [e for e in exc if e["check"] == "R6"]
    w(f"**R6 attendance.** {run.get('R6', 0)} roll calls were compared; {len(r6)} disagree with the minutes.")
    for e in r6:
        w(f"- {e['date']} {BODY.get(e['body'], e['body'])}: " + "; ".join(e["issues"]))
    w("")
    r7 = [e for e in exceptions if e["check"] == "R7"]
    if r7:
        st = Counter(e["status"] for e in r7)
        w(f"**R7 citation grounding.** Out of {len(r7)} distinct statute numbers spoken (per meeting and role), "
          f"{st['in_official_record']} appear in that meeting's official agenda or minutes, "
          f"{st['caption_variant_of_official']} are near-misses of an official number (caption errors such as '15-1-42' "
          f"for 15-1-402), and {st['not_in_official_record']} appear only in the spoken record.")
        w("")
        w("| Date | Body | Spoken | Role | Link |")
        w("|---|---|---|---|---|")
        for e in [e for e in r7 if e["exception"]][:25]:
            w(f"| {e['date']} | {BODY.get(e['body'], e['body'])} | {e['citation']} | {e['role'].replace('_', ' ')} | [video]({e['url']}) |")
        w("")
    r8 = [e for e in exceptions if e["check"] == "R8"]
    if r8:
        n_mis = sum(1 for e in r8 if e["purpose_mismatch"])
        n_uns = sum(1 for e in r8 if any("without a subsection;" in n for n in e["notes"]))
        n_ix = sum(1 for e in r8 if e["spoken_purpose_basis"] == [9])
        cited = sorted({c for e in r8 if e["purpose_mismatch"] for c in set(e["agenda_basis"]) | set(e["minutes_basis"]) | set(e["spoken_basis"])})
        names = {3: "(a)(iii) litigation", 7: "(a)(vii) site selection or real-estate purchase", 10: "(a)(x) wage and benefit negotiations"}
        w(f"**R8 executive sessions.** {len(r8)} council meetings went into executive session under W.S. 16-4-405(a). "
          "Under subsection (c), a motion that \"specifies any of the reasons set forth in paragraphs (a)(i) through (xii)\" "
          "is sufficient notice of the issue. The subsection numbers agree between agenda, minutes and captions at every "
          f"meeting where all three give one. In {n_ix} of {len(r8)} spoken motions, however, the reason given is the same: "
          "\"to consider or receive any information classified as confidential by law\", which is the wording of **(a)(ix)**. "
          f"At {n_mis} meetings the cited subsection is a different one: " + ", ".join(names.get(c, f"(a)({c})") for c in cited) +
          f". At {n_uns} meetings no subsection is cited in the agenda or minutes, so the (ix) wording is the only reason "
          "given. Whether the cited number or the spoken wording controls is a legal question for counsel. The "
          "table only shows that the two differ. Statute text: 2025 Wyoming Statutes §16-4-405 "
          "(https://law.justia.com/codes/wyoming/title-16/chapter-4/article-4/section-16-4-405/).")
        w("")
        w("| Date | Agenda cites | Minutes cite | Motion cites (captions) | Reason stated aloud | Notes | Link |")
        w("|---|---|---|---|---|---|---|")
        rn = lambda xs: ", ".join(f"(a)({R_ROMAN.get(x, x)})" for x in xs) or "(a) only"  # noqa: E731
        for e in r8:
            w(f"| {e['date']} | {rn(e['agenda_basis'])} | {rn(e['minutes_basis']) if e['minutes_basis'] or 'minutes not yet available' not in e['notes'] else 'n/a'} | "
              f"{rn(e['spoken_basis'])} | {rn(e['spoken_purpose_basis']) if e['spoken_purpose_basis'] else '—'} | "
              f"{_t('; '.join(n for n in e['notes'] if not n.startswith('spoken motion states')), 120) or '—'} | [video]({e['url']}) |")
        w("")

    # ---------------------------------------------------------------- claims
    w("## 5. Legal claims made on the record")
    w("")
    asserted = [c for c in claims if c["polarity"] == "assert"]
    types = Counter(t for c in asserted for t in c["assertion_types"])
    roles = Counter(c["role"] for c in asserted)
    w("A claim is a sentence that says something is a violation, illegal, unconstitutional, void, preempted, procedurally "
      "defective or non-compliant. Each claim records its type, whether it was asserted or denied, any authority cited, "
      "who was speaking (by role), the agenda item, and what happened to that item.")
    w("")
    w("| Assertion type | Count |")
    w("|---|---|")
    for k, n in types.most_common():
        w(f"| {k.replace('_', ' ')} | {n} |")
    w("")
    w("By speaker role: " + ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in roles.most_common()) + ".")
    w("")
    if summary["claims_by_authority_class"]:
        w("Authorities cited alongside claims: " + ", ".join(
            f"{k.replace('_', ' ')} {n}" for k, n in summary["claims_by_authority_class"].items()) + ".")
        w("")
    by_item = Counter((c["date"], c["item_title"]) for c in asserted if c["item_title"])
    w("**Items that drew the most legal claims:**")
    w("")
    w("| Date | Item | Claims | Outcome | Final vote |")
    w("|---|---|---|---|---|")
    for (d, t), n in by_item.most_common(12):
        it = next((i for i in items if i["date"] == d and i["title"][:200] == t), None)
        w(f"| {d} | {_t(t, 80)} | {n} | {OUTCOME.get(it['outcome'], it['outcome']) if it else '—'} | {_vote(it['vote']) if it else '—'} |")
    w("")
    strong_pc = [c for c in asserted if c["strength"] == "strong" and c["role"] == "public_comment"]
    w(f"**Strong claims made in public comment ({len(strong_pc)}).** These are the allegations most likely to need a "
      "documented answer. 'Response' means an official statement later in the same item that names counsel or legal review, "
      "or repeats the claim's authority or key terms. It is a candidate for a human to check, not proof that the point was addressed.")
    w("")
    w("| Date | Time | Claim (excerpt) | Authority | Item outcome | Candidate response |")
    w("|---|---|---|---|---|---|")
    for c in strong_pc[:30]:
        au = ", ".join(a["value"] for a in c["authorities"][:2]) or "—"
        resp = f"[{c['response']['ts']}]({c['url'].split('&t=')[0]}&t={_sec(c['response']['ts'])}s)" if c["response"] else "none found"
        w(f"| {c['date']} | [{c['ts']}]({c['url']}) | {_t(c['sentence'], 110)} | {_t(au, 40)} | "
          f"{OUTCOME.get(c['item_outcome'], c['item_outcome'])} | {resp} |")
    w("")
    off = [c for c in claims if c["role"] == "official" and c["strength"] == "strong"]
    w(f"**Strong legal statements by officials and staff ({len(off)}),** including denials. Excerpts:")
    w("")
    for c in off[:12]:
        w(f"- {c['date']} [{c['ts']}]({c['url']}) _{c['polarity']}_: {_t(c['sentence'], 160)}")
    w("")

    # ---------------------------------------------------------------- votes
    w("## 6. Voting record (2026 minutes)")
    w("")
    w("No-rate is no votes divided by all votes cast. Minority rate is how often the member was on the losing side, "
      "counting contested votes only. Motions and seconds are taken from the minutes.")
    w("")
    w("| Member | Votes cast | No | No-rate | Contested | Minority rate | Motions | Seconds | Absent |")
    w("|---|---|---|---|---|---|---|---|---|")
    for m in sorted(voting["members"], key=lambda r: -(r.get("no_rate") or 0)):
        if not m.get("votes_cast"):
            continue
        w(f"| {m['member']} | {m['votes_cast']} | {m.get('no_votes', 0)} | {m['no_rate']} | {m.get('contested_votes', 0)} | "
          f"{m['minority_rate_contested'] if m['minority_rate_contested'] is not None else '—'} | {m.get('motions_made', 0)} | "
          f"{m.get('motions_seconded', 0)} | {m.get('meetings_absent', 0)} |")
    w("")
    pairs = voting["pairwise_agreement"]
    if pairs:
        w("Lowest pairwise agreement on contested votes: " + "; ".join(
            f"{p['a']}–{p['b']} {p['agreement']} (n={p['contested_votes_together']})" for p in pairs[:5]) + ". Highest: " + "; ".join(
            f"{p['a']}–{p['b']} {p['agreement']}" for p in pairs[-3:]) + ".")
        w("")
    close = [c for c in voting["contested"] if c["margin"] <= 2]
    w(f"**Close votes (margin of 2 or less): {len(close)}.**")
    w("")
    w("| Date | Item | Motion | Result | Yes–No | Voting no |")
    w("|---|---|---|---|---|---|")
    for c in close:
        w(f"| {c['date']} | {_t(c['title'], 70)} | {_t(c['motion'], 40)} | {c['result'] or '—'}{' (tie)' if c['tie'] else ''} | "
          f"{len(c['yes'])}–{len(c['no'])} | {', '.join(c['no'])} |")
    w("")

    # ---------------------------------------------------------------- time
    w("## 7. Where meeting time goes")
    w("")
    w("Shares are computed from segment timestamps. 'Public comment' runs from an invitation to speak until the chair "
      "closes it or a motion is called for, so it also counts any staff answers given in between; read it as an upper bound. 'Agenda reading' is the clerk reading item titles.")
    w("")
    w("| Date | Body | Length | Public comment | Items aligned | Longest item (outcome) |")
    w("|---|---|---|---|---|---|")
    for m in meetings:
        if not m["official_match"]:
            continue
        li = m["longest_items"][0] if m["longest_items"] else None
        w(f"| {m['date']} | {BODY.get(m['body'], m['body'])} | {_hm(m['duration_s'])} | "
          f"{round(100 * (m['public_comment_share'] or 0))}% | {m['aligned_items']} | "
          f"{(_t(li['title'], 60) + ' — ' + _hm(li['seconds']) + ' (' + OUTCOME.get(li['outcome'], str(li['outcome'])) + ')') if li else '—'} |")
    w("")

    # ---------------------------------------------------------------- passages
    w("## 8. Passage flags, v1 vs v2")
    w("")
    w("v2 rescoring starts from the v1 keyword score and makes three changes:")
    w("")
    w("- A marker that appears in the official title of the agenda item under discussion is dropped. 'Warrant' during "
      "the Administrative Inspection Warrants ordinance is the topic, not a sign of deviation.")
    w("- The score is multiplied by 0.25 when most of the passage is the clerk reading agenda titles.")
    w("- Each strong asserted legal claim in the passage adds 3, and each other claim adds 1.")
    w("")
    w(f"Flag rule: score above 3.0 (the v1 threshold), or any strong asserted claim. Flags: {h['passages_flagged_v1']} "
      f"(v1) → {h['passages_flagged_v2']} (v2). {h['v1_flags_removed_topic_terms']} v1 flags were dropped because their "
      f"markers were the item's own subject, {h['v1_flags_removed_other']} for other reasons, and "
      f"{h['flags_added_by_claims']} passages were newly flagged because of the legal claims in them. The lexicon "
      "exclusions (stormwater detention, 'warrant' as a verb, 'curb appeal', prepayment penalty) apply to both versions.")
    w("")
    top = sorted([p for p in passages if p["v2_flag"]], key=lambda p: -p["v2_score"])[:12]
    if top:
        w("| Date | Body | Time | v1 | v2 | Strong claims | Markers |")
        w("|---|---|---|---|---|---|---|")
        for p in top:
            w(f"| {p['date']} | {BODY.get(p['body'], p['body'])} | [{p['start']}]({p['url']}) | {p['v1_score']} | {p['v2_score']} | "
              f"{p['strong_claims']} | {_t(', '.join(p['deviations'] + p['statutory']), 60) or '—'} |")
        w("")

    # ---------------------------------------------------------------- validation
    w("## 9. Validation and limits")
    w("")
    w("| Check | Result |")
    w("|---|---|")
    w(f"| Aligned items where the spoken item number matched the agenda | {v['alignment_number_match_rate']:.0%} |")
    w(f"| Aligned items joined to a minutes entry | {v['items_with_minutes_match_rate']:.0%} |")
    w(f"| Correlation of public-comment counts, minutes vs captions ({v['r5_items_compared']} items) | {v['public_comment_count_correlation_minutes_vs_captions']} |")
    w(f"| Caption name mentions resolved to a canonical member | {v['alias_mentions_resolved']:.0%} |")
    w("")
    w("- **Alignment covers items that are announced aloud.** Consent-agenda items approved in a single motion have no start "
      "time of their own, so the aligned share is lower on long consent agendas.")
    w("- **The minutes parser was spot-checked against the source text** for every key result in this report "
      "(for example, Ch. 1.28 at third reading on 2026-02-09: carried by substitute as amended, 7–3, #4656). The "
      "parser has unit tests. Minutes from 2025-08-11 are a scanned PDF with no text and are excluded.")
    w("- **Claims are detected by pattern.** In a hand-checked random sample of 30 strong asserted claims, about 22 of "
      "the 24 from public comment were genuine legal allegations about a government action. Only 1 of the 6 attributed "
      "to officials was; the rest were staff describing enforcement against third parties, or hypothetical questions. "
      "Use the public-comment claims as a ledger and treat the official-side counts as mentions. Sarcasm and "
      "quotation are not detected.")
    w("- **Quoted text is redacted.** Names of members of the public found in the minutes' public-comment lists, and "
      "spoken self-introductions, are replaced with [member of the public].")
    w("- **Speaker roles are inferred** from public-comment opening and closing phrases. A commenter who keeps speaking "
      "after the chair closes public comment, or staff speaking during it, will be mislabelled.")
    w("- **Committee meetings** are compared to the official record only when the archive holds a matching agenda.")
    w("")
    w("Full outputs (gitignored, regenerate with `python3 audit/build_analysis.py`): `audit/output/analysis/` → "
      "`claims.jsonl`, `items.jsonl`, `exceptions.jsonl`, `lifecycles.json`, `voting.json`, `meetings.json`, `aliases.json`, "
      "`passages_v2.jsonl`.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


R_ROMAN = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii", 8: "viii", 9: "ix", 10: "x", 11: "xi", 12: "xii", 13: "xiii"}


def _sec(ts: str) -> int:
    h, m, s = (int(x) for x in ts.split(":"))
    return h * 3600 + m * 60 + s
