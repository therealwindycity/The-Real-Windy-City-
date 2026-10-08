"""Pluggable legal-source search providers.

Provider results are discovery leads. They do not determine precedential force,
primary-source status beyond the provider's documented origin, currentness, or
legal applicability. Tests use injected transports and make no live requests.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from .ingest import SUPPORTED_SUFFIXES, extract_pdf_pages, load_case
from .models import AUTHORITY_LAYERS


class ProviderError(RuntimeError):
    """A provider could not be configured or returned a usable response."""


class HttpTransport(Protocol):
    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0) -> bytes:
        """Return response bytes or raise an informative exception."""


class UrllibTransport:
    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0) -> bytes:
        request = Request(url, headers=headers or {"User-Agent": "CivicLegalResearchRedTeam/0.2"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise ProviderError(f"HTTP {exc.code} fetching {url}") from exc
        except URLError as exc:
            raise ProviderError(f"Network error fetching {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ProviderError(f"Timed out fetching {url}") from exc


def _build_url(base: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return base
    parsed = urlparse(base)
    existing = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in params.items():
        if value is None or value == "":
            continue
        existing[key] = value if isinstance(value, list) else [str(value)]
    query = urlencode([(key, item) for key, values in existing.items() for item in values], doseq=True)
    return urlunparse(parsed._replace(query=query))


def _get_json(
    transport: HttpTransport,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> Any:
    full_url = _build_url(url, params)
    raw = transport.get(full_url, headers=headers, timeout=timeout)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(f"Provider returned invalid UTF-8 JSON from {full_url}") from exc


def _plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", " ", text)
    return " ".join(text.split()).strip()


def _captured_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class SearchRequest:
    query: str
    limit: int = 10
    jurisdiction: str | None = None
    as_of: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("Search query must be non-empty text")
        if not 1 <= self.limit <= 100:
            raise ValueError("Search limit must be between 1 and 100")
        if self.as_of is not None:
            if not isinstance(self.as_of, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.as_of):
                raise ValueError("Search as-of date must use YYYY-MM-DD format")
            try:
                date.fromisoformat(self.as_of)
            except ValueError as exc:
                raise ValueError("Search as-of date must be a valid calendar date") from exc


@dataclass(slots=True)
class SearchHit:
    provider: str
    record_id: str
    title: str
    citation: str | None = None
    layer: str = "other"
    jurisdiction: str | None = None
    source_kind: str = "unknown"
    source_url: str | None = None
    snippet: str | None = None
    decision_or_enactment_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    captured_at: str | None = None
    content_sha256: str | None = None
    primary_source_status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegalResearchProvider(Protocol):
    provider_id: str

    def search(self, request: SearchRequest) -> list[SearchHit]:
        """Search the provider and return provenance-tagged results."""


class EcfrProvider:
    """Official eCFR search API connector for current/historical regulations."""

    provider_id = "ecfr"
    SEARCH_URL = "https://www.ecfr.gov/api/search/v1/results"

    def __init__(self, transport: HttpTransport | None = None, *, timeout: float = 20.0) -> None:
        self.transport = transport or UrllibTransport()
        self.timeout = timeout

    def search(self, request: SearchRequest) -> list[SearchHit]:
        params: dict[str, Any] = {"query": request.query, "per_page": min(request.limit, 100)}
        if request.as_of:
            params["date"] = request.as_of
        payload = _get_json(
            self.transport,
            self.SEARCH_URL,
            params=params,
            headers={"User-Agent": "CivicLegalResearchRedTeam/0.2 (eCFR search)"},
            timeout=self.timeout,
        )
        records = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            raise ProviderError("eCFR search response did not contain a results array")
        hits: list[SearchHit] = []
        for record in records[:request.limit]:
            hierarchy = record.get("hierarchy") or {}
            headings = record.get("headings") or {}
            title_number = str(hierarchy.get("title") or "").strip()
            section = str(hierarchy.get("section") or "").strip()
            appendix = str(hierarchy.get("appendix") or "").strip()
            part = str(hierarchy.get("part") or "").strip()
            title_name = _plain_text(headings.get("title")) or f"Title {title_number}"
            section_heading = _plain_text(headings.get("section") or headings.get("appendix") or headings.get("part"))
            cite_unit = f"§ {section}" if section else (f"appendix {appendix}" if appendix else (f"part {part}" if part else ""))
            citation = f"{title_number} C.F.R. {cite_unit}" if title_number and cite_unit else None
            route, route_value = (
                ("section", section) if section else
                (("part", part) if part else (("appendix", appendix) if appendix else ("title", title_number)))
            )
            if request.as_of:
                source_url = f"https://www.ecfr.gov/on/{request.as_of}/title-{title_number}/{route}-{route_value}"
            else:
                source_url = f"https://www.ecfr.gov/current/title-{title_number}/{route}-{route_value}"
            identifier = section or appendix or part or str(record.get("structure_index", len(hits)))
            rid = f"ecfr-title-{title_number}-{route}-{identifier}"
            hits.append(SearchHit(
                provider=self.provider_id,
                record_id=rid,
                title=section_heading or title_name,
                citation=citation,
                layer="federal_regulation",
                jurisdiction="United States",
                source_kind=f"regulation_{route}",
                source_url=source_url,
                snippet=_plain_text(record.get("full_text_excerpt")),
                effective_from=record.get("starts_on"),
                effective_to=record.get("ends_on"),
                captured_at=_captured_now(),
                primary_source_status="official eCFR text; verify official CFR/Federal Register history for formal publication and amendments",
                metadata={
                    "title_number": title_number,
                    "section": section,
                    "appendix": appendix,
                    "part": part,
                    "hierarchy": hierarchy,
                    "change_types": record.get("change_types", []),
                    "removed": record.get("removed", False),
                    "reserved": record.get("reserved", False),
                    "date_filter": request.as_of,
                    "relevance_score": record.get("score"),
                    "index_url": "https://www.ecfr.gov/",
                },
                warnings=["Search result is a lead; verify the exact text, effective date, and Federal Register history before relying on it."],
            ))
        return hits


class FederalRegisterProvider:
    """Public Federal Register API connector for rules, notices, and amendments."""

    provider_id = "federal-register"
    SEARCH_URL = "https://www.federalregister.gov/api/v1/documents.json"

    def __init__(self, transport: HttpTransport | None = None, *, timeout: float = 20.0) -> None:
        self.transport = transport or UrllibTransport()
        self.timeout = timeout

    def search(self, request: SearchRequest) -> list[SearchHit]:
        params: dict[str, Any] = {
            "conditions[term]": request.query,
            "per_page": min(request.limit, 100),
            "order": "newest",
        }
        if request.as_of:
            params["conditions[publication_date][lte]"] = request.as_of
        payload = _get_json(
            self.transport,
            self.SEARCH_URL,
            params=params,
            headers={"User-Agent": "CivicLegalResearchRedTeam/0.2 (Federal Register search)"},
            timeout=self.timeout,
        )
        records = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            raise ProviderError("Federal Register response did not contain a results array")
        hits: list[SearchHit] = []
        for record in records[:request.limit]:
            volume = record.get("volume")
            start_page = record.get("start_page")
            if volume and start_page:
                citation = f"{volume} Fed. Reg. {start_page}"
            else:
                number = record.get("document_number")
                citation = f"Federal Register Document No. {number}" if number else None
            source_url = record.get("html_url") or record.get("public_inspection_pdf_url")
            hits.append(SearchHit(
                provider=self.provider_id,
                record_id=str(record.get("document_number") or record.get("id") or len(hits) + 1),
                title=_plain_text(record.get("title")) or "Untitled Federal Register document",
                citation=citation,
                layer="federal_regulation" if "rule" in str(record.get("type", "")).lower() else "agency_record",
                jurisdiction="United States",
                source_kind=str(record.get("type") or "Federal Register document"),
                source_url=source_url,
                snippet=_plain_text(record.get("abstract")),
                decision_or_enactment_date=record.get("publication_date"),
                effective_from=record.get("effective_on"),
                captured_at=_captured_now(),
                primary_source_status="official Federal Register government publication/search record; verify document and legal effect",
                metadata={
                    "document_number": record.get("document_number"),
                    "publication_date": record.get("publication_date"),
                    "effective_on": record.get("effective_on"),
                    "type": record.get("type"),
                    "volume": volume,
                    "start_page": start_page,
                    "end_page": record.get("end_page"),
                    "agencies": record.get("agencies", []),
                    "requested_as_of": request.as_of,
                    "publication_date_filter_applied": bool(request.as_of),
                },
                warnings=[
                    "A Federal Register publication may amend a regulation but does not by itself establish the currently operative codified text.",
                    *(["The as-of filter limits publication date only; it does not reconstruct legal effect as of that date."] if request.as_of else []),
                ],
            ))
        return hits


class _ConstitutionBlockParser(HTMLParser):
    """Retain headings and paragraph text from the Archives transcription."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str]] = []
        self.heading = "Preamble / unclassified section"
        self._tag: str | None = None
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "nav", "footer", "header"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in {"h1", "h2", "h3", "h4", "p", "li"}:
            self._flush()
            self._tag = tag
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "nav", "footer", "header"} and self._skip:
            self._skip -= 1
            return
        if self._tag == tag:
            value = " ".join(" ".join(self._parts).split())
            if value:
                if tag.startswith("h"):
                    self.heading = value
                else:
                    self.blocks.append((self.heading, value))
            self._tag = None
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._tag and not self._skip and data.strip():
            self._parts.append(data.strip())

    def _flush(self) -> None:
        if self._tag:
            value = " ".join(" ".join(self._parts).split())
            if value:
                if self._tag.startswith("h"):
                    self.heading = value
                else:
                    self.blocks.append((self.heading, value))
        self._tag = None
        self._parts = []


class NationalArchivesConstitutionProvider:
    """Search the National Archives' U.S. Constitution transcription."""

    provider_id = "us-constitution"
    SOURCE_URL = "https://www.archives.gov/founding-docs/constitution-transcript"

    def __init__(self, transport: HttpTransport | None = None, *, timeout: float = 20.0) -> None:
        self.transport = transport or UrllibTransport()
        self.timeout = timeout

    @staticmethod
    def _pinpoint(heading: str) -> str:
        article = re.search(r"Article\s+([IVXLCDM]+).*?Section\s+(\d+)", heading, re.I)
        if article:
            return f"U.S. Const. art. {article.group(1)}, § {article.group(2)}"
        amendment = re.search(r"Amendment\s+([IVXLCDM]+)", heading, re.I)
        if amendment:
            return f"U.S. Const. amend. {amendment.group(1)}"
        if "preamble" in heading.lower():
            return "U.S. Const. pmbl."
        return f"U.S. Const., {heading}"

    def search(self, request: SearchRequest) -> list[SearchHit]:
        raw = self.transport.get(
            self.SOURCE_URL,
            headers={"User-Agent": "CivicLegalResearchRedTeam/0.2 (National Archives Constitution search)"},
            timeout=self.timeout,
        )
        try:
            page = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProviderError("National Archives Constitution page was not UTF-8 HTML") from exc
        parser = _ConstitutionBlockParser()
        parser.feed(page)
        terms = [term for term in re.findall(r"[a-z0-9]+", request.query.lower()) if len(term) > 2]
        terms = list(dict.fromkeys(terms))
        hits: list[SearchHit] = []
        for index, (heading, paragraph) in enumerate(parser.blocks, start=1):
            normalized = " ".join(re.findall(r"[a-z0-9]+", paragraph.lower()))
            matches = [term for term in terms if term in normalized]
            if not matches:
                continue
            hits.append(SearchHit(
                provider=self.provider_id,
                record_id=f"archives-constitution-block-{index}",
                title=heading,
                citation=self._pinpoint(heading),
                layer="federal_constitution",
                jurisdiction="United States",
                source_kind="constitution_transcription",
                source_url=self.SOURCE_URL,
                snippet=paragraph[:900],
                captured_at=_captured_now(),
                primary_source_status="National Archives transcription of the U.S. Constitution; compare against authoritative text and relevant case law",
                metadata={
                    "heading": heading,
                    "matched_query_terms": matches,
                    "text_search_only": True,
                    "requested_as_of": request.as_of,
                    "as_of_applied": False,
                },
                warnings=[
                    "This is a transcription/search lead, not constitutional interpretation; identify the exact provision and controlling cases.",
                    *(["The requested as-of date was not used to reconstruct constitutional amendments or historical text."] if request.as_of else []),
                ],
            ))
            if len(hits) >= request.limit:
                break
        return hits


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join(self._parts).strip()))
            self._href = None
            self._parts = []


class WyomingStatutesProvider:
    """Search selected titles from Wyoming Legislature's official PDF edition.

    The statute site publishes separate PDF files, not a public full-text search
    API. For that reason a title number must be supplied explicitly (or present
    in the query); the provider never silently searches a partial title set as if
    it were comprehensive.
    """

    provider_id = "wyoming-statutes"
    INDEX_URL = "https://www.wyoleg.gov/stateStatutes/StatutesDownload"
    OFFICIAL_HOSTS = {"www.wyoleg.gov", "wyoleg.gov"}

    def __init__(
        self,
        title_numbers: Sequence[str] = (),
        *,
        cache_dir: str | Path | None = None,
        transport: HttpTransport | None = None,
        pdf_extractor: Any | None = None,
        cache_ttl_seconds: int = 24 * 60 * 60,
        timeout: float = 40.0,
    ) -> None:
        self.title_numbers = tuple(str(value).strip().removeprefix("title-").removesuffix(".pdf") for value in title_numbers)
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "legal-redteam" / "wyoming-statutes"
        self.transport = transport or UrllibTransport()
        self.pdf_extractor = pdf_extractor or extract_pdf_pages
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout = timeout
        for title in self.title_numbers:
            if not re.fullmatch(r"\d{1,2}(?:\.\d)?|97|99", title):
                raise ValueError(f"Invalid Wyoming statute title number: {title}")

    def _selected_titles(self, query: str) -> list[str]:
        if self.title_numbers:
            return list(dict.fromkeys(self.title_numbers))
        normalized = query.lower()
        if (
            "wyoming constitution" in normalized
            or "wyoming constitutional" in normalized
            or re.search(r"\bwyo\.?\s*const\.?\b", normalized)
        ):
            return ["97"]
        citation_match = re.search(r"\b(?:wyo\.?\s*)?(?:stat(?:ute)?s?\.?\s*)?(?:§\s*)?(\d{1,2}(?:\.\d)?)-\d+-\d+", query, re.I)
        title_match = re.search(r"\btitle\s+(\d{1,2}(?:\.\d)?|97|99)\b", query, re.I)
        if citation_match:
            return [citation_match.group(1)]
        if title_match:
            return [title_match.group(1)]
        raise ProviderError(
            "Wyoming's official statutes are distributed as separate title PDFs. Select titles explicitly "
            "with --wyoming-titles (for example 15,16,18) or include 'Title N' / a Wyo. Stat. section in the query."
        )

    def _index(self) -> tuple[dict[str, dict[str, str]], str]:
        raw = self.transport.get(
            self.INDEX_URL,
            headers={"User-Agent": "CivicLegalResearchRedTeam/0.2 (Wyoming statutes)"},
            timeout=self.timeout,
        )
        try:
            page = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProviderError("Wyoming statute index was not UTF-8 HTML") from exc
        parser = _AnchorParser()
        parser.feed(page)
        titles: dict[str, dict[str, str]] = {}
        for href, label in parser.anchors:
            match = re.search(r"/title(\d{1,2}(?:\.\d)?|97|99)\.pdf(?:$|[?#])", href, re.I)
            if not match:
                continue
            title = match.group(1)
            url = urljoin(self.INDEX_URL, href)
            host = urlparse(url).hostname
            if host not in self.OFFICIAL_HOSTS or not url.lower().endswith(".pdf"):
                continue
            titles[title] = {"url": url, "label": _plain_text(label) or f"Wyoming Title {title}"}
        if not titles:
            raise ProviderError("Could not find official Wyoming title PDF links on the statute download page")
        edition_match = re.search(
            r"(?:as of|exist as of)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
            _plain_text(page),
            re.I,
        )
        edition_note = f"official index describes the edition as of {edition_match.group(1)}" if edition_match else "edition date not parsed from the official index"
        return titles, edition_note

    def _cached_pdf(self, title: str, url: str) -> tuple[bytes, str, str]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        safe_title = title.replace(".", "_")
        pdf_path = self.cache_dir / f"title{safe_title}.pdf"
        sidecar = self.cache_dir / f"title{safe_title}.json"
        if pdf_path.is_file() and sidecar.is_file():
            try:
                metadata = json.loads(sidecar.read_text(encoding="utf-8"))
                age = time.time() - pdf_path.stat().st_mtime
                if metadata.get("source_url") == url and age < self.cache_ttl_seconds:
                    raw = pdf_path.read_bytes()
                    digest = hashlib.sha256(raw).hexdigest()
                    if (
                        raw.startswith(b"%PDF")
                        and metadata.get("sha256") == digest
                        and metadata.get("byte_size") == len(raw)
                    ):
                        return raw, digest, str(metadata.get("captured_at") or "")
            except (OSError, json.JSONDecodeError):
                pass
        raw = self.transport.get(
            url,
            headers={"User-Agent": "CivicLegalResearchRedTeam/0.2 (official Wyoming statute PDF)"},
            timeout=self.timeout,
        )
        if not raw.startswith(b"%PDF"):
            raise ProviderError(f"Official Wyoming title {title} link did not return a PDF")
        digest = hashlib.sha256(raw).hexdigest()
        captured = _captured_now()
        pdf_path.write_bytes(raw)
        sidecar.write_text(json.dumps({
            "source_url": url,
            "captured_at": captured,
            "sha256": digest,
            "byte_size": len(raw),
        }, indent=2) + "\n", encoding="utf-8")
        return raw, digest, captured

    def search(self, request: SearchRequest) -> list[SearchHit]:
        selected = self._selected_titles(request.query)
        index, edition_note = self._index()
        missing = [title for title in selected if title not in index]
        if missing:
            raise ProviderError("Title(s) not found on the official Wyoming download page: " + ", ".join(missing))
        query_terms = [term for term in re.findall(r"[a-z0-9]+", request.query.lower()) if len(term) > 2]
        stopwords = {"the", "and", "for", "with", "from", "that", "this", "what", "does", "title", "wyoming", "statute", "statutes"}
        query_terms = [term for term in query_terms if term not in stopwords]
        query_terms = list(dict.fromkeys(query_terms))
        hits: list[SearchHit] = []

        for title_number in selected:
            title_info = index[title_number]
            raw, digest, captured = self._cached_pdf(title_number, title_info["url"])
            try:
                pages = self.pdf_extractor(raw)
            except Exception as exc:
                raise ProviderError(
                    f"Could not extract Wyoming Title {title_number} PDF; install pypdf/PyMuPDF: {exc}"
                ) from exc
            current_section: str | None = None
            title_hit_count = 0
            for page_number, page_text in enumerate(pages, start=1):
                paragraphs = re.split(r"\n\s*\n", page_text or "")
                for paragraph in paragraphs:
                    section_match = re.search(
                        r"(?:§|Section)\s*(\d{1,2}(?:\.\d)?-\d+-\d+[A-Za-z]?)",
                        paragraph,
                        re.I,
                    )
                    if section_match:
                        current_section = section_match.group(1)
                    normalized = " ".join(re.findall(r"[a-z0-9]+", paragraph.lower()))
                    matched_terms = [term for term in query_terms if term in normalized]
                    if not matched_terms:
                        continue
                    excerpt = " ".join(paragraph.split())
                    if len(excerpt) > 900:
                        term = matched_terms[0]
                        location = normalized.find(term)
                        start = max(0, location - 320)
                        excerpt = "…" + excerpt[start:start + 850] + "…"
                    if title_number == "97":
                        layer = "state_constitution"
                        const_match = re.search(r"(?:Article|Art\.)\s*(\d+).*?(?:Section|§)\s*(\d+)", paragraph, re.I)
                        citation = (
                            f"Wyo. Const. art. {const_match.group(1)}, § {const_match.group(2)}"
                            if const_match else f"Wyoming Constitution, page {page_number}"
                        )
                    else:
                        layer = "state_statute"
                        citation = f"Wyo. Stat. § {current_section}" if current_section else f"Wyo. Stat., Title {title_number}, page {page_number}"
                    section_key = current_section or f"page-{page_number}-{len(hits) + 1}"
                    hits.append(SearchHit(
                        provider=self.provider_id,
                        record_id=f"wyostat-title-{title_number}-{section_key}-{page_number}",
                        title=title_info["label"],
                        citation=citation,
                        layer=layer,
                        jurisdiction="Wyoming",
                        source_kind="official_statute_pdf" if title_number != "97" else "official_state_constitution_pdf",
                        source_url=title_info["url"],
                        snippet=excerpt,
                        captured_at=captured,
                        content_sha256=digest,
                        primary_source_status="Wyoming Legislature official downloadable statute/constitution PDF; version and amendments still require event-date verification",
                        metadata={
                            "title_number": title_number,
                            "title_label": title_info["label"],
                            "page": page_number,
                            "section": current_section,
                            "edition_note_from_official_index": edition_note,
                            "index_url": self.INDEX_URL,
                            "requested_as_of": request.as_of,
                            "as_of_applied": False,
                            "matched_query_terms": matched_terms,
                            "lexical_match_count": len(matched_terms),
                            "total_query_terms": len(query_terms),
                        },
                        warnings=[
                            "Lexical PDF search is not a complete statutory search; inspect neighboring provisions, definitions, history, and enacted session laws.",
                            "The returned PDF edition may not establish the text effective on a past event date.",
                            *(["The requested as-of date was not used to retrieve a historical Wyoming edition."] if request.as_of else []),
                        ],
                    ))
                    title_hit_count += 1
                    if title_hit_count >= request.limit:
                        break
                if title_hit_count >= request.limit:
                    break
        hits.sort(key=lambda hit: hit.metadata.get("lexical_match_count", 0), reverse=True)
        return hits[:request.limit]


class LocalFolderProvider:
    """Offline search across user-supplied files, including local enacted records."""

    provider_id = "local-folder"

    def __init__(
        self,
        root: str | Path,
        *,
        manifest_path: str | Path | None = None,
        enable_ocr: bool = False,
    ) -> None:
        self.root = Path(root)
        self.enable_ocr = enable_ocr
        self.search_warnings: list[str] = []
        self.manifest: dict[str, dict[str, Any]] = {}
        if not self.root.is_dir():
            raise ValueError(f"Local corpus folder does not exist: {self.root}")
        if manifest_path:
            try:
                data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Could not read local-corpus manifest: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError("Local-corpus manifest must be a JSON object keyed by relative file path")
            for relative_path, metadata in data.items():
                if not isinstance(metadata, dict):
                    raise ValueError(f"Local-corpus manifest entry '{relative_path}' must be an object")
                layer = metadata.get("layer")
                if layer is not None and layer not in AUTHORITY_LAYERS:
                    raise ValueError(f"Local-corpus manifest entry '{relative_path}' has unknown authority layer '{layer}'")
                parsed = Path(str(relative_path))
                if parsed.is_absolute() or ".." in parsed.parts:
                    raise ValueError(f"Local-corpus manifest path must be relative and stay inside the corpus: {relative_path}")
            self.manifest = {str(key): value for key, value in data.items()}

    def search(self, request: SearchRequest) -> list[SearchHit]:
        self.search_warnings = []
        terms = [term for term in re.findall(r"[a-z0-9]+", request.query.lower()) if len(term) > 2]
        terms = list(dict.fromkeys(terms))
        hits: list[SearchHit] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES or path.suffix.lower() == ".json":
                continue
            relative = path.relative_to(self.root).as_posix()
            try:
                case = load_case(path, enable_ocr=self.enable_ocr)
            except (OSError, ValueError) as exc:
                safe_message = str(exc).replace(str(path), relative).replace(str(self.root), "<local corpus>")
                self.search_warnings.append(f"Skipped {relative}: {type(exc).__name__}: {safe_message}")
                continue
            if not case.documents:
                continue
            document = case.documents[0]
            self.search_warnings.extend(
                f"{relative}: {warning}" for warning in document.extraction_warnings
            )
            metadata = self.manifest.get(relative, {})
            for fact in case.facts:
                normalized = " ".join(re.findall(r"[a-z0-9]+", fact.statement.lower()))
                matches = [term for term in terms if term in normalized]
                if not matches:
                    continue
                hits.append(SearchHit(
                    provider=self.provider_id,
                    record_id=f"local:{relative}:{fact.id}",
                    title=str(metadata.get("title") or path.name),
                    citation=_optional_manifest_text(metadata.get("citation")),
                    layer=str(metadata.get("layer") or "other"),
                    jurisdiction=_optional_manifest_text(metadata.get("jurisdiction")),
                    source_kind=str(metadata.get("source_kind") or document.kind),
                    source_url=_optional_manifest_text(metadata.get("official_url")),
                    snippet=fact.statement[:900],
                    captured_at=document.captured_at,
                    content_sha256=document.content_sha256,
                    primary_source_status=str(metadata.get("primary_source_status") or "unknown_as_entered"),
                    metadata={
                        "relative_path": relative,
                        "source_document_id": document.id,
                        "fact_id": fact.id,
                        "locator": fact.locator,
                        "extraction_method": fact.extraction_method,
                        "extraction_confidence": fact.extraction_confidence,
                        "matched_query_terms": matches,
                        "manifest_entry_present": bool(metadata),
                        "requested_as_of": request.as_of,
                        "as_of_applied": False,
                    },
                    warnings=[
                        "Local-file contents and any manifest assertions are user-supplied; verify official enactment, text, version, and authority status.",
                        *(["The requested as-of date was not used to select a historical local-corpus version."] if request.as_of else []),
                    ],
                ))
        hits.sort(key=lambda hit: len(hit.metadata.get("matched_query_terms", [])), reverse=True)
        return hits[:request.limit]


def _optional_manifest_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class CourtListenerProvider:
    """Case-law discovery connector; results are not official opinions or a citator judgment."""

    provider_id = "courtlistener"
    SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"

    def __init__(
        self,
        token: str | None = None,
        *,
        transport: HttpTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.token = token
        self.transport = transport or UrllibTransport()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "CivicLegalResearchRedTeam/0.2 (case-law discovery)"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def _search_api(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not self.token:
            raise ProviderError(
                "CourtListener API token is not configured. Set LEGAL_REDTEAM_COURTLISTENER_TOKEN; "
                "do not place credentials in a case packet or command history."
            )
        payload = _get_json(
            self.transport,
            self.SEARCH_URL,
            params={"q": query, "type": "o", "order_by": "score desc", "page_size": min(limit, 100)},
            headers=self._headers(),
            timeout=self.timeout,
        )
        records = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            raise ProviderError("CourtListener search response did not contain a results array")
        return records[:limit]

    @staticmethod
    def _hit(record: dict[str, Any], index: int, requested_as_of: str | None = None) -> SearchHit:
        citations = record.get("citations") or []
        if isinstance(citations, str):
            citations = [citations]
        citation = "; ".join(str(item) for item in citations if item) or _optional_manifest_text(record.get("citation"))
        court_id = str(record.get("court_id") or "")
        court_jurisdiction = str(record.get("court_jurisdiction") or "")
        if court_jurisdiction.upper() == "F":
            layer = "federal_case"
        elif court_jurisdiction.upper() in {"S", "STATE"}:
            layer = "state_case"
        else:
            layer = "other"
        url = record.get("absolute_url") or record.get("source_url")
        if isinstance(url, str) and url.startswith("/"):
            url = urljoin("https://www.courtlistener.com", url)
        return SearchHit(
            provider="courtlistener",
            record_id=str(record.get("cluster_id") or record.get("id") or index),
            title=_optional_manifest_text(record.get("case_name") or record.get("caseName")) or "Untitled opinion record",
            citation=citation,
            layer=layer,
            jurisdiction=_optional_manifest_text(record.get("court")),
            source_kind="case_law_search_result",
            source_url=url,
            snippet=_plain_text(record.get("snippet") or record.get("opinion_snippet")),
            decision_or_enactment_date=_optional_manifest_text(record.get("date_filed") or record.get("dateFiled")),
            captured_at=_captured_now(),
            primary_source_status="secondary case-law index; verify opinion, docket, reporter citation, and subsequent history in official/primary sources",
            metadata={
                "cluster_id": record.get("cluster_id"),
                "court_id": court_id,
                "court": record.get("court"),
                "court_jurisdiction": court_jurisdiction,
                "docket_number": record.get("docket_number") or record.get("docketNumber"),
                "docket_url": record.get("docket_url"),
                "docket_id": record.get("docket_id"),
                "citations": citations,
                "reporter_citation": record.get("reporter_citation") or (citations[0] if citations else None),
                "precedential_status": record.get("status") or record.get("precedential_status"),
                "cite_count": record.get("cite_count") or record.get("citeCount"),
                "opinions": record.get("opinions", []),
                "court_document_url_as_reported": record.get("court_document_url"),
                "requested_as_of": requested_as_of,
                "as_of_applied": False,
                "source_url_is_official": False,
            },
            warnings=[
                "Search index/snippet is a discovery lead, not the official opinion or verified holding.",
                "No precedential status, citation, or subsequent treatment is independently confirmed by this connector.",
                *(["The requested as-of date was not used to filter or reconstruct historical case-law status."] if requested_as_of else []),
            ],
        )

    def search(self, request: SearchRequest) -> list[SearchHit]:
        records = self._search_api(request.query, request.limit)
        return [
            self._hit(record, index, request.as_of)
            for index, record in enumerate(records, start=1)
        ]

    def search_citing(self, cluster_id: int | str, *, limit: int = 100) -> list[SearchHit]:
        """Find indexed opinions whose text/citation graph reports citing a cluster."""
        records = self._search_api(f"cites:{cluster_id}", min(limit, 100))
        return [self._hit(record, index) for index, record in enumerate(records, start=1)]


def default_provider(provider_id: str, **options: Any) -> LegalResearchProvider:
    """Construct a provider by registered name, supporting future plugin adapters."""
    constructors = {
        "ecfr": EcfrProvider,
        "federal-register": FederalRegisterProvider,
        "wyoming-statutes": WyomingStatutesProvider,
        "courtlistener": CourtListenerProvider,
        "local-folder": LocalFolderProvider,
        "us-constitution": NationalArchivesConstitutionProvider,
    }
    if provider_id == "uscode":
        from .providers_uscode import UsCodeProvider
        constructor = UsCodeProvider
    else:
        try:
            constructor = constructors[provider_id]
        except KeyError as exc:
            names = sorted([*constructors, "uscode"])
            raise ValueError(f"Unknown provider '{provider_id}'. Registered providers: {', '.join(names)}") from exc
    return constructor(**options)
