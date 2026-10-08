"""Official OLRC U.S. Code section lookup by citation."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode

from .providers import HttpTransport, ProviderError, SearchHit, SearchRequest, UrllibTransport, _captured_now


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._blocked += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._blocked:
            self._blocked -= 1
        elif tag.lower() in {"p", "div", "h1", "h2", "h3", "li", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._blocked and data.strip():
            self.parts.append(data.strip())


class UsCodeProvider:
    """Retrieve an exact section from the official OLRC U.S. Code site.

    OLRC does not expose a documented per-section JSON search API. This
    connector therefore performs exact citation lookups only; it does not
    claim to search the entire Code by arbitrary subject terms.
    """

    provider_id = "uscode"
    BASE_URL = "https://uscode.house.gov/view.xhtml"

    def __init__(
        self,
        *,
        edition: str = "prelim",
        transport: HttpTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not re.fullmatch(r"prelim|(?:19|20)\d{2}", edition):
            raise ValueError("U.S. Code edition must be 'prelim' or a four-digit year")
        self.edition = edition
        self.transport = transport or UrllibTransport()
        self.timeout = timeout

    @staticmethod
    def _parse_citation(query: str) -> tuple[str, str] | None:
        patterns = (
            r"\b(?:title\s*)?(\d{1,2})\s+U\.?\s*S\.?\s*C\.?\s*§{1,2}\s*([0-9A-Za-z.-]+)",
            r"\btitle\s+(\d{1,2})\s*(?:,|\s)+section\s+([0-9A-Za-z.-]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, query, re.I)
            if match:
                return match.group(1), match.group(2)
        return None

    def search(self, request: SearchRequest) -> list[SearchHit]:
        parsed = self._parse_citation(request.query)
        if not parsed:
            raise ProviderError(
                "The official OLRC connector supports exact citations only; query with a form such as '42 U.S.C. § 1983'."
            )
        title, section = parsed
        granule_id = f"USC-{self.edition}-title{title}-section{section}"
        query = urlencode({"req": f"granuleid:{granule_id}", "num": "0", "edition": self.edition})
        url = f"{self.BASE_URL}?{query}"
        raw = self.transport.get(
            url,
            headers={"User-Agent": "CivicLegalResearchRedTeam/0.2 (official OLRC U.S. Code lookup)"},
            timeout=self.timeout,
        )
        try:
            page = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProviderError("OLRC returned a response that was not UTF-8 HTML") from exc
        collector = _TextCollector()
        collector.feed(page)
        text = " ".join(" ".join(collector.parts).split())
        if not text or "under maintenance" in text.lower() or "not found" in text.lower():
            raise ProviderError("The official OLRC page did not return the requested Code section (site may be unavailable or citation/edition may not exist)")
        canonical = f"https://uscode.house.gov/view.xhtml?{query}"
        citation = f"{title} U.S.C. § {section}"
        return [SearchHit(
            provider=self.provider_id,
            record_id=granule_id,
            title=f"Title {title}, section {section}",
            citation=citation,
            layer="federal_statute",
            jurisdiction="United States",
            source_kind="official_us_code_section",
            source_url=canonical,
            snippet=text[:1200],
            captured_at=_captured_now(),
            primary_source_status="Official OLRC U.S. Code page; confirm enactment/classification, currency, and event-date effect",
            metadata={
                "title_number": title,
                "section": section,
                "edition": self.edition,
                "granule_id": granule_id,
                "official_source": "Office of the Law Revision Counsel, U.S. House of Representatives",
                "section_lookup_method": "exact_citation",
                "requested_as_of": request.as_of,
                "as_of_applied": False,
            },
            warnings=[
                "A preliminary/current Code page does not by itself reconstruct all event-date amendments; check the enacted law and official currency/classification tables.",
                "The connector looks up one exact citation and does not search the complete U.S. Code by arbitrary query terms.",
                *(["The requested as-of date was not used to select a historical Code edition."] if request.as_of else []),
            ],
        )]
