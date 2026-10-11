"""
MINUTES PARSER
==============

Turns the official "Record of Proceedings" text (from ``official_records.json``)
into structured, deterministic records:

* meeting roster: who was present, absent, remote, or late
* one entry per agenda action: kind, reading, consent flag, title, and the
  ordinance/resolution number assigned
* an ordered list of events per entry: motions (mover, seconder, what was moved),
  outcomes (carried, failed, tie), and votes (exactly who voted yes and no)
* referrals, postponements with a target date, public commenters, and member commenters

Nothing is inferred beyond what the clerk wrote. When phrasing doesn't match a
known pattern, the raw text stays on the entry, so a reviewer can always read the
source sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
TITLE_RE = r"(?:Mayor|Dr|Mr|Mrs|Ms)"
_ABBR = re.compile(r"\b(Dr|Mr|Mrs|Ms|St|No|Ave|Blvd|Inc|Co|Corp|Jr|Sr|U\.S|W\.S|Ltd|LLC)\.(?=\s)")
_QUOTE = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"}


def _date(s: str) -> Optional[str]:
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                  r"\s+(\d{1,2}),?\s+(\d{4})", s)
    if not m:
        return None
    return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


def clean(text: str) -> str:
    for a, b in _QUOTE.items():
        text = text.replace(a, b)
    text = _ABBR.sub(r"\1", text)                       # "Dr. Rinne" -> "Dr Rinne" (keeps sentence splits sane)
    text = re.sub(r"(\d)-\s+(\d)", r"\1-\2", text)        # "15- 1-402" -> "15-1-402"
    text = re.sub(r"(\w) -(\w)", r"\1-\2", text)         # "owner -occupancy"
    text = re.sub(r"[ \t]+,", ",", text)                     # "Esquibel , Dr" -> "Esquibel, Dr"
    text = text.replace('"no."', '"no".').replace('"yes."', '"yes".')
    return text


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


_KEYWORDS = ["amended", "Motion", "motion", "seconded", "carried", "failed", "Voting", "amend", "substitute", "postpone",
             "governing", "exception", "members", "Public", "comment", "Comments", "moved", "approve", "adopt"]


def repair_names(text: str, surnames: List[str]) -> str:
    """Fix PDF-extraction splits inside known surnames and clerk vocabulary
    ("R inne" -> "Rinne", "D r" -> "Dr", "Mot ion" -> "Motion")."""
    text = re.sub(r"\bD r\b", "Dr", text)
    for s in sorted(set(surnames) | set(_KEYWORDS), key=len, reverse=True):
        if len(s) < 4:
            continue
        pat = r"\b" + r"\s?".join(re.escape(ch) for ch in s) + r"\b"
        text = re.sub(pat, s, text)
    return text


# ----------------------------------------------------------------------------
# Roster
# ----------------------------------------------------------------------------
@dataclass
class Roster:
    mayor: Optional[str] = None
    present: List[str] = field(default_factory=list)      # surnames, mayor included
    absent: List[str] = field(default_factory=list)
    remote: List[str] = field(default_factory=list)
    partial: Dict[str, str] = field(default_factory=dict)  # surname -> note ("arrived at 6:02", ...)
    clerk: Optional[str] = None


def _surname(chunk: str) -> Optional[str]:
    chunk = re.sub(r"\(.*?\)", "", chunk)
    chunk = re.sub(r"^(?:MAYOR|COUNCIL MEMBERS)\s*-\s*", "", chunk.strip())
    toks = [t for t in re.findall(r"[A-Z][A-Za-z'\-]+", chunk) if t not in ("Dr", "Mr", "Mrs", "Ms", "MAYOR")]
    return toks[-1] if toks else None


def parse_roster(text: str) -> Roster:
    flat = _flat(text)
    r = Roster()
    m = re.search(r"Present were:(.*?)(?:Also present:(.*?)(?:\.|;)|The pledge)", flat)
    if not m:
        return r
    body = m.group(1)
    notes = {}
    for nm in re.finditer(r"([A-Z][A-Za-z'\-]+)\s*\(([^)]*)\)", body):
        notes[nm.group(1)] = nm.group(2)
    body = re.sub(r"\([^)]*\)", "", body)
    if m.group(2):
        r.clerk = _flat(m.group(2).split(",")[0])
    absent_part = ""
    if "Absent:" in body:
        body, absent_part = body.split("Absent:", 1)
    mm = re.search(r"MAYOR\s*-\s*(.*?)(?:,|;|\(|COUNCIL)", body)
    parts = re.split(r",|;|\band\b|(?=COUNCIL MEMBERS)", body)
    for p in parts:
        if not p.strip():
            continue
        s = _surname(p)
        if not s or s in ("COUNCIL", "MEMBERS"):
            continue
        r.present.append(s)
        n = notes.get(s)
        if n:
            if "zoom" in n.lower():
                r.remote.append(s)
            if re.search(r"arriv|join|leav", n, re.I):
                r.partial[s] = n
    if mm:
        r.mayor = _surname(mm.group(1))
    for p in re.split(r",|\band\b", absent_part):
        s = _surname(p)
        if s:
            r.absent.append(s)
    r.present = list(dict.fromkeys(r.present))
    return r


# ----------------------------------------------------------------------------
# Entries
# ----------------------------------------------------------------------------
_KINDS = [
    ("ordinance", r"^ORDINANCE"), ("resolution", r"^RESOLUTION"),
    ("minutes", r"^Minutes from"), ("public_hearing", r"^Public Hearing|^PUBLIC HEARING"),
    ("executive_session", r"[Ee]xecutive [Ss]ession"), ("plat", r"Plat\b"),
    ("bid", r"^Consideration of (?:Bid|RFP|Request)"), ("agreement", r"Agreement|Contract|Amendment|Lease|MOU|Memorandum"),
    ("license", r"liquor|license", ), ("appointment", r"[Aa]ppointment|[Rr]eappointment"),
    ("consent_block", r"^Consent Agenda"), ("call_to_order", r"^The Governing Body of the City"),
    ("adjourn", r"adjourn"),
]
_MOVE = re.compile(rf"\b({TITLE_RE}) ([A-Z][a-z]+) moved (to .+?|that .+?)(?:, seconded by ({TITLE_RE}) ([A-Z][a-z]+))?\s*(?:\.(?=\s|$)|$)")
_OUTCOME = re.compile(r"\b((?:Main )?[Mm]otion(?: \(per Consent Agenda\))?(?:,? [a-z][A-Za-z0-9 ,]{0,100}?)?)"
                      r" (carried|failed|passed)(?: (due to a tie vote))?")
_VOTE_ALL = re.compile(r'Voting "(yes|no)" - all members of the governing body( present)?'
                       r'(?: with the exception of (.+?) (?:voting "(yes|no)"|who (?:did not vote|abstained)[^.]*))?')
_VOTE_LIST = re.compile(rf'Voting "(yes|no)"\s*-?\s*((?:(?:{TITLE_RE}) [A-Z][a-z]+(?:,? and |, | )?)+)')
_NAME = re.compile(rf"\b({TITLE_RE}) ([A-Z][a-z]+)")
_NUMBER = re.compile(r"\(#\s?(\d{4})\)")


@dataclass
class Event:
    type: str                     # motion | outcome | vote
    text: str
    mover: Optional[str] = None
    seconder: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None  # carried | failed
    tie: bool = False
    yes: List[str] = field(default_factory=list)
    no: List[str] = field(default_factory=list)
    not_voting: List[str] = field(default_factory=list)


@dataclass
class Entry:
    seq: int
    kind: str
    consent: bool
    reading: Optional[int]
    title: str
    number: Optional[str]
    final_result: Optional[str]
    postponed_to: Optional[str]
    referred_to: Optional[str]
    public_commenters: List[str]
    member_commenters: List[str]
    events: List[Event]
    raw: str


def _names(s: str) -> List[str]:
    return [m.group(2) for m in _NAME.finditer(s)]


def _people_list(s: str) -> List[str]:
    """Split "A B, C D, Director of X and E F" into people. Organisation
    fragments ("Executive Director of ...", "representing ...") stick to the previous person."""
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    parts = re.split(r",\s*|\s+and\s+", s)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and (re.match(r"(?:the |a |an )?(?:Executive|Director|President|Chair|CEO|Owner|representing|on behalf|"
                             r"of |for |with |[A-Z]{2,}\b|[A-Z][a-z]+ (?:LLC|Inc|Group|Offices?|Company|Association|"
                             r"Council|Foundation|Hart|Law))", p) or len(p.split()) > 4):
            out[-1] = out[-1] + ", " + p
            continue
        out.append(p)
    return out


def _kind(par: str) -> str:
    head = re.sub(r"^\[CA\]\s*", "", par)[:220]
    for k, pat in _KINDS:
        if re.search(pat, head):
            return k
    return "other"


def _title(par: str) -> str:
    t = re.sub(r"^\[CA\]\s*", "", par)
    stop = re.search(rf"\s(?:Reporting for|{TITLE_RE} [A-Z][a-z]+ (?:moved|advised|stated|requested|noted)|Motion|"
                     rf"Upon request|Public comment|Comments? (?:was|were) made|- referred to|Mayor Collins (?:called|announced))", t)
    return _flat(t[:stop.start()] if stop else t[:400]).rstrip(" .")


_SUBSIDIARY = r"to (?:amend|divide|suspend|recess|go into|postpone|adjourn|table|lay|reconsider|call the question|extend|limit|appeal|refer)"
_MAIN_OUTCOME = re.compile(r"(?:Main motion,?[a-z ,]{0,80}?|(?<!to )\bMotion(?: \(per Consent Agenda\))?(?: as amended[a-z ,]{0,60}?)?) "
                           r"(?:carried|failed|passed)")


def _main_pending(par: str) -> bool:
    """True when the paragraph moves a main question but records no main-motion outcome yet."""
    starts = [m.end() for m in re.finditer(r"moved to (?:approve|adopt|accept|deny|authorize|reject)", par)]
    if not starts:
        return False
    tail = par[starts[0]:]
    return not any(not re.search(_SUBSIDIARY, m.group(0)) for m in _MAIN_OUTCOME.finditer(tail))


def split_entries(text: str) -> List[str]:
    raw = text.replace("\f", "\n\n")
    chunks = [c for c in re.split(r"\n\s*\n", raw) if c.strip()]
    merged: List[str] = []
    for c in chunks:
        fc = _flat(c)
        if fc.startswith("RECORD OF PROCEEDINGS") or fc.startswith("Office of City Clerk") or re.fullmatch(r"\w+ \d{1,2}, \d{4}", fc):
            continue
        if re.fullmatch(r"(?:Page )?\d+(?: of \d+)?", fc):
            continue
        continuation = re.match(rf"(?:Motion|Main motion|Voting|{TITLE_RE}\.? [A-Z][a-z]+ (?:moved|advised|stated|requested|"
                                rf"withdrew|called|reconvened|announced|ruled|raised|noted)|Following|Public comments?|"
                                rf"Comments? (?:was|were)|The (?:item|motion) died|Upon|After|Discussion)", fc)
        if merged and not continuation and _main_pending(merged[-1]) and re.match(rf"{TITLE_RE}\.? [A-Z][a-z]+\b", fc) \
                and not re.match(rf"{TITLE_RE}\.? [A-Z][a-z]+ moved to adjourn", fc):
            continuation = True
        if merged and (continuation or (not re.search(r"[.)\]:]\s*$", merged[-1])
                                        and not fc.startswith(("[CA]", "ORDINANCE", "RESOLUTION")))):
            merged[-1] += " " + fc
        else:
            merged.append(fc)
    return merged


def parse_entry(par: str, seq: int, roster: Roster) -> Entry:
    full = par
    adj = re.search(rf"{TITLE_RE}\.? [A-Z][a-z]+ moved to adjourn", par)
    if adj and adj.start() > 0:
        par = par[:adj.start()].rstrip()   # adjournment belongs to the meeting, not to this item
    events: List[Event] = []
    spans = []
    for m in _MOVE.finditer(par):
        spans.append((m.start(), Event("motion", m.group(0), mover=m.group(2), seconder=m.group(5),
                                       action=_flat(m.group(3))[:240])))
    for m in _OUTCOME.finditer(par):
        spans.append((m.start(), Event("outcome", m.group(0), action=m.group(1), result=m.group(2).replace("passed", "carried"),
                                       tie=bool(m.group(3)))))
    present = roster.present or []
    for m in _VOTE_ALL.finditer(par):
        side, exc, exc_side = m.group(1), m.group(3), m.group(4)
        excluded = _names(exc) if exc else []
        everyone = [p for p in present if p not in excluded]
        ev = Event("vote", m.group(0))
        if side == "yes":
            ev.yes, ev.no = everyone, (excluded if exc_side == "no" else [])
        else:
            ev.no, ev.yes = everyone, (excluded if exc_side == "yes" else [])
        if exc and not exc_side:
            ev.not_voting = excluded
        spans.append((m.start(), ev))
    for m in _VOTE_LIST.finditer(par):
        names = _names(m.group(2))
        ev = Event("vote", m.group(0))
        if m.group(1) == "yes":
            ev.yes = names
        else:
            ev.no = names
        spans.append((m.start(), ev))
    spans.sort(key=lambda x: x[0])
    # merge "Voting yes - A, B. Voting no - C, D." list pairs into one vote event
    for _, ev in spans:
        if ev.type == "vote" and events and events[-1].type == "vote" and \
                ((not events[-1].no and ev.no and not ev.yes) or (not events[-1].yes and ev.yes and not ev.no)) and \
                "all members" not in ev.text and "all members" not in events[-1].text:
            events[-1].yes = events[-1].yes or ev.yes
            events[-1].no = events[-1].no or ev.no
            events[-1].text += " " + ev.text
            continue
        events.append(ev)
    # a bare "Motion carried/failed" decides the motion made just before it, unless that motion
    # died for lack of a second or was already decided, in which case it decides the main motion
    main_motion, last, last_pos = None, None, 0
    for pos, ev in spans:
        if ev.type == "motion":
            main_motion = main_motion or ev
            last, last_pos = ev, pos
        elif ev.type == "outcome" and last is not None:
            if last is not main_motion and re.search(r"died (?:due to|for) (?:a )?lack of (?:a )?second", par[last_pos:pos]):
                last = main_motion
            if re.fullmatch(r"[Mm]otion", (ev.action or "").strip()):
                verb = re.match(r"to (\w+)", last.action or "")
                if verb and re.search(_SUBSIDIARY.replace("to (?:", "(?:") + r"|strike|recommit|insert|replace|rescind",
                                      verb.group(1)):
                    ev.action = f"Motion to {verb.group(1)}"
            if last is not main_motion:
                last = main_motion

    pc = re.search(r"Public comments? (?:was|were) made by:?\s*(.+?)(?:\.\s+(?=Comments?|[A-Z][a-z]+ [A-Z]|\(#|$)|$)", par)
    mc = re.search(r"Comments? (?:was|were) made by the following members? of the governing body:?\s*(.+?)(?:\.|$)", par)
    pps = list(re.finditer(r"postpone(?:d|ment)?(?: [a-z ]+?)? (?:to|until|of) ((?:January|February|March|April|May|June|July|"
                           r"August|September|October|November|December) \d{1,2},? \d{4})", par))
    pp = pps[-1] if pps else None
    rf = re.search(r"(?:referred|refer) to (?:the )?([A-Z][A-Za-z ]+?(?:Committee|Whole|Commission|Board))", par)
    outcomes = [e for e in events if e.type == "outcome"]
    final = None
    if outcomes:
        main = [e for e in outcomes if not re.search(_SUBSIDIARY, e.action or "")]
        final = main[-1].result if main else None
        if any("postpone" in (e.action or "") and e.result == "carried" for e in outcomes) and (pp or not main):
            final = "postponed"
        elif final is None and any("refer" in (e.action or "") and e.result == "carried" for e in outcomes):
            final = "referred"
    elif re.search(r"died (?:due to|for) (?:a )?lack of a second", par):
        final = "died_no_second"
    elif re.search(r"withdr[ae]w", par):
        final = "withdrawn"
    elif rf:
        final = "referred"
    reading = re.search(r"(1st|2nd|3rd|first|second|third) READING", par[:120], re.I)
    rmap = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3}
    num = _NUMBER.search(par)
    if num and final is None:
        final = "carried"   # the clerk assigns an ordinance/resolution number only on adoption
    return Entry(
        seq=seq, kind=_kind(par), consent=par.startswith("[CA]") or "per Consent Agenda" in par,
        reading=rmap[reading.group(1).lower()] if reading else None,
        title=_title(par), number=num.group(1) if num else None,
        final_result=final, postponed_to=_date(pp.group(1)) if pp and final == "postponed" else None,
        referred_to=_flat(rf.group(1)) if rf else None,
        public_commenters=_people_list(pc.group(1)) if pc else [],
        member_commenters=_names(mc.group(1)) if mc else [],
        events=events, raw=full,
    )


def parse_minutes(text: str, known_surnames: Optional[List[str]] = None) -> Dict:
    text = clean(text)
    roster = parse_roster(text)
    surnames = sorted(set((known_surnames or []) + roster.present + roster.absent))
    text = clean(repair_names(text, surnames))
    roster = parse_roster(text)
    entries = [parse_entry(p, i, roster) for i, p in enumerate(split_entries(text))]
    entries = [e for e in entries if e.kind not in ("call_to_order",) or e.events]
    return {"roster": asdict(roster), "entries": [asdict(e) for e in entries]}
