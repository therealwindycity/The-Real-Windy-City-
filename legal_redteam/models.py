"""Input models for the legal research red-team prototype.

The models preserve source metadata and distinguish factual assertions from
legal authorities. User-entered review labels are never treated as findings by
the engine.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

FACT_STATUSES = {
    "unclassified",
    "unverified",
    "alleged",
    "disputed",
    "undisputed",
    "adjudicated",
    "inference",
}

AUTHORITY_LAYERS = {
    "federal_constitution",
    "federal_statute",
    "federal_regulation",
    "federal_case",
    "state_constitution",
    "state_statute",
    "state_regulation",
    "state_case",
    "county_code",
    "municipal_code",
    "local_charter_or_resolution",
    "local_administrative_decision",
    "court_rule",
    "treaty",
    "customary_international_law",
    "international_decision",
    "international_soft_law",
    "tribal_law",
    "foreign_law",
    "interstate_compact",
    "agency_guidance",
    "agency_record",
    "legislative_history",
    "contract_or_private_rule",
    "secondary_source",
    "other",
}

BINDINGNESS_STATUSES = {
    "unknown",
    "controlling",
    "binding",
    "persuasive",
    "nonbinding",
}

AUTHORITY_TREATMENTS = {
    "unknown",
    "supports",
    "contrary",
    "distinguishes",
    "neutral",
}

VERIFICATION_CHECK_STATUSES = {
    "not_checked",
    "checked",
    "failed",
    "unresolved",
    "not_applicable",
}

EVIDENCE_STRENGTHS = {"not_assessed", "strong", "moderate", "weak", "contested"}
EVIDENCE_AUTHENTICITY = {"not_assessed", "authenticated", "contested", "unknown"}
EVIDENCE_DIRECTNESS = {
    "not_assessed", "firsthand", "documentary", "hearsay_or_secondhand",
    "inference", "expert", "mixed", "unknown",
}
EVIDENCE_CORROBORATION = {
    "not_assessed", "corroborated", "single_source", "contradicted", "unknown",
}
LINK_FROM_TYPES = {"fact", "authority"}
LINK_TO_TYPES = {"issue", "element", "fact"}
LINK_RELATIONS = {
    "supports", "undercuts", "distinguishes", "corroborates", "contradicts",
    "addresses", "analogizes",
}
LINK_REVIEW_STATUSES = {"proposed", "reviewed", "rejected"}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"'{field_name}' must be a list of strings")
    return [str(item).strip() for item in value if str(item).strip()]


def _sha256(value: Any, field_name: str, index: int | None = None) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    if not re.fullmatch(r"[a-fA-F0-9]{64}", text):
        label = f"[{index}]" if index is not None else ""
        raise ValueError(f"{field_name}{label} must be a 64-character SHA-256 hex digest")
    return text.lower()


@dataclass(slots=True)
class SourceDocument:
    id: str
    title: str
    kind: str = "unknown"
    text: str = ""
    url: str | None = None
    captured_at: str | None = None
    publisher: str | None = None
    primary_source_status: str = "unknown"
    original_filename: str | None = None
    archived_path: str | None = None
    content_sha256: str | None = None
    byte_size: int | None = None
    extraction_method: str = "not_recorded"
    extraction_confidence: str = "unassessed"
    extraction_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 1) -> "SourceDocument":
        if not isinstance(data, dict):
            raise ValueError(f"documents[{index - 1}] must be an object")
        raw_size = data.get("byte_size")
        if raw_size is None:
            byte_size = None
        else:
            try:
                byte_size = int(raw_size)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"documents[{index - 1}].byte_size must be a non-negative integer") from exc
            if byte_size < 0:
                raise ValueError(f"documents[{index - 1}].byte_size must be a non-negative integer")
        return cls(
            id=_optional_text(data.get("id")) or f"source-{index}",
            title=_optional_text(data.get("title")) or f"Untitled source {index}",
            kind=_optional_text(data.get("kind")) or "unknown",
            text=str(data.get("text") or ""),
            url=_optional_text(data.get("url")),
            captured_at=_optional_text(data.get("captured_at")),
            publisher=_optional_text(data.get("publisher")),
            primary_source_status=_optional_text(data.get("primary_source_status")) or "unknown",
            original_filename=_optional_text(data.get("original_filename")),
            archived_path=_optional_text(data.get("archived_path")),
            content_sha256=_sha256(data.get("content_sha256"), f"documents[{index - 1}].content_sha256"),
            byte_size=byte_size,
            extraction_method=_optional_text(data.get("extraction_method")) or "not_recorded",
            extraction_confidence=_optional_text(data.get("extraction_confidence")) or "unassessed",
            extraction_warnings=_string_list(data.get("extraction_warnings"), f"documents[{index - 1}].extraction_warnings"),
        )


@dataclass(slots=True)
class EvidenceAssessment:
    """Qualitative evidence review entered by a person; never calculated by the engine."""

    strength: str = "not_assessed"
    authenticity: str = "not_assessed"
    directness: str = "not_assessed"
    corroboration: str = "not_assessed"
    rationale: str | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None
    limitations: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any, index: int = 1) -> "EvidenceAssessment":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"facts[{index - 1}].evidence_assessment must be an object")
        values = {
            "strength": (_optional_text(data.get("strength")) or "not_assessed", EVIDENCE_STRENGTHS),
            "authenticity": (_optional_text(data.get("authenticity")) or "not_assessed", EVIDENCE_AUTHENTICITY),
            "directness": (_optional_text(data.get("directness")) or "not_assessed", EVIDENCE_DIRECTNESS),
            "corroboration": (_optional_text(data.get("corroboration")) or "not_assessed", EVIDENCE_CORROBORATION),
        }
        for name, (value, allowed) in values.items():
            if value not in allowed:
                raise ValueError(
                    f"facts[{index - 1}].evidence_assessment.{name} must be one of: "
                    + ", ".join(sorted(allowed))
                )
        rationale = _optional_text(data.get("rationale"))
        reviewer = _optional_text(data.get("reviewer"))
        reviewed_at = _optional_text(data.get("reviewed_at"))
        limits = _string_list(data.get("limitations"), f"facts[{index - 1}].evidence_assessment.limitations")
        assessed = any(value != "not_assessed" for value, _ in values.values())
        if assessed and (not reviewer or not rationale):
            raise ValueError(
                f"facts[{index - 1}].evidence_assessment needs reviewer and rationale when a qualitative assessment is entered"
            )
        return cls(
            strength=values["strength"][0],
            authenticity=values["authenticity"][0],
            directness=values["directness"][0],
            corroboration=values["corroboration"][0],
            rationale=rationale,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            limitations=limits,
        )


@dataclass(slots=True)
class Fact:
    id: str
    statement: str
    status: str = "unclassified"
    source_id: str | None = None
    locator: str | None = None
    event_date: str | None = None
    issue_tags: list[str] = field(default_factory=list)
    source_quote: str | None = None
    extraction_method: str | None = None
    extraction_confidence: str = "unassessed"
    evidence_assessment: EvidenceAssessment = field(default_factory=EvidenceAssessment)

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 1) -> "Fact":
        if not isinstance(data, dict):
            raise ValueError(f"facts[{index - 1}] must be an object")
        statement = _optional_text(data.get("statement") or data.get("text"))
        if not statement:
            raise ValueError(f"facts[{index - 1}] needs a non-empty 'statement'")
        status = _optional_text(data.get("status")) or "unclassified"
        if status not in FACT_STATUSES:
            allowed = ", ".join(sorted(FACT_STATUSES))
            raise ValueError(f"facts[{index - 1}].status must be one of: {allowed}")
        return cls(
            id=_optional_text(data.get("id")) or f"fact-{index}",
            statement=statement,
            status=status,
            source_id=_optional_text(data.get("source_id")),
            locator=_optional_text(data.get("locator")),
            event_date=_optional_text(data.get("event_date") or data.get("date")),
            issue_tags=_string_list(data.get("issue_tags"), f"facts[{index - 1}].issue_tags"),
            source_quote=_optional_text(data.get("source_quote")),
            extraction_method=_optional_text(data.get("extraction_method")),
            extraction_confidence=_optional_text(data.get("extraction_confidence")) or "unassessed",
            evidence_assessment=EvidenceAssessment.from_dict(data.get("evidence_assessment"), index),
        )


@dataclass(slots=True)
class ResearchLink:
    """A proposed or human-reviewed edge in the element/fact/authority graph."""

    id: str
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    relation: str
    review_status: str = "proposed"
    rationale: str | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 1) -> "ResearchLink":
        if not isinstance(data, dict):
            raise ValueError(f"research_links[{index - 1}] must be an object")
        from_type = _optional_text(data.get("from_type")) or ""
        to_type = _optional_text(data.get("to_type")) or ""
        relation = _optional_text(data.get("relation")) or ""
        status = _optional_text(data.get("review_status")) or "proposed"
        if from_type not in LINK_FROM_TYPES:
            raise ValueError(f"research_links[{index - 1}].from_type must be one of: " + ", ".join(sorted(LINK_FROM_TYPES)))
        if to_type not in LINK_TO_TYPES:
            raise ValueError(f"research_links[{index - 1}].to_type must be one of: " + ", ".join(sorted(LINK_TO_TYPES)))
        if relation not in LINK_RELATIONS:
            raise ValueError(f"research_links[{index - 1}].relation must be one of: " + ", ".join(sorted(LINK_RELATIONS)))
        if status not in LINK_REVIEW_STATUSES:
            raise ValueError(f"research_links[{index - 1}].review_status must be one of: " + ", ".join(sorted(LINK_REVIEW_STATUSES)))
        from_id = _optional_text(data.get("from_id"))
        to_id = _optional_text(data.get("to_id"))
        if not from_id or not to_id:
            raise ValueError(f"research_links[{index - 1}] needs non-empty from_id and to_id")
        rationale = _optional_text(data.get("rationale"))
        reviewer = _optional_text(data.get("reviewer"))
        if status in {"reviewed", "rejected"} and (not reviewer or not rationale):
            raise ValueError(
                f"research_links[{index - 1}] needs reviewer and rationale when review_status is '{status}'"
            )
        return cls(
            id=_optional_text(data.get("id")) or f"link-{index}",
            from_type=from_type,
            from_id=from_id,
            to_type=to_type,
            to_id=to_id,
            relation=relation,
            review_status=status,
            rationale=rationale,
            reviewer=reviewer,
            reviewed_at=_optional_text(data.get("reviewed_at")),
        )


@dataclass(slots=True)
class Authority:
    id: str
    citation: str
    layer: str = "other"
    jurisdiction: str | None = None
    court_or_body: str | None = None
    bindingness: str = "unknown"
    treatment: str = "unknown"
    issue_tags: list[str] = field(default_factory=list)
    proposition: str | None = None
    source_excerpt: str | None = None
    pinpoint: str | None = None
    official_url: str | None = None
    official_opinion_url: str | None = None
    docket_url: str | None = None
    docket_number: str | None = None
    reporter_citation: str | None = None
    precedential_status: str | None = None
    source_capture_sha256: str | None = None
    captured_at: str | None = None
    decision_or_enactment_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    citation_check: str = "not_checked"
    primary_text_check: str = "not_checked"
    currentness_check: str = "not_checked"
    subsequent_history_check: str = "not_checked"

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 1) -> "Authority":
        if not isinstance(data, dict):
            raise ValueError(f"authorities[{index - 1}] must be an object")
        citation = _optional_text(data.get("citation"))
        if not citation:
            raise ValueError(f"authorities[{index - 1}] needs a non-empty 'citation'")
        layer = _optional_text(data.get("layer")) or "other"
        if layer not in AUTHORITY_LAYERS:
            allowed = ", ".join(sorted(AUTHORITY_LAYERS))
            raise ValueError(f"authorities[{index - 1}].layer must be one of: {allowed}")
        bindingness = _optional_text(data.get("bindingness")) or "unknown"
        if bindingness not in BINDINGNESS_STATUSES:
            allowed = ", ".join(sorted(BINDINGNESS_STATUSES))
            raise ValueError(f"authorities[{index - 1}].bindingness must be one of: {allowed}")
        treatment = _optional_text(data.get("treatment")) or "unknown"
        if treatment not in AUTHORITY_TREATMENTS:
            allowed = ", ".join(sorted(AUTHORITY_TREATMENTS))
            raise ValueError(f"authorities[{index - 1}].treatment must be one of: {allowed}")
        raw_checks = data.get("verification_checks") or {}
        if not isinstance(raw_checks, dict):
            raise ValueError(f"authorities[{index - 1}].verification_checks must be an object")
        # Compatibility for early prototype packets: the legacy stage expands
        # into independent checks, but new packets should use verification_checks.
        legacy_stage = _optional_text(data.get("verification_status")) or "unverified"
        legacy_checks = {
            "unverified": ("not_checked", "not_checked", "not_checked", "not_checked"),
            "citation_checked": ("checked", "not_checked", "not_checked", "not_checked"),
            "primary_text_checked": ("checked", "checked", "not_checked", "not_checked"),
            "currentness_checked": ("checked", "checked", "checked", "not_checked"),
            "treatment_checked": ("checked", "checked", "checked", "checked"),
        }
        if legacy_stage not in legacy_checks:
            raise ValueError(f"authorities[{index - 1}].verification_status is not a recognized legacy stage")
        defaults = dict(zip(
            ("citation", "primary_text", "currentness", "subsequent_history"),
            legacy_checks[legacy_stage],
        ))
        parsed_checks: dict[str, str] = {}
        for check_name in ("citation", "primary_text", "currentness", "subsequent_history"):
            value = _optional_text(raw_checks.get(check_name) or data.get(f"{check_name}_check")) or defaults[check_name]
            if value not in VERIFICATION_CHECK_STATUSES:
                allowed = ", ".join(sorted(VERIFICATION_CHECK_STATUSES))
                raise ValueError(
                    f"authorities[{index - 1}].verification_checks.{check_name} must be one of: {allowed}"
                )
            parsed_checks[check_name] = value
        return cls(
            id=_optional_text(data.get("id")) or f"authority-{index}",
            citation=citation,
            layer=layer,
            jurisdiction=_optional_text(data.get("jurisdiction")),
            court_or_body=_optional_text(data.get("court_or_body") or data.get("court")),
            bindingness=bindingness,
            treatment=treatment,
            issue_tags=_string_list(data.get("issue_tags"), f"authorities[{index - 1}].issue_tags"),
            proposition=_optional_text(data.get("proposition") or data.get("holding")),
            source_excerpt=_optional_text(data.get("source_excerpt")),
            pinpoint=_optional_text(data.get("pinpoint")),
            official_url=_optional_text(data.get("official_url")),
            official_opinion_url=_optional_text(data.get("official_opinion_url")),
            docket_url=_optional_text(data.get("docket_url")),
            docket_number=_optional_text(data.get("docket_number")),
            reporter_citation=_optional_text(data.get("reporter_citation")),
            precedential_status=_optional_text(data.get("precedential_status")),
            source_capture_sha256=_sha256(data.get("source_capture_sha256"), f"authorities[{index - 1}].source_capture_sha256"),
            captured_at=_optional_text(data.get("captured_at")),
            decision_or_enactment_date=_optional_text(
                data.get("decision_or_enactment_date") or data.get("decision_date")
            ),
            effective_from=_optional_text(data.get("effective_from")),
            effective_to=_optional_text(data.get("effective_to")),
            citation_check=parsed_checks["citation"],
            primary_text_check=parsed_checks["primary_text"],
            currentness_check=parsed_checks["currentness"],
            subsequent_history_check=parsed_checks["subsequent_history"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CaseRecord:
    case_id: str
    title: str
    jurisdiction: dict[str, str | None] = field(default_factory=dict)
    forum: dict[str, str | None] = field(default_factory=dict)
    as_of: str | None = None
    procedural_posture: str | None = None
    questions: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    documents: list[SourceDocument] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    authorities: list[Authority] = field(default_factory=list)
    research_links: list[ResearchLink] = field(default_factory=list)
    narrative_text: str = ""
    ingestion_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseRecord":
        if not isinstance(data, dict):
            raise ValueError("Case JSON must contain one top-level object")
        raw_jurisdiction = data.get("jurisdiction") or {}
        raw_forum = data.get("forum") or {}
        if not isinstance(raw_jurisdiction, dict):
            raise ValueError("'jurisdiction' must be an object")
        if not isinstance(raw_forum, dict):
            raise ValueError("'forum' must be an object")
        for list_name in ("documents", "facts", "authorities"):
            if not isinstance(data.get(list_name, []), list):
                raise ValueError(f"'{list_name}' must be a list")
        raw_links = data.get("research_links", data.get("links", []))
        if raw_links is None:
            raw_links = []
        if not isinstance(raw_links, list):
            raise ValueError("'research_links' must be a list")

        jurisdiction = {
            str(key): _optional_text(value)
            for key, value in raw_jurisdiction.items()
        }
        forum = {str(key): _optional_text(value) for key, value in raw_forum.items()}
        return cls(
            case_id=_optional_text(data.get("case_id")) or "ingested-case",
            title=_optional_text(data.get("title")) or "Untitled legal matter",
            jurisdiction=jurisdiction,
            forum=forum,
            as_of=_optional_text(data.get("as_of")),
            procedural_posture=_optional_text(data.get("procedural_posture")),
            questions=_string_list(data.get("questions"), "questions"),
            actors=_string_list(data.get("actors"), "actors"),
            documents=[
                SourceDocument.from_dict(document, index)
                for index, document in enumerate(data.get("documents", []), start=1)
            ],
            facts=[Fact.from_dict(fact, index) for index, fact in enumerate(data.get("facts", []), start=1)],
            authorities=[
                Authority.from_dict(authority, index)
                for index, authority in enumerate(data.get("authorities", []), start=1)
            ],
            research_links=[
                ResearchLink.from_dict(link, index)
                for index, link in enumerate(raw_links, start=1)
            ],
            narrative_text=str(data.get("narrative_text") or ""),
            ingestion_warnings=_string_list(data.get("ingestion_warnings"), "ingestion_warnings"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "jurisdiction": self.jurisdiction,
            "forum": self.forum,
            "as_of": self.as_of,
            "procedural_posture": self.procedural_posture,
            "questions": self.questions,
            "actors": self.actors,
            "documents": [asdict(document) for document in self.documents],
            "facts": [asdict(fact) for fact in self.facts],
            "authorities": [authority.to_dict() for authority in self.authorities],
            "research_links": [asdict(link) for link in self.research_links],
            "narrative_text": self.narrative_text,
            "ingestion_warnings": self.ingestion_warnings,
        }
