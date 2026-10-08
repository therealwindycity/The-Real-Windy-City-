"""Expanded starter issue pack and loader for user-authored rule catalogs.

Rules are research prompts. A custom pack extends the built-in set and cannot
silently replace a built-in identifier.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .catalog import ISSUE_RULES, IssueRule
from .models import AUTHORITY_LAYERS


EXPANDED_ISSUE_RULES: tuple[IssueRule, ...] = (
    IssueRule(
        id="employment_labor",
        title="Employment, labor, and workplace regulation",
        trigger_terms=(
            "employment", "employee", "termination", "workplace", "wage", "overtime",
            "collective bargaining", "union", "workplace retaliation", "reasonable accommodation",
            "workplace discrimination", "leave entitlement",
        ),
        issue_question=(
            "Identify the employment relationship, governing source, protected status or activity if any, "
            "decision, timing, required administrative path, and available remedy."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_regulation",
            "federal_case", "state_case", "agency_record", "contract_or_private_rule",
        ),
        elements_to_verify=(
            "Determine worker/employer status, public/private capacity, coverage, and the applicable source of rights.",
            "Identify the challenged act, protected status/activity, required intent or causation, and comparator evidence.",
            "Check collective bargaining terms, internal grievance steps, exhaustion, charge deadlines, and limitation periods.",
            "Separate wage/hour, leave, accommodation, discrimination, retaliation, contract, and constitutional theories.",
            "Identify defenses, immunity where applicable, damages limits, reinstatement, and other authorized remedies.",
        ),
        evidence_to_collect=(
            "Employment agreement, policies, job classification, personnel file, schedules, pay records, and relevant notices.",
            "Decision-maker identity, contemporaneous reasons, comparator records, protected-activity timeline, and communications.",
            "Administrative charges, grievance filings, collective bargaining materials, deadlines, and proof of service.",
        ),
        opposing_questions=(
            "Is the actor/employer covered, and is the claimant within the statute's protected class or activity?",
            "Is there a documented non-retaliatory or nondiscriminatory reason supported by contemporaneous evidence?",
            "Were required administrative steps or contractual grievances timely completed?",
            "Do immunity, causation, damages limits, arbitration, or a time bar narrow the route?",
        ),
        research_queries=(
            "Locate controlling federal and forum-state statutes, regulations, elements, remedies, and filing periods.",
            "Check agency guidance separately from binding regulations and the administrative record.",
            "Search controlling decisions on coverage, causation, defenses, exhaustion, and available relief.",
        ),
    ),
    IssueRule(
        id="environmental_public_health",
        title="Environmental, natural-resource, and public-health regulation",
        trigger_terms=(
            "environmental", "pollution", "contamination", "emissions", "hazardous waste",
            "water quality", "air quality", "drinking water", "permit violation", "public health",
            "endangered species", "wetlands", "environmental impact",
        ),
        issue_question=(
            "Identify the regulated activity, permit or statutory program, responsible sovereign/agency, "
            "record, enforcement or review path, and any citizen-suit or other remedy requirements."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_regulation",
            "state_case", "federal_case", "county_code", "municipal_code", "agency_record",
            "agency_guidance", "treaty", "tribal_law",
        ),
        elements_to_verify=(
            "Identify the pollutant/resource, source, regulated entity, jurisdiction, and applicable permit/program.",
            "Verify the operative statutory and regulatory text, permit conditions, monitoring, and effective dates.",
            "Check standing, notice, exhaustion, diligent prosecution, preemption, and any citizen-suit prerequisites.",
            "Separate agency compliance/enforcement from private injury, causation, and a judicially available remedy.",
            "Review tribal, interstate, federal, state, and local jurisdiction or consultation duties when implicated.",
        ),
        evidence_to_collect=(
            "Permits, applications, monitoring data, inspection reports, notices of violation, and administrative orders.",
            "Sampling methodology, chain of custody, expert reports, source attribution, exposure, and injury evidence.",
            "Agency docket, public comments, consultation records, notice letters, and current compliance history.",
        ),
        opposing_questions=(
            "Does the claimant have a cognizable injury and a traceable, redressable connection to this source?",
            "Does a permit, exception, federal preemption rule, or agency enforcement decision alter the route?",
            "Were notice, exhaustion, diligent-prosecution, and limitations prerequisites satisfied?",
            "Are sampling, causation, exposure, and alleged harms supported by reliable evidence?",
        ),
        research_queries=(
            "Retrieve official current and historical statutes, regulations, permit text, and Federal Register amendments.",
            "Find controlling cases on standing, preemption, citizen-suit prerequisites, causation, and remedy.",
            "Search the complete agency record and distinguish binding findings from guidance or press materials.",
        ),
    ),
    IssueRule(
        id="public_contracts_procurement",
        title="Public contracting, procurement, and bidding",
        trigger_terms=(
            "procurement", "public contract", "contract award", "competitive bid", "request for proposals",
            "lowest responsible bidder", "sole source", "bid protest", "change order", "vendor selection",
        ),
        issue_question=(
            "Trace the public entity's contracting authority, solicitation and award rules, record of evaluation, "
            "protest route, and the contract's terms before assessing a procurement challenge."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_regulation", "state_case",
            "federal_case", "county_code", "municipal_code", "local_charter_or_resolution",
            "contract_or_private_rule", "agency_record",
        ),
        elements_to_verify=(
            "Identify the entity, funding source, procurement method, delegation, solicitation, and protest forum.",
            "Read the controlling procurement statute/code, solicitation terms, evaluation criteria, and amendments.",
            "Compare the documented evaluation and award to published criteria and required procedure.",
            "Check protest standing, exhaustion, notice, deadlines, waiver, and any federal grant conditions.",
            "Identify contract formation, sovereign immunity, damages restrictions, injunction standards, and remedies.",
        ),
        evidence_to_collect=(
            "Solicitation and addenda, bids/proposals, scoring sheets, evaluator communications, award, and contract.",
            "Delegation, appropriations, conflict disclosures, procurement file, protest, and agency response.",
            "Federal funding terms, change orders, performance records, and documented loss or bid-preparation costs.",
        ),
        opposing_questions=(
            "Did the solicitation reserve discretion or provide a lawful basis for the challenged selection?",
            "Was the protest timely, brought by an eligible party, and filed in the correct forum?",
            "Did the claimant have a legally protected right to award, or only an opportunity to compete?",
            "Would the requested relief disrupt performance, prejudice other bidders, or exceed statutory authority?",
        ),
        research_queries=(
            "Retrieve the official procurement code, regulations, solicitation, amendments, and delegated authority.",
            "Find controlling cases on bid protests, standing, discretion, waiver, and available remedies.",
            "Check grant/funding conditions and forum-specific notice or protest deadlines.",
        ),
    ),
    IssueRule(
        id="tax_assessment_fiscal",
        title="Taxation, assessment, fees, and public finance",
        trigger_terms=(
            "tax assessment", "property tax", "special assessment", "tax levy", "tax refund", "tax rate",
            "user fee", "municipal fee", "revenue bond", "public debt", "tax exemption", "tax valuation",
        ),
        issue_question=(
            "Identify the taxing authority, legal characterization of the charge, valuation or rate method, "
            "administrative appeal path, and jurisdiction-specific deadlines."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_statute", "state_statute",
            "state_regulation", "state_case", "federal_case", "county_code", "municipal_code",
            "local_charter_or_resolution", "agency_record",
        ),
        elements_to_verify=(
            "Distinguish a tax, assessment, regulatory fee, user charge, penalty, and contractual payment.",
            "Identify the authorized government, affected property/person, rate, valuation, and operative period.",
            "Check notice, hearing, equalization or administrative appeal, exhaustion, and payment-under-protest rules.",
            "Research uniformity, classification, nexus, statutory delegation, debt limits, and any constitutional constraints.",
            "Calculate deadlines and identify the forum, burden, refund procedure, and remedy from primary law.",
        ),
        evidence_to_collect=(
            "Assessment notice, valuation record, rate/resolution, parcel data, comparables, and administrative appeal file.",
            "Cost-of-service or nexus study, budget, enabling statute, hearing notice, and adoption minutes.",
            "Payment receipts, refund request, protest, deadlines, and calculation of the claimed amount.",
        ),
        opposing_questions=(
            "Is the charge a tax, a valid regulatory/user fee, or a cost allocation authorized by law?",
            "Were statutory appeal procedures and strict filing/payment deadlines followed?",
            "Does the classification have a rational or otherwise applicable legal basis?",
            "Is the requested refund or injunction available against this entity and in this forum?",
        ),
        research_queries=(
            "Retrieve the relevant constitution, enabling statute, current code, rate resolution, and historical version.",
            "Find controlling cases distinguishing taxes, fees, assessments, and regulatory charges.",
            "Verify valuation/appeal procedures, deadlines, burdens, and refund remedies in official sources.",
        ),
    ),
    IssueRule(
        id="elections_voting",
        title="Elections, voting, and political participation",
        trigger_terms=(
            "election", "voting", "ballot", "voter registration", "polling place", "redistricting",
            "campaign finance", "candidate qualification", "recount", "election challenge", "absentee ballot",
        ),
        issue_question=(
            "Identify the election, rule, affected voter/candidate, decision-maker, timing, and expedited "
            "state or federal review path; election deadlines can be unusually short."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_statute", "state_statute",
            "state_regulation", "federal_case", "state_case", "county_code", "municipal_code",
            "local_administrative_decision", "agency_record",
        ),
        elements_to_verify=(
            "Identify the office/election, governing jurisdiction, challenged rule or act, and injury to participation.",
            "Determine the applicable constitutional/statutory test, protected class, and relevant comparator or burden.",
            "Check the election calendar, exhaustion, notice, standing, preservation, and emergency-review requirements.",
            "Separate ballot access, districting, administration, campaign finance, recount, and voting-rights theories.",
            "Identify the responsible official/entity, causation, immunity, and relief that remains practically available.",
        ),
        evidence_to_collect=(
            "Election calendar, registration/ballot records, district maps, written decision, and applicable procedures.",
            "Affected-voter or candidate declarations, comparator data, polling-place records, and communications.",
            "Administrative objections, recount/protest filings, service records, and expedited docket materials.",
        ),
        opposing_questions=(
            "Is the claim timely and justiciable before the election, and can the requested relief be implemented?",
            "Is the rule neutral and supported by an adequate administrative or legislative record?",
            "Does the claimant have standing, and were available state remedies or objections preserved?",
            "Would an injunction or changed procedure create confusion or impair other voters' rights?",
        ),
        research_queries=(
            "Retrieve the official federal/state election statutes, regulations, district plans, and current calendar.",
            "Find controlling precedent for the exact burden, classification, election stage, and requested remedy.",
            "Check emergency procedures, filing deadlines, exhaustion, and local election-board records immediately.",
        ),
    ),
    IssueRule(
        id="speech_assembly_press",
        title="Speech, assembly, petition, press, and public comment",
        trigger_terms=(
            "free speech", "freedom of speech", "public comment", "viewpoint discrimination", "protest",
            "assembly", "petition", "press freedom", "prior restraint", "retaliation for speech", "expressive conduct",
        ),
        issue_question=(
            "Identify the speaker, forum, government action, speech or conduct, and applicable forum/content "
            "rules without assuming every restriction is unconstitutional or every public setting is a forum."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_case", "state_case", "federal_statute",
            "state_statute", "municipal_code", "county_code", "local_administrative_decision", "agency_record",
        ),
        elements_to_verify=(
            "Classify the forum and challenged rule; distinguish content-, viewpoint-, and time/place/manner restrictions.",
            "Identify protected speech/conduct, government actor, adverse action, causation, and the applicable test.",
            "Check permit, conduct, safety, disruption, access, and neutral administration evidence.",
            "Analyze retaliation, prior restraint, petition, press, and state constitutional provisions separately where relevant.",
            "Check standing, preservation, immunity, deadlines, and whether prospective or retrospective relief is available.",
        ),
        evidence_to_collect=(
            "Written policy, forum designation, permits, enforcement criteria, recordings, notices, and contemporaneous reasons.",
            "Full statement/context, timing, audience, comparable speakers, access history, and decision-maker communications.",
            "Injury, requested relief, recurrence risk, and any administrative appeal or preservation record.",
        ),
        opposing_questions=(
            "Is the speech protected in this forum, and does the rule regulate conduct rather than viewpoint?",
            "Was the restriction content-neutral, narrowly tailored where required, and supported by a record?",
            "Did actual disruption, safety, property, or time/place/manner limits explain the decision?",
            "Is there a causal link, an ongoing controversy, and a defendant/remedy capable of redress?",
        ),
        research_queries=(
            "Find controlling forum doctrine and the precise scrutiny/test for this speech, forum, and restriction.",
            "Search state constitutional speech and petition provisions independently from the federal floor.",
            "Retrieve official policies, permits, enforcement records, and any appeal or injunction standards.",
        ),
    ),
    IssueRule(
        id="housing_tenant_fair_housing",
        title="Housing, landlord-tenant, eviction, and fair-housing issues",
        trigger_terms=(
            "eviction", "landlord", "tenant", "lease", "rent increase", "habitability", "housing discrimination",
            "fair housing", "housing voucher", "security deposit", "foreclosure", "housing accommodation",
        ),
        issue_question=(
            "Identify the property, legal relationship, decision-maker, notice and process, any protected-class or "
            "statutory right, and the court or administrative route."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_case", "federal_case",
            "county_code", "municipal_code", "court_rule", "contract_or_private_rule", "agency_record",
        ),
        elements_to_verify=(
            "Establish the lease/tenancy or housing program, parties, property, governing law, and event dates.",
            "Identify notice, service, cure, hearing, defenses, habitability, and appeal requirements.",
            "For discrimination/accommodation, verify coverage, protected class, request, decision, causation, and defenses.",
            "Check federal/state/local overlap, preemption, subsidy terms, and any administrative charge/exhaustion path.",
            "Identify urgent possession deadlines, available stay, damages, injunction, and legal-aid/counsel needs.",
        ),
        evidence_to_collect=(
            "Lease, notices, service proof, payment ledger, inspection/repair records, and court/agency docket.",
            "Accommodation request, communications, comparator evidence, program rules, and stated reasons.",
            "Condition photographs, expert/inspection records, receipts, benefit correspondence, and deadline notices.",
        ),
        opposing_questions=(
            "Was notice and service legally sufficient, and were required defenses or counterclaims timely raised?",
            "Does the governing law cover this property, landlord, program, or requested accommodation?",
            "Is there a documented non-discriminatory reason or a reasonable alternative accommodation?",
            "Can requested relief be granted by this tribunal, and are urgent deadlines or stays implicated?",
        ),
        research_queries=(
            "Retrieve current state landlord-tenant/eviction statutes, court rules, local housing code, and official forms.",
            "Find controlling federal/state fair-housing rules and administrative filing periods.",
            "Check the exact notice, service, hearing, appeal, and stay rules for the forum and case posture.",
        ),
    ),
    IssueRule(
        id="consumer_protection_product_liability",
        title="Consumer protection, products, and unfair/deceptive practices",
        trigger_terms=(
            "consumer protection", "deceptive trade", "unfair trade practice", "consumer fraud", "warranty",
            "product defect", "debt collection", "false advertising", "subscription cancellation", "consumer contract",
        ),
        issue_question=(
            "Identify the transaction, covered parties, representation or product conduct, reliance/causation where required, "
            "administrative prerequisites, and the statute-specific remedy."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_regulation", "federal_case",
            "state_case", "agency_record", "contract_or_private_rule", "secondary_source",
        ),
        elements_to_verify=(
            "Identify the consumer, seller/manufacturer/debt collector, transaction, product, and statutory coverage.",
            "Determine the precise representation, omission, defect, collection act, warranty, or prohibited practice.",
            "Verify materiality, reliance, causation, injury, notice, pre-suit demand, and class-action requirements if applicable.",
            "Check federal/state preemption, arbitration/forum clauses, limitations, and agency enforcement rules.",
            "Separate actual, statutory, punitive, equitable, warranty, and regulatory remedies and their prerequisites.",
        ),
        evidence_to_collect=(
            "Contracts, advertisements, receipts, disclosures, product/version records, and communications.",
            "Defect/inspection evidence, expert records, consumer notices, payment history, and damages calculations.",
            "Agency complaint, pre-suit demand, arbitration agreement, and relevant online terms as captured at transaction time.",
        ),
        opposing_questions=(
            "Is the claimant a covered consumer and the transaction/practice within the specific statute?",
            "Was the statement actionable, material, and a cause of the claimed injury under forum law?",
            "Do disclaimers, arbitration, safe harbors, preemption, notice, or limitations defenses apply?",
            "Are damages and requested statutory/equitable relief authorized and supported?",
        ),
        research_queries=(
            "Retrieve the current official federal/state consumer statutes, regulations, and historical transaction-date versions.",
            "Find controlling cases on coverage, reliance/causation, defenses, arbitration, and remedies.",
            "Check agency enforcement materials as context, distinguishable from binding law or private rights of action.",
        ),
    ),
    IssueRule(
        id="immigration_nationality",
        title="Immigration, nationality, and cross-border status",
        trigger_terms=(
            "immigration", "deportation", "removal proceeding", "visa", "asylum", "naturalization",
            "citizenship", "immigration detention", "border inspection", "work authorization", "consular decision",
        ),
        issue_question=(
            "Identify the federal immigration posture, agency/court, custody or filing deadlines, source of status, "
            "and any distinct constitutional, statutory, treaty, or review question."
        ),
        authority_lanes=(
            "federal_constitution", "federal_statute", "federal_regulation", "federal_case", "court_rule",
            "treaty", "international_decision", "agency_record", "agency_guidance", "foreign_law",
        ),
        elements_to_verify=(
            "Identify status, application/order, agency or immigration-court stage, custody, counsel, and controlling dates.",
            "Retrieve the operative statute, regulation, agency record, and current circuit/supreme-court precedent.",
            "Check exhaustion, jurisdiction-stripping provisions, filing/service deadlines, detention review, and standard of review.",
            "Separate asylum/withholding/CAT, removal relief, citizenship, consular processing, and constitutional theories.",
            "Verify treaty-party status and domestic implementation; do not assume direct enforceability or private remedy.",
        ),
        evidence_to_collect=(
            "Notices to appear, orders, applications, credible-fear/interview records, custody documents, and A-file materials.",
            "Identity/status documents, translations, country-condition evidence, prior filings, and proof of service.",
            "Docket, hearing calendar, administrative exhaustion record, counsel contacts, and emergency deadlines.",
        ),
        opposing_questions=(
            "Is the tribunal authorized to review this action at this stage, and has the correct remedy been sought?",
            "Were administrative deadlines, exhaustion, and preservation requirements satisfied?",
            "Does the record support eligibility, discretion, credibility, or a protected-ground nexus?",
            "Are treaty provisions self-executing or otherwise implemented and enforceable in this forum?",
        ),
        research_queries=(
            "Retrieve current federal immigration statutes, regulations, official forms, and agency decisions.",
            "Find binding Supreme Court and relevant circuit precedent, then verify later history and emergency orders.",
            "Check detention, petition-for-review, habeas, exhaustion, and filing/service deadlines immediately.",
        ),
    ),
    IssueRule(
        id="bankruptcy_insolvency",
        title="Bankruptcy, insolvency, and creditor-debtor issues",
        trigger_terms=(
            "bankruptcy", "insolvency", "automatic stay", "creditor", "debtor", "foreclosure sale",
            "discharge", "preference", "fraudulent transfer", "proof of claim", "reorganization plan",
        ),
        issue_question=(
            "Identify the bankruptcy case, chapter, stay/status, claimant's capacity, relevant order, and specialized "
            "bankruptcy-court procedure before analyzing a creditor-debtor dispute."
        ),
        authority_lanes=(
            "federal_statute", "federal_case", "court_rule", "state_statute", "state_case",
            "contract_or_private_rule", "agency_record",
        ),
        elements_to_verify=(
            "Identify petition date, chapter, estate property, debtor/creditor status, and bankruptcy-court orders.",
            "Check the automatic stay, discharge injunction, claim allowance, priority, exemptions, and plan terms.",
            "Determine whether the issue is core, related, abstainable, or subject to a jury/withdrawal right.",
            "Research avoidance, transfer, lien, contract, and state-law rights without overlooking federal preemption.",
            "Confirm notice, claim, adversary-proceeding, appeal, and reopening deadlines and the authorized remedy.",
        ),
        evidence_to_collect=(
            "Petition and schedules, docket, stay/order notices, proof of claim, plan, confirmation order, and trustee communications.",
            "Transaction documents, payment history, lien records, valuation, transfer dates, and creditor notices.",
            "Adversary complaint, service, appeal notice, and state-court orders/actions before and after filing.",
        ),
        opposing_questions=(
            "Was the conduct stayed, covered by an exception, authorized by court order, or outside estate property?",
            "Does the bankruptcy court have jurisdiction and authority to grant this form of relief?",
            "Are claim, avoidance, discharge, or appeal deadlines expired or subject to an exception?",
            "Does a plan, confirmation order, discharge, or preclusion doctrine resolve the dispute?",
        ),
        research_queries=(
            "Retrieve the U.S. Bankruptcy Code, Federal Rules of Bankruptcy Procedure, local rules, and case orders.",
            "Find controlling circuit and bankruptcy-court precedent for the precise stay, claim, or avoidance issue.",
            "Check docket events and appeal/adversary deadlines from primary docket records.",
        ),
    ),
)

BUILTIN_ISSUE_RULES: tuple[IssueRule, ...] = ISSUE_RULES + EXPANDED_ISSUE_RULES


def _string_tuple(value: Any, field_name: str, *, minimum: int = 1) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"custom issue rule '{field_name}' must be a list of non-empty strings")
    result = tuple(item.strip() for item in value)
    if len(result) < minimum:
        raise ValueError(f"custom issue rule '{field_name}' must contain at least {minimum} item(s)")
    return result


def load_issue_rules(path: str | Path | None = None) -> tuple[IssueRule, ...]:
    """Return built-ins plus validated custom JSON rules when a path is supplied."""
    if path is None:
        return BUILTIN_ISSUE_RULES
    pack_path = Path(path)
    try:
        payload = json.loads(pack_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read custom issue pack {pack_path}: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("rules")
    if not isinstance(payload, list):
        raise ValueError("Custom issue pack must be a JSON array or an object with a 'rules' array")

    used_ids = {rule.id for rule in BUILTIN_ISSUE_RULES}
    custom: list[IssueRule] = []
    required = {
        "id", "title", "trigger_terms", "issue_question", "authority_lanes",
        "elements_to_verify", "evidence_to_collect", "opposing_questions", "research_queries",
    }
    for index, raw in enumerate(payload, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"custom issue rule {index} must be a JSON object")
        missing = required - set(raw)
        if missing:
            raise ValueError(f"custom issue rule {index} is missing: {', '.join(sorted(missing))}")
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,79}", rule_id):
            raise ValueError(f"custom issue rule {index}.id must be a lower-case identifier with underscores")
        if rule_id in used_ids:
            raise ValueError(f"custom issue rule id '{rule_id}' duplicates a built-in or earlier rule")
        used_ids.add(rule_id)
        title = raw.get("title")
        question = raw.get("issue_question")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"custom issue rule '{rule_id}'.title must be non-empty text")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"custom issue rule '{rule_id}'.issue_question must be non-empty text")
        lanes = _string_tuple(raw.get("authority_lanes"), f"{rule_id}.authority_lanes")
        invalid_lanes = sorted(set(lanes) - AUTHORITY_LAYERS)
        if invalid_lanes:
            raise ValueError(f"custom issue rule '{rule_id}' has unknown authority lane(s): {', '.join(invalid_lanes)}")
        custom.append(IssueRule(
            id=rule_id,
            title=title.strip(),
            trigger_terms=_string_tuple(raw.get("trigger_terms"), f"{rule_id}.trigger_terms"),
            issue_question=question.strip(),
            authority_lanes=lanes,
            elements_to_verify=_string_tuple(raw.get("elements_to_verify"), f"{rule_id}.elements_to_verify"),
            evidence_to_collect=_string_tuple(raw.get("evidence_to_collect"), f"{rule_id}.evidence_to_collect"),
            opposing_questions=_string_tuple(raw.get("opposing_questions"), f"{rule_id}.opposing_questions"),
            research_queries=_string_tuple(raw.get("research_queries"), f"{rule_id}.research_queries"),
        ))
    return BUILTIN_ISSUE_RULES + tuple(custom)
