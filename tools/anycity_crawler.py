#!/usr/bin/env python3
"""Any-city municipal harvester: an adaptive focused incremental crawler.

Technical classification
------------------------
The established name for this class of tool is an **adaptive focused
incremental Web crawler with automatic wrapper induction**:

* *Focused (topical) crawling* -- Chakrabarti, van den Berg & Dom (1999):
  a crawler that does not try to copy the whole Web (or whole site); it
  scores every discovered URL for relevance to a topic -- here, civic
  records -- and spends its fetch budget best-first on the highest scores.
* *Platform fingerprinting + automatic wrapper induction* -- before
  harvesting, an exploratory/reconnaissance crawl maps the target's
  infrastructure (CMS and agenda-platform signatures, sitemaps, URL
  templates, document listings).  From that map the tool *induces a
  wrapper*: the site-specific extraction configuration (allowed hosts,
  listing pages, document URL templates, classification evidence).  The
  wrapper is written out as ``site-profile.json`` so a human can review,
  edit and reuse it -- the generated scraper design.
* *Incremental crawling* -- later runs re-visit with conditional requests
  (ETag / Last-Modified) and SHA-256 comparison, so only new or changed
  PDFs and pages are downloaded and every observed change is logged.

Point it at any town or city seed URL::

    python3 tools/anycity_crawler.py run https://www.exampleville.gov \\
        --workdir towns/exampleville

    # or the two phases separately (review/edit the wrapper in between):
    python3 tools/anycity_crawler.py recon https://www.exampleville.gov \\
        --out towns/exampleville/site-profile.json
    python3 tools/anycity_crawler.py crawl \\
        --profile towns/exampleville/site-profile.json \\
        --state-dir towns/exampleville/state --output towns/exampleville/out

Standard library only, like ``tools/sync_city.py`` (the Cheyenne-specific
mirror).  Safety defaults mirror that tool: robots.txt is honoured per
host and fails closed, requests are delayed and budgeted, no forms are
submitted, no logins are attempted, upstream scripts are never executed
or republished, and PDFs are stored byte-for-byte with their hash.

Known limitation (true of every non-browser crawler): agenda platforms
that render listings only with JavaScript (notably BoardDocs) or hide
documents behind search forms are *fingerprinted and recorded*, but their
JS-only listings need a headless-browser (deep/hidden-Web) stage that is
deliberately out of scope here.  The profile says which platform was
found so that stage can be added per platform, not per city.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import heapq
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse as urlparse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def default_config(**overrides):
    config = {
        "user_agent": "RealWindyCityAnyCity/1.0 (+https://github.com/therealwindycity/The-Real-Windy-City-)",
        "delay_seconds": 3,
        "timeout_seconds": 35,
        "max_run_seconds": 5400,
        "recon_max_pages": 200,
        "recon_min_score": 5,
        "focused_min_score": 5,
        "max_pages_per_run": 1500,
        "max_bytes_per_run": 250_000_000,
        "max_file_bytes": 20_000_000,
        "max_archive_bytes": 400_000_000,
        "max_sitemaps": 30,
        "document_types": {"application/pdf": ".pdf", "text/plain": ".txt"},
        "exclude_path_patterns": [
            r"/(?:admin|wp-admin|wp-login\.php|login|logout|signin|cart|checkout|myaccount|payments?)(?:/|$)",
            r"\.(?:js|css|png|jpe?g|gif|webp|svg|ico|woff2?|ttf|eot|mp[34]|mov|avi|zip|exe|msi)$",
        ],
    }
    config.update({k: v for k, v in overrides.items() if v is not None})
    return config


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def key(url):
    return hashlib.sha256(url.encode()).hexdigest()[:24]


# --------------------------------------------------------------------------
# Platform fingerprint signatures
#
# US municipal sites are rarely bespoke: the main site is usually one CMS
# and the agendas/minutes live on a second, vendor-hosted platform.  One
# adapter per *platform* therefore generalises across thousands of cities.
# Evidence is deliberately redundant (host, URL shape, body text) because
# vendors also run on city-owned custom domains.
# --------------------------------------------------------------------------

PLATFORMS = [
    {"id": "civicplus", "name": "CivicPlus (incl. Agenda Center / Document Center)",
     "host": r"(^|\.)civicplus\.com$", "url": r"/(?:AgendaCenter|DocumentCenter|CivicAlerts)/",
     "body": ("civicplus", "powered by civicplus"), "crawlable": True},
    {"id": "granicus", "name": "Granicus govMeetings / Peak Agenda / MediaManager",
     "host": r"(^|\.)granicus\.com$", "url": r"/(?:MetaViewer\.php|AgendaViewer|ViewPublisher|ViewAgendaHTML)",
     "body": ("granicus",), "crawlable": True},
    {"id": "legistar", "name": "Granicus Legistar / InSite",
     "host": r"(^|\.)legistar\.com$", "url": r"/LegislationDetail\.aspx",
     "body": ("legistar",), "crawlable": True},
    {"id": "boarddocs", "name": "BoardDocs (Diligent)",
     "host": r"(^|\.)boarddocs\.com$", "url": r"/Board\.nsf/",
     "body": ("boarddocs",), "crawlable": True,
     "note": "Listings are JavaScript-rendered; fingerprint is reliable, document discovery may need a headless-browser stage."},
    {"id": "primegov", "name": "PrimeGov",
     "host": r"(^|\.)primegov\.com$", "url": r"/public/(?:portal|meeting|compiledagenda)",
     "body": ("primegov",), "crawlable": True},
    {"id": "novusagenda", "name": "NovusAGENDA (Granicus)",
     "host": r"(^|\.)novusagenda\.com$", "url": r"/AgendaPublic/",
     "body": ("novusagenda",), "crawlable": True},
    {"id": "civicclerk", "name": "CivicClerk (CivicPlus / Municode Meetings)",
     "host": r"(^|\.)civicclerk\.com$", "url": r"/web/(?:Meetings|agenda)",
     "body": ("civicclerk",), "crawlable": True},
    {"id": "municode", "name": "Municode Library / Meetings",
     "host": r"(^|\.)municode\.com$", "url": r"/codes/code_of_ordinances",
     "body": ("municode",), "crawlable": True},
    {"id": "laserfiche", "name": "Laserfiche WebLink / Public Portal",
     "host": r"(^|\.)laserfiche\.com$", "url": r"/WebLink/",
     "body": ("laserfiche", "lfweblink"), "crawlable": True},
    {"id": "iqm2", "name": "IQM2 MinuteTraq",
     "host": r"(^|\.)iqm2\.com$", "url": r"/Citizens/",
     "body": ("iqm2", "minutetraq"), "crawlable": True},
    {"id": "simbli", "name": "Simbli eBoardSolutions",
     "host": r"(^|\.)eboardsolutions\.com$", "url": r"/(?:SB_|simbli)/",
     "body": ("simbli", "eboardsolutions"), "crawlable": True},
    {"id": "onbase", "name": "Hyland OnBase Agenda Online",
     "host": r"(^|\.)onbaseonline\.com$", "url": r"/AgendaOnline/",
     "body": ("onbase agenda", "hyland onbase"), "crawlable": True},
    {"id": "wordpress", "name": "WordPress (generic small-town site)",
     "host": r"$^", "url": r"/wp-content/uploads/",
     "body": ("wp-content", "wp-includes", 'content="wordpress'), "crawlable": True},
    {"id": "drupal", "name": "Drupal (generic)",
     "host": r"$^", "url": r"/sites/default/files/",
     "body": ("drupalsettings", 'content="drupal'), "crawlable": True},
    {"id": "youtube", "name": "YouTube (meeting video)",
     "host": r"(^|\.)(?:youtube\.com|youtu\.be)$", "url": r"/(?:watch|live|@|channel/)",
     "body": (), "crawlable": False,
     "note": "Video/captions are a separate harvester (see tools/fetch_transcripts.py); recorded here as linked infrastructure."},
    {"id": "vimeo", "name": "Vimeo (meeting video)",
     "host": r"(^|\.)vimeo\.com$", "url": r"/\d+$",
     "body": (), "crawlable": False,
     "note": "Recorded as linked video infrastructure; not crawled by this tool."},
]

PLATFORM_BY_ID = {p["id"]: p for p in PLATFORMS}


def _platform_hits(url="", html_sample="", headers=None):
    """Yield (platform_id, evidence_type, evidence) for one observation."""
    parsed = urlparse.urlsplit(url) if url else None
    host = (parsed.hostname or "") if parsed else ""
    path = (parsed.path or "") if parsed else ""
    sample = (html_sample or "")[:200_000].lower()
    for plat in PLATFORMS:
        if host and re.search(plat["host"], host):
            yield plat["id"], "host", host
        if path and re.search(plat["url"], path):
            yield plat["id"], "url", url[:200]
        for marker in plat["body"]:
            if marker in sample:
                yield plat["id"], "body", marker
        if headers:
            server = " ".join(str(headers.get(k, "")) for k in ("server", "x-powered-by")).lower()
            for marker in plat["body"]:
                if marker in server:
                    yield plat["id"], "header", marker


# --------------------------------------------------------------------------
# Civic relevance scoring, document classification, date extraction
# --------------------------------------------------------------------------

CIVIC_KEYWORDS = {
    "agenda": 12, "minutes": 12, "packet": 10, "ordinance": 9,
    "resolution": 8, "staff report": 8, "public hearing": 8,
    "budget": 7, "meeting": 6, "council": 6, "commission": 6,
    "board": 5, "planning": 5, "zoning": 5, "proclamation": 5,
    "record of proceedings": 9, "documents": 3, "archive": 4,
    "records": 4, "calendar": 3, "news": 2,
}

_MONTHS = {name: i for i, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_MONTHS.update({name[:3]: i for name, i in list(_MONTHS.items())})


def _safe_date(year, month, day):
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (ValueError, OverflowError):
        return None


def extract_date(*texts):
    """First plausible meeting/document date in the texts, ISO or None."""
    blob = " ".join(t for t in texts if t)
    match = re.search(r"\b(20\d{2})[-_/](1[0-2]|0?[1-9])[-_/](3[01]|[12]\d|0?[1-9])\b", blob)
    if match and (found := _safe_date(*match.groups())):
        return found
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(3[01]|[12]?\d)(?:st|nd|rd|th)?,?\s+(20\d{2})\b", blob, re.I)
    if match:
        month = _MONTHS.get(match.group(1).lower().rstrip(".")[:9]) or _MONTHS.get(match.group(1).lower()[:3])
        if month and (found := _safe_date(match.group(3), month, match.group(2))):
            return found
    match = re.search(r"\b(1[0-2]|0?[1-9])[-/.](3[01]|[12]\d|0?[1-9])[-/.](20\d{2})\b", blob)
    if match and (found := _safe_date(match.group(3), match.group(1), match.group(2))):
        return found
    match = re.search(r"(?:^|[-_])(20\d{2})(1[0-2]|0[1-9])(3[01]|[12]\d|0[1-9])(?:[-_.]|$)", blob)
    if match and (found := _safe_date(*match.groups())):
        return found
    return None


def classify_document(*texts):
    """Civic document kind from anchor text / URL, most specific first."""
    blob = " ".join(t for t in texts if t).lower().replace("-", " ").replace("_", " ")
    if "packet" in blob:
        return "agenda-packet"
    if "minutes" in blob or "record of proceedings" in blob:
        return "minutes"
    if "agenda" in blob:
        return "agenda"
    if "staff report" in blob:
        return "staff-report"
    if "ordinance" in blob:
        return "ordinance"
    if "resolution" in blob:
        return "resolution"
    if "budget" in blob or "audit" in blob or "financial" in blob:
        return "budget-finance"
    if "proclamation" in blob:
        return "proclamation"
    return "document"


def score_candidate(url, anchor=""):
    """Focused-crawling relevance score for a discovered URL."""
    path = urlparse.unquote(urlparse.urlsplit(url).path).lower().replace("-", " ").replace("_", " ")
    blob = f"{anchor.lower()} {path}"
    score = sum(weight for word, weight in CIVIC_KEYWORDS.items() if word in blob)
    if path.strip().endswith((".pdf", ".txt")):
        score += 8
    if re.search(r"viewfile|viewagenda|getagenda|document|download|weblink", path):
        score += 4
    if extract_date(anchor, urlparse.urlsplit(url).path):
        score += 5
    return score


def templatize_url(url):
    """Wrapper-induction primitive: generalise a URL into its template.

    ``/AgendaCenter/ViewFile/Item/1234`` -> ``/AgendaCenter/ViewFile/Item/{id}``
    ``/uploads/2026/01/agenda-2026-01-05.pdf`` -> ``/uploads/{year}/{id}/agenda-{date}.pdf``
    Repeated templates with many instances are a platform's document
    pattern, whether or not the platform itself was recognised.
    """
    parsed = urlparse.urlsplit(url)
    segments = []
    for segment in parsed.path.split("/"):
        if not segment:
            segments.append(segment)
        elif re.fullmatch(r"20\d{2}", segment):
            segments.append("{year}")
        elif re.fullmatch(r"\d+", segment):
            segments.append("{id}")
        elif re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|[0-9a-fA-F]{16,}", segment):
            segments.append("{id}")
        else:
            segment = re.sub(r"20\d{2}[-_](?:1[0-2]|0\d)[-_](?:3[01]|[12]\d|0\d)", "{date}", segment)
            segment = re.sub(r"\d+", "{id}", segment)
            segments.append(segment)
    template = "/".join(segments)
    if parsed.query:
        keys = sorted(k for k, _ in urlparse.parse_qsl(parsed.query, keep_blank_values=True))
        template += "?" + "&".join(f"{k}={{*}}" for k in keys)
    return f"{parsed.hostname}{template}"


def is_document_url(url):
    return urlparse.urlsplit(url).path.lower().endswith((".pdf", ".txt"))


# --------------------------------------------------------------------------
# Scope: which hosts may be crawled for this town
# --------------------------------------------------------------------------

class Scope:
    """Seed domain + its subdomains + fingerprinted vendor platforms.

    This is what makes the crawler portable: a city's agendas usually do
    NOT live on the seed host, so a single-host crawler (like the original
    Cheyenne mirror) silently misses them.  Vendor hosts are admitted by
    fingerprint, recorded in the profile, and robots-checked separately.
    """

    def __init__(self, seed_url, allow_hosts=()):
        parsed = urlparse.urlsplit(seed_url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise ValueError(f"Seed must be an http(s) URL, got {seed_url!r}")
        self.seed_url = seed_url
        self.seed_host = parsed.hostname.lower()
        self.bare_host = self.seed_host[4:] if self.seed_host.startswith("www.") else self.seed_host
        self.allow_hosts = {h.lower() for h in allow_hosts}
        self.discovered = {}  # host -> reason, filled as platforms are found

    def reason(self, url):
        host = (urlparse.urlsplit(url).hostname or "").lower()
        if not host:
            return None
        if host == self.bare_host or host.endswith("." + self.bare_host):
            return "seed-domain"
        if host in self.allow_hosts or host in self.discovered:
            return "allowlist"
        for plat in PLATFORMS:
            if plat["crawlable"] and re.search(plat["host"], host):
                return f"platform:{plat['id']}"
        return None

    def allowed(self, url):
        return self.reason(url) is not None

    def note(self, url):
        reason = self.reason(url)
        host = (urlparse.urlsplit(url).hostname or "").lower()
        if reason and reason != "seed-domain" and host:
            self.discovered.setdefault(host, reason)
        return reason


def canonical(raw, base, scope, config):
    try:
        parsed = urlparse.urlsplit(urlparse.urljoin(base, raw))
    except (ValueError, TypeError):
        return None
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password:
        return None
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = host + (f":{port}" if port and (parsed.scheme, port) not in
                     (("https", 443), ("http", 80)) else "")
    absolute = urlparse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    if not scope.allowed(absolute):
        return None
    decoded = urlparse.unquote(parsed.path or "/")
    if any(re.search(p, decoded, re.I) for p in config["exclude_path_patterns"]):
        return None
    query = [(k, v) for k, v in urlparse.parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    if len(query) > 10 or len(parsed.query) > 1000:
        return None
    origin = f"{parsed.scheme}://{netloc}"
    path = urlparse.quote(parsed.path or "/", safe="/%;:@!$&'()*+,=-._~")
    return origin + path + ("?" + urlparse.urlencode(sorted(query)) if query else "")


# --------------------------------------------------------------------------
# HTML parsing (links, title, text, fingerprint assets)
# --------------------------------------------------------------------------

class ReconParser(HTMLParser):
    blocked = {"script", "style", "noscript", "template"}
    blocks = {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "h4", "tr", "br", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.suppressed = []
        self.parts, self.title_parts, self.links, self.assets = [], [], [], []
        self.in_title = False
        self.link = None
        self.generator = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and (attrs.get("name") or "").lower() == "generator":
            self.generator = attrs.get("content") or ""
        if tag in ("script", "link", "img", "iframe"):
            src = attrs.get("src") or attrs.get("href")
            if src:
                self.assets.append(src)
        if tag in self.blocked:
            self.suppressed.append(tag)
        if self.suppressed:
            return
        if tag == "title":
            self.in_title = True
        if tag in self.blocks:
            self.parts.append("\n")
        if tag == "a" and attrs.get("href"):
            self.link = [attrs["href"], []]

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if tag == "title":
            self.in_title = False
        if tag in self.blocks:
            self.parts.append("\n")
        if tag == "a" and self.link:
            self.links.append((self.link[0], "".join(self.link[1]).strip()))
            self.link = None

    def handle_data(self, data):
        if self.suppressed:
            return
        (self.title_parts if self.in_title else self.parts).append(data)
        if self.link:
            self.link[1].append(data)

    @property
    def text(self):
        return "\n".join(line for line in
                         (re.sub(r"\s+", " ", x).strip() for x in "".join(self.parts).splitlines()) if line)

    @property
    def title(self):
        return re.sub(r"\s+", " ", "".join(self.title_parts)).strip()


def decode_html(body, content_type=""):
    charset = re.search(r"charset=[\"']?([\w-]+)", content_type or "", re.I)
    try:
        return body.decode(charset.group(1) if charset else "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Per-host polite fetcher (robots fails closed per host, like sync_city.py)
# --------------------------------------------------------------------------

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Fetcher:
    def __init__(self, config, scope, transport=None, sleep=time.sleep):
        self.config, self.scope = config, scope
        self.transport = transport or self.http
        self.sleep = sleep
        self.robots = {}          # origin -> RobotFileParser | Exception
        self.sitemaps = {}        # origin -> [sitemap urls]
        self.delay = {}           # origin -> seconds
        self.last_request = {}
        self.bytes = 0
        self.deadline = time.monotonic() + config.get("max_run_seconds", 5400)

    @staticmethod
    def origin_of(url):
        parsed = urlparse.urlsplit(url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        suffix = f":{port}" if port and (parsed.scheme, port) not in \
            (("https", 443), ("http", 80)) else ""
        return f"{parsed.scheme}://{parsed.hostname}{suffix}"

    def http(self, url, headers):
        req = urllib.request.Request(url, headers=headers, method="GET")
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(req, timeout=self.config["timeout_seconds"])
        except urllib.error.HTTPError as error:
            response = error
        with response:
            cap = min(self.config["max_file_bytes"],
                      self.config["max_bytes_per_run"] - self.bytes)
            length = response.headers.get("Content-Length")
            if length and int(length) > cap:
                raise ValueError("Response exceeds download budget")
            body = response.read(cap + 1)
            if len(body) > cap:
                self.bytes += len(body)
                raise ValueError("Response exceeds download budget")
            return response.status, {k.lower(): v for k, v in response.headers.items()}, body

    def _polite_wait(self, origin):
        if origin in self.last_request:
            wait = self.delay.get(origin, self.config["delay_seconds"]) - (time.monotonic() - self.last_request[origin])
            if wait > 0:
                self.sleep(wait)
        self.last_request[origin] = time.monotonic()

    def ensure_robots(self, origin):
        if origin in self.robots:
            cached = self.robots[origin]
            if isinstance(cached, Exception):
                raise PermissionError(str(cached))
            return cached
        parser = urllib.robotparser.RobotFileParser()
        try:
            url = origin + "/robots.txt"
            for _ in range(4):
                self._polite_wait(origin)
                status, headers, body = self.transport(
                    url, {"User-Agent": self.config["user_agent"], "Accept-Encoding": "identity"})
                self.bytes += len(body)
                if status in (301, 302, 303, 307, 308):
                    dest = canonical(headers.get("location", ""), url, self.scope, self.config)
                    if not dest or self.origin_of(dest) != origin:
                        raise ValueError("robots.txt redirects off-origin; failing closed")
                    url = dest
                    continue
                break
            else:
                raise ValueError("robots.txt redirect loop; failing closed")
            if status == 404:
                parser.parse([])
            elif status == 200:
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
            else:
                raise ValueError(f"robots.txt HTTP {status} at {origin}; failing closed for this host")
        except Exception as error:
            self.robots[origin] = error
            raise PermissionError(str(error)) from error
        self.robots[origin] = parser
        delay = parser.crawl_delay(self.config["user_agent"])
        rate = parser.request_rate(self.config["user_agent"])
        self.delay[origin] = max(
            self.config["delay_seconds"], delay or 0,
            rate.seconds / rate.requests if rate and rate.requests else 0)
        self.sitemaps[origin] = parser.site_maps() or [origin + "/sitemap.xml"]
        return parser

    def request(self, url, headers=None):
        """GET with per-host robots, bounded redirects/retries. Returns
        (status, headers, body, final_url)."""
        headers = {"User-Agent": self.config["user_agent"],
                   "Accept-Encoding": "identity", **(headers or {})}
        for _redirect in range(6):
            if canonical(url, url, self.scope, self.config) != url:
                raise ValueError("URL outside allowed scope")
            origin = self.origin_of(url)
            robots = self.ensure_robots(origin)
            if not robots.can_fetch(self.config["user_agent"], url):
                raise PermissionError(f"Disallowed by robots.txt at {origin}")
            if self.bytes >= self.config["max_bytes_per_run"]:
                raise ValueError("Run download budget exhausted")
            for attempt in range(3):
                if time.monotonic() >= self.deadline:
                    raise TimeoutError("Run time budget exhausted")
                self._polite_wait(origin)
                status, response_headers, body = self.transport(url, headers)
                self.bytes += len(body)
                if status not in (429, 503) or attempt == 2:
                    break
                retry = str(response_headers.get("retry-after", ""))
                self.sleep(min(120, max(self.delay.get(origin, 3),
                                        int(retry) if retry.isdigit() else 15 * (attempt + 1))))
            if status in (301, 302, 303, 307, 308):
                destination = canonical(response_headers.get("location", ""), url,
                                        self.scope, self.config)
                if not destination or destination == url:
                    raise ValueError("Redirect outside allowed scope or redirect loop")
                self.scope.note(destination)
                url = destination
                headers = {"User-Agent": self.config["user_agent"], "Accept-Encoding": "identity"}
                continue
            return status, response_headers, body, url
        raise ValueError("Too many redirects")


def sitemap_urls(fetcher, seeds, config, errors):
    maps, visited, pages = deque(seeds), set(), []
    while maps and len(visited) < config["max_sitemaps"] and time.monotonic() < fetcher.deadline:
        raw_map = maps.popleft()
        url = canonical(raw_map, raw_map, fetcher.scope, config)
        if not url or url in visited:
            continue
        visited.add(url)
        try:
            status, _, body, _ = fetcher.request(url)
            if status != 200:
                continue
            tree = ET.fromstring(body)
            is_index = tree.tag.split("}")[-1] == "sitemapindex"
            for element in tree.iter():
                if element.tag.split("}")[-1] == "loc" and element.text:
                    candidate = canonical(element.text.strip(), url, fetcher.scope, config)
                    if candidate:
                        (maps if is_index else pages).append(candidate)
        except Exception as error:  # a bad sitemap must not sink the run
            errors.append({"url": url, "error": str(error)[:250]})
    return pages


# --------------------------------------------------------------------------
# Phase 1 -- reconnaissance / fingerprinting + wrapper induction
# --------------------------------------------------------------------------

class Recon:
    def __init__(self, seed_url, config=None, transport=None, sleep=time.sleep, allow_hosts=()):
        self.config = config or default_config()
        self.scope = Scope(seed_url, allow_hosts)
        self.seed = canonical(seed_url, seed_url, self.scope, self.config) or seed_url
        self.fetcher = Fetcher(self.config, self.scope, transport, sleep)
        self.evidence = defaultdict(lambda: {"count": 0, "types": set(), "examples": []})
        self.candidates = {}   # url -> candidate record
        self.pages = []        # visited page summaries
        self.errors, self.blocked = [], 0

    def _note_platform(self, url="", html_sample="", headers=None):
        for plat_id, kind, evidence in _platform_hits(url, html_sample, headers):
            slot = self.evidence[plat_id]
            slot["count"] += 1
            slot["types"].add(kind)
            if evidence not in slot["examples"] and len(slot["examples"]) < 5:
                slot["examples"].append(evidence)

    def _candidate(self, url, anchor, source):
        record = self.candidates.setdefault(url, {
            "url": url, "anchors": [], "sources": [], "score": 0,
            "is_document_url": is_document_url(url),
            "doc_kind_guess": None, "date_guess": None, "template": templatize_url(url)})
        if anchor and anchor not in record["anchors"] and len(record["anchors"]) < 5:
            record["anchors"].append(anchor[:200])
        if source and source not in record["sources"] and len(record["sources"]) < 5:
            record["sources"].append(source)
        record["score"] = max(record["score"], score_candidate(url, anchor))
        record["doc_kind_guess"] = classify_document(anchor, url)
        record["date_guess"] = extract_date(anchor, urlparse.urlsplit(url).path)
        return record

    def run(self):
        heap, scheduled, counter = [], set(), 0

        def enqueue(url, score, depth, anchor="", source=""):
            nonlocal counter
            if url in scheduled:
                return
            scheduled.add(url)
            counter += 1
            heapq.heappush(heap, (-score, counter, url, depth, anchor, source))

        enqueue(self.seed, 10_000, 0)
        self._candidate(self.seed, "seed", "")
        # Sitemap seeds from the seed host's robots.txt.
        try:
            self.fetcher.ensure_robots(Fetcher.origin_of(self.seed))
            for url in sitemap_urls(self.fetcher,
                                    self.fetcher.sitemaps.get(Fetcher.origin_of(self.seed), []),
                                    self.config, self.errors):
                record = self._candidate(url, "", "sitemap")
                enqueue(url, record["score"], 1, source="sitemap")
        except PermissionError as error:
            self.errors.append({"url": self.seed, "error": str(error)[:250]})
            self.blocked += 1

        fetched = 0
        while heap and fetched < self.config["recon_max_pages"] \
                and self.fetcher.bytes < self.config["max_bytes_per_run"] \
                and time.monotonic() < self.fetcher.deadline:
            _neg, _n, url, depth, anchor, _source = heapq.heappop(heap)
            if is_document_url(url):
                continue  # catalogued as a candidate; bytes are Phase 2's job
            fetched += 1
            try:
                status, headers, body, final = self.fetcher.request(url)
            except PermissionError:
                self.blocked += 1
                continue
            except Exception as error:
                self.errors.append({"url": url, "error": str(error)[:250]})
                continue
            self.scope.note(final)
            self._note_platform(url=final, headers=headers)
            content_type = headers.get("content-type", "").split(";")[0].strip().lower()
            if status != 200:
                self.errors.append({"url": url, "error": f"HTTP {status}"})
                continue
            if content_type in self.config["document_types"]:
                record = self._candidate(final, anchor, url)
                record["probed_content_type"] = content_type
                record["is_document_url"] = True
                continue
            if content_type not in ("text/html", "application/xhtml+xml"):
                continue
            html_text = decode_html(body, headers.get("content-type", ""))
            self._note_platform(url=final, html_sample=html_text, headers=headers)
            parser = ReconParser()
            parser.feed(html_text)
            if parser.generator:
                self._note_platform(html_sample=parser.generator)
            for asset in parser.assets:
                self._note_platform(url=urlparse.urljoin(final, asset))
            doc_links = civic_links = 0
            for href, text in parser.links:
                absolute = urlparse.urljoin(final, href)
                self._note_platform(url=absolute)  # outbound vendor links are infrastructure too
                target = canonical(href, final, self.scope, self.config)
                if not target:
                    continue
                self.scope.note(target)
                record = self._candidate(target, text, final)
                if record["is_document_url"] or record["doc_kind_guess"] != "document" \
                        and record["score"] >= 12:
                    doc_links += 1
                if record["score"] >= self.config["recon_min_score"]:
                    civic_links += 1
                if depth < 1 or record["score"] >= self.config["recon_min_score"]:
                    enqueue(target, record["score"], depth + 1, text, final)
            self.pages.append({
                "url": final, "title": parser.title or final,
                "out_links": len(parser.links),
                "document_links": doc_links, "civic_links": civic_links,
                "score": score_candidate(final, parser.title),
            })
        return self.profile(pending=len(heap))

    def profile(self, pending=0):
        """Induce the wrapper: the generated, reviewable scraper design."""
        platforms = []
        for plat_id, slot in self.evidence.items():
            plat = PLATFORM_BY_ID[plat_id]
            types = sorted(slot["types"])
            confidence = "high" if "host" in types or len(types) >= 2 or slot["count"] >= 3 \
                else "medium" if slot["count"] >= 1 else "low"
            platforms.append({
                "id": plat_id, "name": plat["name"], "confidence": confidence,
                "evidence_count": slot["count"], "evidence_types": types,
                "examples": slot["examples"], "crawlable": plat["crawlable"],
                **({"note": plat["note"]} if "note" in plat else {}),
            })
        platforms.sort(key=lambda p: (-p["evidence_count"], p["id"]))

        templates = {}
        for record in self.candidates.values():
            slot = templates.setdefault(record["template"], {
                "template": record["template"], "count": 0, "examples": [],
                "is_document_template": False, "doc_kinds": Counter()})
            slot["count"] += 1
            if len(slot["examples"]) < 5:
                slot["examples"].append(record["url"])
            slot["is_document_template"] = slot["is_document_template"] or \
                record["is_document_url"] or bool(record.get("probed_content_type"))
            slot["doc_kinds"][record["doc_kind_guess"]] += 1
        template_list = [{
            "template": s["template"], "count": s["count"], "examples": s["examples"],
            "is_document_template": s["is_document_template"],
            "doc_kinds": dict(s["doc_kinds"]),
        } for s in sorted(templates.values(), key=lambda s: (-s["count"], s["template"]))]

        listing_pages = sorted(
            (p for p in self.pages if p["document_links"] >= 2 or p["civic_links"] >= 5),
            key=lambda p: (-p["document_links"], -p["civic_links"], p["url"]))[:25]
        suggested = [self.seed]
        for page in listing_pages:
            if page["url"] not in suggested:
                suggested.append(page["url"])
        for record in sorted((c for c in self.candidates.values() if not c["is_document_url"]),
                              key=lambda c: (-c["score"], c["url"])):
            if len(suggested) >= 60:
                break
            if record["score"] >= self.config["focused_min_score"] and record["url"] not in suggested:
                suggested.append(record["url"])

        return {
            "schema_version": 1,
            "tool": "anycity_crawler.py",
            "crawler_type": "adaptive focused incremental crawler with platform "
                            "fingerprinting and automatic wrapper induction",
            "generated_at": now(),
            "seed": self.seed,
            "scope": {
                "seed_host": self.scope.seed_host,
                "bare_host": self.scope.bare_host,
                "discovered_external_hosts": [
                    {"host": host, "reason": reason}
                    for host, reason in sorted(self.scope.discovered.items())],
                "allow_hosts": sorted(self.scope.allow_hosts),
            },
            "platforms_detected": platforms,
            "wrapper": {
                "suggested_seeds": suggested,
                "listing_pages": listing_pages,
                "url_templates": template_list,
                "document_templates": [t for t in template_list if t["is_document_template"]],
                "candidate_documents_seen_in_recon": sum(
                    1 for c in self.candidates.values() if c["is_document_url"]),
            },
            "recon_report": {
                "pages_fetched": len(self.pages),
                "candidates_discovered": len(self.candidates),
                "blocked_by_robots": self.blocked,
                "pending_unfetched": pending,
                "bytes_downloaded": self.fetcher.bytes,
                "errors": self.errors,
            },
            "crawl_policy": {k: self.config[k] for k in (
                "user_agent", "delay_seconds", "focused_min_score",
                "max_pages_per_run", "max_file_bytes", "document_types")},
            "limitations": [
                "JavaScript-only listings and search-form (deep Web) archives are fingerprinted but not enumerated by this static crawler.",
                "'Platforms detected' is fingerprint evidence, not proof of contract or completeness.",
                "A completed run means the discovered priority queue was processed within budget, not that every public record was found.",
            ],
        }


# --------------------------------------------------------------------------
# Phase 2 -- focused incremental harvest using the induced wrapper
# --------------------------------------------------------------------------

def fresh_state():
    return {"records": {}, "changes": [], "pending": []}


class Harvester:
    def __init__(self, profile, state_dir, output_dir, config=None,
                 transport=None, sleep=time.sleep):
        if profile.get("schema_version") != 1 or not profile.get("seed"):
            raise ValueError("Profile is not a schema-1 anycity site profile")
        merged = default_config(**{**profile.get("crawl_policy", {}),
                                   **(config or {})})
        self.config, self.profile = merged, profile
        allow = [h["host"] for h in profile.get("scope", {}).get("discovered_external_hosts", [])]
        allow += profile.get("scope", {}).get("allow_hosts", [])
        self.scope = Scope(profile["seed"], allow_hosts=allow)
        self.fetcher = Fetcher(self.config, self.scope, transport, sleep)
        self.state_dir, self.output = Path(state_dir), Path(output_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "state.json"
        self.state = self._load_state()
        self.records = self.state["records"]
        self.archive_bytes = sum(r.get("source_bytes", 0) for r in self.records.values())
        self.meta = {}  # url -> best {anchor, source, score, depth}
        self.report = {"started_at": now(), "status": "running", "checked": 0,
                       "documents": 0, "pages": 0, "updated": 0, "unchanged": 0,
                       "blocked": 0, "excluded": 0, "errors": [], "pending": 0}

    def _load_state(self):
        if not self.state_path.exists():
            return fresh_state()
        try:
            state = json.loads(self.state_path.read_text())
            if not isinstance(state, dict) or not isinstance(state.get("records"), dict):
                raise ValueError("state shape invalid")
            state.setdefault("changes", [])
            state.setdefault("pending", [])
            return state
        except (ValueError, OSError, UnicodeDecodeError) as error:
            quarantine = self.state_dir / f"state-quarantine-{now().replace(':', '')}.json"
            try:
                self.state_path.replace(quarantine)
            except OSError:
                pass
            state = fresh_state()
            state["state_recovery"] = {"reason": str(error), "quarantined_at": now()}
            return state

    # -- one URL ----------------------------------------------------------
    def fetch_one(self, url, depth):
        old = self.records.get(url, {})
        headers = {}
        if old.get("etag"):
            headers["If-None-Match"] = old["etag"]
        if old.get("last_modified"):
            headers["If-Modified-Since"] = old["last_modified"]
        status, meta, body, final = self.fetcher.request(url, headers)
        self.report["checked"] += 1
        if status == 304 and old:
            old["checked_at"], old["source_status"] = now(), 304
            self.report["unchanged"] += 1
            return [(link, depth + 1, "") for link in old.get("links", [])]
        if status != 200:
            if old:
                old["source_status"], old["checked_at"] = status, now()
            raise RuntimeError(f"HTTP {status}; last archived version retained if available")
        kind = meta.get("content-type", "").split(";")[0].strip().lower()
        supported = kind in ("text/html", "application/xhtml+xml") or kind in self.config["document_types"]
        if supported and self.archive_bytes - old.get("source_bytes", 0) + len(body) \
                > self.config["max_archive_bytes"]:
            raise ValueError("Total archive budget exhausted; raise it deliberately or narrow the wrapper")
        info = self.meta.get(url, {})
        record = {"url": url, "final_url": final, "checked_at": now(), "fetched_at": now(),
                  "source_status": status, "etag": meta.get("etag"),
                  "last_modified": meta.get("last-modified"),
                  "sha256": hashlib.sha256(body).hexdigest(),
                  "content_type": kind, "source_bytes": len(body),
                  "template": templatize_url(final),
                  "discovered_from": info.get("source"), "anchor_text": info.get("anchor")}
        discovered = []
        if kind in ("text/html", "application/xhtml+xml"):
            parser = ReconParser()
            parser.feed(decode_html(body, meta.get("content-type", "")))
            links = []
            for href, text in parser.links:
                target = canonical(href, final, self.scope, self.config)
                if target:
                    links.append(target)
                    discovered.append((target, depth + 1, text))
            record.update(title=parser.title or final, text=parser.text, links=links,
                          kind="page", path=None,
                          doc_kind=classify_document(parser.title, final),
                          meeting_date=extract_date(parser.title, final))
            self.report["pages"] += 1
        elif kind in self.config["document_types"]:
            if kind == "application/pdf" and not body.startswith(b"%PDF-"):
                raise ValueError("PDF content signature mismatch")
            name = key(url) + self.config["document_types"][kind]
            dest = self.state_dir / "documents" / name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(body)
            record.update(
                title=info.get("anchor") or urlparse.unquote(
                    urlparse.urlsplit(final).path.rsplit("/", 1)[-1]) or "Document",
                kind="document", path="documents/" + name, links=[], text="",
                doc_kind=classify_document(info.get("anchor"), final),
                meeting_date=extract_date(info.get("anchor"), urlparse.urlsplit(final).path))
            self.report["documents"] += 1
        else:
            self.report["excluded"] += 1
            return []
        if old.get("sha256") == record["sha256"]:
            self.report["unchanged"] += 1
            record["fetched_at"] = old.get("fetched_at", record["fetched_at"])
        else:
            self.report["updated"] += 1
            self.state["changes"].append({"url": url, "observed_at": now(),
                                           "before": old.get("sha256"),
                                           "after": record["sha256"]})
        self.archive_bytes += len(body) - old.get("source_bytes", 0)
        self.records[url] = record
        return discovered

    # -- best-first (focused) run -----------------------------------------
    def run(self):
        heap, scheduled, counter = [], set(), 0

        def enqueue(url, score, depth, anchor="", source=""):
            nonlocal counter
            target = canonical(url, self.profile["seed"], self.scope, self.config)
            if not target:
                return
            best = self.meta.get(target)
            if not best or score > best["score"]:
                self.meta[target] = {"anchor": anchor, "source": source,
                                     "score": score, "depth": depth}
            if target in scheduled:
                return
            scheduled.add(target)
            counter += 1
            heapq.heappush(heap, (-score, counter, target, depth))

        for url in self.state.get("pending", []):  # unfinished work first
            enqueue(url, 9_000, 1)
        enqueue(self.profile["seed"], 10_000, 0)
        for url in self.profile.get("wrapper", {}).get("suggested_seeds", []):
            enqueue(url, 8_000, 1)
        for url in sorted(self.records, key=lambda u: self.records[u].get("checked_at", "")):
            enqueue(url, 1, 1)  # incremental re-check, lowest priority

        attempts = 0
        while heap and attempts < self.config["max_pages_per_run"] \
                and self.fetcher.bytes < self.config["max_bytes_per_run"] \
                and time.monotonic() < self.fetcher.deadline:
            _neg, _n, url, depth = heapq.heappop(heap)
            attempts += 1
            try:
                for target, next_depth, anchor in self.fetch_one(url, depth):
                    score = score_candidate(target, anchor)
                    self.scope.note(target)
                    if is_document_url(target) or score >= self.config["focused_min_score"] \
                            or next_depth <= 1:
                        enqueue(target, score, next_depth, anchor, url)
            except PermissionError:
                self.report["blocked"] += 1
                if url in self.records:
                    self.records[url]["source_status"] = "robots-blocked"
            except Exception as error:
                self.report["errors"].append({"url": url, "error": str(error)[:250]})

        pending = [url for _s, _n, url, _d in heap]
        self.state["pending"] = pending
        self.report["pending"] = len(pending)
        self.report["status"] = "partial" if pending or self.report["errors"] else "completed"
        self.report["finished_at"] = now()
        self.report["bytes_downloaded"] = self.fetcher.bytes
        self.state["latest_run"] = self.report
        save_json(self.state_path, self.state)
        self.write_outputs()
        return self.report

    def write_outputs(self):
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "documents").mkdir(exist_ok=True)
        catalog, documents = [], []
        for url, record in sorted(self.records.items()):
            entry = {k: record.get(k) for k in (
                "title", "url", "final_url", "kind", "doc_kind", "meeting_date",
                "content_type", "source_bytes", "sha256", "etag", "last_modified",
                "fetched_at", "checked_at", "source_status", "template",
                "discovered_from", "anchor_text", "path")}
            catalog.append(entry)
            if record["kind"] == "document":
                source = self.state_dir / record["path"]
                if source.exists():
                    (self.output / record["path"]).write_bytes(source.read_bytes())
                    documents.append(entry)
        save_json(self.output / "catalog.json", catalog)
        with (self.output / "documents.jsonl").open("w", encoding="utf-8") as handle:
            for entry in sorted(documents, key=lambda e: (e["meeting_date"] or "", e["url"])):
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        save_json(self.output / "status.json", {
            "seed": self.profile["seed"],
            "platforms_detected": self.profile.get("platforms_detected", []),
            "latest_run": self.state.get("latest_run"),
            "changes": self.state.get("changes", []),
            "totals": {"records": len(catalog), "documents": len(documents)},
        })


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_common(parser):
    parser.add_argument("--delay-seconds", type=float)
    parser.add_argument("--user-agent")
    parser.add_argument("--max-pages", type=int, dest="max_pages_per_run")
    parser.add_argument("--allow-host", action="append", default=[])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    recon_parser = sub.add_parser("recon", help="Phase 1: fingerprint the site and induce a wrapper (site-profile.json)")
    recon_parser.add_argument("seed")
    recon_parser.add_argument("--out", required=True)
    recon_parser.add_argument("--recon-max-pages", type=int)
    _add_common(recon_parser)

    crawl_parser = sub.add_parser("crawl", help="Phase 2: focused incremental harvest using a site profile")
    crawl_parser.add_argument("--profile", required=True)
    crawl_parser.add_argument("--state-dir", required=True)
    crawl_parser.add_argument("--output", required=True)
    _add_common(crawl_parser)

    run_parser = sub.add_parser("run", help="Recon then harvest, in one workdir")
    run_parser.add_argument("seed")
    run_parser.add_argument("--workdir", required=True)
    run_parser.add_argument("--recon-max-pages", type=int)
    _add_common(run_parser)

    args = parser.parse_args(argv)
    overrides = {k: v for k, v in vars(args).items()
                 if k in ("delay_seconds", "user_agent", "max_pages_per_run", "recon_max_pages")
                 and v is not None}
    config = default_config(**overrides)

    if args.command == "recon":
        profile = Recon(args.seed, config, allow_hosts=args.allow_host).run()
        save_json(args.out, profile)
        print(json.dumps(profile["recon_report"], indent=2))
    elif args.command == "crawl":
        profile = json.loads(Path(args.profile).read_text())
        report = Harvester(profile, args.state_dir, args.output, config=overrides).run()
        print(json.dumps(report, indent=2))
        if report["errors"] and not report["checked"]:
            raise SystemExit(1)
    else:  # run
        workdir = Path(args.workdir)
        profile = Recon(args.seed, config, allow_hosts=args.allow_host).run()
        save_json(workdir / "site-profile.json", profile)
        report = Harvester(profile, workdir / "state", workdir / "out",
                           config=overrides).run()
        print(json.dumps({"recon": profile["recon_report"], "crawl": report}, indent=2))
        if report["errors"] and not report["checked"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
