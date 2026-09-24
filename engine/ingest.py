"""Tiered ingestion: api > legistar/elms > rss > html > playwright > pra_only.

Every networked tier goes through net.Gate (robots.txt + rate limits + honest
UA). A refusal is never a dead end: it becomes a `blocked_source` event plus an
auto-drafted statutory bulk-access request for the same public records.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from xml.etree import ElementTree as ET

from . import db, records
from .analyze import compile_watchlist
from .extract import to_text
from .net import Blocked, FetchError, Gate
from .util import now, now_iso, parse_iso, sha256, short_id

SILENT_EDIT_METHODS = {"html", "playwright", "document"}


# ------------------------------------------------------------------ helpers
def _store(conn, *, src_key, jkey, url, title, text, content_type, method,
           published_at=None, lat=None, lon=None, analyze=True) -> bool:
    """Store a version; enqueue analysis when content changed. Returns changed."""
    h = sha256(text)
    doc_id, prev, changed = db.store_version(
        conn, source_key=src_key, jurisdiction=jkey, url=url, title=title, text=text,
        content_hash=h, content_type=content_type, method=method,
        published_at=published_at, lat=lat, lon=lon, fetched_at=now_iso())
    if changed and analyze:
        db.enqueue(conn, "analyze", {"document_id": doc_id, "source_key": src_key,
                                     "prev_version_id": prev["id"] if prev else None})
    return changed


def record_block(conn, cfg, jkey, jcfg, *, url: str, reason: str,
                 records_description: str | None = None, source_name: str = "") -> int:
    """Blocked source -> info event + deduplicated bulk-access request draft."""
    host = urllib.parse.urlsplit(url).netloc or url
    desc = records_description or (
        f"All public agendas, agenda packets, minutes, staff reports and attachments published at {host}")
    req_id, created = records.save_request(
        conn, jurisdiction=jkey, jcfg=jcfg, kind="bulk_access", records_description=desc,
        source_url=url, dedupe_key=f"bulk:{jkey}:{host}", identity=cfg.get("identity"),
        block_reason=reason)
    s = records.statute(jcfg["state"])
    db.add_event(conn, {
        "id": short_id("blocked", jkey, host),
        "jurisdiction": jkey, "kind": "blocked_source", "severity": "info",
        "title": f"Automated access refused at {host} → bulk records request #{req_id} drafted",
        "quote": f"{reason}. Routed to the statutory channel: {s['name']} ({s['cite']}).",
        "source_url": url, "method": "legal_channel", "fetched_at": now_iso(),
        "data": {"request_id": req_id, "host": host, "source": source_name, "new_request": created},
    })
    return req_id


# ------------------------------------------------------------------ tier: api (Socrata)
def crawl_socrata(conn, gate: Gate, cfg, jkey, jcfg, src, src_key) -> tuple[int, str]:
    since = (now() - dt.timedelta(days=int(src.get("lookback_days", 120)))).strftime("%Y-%m-%dT00:00:00")
    where = f"{src['date_field']} > '{since}'"
    grp = src.get("group_field")
    series = f"{src['name']}:{src.get('trend', {}).get('series', 'count_per_month')}"
    n_items, notes = 0, []

    if grp:
        params = {
            "$select": f"date_trunc_ym({src['date_field']}) AS month, {grp}, count(*) AS n",
            "$where": f"{where} AND {grp} IS NOT NULL",
            "$group": f"month, {grp}",
            "$limit": 50000,
        }
        rows = json.loads(gate.get(src["url"], params=params, accept="application/json").text())
        for r in rows:
            month = (r.get("month") or "")[:7]
            if month:
                db.put_metric(conn, jkey, series, r.get(grp), month, float(r.get("n", 0)))
        conn.commit()
        n_items += len(rows)
        notes.append(f"{len(rows)} aggregate buckets")

    text_fields = src.get("text_fields") or []
    if text_fields:
        compiled = compile_watchlist(cfg["watchlist"], jkey)
        lat_f, lon_f = src.get("lat_field"), src.get("lon_field")
        fields = [":id", src["date_field"], *text_fields, *(f for f in (grp, lat_f, lon_f) if f)]
        params = {"$select": ", ".join(dict.fromkeys(fields)), "$where": where,
                  "$order": f"{src['date_field']} DESC", "$limit": int(src.get("limit", 5000))}
        rows = json.loads(gate.get(src["url"], params=params, accept="application/json").text())
        stored = 0
        for r in rows:
            text = "\n".join(str(r.get(f, "")) for f in text_fields if r.get(f))
            if not text or not any(rx.search(text) for rx, _ in compiled):
                continue  # keep the DB lean: only rows that touch the watchlist are stored
            row_id = r.get(":id", sha256(json.dumps(r, sort_keys=True))[:12])
            url = f"{src['url']}?$where=" + urllib.parse.quote(f":id='{row_id}'")
            title = f"{src['name'].replace('_', ' ').title()}: {r.get(src.get('title_field') or text_fields[0], '')}"
            if grp and r.get(grp):
                title += f" ({src.get('group_label', grp)} {r[grp]})"
            _store(conn, src_key=src_key, jkey=jkey, url=url, title=title[:200], text=text,
                   content_type="application/json", method="official_api",
                   published_at=r.get(src["date_field"]),
                   lat=_f(r.get(lat_f)) if lat_f else None, lon=_f(r.get(lon_f)) if lon_f else None)
            stored += 1
        n_items += stored
        notes.append(f"{len(rows)} rows scanned, {stored} watchlist rows stored")
    return n_items, "; ".join(notes)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ tier: legistar (official API)
def crawl_legistar(conn, gate: Gate, cfg, jkey, jcfg, src, src_key) -> tuple[int, str]:
    since = (now() - dt.timedelta(days=int(src.get("lookback_days", 30)))).strftime("%Y-%m-%d")
    params = {"$filter": f"MatterLastModifiedUtc ge datetime'{since}'",
              "$orderby": "MatterLastModifiedUtc desc", "$top": 200}
    matters = json.loads(gate.get(src["url"], params=params, accept="application/json").text())
    client = src.get("client", "")
    n = 0
    for m in matters:
        mid = m.get("MatterId")
        url = f"https://{client}.legistar.com/LegislationDetail.aspx?ID={mid}&GUID={m.get('MatterGuid', '')}"
        title = f"{m.get('MatterFile') or ''} {m.get('MatterName') or m.get('MatterTitle') or ''}".strip()
        text = "\n".join(str(x) for x in (
            m.get("MatterTitle"), m.get("MatterName"), f"Type: {m.get('MatterTypeName')}",
            f"Status: {m.get('MatterStatusName')}", f"Body: {m.get('MatterBodyName')}",
            f"Introduced: {m.get('MatterIntroDate')}") if x)
        _store(conn, src_key=src_key, jkey=jkey, url=url, title=title[:200], text=text,
               content_type="application/json", method="legistar_api",
               published_at=m.get("MatterIntroDate"))
        n += 1
    return n, f"{n} matters modified since {since}"


# ------------------------------------------------------------------ tier: Chicago eLMS (official API)
def crawl_elms(conn, gate: Gate, cfg, jkey, jcfg, src, src_key) -> tuple[int, str]:
    """Chicago City Clerk eLMS legislation API (replaced Legistar in 2023).
    Swagger: https://api.chicityclerkelms.chicago.gov/"""
    since = (now() - dt.timedelta(days=int(src.get("lookback_days", 14)))).strftime("%Y-%m-%dT00:00:00Z")
    cap = int(src.get("limit", 1000))
    base = src["url"].rstrip("/")
    n, skip, total = 0, 0, None
    while n < cap:
        params = {"filter": f"recordCreateDate gt {since}", "sort": "introductionDate desc",
                  "top": min(500, cap - n), "skip": skip}
        payload = json.loads(gate.get(f"{base}/matter", params=params, accept="application/json").text())
        rows = payload.get("data") or []
        total = (payload.get("meta") or {}).get("count", total)
        if not rows:
            break
        for m in rows:
            url = f"https://chicityclerkelms.chicago.gov/Matter/?matterId={m.get('matterId')}"
            title = f"{m.get('recordNumber') or ''} {m.get('title') or m.get('shortTitle') or ''}".strip()
            text = "\n".join(str(x) for x in (
                m.get("title"), m.get("shortTitle"), f"Type: {m.get('type')}", f"Category: {m.get('matterCategory')}",
                f"Status: {m.get('status')} ({m.get('subStatus')})", f"Controlling body: {m.get('controllingBody')}",
                f"Sponsor: {m.get('filingSponsor')}", f"Key legislation: {m.get('keyLegislation')}",
                f"Economic disclosure: {m.get('economicDisclosure')}",
                f"Introduced: {m.get('introductionDate')}") if x)
            _store(conn, src_key=src_key, jkey=jkey, url=url, title=title[:200], text=text,
                   content_type="application/json", method="elms_api", published_at=m.get("introductionDate"))
            n += 1
        skip += len(rows)
        if total is not None and skip >= total:
            break
    return n, f"{n} matters created since {since[:10]}" + (f" (of {total})" if total else "")


# ------------------------------------------------------------------ tier: rss / atom
def _strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    items = []
    atom = "{http://www.w3.org/2005/Atom}"
    content_ns = "{http://purl.org/rss/1.0/modules/content/}encoded"
    for it in root.iter("item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "summary": _strip_tags(it.findtext(content_ns) or it.findtext("description") or ""),
            "published": (it.findtext("pubDate") or "").strip(),
        })
    for it in root.iter(f"{atom}entry"):
        link_el = it.find(f"{atom}link")
        items.append({
            "title": (it.findtext(f"{atom}title") or "").strip(),
            "link": link_el.get("href", "") if link_el is not None else "",
            "summary": _strip_tags(it.findtext(f"{atom}content") or it.findtext(f"{atom}summary") or ""),
            "published": (it.findtext(f"{atom}updated") or it.findtext(f"{atom}published") or "").strip(),
        })
    return items


def crawl_rss(conn, gate: Gate, cfg, jkey, jcfg, src, src_key) -> tuple[int, str]:
    resp = gate.get(src["url"], accept="application/rss+xml, application/atom+xml, application/xml, text/xml")
    items = parse_feed(resp.text())
    cap = int(cfg["identity"].get("max_docs_per_source_per_run", 40))
    new = 0
    for it in items[:cap]:
        if not it["link"]:
            continue
        # Headline + publisher-provided summary only; we don't scrape full articles.
        text = f"{it['title']}\n\n{it['summary']}".strip()
        if _store(conn, src_key=src_key, jkey=jkey, url=it["link"], title=it["title"][:200], text=text,
                  content_type="application/rss+xml", method="rss", published_at=it["published"]):
            new += 1
    return new, f"{len(items)} items in feed, {new} new/changed"


# ------------------------------------------------------------------ tier: html / playwright
def _render_playwright(url: str, gate: Gate) -> tuple[str, str]:
    """Render a JS-heavy public page with our honest UA. Only called after robots allows."""
    from playwright.sync_api import sync_playwright  # optional dependency
    gate._wait(url)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_context(user_agent=gate.ua).new_page()
            page.goto(url, wait_until="networkidle", timeout=int(gate.timeout * 1000))
            return page.content(), page.url
        finally:
            browser.close()


def crawl_html(conn, gate: Gate, cfg, jkey, jcfg, src, src_key, rendered: bool = False) -> tuple[int, str]:
    url = src["url"]
    if rendered:
        if not gate.allowed(url):
            raise Blocked(url, "robots.txt disallow")
        try:
            html, final_url = _render_playwright(url, gate)
        except ImportError:
            raise FetchError("playwright not installed (pip install playwright && playwright install chromium)")
        body, ctype = html.encode("utf-8"), "text/html"
    else:
        resp = gate.get(url, accept="text/html,application/xhtml+xml")
        body, ctype, final_url = resp.body, resp.content_type, resp.url

    title, text, links = to_text(body, ctype, final_url)
    method = "playwright" if rendered else "html"
    changed = _store(conn, src_key=src_key, jkey=jkey, url=url, title=title or src["name"], text=text,
                     content_type=ctype, method=method)

    patterns = [re.compile(p, re.I) for p in cfg.get("document_link_patterns", [])]
    cap = int(cfg["identity"].get("max_docs_per_source_per_run", 40))
    seen, fetched, skipped_fresh, blocked_hosts = set(), 0, 0, {}
    refetch_after = now() - dt.timedelta(hours=float(src.get("refetch_hours", 24)))
    for href, label in links:
        if href in seen or not href.startswith("http") or href == url:
            continue
        seen.add(href)
        if not any(p.search(f"{href} {label}") for p in patterns):
            continue
        if fetched >= cap:
            break
        known = db.get_document(conn, href)
        if known is not None and (parse_iso(known["last_fetched"]) or refetch_after) > refetch_after:
            skipped_fresh += 1  # checked recently; silent-edit recheck happens after refetch_hours
            continue
        try:
            r = gate.get(href)
        except Blocked as b:
            blocked_hosts.setdefault(urllib.parse.urlsplit(href).netloc, (href, b.reason))
            continue
        except FetchError:
            continue
        if len(r.body) > 25_000_000:
            continue
        dtitle, dtext, _ = to_text(r.body, r.content_type, r.url)
        if not dtext:
            continue
        _store(conn, src_key=src_key, jkey=jkey, url=href, title=(label or dtitle or href)[:200],
               text=dtext, content_type=r.content_type, method="document")
        fetched += 1
    for host, (example_url, reason) in blocked_hosts.items():
        record_block(conn, cfg, jkey, jcfg, url=example_url, reason=reason, source_name=src["name"])
    detail = f"page {'changed' if changed else 'unchanged'}; {fetched} linked documents fetched"
    if skipped_fresh:
        detail += f", {skipped_fresh} recently checked"
    if blocked_hosts:
        detail += f"; refused by robots at {', '.join(blocked_hosts)} → bulk request drafted"
    return 1 + fetched, detail


# ------------------------------------------------------------------ dispatcher
def crawl_source(conn, gate: Gate, cfg: dict, jkey: str, src: dict) -> dict:
    jcfg = cfg["jurisdictions"][jkey]
    src_key = db.upsert_source(conn, jkey, src)
    method = src["method"]
    try:
        if method == "pra_only":
            rid = record_block(conn, cfg, jkey, jcfg, url=src["url"],
                               reason=src.get("block_reason", "the hosting platform does not permit automated access"),
                               records_description=src.get("records_description"), source_name=src["name"])
            n, detail, status = 0, f"legal channel: bulk request #{rid}", "legal_channel"
        else:
            fn = {"api": crawl_socrata, "legistar": crawl_legistar, "elms": crawl_elms,
                  "rss": crawl_rss, "html": crawl_html}.get(method)
            if method == "playwright":
                n, detail = crawl_html(conn, gate, cfg, jkey, jcfg, src, src_key, rendered=True)
            elif fn is None:
                raise FetchError(f"unknown method {method!r}")
            else:
                n, detail = fn(conn, gate, cfg, jkey, jcfg, src, src_key)
            status = "ok"
    except Blocked as b:
        rid = record_block(conn, cfg, jkey, jcfg, url=b.url, reason=b.reason,
                           records_description=src.get("records_description"), source_name=src["name"])
        n, detail, status = 0, f"BLOCKED ({b.reason}) → auto-queued bulk request #{rid} ({jcfg['state']})", "blocked"
    except (FetchError, ValueError, ET.ParseError, KeyError) as e:
        n, detail, status = 0, f"{type(e).__name__}: {e}", "error"
    db.mark_source(conn, src_key, status, detail, n)
    return {"source": src_key, "method": method, "status": status, "items": n, "detail": detail}
