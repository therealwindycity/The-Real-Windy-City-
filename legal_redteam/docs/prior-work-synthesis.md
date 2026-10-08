# Prior-work synthesis and design decisions

## Drive materials reviewed

This prototype was shaped by a targeted review of the user's connected Google Drive/Docs material, including:

- The Google Doc titled **“Promethean OS: Paradox Engine (Universal Municipal Binary-Trap Framework)”** (in the October 3, 2026 Gemini export).
- The Google Doc **“Ordinance Vulnerabilities: Red Team Analysis.”**
- The PDF **“Geminiexportedchats80pagesoct1.pdf,”** used as evidence of the existing workflow and the kind of mixed fact, inference, legal theory, and strategy text the tool may be asked to review.

The repository contains only a synthetic example. No case-specific facts, private records, allegations, names, or Drive file contents were copied into this codebase.

## What is retained

The Paradox Engine's five-vector idea is useful as an intake scaffold. It was mapped into these fields:

| Prior vector | New representation | Reason for adjustment |
|---|---|---|
| Target entity / official | Actor + alleged source of duty/authority/capacity | An actor's title alone does not establish duty, policymaking status, or liability. |
| Statutory / code basis | Multi-layer authority inventory | A case may implicate constitutions, statutes, regulations, court rules, local enactments, cases, treaties, agency records, and secondary sources. |
| Operational / factual reality | Dated fact records with source, locator, and status | A statement in a memo or AI export is not automatically an established fact. |
| Legal paradox / trap | Candidate issue or competing theory | Tension can identify a question, but it does not itself prove illegality, a taking, discrimination, or a procedural defect. |
| Strategic / procedural setting | Forum, jurisdiction, posture, date, deadlines, and remedy | Forum and procedural posture affect applicable authority, burdens, preservation, and available relief. |

The red-team analysis document also demonstrates a productive multi-source pattern: compare enacted text, legislative/administrative records, testimony, and controlling jurisprudence rather than relying on a single narrative.

## What is deliberately changed

The prior framework's “Admission → Hook → Checkmate” and “no escape clause” output is **not** carried forward. A forced binary choice may be inaccurate, legally irrelevant, or strategically counterproductive; an official's answer or silence is not automatically a legal admission. The prototype instead asks neutral, answerable questions, maps every theory to elements and evidence, and presents the strongest opposing account beside the supporting theory.

The existing ordinance analysis also uses legal conclusions and broad claims about doctrinal consequences. The prototype treats those as **propositions to test**, not source authority. A robust workflow must:

1. retrieve the primary text and version in force at the operative date;
2. cite the relevant holding/rule and pinpoint, not just a case name;
3. verify court, jurisdiction, precedential status, later history, and contrary authority;
4. separate criminal probable-cause analysis from administrative-search standards where relevant;
5. compare the actual facts to the nearest cases and identify both analogy and disanalogy; and
6. identify procedural gates and remedies before drafting a conclusion.

A phrase such as “clearly unconstitutional,” “automatic,” “deliberate,” or “designed to” can be a useful search lead but is not proof. The self-red-team wording flags are prompts to verify the record and alternatives; they are not truth determinations.

## Novel and untried theories

The program should be able to help develop an argument whose exact factual configuration has not previously been litigated. But it cannot infer that a legal theory is novel just because the input packet contains no exact-match case. The research record must show:

- the existing legal rule and verified source;
- the closest controlling and persuasive analogies;
- the factual and doctrinal bridge;
- meaningful distinctions and contrary authority;
- additional facts/evidence needed;
- a procedural vehicle and legally available remedy; and
- a falsifier that would show the theory should not be advanced.

Until that work is documented, the status remains `unassessed`. Novelty is not the same as legal validity, a cause of action, or likelihood of success.

## Resulting design

The first implementation is intentionally conservative and inspectable: a local Python CLI, typed source/fact/authority fields, a transparent issue-rule catalog, a report generator, and tests. The next phase should add official source retrieval and citation treatment checks before adding any model-based theory drafting. The authority system is a contextual graph, not a single numeric “law rank” score.
