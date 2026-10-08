"""Transparent issue-spotting rules.

These are research prompts, not statements of governing law. The rules are kept
small and inspectable so reviewers can amend them without retraining a model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IssueRule:
    id: str
    title: str
    trigger_terms: tuple[str, ...]
    issue_question: str
    authority_lanes: tuple[str, ...]
    elements_to_verify: tuple[str, ...]
    evidence_to_collect: tuple[str, ...]
    opposing_questions: tuple[str, ...]
    research_queries: tuple[str, ...]


ISSUE_RULES: tuple[IssueRule, ...] = (
    IssueRule(
        id="administrative_search",
        title="Search, seizure, inspection, and privacy",
        trigger_terms=(
            "inspection", "inspect", "entry", "search warrant", "administrative warrant",
            "without consent", "private residence", "no-knock", "search and seizure",
        ),
        issue_question=(
            "Investigate whether the challenged inspection or entry is a search or seizure, "
            "what constitutional and statutory safeguards govern it, and whether the "
            "authorization and execution fit those safeguards."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_case", "state_case",
            "municipal_code", "county_code", "state_statute", "court_rule",
        ),
        elements_to_verify=(
            "Identify the government actor, place, privacy/property interest, and exact conduct.",
            "Separate consent, emergency, criminal-investigation, and administrative-inspection theories.",
            "Find the forum's governing standard for authorization, neutral review, scope, and execution.",
            "Check whether the rule differs for a home, business, regulated industry, or common area.",
            "Analyze state constitutional protection independently from the federal minimum.",
        ),
        evidence_to_collect=(
            "The operative ordinance/statute and version in force on the event date.",
            "Inspection notice, warrant application/order, sworn supporting facts, and the decision-maker's record.",
            "Consent communications, entry/execution logs, scope limits, and any emergency facts.",
            "Inspection schedules, selection criteria, prior inspections, and communications with law enforcement.",
        ),
        opposing_questions=(
            "Was there valid consent, a recognized emergency, or another independently sufficient basis?",
            "Was the program neutral, limited in scope, and supported by applicable administrative standards?",
            "Does the record show a criminal-investigatory purpose, or only an asserted concern?",
            "What facts distinguish this case from the closest controlling or adverse decision?",
        ),
        research_queries=(
            "Locate current federal and forum-state constitutional text and controlling search/inspection opinions.",
            "Search administrative-inspection decisions by location, purpose, warrant process, scope, and execution.",
            "Find the enabling statute, local enactment, and any controlling state constitutional analogue.",
        ),
    ),
    IssueRule(
        id="delegated_authority",
        title="Delegated power, statutory authority, and ultra vires action",
        trigger_terms=(
            "enabling statute", "authorizing statute", "delegated authority", "statutory authority",
            "without authority", "ultra vires", "municipal code", "ordinance", "charter",
        ),
        issue_question=(
            "Trace the challenged actor's power to an enacted source and test whether the specific "
            "action stayed within the delegation, required procedure, and territorial scope."
        ),
        authority_lanes=(
            "federal_statute", "state_constitution", "state_statute", "state_regulation",
            "county_code", "municipal_code", "local_charter_or_resolution", "state_case",
            "local_administrative_decision",
        ),
        elements_to_verify=(
            "Identify the actor, capacity, source of power, and the exact action taken or proposed.",
            "Read the full delegation, definitions, conditions, exceptions, and effective-date history.",
            "Check whether required notice, findings, hearing, vote, delegation, or rulemaking steps occurred.",
            "Test territorial limits, conflict/preemption, and any home-rule or charter provisions.",
            "Identify the available review route, remedy, limitations period, and any exhaustion rule.",
        ),
        evidence_to_collect=(
            "Current and historical versions of the enabling law, charter, code, rules, and resolutions.",
            "Delegations, appointment records, adopted procedures, votes, findings, notices, and administrative records.",
            "Maps, boundary descriptions, service agreements, and dated records of the challenged action.",
        ),
        opposing_questions=(
            "Is the power express, necessarily implied, or supplied by home rule or another law?",
            "Does a saving clause, later enactment, emergency provision, or valid delegation answer the objection?",
            "Is the alleged defect jurisdictional, procedural, harmless, waived, or curable?",
        ),
        research_queries=(
            "Trace the statute/charter provision through amendments and the implementing regulation or local code.",
            "Find controlling decisions interpreting the exact delegation and limits on the actor or locality.",
            "Search state preemption and home-rule decisions addressing the same subject and remedy.",
        ),
    ),
    IssueRule(
        id="procedural_due_process",
        title="Procedural due process, notice, and hearing",
        trigger_terms=(
            "due process", "notice", "denied a hearing", "hearing was denied", "appeal",
            "property interest", "liberty interest", "deprivation", "without notice",
            "administrative review", "opportunity to be heard",
        ),
        issue_question=(
            "Determine whether a protected interest and government deprivation are present, "
            "what process was due in this posture, and whether available pre- or post-deprivation "
            "review changes the analysis."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_case", "state_case",
            "state_statute", "state_regulation", "municipal_code", "county_code", "court_rule",
        ),
        elements_to_verify=(
            "Identify the asserted property or liberty interest and the source that creates it.",
            "Define the government action, timing, finality, and whether the deprivation is contested.",
            "Map notice, opportunity to respond, decision-maker, reasons, and available review.",
            "Check emergency, pre-deprivation impracticability, and adequate post-deprivation process doctrines.",
            "Identify the required prejudice, causation, and remedy in the forum.",
        ),
        evidence_to_collect=(
            "Notices, service records, deadlines, hearing recordings/minutes, findings, and appeal instructions.",
            "Policies, actual decision sequence, written reasons, and communications about the affected interest.",
            "The specific loss, its date, and any available administrative or judicial review.",
        ),
        opposing_questions=(
            "Is the claimed interest protected by law, or merely an expectation or discretionary benefit?",
            "Was meaningful process available before or after the action, and was it used or waived?",
            "Was the decision final, caused by the defendant, and actionable in this procedural posture?",
        ),
        research_queries=(
            "Find controlling federal and state procedural due-process tests for this interest and type of decision.",
            "Search the governing statute, local code, agency rules, and judicial-review deadlines.",
            "Check emergency and post-deprivation cases and the remedies available in this forum.",
        ),
    ),
    IssueRule(
        id="equal_protection_selective_enforcement",
        title="Equal protection, comparator evidence, and selective enforcement",
        trigger_terms=(
            "equal protection", "selective enforcement", "similarly situated", "disparate treatment",
            "unequal", "discrimination", "different treatment", "comparator",
        ),
        issue_question=(
            "Test the asserted difference in treatment against the applicable constitutional or statutory "
            "standard; do not infer unlawful intent from unequal outcomes alone."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_statute", "state_statute",
            "federal_case", "state_case", "local_administrative_decision", "agency_record",
        ),
        elements_to_verify=(
            "Identify the protected classification, right, enforcement context, and governing level of scrutiny or test.",
            "Define genuinely comparable persons/properties and the relevant time, location, and conditions.",
            "Separate outcome disparity from discriminatory purpose or other required intent evidence.",
            "Check statutory anti-discrimination, retaliation, and selective-enforcement routes separately.",
            "Map causation, defenses, available relief, and any limitations or exhaustion rules.",
        ),
        evidence_to_collect=(
            "Comparator cases, enforcement logs, written criteria, exception records, and outcome data.",
            "Decision-maker communications, contemporaneous reasons, and evidence of neutral explanations.",
            "A consistent denominator and time window for any quantitative comparison.",
        ),
        opposing_questions=(
            "Are the proposed comparators alike in the legally material respects?",
            "Could workload, risk, timing, complaint source, or another neutral criterion explain the difference?",
            "What evidence supports the required intent or classification-specific element?",
        ),
        research_queries=(
            "Find the forum's comparator, intent, and scrutiny rules for this exact claim type.",
            "Search controlling decisions on selective enforcement and the evidence they require.",
            "Identify parallel statutory protections and their administrative exhaustion requirements.",
        ),
    ),
    IssueRule(
        id="property_takings_land_use",
        title="Property rights, land use, and possible takings theories",
        trigger_terms=(
            "taking", "regulatory taking", "compensation", "property value", "permit denial",
            "land use", "land-use", "property interest", "deprivation of property", "easement",
        ),
        issue_question=(
            "Screen for a property-based claim only after identifying the protected property interest, "
            "the final government action, the applicable test, and the procedural vehicle."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_case", "state_case",
            "federal_statute", "state_statute", "state_regulation", "municipal_code", "county_code",
        ),
        elements_to_verify=(
            "Define the property interest under applicable state law and the precise government action.",
            "Check finality, ripeness, exhaustion, and any required application/variance process.",
            "Identify which categorical or fact-specific takings framework, if any, could apply.",
            "Test economic effect, expectations, character of action, background principles, and available defenses.",
            "Separate a taking theory from due process, permit, contract, and statutory claims.",
        ),
        evidence_to_collect=(
            "Title, parcel history, permits/applications, final decisions, conditions, and appeal record.",
            "Before/after valuation and use evidence tied to a qualified method, not an unsupported estimate.",
            "Investment-backed expectations, existing regulations, comparable uses, and duration of any restriction.",
        ),
        opposing_questions=(
            "Is there a final decision and a cognizable property interest, or is the dispute premature?",
            "Does the action leave viable uses, implement a background property principle, or fall within a relevant exception?",
            "Is the claimed loss caused by government action and supported by admissible evidence?",
        ),
        research_queries=(
            "Find controlling federal and state takings decisions for the type of property action and remedy.",
            "Trace state property law, land-use statutes, local enactments, and required administrative steps.",
            "Search cases applying finality, ripeness, valuation, and background-principles limits.",
        ),
    ),
    IssueRule(
        id="local_power_preemption",
        title="Federalism, local power, preemption, boundaries, and home rule",
        trigger_terms=(
            "preemption", "preempt", "home rule", "annexation", "county pocket", "city boundary",
            "municipal", "county", "extraterritorial", "local ordinance", "jurisdictional boundary",
        ),
        issue_question=(
            "Map the geographic and subject-matter authority of each government, then test any claimed "
            "conflict, preemption, boundary, or home-rule issue under the governing state and federal rules."
        ),
        authority_lanes=(
            "federal_constitution", "federal_statute", "federal_regulation", "state_constitution",
            "state_statute", "state_regulation", "state_case", "county_code", "municipal_code",
            "local_charter_or_resolution", "federal_case",
        ),
        elements_to_verify=(
            "Locate the property/action and fix the relevant dates, boundaries, actors, and government services.",
            "Identify the source and limits of city, county, state, and federal authority for each action.",
            "Analyze express, field, and conflict preemption only where the governing doctrine makes them relevant.",
            "Check home-rule text, enabling statutes, annexation procedures, notice, findings, and service plans.",
            "Separate fiscal or policy disagreement from a legally enforceable duty or limit.",
        ),
        evidence_to_collect=(
            "Official maps, legal descriptions, annexation instruments, plats, service agreements, and effective dates.",
            "Current and historical statutes, charter provisions, ordinances, plans, and adopted findings.",
            "Records establishing who provided, funded, authorized, or regulated each service or decision.",
        ),
        opposing_questions=(
            "Does state law affirmatively authorize the action, and is there an actual legal conflict?",
            "Could different tax, service, or land-use treatment follow from lawful boundaries or classifications?",
            "Is the asserted duty enforceable by this party, through this remedy, at this stage?",
        ),
        research_queries=(
            "Find the state constitution, statutes, and controlling cases governing county/city powers and home rule.",
            "Trace the actual enactment and boundary record; compare effective dates and required procedures.",
            "Search federal and state preemption only for the specific regulated subject and forum.",
        ),
    ),
    IssueRule(
        id="choice_of_law_and_sovereign_jurisdiction",
        title="Choice of law, sovereign jurisdiction, and cross-border authority",
        trigger_terms=(
            "choice of law", "conflict of laws", "foreign law", "tribal jurisdiction", "tribal law",
            "interstate compact", "jurisdictional conflict", "comity", "cross-border",
        ),
        issue_question=(
            "Determine which sovereign's law and forum govern each issue; do not assume that the place, "
            "party, or source with the strongest connection supplies the rule without applying the forum's conflicts framework."
        ),
        authority_lanes=(
            "federal_constitution", "federal_statute", "federal_case", "state_constitution", "state_statute",
            "state_case", "tribal_law", "foreign_law", "interstate_compact", "treaty",
        ),
        elements_to_verify=(
            "Identify each sovereign, territory, forum, party, claim, and event location/date.",
            "Apply the forum's choice-of-law method issue by issue, including any statutory directive or public-policy limit.",
            "For tribal-law questions, research tribal authority, territorial/personal jurisdiction, and federal/state interactions.",
            "For foreign law, establish the content and status of the asserted law and the forum's proof procedure.",
            "For interstate compacts, verify enacted text, participating jurisdictions, effective date, and enforcement route.",
        ),
        evidence_to_collect=(
            "Domicile, location, contacts, contracts/choice clauses, conduct, injury, and sovereign-status facts.",
            "Official tribal or foreign legal text, translations/version, compact text, ratification and implementation records.",
            "The forum's conflicts statute, court rule, and decisions applying the relevant test.",
        ),
        opposing_questions=(
            "Does the forum have authority over the parties and subject, and does another sovereign's law actually govern?",
            "Could the relevant rule be procedural, territorially limited, preempted, or inconsistent with the forum's conflicts rules?",
            "Has the proponent established the content, applicability, and enforceability of the non-forum law?",
        ),
        research_queries=(
            "Find the forum's current choice-of-law test and decisions applying it to this claim type.",
            "Check jurisdiction-specific tribal, foreign-law, compact, and comity sources from official materials.",
            "Map any federal preemption, treaty, recognition, or implementation question separately.",
        ),
    ),
    IssueRule(
        id="administrative_review",
        title="Administrative law, finality, record review, and deadlines",
        trigger_terms=(
            "agency decision", "administrative record", "arbitrary and capricious", "final agency action",
            "exhaustion", "judicial review", "administrative appeal", "rulemaking", "agency order",
        ),
        issue_question=(
            "Identify the correct review statute and record-based standard before characterizing an "
            "administrative decision as unlawful, arbitrary, or unsupported."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_regulation", "federal_case",
            "state_case", "local_administrative_decision", "agency_record", "court_rule",
        ),
        elements_to_verify=(
            "Identify the agency/body, statutory review route, finality, standing, and applicable deadline.",
            "Determine exhaustion requirements and any recognized exception in the controlling forum.",
            "Obtain and index the complete record, findings, notice, and preserved objections.",
            "Use the correct standard of review and distinguish record review from a new evidentiary case.",
            "Identify remedies, stays, remand options, and preservation requirements.",
        ),
        evidence_to_collect=(
            "Complete certified administrative record, docket, orders, findings, transcript, exhibits, and notices.",
            "The enabling/review statute, procedural rules, local rules, and deadline computation.",
            "Preserved objections, reconsideration requests, exhaustion steps, and proof of service.",
        ),
        opposing_questions=(
            "Is the action final and reviewable, or is further agency process available or required?",
            "Does the record support the agency's stated rationale under the correct review standard?",
            "Was an objection waived, harmless, untimely, or outside the permitted record?",
        ),
        research_queries=(
            "Locate the current review statute, agency rules, court rules, and local filing rules.",
            "Find controlling decisions on finality, exhaustion, preservation, and the exact standard of review.",
            "Check limitations periods and available temporary or final relief from primary sources.",
        ),
    ),
    IssueRule(
        id="municipal_civil_rights",
        title="Civil-rights claims and municipal/official liability",
        trigger_terms=(
            "section 1983", "1983", "monell", "municipal liability", "policy or custom",
            "official policy", "failure to train", "state actor", "under color of law",
        ),
        issue_question=(
            "Separate the underlying rights question, each defendant's capacity, causation, and the "
            "distinct rules for individual, municipal, and prospective-relief claims."
        ),
        authority_lanes=(
            "federal_constitution", "federal_statute", "federal_case", "state_case", "state_statute",
            "municipal_code", "agency_record", "court_rule",
        ),
        elements_to_verify=(
            "Identify the asserted federal right, state action, each defendant, capacity, and causal conduct.",
            "For municipal liability, test the applicable policy/custom, attribution, and moving-force requirements.",
            "For individual liability, research the elements, defenses, and any immunity issues separately.",
            "For prospective relief, check standing, ongoing injury, causation, and proper defendant requirements.",
            "Check limitations, venue, exhaustion, and the precise remedy authorized by the claim.",
        ),
        evidence_to_collect=(
            "Written policies, repeated practices, final policymaker decisions, training records, and similar incidents.",
            "Actor-specific communications, decision records, causation evidence, and proof of injury.",
            "The procedural history, requested relief, and facts bearing on defenses or immunity.",
        ),
        opposing_questions=(
            "Is there an underlying constitutional violation, and is it attributable to each defendant?",
            "Is the alleged practice a policy/custom rather than an isolated event, and is causation shown?",
            "Do immunity, standing, limitations, or remedial rules foreclose or narrow the claim?",
        ),
        research_queries=(
            "Find current Supreme Court and controlling circuit decisions for each distinct liability route.",
            "Search the forum's municipal-liability, causation, policymaker, and immunity decisions.",
            "Verify claim-specific limitations and remedies from current primary authority.",
        ),
    ),
    IssueRule(
        id="open_government",
        title="Open meetings, public records, and government transparency",
        trigger_terms=(
            "public records", "records request", "open meetings", "meeting notice", "executive session",
            "minutes", "agenda packet", "public comment", "public records act",
        ),
        issue_question=(
            "Identify the applicable transparency statute, covered body or record, applicable exception, "
            "required procedure, and available enforcement route."
        ),
        authority_lanes=(
            "state_constitution", "state_statute", "state_regulation", "state_case", "county_code",
            "municipal_code", "local_charter_or_resolution", "local_administrative_decision",
        ),
        elements_to_verify=(
            "Determine whether the entity, gathering, communication, or record is covered by the law.",
            "Check notice, agenda, access, minutes, response, retention, and deadline requirements.",
            "Analyze each claimed exception separately and locate the exact statutory text.",
            "Identify standing, administrative prerequisites, remedies, and any fee/cost provisions.",
        ),
        evidence_to_collect=(
            "Requests, acknowledgments, production logs, redactions, notices, agendas, minutes, and recordings.",
            "Calendars, attendance, communications, retention schedules, and the claimed exception's basis.",
            "The then-current statute/rule and any agency or court interpretation.",
        ),
        opposing_questions=(
            "Is the body or material within the statute's defined scope?",
            "Does a specific exception apply, and were segregation and required findings handled correctly?",
            "Was the request timely, properly submitted, or subject to a cure/appeal procedure?",
        ),
        research_queries=(
            "Find the current state public-records and open-meetings statutes and implementing rules.",
            "Search controlling decisions on the exact body, record, exception, deadline, and remedy.",
            "Check local retention, notice, and appeal procedures without treating policy as statute.",
        ),
    ),
    IssueRule(
        id="international_law_gate",
        title="International law applicability gate",
        trigger_terms=(
            "international law", "treaty", "convention", "customary international law",
            "human rights treaty", "united nations", "international tribunal", "soft law",
        ),
        issue_question=(
            "Treat the international source as a research lane, then establish whether and how it applies "
            "in the domestic forum; do not assume that a treaty, decision, or declaration creates a "
            "directly enforceable claim."
        ),
        authority_lanes=(
            "treaty", "customary_international_law", "international_decision", "international_soft_law",
            "federal_constitution", "federal_statute", "federal_case", "state_case",
        ),
        elements_to_verify=(
            "Identify the exact instrument, parties, entry-into-force date, reservations, and applicable text.",
            "Research domestic status, self-execution or implementation, private enforceability, and forum rules.",
            "For custom, document state practice and opinio juris from reliable sources rather than assertion.",
            "Classify decisions, declarations, resolutions, and guidance as binding or persuasive only after source review.",
            "Analyze conflicts with domestic law and any jurisdictional or remedial limitations.",
        ),
        evidence_to_collect=(
            "Official treaty text, ratification/accession record, reservations, and effective dates.",
            "Implementing legislation, relevant domestic decisions, and the actual forum/jurisdiction.",
            "For customary-law claims, cited state practice and legal-opinion materials with dates and provenance.",
        ),
        opposing_questions=(
            "Is the instrument binding on the relevant state and in force for the relevant time and subject?",
            "Is there domestic implementation or a recognized path to judicial enforcement?",
            "Is the cited item a nonbinding declaration or policy document rather than a source of enforceable law?",
        ),
        research_queries=(
            "Verify the instrument and party status in an official treaty collection and the relevant domestic record.",
            "Find domestic decisions addressing enforceability, implementation, reservations, and conflict rules.",
            "For customary international law, identify authoritative evidence of practice and opinio juris.",
        ),
    ),
    IssueRule(
        id="statutory_interpretation",
        title="Statutory and regulatory interpretation",
        trigger_terms=(
            "statutory interpretation", "legislative history", "plain text", "ambiguous statute",
            "statutory construction", "definition in statute", "agency interpretation",
        ),
        issue_question=(
            "Read the operative text in its full statutory/regulatory context and identify the interpretive "
            "method and precedent actually used by the forum."
        ),
        authority_lanes=(
            "federal_statute", "federal_regulation", "state_statute", "state_regulation", "state_case",
            "federal_case", "legislative_history", "agency_guidance", "secondary_source",
        ),
        elements_to_verify=(
            "Use the version effective on the relevant date and compare enrolled/session law where needed.",
            "Read definitions, neighboring provisions, cross-references, exceptions, and the whole statutory scheme.",
            "Separate binding text and holdings from legislative history, agency guidance, and commentary.",
            "Identify the forum's current interpretive rules and the treatment of agency interpretations.",
        ),
        evidence_to_collect=(
            "Official enacted text, amendments, effective dates, regulations, and incorporated materials.",
            "Relevant administrative interpretations and the record showing how the agency applied the text.",
            "Legislative history only when relevant under the forum's interpretive method.",
        ),
        opposing_questions=(
            "Does context or a specific definition undermine a reading based on an isolated phrase?",
            "Is the proposed interpretation consistent with the rest of the law and controlling precedent?",
            "Is an agency view authorized, persuasive, or otherwise relevant under current law?",
        ),
        research_queries=(
            "Retrieve official historical and current text and the enactment/session law.",
            "Find controlling appellate decisions interpreting the exact text and relevant neighboring provisions.",
            "Check current agency interpretations and distinguish binding rules from guidance or commentary.",
        ),
    ),
    IssueRule(
        id="criminal_procedure",
        title="Criminal procedure and suppression-related questions",
        trigger_terms=(
            "criminal warrant", "probable cause", "arrest", "suppression", "exclusionary rule",
            "criminal proceeding", "criminal investigation", "search incident to arrest",
        ),
        issue_question=(
            "If criminal process is implicated, identify the specific search, seizure, statement, or charging "
            "event and analyze its distinct constitutional, statutory, and procedural rules."
        ),
        authority_lanes=(
            "federal_constitution", "state_constitution", "federal_statute", "state_statute",
            "federal_case", "state_case", "court_rule", "agency_record",
        ),
        elements_to_verify=(
            "Separate the criminal and administrative tracks and identify the actor, event, and legal purpose.",
            "Determine the applicable warrant, exception, notice, execution, and suppression doctrines.",
            "Check preservation, motion deadlines, standing, harmless error, and available remedy.",
            "Distinguish a search's legality from admissibility, civil liability, and the underlying regulatory action.",
        ),
        evidence_to_collect=(
            "Warrants/affidavits, dispatch and body-camera logs, reports, chain of custody, and hearing transcripts.",
            "Facts supporting any claimed exception and the timing/sequence of administrative and criminal actions.",
            "The charging instrument, docket, deadlines, and preserved objections.",
        ),
        opposing_questions=(
            "Does the claimant have standing to challenge the search, and did a valid exception apply?",
            "Was the issue preserved, and would exclusion or another remedy follow even if a violation occurred?",
            "Was evidence obtained independently or through a separate lawful path?",
        ),
        research_queries=(
            "Find controlling federal and state cases for the exact search, seizure, exception, and remedy.",
            "Check current criminal procedure/evidence rules, local rules, and motion deadlines.",
            "Research administrative/criminal coordination only from facts in the record, not inference alone.",
        ),
    ),
    IssueRule(
        id="contract_tort_property",
        title="Contract, tort, and other private-law routes",
        trigger_terms=(
            "contract", "breach", "negligence", "duty of care", "damages", "tort", "promise",
            "agreement", "reliance", "estoppel", "property damage",
        ),
        issue_question=(
            "Screen for a separate private-law route without treating a policy disagreement or an informal "
            "assurance as a contract, tort, or enforceable promise by default."
        ),
        authority_lanes=(
            "state_statute", "state_case", "federal_statute", "federal_case", "contract_or_private_rule",
            "municipal_code", "county_code",
        ),
        elements_to_verify=(
            "Identify the legal relationship, duty, promise, breach, causation, damages, and available defenses.",
            "Check governmental immunity, notice-of-claim rules, authorization to contract, and capacity.",
            "Separate estoppel, reliance, contract, negligence, and constitutional theories and their elements.",
            "Establish limitations, forum, damages restrictions, and any required administrative steps.",
        ),
        evidence_to_collect=(
            "Executed agreements, authorized signatures, written representations, consideration, and performance.",
            "Contemporaneous reliance, notice, loss calculations, causation, and mitigation records.",
            "Immunity, claim-notice, delegation, and limitation-period documents.",
        ),
        opposing_questions=(
            "Did a person with authority make an enforceable promise or assume a legal duty?",
            "Is reliance reasonable and causally connected to a measurable loss?",
            "Do immunity, disclaimer, statutory procedure, or limitations bar the route?",
        ),
        research_queries=(
            "Find current state elements and defenses for each potentially distinct private-law theory.",
            "Check governmental immunity, notice-of-claim, and public-contract authorization statutes.",
            "Search remedies and limitations for the specific defendant and relief requested.",
        ),
    ),
)


GLOBAL_RED_TEAM_CHECKS: tuple[str, ...] = (
    "Write the strongest competing factual narrative, including a neutral or lawful explanation for the challenged conduct.",
    "Identify the element, factual inference, and source most likely to defeat or narrow the proposed theory.",
    "Search for the strongest contrary authority, exceptions, limiting holdings, and adverse subsequent treatment.",
    "Check whether each factual assertion has a primary record citation and what evidence could falsify it.",
    "Separate proof of a legal violation from causation, attribution, injury, and entitlement to a particular remedy.",
)


NOVELTY_PROTOCOL: tuple[str, ...] = (
    "State the existing rule and cite a verified primary source with a pinpoint citation.",
    "Locate the closest controlling and persuasive cases; compare legally material facts, not labels.",
    "Explain the proposed doctrinal bridge and the strongest factual/doctrinal disanalogy.",
    "Develop the best opposing argument and identify authority that would defeat or narrow the theory.",
    "Specify additional facts, evidence, procedural vehicle, and remedy required to present the theory.",
    "State a falsifier: what new fact or authority would show the theory should not be advanced?",
)
