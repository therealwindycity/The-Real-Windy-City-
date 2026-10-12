"""
AGENDA ALIGNMENT & ROLE ATTRIBUTION
===================================

Aligns a caption transcript to the city's published agenda, then labels each
transcript segment with a discourse role.

Alignment
---------
The clerk reads every item aloud ("Number six, ordinance third reading creating
chapter 1.28 ..."). Every "number N" / "item N" in the captions becomes a
candidate anchor, scored on:

* whether the spoken number matches the agenda item number (1, 8a, 22A; digits or words)
* overlap between the item title's distinctive words and the 300 characters after the anchor

A dynamic program then picks the highest-scoring set of anchors that keeps agenda
order and stays monotonic in time. Items not read separately, like most consent
items, are skipped. An item runs from its anchor to the next aligned anchor.

Roles
-----
``agenda_reading``  the clerk/chair reading an item title (anchor segment)
``public_comment``  from a speaker-introduction cue ("my name is", "unmute yourself",
                    "introduce yourself", "I live at") until a chair hand-back cue
                    ("seeing none", "all those in favor", "bring it back to council", ...)
``official``        everything else: chair, members, staff, attorney

These are cue-based heuristics and deterministic. Validation against the
minutes' public-commenter lists is reported in the analysis (see reconcile.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_NUM_WORDS.update({"thirty": 30, "forty": 40})
_ANCHOR = re.compile(
    r"\b(?:number|item(?: number)?|no\.)\s+"
    r"((?:\d{1,2})(?:\s?[a-hA-H]\b)?|(?:(?:twenty|thirty|forty)[- ])?"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty)(?:[- ]?[a-hA-H]\b)?)",
    re.IGNORECASE)
# Caption homophones for spoken item numbers ("number eight" is often captioned "number A").
_ANCHOR_HOMOPHONE = re.compile(r"\bnext item is (?:number |item )?(a|ate|won|to|too|for)\b[ ,.]", re.IGNORECASE)
_HOMOPHONES = {"a": "8", "ate": "8", "won": "1", "to": "2", "too": "2", "for": "4"}
_STOP = set("""
the and for with that this from into upon city cheyenne wyoming ordinance resolution reading first second third
amending amend official located generally land lands various tracts tract certain authorizing approving between
agreement mayor clerk sign which their there have been will shall being under over said such other than more
public hearing hearings section sections chapter code municipal fund funds general project item number page
""".split())
PUBLIC_START = re.compile(
    r"\b(?:my name is|name is [A-Z]|introduce yourself|state your name|your name and address|unmute yourself|"
    r"i live (?:at|on|in)|i reside|i'?m a (?:resident|homeowner|property owner)|i've lived|"
    r"(?:welcome|go ahead),? (?:mr|ms|mrs|miss|dr)\b|come (?:on )?up to the (?:podium|microphone)|"
    r"(?:raise|raised) (?:their|your) hands?|"
    r"(?:anybody|anyone|somebody|someone) (?:else )?(?:in the (?:audience|room|public)|online|on zoom|from the (?:public|audience))|"
    r"(?:go|come) (?:out )?to the (?:audience|public)|(?:mr|ms|mrs|miss)\.? [A-Z][a-z]+,? you can go ahead|"
    r"for the (?:permanent )?(?:administrative |public )?record[.,]|members of the (?:city )?council,)", re.IGNORECASE)
PUBLIC_END = re.compile(
    r"\b(?:seeing none|hearing none|anyone else (?:online|in the (?:room|audience))\?? (?:seeing|hearing) none|"
    r"close (?:the )?public (?:comment|hearing)|bring it back to (?:the )?(?:council|governing body|committee)|"
    r"back to (?:the )?(?:council|governing body|committee) for (?:discussion|a vote)|"
    r"(?:all|those) in favor|roll call|discussion (?:from|by) (?:the )?(?:council|governing body|committee)|"
    r"questions? (?:from|by) (?:the )?(?:council|governing body|committee)|"
    r"comments? from (?:the )?(?:council|governing body|committee)|"
    r"may (?:we|i) have a motion|i (?:would |will )?(?:so )?move (?:to|that)|i would so move|"
    r"(?:ask|to) the governing body|(?:anyone|anybody) (?:else )?(?:in|on|from) the (?:governing body|council|committee)|"
    r"comments? (?:from|on|by) (?:the )?governing body)", re.IGNORECASE)


def tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9.\-]{2,}", s.lower()) if w not in _STOP and len(w) >= 4}


def norm_item_no(s: str) -> Optional[str]:
    s = s.strip().lower().replace("-", " ")
    m = re.fullmatch(r"(\d{1,2})\s?([a-h])?", s)
    if m:
        return m.group(1) + (m.group(2) or "")
    parts = s.split()
    total, suffix = 0, ""
    for p in parts:
        if p in _NUM_WORDS:
            total += _NUM_WORDS[p]
        elif re.fullmatch(r"[a-h]", p):
            suffix = p
        else:
            m2 = re.fullmatch(r"([a-z]+?)([a-h])", p)
            if m2 and m2.group(1) in _NUM_WORDS:
                total += _NUM_WORDS[m2.group(1)]
                suffix = m2.group(2)
            else:
                return None
    return f"{total}{suffix}" if total else None


def hms(ts: str) -> int:
    h, m, s = (int(x) for x in ts.split(":"))
    return h * 3600 + m * 60 + s


def fmt(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


_HEADER = re.compile(r"^(?:CALL (?:MEETING TO ORDER|ROLL)|PLEDGE|CONSENT AGENDA|PUBLIC HEARINGS:|PRELIMINARY PLATS:|"
                     r"LEASES/CONTRACTS|CONSIDERATION OF BIDS|ANNOUNCEMENTS|OTHER BUSINESS|ADJOURN|"
                     r"[A-Z /&]+:$)")


def alignable(item: Dict) -> bool:
    return bool(item.get("title")) and not _HEADER.match(item["title"].strip())


@dataclass
class AlignedItem:
    item_no: str
    title: str
    consent: bool
    start: str
    end: Optional[str]
    seconds: Optional[int]
    score: float
    number_matched: bool
    anchor_text: str


def align(segments: List[Tuple[str, str]], items: List[Dict]) -> List[AlignedItem]:
    """segments: [(HH:MM:SS, text)] in time order. items: official agenda items in order."""
    cands: List[List[Tuple[int, float, bool, str]]] = []
    use = [it for it in items if alignable(it)]
    item_tok = [tokens(it["title"])[:0] if False else tokens(it["title"]) for it in use]
    anchors = []
    for si, (ts, text) in enumerate(segments):
        for m in _ANCHOR.finditer(text):
            n = norm_item_no(m.group(1))
            follow = text[m.end(): m.end() + 300]
            if si + 1 < len(segments) and len(follow) < 200:
                follow += " " + segments[si + 1][1][:300 - len(follow)]
            anchors.append((si, n, tokens(follow), text[max(0, m.start() - 20): m.end() + 140]))
        for m in _ANCHOR_HOMOPHONE.finditer(text):
            follow = text[m.end(): m.end() + 300]
            anchors.append((si, _HOMOPHONES[m.group(1).lower()], tokens(follow), text[max(0, m.start() - 20): m.end() + 140]))
    anchors.sort(key=lambda a: a[0])
    for ii, it in enumerate(use):
        want = norm_item_no(it["item_no"] or "")
        tt = item_tok[ii]
        row = []
        for ai, (si, n, ft, snippet) in enumerate(anchors):
            num = bool(want and n == want)
            ov = len(tt & ft) / max(1, min(len(tt), 8))
            score = (2.5 if num else 0.0) + 4.0 * ov
            if (num and ov >= 0.12) or ov >= 0.45 or (num and len(tt) == 0):
                row.append((ai, score, num, snippet))
        cands.append(row)
    # weighted longest increasing path over (item order, anchor order)
    best: Dict[Tuple[int, int], Tuple[float, Optional[Tuple[int, int]]]] = {}
    flat = [(ii, ai, sc) for ii, row in enumerate(cands) for (ai, sc, _, _) in row]
    flat.sort()
    for ii, ai, sc in flat:
        prev_best, prev_key = 0.0, None
        for (pi, pa), (val, _) in best.items():
            if pi < ii and pa < ai and val > prev_best:
                prev_best, prev_key = val, (pi, pa)
        best[(ii, ai)] = (prev_best + sc, prev_key)
    if not best:
        return []
    key = max(best, key=lambda k: (best[k][0], -k[0]))
    chosen = []
    while key:
        chosen.append(key)
        key = best[key][1]
    chosen.reverse()
    out: List[AlignedItem] = []
    for idx, (ii, ai) in enumerate(chosen):
        it = use[ii]
        si = anchors[ai][0]
        start = segments[si][0]
        nxt = segments[anchors[chosen[idx + 1][1]][0]][0] if idx + 1 < len(chosen) else None
        meta = next(c for c in cands[ii] if c[0] == ai)
        out.append(AlignedItem(item_no=it["item_no"], title=it["title"], consent=bool(it.get("consent")),
                               start=start, end=nxt, seconds=(hms(nxt) - hms(start)) if nxt else None,
                               score=round(meta[1], 2), number_matched=meta[2], anchor_text=meta[3]))
    return out


def item_at(aligned: List[AlignedItem], ts: str) -> Optional[AlignedItem]:
    t = hms(ts)
    cur = None
    for a in aligned:
        if hms(a.start) <= t:
            cur = a
        else:
            break
    return cur


def label_roles(segments: List[Tuple[str, str]], anchor_starts: set) -> List[str]:
    """Return one role per segment: agenda_reading | public_comment | official."""
    roles, state = [], "official"
    for ts, text in segments:
        if ts in anchor_starts and (_ANCHOR.search(text[:80]) or _ANCHOR_HOMOPHONE.search(text[:80])):
            roles.append("agenda_reading")
            state = "official"
            continue
        start = PUBLIC_START.search(text)
        end = PUBLIC_END.search(text)
        if state == "official" and start:
            state = "public_comment"
        elif state == "public_comment" and end and (not start or end.start() > start.start()):
            roles.append("public_comment" if end.start() > 80 else "official")
            state = "official"
            continue
        roles.append(state)
    return roles


def count_comment_starts(segments: List[Tuple[str, str]], roles: List[str]) -> int:
    """Number of distinct public speakers detected (speaker-intro cues inside public-comment stretches)."""
    n = 0
    for (ts, text), r in zip(segments, roles):
        if r == "public_comment":
            n += len(re.findall(r"\b(?:my name is|introduce yourself|state your name|unmute yourself|you can go ahead|"
                                r"for the (?:permanent )?(?:administrative |public )?record)\b", text, re.I))
    return n
