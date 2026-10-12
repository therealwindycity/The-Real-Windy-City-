"""
BUILD ANALYSIS (v2)
===================

Runs the whole multi-source analysis and writes:

    audit/output/analysis/claims.jsonl       legal assertions with item, outcome and response linkage
    audit/output/analysis/items.jsonl        transcript-aligned agenda items joined to minutes outcomes
    audit/output/analysis/exceptions.jsonl   R1-R8 reconciliation exceptions (and passes, flagged false)
    audit/output/analysis/lifecycles.json    ordinance reading sequences (R2)
    audit/output/analysis/voting.json        voting record from the minutes
    audit/output/analysis/meetings.json      per-meeting time allocation, roles, coverage
    audit/output/analysis/aliases.json       caption spelling -> canonical member
    audit/output/analysis/passages_v2.jsonl  v1 passages rescored with role, claim and exclusion context
    audit/reports/analysis_summary.json      headline numbers (committed)
    audit/reports/ANALYSIS_2026.md           the written report (committed)

Usage:  python3 audit/build_analysis.py [--since 2026-01-01]
Requires audit/reference/official_records.json (see official_records.py).
Deterministic: identical inputs always produce byte-identical outputs, apart from the generated_at date.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from alignment import align, label_roles, count_comment_starts, item_at, hms  # noqa: E402
from audit_ingest_node import (RegulatoryAuditPipeline, _timestamped_segments, DEFAULT_TRANSCRIPTS,  # noqa: E402
                               DEFAULT_OUTPUT, iter_transcripts)
from claims import extract_claims, link_responses, authorities  # noqa: E402
from minutes_parser import parse_minutes  # noqa: E402
import reconcile as R  # noqa: E402

REF = HERE / "reference" / "official_records.json"
OUT = HERE / "output" / "analysis"
REPORTS = HERE / "reports"
BODY_TO_KIND = {"city-council": ("City Council Meeting", "City Council"),
                "public-services-committee": ("Public Services Committee",),
                "finance-committee": ("Finance Committee",)}


def jdump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False))


def jsonl(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def official_for(meeting: Dict, official: List[Dict]) -> Optional[Dict]:
    kinds = BODY_TO_KIND.get(meeting["body"])
    if not kinds:
        return None
    for m in official:
        if m["date"] == meeting["date"] and m["kind"] in kinds and not m["special"]:
            return m
    return None


def minutes_entry_for(title: str, entries: List[Dict]) -> Tuple[Optional[Dict], float]:
    best, bs = None, 0.0
    for e in entries:
        s = R.title_sim(title, e["title"])
        if s > bs:
            best, bs = e, s
    return (best, bs) if bs >= 0.3 else (None, bs)


def final_vote(entry: Dict) -> Optional[Dict]:
    votes = [v for v in entry["events"] if v["type"] == "vote"]
    if not votes:
        return None
    v = votes[-1]
    return {"yes": len(v["yes"]), "no": len(v["no"]), "dissent": v["no"], "not_voting": v.get("not_voting", [])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--transcripts", type=Path, default=DEFAULT_TRANSCRIPTS)
    a = ap.parse_args(argv)

    ref = json.loads(REF.read_text())
    official = ref["meetings"]
    pms = []
    for m in official:
        for x in m["minutes"]:
            pms.append({"date": m["date"], "kind": m["kind"], "special": m["special"], "text_chars": len(x["text"]),
                        "minutes_url": x["url"], "parsed": parse_minutes(x["text"])})
    pms_by = {(p["date"], p["kind"]): p for p in pms}
    roster = R.canonical_roster(pms, since=a.since)
    pipe = RegulatoryAuditPipeline(output_path=OUT / "_unused.jsonl")
    catalog = json.loads((a.transcripts / "meetings.json").read_text())

    claims_all, items_all, exceptions, meetings_out = [], [], [], []
    caption_names = Counter()
    seg_index: Dict[str, Tuple[List[Tuple[str, str]], List[str]]] = {}

    for mt in sorted([m for m in catalog if m.get("file")], key=lambda m: (m["date"], m["body"])):
        if not re.match(r"\d{4}-\d{2}-\d{2}$", mt["date"]) or mt["date"] < a.since:
            continue
        text = (a.transcripts / mt["file"]).read_text(encoding="utf-8")
        segs = _timestamped_segments(text, 600)
        if not segs:
            continue
        for _, t in segs:
            for o in pipe.extract_entities(t)["officials"]:
                caption_names[o] += 1
        off = official_for(mt, official)
        aligned = align(segs, off["items"]) if off else []
        anchor_ts = {x.start for x in aligned}
        roles = label_roles(segs, anchor_ts)
        seg_index[mt["file"]] = (segs, roles, aligned)
        url = f"https://www.youtube.com/watch?v={mt['youtube_id']}"
        pm = pms_by.get((off["date"], off["kind"])) if off else None
        entries = pm["parsed"]["entries"] if pm else []

        # item bounds in segment indices
        seg_starts = [hms(ts) for ts, _ in segs]
        bounds = []
        for x in aligned:
            lo = next((i for i, s in enumerate(seg_starts) if s >= hms(x.start)), len(segs))
            hi = next((i for i, s in enumerate(seg_starts) if x.end and s >= hms(x.end)), len(segs))
            bounds.append((lo, hi))

        # ---- items joined to minutes
        meeting_items = []
        for x, (lo, hi) in zip(aligned, bounds):
            e, sim = minutes_entry_for(x.title, entries)
            starts = count_comment_starts(segs[lo:hi], roles[lo:hi])
            role_secs = Counter()
            for k in range(lo, hi):
                nxt = seg_starts[k + 1] if k + 1 < len(segs) else seg_starts[k]
                role_secs[roles[k]] += max(0, nxt - seg_starts[k])
            row = {
                "date": mt["date"], "body": mt["body"], "item_no": x.item_no, "title": x.title, "consent": x.consent,
                "start": x.start, "end": x.end, "seconds": x.seconds, "url": f"{url}&t={hms(x.start)}s",
                "align_score": x.score, "number_matched": x.number_matched,
                "minutes_match": round(sim, 2) if e else None,
                "outcome": e["final_result"] if e else None, "reading": e["reading"] if e else None,
                "postponed_to": e["postponed_to"] if e else None, "number": e["number"] if e else None,
                "vote": final_vote(e) if e else None,
                "minutes_public_commenters": e["public_commenters"] if e else [],
                "transcript_speaker_intros": starts,
                "seconds_by_role": dict(role_secs),
                "claims": 0, "strong_claims": 0,
            }
            meeting_items.append(row)
            # R5 public-comment roster
            if e is not None:
                listed = len(e["public_commenters"])
                if listed or starts:
                    window = " ".join(t for _, t in segs[lo:hi]).lower()
                    found = [p for p in e["public_commenters"]
                             if any(len(w) > 3 and w.lower() in window for w in re.findall(r"[A-Za-z']+", p.split(",")[0])[-1:])]
                    diff = listed - starts
                    related = [r for r in entries if r is not e and r["public_commenters"]
                               and R.title_sim(x.title, r["title"]) >= 0.3] if listed == 0 else []
                    exc = (listed >= 2 and starts == 0) or (listed == 0 and starts >= 2 and not related) or abs(diff) >= 4
                    if related and listed == 0:
                        exc = False
                    exceptions.append({"check": "R5", "date": mt["date"], "body": mt["body"], "item_no": x.item_no,
                                       "title": x.title[:200], "minutes_listed": listed, "transcript_intros": starts,
                                       "listed_surnames_heard": len(found), "url": row["url"],
                                       "attributed_to_related_item": related[0]["title"][:160] if related else None,
                                       "exception": exc})

        # ---- claims
        cl = extract_claims(segs, roles)
        link_responses(cl, segs, roles, bounds)
        for c in cl:
            it = item_at(aligned, c["ts"]) if aligned else None
            irow = next((r for r in meeting_items if it and r["item_no"] == it.item_no and r["start"] == it.start), None)
            if irow:
                irow["claims"] += 1
                irow["strong_claims"] += c["strength"] == "strong" and c["polarity"] == "assert"
            claims_all.append({
                "date": mt["date"], "body": mt["body"], "file": mt["file"], "ts": c["ts"],
                "url": f"{url}&t={hms(c['ts'])}s", "role": c["role"], "speaker_hint": c["speaker_hint"],
                "assertion_types": c["assertion_types"], "polarity": c["polarity"], "strength": c["strength"],
                "authorities": c["authorities"], "sentence": c["sentence"], "context": c["context"],
                "item_no": irow["item_no"] if irow else None, "item_title": irow["title"][:200] if irow else None,
                "item_outcome": irow["outcome"] if irow else None, "item_vote": irow["vote"] if irow else None,
                "response": c["response"],
            })

        # ---- R6 attendance, R7 citations, R8 executive session
        if pm:
            rc = R.roll_call_from_transcript(segs, roster)
            att = R.attendance_check(pm["parsed"]["roster"], rc)
            if att:
                exceptions.append({"check": "R6", "date": mt["date"], "body": mt["body"],
                                   "minutes_present": pm["parsed"]["roster"]["present"],
                                   "minutes_absent": pm["parsed"]["roster"]["absent"],
                                   "minutes_partial": pm["parsed"]["roster"]["partial"], **att})
            official_text = " ".join(it["title"] for it in off["items"]) + " " + " ".join(
                x["text"] for x in off["minutes"])
            cites = []
            for (ts, t), r in zip(segs, roles):
                for au in authorities(t):
                    if au["class"] == "wyoming_statute":
                        cites.append((au["value"], r, ts))
            seen = set()
            for row in R.citation_grounding(cites, official_text):
                k = (row["core"], row["role"])
                if k in seen:
                    continue
                seen.add(k)
                exceptions.append({**row, "date": mt["date"], "body": mt["body"], "url": f"{url}&t={hms(row['ts'])}s"})
        if off:
            agenda_basis = R.exec_basis(" ".join(it["title"] for it in off["items"]))
            minutes_text = re.sub(r"-\s+", "-", " ".join(x["text"] for x in off["minutes"]))
            minutes_basis = R.exec_basis(minutes_text)
            agenda_text = re.sub(r"-\s+", "-", " ".join(it["title"] for it in off["items"]))
            unspecified = [src for src, txt in (("agenda", agenda_text), ("minutes", minutes_text))
                           if re.search(r"16-4-405\s*\(a\)(?!\s*\()", txt)]
            motion_ts, motion_text = None, ""
            for k, (ts, t) in enumerate(segs):
                if re.search(r"executive session", t, re.I) and re.search(r"16\s?-?\s?4\s?-?\s?405|pursuant", " ".join(
                        x for _, x in segs[max(0, k - 2): k + 1]), re.I):
                    motion_ts = segs[max(0, k - 2)][0]
                    motion_text = " ".join(x for _, x in segs[max(0, k - 2): k + 3])
                    break
            sp = R.exec_spoken(motion_text)
            if agenda_basis or minutes_basis or sp["numbers"] or motion_text or unspecified:
                cited = set(agenda_basis) | set(minutes_basis) | set(sp["numbers"])
                sets = [set(x) for x in (agenda_basis, minutes_basis, sp["numbers"]) if x]
                numbers_consistent = all(x == sets[0] for x in sets) if sets else True
                purpose_mismatch = bool(sp["purpose_language"]) and bool(cited) and not (set(sp["purpose_language"]) & cited)
                notes = []
                if not numbers_consistent:
                    notes.append("subsection numbers differ between agenda, minutes and spoken motion")
                if purpose_mismatch:
                    notes.append("spoken motion states the purpose of " + ", ".join(
                        f"(a)({R._roman(p)}) [{R.EXEC_PURPOSES[p][0]}]" for p in sp["purpose_language"]) +
                        " but cites " + ", ".join(f"(a)({R._roman(c)})" + (f" [{R.EXEC_PURPOSES[c][0]}]" if c in R.EXEC_PURPOSES else "")
                                                   for c in sorted(cited)))
                if agenda_basis and not minutes_basis and pm:
                    notes.append("agenda cites a basis but the minutes do not")
                if not pm:
                    notes.append("minutes not yet available")
                if unspecified:
                    notes.append(" and ".join(unspecified) + " cite 16-4-405(a) without a subsection" +
                                 ("; the only reason stated aloud is the " + ", ".join(
                                     f"(a)({R._roman(p)})" for p in sp["purpose_language"]) + " wording"
                                  if sp["purpose_language"] else ""))
                if motion_text and sp["cited_without_subsection"] and not sp["numbers"]:
                    notes.append("spoken motion cites 16-4-405 without a subsection (as captioned)")
                exceptions.append({"check": "R8", "date": mt["date"], "body": mt["body"],
                                   "agenda_basis": agenda_basis, "minutes_basis": minutes_basis,
                                   "spoken_basis": sp["numbers"], "spoken_purpose_basis": sp["purpose_language"],
                                   "consistent": numbers_consistent, "purpose_mismatch": purpose_mismatch,
                                   "notes": notes, "url": f"{url}&t={hms(motion_ts)}s" if motion_ts else url,
                                   "exception": bool(notes) and (not numbers_consistent or purpose_mismatch or
                                                                 (agenda_basis and not minutes_basis and pm) or bool(unspecified))})

        dur = seg_starts[-1]
        role_secs = Counter()
        for k in range(len(segs)):
            nxt = seg_starts[k + 1] if k + 1 < len(segs) else seg_starts[k]
            role_secs[roles[k]] += max(0, nxt - seg_starts[k])
        substantive = [it for it in (off["items"] if off else []) if not it["consent"]
                       and re.match(r"(?:ORDINANCE|RESOLUTION|Public Hearing|.*Agreement|.*Plat|Consideration)", it["title"])]
        meetings_out.append({
            "date": mt["date"], "body": mt["body"], "file": mt["file"], "url": url, "duration_s": dur,
            "official_match": bool(off), "minutes_available": bool(pm),
            "aligned_items": len(aligned), "substantive_nonconsent_items": len(substantive),
            "seconds_by_role": dict(role_secs),
            "public_comment_share": round(role_secs["public_comment"] / dur, 3) if dur else None,
            "claims": sum(1 for c in claims_all if c["file"] == mt["file"]),
            "longest_items": sorted([{"item_no": r["item_no"], "title": r["title"][:120], "seconds": r["seconds"],
                                      "outcome": r["outcome"]} for r in meeting_items if r["seconds"]],
                                    key=lambda r: -r["seconds"])[:3],
        })
        items_all.extend(meeting_items)

    # ---- official-record-only checks
    pms_window = [p for p in pms if p["date"] >= "2025-01-01"]
    exceptions.extend(R.postponement_continuity(pms_window, official))
    lifecycles = R.reading_sequences(pms_window, official)
    for lc in lifecycles:
        if lc["exception"]:
            exceptions.append({"check": "R2", "title": lc["title"], "first": lc["first"], "last": lc["last"],
                               "readings": lc["readings"], "flags": lc["flags"], "adopted": lc["adopted"],
                               "exception": True})
    exceptions.extend(R.agenda_minutes_coverage(pms_window, official))
    exceptions.extend(R.record_integrity(pms_window))
    unavailable = [{"check": "R3", "type": "minutes_text_unavailable", "date": p["date"], "kind": p["kind"],
                    "text_chars": p["text_chars"], "minutes_url": p["minutes_url"], "exception": True}
                   for p in pms_window if p["text_chars"] < 400]
    exceptions.extend(unavailable)

    voting_2026 = R.voting_record([p for p in pms if p["date"] >= a.since])
    voting_all = R.voting_record(pms_window)
    aliases = R.alias_table(caption_names, roster)

    # ---- passages v2 (rescore v1 passages with role, claim and exclusion context)
    v1_path = DEFAULT_OUTPUT
    if not v1_path.exists():
        pipe.output_path = v1_path
        pipe.process_and_persist(iter_transcripts(a.transcripts), "text", source={"type": "transcript"}, mode="rebuild")
    claims_by_file = defaultdict(list)
    for c in claims_all:
        claims_by_file[c["file"]].append(c)
    passages_v2 = []
    w_dev, w_stat, thr = pipe.w_dev, pipe.w_stat, pipe.threshold
    tally = Counter()
    with v1_path.open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            raw, cls = p["raw_source"], p["audit_classification"]
            if p["source"].get("type") != "transcript":
                continue
            file = p["source"]["file"]
            segs, roles, aligned = seg_index.get(file, ([], [], []))
            start, end = hms(raw["start"]), hms(raw["end"]) + 1
            rs = Counter(r for (ts, _), r in zip(segs, roles) if start <= hms(ts) <= end)
            total = sum(rs.values()) or 1
            dominant = rs.most_common(1)[0][0] if rs else "unknown"
            it = item_at(aligned, raw["start"]) if aligned else None
            title = (it.title.lower() if it else "")
            topical = sorted({ev["term"] for ev in cls["evidence"] if title and ev["term"].lower() in title})
            discount = sum(w_dev if ev["category"] == "procedural_deviation" else w_stat
                           for ev in {(e["term"], e["category"]): e for e in cls["evidence"]}.values()
                           if ev["term"] in topical)
            pc = [c for c in claims_by_file.get(file, []) if start <= hms(c["ts"]) <= end]
            strong = sum(1 for c in pc if c["strength"] == "strong" and c["polarity"] == "assert")
            weak = len(pc) - strong
            base = cls["compliance_friction_score"]
            role_factor = 0.25 if rs["agenda_reading"] / total >= 0.5 else 1.0
            lexical = max(0.0, base - discount) * role_factor
            score = round(lexical + 3.0 * strong + 1.0 * weak, 2)
            v1_flag = cls["remediation_status"] == "Eligible for Administrative Review"
            v2_flag = score > thr or strong >= 1
            if v1_flag and not v2_flag:
                tally["removed_topical" if discount else "removed_other"] += 1
            if v2_flag and not v1_flag:
                tally["added_by_claims"] += 1
            tally["v1"] += v1_flag
            tally["v2"] += v2_flag
            passages_v2.append({"record_id": p["record_id"], "date": raw["date"], "body": raw["body"],
                                "start": raw["start"], "url": raw["url"], "v1_score": base, "v1_flag": v1_flag,
                                "v2_score": score, "v2_flag": v2_flag, "dominant_role": dominant,
                                "role_mix": {k: round(v / total, 2) for k, v in rs.items()},
                                "item": it.title[:160] if it else None, "topical_terms_discounted": topical,
                                "strong_claims": strong, "weak_claims": weak,
                                "deviations": [t for t in cls["procedural_deviations"] if t != "None identified"],
                                "statutory": [t for t in cls["statutory_reference_points"] if t != "None identified"],
                                "preview": raw["text"][:220]})
    flagged_v1, flagged_v2 = tally["v1"], tally["v2"]

    # ---- write outputs
    jsonl(OUT / "claims.jsonl", claims_all)
    jsonl(OUT / "items.jsonl", items_all)
    jsonl(OUT / "exceptions.jsonl", exceptions)
    jsonl(OUT / "passages_v2.jsonl", passages_v2)
    jdump(OUT / "lifecycles.json", lifecycles)
    jdump(OUT / "voting.json", {"since": a.since, "window_2026": voting_2026, "window_2025_2026": voting_all})
    jdump(OUT / "meetings.json", meetings_out)
    jdump(OUT / "aliases.json", aliases)

    summary = summarize(meetings_out, items_all, claims_all, exceptions, lifecycles, voting_2026, aliases,
                        passages_v2, flagged_v1, flagged_v2, tally, ref, a.since)
    jdump(REPORTS / "analysis_summary.json", summary)
    from report import write_report, set_redactions  # noqa: E402
    public_names = {n.split(",")[0].strip() for p in pms for e in p["parsed"]["entries"] for n in e["public_commenters"]}
    set_redactions(public_names, set(roster))
    write_report(REPORTS / "ANALYSIS_2026.md", summary, meetings_out, items_all, claims_all, exceptions,
                 lifecycles, voting_2026, aliases, passages_v2)
    print(json.dumps(summary["headline"], indent=1))
    return 0


def summarize(meetings, items, claims, exceptions, lifecycles, voting, aliases, passages, f1, f2, tally, ref, since):
    exc = [e for e in exceptions if e.get("exception")]
    by_check = Counter(e["check"] for e in exc)
    checks_run = Counter(e["check"] for e in exceptions)
    cc = [m for m in meetings if m["body"] == "city-council"]
    r5 = [e for e in exceptions if e["check"] == "R5"]
    pairs = [(e["minutes_listed"], e["transcript_intros"]) for e in r5]
    corr = None
    if len(pairs) > 3 and len({p[0] for p in pairs}) > 1 and len({p[1] for p in pairs}) > 1:
        corr = round(statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs]), 3)
    assert_claims = [c for c in claims if c["polarity"] == "assert"]
    pc_claims = [c for c in assert_claims if c["role"] == "public_comment"]
    with_resp = [c for c in pc_claims if c["response"]]
    auth_classes = Counter(a["class"] for c in assert_claims for a in c["authorities"])
    outcome_after = Counter(c["item_outcome"] for c in pc_claims if c["item_outcome"])
    contested = voting["contested"]
    return {
        "generated_at": date.today().isoformat(),
        "since": since,
        "sources": {"transcripts": len(meetings), "official_meetings": len(ref["meetings"]),
                    "official_agenda_items": sum(len(m["items"]) for m in ref["meetings"]),
                    "official_minutes": sum(len(m["minutes"]) for m in ref["meetings"]),
                    "official_source_commit": ref["generated_from"].get("commit")},
        "headline": {
            "council_meetings_aligned": sum(1 for m in cc if m["aligned_items"]),
            "agenda_items_aligned": len(items),
            "items_joined_to_minutes": sum(1 for i in items if i["outcome"]),
            "claims_total": len(claims), "claims_asserted": len(assert_claims),
            "claims_strong_asserted": sum(1 for c in assert_claims if c["strength"] == "strong"),
            "claims_public_comment": len(pc_claims), "claims_official": sum(1 for c in assert_claims if c["role"] == "official"),
            "official_denials": sum(1 for c in claims if c["polarity"] == "deny"),
            "public_claims_with_candidate_response": len(with_resp),
            "reconciliation_checks_run": sum(checks_run.values()),
            "reconciliation_exceptions": len(exc),
            "contested_votes_2026": len(contested),
            "tie_votes_2026": sum(1 for v in contested if v["tie"]),
            "passages_flagged_v1": f1, "passages_flagged_v2": f2,
            "v1_flags_removed_topic_terms": tally["removed_topical"], "v1_flags_removed_other": tally["removed_other"],
            "flags_added_by_claims": tally["added_by_claims"],
        },
        "exceptions_by_check": dict(sorted(by_check.items())),
        "checks_run_by_check": dict(sorted(checks_run.items())),
        "validation": {
            "alignment_number_match_rate": round(sum(i["number_matched"] for i in items) / max(1, len(items)), 3),
            "items_with_minutes_match_rate": round(sum(1 for i in items if i["outcome"]) / max(1, len(items)), 3),
            "public_comment_count_correlation_minutes_vs_captions": corr,
            "r5_items_compared": len(pairs),
            "alias_mentions_resolved": round(sum(r["mentions"] for r in aliases if r["canonical"]) /
                                             max(1, sum(r["mentions"] for r in aliases)), 3),
        },
        "claims_by_authority_class": dict(auth_classes.most_common()),
        "public_claim_item_outcomes": dict(outcome_after.most_common()),
        "lifecycles": {"ordinances_tracked": len(lifecycles), "adopted": sum(1 for l in lifecycles if l["adopted"]),
                       "flagged": sum(1 for l in lifecycles if l["exception"])},
    }


if __name__ == "__main__":
    sys.exit(main())
