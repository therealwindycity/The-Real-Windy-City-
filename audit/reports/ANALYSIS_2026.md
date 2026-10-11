# Cheyenne Governing Body: Multi-Source Analysis, 2026

_Generated 2026-10-11 by `audit/build_analysis.py`. Deterministic; rerun to reproduce._

> **Read this first.** This report cross-checks three independent records of the same meetings: the YouTube caption transcripts, the official agendas, and the approved minutes. Captions are machine-generated and misspell names and statute numbers. Minutes text is PDF extraction and has spacing artifacts. Every finding below is a **lead for human review**, linked to its source, and not a conclusion. **Legal claims made by speakers are their allegations**; this report records that they were made, not whether they are correct.

## 1. What changed from v1

v1 was a keyword classifier that read one transcript passage at a time. v2 adds four layers on top of it:

| Layer | v1 | v2 |
|---|---|---|
| Sources | Captions only | Captions + 51 official meetings (1,800 agenda items, 47 minutes documents) |
| Unit of analysis | 1,200-character passage | Agenda item, with start/end time, outcome, vote and ordinance number |
| Who is speaking | Unknown | Each segment labelled as agenda reading, public comment or official |
| Legal language | Keyword hit | Claim: assertion type, polarity (asserted or denied), cited authority, item, outcome, candidate official response |
| Procedure | Keyword hit | Eight reconciliation checks (R1–R8) between the records |
| Votes | Not measured | Member-level voting record, contested votes, pairwise agreement |
| False positives | Stormwater 'detention', verb 'warrant' | Context exclusions in the lexicon (v2026.10.2); clerk readings of agenda titles down-weighted |

## 2. Headline numbers

| Measure | Value |
|---|---|
| Council meetings aligned to their official agenda | 17 |
| Agenda items located in the video (start/end) | 264 |
| …of which joined to a minutes entry (outcome + vote) | 203 |
| Legal-claim sentences detected | 244 |
| …asserted (not denied) | 230 |
| …strong (cites an authority, makes more than one kind of allegation, says 'unconstitutional', or alleges preemption or action without authority) | 48 |
| …made during public comment | 168 |
| …made by officials or staff | 62 |
| Denials (e.g. "this is not a violation") | 14 |
| Public-comment claims with a candidate official response in the same item | 72 |
| Reconciliation checks run | 215 |
| Reconciliation exceptions (leads) | 67 |
| Contested roll-call votes in 2026 minutes | 79 |
| Tie votes | 2 |
| Passages flagged: v1 → v2 | 240 → 221 |

## 3. Ordinance lifecycles (R2)

93 ordinances were traced across readings in the 2025–2026 minutes. 80 reached adoption at third reading in the window, and 22 have a feature worth a look: a failed reading, repeated postponement, a substitute at third reading, or a reading with no recorded predecessor (usually because the earlier reading falls before January 2025).

| First | Last | Ordinance | Readings | Adopted | Flags |
|---|---|---|---|---|---|
| 2025-01-27 | 2025-02-24 | ORDINANCE-1st READING - Amending various sections within Chapter 8.12, Internat… | 1→2→3 | yes 4614 | amended by substitute at third reading (2025-02-24) |
| 2025-04-28 | 2025-05-27 | ORDINANCE-1st READING - Amending Sections 1.4.3, 1.4.4, and 5.7.2 of the Unifie… | 1→2→3 | yes 4623 | amended by substitute at third reading (2025-05-27) |
| 2025-05-12 | 2025-06-09 | ORDINANCE-1st READING - Appropriating moneys for the City of Cheyenne, Wyoming,… | 1→2→3 | yes 4624 | amended by substitute at third reading (2025-06-09) |
| 2025-05-27 | 2025-06-23 | ORDINANCE-1st READING -- Amending portions of the Unified Development Code, mod… | 1→3 | yes 4626 | reading 3 on 2025-06-23 with no recorded reading 2 in the record window; amended by substitute at third reading (2025-0… |
| 2025-06-09 | 2025-07-14 | ORDINANCE-1st READING - Amending Section 6.08.180, Feeding Geese and Ducks Proh… | 1→2→3 | yes 4633 | amended by substitute at third reading (2025-07-14) |
| 2025-10-13 | 2025-11-10 | ORDINANCE-1st READING - Amending Sections 1.4.3, 1.4.4, 5.1.4, 5.7.10 and 5.8.2… | 1→2→3 | yes 4649 | amended by substitute at third reading (2025-11-10) |
| 2025-11-10 | 2025-11-24 | ORDINANCE-1st READING - Amending Section 5.76.050, Residential Door-to-Door Sol… | 1→2 | no | failed at reading 2 (2025-11-24) |
| 2025-12-22 | 2026-02-09 | ORDINANCE-1st READING - Creating Chapter 1.28, Administrative Inspection Warran… | 1→2→3→3 | yes 4656 | amended by substitute at third reading (2026-02-09) |
| 2026-01-26 | 2026-03-09 | ORDINANCE-1st READING - Creating Chapter 8.72, Private Displays on Public Prope… | 1→2→2→3 | no | failed at reading 3 (2026-03-09) |
| 2026-02-09 | 2026-03-09 | ORDINANCE - 1st READING - Annexing to the City of Cheyenne, Wyoming, various tr… | 1→2→3 | no | pending: postponed on 2026-03-09 to 2026-11-09 |
| 2026-02-09 | 2026-03-09 | ORDINANCE - 1st READING - Amending the Official Zoning Map of the City of Cheye… | 1→2→3 | no | pending: postponed on 2026-03-09 to 2026-11-09 |
| 2026-03-23 | 2026-06-08 | ORDINANCE-1st READING - Amending Section 13.20.050, General Prohibitions, and S… | 1→2→3→3→3→3 | yes 4673 | postponed 3 times; amended by substitute at third reading (2026-04-27) |
| 2026-04-27 | 2026-05-26 | ORDINANCE - 1st READING - Amending enforcement and permitting requirements rela… | 1→2→3 | yes 4672 | amended by substitute at third reading (2026-05-26) |
| 2026-05-11 | 2026-06-08 | ORDINANCE - 1st READING - Amending the Official Zoning Map of the City of Cheye… | 1→2→3 | yes 4677 | amended by substitute at third reading (2026-06-08) |
| 2026-05-11 | 2026-05-26 | ORDINANCE - 1st READING - Imposing a temporary twelve (12) month moratorium on… | 1→2 | no | failed at reading 2 (2026-05-26) |
| 2026-05-26 | 2026-06-08 | ORDINANCE - 1st READING - Amending Section 1.4.3 and 5.8.8 of the Unified Devel… | 1→2 | no | failed at reading 2 (2026-06-08) |
| 2026-05-26 | 2026-06-22 | ORDINANCE - 1st READING - Amending Section 1.3.11 Nonconformities; 1.4.4 Defini… | 1→2→3 | yes 4680 | amended by substitute at third reading (2026-06-22) |

## 4. Reconciliation between the records (R1–R8)

| Check | What it compares | Run | Exceptions |
|---|---|---|---|
| R1 | A postponement in the minutes vs the agenda of the target date | 19 | 0 |
| R2 | Ordinance reading order across meetings (see §3) | 22 | 22 |
| R3 | Substantive agenda items vs minutes entries, and minutes availability | 2 | 2 |
| R4 | Internal consistency of minutes: motion without outcome, vote count vs roster | 3 | 3 |
| R5 | Public commenters listed in minutes vs speaker introductions in the captions, per item | 113 | 22 |
| R6 | Roll call heard in the captions vs attendance in the minutes | 16 | 0 |
| R7 | Wyoming statute numbers spoken vs numbers in the official agenda and minutes | 31 | 9 |
| R8 | Executive-session statutory basis: agenda vs minutes vs spoken | 9 | 9 |

R1 and R2 report every row, including the ones that pass. R3–R8 report a row only when there is something to compare.

**R1 postponement continuity.** 19 of 19 postponements reappeared on the agenda of the date they were postponed to.

**R3 agenda and minutes coverage.**
- 2025-10-27 City Council Meeting: agenda item with no matching minutes entry: Agreement between the City of Cheyenne and WYDOT for a Wyoming Rural Public Transportation Grant to assist in…
- 2025-08-11 City Council Meeting: minutes text unavailable (3 characters of text; probably a scanned PDF)

**R4 record integrity.**
- 2025-11-24 City Council Meeting: vote count differs from roster (9 recorded vs 10 present): ORDINANCE-2nd READING - Amending Section 5.76.050, Residential Door-to-Door Solicitor Restrictions-Prohibited…
- 2026-08-24 City Council Meeting: motion without recorded outcome: Contract Modification #1 to Contract #8374 between the City of Cheyenne and the Cheyenne Downtown Development…

**R5 public comment.** Compared on 113 items where the minutes list speakers or the captions show speaker introductions. The correlation between the two counts is 0.902. Large gaps usually mean the captions did not record the introduction (remote speakers, or the clerk calling names off-mic). They can also mean the minutes list is incomplete. Largest gaps:

| Date | Item | Minutes list | Caption intros | Link |
|---|---|---|---|---|
| 2026-02-09 | Public Hearing to determine whether compliance of annexation conditio… | 0 | 29 | [video](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=178s) |
| 2026-05-26 | ORDINANCE – 2nd READING – Imposing a temporary twelve (12) month mora… | 75 | 51 | [video](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=7015s) |
| 2026-06-22 | ORDINANCE – 2nd READING – Annexing to the City of Cheyenne, Wyoming,… | 28 | 11 | [video](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=1983s) |
| 2026-04-27 | ORDINANCE – 2nd READING – Annexing to the City of Cheyenne, Wyoming,… | 38 | 26 | [video](https://www.youtube.com/watch?v=y9vnXtjZpR0&t=1834s) |
| 2026-06-08 | Public Hearing to determine whether compliance of annexation conditio… | 13 | 5 | [video](https://www.youtube.com/watch?v=69FQxIr9sJA&t=911s) |
| 2026-02-23 | ORDINANCE - 2nd READING - Annexing to the City of Cheyenne, Wyoming,… | 11 | 4 | [video](https://www.youtube.com/watch?v=rgnKyKmx3JU&t=1636s) |
| 2026-06-22 | ORDINANCE – 2nd READING – Amending the Official Zoning Map of the Cit… | 14 | 8 | [video](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=13069s) |
| 2026-05-26 | ORDINANCE – 2nd READING – Amending the Official Zoning Map of the Cit… | 19 | 14 | [video](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=3440s) |
| 2026-01-12 | Public Hearing for a transfer of ownership of retail liquor license a… | 5 | 1 | [video](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=520s) |
| 2026-05-11 | Consideration of Bid #S-19-26 for a Contract between the City of Chey… | 6 | 2 | [video](https://www.youtube.com/watch?v=vBJi7WeZ4C0&t=6139s) |

**R6 attendance.** 16 roll calls were compared; 0 disagree with the minutes.

**R7 citation grounding.** Out of 31 distinct statute numbers spoken (per meeting and role), 15 appear in that meeting's official agenda or minutes, 7 are near-misses of an official number (caption errors such as '15-1-42' for 15-1-402), and 9 appear only in the spoken record.

| Date | Body | Spoken | Role | Link |
|---|---|---|---|---|
| 2026-01-12 | CC | W.S. 15-1-404 | public comment | [video](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=350s) |
| 2026-01-12 | CC | W.S. 35-7-1046 | public comment | [video](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4232s) |
| 2026-02-09 | CC | W.S. 15-1-404 | official | [video](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=289s) |
| 2026-05-26 | CC | W.S. 37-3-116 | official | [video](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=19525s) |
| 2026-06-08 | CC | W.S. 15-1-405 | public comment | [video](https://www.youtube.com/watch?v=69FQxIr9sJA&t=2587s) |
| 2026-06-22 | CC | W.S. 16-3-114C | public comment | [video](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=19627s) |
| 2026-07-13 | CC | W.S. 37-3-116 | public comment | [video](https://www.youtube.com/watch?v=6dPLuulCpbI&t=21963s) |
| 2026-07-13 | CC | W.S. 15-1-506to | public comment | [video](https://www.youtube.com/watch?v=6dPLuulCpbI&t=25251s) |
| 2026-07-13 | CC | W.S. 16-3-114C | public comment | [video](https://www.youtube.com/watch?v=6dPLuulCpbI&t=25264s) |

**R8 executive sessions.** 9 council meetings went into executive session under W.S. 16-4-405(a). Under subsection (c), a motion that "specifies any of the reasons set forth in paragraphs (a)(i) through (xii)" is sufficient notice of the issue. The subsection numbers agree between agenda, minutes and captions at every meeting where all three give one. In 9 of 9 spoken motions, however, the reason given is the same: "to consider or receive any information classified as confidential by law", which is the wording of **(a)(ix)**. At 6 meetings the cited subsection is a different one: (a)(iii) litigation, (a)(vii) site selection or real-estate purchase, (a)(x) wage and benefit negotiations. At 3 meetings no subsection is cited in the agenda or minutes, so the (ix) wording is the only reason given. Whether the cited number or the spoken wording controls is a legal question for counsel. The table only shows that the two differ. Statute text: 2025 Wyoming Statutes §16-4-405 (https://law.justia.com/codes/wyoming/title-16/chapter-4/article-4/section-16-4-405/).

| Date | Agenda cites | Minutes cite | Motion cites (captions) | Reason stated aloud | Notes | Link |
|---|---|---|---|---|---|---|
| 2026-01-12 | (a)(vii) | (a)(vii) | (a)(vii) | (a)(ix) | — | [video](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=8642s) |
| 2026-02-09 | (a) only | (a) only | (a) only | (a)(ix) | agenda and minutes cite 16-4-405(a) without a subsection; the only reason stated aloud is the (a)(ix) wording; spoken m… | [video](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=15824s) |
| 2026-02-23 | (a) only | (a) only | (a) only | (a)(ix) | agenda and minutes cite 16-4-405(a) without a subsection; the only reason stated aloud is the (a)(ix) wording; spoken m… | [video](https://www.youtube.com/watch?v=rgnKyKmx3JU&t=10019s) |
| 2026-03-09 | (a) only | (a) only | (a) only | (a)(ix) | agenda and minutes cite 16-4-405(a) without a subsection; the only reason stated aloud is the (a)(ix) wording; spoken m… | [video](https://www.youtube.com/watch?v=19tQtLA8klo&t=21058s) |
| 2026-04-13 | (a)(vii) | (a)(vii) | (a)(vii) | (a)(ix) | — | [video](https://www.youtube.com/watch?v=mPv73_3Clls&t=7637s) |
| 2026-05-11 | (a)(x) | (a)(x) | (a) only | (a)(ix) | spoken motion cites 16-4-405 without a subsection (as captioned) | [video](https://www.youtube.com/watch?v=vBJi7WeZ4C0&t=9286s) |
| 2026-06-08 | (a)(x) | (a)(x) | (a)(x) | (a)(ix) | — | [video](https://www.youtube.com/watch?v=69FQxIr9sJA&t=13149s) |
| 2026-08-10 | (a)(iii) | (a)(iii) | (a)(iii) | (a)(ix) | — | [video](https://www.youtube.com/watch?v=7tVKl_N80dE&t=1991s) |
| 2026-09-14 | (a)(x) | n/a | (a) only | (a)(ix) | minutes not yet available; spoken motion cites 16-4-405 without a subsection (as captioned) | [video](https://www.youtube.com/watch?v=-zBOAUpDE3E&t=14128s) |

## 5. Legal claims made on the record

A claim is a sentence that says something is a violation, illegal, unconstitutional, void, preempted, procedurally defective or non-compliant. Each claim records its type, whether it was asserted or denied, any authority cited, who was speaking (by role), the agenda item, and what happened to that item.

| Assertion type | Count |
|---|---|
| violation | 137 |
| illegality | 44 |
| non compliance | 23 |
| unconstitutional | 12 |
| void or ultra vires | 10 |
| procedural defect | 7 |
| preemption | 3 |

By speaker role: public comment 168, official 62.

Authorities cited alongside claims: constitution 19, municipal code 5, udc or plan 5, wyoming statute 3, named act 2, case law 1.

**Items that drew the most legal claims:**

| Date | Item | Claims | Outcome | Final vote |
|---|---|---|---|---|
| 2026-01-12 | ORDINANCE –2nd READING – Creating Chapter 1.28, Administrative Inspection Warra… | 33 | carried | 7–3 (no: Aldrich, Moody, Rinne) |
| 2026-02-09 | ORDINANCE –3rd READING – Creating Chapter 1.28, Administrative Inspection Warra… | 13 | carried | 7–3 (no: Esquibel, Moody, Rinne) |
| 2026-07-13 | ORDINANCE – 3rd READING – Annexing to the City of Cheyenne, Wyoming, land east… | 9 | carried | 7–3 (no: Laybourn, Moody, Wolfe) |
| 2026-01-26 | ORDINANCE –3rd READING – Creating Chapter 1.28, Administrative Inspection Warra… | 8 | postponed | 10–0 |
| 2026-03-09 | ORDINANCE –3rd READING – Annexing to the City of Cheyenne, Wyoming, various tra… | 7 | postponed | 10–0 |
| 2026-04-27 | ORDINANCE – 2nd READING – Annexing to the City of Cheyenne, Wyoming, land west… | 4 | postponed | 10–0 |
| 2026-05-26 | ORDINANCE – 2nd READING – Imposing a temporary twelve (12) month moratorium on… | 4 | failed | 1–9 (no: Collins, Aldrich, Emmons, Esquibel, Laybourn, Rinne, Segrave, White, Wolfe) |
| 2026-05-26 | Urban Renewal Authority 2025 Annual Report. | 3 | carried | 10–0 |
| 2026-06-22 | ORDINANCE – 2nd READING – Amending the Official Zoning Map of the City of Cheye… | 3 | carried | 7–3 (no: Laybourn, Moody, Wolfe) |
| 2026-07-13 | RESOLUTION – Overruling the Planning Commission’s disapproval of an amendment t… | 3 | carried | 7–3 (no: Laybourn, Moody, Wolfe) |
| 2026-02-23 | ORDINANCE - 2nd READING - Annexing to the City of Cheyenne, Wyoming, various tr… | 2 | carried | 8–2 (no: Esquibel, Moody) |
| 2026-03-09 | ORDINANCE –3rd READING – Creating Chapter 8.72, Private Displays on Public Prop… | 2 | failed | 3–7 (no: Collins, Emmons, Esquibel, Moody, Rinne, Segrave, Wolfe) |

**Strong claims made in public comment (40).** These are the allegations most likely to need a documented answer. 'Response' means an official statement later in the same item that names counsel or legal review, or repeats the claim's authority or key terms. It is a candidate for a human to check, not proof that the point was addressed.

| Date | Time | Claim (excerpt) | Authority | Item outcome | Candidate response |
|---|---|---|---|---|---|
| 2026-01-12 | [00:27:20](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=1640s) | But at the end of the day, the overarching of this ordinance does violate the fourth amendment and article 1… | fourth amendment, article 1 section 4 | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [00:28:31](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=1711s) | having their Fourth Amendment violated. | Fourth Amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [00:56:12](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=3372s) | I stand in opposition to this bill because it violates the spirit of the fourth amendment of the Constitution… | fourth amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [00:57:08](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=3428s) | It is this is a violation of the fourth amendment of the constitution of the United States and we weasle word… | fourth amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [00:57:37](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=3457s) | I think that it is a violation of the fourth amendment. | fourth amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [00:57:37](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=3457s) | It is at least a violation of the spirit of the fourth amendment. | fourth amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:10:18](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4218s) | Specifically, it violates two critical legal fa frameworks. | United States Constitution, Fourth Amen… | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:10:18](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4218s) | Um, there are actually four major violations in this ordinance. | United States Constitution, Fourth Amen… | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:10:32](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4232s) | The ordinance uses a municipal judge instead of a district court judge, which directly violates Wyoming statu… | W.S. 35-7-1046 | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:10:45](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4245s) | It allows secret warrants without notifying the property owner, which violates the Supreme Court's ruling in… | Patel | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:11:01](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4261s) | Let's start with violation number one, state law, Wyoming statute section 35-7-1046 | W.S. 35-7-1046 | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:11:25](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4285s) | The result, the city is lowering the standard set by state law. | — | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:12:00](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4320s) | That's unconstitutional. | Fourth Amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-12 | [01:12:00](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4320s) | Violation number four, misusing the fire code. | Fourth Amendment | carried | [01:23:19](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4999s) |
| 2026-01-26 | [00:33:07](https://www.youtube.com/watch?v=x6Veeticz3Q&t=1987s) | First, it replaces the unconstitutional area inspection standard with particularized | — | postponed | [00:44:20](https://www.youtube.com/watch?v=x6Veeticz3Q&t=2660s) |
| 2026-02-09 | [02:18:28](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=8308s) | legal terms, that is an unconstitutional fishing expedition. | state constitution, Fourth Amendment | carried | [02:28:03](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=8883s) |
| 2026-02-09 | [02:43:19](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=9799s) | removing the unconstitutional language, you inoculate the ordinance against immediate legal challenge. | — | carried | [02:59:49](https://www.youtube.com/watch?v=OxeCnRnBLkU&t=10789s) |
| 2026-03-02 | [00:05:27](https://www.youtube.com/watch?v=o5zAVk1HSh8&t=327s) | The last thing someone who is graving is going to be thinking of is the fact that they need to check their ci… | city code | — | none found |
| 2026-03-02 | [01:11:04](https://www.youtube.com/watch?v=o5zAVk1HSh8&t=4264s) | violations of municipal code, whether it be zoning or whatever portion of municipal code have always been | municipal code | — | none found |
| 2026-03-09 | [01:14:47](https://www.youtube.com/watch?v=19tQtLA8klo&t=4487s) | It's unfair and in my opinion, it's unconstitutional. | — | postponed | [04:54:18](https://www.youtube.com/watch?v=19tQtLA8klo&t=17658s) |
| 2026-03-09 | [02:41:14](https://www.youtube.com/watch?v=19tQtLA8klo&t=9674s) | Please be advised that under Wyoming Food Freedom Act statute 1147103, local municipalities are expressly pre… | — | postponed | [04:54:18](https://www.youtube.com/watch?v=19tQtLA8klo&t=17658s) |
| 2026-04-20 | [02:06:18](https://www.youtube.com/watch?v=t17ft4xMMx4&t=7578s) | It is illegal to engage in viewpoint discrimination. | first amendment, United States Constitu… | — | none found |
| 2026-05-26 | [05:02:05](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=18125s) | Action taken at a meeting not in conformity with the act is null and void. | — | failed | none found |
| 2026-05-26 | [06:38:28](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=23908s) | You have successfully established an official policy of unconstitutional viewpoint discrimination. | — | carried | none found |
| 2026-05-26 | [06:39:06](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=23946s) | You have manufactured a legally defective legislative record as the statute dictates actions taken not in con… | public meetings act | carried | none found |
| 2026-06-01 | [03:41:14](https://www.youtube.com/watch?v=GcTnJFfrApg&t=13274s) | It violates section 2.2.1 2.1 | section 2.2.1 | — | none found |
| 2026-06-01 | [03:41:26](https://www.youtube.com/watch?v=GcTnJFfrApg&t=13286s) | It also violates section 2.2.1 D2 and D4 | section 2.2.1, future land use map | — | none found |
| 2026-06-01 | [03:42:05](https://www.youtube.com/watch?v=GcTnJFfrApg&t=13325s) | It violates the fundamental burden of proof. | Section 2.2.1 | — | none found |
| 2026-06-22 | [03:40:15](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=13215s) | Councilman Wolf defended the statutory evasion, stating verbatim, "The legislature created this scheme." So t… | — | carried | none found |
| 2026-06-22 | [03:41:27](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=13287s) | The evidence is void. | — | carried | none found |

**Strong legal statements by officials and staff (8),** including denials. Excerpts:

- 2026-02-02 [01:59:53](https://www.youtube.com/watch?v=pO5K8gfvy0g&t=7193s) _assert_: have no authority um or don't feel they
- 2026-04-27 [00:21:21](https://www.youtube.com/watch?v=y9vnXtjZpR0&t=1281s) _assert_: change, it would um basically preempt,
- 2026-05-18 [00:53:43](https://www.youtube.com/watch?v=eyf-DZyuDis&t=3223s) _assert_: kids have been doing it for quite a while and cutting across illegally on the property.
- 2026-06-01 [01:57:30](https://www.youtube.com/watch?v=GcTnJFfrApg&t=7050s) _assert_: Um, basically the zoning violation process would start basically telling them they're out of compliance and that they need to fix it.
- 2026-06-01 [00:09:40](https://www.youtube.com/watch?v=AEKufmR2Dc0&t=580s) _assert_: zoning violation, is illegal.
- 2026-06-15 [03:54:53](https://www.youtube.com/watch?v=e8pByyWP7RE&t=14093s) _assert_: overrule this, it's null and void anyway.
- 2026-06-15 [04:02:11](https://www.youtube.com/watch?v=e8pByyWP7RE&t=14531s) _assert_: and is therefore null and void.
- 2026-06-22 [00:23:15](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=1395s) _assert_: action over which we have no authority

## 6. Voting record (2026 minutes)

No-rate is no votes divided by all votes cast. Minority rate is how often the member was on the losing side, counting contested votes only. Motions and seconds are taken from the minutes.

| Member | Votes cast | No | No-rate | Contested | Minority rate | Motions | Seconds | Absent |
|---|---|---|---|---|---|---|---|---|
| Moody | 237 | 55 | 0.232 | 79 | 0.759 | 6 | 37 | 0 |
| Laybourn | 237 | 31 | 0.131 | 79 | 0.304 | 6 | 4 | 0 |
| Rinne | 234 | 25 | 0.107 | 79 | 0.101 | 21 | 2 | 4 |
| Wolfe | 230 | 24 | 0.104 | 76 | 0.171 | 4 | 19 | 3 |
| Segrave | 225 | 21 | 0.093 | 77 | 0.052 | 27 | 58 | 1 |
| Emmons | 236 | 20 | 0.085 | 79 | 0.063 | 43 | 25 | 1 |
| Collins | 229 | 17 | 0.074 | 79 | 0.0 | 0 | 0 | 0 |
| Esquibel | 237 | 15 | 0.063 | 79 | 0.076 | 66 | 5 | 1 |
| White | 237 | 12 | 0.051 | 79 | 0.038 | 15 | 70 | 0 |
| Aldrich | 236 | 10 | 0.042 | 79 | 0.139 | 70 | 31 | 1 |

Lowest pairwise agreement on contested votes: Emmons–Moody 0.177 (n=79); Moody–Rinne 0.19 (n=79); Moody–Segrave 0.195 (n=77); Collins–Moody 0.215 (n=79); Moody–White 0.253 (n=79). Highest: Collins–White 0.937; Esquibel–White 0.937; Collins–Segrave 0.948.

**Close votes (margin of 2 or less): 6.**

| Date | Item | Motion | Result | Yes–No | Voting no |
|---|---|---|---|---|---|
| 2026-02-09 | ORDINANCE-3rd READING - Creating Chapter 1.28, Administrative Inspect… | Motion to amend | carried | 6–4 | Emmons, Laybourn, Segrave, Wolfe |
| 2026-02-23 | ORDINANCE - 2nd READING - Annexing to the City of Cheyenne, Wyoming,… | Motion to postpone | failed | 4–6 | Collins, Emmons, Laybourn, Rinne, Segrave, Wolfe |
| 2026-02-23 | ORDINANCE - 2nd READING - Annexing to the City of Cheyenne, Wyoming,… | Motion to divide the question | failed | 4–6 | Collins, Emmons, Laybourn, Rinne, Segrave, Wolfe |
| 2026-03-09 | ORDINANCE - 3rd READING - Annexing to the City of Cheyenne, Wyoming,… | Motion to amend | failed (tie) | 5–5 | Collins, Emmons, Laybourn, Rinne, Segrave |
| 2026-03-09 | ORDINANCE - 3rd READING - Annexing to the City of Cheyenne, Wyoming,… | Motion to divide the question | failed (tie) | 5–5 | Collins, Emmons, Laybourn, Rinne, Segrave |
| 2026-03-23 | Contract Modification #1 to Contract #8267 between the City of Cheyen… | Motion | carried | 6–4 | Aldrich, Laybourn, Moody, Wolfe |

## 7. Where meeting time goes

Shares are computed from segment timestamps. 'Public comment' runs from an invitation to speak until the chair closes it or a motion is called for, so it also counts any staff answers given in between; read it as an upper bound. 'Agenda reading' is the clerk reading item titles.

| Date | Body | Length | Public comment | Items aligned | Longest item (outcome) |
|---|---|---|---|---|---|
| 2026-01-12 | CC | 2:24 | 64% | 11 | ORDINANCE –2nd READING – Creating Chapter 1.28, Administrat… — 1:47 (carried) |
| 2026-01-26 | CC | 1:48 | 59% | 12 | ORDINANCE –3rd READING – Creating Chapter 1.28, Administrat… — 0:50 (postponed) |
| 2026-02-09 | CC | 4:24 | 67% | 14 | Public Hearing to determine whether compliance of annexatio… — 2:13 (—) |
| 2026-02-23 | CC | 2:47 | 36% | 10 | ORDINANCE - 2nd READING - Annexing to the City of Cheyenne,… — 1:42 (carried) |
| 2026-03-09 | CC | 5:51 | 63% | 15 | ORDINANCE –3rd READING – Annexing to the City of Cheyenne,… — 4:32 (postponed) |
| 2026-03-23 | CC | 2:37 | 76% | 11 | Contract Modification #1 to Contract #8267 between the City… — 0:37 (carried) |
| 2026-04-13 | CC | 2:07 | 66% | 19 | Public Hearing to determine whether compliance of annexatio… — 0:56 (—) |
| 2026-04-27 | CC | 4:09 | 73% | 15 | ORDINANCE – 2nd READING – Annexing to the City of Cheyenne,… — 2:28 (postponed) |
| 2026-05-11 | CC | 2:35 | 56% | 17 | Consideration of Bid #S-19-26 for a Contract between the Ci… — 0:44 (carried) |
| 2026-05-26 | CC | 6:43 | 76% | 14 | ORDINANCE – 2nd READING – Imposing a temporary twelve (12)… — 4:08 (failed) |
| 2026-06-08 | CC | 3:39 | 65% | 28 | Public Hearing to determine whether compliance of annexatio… — 1:08 (—) |
| 2026-06-22 | CC | 5:29 | 67% | 24 | ORDINANCE – 2nd READING – Annexing to the City of Cheyenne,… — 2:41 (carried) |
| 2026-07-13 | CC | 7:43 | 83% | 19 | ORDINANCE – 3rd READING – Annexing to the City of Cheyenne,… — 4:42 (carried) |
| 2026-07-27 | CC | 1:15 | 64% | 9 | RESOLUTION – Authorizing the Mayor to execute a Memorandum… — 0:16 (carried) |
| 2026-08-10 | CC | 1:25 | 30% | 4 | Consideration of Bid #S-22-26 for a Contract between the Ci… — 0:08 (—) |
| 2026-08-24 | CC | 1:01 | 22% | 4 | Transfer of location and ownership of retail liquor license… — 0:16 (—) |
| 2026-09-14 | CC | 3:55 | 65% | 14 | ORDINANCE – 2nd READING – Annexing to the City of Cheyenne,… — 1:32 (—) |
| 2026-09-21 | PSC | 3:05 | 37% | 14 | ORDINANCE – 2nd READING – Amending the Official Zoning Map… — 0:48 (—) |
| 2026-09-22 | Finance | 0:51 | 24% | 10 | RESOLUTION – Supporting the continuation of the Optional On… — 0:14 (—) |

## 8. Passage flags, v1 vs v2

v2 rescoring starts from the v1 keyword score and makes three changes:

- A marker that appears in the official title of the agenda item under discussion is dropped. 'Warrant' during the Administrative Inspection Warrants ordinance is the topic, not a sign of deviation.
- The score is multiplied by 0.25 when most of the passage is the clerk reading agenda titles.
- Each strong asserted legal claim in the passage adds 3, and each other claim adds 1.

Flag rule: score above 3.0 (the v1 threshold), or any strong asserted claim. Flags: 240 (v1) → 221 (v2). 49 v1 flags were dropped because their markers were the item's own subject, 0 for other reasons, and 30 passages were newly flagged because of the legal claims in them. The lexicon exclusions (stormwater detention, 'warrant' as a verb, 'curb appeal', prepayment penalty) apply to both versions.

| Date | Body | Time | v1 | v2 | Strong claims | Markers |
|---|---|---|---|---|---|---|
| 2026-01-12 | CC | [01:10:56](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4256s) | 12.5 | 24.5 | 4 | warrant, statute, ordinance, wyoming statute, fourth amendm… |
| 2026-01-12 | CC | [01:09:42](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=4182s) | 10.5 | 20.5 | 4 | warrant, statute, ordinance, wyoming statute, fourth amendm… |
| 2026-05-26 | CC | [06:38:18](https://www.youtube.com/watch?v=bGt1XMfaTTw&t=23898s) | 7.5 | 13.5 | 2 | statute, wyoming statute, title 16, public meetings act |
| 2026-01-12 | CC | [00:56:46](https://www.youtube.com/watch?v=Dfqmg--DVPE&t=3406s) | 3.5 | 11.0 | 3 | ordinance, fourth amendment |
| 2026-09-14 | CC | [02:55:57](https://www.youtube.com/watch?v=-zBOAUpDE3E&t=10557s) | 10.0 | 11.0 | 1 | statute, ordinance, postponed, out of order, wyoming statut… |
| 2026-01-26 | CC | [00:32:35](https://www.youtube.com/watch?v=x6Veeticz3Q&t=1955s) | 8.5 | 10.5 | 1 | warrant, statute, ordinance, wyoming statute, state law |
| 2026-04-20 | PSC | [02:05:55](https://www.youtube.com/watch?v=t17ft4xMMx4&t=7555s) | 5.5 | 9.5 | 1 | statute, due process, public meetings act |
| 2026-06-01 | planning-commission | [03:40:19](https://www.youtube.com/watch?v=GcTnJFfrApg&t=13219s) | 3.5 | 9.5 | 2 | failed to, udc |
| 2026-06-22 | CC | [05:25:47](https://www.youtube.com/watch?v=RjSGlhh4q9s&t=19547s) | 5.5 | 9.5 | 1 | statute, wyoming statute, W.S. 16-3-114 |
| 2026-03-02 | PSC | [01:10:46](https://www.youtube.com/watch?v=o5zAVk1HSh8&t=4246s) | 5.0 | 9.0 | 1 | statute, ordinance, municipal code |
| 2026-05-18 | PSC | [01:31:18](https://www.youtube.com/watch?v=eyf-DZyuDis&t=5478s) | 9.0 | 9.0 | 0 | statute, ordinance, wyoming statute, udc, W.S. 9-8-301 |
| 2026-07-06 | PSC | [01:15:23](https://www.youtube.com/watch?v=7BwdzgyTD2Y&t=4523s) | 9.0 | 9.0 | 0 | statute, ordinance, wyoming statute, due process, W.S. 16-3… |

## 9. Validation and limits

| Check | Result |
|---|---|
| Aligned items where the spoken item number matched the agenda | 97% |
| Aligned items joined to a minutes entry | 77% |
| Correlation of public-comment counts, minutes vs captions (113 items) | 0.902 |
| Caption name mentions resolved to a canonical member | 61% |

- **Alignment covers items that are announced aloud.** Consent-agenda items approved in a single motion have no start time of their own, so the aligned share is lower on long consent agendas.
- **The minutes parser was spot-checked against the source text** for every key result in this report (for example, Ch. 1.28 at third reading on 2026-02-09: carried by substitute as amended, 7–3, #4656). The parser has unit tests. Minutes from 2025-08-11 are a scanned PDF with no text and are excluded.
- **Claims are detected by pattern.** In a hand-checked random sample of 30 strong asserted claims, about 22 of the 24 from public comment were genuine legal allegations about a government action. Only 1 of the 6 attributed to officials was; the rest were staff describing enforcement against third parties, or hypothetical questions. Use the public-comment claims as a ledger and treat the official-side counts as mentions. Sarcasm and quotation are not detected.
- **Quoted text is redacted.** Names of members of the public found in the minutes' public-comment lists, and spoken self-introductions, are replaced with [member of the public].
- **Speaker roles are inferred** from public-comment opening and closing phrases. A commenter who keeps speaking after the chair closes public comment, or staff speaking during it, will be mislabelled.
- **Committee meetings** are compared to the official record only when the archive holds a matching agenda.

Full outputs (gitignored, regenerate with `python3 audit/build_analysis.py`): `audit/output/analysis/` → `claims.jsonl`, `items.jsonl`, `exceptions.jsonl`, `lifecycles.json`, `voting.json`, `meetings.json`, `aliases.json`, `passages_v2.jsonl`.
