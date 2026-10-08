"""Potential negative-treatment search with mandatory human verification.

This is a retrieval aid, not a commercial citator and not a treatment judgment.
No authority's verification state is changed automatically.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import Authority, CaseRecord
from .providers import CourtListenerProvider, SearchHit, SearchRequest


_NEGATIVE_TREATMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("overruled", re.compile(r"\b(?:overruled|overruling|overrule)\b", re.I)),
    ("abrogated", re.compile(r"\b(?:abrogated|abrogating|abrogate)\b", re.I)),
    ("vacated", re.compile(r"\b(?:vacated|vacating|vacate)\b", re.I)),
    ("reversed", re.compile(r"\b(?:reversed|reversing|reverse)\b", re.I)),
    ("disapproved", re.compile(r"\b(?:disapproved|disapproving|disapprove)\b", re.I)),
    ("superseded", re.compile(r"\b(?:superseded|superseding|supersede)\b", re.I)),
    ("no_longer_good_law", re.compile(r"\bno longer (?:good law|valid|controlling)\b", re.I)),
    ("limited", re.compile(r"\b(?:limited|limiting|limits)\b", re.I)),
    ("questioned", re.compile(r"\b(?:questioned|questioning)\b", re.I)),
    ("distinguished", re.compile(r"\b(?:distinguished|distinguishing)\b", re.I)),
)


class CitingCaseProvider(Protocol):
    provider_id: str

    def search(self, request: SearchRequest) -> list[SearchHit]:
        ...

    def search_citing(self, cluster_id: int | str, *, limit: int = 100) -> list[SearchHit]:
        ...


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _negative_terms(text: str) -> list[str]:
    return [label for label, pattern in _NEGATIVE_TREATMENT_PATTERNS if pattern.search(text or "")]


def _case_authorities(case: CaseRecord) -> list[Authority]:
    return [authority for authority in case.authorities if authority.layer in {"federal_case", "state_case"}]


def check_case_authority(
    authority: Authority,
    provider: CitingCaseProvider,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Search an aggregator's citation graph; never mark the authority checked."""
    base: dict[str, Any] = {
        "authority_id": authority.id,
        "citation_as_entered": authority.citation,
        "provider": provider.provider_id,
        "checked_at": _now(),
        "manual_review_required": True,
        "subsequent_history_check_as_entered": authority.subsequent_history_check,
        "status": "unresolved",
        "candidate_negative_treatment_hits": [],
        "retrieved_citing_opinion_count": 0,
    }
    try:
        lookup_hits = provider.search(SearchRequest(query=f'"{authority.citation}"', limit=10))
    except Exception as exc:
        base["status"] = "provider_error"
        base["provider_error"] = f"{type(exc).__name__}: {exc}"
        base["coverage_note"] = "The search failed; no conclusion about subsequent history is possible."
        return base

    matched = [
        hit for hit in lookup_hits
        if authority.citation.casefold() in (hit.citation or "").casefold()
        or authority.citation.casefold() in hit.title.casefold()
    ]
    lookup = matched[0] if matched else (lookup_hits[0] if lookup_hits else None)
    if lookup is None:
        base["status"] = "citation_not_resolved_by_provider"
        base["coverage_note"] = (
            "No indexed match was returned. The citation may be unindexed or formatted differently; "
            "this is not a negative-history result."
        )
        return base
    cluster_id = lookup.metadata.get("cluster_id")
    base["resolved_case_record"] = {
        "title": lookup.title,
        "citation": lookup.citation,
        "provider_record_id": lookup.record_id,
        "cluster_id": cluster_id,
        "decision_date": lookup.decision_or_enactment_date,
        "index_url": lookup.source_url,
        "court_document_url_as_reported": lookup.metadata.get("court_document_url_as_reported"),
        "docket_number": lookup.metadata.get("docket_number"),
        "docket_url_as_reported": lookup.metadata.get("docket_url"),
        "precedential_status_as_indexed": lookup.metadata.get("precedential_status"),
        "source_capture_time": lookup.captured_at,
        "source_capture_sha256": lookup.content_sha256,
        "primary_source_status": lookup.primary_source_status,
    }
    if cluster_id is None:
        base["status"] = "provider_record_has_no_citation_graph_id"
        base["coverage_note"] = "A possible case record was found, but the provider supplied no citation-graph identifier."
        return base

    try:
        citing_hits = provider.search_citing(cluster_id, limit=limit)
    except Exception as exc:
        base["status"] = "citing_search_error"
        base["provider_error"] = f"{type(exc).__name__}: {exc}"
        base["coverage_note"] = "The citing-opinion search failed; no conclusion about subsequent history is possible."
        return base

    base["retrieved_citing_opinion_count"] = len(citing_hits)
    candidates: list[dict[str, Any]] = []
    for hit in citing_hits:
        excerpt = hit.snippet or ""
        signals = _negative_terms(excerpt)
        if not signals:
            continue
        candidates.append({
            "case_name": hit.title,
            "citation": hit.citation,
            "decision_date": hit.decision_or_enactment_date,
            "provider_record_id": hit.record_id,
            "cluster_id": hit.metadata.get("cluster_id"),
            "index_url": hit.source_url,
            "court_document_url_as_reported": hit.metadata.get("court_document_url_as_reported"),
            "docket_number": hit.metadata.get("docket_number"),
            "docket_url_as_reported": hit.metadata.get("docket_url"),
            "possible_treatment_terms": signals,
            "excerpt": excerpt,
            "primary_source_status": hit.primary_source_status,
            "review_status": "unreviewed_candidate",
        })
    base["candidate_negative_treatment_hits"] = candidates
    base["status"] = "potential_negative_treatment_candidates_found" if candidates else "no_negative_terms_in_retrieved_snippets"
    base["coverage_note"] = (
        "A phrase hit can discuss another authority, quote a litigant, or describe a different procedural event. "
        "Open the official opinion and inspect the exact passage, target authority, court, and subsequent history."
        if candidates else
        "No configured negative-treatment phrase appeared in the retrieved snippets. This is not a clean bill of health: "
        "coverage, indexing, opinion text, and unreturned pages may be incomplete."
    )
    base["automatic_verification_change"] = "none"
    return base


def check_case_authorities(
    case: CaseRecord,
    provider: CitingCaseProvider | None = None,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Run a case-law subsequent-treatment discovery check for entered cases."""
    client = provider or CourtListenerProvider()
    records = [check_case_authority(authority, client, limit=limit) for authority in _case_authorities(case)]
    return {
        "case_id": case.case_id,
        "provider": client.provider_id,
        "run_at": _now(),
        "citator_status": "discovery_search_only_human_review_required",
        "authority_checks": records,
        "note": (
            "This is not a citator guarantee. No citation, primary-text, currentness, bindingness, or subsequent-history "
            "field in the case packet is changed automatically. Verify candidate opinions from official sources."
        ),
    }
