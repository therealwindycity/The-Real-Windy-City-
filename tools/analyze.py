"""Thread & project reconstruction: themes, sessions, completeness, branches.

Everything here is deterministic and auditable - no model calls. Each score
carries the signals that produced it so the UI can justify every number.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- themes

THEMES = [
    {
        "id": "legal",
        "name": "Legal, Court & Housing Defense",
        "color": "#e5484d",
        "blurb": "Eviction / forcible entry & detainer, bankruptcy cure, landlord disputes, court dates, testimony, statutes and motions.",
        "keywords": {
            "court": 3, "eviction": 4, "evict": 3, "landlord": 3, "tenant": 2.5, "bankruptcy": 4,
            "chapter 13": 3, "chapter 7": 3, "trustee": 2.5, "judge": 3, "hearing": 3, "lawsuit": 4,
            "statute": 2.5, "motion": 2.5, "affidavit": 3, "subpoena": 3, "complaint": 2.5,
            "forcible entry": 4, "detainer": 4, "summons": 3, "cure": 2, "deficien": 2,
            "testimony": 3, "deposition": 3, "case number": 3, "docket": 3, "legal": 2.5,
            "attorney": 3, "counsel": 2, "settlement": 2.5, "damages": 2.5, "injunction": 3,
            "default judgment": 3, "garnishment": 3, "lien": 2, "small claims": 3, "tia": 1.2,
            "evicting": 3, "rent": 2, "lease violation": 3, "habitability": 3, "retaliatory": 3,
        },
    },
    {
        "id": "property",
        "name": "Property, Land Use & Annexation",
        "color": "#f76808",
        "blurb": "Parcels, county pockets, annexation offensives, zoning, plats, man-camp development, deeds and HOA documents.",
        "keywords": {
            "property": 2.5, "parcel": 3, "annex": 3.5, "annexation": 4, "zoning": 3.5, "plat": 3.5,
            "deed": 3, "easement": 3, "hoa": 3, "land": 2, "acre": 2.5, "lot": 1.5,
            "man camp": 4, "site plan": 3, "county pocket": 4, "comprehensive plan": 3,
            "variance": 3, "setback": 2.5, "right of way": 2.5, "survey": 2.5, "tract": 2.5,
            "table mountain": 3, "happy jack": 3, "wyfresh": 3, "development": 2,
            "modular housing": 3, "iron guard": 3, "acquire": 2, "eminent domain": 4,
        },
    },
    {
        "id": "vehicles",
        "name": "Vehicles, Towing & Traffic",
        "color": "#ffb224",
        "blurb": "Registration and title fights, bill-of-sale defense, impound and tow disputes, traffic stops, vehicle records.",
        "keywords": {
            "vehicle": 3, "tow": 3.5, "towing": 3.5, "impound": 3.5, "registration": 3, "title": 2.5,
            "vin": 3.5, "bill of sale": 4, "traffic": 2.5, "license plate": 3, "plate": 2,
            "speeding": 2.5, "ticket": 3, "citation": 3, "insurance": 2, "car": 1.8,
            "truck": 2, "motorcycle": 2, "odometer": 3, "salvage": 3, "drivers license": 3,
        },
    },
    {
        "id": "policing",
        "name": "Policing, Records & Oversight",
        "color": "#8e4ec6",
        "blurb": "Police reports, body-cam and dispatch records, scanner/RF monitoring, officer conduct, public-records demands.",
        "keywords": {
            "police": 3, "officer": 3, "sheriff": 3, "dispatch": 3, "report number": 3.5,
            "body cam": 4, "bodycam": 4, "public records": 3.5, "foia": 4, "records request": 4,
            "scanner": 3.5, "radio": 3, "frequency": 3, "channel": 2, "callsign": 3,
            "cad": 2, "incident report": 3.5, "citation log": 3, "badge": 3, "conduct": 2.5,
            "use of force": 4, "criminal": 2.5, "warrant": 3, "arrest": 3, "citation number": 3,
        },
    },
    {
        "id": "forensics",
        "name": "Forensic Audit & Evidence Timeline",
        "color": "#12a594",
        "blurb": "Dossier building, cross-platform extraction protocols, contradiction matrices, red-team verification and timeline resurrection.",
        "keywords": {
            "forensic": 4, "dossier": 3.5, "timeline": 2.5, "evidence": 3, "chain of custody": 4,
            "red team": 3.5, "veracity": 3, "cross-reference": 3, "audit": 3, "verification": 3,
            "metadata": 3, "exhibit": 3.5, "contradiction": 3.5, "anomaly": 3, "extraction": 2.5,
            "protocol": 2, "matrix": 2.5, "reconstruct": 3, "provenance": 3.5, "hash": 2.5,
            "saturation": 2, "reality resurrection": 4, "omni-prompt": 3.5,
        },
    },
    {
        "id": "meetings",
        "name": "Public Meetings, Transcripts & Testimony",
        "color": "#3e63dd",
        "blurb": "Council and committee video, verbatim transcripts, podium statements, ordinances, agenda packets and archive publishing.",
        "keywords": {
            "transcript": 3.5, "council": 3.5, "city council": 4, "meeting": 2.5, "minutes": 3,
            "agenda": 3, "ordinance": 3.5, "mayor": 3, "commission": 3, "planning commission": 4,
            "public comment": 3.5, "podium": 3.5, "work session": 3.5, "youtube": 2.5,
            "archive": 2.5, "verbatim": 3, "quorum": 3, "resolution": 2.5, "board of adjustment": 4,
            "urban renewal": 3.5, "finance committee": 3.5, "histori": 2, "preservation": 2,
            "public services committee": 3.5, "livestream": 3,
        },
    },
    {
        "id": "ai",
        "name": "AI Systems & Prompt Architecture",
        "color": "#00749e",
        "blurb": "Prompt frameworks, Gems/personas, cross-account history mining, agent handoffs and model capability mapping.",
        "keywords": {
            "prompt": 3, "gem": 2.5, "persona": 3, "system directive": 3.5, "gemini": 2,
            "chatgpt": 2.5, "notebooklm": 3.5, "context window": 3, "system state": 3,
            "ai": 1.5, "llm": 3, "model": 1.8, "agent": 3, "workspace adapter": 3.5,
            "omni": 3, "apex": 2.5, "promethean": 4, "paradox engine": 4, "cogni": 3,
            "memory": 2, "training": 2, "jailbreak": 3.5, "token": 2.5, "rag": 2.5,
            "fine-tune": 3, "capabilit": 2.5, "instruction": 2.5,
        },
    },
    {
        "id": "code",
        "name": "Code, Automation & Web Builds",
        "color": "#30a46c",
        "blurb": "Python/JS builds, scrapers, Colab notebooks, repo and pages publishing, data pipelines and APIs.",
        "keywords": {
            "python": 3.5, "script": 3, "javascript": 3.5, "html": 3, "css": 3, "json": 3,
            "api": 3, "github": 3.5, "repo": 3, "colab": 3.5, "notebook": 2.5, "streamlit": 3.5,
            "sqlite": 3.5, "sql": 2.5, "function": 2.5, "regex": 3, "scrape": 3.5, "cron": 3,
            "deploy": 3, "server": 2.5, "terminal": 2.5, "debug": 3, "error": 2, "install": 2.5,
            "code": 2.5, "netlify": 3, "cloudflare": 3, "sitemap": 3, "seo": 3, "index.html": 3,
        },
    },
    {
        "id": "media",
        "name": "Media, Imagery & Asset Production",
        "color": "#d6409f",
        "blurb": "Image generation and editing, audio capture and transcripts, video/screen recordings, memes, thumbnails and graphics.",
        "keywords": {
            "image": 2.5, "png": 3.5, "jpg": 3, "jpeg": 2.5, "photo": 2.5, "picture": 2.5,
            "generate an image": 4, "imagen": 3.5, "meme": 3.5, "thumbnail": 3, "logo": 3,
            "audio": 3, "wav": 3.5, "mp3": 3.5, "mp4": 3, "video": 2.5, "screen recording": 3.5,
            "caption": 2.5, "graphic": 2.5, "banner": 2.5, "render": 2.5, "overlay": 2.5,
            "drone": 2.5, "camera": 2.5, "color grade": 3,
        },
    },
    {
        "id": "publishing",
        "name": "Publishing, Business & Outreach",
        "color": "#e93d82",
        "blurb": "The blotter and newsletter, press and distro lists, client and revenue ops, sponsorship asks, branding and marketing copy.",
        "keywords": {
            "blotter": 4, "newsletter": 3.5, "subscriber": 3.5, "press release": 3.5, "distro": 3.5,
            "client": 2.5, "invoice": 3, "revenue": 3, "business": 2.5, "llc": 3, "brand": 2.5,
            "marketing": 3, "monetiz": 3.5, "sponsor": 3, "advertis": 3, "audience": 3,
            "engagement": 2.5, "facebook": 2.5, "instagram": 2.5, "twitter": 2.5, "x.com": 2.5,
            "article": 2.5, "blog": 2.5, "post": 1.8, "email": 1.8, "outreach": 3, "pitch": 3,
        },
    },
    {
        "id": "personal",
        "name": "Personal, Household & Local Life",
        "color": "#978365",
        "blurb": "Family and household logistics, utilities and generators, school matters, local services, travel and everyday questions.",
        "keywords": {
            "generator": 3, "u-haul": 3, "renters insurance": 3, "utility": 3, "utility bill": 3,
            "school": 2.5, "kid": 2, "daughter": 2.5, "son": 2, "wife": 2.5, "rose": 1.5,
            "chuck": 1.5, "doctor": 2.5, "prescription": 3, "appointment": 2.5, "weather": 2.5,
            "recipe": 2.5, "grocery": 3, "move": 1.5, "travel": 2, "hotel": 2.5, "flight": 2.5,
        },
    },
]
THEME_BY_ID = {t["id"]: t for t in THEMES}
FALLBACK_THEME = {
    "id": "general",
    "name": "Research & Everyday Questions",
    "color": "#7c7c7c",
    "blurb": "General lookups: facts, comparisons, how-tos and one-off questions.",
    "keywords": {},
}

_STOP = set("""a about above after again against all am an and any are as at be because been before being below
between both but by can cannot could did do does doing down during each few for from further had has have having he
her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now
of off on once only or other ought our ours ourselves out over own same she should so some such than that the their
theirs them themselves then there these they this those through to too under until up very was we were what when
where which while who whom why with would you your yours yourself yourselves will shall may might must also get got
make made use used using like want need know think see say said tell told ask asked let us one two three new via per
etc please thanks thank hey okay ok yeah yes im ive dont doesnt didnt cant wont thats theres heres whats youre theyre
didnt wasnt isnt arent havent hasnt couldnt wouldnt shouldnt ill id youve weve theyve he's it's let's""".split())

_WORD = re.compile(r"[a-z0-9][a-z0-9'\-_]{1,}")


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 2]


def theme_scores(text: str) -> dict[str, float]:
    low = (text or "").lower()
    scores: dict[str, float] = {}
    for theme in THEMES:
        s = 0.0
        for kw, weight in theme["keywords"].items():
            if " " in kw:
                n = low.count(kw)
            else:
                n = len(re.findall(rf"\b{re.escape(kw)}\w*", low))
            if n:
                s += weight * min(n, 3)
                if n >= 3:
                    s += weight  # sustained topic bonus
        if s:
            scores[theme["id"]] = round(s, 2)
    return scores


def assign_themes(text: str) -> tuple[str, list[str], dict[str, float]]:
    scores = theme_scores(text)
    if not scores:
        return FALLBACK_THEME["id"], [], {}
    ordered = sorted(scores.items(), key=lambda kv: -kv[1])
    primary = ordered[0][0]
    top = ordered[0][1]
    secondary = [k for k, v in ordered[1:] if v >= max(2.0, top * 0.45)][:2]
    return primary, secondary, scores


# --------------------------------------------------------------------------- clustering


def parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


SALIENT_EXTRA_STOP = set("""cheyenne wyoming laramie county city state google gemini drive docs gmail chat
information file files attached attachment data give going able included page pages please need give tell
best functions projects project manage pinned gemmed everything use used want know think thing things
actually really something anything everything today tomorrow yesterday time date calendar
png jpg jpeg image images img generated generate audio wav mp3 mp4 video href comp content html https http
www com net org text copy paste link links attached-file pdf docx csv json txt md file-image image-png
prompt prompts output outputs response responses answer answers query queries question questions
nope ummm uhmmm huh hmm hmmm okay ok yeah yep nah express natural talk voice models
keep much game games play played playing watch watched watching
tell told says saying looking looks good bad nice cool weird strange funny
maybe perhaps probably around about above along already almost alone along

said says told ask asked said-message assistant user system message conversation thread turns
one two three four five six seven eight nine ten first second third next last latest newest
make made take took give gave look looks looking find found search searched result results
write wrote wrote write read reading help helped need needs want wants try tried trying
format formats version versions type types kind kinds way ways thing things stuff lot lots
better best good great nice okay right wrong true false yes yeah hey hello thanks thank
let lets gonna gotta wanna kinda sorta maybe probably definitely absolutely totally
here there where when what which who whom whose why how
someone something sometime somewhere anyone anything anyways anyway
said message sent received inbox email emails phone call calls
name names called titled title page pages section sections part parts
list lists item items number numbers count counts total totals
time times day days week weeks month months year years hour hours minute minutes
""".split())


def profile_of(texts: list[str], k: int = 40) -> dict[str, float]:
    """Salient unigrams + bigrams with capitalisation boost."""
    counts: Counter = Counter()
    for text in texts:
        ws = tokens(text)
        counts.update(ws)
        for a, b in zip(ws, ws[1:]):
            counts[f"{a} {b}"] += 1
        for cap in re.findall(r"\b[A-Z][a-z]{3,}\b", text or ""):
            cl = cap.lower()
            if cl not in _STOP and cl not in SALIENT_EXTRA_STOP:
                counts[cl] += 1.5
    cleaned = {
        w: c for w, c in counts.items()
        if not (w in SALIENT_EXTRA_STOP or all(part in SALIENT_EXTRA_STOP for part in w.split()))
    }
    total = sum(cleaned.values()) or 1
    top = sorted(cleaned.items(), key=lambda kv: -kv[1])[:k]
    return {w: c / total for w, c in top}


def similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    num = sum(min(a[k], b[k]) for k in keys)
    den = sum(a.values()) + sum(b.values())
    return (2 * num / den) if den else 0.0


# Domain vocabulary that names a thread far better than raw frequency does.
TOPIC_LABELS: list[tuple[str, str]] = [
    (r"iron guard|man camp|modular housing", "Iron Guard Man-Camp Fight"),
    (r"table mountain ranches|happy jack", "Table Mountain Ranches"),
    (r"wyfresh|distro", "WyFresh Distribution"),
    (r"forcible entry|detainer|fed hearing", "Eviction / FED Defense"),
    (r"chapter 13|chapter 7|bankruptcy", "Bankruptcy Proceedings"),
    (r"bill of sale|registration|impound|towed|tow(?:ing)? my", "Vehicle Title & Tow Fight"),
    (r"body ?cam|public records request|foia|records request", "Records Request Campaign"),
    (r"forensic|dossier|chain of custody|red team", "Forensic Dossier Build"),
    (r"paradox engine|promethean|omni-prompt|system directive|apex", "Promethean / Paradox Engine"),
    (r"notebooklm", "NotebookLM Pipeline"),
    (r"prompt (?:framework|library|pack)|jailbreak|gems?\b.*prompt", "Prompt Architecture"),
    (r"council|ordinance|public comment|podium", "Council Testimony & Ordinance"),
    (r"transcript|minutes|meeting video", "Meeting Transcript Work"),
    (r"scanner|frequency|pro-?46|radio shack", "Scanner & RF Frequencies"),
    (r"blotter|newsletter|subscriber|distro list", "The Blotter / Newsletter"),
    (r"streamlit|civic-cycle|colab|notebook", "Automation Build"),
    (r"generator|treadmill|wiring|motor", "Hardware & Wiring"),
    (r"eviction|landlord|tenant|rent", "Landlord / Tenancy Dispute"),
    (r"police|officer|sheriff|dispatch", "Police Contact Record"),
    (r"google (?:history|takeout|data)|my activity", "Google History Mining"),
    (r"image|png|generate a picture|imagen", "Image Generation"),
    (r"audio|wav|record(?:ing)?|transcribe", "Audio Capture & Transcription"),
    (r"meme|poster|flyer", "Poster / Meme Production"),
    (r"school|teacher", "School Matter"),
    (r"market(?:ing)?|client|invoice|revenue|business", "Business & Revenue Ops"),
]
_LABEL_RE = [(re.compile(p, re.I), label) for p, label in TOPIC_LABELS]

# Labels that are true but too broad to name a thread on their own.
GENERIC_LABELS = {
    "Image Generation", "Landlord / Tenancy Dispute", "Business & Revenue Ops",
    "Hardware & Wiring", "Audio Capture & Transcription", "Meeting Transcript Work",
}

BOILERPLATE_RE = re.compile(
    r"Attached \d+ files?\.|\[(?:Audio included|image[^\]]*)\.?\]\([^)]*\)"
    r"|!\[[^\]]*\]|\[[^\]]*\.(?:png|jpe?g|wav|mp3|mp4|pdf|html?|csv|json|txt|srt|vtt)\]\([^)]*\)",
    re.I)


def name_project(turns: list[dict]) -> str:
    # Name from the anchor of the thread (first turns) plus where it ended up,
    # not the whole drift, and weight multi-word patterns as more specific.
    anchor = turns[:8] + turns[-4:]
    joined = "\n".join((t.get("prompt") or "") for t in anchor)[:12000]
    if not joined.strip():
        joined = "\n".join((t.get("output") or "")[:600] for t in anchor)[:12000]
    # Attachment boilerplate must not drive naming.
    joined = BOILERPLATE_RE.sub(" ", joined)
    # 1. A recognised subject beats statistics.
    counts: Counter = Counter()
    for rx, label in _LABEL_RE:
        n = len(rx.findall(joined))
        if n:
            specificity = 2.0 if " " in rx.pattern or "|" in rx.pattern else 1.0
            if label in GENERIC_LABELS:
                specificity *= 0.35
            counts[label] += n * specificity
    if counts:
        label, weight = counts.most_common(1)[0]
        if label not in GENERIC_LABELS or weight >= 4.0:
            return label
    # 2. Proper nouns are almost always the subject in personal archives.
    proper: Counter = Counter()
    for t in anchor:
        text = BOILERPLATE_RE.sub(" ", t.get("prompt") or "")
        for sent in re.split(r"[.!?\n]", text):
            words = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", sent)
            # skip a leading capitalised word (sentence start)
            if words and sent.strip().startswith(words[0]):
                words = words[1:]
            for w in words:
                if w.lower() not in _STOP and w.lower() not in SALIENT_EXTRA_STOP:
                    proper[w] += 1
    strong = [(w, c) for w, c in proper.most_common(6) if c >= 2]
    if len(strong) >= 2:
        return " / ".join(w for w, _ in strong[:2])
    if len(strong) == 1:
        return strong[0][0]

    # 3. Fall back to salient vocabulary.
    prof = profile_of([t.get("prompt", "") for t in turns], k=12) or \
        profile_of([t.get("output", "")[:800] for t in turns], k=12)
    if not prof:
        return "Untitled thread"
    bigrams = [(w, s) for w, s in prof.items() if " " in w and len(w) < 40]
    if bigrams and bigrams[0][1] >= 0.02:
        return bigrams[0][0].title()
    words = [w for w, _ in sorted(prof.items(), key=lambda kv: -kv[1])[:2]]
    return " / ".join(w.title() for w in words)


def build_threads(turns: list[dict], *, session_gap_minutes: int = 90,
                  merge_threshold: float = 0.10, merge_max_days: int = 21) -> list[dict]:
    """Group turns into sessions, then sessions into projects."""
    ordered = sorted([t for t in turns if t.get("ts")], key=lambda t: t["ts"])
    undated = [t for t in turns if not t.get("ts")]

    sessions: list[list[dict]] = []
    for t in ordered:
        if sessions:
            prev = sessions[-1][-1]
            gap = (parse_iso(t["ts"]) - parse_iso(prev["ts"])).total_seconds() / 60
            if gap <= session_gap_minutes:
                sessions[-1].append(t)
                continue
        sessions.append([t])

    projects: list[dict] = []
    for sess in sessions:
        texts = [s.get("prompt") or s.get("output", "")[:400] for s in sess]
        prof = profile_of(texts, k=50)
        best, best_sim = None, 0.0
        for p in reversed(projects[-12:]):
            gap_days = (parse_iso(sess[0]["ts"]) - parse_iso(p["turns"][-1]["ts"])).days
            if gap_days > merge_max_days:
                continue
            sim = similarity(prof, p["profile"])
            if sim > best_sim:
                best, best_sim = p, sim
        if best is not None and best_sim >= merge_threshold:
            best["turns"].extend(sess)
            best["profile"] = profile_of(
                [t.get("prompt") or t.get("output", "")[:400] for t in best["turns"]], k=50)
        else:
            projects.append({"turns": list(sess), "profile": prof})

    for p in projects:
        if undated and len(projects) == 1:
            p["turns"].extend(undated)
        p["name"] = name_project(p["turns"])
        p["start"] = p["turns"][0].get("ts")
        p["end"] = p["turns"][-1].get("ts")
        p["duration_hours"] = round(
            (parse_iso(p["end"]) - parse_iso(p["start"])).total_seconds() / 3600, 2
        ) if p["start"] and p["end"] else 0.0
    projects.sort(key=lambda p: p["start"] or "")
    return projects


# --------------------------------------------------------------------------- completeness

DELIVERABLE_MARKERS = [
    (r"\|\s*-{3,}", 10, "delivered a table"),
    (r"```", 8, "delivered code"),
    (r"\b(?:here(?:'s| is) (?:the|a) (?:complete|full|final|finished|step-by-step))", 12, "declared complete deliverable"),
    (r"\bstep 1\b.*\bstep \d\b", 8, "delivered numbered procedure"),
    (r"^\s*\d+\.\s", 5, "delivered an ordered list"),
    (r"\b(?:final|finished|ready to (?:file|send|submit))\b", 8, "final-form language"),
    (r"\b(?:draft|template|checklist|playbook|script)\b", 6, "produced a reusable artifact"),
    (r"\.(?:md|pdf|docx|html|py|json|csv)\b", 6, "references a produced file"),
    (r"\b(?:cite|citation|source:|per the record|statute §|wy\.? stat)", 5, "grounded in sources"),
]
RICHNESS_MARKERS = [
    (r"^#{1,4}\s", 4, "structured answer with headings"),
    (r"(?:^|\n)\s*[-*•]\s", 3, "structured answer with bullets"),
    (r"\bhttps?://", 3, "answer carried links to sources"),
    (r"\b\d{2,}(?:\.\d+)?\s*(?:%|million|usd|\$|acres|units|feet|sq)", 3, "answer carried hard figures"),
    (r"\b(?:Wyo\.?\s*Stat|W\.S\.|§|CFR|U\.?S\.?C\.?)\b", 4, "cited statute or code"),
    (r"\b(?:because|therefore|which means|the reason)\b", 2, "answer explained reasoning"),
    (r"\bI (?:searched|looked up|checked|reviewed|analyzed)\b", 3, "answer reported source work"),
]
OPEN_MARKERS = [
    (r"\bwould you like me to\b", -12, "assistant asked whether to continue"),
    (r"\b(?:do you want me to|shall i|should i)\b", -12, "assistant asked whether to continue"),
    (r"\blet me know (?:if|what|which)\b", -8, "assistant waiting on your input"),
    (r"\bwhich (?:would you|do you) prefer\b", -8, "assistant offered a choice"),
    (r"\b(?:option a|option b|option 1)\b", -6, "assistant presented options"),
    (r"\bnext steps?:\s*$", -4, "declared next steps pending"),
    (r"\b(?:to be continued|part 1 of|continued in)\b", -14, "explicitly part of a longer series"),
]
FAILURE_MARKERS = [
    (r"\bi (?:can(?:no|')t|am unable|'m unable|am not able)", -18, "model declined or was unable"),
    (r"\bi don'?t have (?:enough|access|the ability)", -16, "model lacked information or access"),
    (r"as an ai\b", -10, "boilerplate capability disclaimer"),
    (r"\b(?:error|failed|timed out|blocked)\b", -6, "error surfaced in response"),
    (r"\bi (?:may have|might have) (?:missed|misunderstood)", -6, "assistant flagged its own gap"),
]
COMPLETE_WORDS = ["perfect", "thank you", "thanks", "great", "exactly", "that works", "awesome",
                  "got it", "yes that's", "nailed", "beautiful", "correct"]
REJECT_STARTS = ["no,", "no ", "nope", "that's not", "thats not", "wrong", "try again", "i meant",
                 "not what i", "you're wrong", "youre wrong", "stop", "again"]


def score_turn(turn: dict, nxt: dict | None) -> tuple[float, list[dict]]:
    """Auditable per-turn progress score (0-100).

    Baseline is "a question was asked and answered" (45). Positive evidence of
    a delivered artifact pushes toward complete; open loops, refusals and thin
    answers pull back. Both are listed in `reasons` so the UI can show its work.
    """
    out = turn.get("output") or ""
    reasons: list[dict] = []
    score = 45.0
    low = out.lower()
    if len(out) > 8000:
        score += 12
        reasons.append({"signal": "very long, developed answer (>8k chars)", "delta": 12})
    elif len(out) > 3000:
        score += 8
        reasons.append({"signal": "developed answer (>3k chars)", "delta": 8})
    elif len(out) > 800:
        score += 3
    elif len(out) < 200:
        score -= 18
        reasons.append({"signal": "thin answer (<200 chars)", "delta": -18})
    elif len(out) < 400:
        score -= 8
        reasons.append({"signal": "brief answer (<400 chars)", "delta": -8})

    # Structural richness: adapters that make answers vary, so the score carries
    # more information than a flat baseline.
    for pat, delta, label in RICHNESS_MARKERS:
        if re.search(pat, out, re.I | re.M):
            score += delta
            reasons.append({"signal": label, "delta": delta})

    positives = 0.0
    negatives = 0.0
    for pat, delta, label in DELIVERABLE_MARKERS:
        if re.search(pat, out, re.I | re.M):
            score += delta
            positives += delta
            reasons.append({"signal": label, "delta": delta})
    for pat, delta, label in OPEN_MARKERS:
        if re.search(pat, low, re.I | re.M):
            score += delta
            negatives += abs(delta)
            reasons.append({"signal": label, "delta": delta})
    for pat, delta, label in FAILURE_MARKERS:
        if re.search(pat, low, re.I | re.M):
            score += delta
            negatives += abs(delta)
            reasons.append({"signal": label, "delta": delta})
    if nxt is not None:
        np = (nxt.get("prompt") or "").lower().strip()
        if any(np.startswith(w) or np.startswith(w + ",") for w in COMPLETE_WORDS) or np in COMPLETE_WORDS:
            score += 16
            positives += 16
            reasons.append({"signal": "you confirmed the result before moving on", "delta": 16})
        if any(np.startswith(w) for w in REJECT_STARTS):
            score -= 14
            reasons.append({"signal": "you rejected or re-aimed the answer next turn", "delta": -14})
    else:
        # Terminal turn of a thread: this is where the work actually stopped.
        if re.search(r"\?", out[-400:]) or re.search(
                r"would you like me to|let me know if", out[-600:], re.I):
            score -= 10
            reasons.append({"signal": "thread ends awaiting your direction", "delta": -10})
        if positives >= 10:
            score += 8
            reasons.append({"signal": "thread ends on a delivered artifact", "delta": 8})
    # Cap the stacking of negatives so one long chatty answer cannot zero a turn.
    if negatives > 32:
        score += min(18.0, negatives - 32)
    return max(0.0, min(100.0, score)), reasons


def project_completeness(turns: list[dict]) -> dict:
    scored = [score_turn(t, turns[i + 1] if i + 1 < len(turns) else None)
              for i, t in enumerate(turns)]
    if not scored:
        return {"percent": 0, "label": "Seed", "reasons": [], "terminal": None}
    # Later turns carry more weight: the state of play is what matters.
    weights = [1.0 + 0.6 * (i / max(1, len(scored) - 1)) for i in range(len(scored))]
    total_w = sum(weights)
    percent = sum(s * w for (s, _), w in zip(scored, weights)) / total_w
    last_score, last_reasons = scored[-1]
    # Terminal state matters most for resumption, but the body of the work counts.
    percent = 0.68 * percent + 0.32 * last_score
    # Effort bonus: a long, sustained thread that produced a lot is rarely a seed,
    # even if it never loudly declared itself finished.
    chars = sum(len(t.get("output") or "") for t in turns)
    if chars > 400_000:
        percent += 10
    elif chars > 120_000:
        percent += 7
    elif chars > 40_000:
        percent += 4
    all_reasons: list[dict] = []
    seen = set()
    for _, rs in scored:
        for r in rs:
            key = r["signal"]
            if key in seen:
                continue
            seen.add(key)
            all_reasons.append(r)
    for r in last_reasons:
        r = dict(r)
        r["terminal"] = True
        all_reasons.insert(0, r)
    percent = round(max(0.0, min(100.0, percent)))
    label = ("Complete" if percent >= 91 else "Near-complete" if percent >= 76 else
             "Substantial" if percent >= 56 else "Partial" if percent >= 36 else
             "Exploring" if percent >= 16 else "Seed")
    return {"percent": percent, "label": label, "reasons": all_reasons[:8],
            "terminal": {"score": round(last_score), "reasons": last_reasons}}


# --------------------------------------------------------------------------- branches

CHOICE_RE = re.compile(
    r"(?:^|\n)\s*(?:option\s*([A-D1-4])|(?:([1-9])\)|([1-9])\.)\s)(.{0,120})", re.I)


def extract_choices(turn: dict) -> list[dict]:
    """Options the assistant offered that you could pick up now."""
    out = turn.get("output") or ""
    choices = []
    for m in CHOICE_RE.finditer(out):
        label = (m.group(3) or m.group(4) or "").strip()
        if len(label) < 8:
            continue
        label = re.sub(r"\s+", " ", re.sub(r"[*_`#]", "", label))[:110]
        choices.append({"label": label, "kind": "offered"})
    # "would you like me to X, or Y?" phrasing
    m = re.search(r"would you like me to (?:([^?.,;]{6,90}))([^?]{0,120})\?", out, re.I)
    if m:
        head = re.sub(r"\s+", " ", m.group(1)).strip()
        if head:
            choices.append({"label": f"Have the assistant {head}", "kind": "offered"})
    seen, uniq = set(), []
    for c in choices:
        k = c["label"].lower()[:60]
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq[:4]


OPEN_THREAD_RE = re.compile(
    r"^(?:todo|next|remaining|still need|to do|open item|pending)\b[:\- ]*(.{6,160})", re.I | re.M)


def open_threads(turns: list[dict]) -> list[str]:
    """Unfinished asks: what a resuming agent should pick up first."""
    items: list[str] = []
    for t in turns[-14:]:
        for m in OPEN_THREAD_RE.finditer(t.get("prompt") or ""):
            items.append(re.sub(r"\s+", " ", m.group(1)).strip())
        for m in OPEN_THREAD_RE.finditer(t.get("output") or ""):
            items.append(re.sub(r"\s+", " ", m.group(1)).strip())
    last_prompt = (turns[-1].get("prompt") or "").strip() if turns else ""
    for sentence in re.split(r"(?<=[?])\s+", last_prompt):
        if sentence.strip().endswith("?") and len(sentence) > 15:
            items.append(re.sub(r"\s+", " ", sentence).strip())
    last_out = (turns[-1].get("output") or "") if turns else ""
    if re.search(r"\bwould you like me to\b|\bwhich (?:would you|do you) prefer\b", last_out, re.I):
        items.append("Assistant ended by asking which direction to take — answer it to continue.")
    seen, out = set(), []
    for i in items:
        k = i.lower()[:60]
        if k not in seen and len(i) > 8:
            seen.add(k)
            out.append(i)
    return out[:6]


ARTIFACT_RE = re.compile(
    r"\(([^()\n]{2,90}\.(?:pdf|png|jpe?g|wav|mp3|mp4|docx?|xlsx?|csv|json|html?|md|txt|srt|vtt|zip))\)")


def artifacts_of(turn: dict) -> list[dict]:
    found: list[dict] = []
    for att in turn.get("attachments") or []:
        found.append({"name": att.get("name") or "attachment", "href": att.get("href"),
                      "kind": "attachment"})
    for m in ARTIFACT_RE.finditer((turn.get("prompt") or "") + "\n" + (turn.get("output") or "")):
        name = m.group(1)
        found.append({"name": name.split("/")[-1], "href": None, "kind": "file"})
    seen, out = set(), []
    for a in found:
        k = (a["href"] or a["name"]).lower()
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out[:12]
