# Authority, jurisdiction, and research-quality model

## Do not model law as one flat list or universal score

A useful legal research engine must record **what a source is, where it applies, what issue it addresses, when it was in force, which tribunal is deciding the question, and whether it is binding or persuasive there**. A universal numeric ranking such as “federal = 100, state = 80, city = 40” would be misleading.

For U.S. matters, constitutional provisions, statutes, treaties, regulations, common law, local enactments, and court decisions interact through issue-specific rules: federal/state subject matter, preemption, state home rule and delegation, forum, territorial scope, effective dates, and the procedural posture. County and municipal enactments are especially dependent on their source of power and geographic limits. State constitutional law may provide independently relevant protection. International sources require their own applicability and domestic-enforceability analysis.

The prototype therefore stores `layer`, `jurisdiction`, `court_or_body`, `bindingness`, `treatment`, dates, `issue_tags`, verification status, and pin cite separately. It does **not** decide that a source controls merely because a record is tagged `binding` or `controlling`; those values are user-entered and must be checked by a researcher.

## Authority and materials to consider

These are research lanes, not a requirement that every case use every source:

1. **Constitutional sources:** applicable national/federal and state constitutions; relevant constitutional amendments and state constitutional provisions.
2. **Legislation:** enacted federal and state statutes, session/enrolled laws, local enabling acts, county ordinances/resolutions, municipal codes, charters, and annexation instruments.
3. **Regulations and administrative materials:** validly adopted federal/state/local regulations, agency adjudications and orders, the administrative record, policies, guidance, manuals, and enforcement criteria. Distinguish binding rules from nonbinding guidance and evidence about how a decision was made.
4. **Case law / jurisprudence:** supreme/high-court decisions, intermediate appellate decisions, federal circuit/district decisions, specialized courts, and relevant out-of-jurisdiction decisions. Track court, date, publication/precedential status, issue, holding, pinpoint, later history, and contrary treatment.
5. **Procedural and evidentiary law:** civil/criminal/administrative procedure, appellate rules, local court rules, evidence rules, filing/service requirements, preservation, burdens, standards of review, and remedies.
6. **International law:** treaty text and status, ratification/accession, reservations/declarations, entry into force, implementation, customary international law (including evidence of state practice and opinio juris), international court decisions, and nonbinding declarations/soft law. Do not presume direct enforceability or a private cause of action.
7. **Tribal, foreign, and compact law:** tribal constitutions/codes/cases and jurisdictional materials; foreign domestic law where choice-of-law makes it relevant; and interstate compact text and implementing enactments. Analyze sovereign reach, forum, conflicts rules, and the applicable federal/state/tribal or foreign-law relationship rather than assuming a simple hierarchy.
8. **Other substantive routes:** property, land use, tax, environmental, labor/employment, procurement, contract, tort, civil rights, criminal, election, public-records, open-meetings, and remedies law as triggered by the facts.
9. **Persuasive / contextual sources:** treatises, restatements, law reviews, legislative history, technical standards, model codes, and policy materials. Label these as secondary or contextual; do not represent them as enacted or controlling law.

The `layer` field records the source family; `issue_tags` record the legal question(s) to which a person has mapped that source. These concepts must not be conflated.

## Required source record

For every proposed authority, capture at least:

- complete citation and pinpoint (page, section, paragraph, or reporter page);
- source type/layer, issuing jurisdiction, court or body, and date;
- official or best available primary-source URL and, where available, a captured copy/version hash; the ingestion workflow records hashes for local source files and can optionally archive a verified copy;
- effective/enactment dates for statutes and regulations;
- court and precedential status for cases, with publication and later-history fields;
- proposition or holding supported, adverse, distinguishing, or neutral;
- issue tag and an explicit note on why it is relevant;
- verification status: citation, primary text, currentness, and subsequent treatment checked separately.

A search-result snippet, AI-generated memo, news story, commentary, case headnote, or user summary may lead to a source. It is not itself a verified holding. Explicit connectors can retrieve discovery records; they do not certify the official opinion, holding, currentness, bindingness, or subsequent treatment.

## International-law applicability gate

An international-law mention should create a review task, not an automatic claim. Researchers should establish the exact instrument/rule, applicable parties, time, reservations or declarations, domestic implementation, self-execution/enforceability where relevant, private right of action, forum, conflicts with domestic law, and available remedy. A resolution or declaration may be influential or persuasive without being binding. For customary international law, the source trail should show state practice and opinio juris rather than merely repeat a conclusion.

## Current primary-source starting points

Use the relevant government's current official source and preserve the version/date used. The following links are starting points, not a complete source database or legal opinion:

- U.S. Constitution text: [National Archives transcription](https://www.archives.gov/founding-docs/constitution-transcript). Use annotations (such as the Congressional Research Service's Constitution Annotated) for research, but distinguish commentary from the constitutional text and judicial holdings.
- U.S. Code: [Office of the Law Revision Counsel, U.S. House](https://uscode.house.gov/).
- Federal regulations and rulemaking history: [eCFR](https://www.ecfr.gov/) and [Federal Register](https://www.federalregister.gov/). The eCFR is updated frequently but should not be mistaken for the official published CFR; verify effective text and amendments in the Federal Register/official CFR materials.
- U.S. Supreme Court opinions: [Supreme Court opinions](https://www.supremecourt.gov/opinions/opinions.aspx); use the official opinion/report and pin cite rather than an aggregator's summary.
- Wyoming statutes and Constitution: [Wyoming Legislature — State Statutes & Constitution](https://www.wyoleg.gov/stateStatutes/StateStatutes) and its [official downloadable title PDFs](https://www.wyoleg.gov/stateStatutes/StatutesDownload). The download page currently describes a 2026 Budget Session edition reflecting the law as of July 1, 2026; verify session/enrolled laws and event-date effectiveness.
- Wyoming appellate opinions and rules: [Wyoming Judicial Branch — Supreme Court opinions](https://www.wyocourts.gov/wy-supreme-court-opinions/). The official site search has limits; an aggregator hit is a discovery lead, not an official opinion.
- Local enactments: obtain the official city/county adopted text, ordinance history, charter, maps, and effective dates from the government/court record. Publisher codifications and aggregator copies are useful search tools, but confirm updates against the adopted law and official record.
- Treaty text/status: [United Nations Treaty Collection](https://treaties.un.org/) and the U.S. Department of State's treaty-affairs materials; verify party status and dates from the relevant depositary/government source.
- Secondary case search/citator services may aid discovery, but every important authority should be checked in primary text and for negative treatment.

## Provenance, evidence review, and graph edges

The packet can retain an original file's SHA-256 and byte size alongside extractor name, categorical extraction status, capture time, and page/paragraph/line/timestamp locators. OCR output is flagged as unreviewed, and the source binary is not rewritten. DOCX uses paragraph/table locators rather than implying stable pagination.

Facts may carry a separate qualitative evidence assessment (strength, authenticity, directness, corroboration), but each non-default assessment requires a named reviewer and rationale. The engine never calculates an evidence score. Research links connect fact or authority IDs to issue/element IDs; proposed, reviewed, and rejected edges remain distinct and auditable. Only human-reviewed, resolvable edges are surfaced as reviewed mappings.

The source-search connectors include National Archives Constitution text, exact-citation OLRC U.S. Code lookup, eCFR/Federal Register search, official Wyoming title PDFs, and user-supplied local corpora. CourtListener is an optional case-law discovery/citing-opinion index, not an official court source or guaranteed citator. Provider calls are explicit; the offline analyzer does not search.

## Quality gates before a legal theory is presented

1. Fix the jurisdiction(s), forum, act date(s), procedural posture, and requested remedy.
2. Authenticate facts and resolve every important factual proposition to a source locator; distinguish allegations, inferences, agreed facts, and adjudicated facts.
3. Identify the legal elements, burdens, standards, defenses, and threshold procedural requirements for each theory.
4. Retrieve primary law, pin-cite the rule, verify currentness and treatment, and map binding versus persuasive status for the forum.
5. Search for contrary authority, exceptions, and the strongest non-violation explanation.
6. For a novel/analogical theory, state a principled bridge and disanalogy, test falsifiers, and explain the procedural vehicle/remedy.
7. Have qualified counsel review high-stakes or filing-ready work. The software cannot supply professional judgment or a complete research search.
