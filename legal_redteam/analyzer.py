"""Deterministic, auditable red-team issue spotting for legal matter packets.

This is intentionally not a legal-outcome predictor or a citation generator. It
surfaces research questions from visible text signals and makes uncertainty
explicit so a researcher can verify, reject, or extend each lead.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict
from datetime import date
from typing import Any, Sequence

from .catalog import GLOBAL_RED_TEAM_CHECKS, NOVELTY_PROTOCOL, IssueRule
from .issue_packs import BUILTIN_ISSUE_RULES
from .models import AUTHORITY_LAYERS, Authority, CaseRecord, Fact, ResearchLink

ENGINE_VERSION = "0.2.0"


_REVIEW_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "false_dichotomy_or_pressure",
        re.compile(r"\b(checkmate|no escape clause|yes or no|force\w*.{0,60}admit)\b", re.I | re.S),
        "Replace forced binary framing with a neutral, answerable factual question; legal elements, exceptions, and alternative explanations may not be binary.",
    ),
    (
        "absolute_or_certainty_claim",
        re.compile(r"\b(automatic(?:ally)?|always|never|undeniabl\w*|conclusive(?:ly)?|certainly|zero[- ]day)\b", re.I),
        "State the exact source and conditions for the absolute claim, check exceptions, and record what evidence could disconfirm it.",
    ),
    (
        "motive_or_intent_inference",
        re.compile(r"\b(designed to|to shield|to avoid|deliberate\w*|bad faith|conspiracy|cover[- ]up|intentional\w*)\b", re.I),
        "Treat motive as an inference unless supported; identify the underlying documents, actor, timing, alternative explanations, and applicable intent element.",
    ),
    (
        "conclusory_legal_label",
        re.compile(r"\b(unconstitutional|illegal|unlawful|violates?|liable|fraudulent|constitutes? a violation)\b", re.I),
        "Convert the label into a testable proposition: identify the rule, elements, forum, facts for each element, contrary authority, and remedy.",
    ),
)


_PROCEDURAL_GATE_CHECKS: tuple[str, ...] = (
    "Confirm subject-matter and personal jurisdiction, venue, and standing.",
    "Confirm finality/ripeness, exhaustion, administrative review, preservation, and the proper procedural vehicle.",
    "Calculate limitation periods, notice-of-claim periods, and filing/service deadlines from primary sources.",
    "Identify immunity, causation, defenses, and the strongest non-liability account.",
    "Match each requested remedy to an authorized claim, defendant, and factual record.",
    "Verify currentness, precedential status, subsequent history, and binding force in the actual forum.",
)


def normalize(text: str) -> str:
    """Normalize text for inspectable phrase matching, not semantic inference."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
    return " " + re.sub(r"\s+", " ", text).strip() + " "


def _phrase_variants(phrase: str) -> set[str]:
    """Return the literal phrase plus a conservative singular/plural variant.

    This is intentionally not a general stemmer: variants are limited to the
    final word so matches remain easy to inspect and explain.
    """
    normalized_phrase = normalize(phrase).strip()
    if not normalized_phrase:
        return set()
    words = normalized_phrase.split()
    last = words[-1]
    variants = {normalized_phrase}

    if last.endswith("ies") and len(last) > 4:
        variants.add(" ".join(words[:-1] + [last[:-3] + "y"]))
    elif last.endswith("s") and len(last) > 3 and not last.endswith(("ss", "us", "is")):
        variants.add(" ".join(words[:-1] + [last[:-1]]))

    if last.endswith("y") and len(last) > 2 and last[-2] not in "aeiou":
        plural = last[:-1] + "ies"
    else:
        plural = last + "s"
    variants.add(" ".join(words[:-1] + [plural]))
    return variants


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    return any(f" {variant} " in normalized_text for variant in _phrase_variants(phrase))


def _all_text(case: CaseRecord) -> str:
    chunks: list[str] = [case.narrative_text]
    chunks.extend(case.questions)
    chunks.extend(case.actors)
    chunks.extend(fact.statement for fact in case.facts)
    chunks.extend(document.text for document in case.documents)
    return "\n".join(chunk for chunk in chunks if chunk)


def _fact_matches_rule(fact: Fact, rule: IssueRule) -> list[str]:
    normalized = normalize(fact.statement)
    return [term for term in rule.trigger_terms if _contains_phrase(normalized, term)]


def _authority_scope_review(authority: Authority, case: CaseRecord) -> dict[str, str]:
    """Offer a limited territorial/temporal review without deciding precedent."""
    layer = authority.layer
    jurisdiction = {key.lower(): value for key, value in case.jurisdiction.items()}
    scope = "not_assessed"
    note = "Researcher must decide applicability; no universal authority ranking is applied."

    if layer.startswith("federal_"):
        country = normalize(jurisdiction.get("country") or "").strip()
        united_states_names = {"united states", "united states of america", "usa", "u s", "u s a"}
        if country in united_states_names:
            scope = "potentially_in_scope"
            note = "Federal source identified for a U.S. matter; subject-matter, forum, and bindingness still require review."
        elif country:
            scope = "country_mismatch_or_conflict_check"
            note = "Confirm whether U.S. federal law has a relevant extraterritorial or other application."
        else:
            scope = "unknown"
            note = "Matter country is missing; territorial fit cannot be assessed."
    elif layer.startswith("state_"):
        matter_state = jurisdiction.get("state")
        source_state = authority.jurisdiction
        if matter_state and source_state:
            if normalize(matter_state).strip() == normalize(source_state).strip():
                scope = "potentially_in_scope"
                note = "State labels match; check the forum, claim, date, and source-specific precedential rule."
            else:
                scope = "different_state_or_choice_of_law_check"
                note = "State labels differ; this may be persuasive or relevant under conflicts rules, not automatically controlling."
        else:
            scope = "unknown"
            note = "Matter state or authority state is missing."
    elif layer == "county_code":
        matter_county = jurisdiction.get("county")
        if matter_county and authority.jurisdiction:
            if normalize(matter_county).strip() == normalize(authority.jurisdiction).strip():
                scope = "potentially_in_scope"
                note = "County labels match; verify territorial reach, enactment, subject matter, and state-law limits."
            else:
                scope = "different_locality_or_conflicts_check"
                note = "County labels differ; local law is not presumed to govern outside its jurisdiction."
        else:
            scope = "unknown"
            note = "Matter county or authority county is missing."
    elif layer in {"municipal_code", "local_charter_or_resolution", "local_administrative_decision"}:
        matter_city = jurisdiction.get("municipality")
        if matter_city and authority.jurisdiction:
            if normalize(matter_city).strip() == normalize(authority.jurisdiction).strip():
                scope = "potentially_in_scope"
                note = "Municipality labels match; verify effective date, territorial reach, enabling law, and preemption."
            else:
                scope = "different_locality_or_conflicts_check"
                note = "Municipal source is not presumed to govern another locality."
        else:
            scope = "unknown"
            note = "Matter municipality or authority locality is missing."
    elif layer in {
        "treaty", "customary_international_law", "international_decision", "international_soft_law"
    }:
        scope = "separate_applicability_gate"
        note = "Check instrument/status, parties, time, domestic implementation or enforceability, forum, and whether the item is binding or persuasive."
    elif layer in {"tribal_law", "foreign_law", "interstate_compact"}:
        scope = "special_jurisdiction_or_conflicts_review"
        note = "Resolve sovereign/territorial jurisdiction, choice-of-law, compact terms, and the relevant federal/state/tribal or foreign-law relationship before assigning force."
    elif layer in {"federal_case", "state_case"}:
        scope = "forum_specific_review_required"
        note = "Court hierarchy, issue, jurisdiction, publication, subsequent history, and the forum determine precedential force."

    temporal = "not_assessed"
    temporal_note = "Supply the operative event date and the law's effective dates; the research snapshot alone is not the event date."
    if case.as_of and (authority.effective_from or authority.effective_to):
        try:
            snapshot = date.fromisoformat(case.as_of[:10])
            start = date.fromisoformat(authority.effective_from[:10]) if authority.effective_from else None
            end = date.fromisoformat(authority.effective_to[:10]) if authority.effective_to else None
            if start and snapshot < start:
                temporal = "not_yet_effective_on_snapshot"
            elif end and snapshot > end:
                temporal = "ended_before_snapshot"
            else:
                temporal = "within_recorded_effective_dates_on_snapshot"
            temporal_note = "Compare this research-snapshot result with the date of each challenged act."
        except (TypeError, ValueError):
            temporal = "invalid_or_ambiguous_date"
            temporal_note = "Dates must be ISO 8601 (YYYY-MM-DD) for this limited check."

    return {
        "territorial_scope": scope,
        "temporal_scope": temporal,
        "bindingness_as_entered": authority.bindingness,
        "verification_checks_as_entered": {
            "citation": authority.citation_check,
            "primary_text": authority.primary_text_check,
            "currentness": authority.currentness_check,
            "subsequent_history": authority.subsequent_history_check,
        },
        "note": note,
        "temporal_note": temporal_note,
    }


def _authority_view(authority: Authority, case: CaseRecord) -> dict[str, Any]:
    return {
        **authority.to_dict(),
        "applicability_review": _authority_scope_review(authority, case),
    }


def _quality_flags(case: CaseRecord) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()

    def add_flags(text: str, *, source_id: str | None, locator: str | None, fact_id: str | None) -> None:
        if not text:
            return
        for category, pattern, suggestion in _REVIEW_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            phrase = match.group(0)
            key = (category, phrase.lower(), source_id)
            if key in seen:
                continue
            seen.add(key)
            flags.append({
                "category": category,
                "matched_text": phrase,
                "fact_id": fact_id,
                "source_id": source_id,
                "locator": locator,
                "review_prompt": suggestion,
                "meaning": "Quality-control flag only; it does not determine that the statement is false.",
            })

    for fact in case.facts:
        add_flags(fact.statement, source_id=fact.source_id, locator=fact.locator, fact_id=fact.id)
    for document in case.documents:
        add_flags(document.text, source_id=document.id, locator=None, fact_id=None)
    add_flags(case.narrative_text, source_id=None, locator=None, fact_id=None)
    return flags


def _completeness_warnings(case: CaseRecord, rules: Sequence[IssueRule]) -> list[str]:
    warnings: list[str] = list(case.ingestion_warnings)
    if not case.as_of:
        warnings.append("No research 'as_of' date is set; currentness cannot be time-bounded.")
    if not case.jurisdiction.get("country"):
        warnings.append("Matter country is missing; legal-source scope cannot be selected reliably.")
    if not case.jurisdiction.get("state"):
        warnings.append("Matter state/province is missing; state-law and state-court analysis may be incomplete.")
    if not case.forum.get("name"):
        warnings.append("Forum/court/agency is missing; bindingness, procedure, and deadlines remain unresolved.")
    if not case.procedural_posture:
        warnings.append("Procedural posture is missing; finality, exhaustion, preservation, and remedy cannot be assessed.")
    if not case.facts:
        warnings.append("No structured facts were supplied; issue signals may come only from document text or questions.")
    if not case.authorities:
        warnings.append("No legal authorities were supplied; the engine will not invent citations or claim the law has been researched.")

    def duplicate_values(values: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        return sorted(duplicates)

    id_groups = {
        "document": [item.id for item in case.documents],
        "fact": [item.id for item in case.facts],
        "authority": [item.id for item in case.authorities],
        "research link": [item.id for item in case.research_links],
    }
    for label, ids in id_groups.items():
        duplicates = duplicate_values(ids)
        if duplicates:
            warnings.append(f"Duplicate {label} id(s) make provenance or graph references ambiguous: {', '.join(duplicates)}.")

    document_ids = {document.id for document in case.documents}
    for document in case.documents:
        if not document.content_sha256:
            warnings.append(f"Source `{document.id}` has no captured SHA-256; byte-level integrity cannot be compared.")
        if not document.extraction_warnings:
            continue
        warnings.extend(f"Source `{document.id}` extraction warning: {warning}" for warning in document.extraction_warnings)

    for fact in case.facts:
        if fact.status in {"unclassified", "unverified", "alleged", "disputed", "inference"}:
            warnings.append(f"Fact `{fact.id}` is marked '{fact.status}'; do not present it as an adjudicated finding.")
        if not fact.source_id:
            warnings.append(f"Fact {fact.id} has no source_id.")
        elif fact.source_id not in document_ids:
            warnings.append(f"Fact {fact.id} references missing source '{fact.source_id}'.")
        if fact.source_id and not fact.locator:
            warnings.append(f"Fact {fact.id} has a source but no page/line/timestamp locator.")

    not_assessed = [fact.id for fact in case.facts if fact.evidence_assessment.strength == "not_assessed"]
    if not_assessed:
        warnings.append(
            f"Qualitative evidence review is not assessed for {len(not_assessed)} fact(s); no strength is inferred by the engine."
        )

    unchecked = [
        authority for authority in case.authorities
        if any(status not in {"checked", "not_applicable"} for status in (
            authority.citation_check,
            authority.primary_text_check,
            authority.currentness_check,
            authority.subsequent_history_check,
        ))
    ]
    if unchecked:
        warnings.append(
            f"{len(unchecked)} supplied authority record(s) have one or more citation/primary-text/currentness/subsequent-history checks incomplete, unresolved, or failed."
        )

    fact_ids = {fact.id for fact in case.facts}
    authority_ids = {authority.id for authority in case.authorities}
    rule_by_id = {rule.id: rule for rule in rules}
    element_ids = {
        _element_id(rule.id, ordinal)
        for rule in rules
        for ordinal, _ in enumerate(rule.elements_to_verify, start=1)
    }
    dangling: list[str] = []
    has_resolved_reviewed_edge = False
    for link in case.research_links:
        from_ids = fact_ids if link.from_type == "fact" else authority_ids
        from_resolves = link.from_id in from_ids
        to_resolves = True
        if not from_resolves:
            dangling.append(f"{link.id} (missing {link.from_type} `{link.from_id}`)")
        if link.to_type == "fact" and link.to_id not in fact_ids:
            dangling.append(f"{link.id} (missing fact `{link.to_id}`)")
            to_resolves = False
        elif link.to_type == "issue" and link.to_id not in rule_by_id:
            dangling.append(f"{link.id} (unknown issue `{link.to_id}`)")
            to_resolves = False
        elif link.to_type == "element" and link.to_id not in element_ids:
            dangling.append(f"{link.id} (unknown issue element `{link.to_id}`)")
            to_resolves = False
        if link.review_status == "reviewed" and from_resolves and to_resolves:
            has_resolved_reviewed_edge = True
    if dangling:
        warnings.append("Research graph has unresolved reference(s): " + "; ".join(dangling) + ".")
    if not has_resolved_reviewed_edge:
        warnings.append("No resolved researcher-reviewed element/fact/authority graph edges are recorded; keyword links remain unvalidated leads.")

    warnings.append(
        "The analyze command is offline. Primary-law searches and case-citator checks require separate, explicitly invoked provider commands."
    )
    return warnings

def _authority_coverage(case: CaseRecord) -> dict[str, Any]:
    counts = {layer: 0 for layer in sorted(AUTHORITY_LAYERS)}
    for authority in case.authorities:
        counts[authority.layer] = counts.get(authority.layer, 0) + 1
    return {
        "layers": counts,
        "note": "Counts show only what was supplied. Presence is not completeness, applicability, or controlling force.",
    }


def _element_id(issue_id: str, ordinal: int) -> str:
    """Stable public identifier used by researcher-authored graph edges."""
    return f"{issue_id}::e{ordinal}"


def _link_is_relevant_to_rule(link: ResearchLink, rule: IssueRule) -> bool:
    element_ids = {_element_id(rule.id, index) for index in range(1, len(rule.elements_to_verify) + 1)}
    return (
        (link.to_type == "issue" and link.to_id == rule.id)
        or (link.to_type == "element" and link.to_id in element_ids)
    )


def _candidate_for_rule(rule: IssueRule, case: CaseRecord, all_normalized_text: str) -> dict[str, Any] | None:
    matched_terms = [
        term for term in rule.trigger_terms if _contains_phrase(all_normalized_text, term)
    ]
    if not matched_terms:
        return None

    matched_facts: list[Fact] = []
    fact_matches: dict[str, list[str]] = {}
    for fact in case.facts:
        terms = _fact_matches_rule(fact, rule)
        if terms:
            matched_facts.append(fact)
            fact_matches[fact.id] = terms

    issue_links = [link for link in case.research_links if _link_is_relevant_to_rule(link, rule)]
    live_links = [link for link in issue_links if link.review_status != "rejected"]
    fact_id_set = {fact.id for fact in case.facts}
    authority_id_set = {authority.id for authority in case.authorities}
    reviewed_fact_link_ids = {
        link.from_id for link in live_links
        if link.from_type == "fact" and link.review_status == "reviewed" and link.from_id in fact_id_set
    }
    proposed_fact_link_ids = {
        link.from_id for link in live_links
        if link.from_type == "fact" and link.review_status == "proposed" and link.from_id in fact_id_set
    }
    linked_fact_ids = reviewed_fact_link_ids | proposed_fact_link_ids
    fact_by_id = {fact.id: fact for fact in case.facts}
    linked_facts = [fact_by_id[fact_id] for fact_id in sorted(linked_fact_ids)]
    candidate_facts = list({fact.id: fact for fact in [*matched_facts, *linked_facts]}.values())
    source_ids = {document.id for document in case.documents}
    fact_views = []
    for fact in candidate_facts:
        if fact.id in fact_matches and fact.id in linked_fact_ids:
            link_origin = "keyword_and_researcher_link"
        elif fact.id in reviewed_fact_link_ids:
            link_origin = "researcher_reviewed_link"
        elif fact.id in proposed_fact_link_ids:
            link_origin = "proposed_link_not_yet_reviewed"
        else:
            link_origin = "keyword_lead"
        fact_views.append({
            "id": fact.id,
            "statement": fact.statement,
            "status": fact.status,
            "source_id": fact.source_id,
            "locator": fact.locator,
            "event_date": fact.event_date,
            "source_quote": fact.source_quote,
            "matched_terms": fact_matches.get(fact.id, []),
            "source_resolves": fact.source_id in source_ids if fact.source_id else False,
            "extraction_method": fact.extraction_method,
            "extraction_confidence": fact.extraction_confidence,
            "evidence_assessment": asdict(fact.evidence_assessment),
            "link_origin": link_origin,
            "note": "Keyword-linked or researcher-linked lead only; this does not prove the fact or map it to a legal element.",
        })

    element_map: list[dict[str, Any]] = []
    for ordinal, item in enumerate(rule.elements_to_verify, start=1):
        stable_id = _element_id(rule.id, ordinal)
        element_links = [
            link for link in issue_links
            if link.to_type == "element" and link.to_id == stable_id
        ]
        reviewed_fact_links = [
            asdict(link) for link in element_links
            if link.from_type == "fact" and link.review_status == "reviewed" and link.from_id in fact_id_set
        ]
        reviewed_authority_links = [
            asdict(link) for link in element_links
            if link.from_type == "authority" and link.review_status == "reviewed" and link.from_id in authority_id_set
        ]
        proposed_links = [asdict(link) for link in element_links if link.review_status == "proposed"]
        element_map.append({
            "element_id": stable_id,
            "research_question": item,
            "candidate_fact_refs": sorted(set(fact.id for fact in matched_facts)),
            "reviewed_fact_links": reviewed_fact_links,
            "reviewed_authority_links": reviewed_authority_links,
            "proposed_links": proposed_links,
            "status": "researcher_reviewed" if reviewed_fact_links or reviewed_authority_links else "researcher_mapping_required",
        })

    authority_by_id = {authority.id: authority for authority in case.authorities}
    tagged_ids = {authority.id for authority in case.authorities if rule.id in authority.issue_tags}
    reviewed_linked_ids = {
        link.from_id for link in live_links
        if link.from_type == "authority" and link.review_status == "reviewed"
        and link.from_id in authority_by_id
    }
    mapped_ids = tagged_ids | reviewed_linked_ids
    authority_views: list[dict[str, Any]] = []
    for authority in case.authorities:
        if authority.id not in mapped_ids:
            continue
        view = _authority_view(authority, case)
        view["mapping_sources"] = [
            *( ["issue_tag_as_entered"] if authority.id in tagged_ids else [] ),
            *( ["researcher_reviewed_link"] if authority.id in reviewed_linked_ids else [] ),
        ]
        authority_views.append(view)
    supporting = [item for item in authority_views if item["treatment"] == "supports"]
    contrary = [item for item in authority_views if item["treatment"] == "contrary"]
    unclassified = [item for item in authority_views if item["treatment"] == "unknown"]
    proposed_authority_refs = sorted({
        link.from_id for link in issue_links
        if link.from_type == "authority" and link.review_status == "proposed"
    })

    return {
        "issue_id": rule.id,
        "title": rule.title,
        "issue_question": rule.issue_question,
        "detection_method": "transparent keyword/phrase match",
        "matched_terms": matched_terms,
        "text_signal_count": len(matched_terms),
        "fact_links": fact_views,
        "elements_to_verify": list(rule.elements_to_verify),
        "element_fact_map": element_map,
        "authority_lanes_to_check": list(rule.authority_lanes),
        "mapped_authorities": authority_views,
        "proposed_authority_link_refs": proposed_authority_refs,
        "supporting_authorities_as_entered": supporting,
        "contrary_or_adverse_authorities_as_entered": contrary,
        "authorities_with_unknown_treatment": unclassified,
        "research_links": [asdict(link) for link in issue_links],
        "evidence_to_collect": list(rule.evidence_to_collect),
        "opposing_questions": list(rule.opposing_questions),
        "research_queries": list(rule.research_queries),
        "research_status": "unresearched_by_engine",
        "candidate_hypothesis": {
            "status": "unassessed",
            "question": (
                "After verifying the governing rule, test whether a principled analogical application or extension could reach the combined fact pattern for this issue, even if no prior case has the exact same facts."
            ),
            "basis_fact_refs": sorted(set(
                [fact.id for fact in matched_facts] + list(reviewed_fact_link_ids)
            )),
            "required_work": [
                "Name the existing rule and verified primary authority before proposing an extension.",
                "Explain the factual/doctrinal bridge and the strongest disanalogy.",
                "Search and address adverse authority, procedural barriers, evidence, and remedy.",
                "State a falsifier; do not infer novelty from an incomplete search.",
            ],
            "not_a_finding": "This is an exploration prompt, not a recognized cause of action, finding of law, or recommendation to file.",
        },
        "novelty_status": "unassessed",
        "novelty_note": (
            "The absence of an exact fact-pattern match in this input is not evidence that a theory is novel, valid, or viable. A systematic search and researcher classification are required."
        ),
        "novel_extension_protocol": list(NOVELTY_PROTOCOL),
        "no_authority_note": (
            "No authority tagged or researcher-linked to this issue was supplied. This is not a finding that no relevant authority exists."
            if not authority_views else
            "Treatment/bindingness labels are as entered and are not independently verified by this analyzer."
        ),
        "signal_warning": "Signal count is not legal strength, likelihood of success, or a recommendation to file.",
    }

def _research_graph(case: CaseRecord, rules: Sequence[IssueRule], issues: list[dict[str, Any]]) -> dict[str, Any]:
    surfaced_ids = {issue["issue_id"] for issue in issues}
    nodes: list[dict[str, Any]] = []
    nodes.extend({"id": fact.id, "type": "fact", "label": fact.statement} for fact in case.facts)
    nodes.extend({"id": authority.id, "type": "authority", "label": authority.citation} for authority in case.authorities)
    for rule in rules:
        nodes.append({
            "id": rule.id,
            "type": "issue",
            "label": rule.title,
            "surfaced_by_text": rule.id in surfaced_ids,
        })
        nodes.extend({
            "id": _element_id(rule.id, ordinal),
            "type": "element",
            "label": question,
            "issue_id": rule.id,
        } for ordinal, question in enumerate(rule.elements_to_verify, start=1))

    fact_ids = {fact.id for fact in case.facts}
    authority_ids = {authority.id for authority in case.authorities}
    issue_ids = {rule.id for rule in rules}
    element_ids = {
        _element_id(rule.id, ordinal)
        for rule in rules
        for ordinal, _ in enumerate(rule.elements_to_verify, start=1)
    }
    valid_link_ids: list[str] = []
    unresolved_link_ids: list[str] = []
    edges = []
    for link in case.research_links:
        from_ids = fact_ids if link.from_type == "fact" else authority_ids
        to_ids = {"issue": issue_ids, "element": element_ids, "fact": fact_ids}[link.to_type]
        valid = link.from_id in from_ids and link.to_id in to_ids
        (valid_link_ids if valid else unresolved_link_ids).append(link.id)
        edge = asdict(link)
        edge["reference_status"] = "resolved" if valid else "unresolved"
        edges.append(edge)
    return {
        "nodes": nodes,
        "edges": edges,
        "reviewed_edge_count": sum(edge["review_status"] == "reviewed" and edge["reference_status"] == "resolved" for edge in edges),
        "unresolved_reviewed_edge_count": sum(edge["review_status"] == "reviewed" and edge["reference_status"] == "unresolved" for edge in edges),
        "proposed_edge_count": sum(link.review_status == "proposed" for link in case.research_links),
        "rejected_edge_count": sum(link.review_status == "rejected" for link in case.research_links),
        "resolved_edge_ids": valid_link_ids,
        "unresolved_edge_ids": unresolved_link_ids,
        "element_id_convention": "<issue_id>::e<ordinal>; ordinals follow the order of elements_to_verify",
        "note": (
            "Only researcher-reviewed, resolved edges are treated as reviewed mappings. Proposed edges remain hypotheses; "
            "rejected edges remain in the audit trail. The graph is not a legal conclusion or a truth determination."
        ),
    }


def analyze_case(
    case: CaseRecord,
    *,
    issue_rules: Sequence[IssueRule] | None = None,
) -> dict[str, Any]:
    """Return an auditable, offline issue map from a normalized case packet."""
    rules = tuple(issue_rules or BUILTIN_ISSUE_RULES)
    corpus = _all_text(case)
    normalized_corpus = normalize(corpus)
    issues = [
        candidate
        for rule in rules
        if (candidate := _candidate_for_rule(rule, case, normalized_corpus)) is not None
    ]

    facts_by_status: dict[str, list[str]] = {}
    for fact in case.facts:
        facts_by_status.setdefault(fact.status, []).append(fact.id)

    vectors = {
        "actors_and_source_of_responsibility": {
            "actors_supplied": case.actors,
            "note": "The prototype does not infer identity, capacity, duty, policymaking status, or personal liability from a name.",
        },
        "law_and_authority": {
            "authority_coverage": _authority_coverage(case)["layers"],
            "note": "Coverage is an input inventory, not a legal hierarchy or completeness score.",
        },
        "facts_and_provenance": {
            "fact_count": len(case.facts),
            "facts_by_status": facts_by_status,
            "ingestion_warnings": case.ingestion_warnings,
            "source_documents": [
                {
                    "id": document.id,
                    "title": document.title,
                    "kind": document.kind,
                    "url": document.url,
                    "captured_at": document.captured_at,
                    "publisher": document.publisher,
                    "primary_source_status_as_entered": document.primary_source_status,
                    "original_filename": document.original_filename,
                    "archived_path": document.archived_path,
                    "content_sha256": document.content_sha256,
                    "byte_size": document.byte_size,
                    "extraction_method": document.extraction_method,
                    "extraction_confidence": document.extraction_confidence,
                    "extraction_warnings": document.extraction_warnings,
                }
                for document in case.documents
            ],
        },
        "tensions_and_candidate_theories": {
            "candidate_issue_ids": [issue["issue_id"] for issue in issues],
            "note": "A candidate is a research prompt, not a conclusion that a cause of action exists.",
        },
        "forum_time_and_procedure": {
            "jurisdiction": case.jurisdiction,
            "forum": case.forum,
            "as_of": case.as_of,
            "procedural_posture": case.procedural_posture,
        },
    }

    linked_from_issues = {
        authority["id"]
        for issue in issues
        for authority in issue["mapped_authorities"]
    }
    unmapped_authorities = [
        _authority_view(authority, case)
        for authority in case.authorities
        if authority.id not in linked_from_issues
    ]

    research_queue = [
        "Confirm the operative jurisdiction(s), forum, event dates, procedural posture, requested remedy, and deadlines.",
        "Resolve each important fact to its original source and precise page/paragraph/line/timestamp locator.",
        "Retrieve current and historical primary law for each triggered issue; record official text, date, and version.",
        "Build and researcher-review the element/fact/authority graph; distinguish support, contrary, and disanalogy links.",
        "Run a case citator/subsequent-history search and inspect every potential negative-treatment hit in context.",
        "Test threshold defenses and remedies before expanding merits theories.",
        "Only then develop analogical or novel extensions using the novelty protocol, strongest counterargument, and a falsifier.",
    ]

    return {
        "engine": "Civic Legal Research Red-Team Prototype",
        "engine_version": ENGINE_VERSION,
        "case_id": case.case_id,
        "title": case.title,
        "method": (
            "Deterministic lexical issue spotting and researcher-entered graph/evidence metadata. This analyze operation is offline; "
            "it performs no legal search, citator check, citation verification, legal-outcome prediction, or automatic evidence weighting."
        ),
        "issue_catalog": {
            "rule_count": len(rules),
            "rule_ids": [rule.id for rule in rules],
            "note": "A non-exhaustive, extensible starter catalog; no match is not a finding that no legal issue exists.",
        },
        "vectors": vectors,
        "candidate_issues": issues,
        "unmapped_authorities": unmapped_authorities,
        "research_graph": _research_graph(case, rules, issues),
        "quality_flags": _quality_flags(case),
        "global_red_team_checks": list(GLOBAL_RED_TEAM_CHECKS),
        "procedural_gate_checks": list(_PROCEDURAL_GATE_CHECKS),
        "authority_coverage": _authority_coverage(case),
        "completeness_warnings": _completeness_warnings(case, rules),
        "research_queue": research_queue,
        "limitations": [
            "Keyword triggers can miss issues or produce false positives; every lead needs human review.",
            "The built-in catalog is not exhaustive. Custom issue packs extend it but do not prove coverage of all law.",
            "The engine does not determine facts, interpret controlling law, validate citations, or predict outcomes.",
            "Qualitative evidence and mapping fields are entered by a person; no evidence weight or legal result is computed.",
            "A provider search or citator result is discovery evidence only and does not establish currentness, holding, or treatment.",
            "Novelty cannot be inferred from this packet or from failure to find an exact factual match.",
            "Legal hierarchy is contextual; the engine deliberately does not assign a single numeric rank to every source.",
            "Not legal advice or a substitute for a licensed attorney's review of the actual record and current law.",
        ],
    }
