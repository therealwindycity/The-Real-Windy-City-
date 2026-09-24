"""Analysis layer.

1. Watchlist scanner — regex terms -> events with verbatim quotes.
2. Trend detection — least-squares slope over monthly series (permits, incidents).
3. Sentiment — small, transparent lexicon scorer over news mentioning a topic.
4. Optional LLM red-flag pass — any OpenAI-compatible endpoint. Every quote the
   model returns is VERIFIED to appear verbatim in the source; unverifiable
   claims are dropped. The model can widen what we look for, never what we assert.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from .util import short_id

SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


# ------------------------------------------------------------------ watchlist
def compile_watchlist(watchlist: dict, jurisdiction: str) -> list[tuple[re.Pattern, dict]]:
    out = []
    for t in watchlist.get("terms", []):
        if t.get("jurisdictions") and jurisdiction not in t["jurisdictions"]:
            continue
        try:
            out.append((re.compile(t["term"], re.I), t))
        except re.error:
            continue
    return out


def _sentence_around(text: str, start: int, end: int, width: int = 220) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
    left = left + 1 if left >= 0 and start - left < width else max(0, start - width // 2)
    candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    right = min(candidates) + 1 if candidates and min(candidates) - end < width else min(len(text), end + width // 2)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def scan_watchlist(text: str, compiled) -> list[dict]:
    """Return one hit per term: {label, severity, quote, count}."""
    hits = []
    for rx, t in compiled:
        matches = list(rx.finditer(text or ""))
        if matches:
            m = matches[0]
            hits.append({"label": t.get("label", t["term"]), "severity": t.get("severity", "medium"),
                         "quote": _sentence_around(text, m.start(), m.end()), "count": len(matches)})
    return hits


def watchlist_event(*, jurisdiction, url, title, text, content_hash, fetched_at, method,
                    compiled, lat=None, lon=None) -> dict | None:
    hits = scan_watchlist(text, compiled)
    if not hits:
        return None
    top = max(hits, key=lambda h: (SEV_RANK[h["severity"]], h["count"]))
    labels = [h["label"] for h in hits]
    return {
        "id": short_id("watchlist", url, content_hash),
        "jurisdiction": jurisdiction,
        "kind": "watchlist_hit",
        "severity": top["severity"],
        "title": f"{', '.join(labels[:3])}{' +' + str(len(labels) - 3) if len(labels) > 3 else ''} — {title or url}"[:300],
        "quote": top["quote"][:600],
        "source_url": url,
        "method": method,
        "fetched_at": fetched_at,
        "watchlist_hits": labels,
        "hash": content_hash,
        "lat": lat, "lon": lon,
        "data": {"hits": hits},
    }


# ------------------------------------------------------------------ trends
def slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xbar, ybar = (n - 1) / 2, sum(values) / n
    den = sum((i - xbar) ** 2 for i in range(n))
    return sum((i - xbar) * (v - ybar) for i, v in enumerate(values)) / den if den else 0.0


def trend_flags(series_rows: list[dict], min_slope: float, min_points: int = 3,
                window: int = 3, drop_partial_last: bool = True, current_bucket: str | None = None):
    """series_rows: metric rows for one series. Yields (group, values, buckets, slope)."""
    by_grp: dict[str, list[dict]] = {}
    for r in series_rows:
        by_grp.setdefault(r["grp"], []).append(r)
    for grp, rows in by_grp.items():
        rows.sort(key=lambda r: r["bucket"])
        if drop_partial_last and current_bucket and rows and rows[-1]["bucket"] == current_bucket:
            rows = rows[:-1]  # the in-progress month would always look like a drop
        rows = rows[-window:]
        if len(rows) < min_points:
            continue
        vals = [r["value"] for r in rows]
        s = slope(vals)
        if s >= min_slope and vals[-1] > vals[0]:
            yield grp, vals, [r["bucket"] for r in rows], s


# ------------------------------------------------------------------ sentiment
_POS = set("""
approve approved support supports supported celebrate celebrates win wins improve improved
improvement growth thriving safe safer success successful benefit benefits welcome welcomed
invest investment praise praised fund funded open opens opened restore restored boost hope
hopeful community partnership progress transparent protect protected clean affordable
""".split())
_NEG = set("""
oppose opposed opposition protest protests protested lawsuit sue sued displacement displace
displaced eviction evictions evict crime crimes shooting shootings violence violent unsafe fear
angry anger outrage outraged corruption scandal fraud illegal violation violations deny denied
denies fail failed failure closure closed close shut delay delayed cut cuts layoffs crisis
controversy controversial concern concerns blight gentrification gentrifying rent hike hikes
secret secrecy lack lacks noise pollution contaminate contaminated
""".split())


def sentiment(text: str) -> float:
    """Polarity in [-1, 1]. Deliberately simple and auditable."""
    words = re.findall(r"[a-z']+", (text or "").lower())
    if not words:
        return 0.0
    pos = sum(w in _POS for w in words)
    neg = sum(w in _NEG for w in words)
    return 0.0 if pos + neg == 0 else (pos - neg) / (pos + neg)


def topic_mentions(text: str, topic: str) -> list[str]:
    """Sentences that mention the topic (scored individually, not the whole article)."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    rx = re.compile(re.escape(topic), re.I)
    return [s.strip() for s in sentences if rx.search(s)]


# ------------------------------------------------------------------ LLM (optional)
LLM_SYSTEM = (
    "You are a careful civic-records analyst. Identify possible accountability red flags "
    "(procurement irregularities, conflicts of interest, zoning changes benefiting specific "
    "parties, budget anomalies, closed-session overuse). You MUST quote the source verbatim for "
    "each flag. Never speculate about private individuals. Respond with JSON only: "
    '{"flags":[{"title":"...","severity":"high|medium|low","quote":"exact text from the document","why":"..."}]}'
)


def llm_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def verify_quotes(flags: list[dict], source_text: str) -> tuple[list[dict], list[dict]]:
    src = _norm(source_text)
    ok, rejected = [], []
    for f in flags:
        q = _norm(f.get("quote", ""))
        (ok if len(q) >= 12 and q in src else rejected).append(f)
    return ok, rejected


def llm_flags(text: str, watch_labels: list[str], max_chars: int = 12000) -> tuple[list[dict], str]:
    """Returns (verified_flags, method_tag). Empty list if not configured / on failure."""
    key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key or not text.strip():
        return [], ""
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user", "content": f"Watchlist context: {', '.join(watch_labels)}\n\nDOCUMENT:\n{text[:max_chars]}"},
        ],
    }
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"]
        flags = json.loads(content).get("flags", [])
    except Exception:
        return [], ""
    verified, _ = verify_quotes([f for f in flags if isinstance(f, dict)], text)
    return verified, f"llm:{model}+quote_verified"


def extractive_summary(text: str, compiled, max_sentences: int = 3) -> str:
    """Offline fallback: the sentences with the most watchlist matches, in document order."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if 30 < len(s.strip()) < 500]
    scored = [(sum(len(rx.findall(s)) for rx, _ in compiled), i, s) for i, s in enumerate(sentences)]
    top = sorted([x for x in scored if x[0] > 0], key=lambda x: (-x[0], x[1]))[:max_sentences]
    return " ".join(s for _, _, s in sorted(top, key=lambda x: x[1]))
