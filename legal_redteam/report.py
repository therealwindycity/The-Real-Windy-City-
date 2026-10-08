"""Human-readable report formatting for analysis output."""

from __future__ import annotations

from typing import Any


def _md(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\r", "").replace("\n", " ").strip()


def _bullet_lines(items: list[Any], empty: str = "None supplied.") -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {_md(item)}" for item in items]


def _fact_excerpt(value: str, limit: int = 420) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_markdown(result: dict[str, Any]) -> str:
    vectors = result["vectors"]
    forum = vectors["forum_time_and_procedure"]
    jurisdiction = forum.get("jurisdiction") or {}
    forum_details = forum.get("forum") or {}
    location = ", ".join(
        _md(jurisdiction.get(key)) for key in ("municipality", "county", "state", "country")
        if jurisdiction.get(key)
    ) or "not supplied"
    forum_name = _md(forum_details.get("name") or "not supplied")
    as_of = _md(forum.get("as_of") or "not supplied")
    posture = _md(forum.get("procedural_posture") or "not supplied").rstrip(".")
    facts_by_status = vectors["facts_and_provenance"]["facts_by_status"]
    fact_status_summary = "; ".join(
        f"{status}: {len(fact_ids)}" for status, fact_ids in sorted(facts_by_status.items())
    ) or "none"

    lines = [
        f"# {result['engine']}",
        "",
        f"**Matter:** {_md(result['title'])}  ",
        f"**Case ID:** `{_md(result['case_id'])}`  ",
        f"**Engine:** `{_md(result['engine_version'])}`  ",
        f"**Location provided:** {location}  ",
        f"**Forum:** {forum_name}  ",
        f"**Research as-of:** {as_of}  ",
        f"**Posture:** {posture}",
        "",
        "> **Research aid only.** Candidate issues are keyword-triggered prompts, not findings, legal advice, filing recommendations, or predictions of success. Verify every fact and legal source against the actual record and current primary law.",
        "",
        "## Method and limits",
        "",
        f"{_md(result['method'])}",
        "",
        "Signal counts below reflect text matches only. They do not measure the merits, novelty, or probability of winning. This offline analysis generates no citations; optional drafting may format only researcher-verified, allowlisted authority records and still requires review.",
        "",
        "## Five-vector intake (adapted from the prior Paradox Engine work)",
        "",
        f"1. **Actors / source of responsibility:** {_md(', '.join(vectors['actors_and_source_of_responsibility']['actors_supplied']) or 'none explicitly supplied')}",
        f"2. **Law and authority inventory:** {sum(vectors['law_and_authority']['authority_coverage'].values())} authority record(s) supplied across tagged layers.",
        f"3. **Facts and provenance:** {vectors['facts_and_provenance']['fact_count']} structured fact record(s); statuses: {_md(fact_status_summary)}.",
        f"4. **Tensions / issue prompts:** {len(result['candidate_issues'])} candidate issue(s) surfaced.",
        f"5. **Forum / time / procedure:** {forum_name}; as-of {as_of}; posture {_md(posture)}.",
        "",
        "The original five coordinates are retained, but the old binary 'checkmate' sequence is not: the engine requires element-by-element support, contrary authority, evidence gaps, and a plausible opposing account.",
        "",
        "## Candidate issue radar",
        "",
    ]

    lines.extend(["## Ingested sources", ""])
    source_documents = vectors["facts_and_provenance"]["source_documents"]
    if source_documents:
        for document in source_documents:
            url = f" — {_md(document['url'])}" if document.get("url") else ""
            captured = f"; captured {_md(document['captured_at'])}" if document.get("captured_at") else ""
            publisher = f"; publisher {_md(document['publisher'])}" if document.get("publisher") else ""
            digest = f"; SHA-256 `{_md(document['content_sha256'])}`" if document.get("content_sha256") else "; no content hash recorded"
            extraction = (
                f"; extraction `{_md(document['extraction_method'])}` / confidence `{_md(document['extraction_confidence'])}`"
                if document.get("extraction_method") else ""
            )
            size = f"; {document['byte_size']} bytes" if document.get("byte_size") is not None else ""
            archive = f"; archived as `{_md(document['archived_path'])}`" if document.get("archived_path") else ""
            lines.append(
                f"- `{_md(document['id'])}` — {_md(document['title'])}; kind `{_md(document['kind'])}`; "
                f"primary-source status `{_md(document['primary_source_status_as_entered'])}`{captured}{publisher}{size}{digest}{extraction}{archive}{url}."
            )
            for warning in document.get("extraction_warnings", []):
                lines.append(f"  - Extraction warning: {_md(warning)}")
    else:
        lines.append("- No source documents supplied.")
    lines.append("")

    if not result["candidate_issues"]:
        lines.append("No issue rules were triggered by the text supplied. This is not a finding that the matter has no legal issues; add facts/questions or broaden the rules and research manually.")
    else:
        for index, issue in enumerate(result["candidate_issues"], start=1):
            lines.extend([
                f"### {index}. {issue['title']} (`{issue['issue_id']}`)",
                "",
                f"**Text signal:** {_md(', '.join(issue['matched_terms']))} ({issue['text_signal_count']} distinct trigger term(s); not a merits score).",
                "",
                f"**Research question:** {_md(issue['issue_question'])}",
                "",
                "**Fact leads (not findings):**",
            ])
            if issue["fact_links"]:
                for fact in issue["fact_links"]:
                    source = f"source `{_md(fact['source_id'])}`" if fact.get("source_id") else "no source linked"
                    locator = f", {_md(fact['locator'])}" if fact.get("locator") else ""
                    review = fact.get("evidence_assessment") or {}
                    strength = review.get("strength", "not_assessed")
                    review_by = f"; evidence review by {_md(review['reviewer'])}" if review.get("reviewer") else ""
                    extraction = f"; extraction `{_md(fact.get('extraction_confidence') or 'unassessed')}`" if fact.get("extraction_method") else ""
                    lines.append(
                        f"- `{_md(fact['id'])}` ({_md(fact['status'])}; {source}{locator}; "
                        f"terms: {_md(', '.join(fact['matched_terms']) or 'none directly matched')}; "
                        f"evidence strength `{_md(strength)}`{review_by}{extraction}): “{_md(_fact_excerpt(fact['statement']))}”"
                    )
                    if fact.get("source_quote"):
                        lines.append(f"  - Source quotation as entered: “{_md(_fact_excerpt(fact['source_quote']))}”")
                    if review.get("rationale"):
                        lines.append(f"  - Assessment rationale: {_md(review['rationale'])}")
            else:
                lines.append("- No structured fact matched directly; this signal came from document text, an actor name, or a question.")
            lines.extend([
                "",
                "**Elements / doctrinal questions to verify:**",
                *_bullet_lines(issue["elements_to_verify"]),
                "",
                "**Element-to-evidence map:**",
            ])
            if issue.get("element_fact_map"):
                for element in issue["element_fact_map"]:
                    candidates = ", ".join(element.get("candidate_fact_refs", [])) or "none"
                    reviewed_facts = ", ".join(
                        f"{link['from_id']} ({link['relation']})" for link in element.get("reviewed_fact_links", [])
                    ) or "none"
                    reviewed_authorities = ", ".join(
                        f"{link['from_id']} ({link['relation']})" for link in element.get("reviewed_authority_links", [])
                    ) or "none"
                    lines.append(
                        f"- `{_md(element['element_id'])}` — `{_md(element['status'])}`; "
                        f"keyword candidates: {_md(candidates)}; reviewed fact links: {_md(reviewed_facts)}; "
                        f"reviewed authority links: {_md(reviewed_authorities)}."
                    )
            else:
                lines.append("- No element map is available.")
            lines.extend([
                "",
                "**Authority lanes to search (applicability is case-specific):**",
                *_bullet_lines(issue["authority_lanes_to_check"]),
                "",
                "**Authorities tagged or researcher-linked to this issue:**",
            ])
            if issue["mapped_authorities"]:
                for authority in issue["mapped_authorities"]:
                    cite = _md(authority["citation"])
                    if authority.get("pinpoint"):
                        cite += f", pinpoint {_md(authority['pinpoint'])}"
                    source_url = authority.get("official_opinion_url") or authority.get("official_url")
                    url = f" — [{_md(source_url)}]({_md(source_url)})" if source_url else ""
                    proposition = f"; proposition entered: {_md(authority['proposition'])}" if authority.get("proposition") else ""
                    case_details = []
                    if authority.get("reporter_citation"):
                        case_details.append(f"reporter cite {_md(authority['reporter_citation'])}")
                    if authority.get("docket_number"):
                        case_details.append(f"docket {_md(authority['docket_number'])}")
                    if authority.get("docket_url"):
                        case_details.append(f"docket URL {_md(authority['docket_url'])}")
                    if authority.get("precedential_status"):
                        case_details.append(f"precedential status {_md(authority['precedential_status'])}")
                    if authority.get("captured_at"):
                        case_details.append(f"captured {_md(authority['captured_at'])}")
                    case_details_text = "; " + "; ".join(case_details) if case_details else ""
                    source_hash = f"; capture SHA-256 `{_md(authority['source_capture_sha256'])}`" if authority.get("source_capture_sha256") else ""
                    verification = authority["applicability_review"]["verification_checks_as_entered"]
                    verification_summary = ", ".join(f"{name}={status}" for name, status in verification.items())
                    lines.append(
                        f"- {cite} — layer `{_md(authority['layer'])}`; bindingness `{_md(authority['bindingness'])}`; "
                        f"treatment `{_md(authority['treatment'])}`; checks: {_md(verification_summary)}{proposition}{case_details_text}{source_hash}{url}."
                    )
                    if authority.get("source_excerpt"):
                        lines.append(f"  - Source excerpt as entered: “{_md(_fact_excerpt(authority['source_excerpt']))}”")
                    lines.append(
                        f"  - Scope check: {_md(authority['applicability_review']['territorial_scope'])}; "
                        f"{_md(authority['applicability_review']['note'])}"
                    )
            else:
                lines.append("- None tagged or researcher-linked. No authority match is not evidence that no relevant authority exists.")
            lines.extend([
                "",
                "**Evidence to collect:**",
                *_bullet_lines(issue["evidence_to_collect"]),
                "",
                "**Opposing-side questions:**",
                *_bullet_lines(issue["opposing_questions"]),
                "",
                "**Research queries:**",
                *_bullet_lines(issue["research_queries"]),
                "",
                "**Novel / analogical hypothesis to explore (not a legal conclusion):**",
                f"{_md(issue['candidate_hypothesis']['question'])} Basis fact refs: {_md(', '.join(issue['candidate_hypothesis']['basis_fact_refs']) or 'none linked')}.",
                *_bullet_lines(issue["candidate_hypothesis"]["required_work"]),
                f"Not a finding: {_md(issue['candidate_hypothesis']['not_a_finding'])}",
                "",
                f"**Novelty status:** `{_md(issue['novelty_status'])}` — {_md(issue['novelty_note'])}",
                "",
                "To develop an untried or analogical theory, complete the novelty protocol: establish the existing rule, compare the closest cases, articulate both the bridge and the disanalogy, address adverse authority, identify a vehicle/remedy, and state a falsifier. Novelty is not viability.",
                "",
            ])

    lines.extend([
        "## Supplied authorities not mapped to a surfaced issue",
        "",
    ])
    if result["unmapped_authorities"]:
        for authority in result["unmapped_authorities"]:
            tags = ", ".join(authority["issue_tags"]) or "none"
            lines.append(
                f"- {_md(authority['citation'])} — layer `{_md(authority['layer'])}`; tags: {_md(tags)}; "
                f"bindingness `{_md(authority['bindingness'])}`; researcher mapping required."
            )
    else:
        if sum(result["authority_coverage"]["layers"].values()) == 0:
            lines.append("- No authority records were supplied.")
        else:
            lines.append("- No supplied authorities remain unmapped to a surfaced issue.")

    graph = result.get("research_graph", {})
    lines.extend([
        "",
        "## Research graph and review status",
        "",
        f"Nodes: {len(graph.get('nodes', []))}; reviewed edges: {graph.get('reviewed_edge_count', 0)}; "
        f"proposed edges: {graph.get('proposed_edge_count', 0)}; rejected edges retained: {graph.get('rejected_edge_count', 0)}.",
        "",
        _md(graph.get("note", "No graph review metadata available.")),
        "",
    ])
    if graph.get("edges"):
        for edge in graph["edges"]:
            lines.append(
                f"- `{_md(edge['id'])}`: `{_md(edge['from_type'])}:{_md(edge['from_id'])}` "
                f"— `{_md(edge['relation'])}` → `{_md(edge['to_type'])}:{_md(edge['to_id'])}`; "
                f"review `{_md(edge['review_status'])}`; reference `{_md(edge.get('reference_status', 'unknown'))}`; "
                f"reviewer `{_md(edge.get('reviewer') or 'not supplied')}`."
            )
    else:
        lines.append("- No research links recorded; add researcher-reviewed edges in the case packet after checking each source.")

    lines.extend([
        "",
        "## Self-red-team quality flags",
        "",
    ])
    if result["quality_flags"]:
        for flag in result["quality_flags"]:
            source = f"source `{_md(flag['source_id'])}`" if flag.get("source_id") else "matter text"
            locator = f", {_md(flag['locator'])}" if flag.get("locator") else ""
            fact = f", fact `{_md(flag['fact_id'])}`" if flag.get("fact_id") else ""
            lines.append(
                f"- **{_md(flag['category'])}** — “{_md(flag['matched_text'])}” ({source}{locator}{fact}). {_md(flag['review_prompt'])}"
            )
    else:
        lines.append("No configured wording flags fired. The rules are narrow and do not certify that the packet is neutral or complete.")

    lines.extend([
        "",
        "## Opposing-side red-team checks",
        "",
        *_bullet_lines(result["global_red_team_checks"]),
        "",
        "## Cross-cutting procedural gates",
        "",
        *_bullet_lines(result["procedural_gate_checks"]),
        "",
        "## Authority inventory coverage",
        "",
        "Counts are exactly the source records entered; zero counts do not mean a layer is legally required, and non-zero counts do not mean the research is complete.",
        "",
    ])
    layers = result["authority_coverage"]["layers"]
    present = [(layer, count) for layer, count in layers.items() if count]
    if present:
        lines.extend(f"- `{_md(layer)}`: {count}" for layer, count in present)
    else:
        lines.append("- No authority records supplied.")

    lines.extend([
        "",
        "## Completeness warnings",
        "",
        *_bullet_lines(result["completeness_warnings"]),
        "",
        "## Research queue",
        "",
        *_bullet_lines(result["research_queue"]),
        "",
        "## Prototype limitations",
        "",
        *_bullet_lines(result["limitations"]),
        "",
    ])
    return "\n".join(lines)
