"""
CLAIMS LEDGER
=============

Sentence-level extraction of *legal assertions* made on the record. A claim is
a sentence asserting that something is unlawful, unconstitutional, void,
pre-empted, non-compliant, or procedurally defective, or one that denies such a
thing ("this does not violate ...").

For each claim this records:

* assertion types and polarity (``assert`` vs. ``deny``)
* the authorities cited: Wyoming statutes, constitutional provisions, case law,
  municipal or UDC sections, named acts
* the speaker's role (public comment / official / agenda reading) and, for public
  comment, the self-introduced name as transcribed by the captions
* the agenda item it was made under (joined to the official outcome later, in build_analysis.py)
* a candidate official response: the first later statement by an official, within
  the same item, that addresses the claim's authority or topic or denies it

A claim is a record that someone *said* this. It is not evidence the assertion
is correct.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

ASSERTIONS: List[Tuple[str, re.Pattern]] = [
    ("violation", re.compile(r"\b(?:violat(?:es?|ed|ing|ions?)|in violation of|breach(?:es|ed)?)\b", re.I)),
    ("illegality", re.compile(r"\b(?:illegal(?:ly)?|unlawful(?:ly)?|not legal|against the law|break(?:s|ing)? the law)\b", re.I)),
    ("unconstitutional", re.compile(r"\b(?:unconstitutional|constitutional (?:rights?|violation|problem|issue|concern))\b", re.I)),
    ("void_or_ultra_vires", re.compile(
        r"\b(?:null and void|void ab\s?initio|ab\s?initio|is void|be void|ultra vires|"
        r"exceed(?:s|ed|ing)? (?:its|their|your|our|the city'?s?|council'?s?) (?:authority|jurisdiction)|"
        r"(?:has|have) no (?:legal )?authority|lacks? (?:the )?(?:legal )?authority|without (?:legal )?authority)\b", re.I)),
    ("preemption", re.compile(
        r"\b(?:pre-?empt(?:s|ed|ion)?|supersed(?:es?|ed|ing) state law|"
        r"state law (?:prohibits|forbids|does(?:n't| not) (?:allow|permit|authorize)) (?:this|the city|cities|you|municipalities|it)|"
        r"(?:conflicts?|inconsistent|at odds) with (?:state|the) (?:law|statute)|lowering the standard set by state law)\b", re.I)),
    ("procedural_defect", re.compile(
        r"\b(?:without (?:proper |adequate )?notice|not (?:properly )?noticed|(?:violat\w+|denied|deny|denies|denying|"
        r"lack of|no) due process|not on the agenda|"
        r"selective(?:ly)? enforc\w+|strip(?:ped)? my standing|denied (?:my|the|our) right|right to be heard)\b", re.I)),
    ("non_compliance", re.compile(
        r"\b(?:not in compliance|non-?complian\w+|(?:does|did|do)(?:n't| not) comply|fail(?:s|ed)? to comply|"
        r"out of compliance|(?:does|did)(?:n't| not) meet the (?:criteria|requirements?|standards?))\b", re.I)),
]
_NEG_BEFORE = re.compile(r"\b(?:not|n't|no|never|nothing|isn't|doesn't|don't|wasn't|aren't|won't|wouldn't|cannot|can't)\b"
                         r"(?:\s+\w+){0,3}\s*$", re.I)

AUTHORITY_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("wyoming_statute", re.compile(
        r"(?:\bW\.?\s?S\.?|Wyo(?:ming)?\.?\s+[Ss]tat(?:ute)?s?|statute|§)\s*(?:section\s+|sec\.\s*)?§?\s*"
        r"(\d{1,2}-\d{1,2}-\d{2,4}(?:\s?\(?[a-z0-9]{1,4}\)?)?)", re.I)),
    ("constitution", re.compile(
        r"\b(?:(?:first|second|fourth|fifth|fourteenth|1st|2nd|4th|5th|14th) amendment|"
        r"(?:wyoming|state|u\.?s\.?|federal|united states) constitution|article (?:\d+|[ivx]+|one|two|three|"
        r"thirteen|13),? section (?:\d+|one|two|four|six))\b", re.I)),
    ("case_law", re.compile(
        r"\b(?:supreme court|court of appeals|case law|precedent|Patel|Camara|Kelo|Nollan|Dolan|Sheetz|Koontz|"
        r"Grants Pass|Marbury|[A-Z][a-z]+ v\.? [A-Z][a-z]+)\b")),
    ("municipal_code", re.compile(
        r"\b(?:(?:city|municipal) code|ordinance (?:\d+(?:\.\d+)+)|chapter \d+(?:\.\d+)+|title \d+ of the (?:city|municipal) code|"
        r"section \d+\.\d+(?:\.\d+)*)\b", re.I)),
    ("udc_or_plan", re.compile(
        r"\b(?:unified development code|UDC(?: section)?(?: \d+(?:\.\d+)+)?|plan ?cheyenne|comprehensive plan|"
        r"future land use map)\b", re.I)),
    ("named_act", re.compile(
        r"\b(?:public (?:meetings|records) act|administrative procedures? act|open meetings? (?:act|law)|"
        r"americans with disabilities act|fair housing act|ADA)\b")),
]
_SENT = re.compile(r"(?<=[.?!])\s+|\s*>>\s*")
_NAME_INTRO = re.compile(r"\b(?:my name is|this is|name's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z']+){0,2})")
_RESPONSE_CUE = re.compile(r"\b(?:city attorney|attorney|legal (?:staff|counsel|department|review|opinion)|counsel|"
                           r"our legal|we(?:'ve| have) (?:reviewed|vetted)|staff (?:has )?reviewed|it is legal|it's legal|"
                           r"does(?:n't| not) violate|is(?:n't| not) (?:illegal|unconstitutional)|complies with|"
                           r"in compliance with|consistent with state law)\b", re.I)


def authorities(text: str) -> List[Dict[str, str]]:
    out, seen = [], set()
    for cls, pat in AUTHORITY_PATTERNS:
        for m in pat.finditer(text):
            val = re.sub(r"\s+", " ", m.group(1) if m.groups() and m.group(1) else m.group(0)).strip()
            if cls == "wyoming_statute":
                val = "W.S. " + re.sub(r"\s", "", val)
            key = (cls, val.lower())
            if key not in seen:
                seen.add(key)
                out.append({"class": cls, "value": val})
    return out


def sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT.split(text) if s and len(s.strip()) > 12]


def detect(sentence: str) -> Tuple[List[str], str]:
    types, neg = [], 0
    for name, pat in ASSERTIONS:
        for m in pat.finditer(sentence):
            types.append(name)
            if _NEG_BEFORE.search(sentence[max(0, m.start() - 40): m.start()]):
                neg += 1
            break
    polarity = "deny" if types and neg >= len(types) else "assert"
    return list(dict.fromkeys(types)), polarity


def extract_claims(segments: List[Tuple[str, str]], roles: List[str]) -> List[Dict]:
    """segments [(ts, text)], roles parallel. Returns claims in time order (no outcome linkage yet)."""
    claims = []
    speaker = None
    for si, ((ts, text), role) in enumerate(zip(segments, roles)):
        if role == "public_comment":
            m = _NAME_INTRO.search(text)
            if m:
                speaker = m.group(1)
        else:
            speaker = None
        sents = sentences(text)
        for k, s in enumerate(sents):
            types, pol = detect(s)
            if not types:
                continue
            ctx = " ".join(sents[max(0, k - 1): k + 2])
            auths = authorities(ctx)
            # a bare "due process" / "violation" with no authority, said by an official, is usually procedural chatter
            strength = "strong" if (auths or len(types) > 1 or types[0] in ("void_or_ultra_vires", "preemption")
                                    or re.search(r"\bunconstitutional\b", s, re.I)) else "weak"
            claims.append({
                "segment": si, "ts": ts, "role": role, "speaker_hint": speaker if role == "public_comment" else None,
                "assertion_types": types, "polarity": pol, "strength": strength,
                "authorities": auths, "sentence": s, "context": ctx,
            })
    return claims


def link_responses(claims: List[Dict], segments: List[Tuple[str, str]], roles: List[str],
                   item_bounds: Optional[List[Tuple[int, int]]] = None, window: int = 160) -> None:
    """For each public-comment claim, find the first later *official* statement
    in the same item (or within ``window`` segments) that plausibly responds.
    Sets claim['response'] = {ts, snippet, cue} or None."""
    def bounds_for(si: int) -> Tuple[int, int]:
        if item_bounds:
            for a, b in item_bounds:
                if a <= si < b:
                    return si + 1, b
        return si + 1, min(len(segments), si + window)

    for c in claims:
        c["response"] = None
        if c["role"] != "public_comment" or c["polarity"] != "assert":
            continue
        topic = {a["value"].lower() for a in c["authorities"]}
        topic_words = {w for w in re.findall(r"[a-z]{6,}", c["context"].lower())} - {
            "council", "cheyenne", "ordinance", "because", "should", "people", "violation", "violates", "about"}
        lo, hi = bounds_for(c["segment"])
        for sj in range(lo, hi):
            if roles[sj] != "official":
                continue
            t = segments[sj][1]
            tl = t.lower()
            cue = _RESPONSE_CUE.search(t)
            auth_hit = any(v in tl for v in topic if len(v) > 4)
            overlap = len(topic_words & set(re.findall(r"[a-z]{6,}", tl)))
            in_item = bool(item_bounds) and any(x <= c["segment"] < y for x, y in item_bounds)
            if (cue and (in_item or auth_hit or overlap >= 2)) or (auth_hit and overlap >= 2) or overlap >= 4:
                i = cue.start() if cue else 0
                c["response"] = {"ts": segments[sj][0], "cue": cue.group(0) if cue else "authority overlap",
                                 "snippet": re.sub(r"\s+", " ", t[max(0, i - 120): i + 220]).strip()}
                break
