"""
RECONCILIATION ENGINE
=====================

Cross-checks three independent records of the same meetings:

    A. official agendas    (what the city said it would take up)
    B. official minutes    (what the clerk recorded happened)
    C. caption transcripts (what was audibly said)

Checks (each one emits ``exceptions`` with evidence from both sides):

R1  postponement_continuity  every "postponed to <date>" in B reappears on A for that date
R2  reading_sequence         ordinances move 1st -> 2nd -> 3rd reading in order, with dates and outcomes
R3  agenda_minutes_coverage  every substantive agenda item in A has an action recorded in B
R4  record_integrity         B: motions with no recorded outcome; vote lists that don't add up to the roster
R5  public_comment_roster    B's listed public commenters vs. speaker introductions detected in C
R6  attendance               B's present/absent roster vs. C's roll call
R7  citation_grounding       statutes cited in C vs. statutes in A/B (caption variants corrected)
R8  executive_session_basis  the statutory basis cited for closed sessions, compared across A, B and C

Also builds the voting record (B) and the caption-alias table that maps caption
spellings to the canonical roster.

An exception is a discrepancy *between records*, or an internal inconsistency
in one. Most have innocent explanations: caption gaps, clerk shorthand, items
renumbered or withdrawn. Each one is a pointer for a person to check against the
source PDFs and video. None is a finding of wrongdoing.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from alignment import tokens

_PREFIX = re.compile(r"^\s*(?:\[CA\]\s*)?(?:ORDINANCE|RESOLUTION)\s*[-–]\s*(?:\d(?:st|nd|rd|th)\s+READING\s*[-–]\s*)?", re.I)


def title_key(title: str) -> set:
    return tokens(_PREFIX.sub("", title or ""))


def title_sim(a: str, b: str) -> float:
    ta, tb = title_key(a), title_key(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def days(a: str, b: str) -> int:
    from datetime import date
    y1, m1, d1 = map(int, a.split("-"))
    y2, m2, d2 = map(int, b.split("-"))
    return (date(y2, m2, d2) - date(y1, m1, d1)).days


# ----------------------------------------------------------------------------
# Roster & caption aliases
# ----------------------------------------------------------------------------
def soundex(name: str) -> str:
    name = re.sub(r"[^a-z]", "", name.lower())
    if not name:
        return ""
    codes = {**dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"), **dict.fromkeys("dt", "3"),
             "l": "4", **dict.fromkeys("mn", "5"), "r": "6"}
    out, last = name[0].upper(), codes.get(name[0], "")
    for ch in name[1:]:
        c = codes.get(ch, "")
        if c and c != last:
            out += c
        if ch not in "hw":
            last = c
    return (out + "000")[:4]


def canonical_roster(parsed_minutes: List[Dict], since: str = "2026-01-01") -> Dict[str, Dict]:
    roster: Dict[str, Dict] = {}
    for pm in parsed_minutes:
        if pm["date"] < since:
            continue
        r = pm["parsed"]["roster"]
        for s in r["present"] + r["absent"]:
            roster.setdefault(s, {"surname": s, "title": None, "meetings": 0})
            roster[s]["meetings"] += 1
        for e in pm["parsed"]["entries"]:
            for m in re.finditer(r"\b(Mayor|Dr|Mr|Mrs|Ms) ([A-Z][a-z]+)", e["raw"]):
                if m.group(2) in roster and not roster[m.group(2)]["title"]:
                    roster[m.group(2)]["title"] = m.group(1)
    return roster


def resolve_alias(title: str, surname: str, roster: Dict[str, Dict]) -> Optional[Tuple[str, float]]:
    title = title.rstrip(".")
    if title == "Mayor":
        mayors = [k for k, v in roster.items() if v["title"] == "Mayor"]
        return (mayors[0], 1.0) if mayors else None
    best, best_score = None, 0.0
    for canon, meta in roster.items():
        if meta["title"] == "Mayor":
            continue
        if title == "Dr" and meta["title"] not in (None, "Dr"):
            continue
        if title in ("Mr", "Mrs", "Ms") and meta["title"] == "Dr":
            continue
        r = SequenceMatcher(None, surname.lower(), canon.lower()).ratio()
        if soundex(surname) == soundex(canon):
            r = max(r, 0.8)
        if surname.lower()[:1] != canon.lower()[:1] and r < 0.75:
            r *= 0.85
        if r > best_score:
            best, best_score = canon, r
    return (best, round(best_score, 2)) if best and best_score >= 0.6 else None


def alias_table(mentions: Counter, roster: Dict[str, Dict]) -> List[Dict]:
    """mentions: Counter of "Title Surname" strings from captions."""
    rows = []
    for full, n in mentions.most_common():
        parts = full.split()
        if len(parts) < 2:
            continue
        title, surname = parts[0], parts[-1]
        if title not in ("Mayor", "Dr.", "Mr.", "Mrs.", "Ms.", "Councilman", "Councilwoman", "Councilmember",
                         "President", "Dr", "Mr"):
            continue
        res = resolve_alias(title if title.startswith(("Dr", "Mr", "Mrs", "Ms", "Mayor")) else "Mr"
                            if title != "Councilwoman" else "Ms", surname, roster)
        rows.append({"caption_form": full, "mentions": n, "canonical": res[0] if res else None,
                     "confidence": res[1] if res else None})
    return rows


# ----------------------------------------------------------------------------
# Voting record (official minutes)
# ----------------------------------------------------------------------------
def voting_record(parsed_minutes: List[Dict]) -> Dict:
    members: Dict[str, Counter] = defaultdict(Counter)
    contested = []
    agree = Counter()
    pair_n = Counter()
    for pm in parsed_minutes:
        roster = pm["parsed"]["roster"]
        for s in roster["present"]:
            members[s]["meetings_present"] += 1
        for s in roster["absent"]:
            members[s]["meetings_absent"] += 1
        for e in pm["parsed"]["entries"]:
            last_outcome = None
            for ev in e["events"]:
                if ev["type"] == "motion":
                    if ev["mover"]:
                        members[ev["mover"]]["motions_made"] += 1
                    if ev["seconder"]:
                        members[ev["seconder"]]["motions_seconded"] += 1
                elif ev["type"] == "outcome":
                    last_outcome = ev
                elif ev["type"] == "vote":
                    yes, no = ev["yes"], ev["no"]
                    for s in yes:
                        members[s]["votes_cast"] += 1
                    for s in no:
                        members[s]["votes_cast"] += 1
                        members[s]["no_votes"] += 1
                    for s in ev.get("not_voting", []):
                        members[s]["not_voting"] += 1
                    if no and yes:
                        minority = no if len(no) < len(yes) else yes if len(yes) < len(no) else []
                        for s in minority:
                            members[s]["minority_votes"] += 1
                        for s in yes + no:
                            members[s]["contested_votes"] += 1
                        voters = sorted(set(yes) | set(no))
                        for a, b in itertools.combinations(voters, 2):
                            pair_n[(a, b)] += 1
                            if (a in yes) == (b in yes):
                                agree[(a, b)] += 1
                        contested.append({
                            "date": pm["date"], "kind": pm["kind"], "title": e["title"][:200],
                            "entry_kind": e["kind"], "reading": e["reading"],
                            "motion": (last_outcome or {}).get("action") or "Motion",
                            "result": (last_outcome or {}).get("result"), "tie": bool((last_outcome or {}).get("tie")),
                            "yes": yes, "no": no, "margin": abs(len(yes) - len(no)),
                        })
    table = []
    for s, c in members.items():
        cv = c["contested_votes"]
        table.append({"member": s, **dict(c),
                      "no_rate": round(c["no_votes"] / c["votes_cast"], 3) if c["votes_cast"] else None,
                      "minority_rate_contested": round(c["minority_votes"] / cv, 3) if cv else None})
    table.sort(key=lambda r: -(r.get("votes_cast") or 0))
    pairs = [{"a": a, "b": b, "contested_votes_together": n, "agreement": round(agree[(a, b)] / n, 3)}
             for (a, b), n in pair_n.items() if n >= 5]
    pairs.sort(key=lambda r: r["agreement"])
    return {"members": table, "contested": contested, "pairwise_agreement": pairs}


# ----------------------------------------------------------------------------
# R1 / R2 / R3 / R4 on the official record
# ----------------------------------------------------------------------------
def _find_on_agenda(title: str, meetings: List[Dict], date_from: str, date_to: str, min_sim=0.5):
    hits = []
    for m in meetings:
        if not (date_from <= m["date"] <= date_to):
            continue
        for it in m["items"]:
            s = title_sim(title, it["title"])
            if s >= min_sim:
                hits.append((m["date"], m["kind"], it["item_no"], round(s, 2), it["title"][:160]))
    hits.sort(key=lambda h: (h[0], -h[3]))
    return hits


def postponement_continuity(parsed_minutes: List[Dict], meetings: List[Dict]) -> List[Dict]:
    out = []
    dates = {m["date"] for m in meetings}
    last_date = max(dates)
    for pm in parsed_minutes:
        for e in pm["parsed"]["entries"]:
            if not e["postponed_to"]:
                continue
            target = e["postponed_to"]
            on_target = _find_on_agenda(e["title"], meetings, target, target)
            later = _find_on_agenda(e["title"], meetings, target, "9999") if not on_target else []
            if on_target:
                status = "honored"
            elif target not in dates:
                status = "target_meeting_not_in_record" if target > last_date else "no_meeting_on_target_date"
            elif later:
                status = "reappeared_later"
            else:
                status = "not_found_after_target"
            out.append({"check": "R1", "date": pm["date"], "title": e["title"][:200], "postponed_to": target,
                        "status": status, "found": (on_target or later)[:2],
                        "exception": status in ("no_meeting_on_target_date", "reappeared_later", "not_found_after_target"),
                        "evidence_minutes": re.sub(r"\s+", " ", e["raw"])[:600]})
    return out


def reading_sequences(parsed_minutes: List[Dict], meetings: List[Dict]) -> List[Dict]:
    """Group ordinance actions across meetings into lifecycles."""
    acts = []
    for pm in parsed_minutes:
        if pm["special"]:
            continue
        for e in pm["parsed"]["entries"]:
            if e["kind"] == "ordinance" and e["reading"]:
                acts.append({"date": pm["date"], "reading": e["reading"], "result": e["final_result"],
                             "title": e["title"], "number": e["number"], "postponed_to": e["postponed_to"],
                             "substitute": bool(re.search(r"by substitute[^.]*carried|substitute (?:dated|ordinance)[^.]*\. Motion to amend by substitute carried", e["raw"])),
                             "dissent": sorted({n for ev in e["events"] if ev["type"] == "vote" for n in ev["no"]}),
                             "public_commenters": len(e["public_commenters"])})
    acts.sort(key=lambda a: (a["date"], a["reading"]))
    groups: List[List[Dict]] = []
    for a in acts:
        best, bs = None, 0.0
        for g in groups:
            s = title_sim(a["title"], g[-1]["title"])
            if s > bs and days(g[-1]["date"], a["date"]) <= 200:
                best, bs = g, s
        if best is not None and bs >= 0.72:
            best.append(a)
        else:
            groups.append([a])
    out = []
    for g in groups:
        readings = [a["reading"] for a in g]
        flags = []
        seen = set()
        for a in g:
            if a["reading"] > 1 and (a["reading"] - 1) not in seen and g[0]["date"] > "2025-01-13":
                flags.append(f"reading {a['reading']} on {a['date']} with no recorded reading {a['reading']-1} in the record window")
            seen.add(a["reading"])
        postponements = [a for a in g if a["result"] == "postponed"]
        if len(postponements) >= 2:
            flags.append(f"postponed {len(postponements)} times")
        for a in g:
            if a["reading"] == 3 and a["substitute"]:
                flags.append(f"amended by substitute at third reading ({a['date']})")
            if a["result"] == "failed":
                flags.append(f"failed at reading {a['reading']} ({a['date']})")
        if g[-1]["result"] == "postponed" and g[-1]["postponed_to"]:
            flags.append(f"pending: postponed on {g[-1]['date']} to {g[-1]['postponed_to']}")
        span = days(g[0]["date"], g[-1]["date"])
        final = next((a for a in reversed(g) if a["reading"] == 3 and a["result"] == "carried"), None)
        out.append({"check": "R2", "title": g[0]["title"][:220], "first": g[0]["date"], "last": g[-1]["date"],
                    "span_days": span, "readings": readings, "adopted": bool(final),
                    "ordinance_number": (final or {}).get("number"), "steps": g, "flags": flags,
                    "exception": bool(flags)})
    out.sort(key=lambda r: (not r["exception"], r["first"]))
    return out


_SUBSTANTIVE = re.compile(r"^(?:ORDINANCE|RESOLUTION|Public Hearing|.*Agreement|.*Contract|Consideration of|.*Plat|"
                          r".*[Aa]ppointment|.*license|MINUTES FROM)", re.I)


def agenda_minutes_coverage(parsed_minutes: List[Dict], meetings: List[Dict]) -> List[Dict]:
    by_key = {(pm["date"], pm["kind"]): pm for pm in parsed_minutes}
    out = []
    for m in meetings:
        pm = by_key.get((m["date"], m["kind"]))
        if not pm or not pm["parsed"]["entries"] or pm.get("text_chars", 1000) < 400:
            continue  # minutes text unavailable (e.g. scanned PDF with no OCR text) - reported separately
        entries = pm["parsed"]["entries"]
        for it in m["items"]:
            t = it["title"]
            if not _SUBSTANTIVE.match(t) or t.endswith(":"):
                continue
            best = max(entries, key=lambda e: title_sim(t, e["title"]), default=None)
            s = title_sim(t, best["title"]) if best else 0.0
            if s < 0.34:
                # fall back to raw-text containment of distinctive words
                tk = title_key(t)
                best2 = max(entries, key=lambda e: len(tk & tokens(e["raw"])) / max(1, len(tk)), default=None)
                s2 = len(tk & tokens(best2["raw"])) / max(1, len(tk)) if best2 else 0
                if s2 >= 0.6:
                    continue
                out.append({"check": "R3", "date": m["date"], "kind": m["kind"], "item_no": it["item_no"],
                            "title": t[:220], "consent": it["consent"], "best_minutes_match": round(max(s, s2), 2),
                            "exception": True})
    return out


def record_integrity(parsed_minutes: List[Dict]) -> List[Dict]:
    out = []
    for pm in parsed_minutes:
        roster = pm["parsed"]["roster"]
        n = len(roster["present"])
        for e in pm["parsed"]["entries"]:
            evs = e["events"]
            if any(v["type"] == "motion" for v in evs) and not any(v["type"] == "outcome" for v in evs) \
                    and e["final_result"] not in ("died_no_second", "withdrawn"):
                out.append({"check": "R4", "type": "motion_without_recorded_outcome", "date": pm["date"],
                            "kind": pm["kind"], "title": e["title"][:200], "exception": True,
                            "evidence_minutes": re.sub(r"\s+", " ", e["raw"])[:700]})
            for v in evs:
                if v["type"] != "vote":
                    continue
                total = len(v["yes"]) + len(v["no"]) + len(v.get("not_voting", []))
                if total != n:
                    out.append({"check": "R4", "type": "vote_count_differs_from_roster", "date": pm["date"],
                                "kind": pm["kind"], "title": e["title"][:200], "recorded": total, "roster": n,
                                "yes": v["yes"], "no": v["no"], "exception": True, "evidence_minutes": v["text"][:400]})
    return out


# ----------------------------------------------------------------------------
# R5 / R6 / R7 / R8 against the transcript
# ----------------------------------------------------------------------------
def roll_call_from_transcript(segments: List[Tuple[str, str]], roster: Dict[str, Dict]) -> Dict:
    head = " ".join(t for _, t in segments[:6])
    i = head.lower().find("roll")
    window = head[max(0, i - 50): i + 900] if i >= 0 else head[:900]
    heard = {}
    for m in re.finditer(r"\b(Mayor|Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Councilman|Councilwoman)\s+([A-Z][a-z']+)[,.]?\s*(?:>>\s*)?"
                         r"(present|here|absent)?", window):
        res = resolve_alias(m.group(1).rstrip("."), m.group(2), roster)
        if res:
            heard.setdefault(res[0], m.group(3) or "named")
    absent_note = re.search(r"(\w+) members? (?:is|are) (?:absent|not present)|all members are present", window, re.I)
    return {"heard": heard, "note": absent_note.group(0) if absent_note else None, "window": window[:500]}


def attendance_check(minutes_roster: Dict, rc: Dict) -> Optional[Dict]:
    present, absent = set(minutes_roster["present"]), set(minutes_roster["absent"])
    heard = rc["heard"]
    issues = []
    for s, status in heard.items():
        if status in ("present", "here") and s in absent:
            issues.append(f"{s}: answered '{status}' in captions but recorded absent")
        if status == "absent" and s in present:
            issues.append(f"{s}: called absent in captions but recorded present")
    if rc["note"] and "all members are present" in rc["note"].lower() and absent:
        issues.append(f"captions: '{rc['note']}' but minutes record absent: {sorted(absent)}")
    m = re.match(r"(\w+) members? (?:is|are) (?:absent|not present)", rc["note"] or "", re.I)
    if m:
        words = {"one": 1, "two": 2, "three": 3}
        k = words.get(m.group(1).lower())
        if k is not None and k != len(absent) and not minutes_roster.get("partial"):
            issues.append(f"captions: '{rc['note']}' but minutes record {len(absent)} absent")
    return {"heard_in_roll_call": heard, "issues": issues, "exception": bool(issues)} if (heard or rc["note"]) else None


_CITE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2,4})")


def citation_grounding(transcript_cites: List[Tuple[str, str, str]], official_text: str) -> List[Dict]:
    """transcript_cites: [(citation 'W.S. x-y-z', role, ts)]."""
    official = set(m.group(0) for m in _CITE.finditer(re.sub(r"-\s+", "-", official_text)))
    out = []
    for cite, role, ts in transcript_cites:
        m = _CITE.search(cite)
        if not m:
            continue
        core = m.group(0)
        if core in official:
            status, match = "in_official_record", core
        else:
            match = None
            for oc in official:
                a, b = core.split("-"), oc.split("-")
                if a[:2] == b[:2] and (b[2].startswith(a[2]) or a[2].replace("0", "") == b[2].replace("0", "")
                                       or SequenceMatcher(None, a[2], b[2]).ratio() >= 0.75):
                    match = oc
                    break
            status = "caption_variant_of_official" if match else "not_in_official_record"
        out.append({"check": "R7", "citation": cite, "core": core, "role": role, "ts": ts, "status": status,
                    "official_match": match, "exception": status == "not_in_official_record"})
    return out


_EXEC = re.compile(r"16-4-405\s*\(?a\)?\s*\(?([ivx]+|\d+)\)?", re.I)
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13}


def _roman(n: int) -> str:
    return {v: k for k, v in _ROMAN.items()}.get(n, str(n))


def exec_basis(text: str) -> List[int]:
    out = []
    for m in _EXEC.finditer(re.sub(r"-\s+", "-", text)):
        v = m.group(1).lower()
        out.append(_ROMAN.get(v) or (int(v) if v.isdigit() else None))
    return sorted({x for x in out if x})


# W.S. 16-4-405(a) subsections (2025 text) and phrases that state each purpose.
EXEC_PURPOSES = {
    1: ("threat to security of property or public access", r"threat to the security|right of access"),
    2: ("personnel: appointment, employment, dismissal, complaints", r"appointment, employment|dismissal of a public officer|personnel"),
    3: ("litigation", r"litigation"),
    7: ("site selection or real-estate purchase", r"selection of a site|purchase of real estate|real estate"),
    8: ("confidential gifts", r"gifts, donations"),
    9: ("information classified as confidential by law", r"classified as confidential by law"),
    10: ("wages, salaries, benefits negotiations", r"wages|salaries|terms of employment"),
    12: ("safety and security planning", r"security planning"),
}
_SPOKEN_EXEC = re.compile(r"16-4-405\s*\(?\s*a\s*\)?\s*\(?\s*(\d{1,2})\b", re.I)


def exec_spoken(text: str) -> Dict:
    """Subsection numbers and purpose language in a spoken executive-session motion.
    Captions render the citation as '164405A7', '16-4-405 A10', '16-4-405A' and so on."""
    t = re.sub(r"\s+", " ", re.sub(r"\[[^\]]{0,40}\]|>>", " ", text))
    t = re.sub(r"\b16\s?-?\s?4\s?-?\s?405", "16-4-405", t)
    nums = sorted({int(m.group(1)) for m in _SPOKEN_EXEC.finditer(t) if 1 <= int(m.group(1)) <= 13})
    purposes = sorted(k for k, (_, pat) in EXEC_PURPOSES.items() if re.search(pat, t, re.I))
    return {"numbers": nums, "purpose_language": purposes,
            "cited_without_subsection": bool(re.search(r"16-4-405(?!\s*\(?\s*a\s*\)?\s*\(?\s*\d)", t, re.I))}
