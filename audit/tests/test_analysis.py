"""Regression tests for the v2 analysis layers.

Each minutes case reproduces a construction that was misparsed during
development. Every one was checked by hand against the official minutes. Names
of members of the public are fictional.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minutes_parser import parse_minutes, split_entries  # noqa: E402
from reconcile import exec_basis, exec_spoken, title_sim, voting_record  # noqa: E402
from alignment import label_roles, align  # noqa: E402
from claims import extract_claims  # noqa: E402
from audit_ingest_node import RegulatoryAuditPipeline  # noqa: E402

HEAD = ("Present were: MAYOR – Patrick Collins, COUNCIL MEMBERS – Dr. Michelle Aldrich, Dr. Jeff Emmons (via Zoom), "
        "Mr. Mark Moody, Mr. Richard Laybourn, Dr. Tom Rinne, Mr. Scott Esquibel, Mr. Tom Segrave, "
        "Mr. Ken White, Mr. Lawrence Wolfe. Absent: None. Also present: Kylie Soden, City Clerk.\n\n")


def entries(body: str):
    return parse_minutes(HEAD + body)["entries"]


def find(es, word):
    return next(e for e in es if word in e["title"])


def test_roster_parenthetical_is_not_a_member():
    r = parse_minutes(HEAD + "ORDINANCE-1st READING - Placeholder - referred to Finance Committee.")["roster"]
    assert "Zoom" not in r["present"]
    assert "Emmons" in r["present"]


def test_substitute_with_split_words_and_no_dash_vote_list():
    es = entries(
        'ORDINANCE-3rd READING - Creating Chapter 1.28, Administrative Inspection Warrants. Dr. Aldrich moved to approve '
        'on third and final reading, seconded by Mr. White. Dr. Aldrich moved to amend by substitute, seconded by '
        'Mr. White. Motion to amend by substitute carried. Voting "yes" – all members of the governing body. '
        'Main motion as amend ed by substitute carried. Voting "yes" Dr. Aldrich, Mayor Collins, Dr. Emmons, '
        'Mr. Laybourn, Mr. Segrave, Mr. White and Mr. Wolfe. Voting "no" – Mr. Esquibel, Mr. Moody and Dr. Rinne. (#4656)')
    e = find(es, "1.28")
    assert e["final_result"] == "carried" and e["number"] == "4656"
    v = [x for x in e["events"] if x["type"] == "vote"][-1]
    assert sorted(v["no"]) == ["Esquibel", "Moody", "Rinne"] and len(v["yes"]) == 7


def test_main_motion_with_comma_label():
    es = entries('ORDINANCE-2nd READING - Appropriating moneys for the City. Dr. Rinne moved to approve on second reading, '
                 'seconded by Mr. White. Mr. Esquibel moved to amend to increase a line item, seconded by Dr. Emmons. '
                 'Motion to amend failed. Voting "no" – all members of the governing body with the exception of '
                 'Dr. Emmons and Mr. Esquibel voting "yes". Main motion, as amended by substitute, as amended, carried. '
                 'Voting "yes" – all members of the governing body.')
    assert find(es, "Appropriating")["final_result"] == "carried"


def test_bare_outcome_after_recommit_and_trailing_adjourn():
    es = entries('ORDINANCE - 3rd READING - Annexing land east of the highway. Dr. Aldrich moved to approve on third and '
                 'final reading, seconded by Dr. Emmons. Mr. Moody moved to recommit the ordinance to committee, seconded '
                 'by Mr. Wolfe. Motion failed. Voting "no" – all members of the governing body with the exception of '
                 'Mr. Laybourn, Mr. Moody and Mr. Wolfe voting "yes". Main motion carried. Voting "yes" – all members of '
                 'the governing body with the exception of Mr. Laybourn, Mr. Moody and Mr. Wolfe voting "no". (#4687) '
                 'Mr. Wolfe moved to adjourn, seconded by Mr. Laybourn. Motion failed. Voting "no" – all members of the '
                 'governing body with the exception of Mr. Laybourn, Mr. Moody and Mr. Wolfe voting "yes".')
    e = find(es, "Annexing")
    assert e["final_result"] == "carried" and e["number"] == "4687"


def test_amendment_dies_then_bare_outcome_decides_main_motion():
    es = entries('ORDINANCE-2nd READING - Creating Section 10.24.200, Vehicle Mufflers. Dr. Rinne moved to approve on second '
                 'reading, seconded by Mr. White. Mr. Moody moved to amend by striking number 7 on page 2. Motion to amend '
                 'died due to lack of a second. Motion carried. Voting "yes" – all members of the governing body.')
    assert find(es, "Mufflers")["final_result"] == "carried"


def test_postponement_date_certain_and_failed_postpone_sets_no_date():
    es = entries('ORDINANCE - 3rd READING - Annexing various tracts. Dr. Rinne moved to approve on third and final reading, '
                 'seconded by Dr. Aldrich. Dr. Aldrich moved to amend with a postponement date certain of June 8, 2026, '
                 'seconded by Mr. Moody. Mr. White moved to amend the amendment with a postponement date certain of '
                 'November 9, 2026, seconded by Mr. Moody. Motion to amend the amendment carried. Voting "yes" – all '
                 'members of the governing body. Motion to postpone by amended postponement date certain of November 9, '
                 '2026 carried. Voting "yes" – all members of the governing body.\n\n'
                 'ORDINANCE - 2nd READING - Annexing other tracts. Dr. Rinne moved to approve on second reading, seconded '
                 'by Dr. Aldrich. Dr. Aldrich moved to postpone to March 9, 2026, seconded by Mr. Moody. Motion to postpone '
                 'failed. Voting "yes" – Dr. Aldrich, Mr. Esquibel, Mr. Moody and Mr. White. Voting "no" – Mayor Collins, '
                 'Dr. Emmons, Mr. Laybourn, Dr. Rinne, Mr. Segrave and Mr. Wolfe. Main motion carried. Voting "yes" – all '
                 'members of the governing body.')
    a = find(es, "various tracts")
    assert a["final_result"] == "postponed" and a["postponed_to"] == "2026-11-09"
    b = find(es, "other tracts")
    assert b["final_result"] == "carried" and b["postponed_to"] is None


def test_continuation_paragraph_after_recess_is_merged():
    text = HEAD + ('ORDINANCE - 2nd READING - Annexing tracts. Dr. Rinne moved to approve on second reading, seconded by '
                   'Dr. Aldrich. Mr. Esquibel moved to divide the question, seconded by Dr. Aldrich. Motion to divide the '
                   'question failed. Voting "yes" – all members of the governing body with the exception of Dr. Rinne '
                   'voting "no". Following a brief recess, Mayor Collins reconvened the meeting at 7:40 p.m.\n\n'
                   'Mr. Moody, with concurrence by Dr. Aldrich as the second to the motion, moved by friendly amendment to '
                   'remove Parcels 4 and 7. Motion to amend failed. Voting "no" – all members of the governing body. Main '
                   'motion carried. Voting "yes" – all members of the governing body with the exception of Mr. Esquibel '
                   'and Mr. Moody voting "no".')
    assert len([p for p in split_entries(text) if "Annexing" in p or "friendly" in p]) == 1
    e = find(parse_minutes(text)["entries"], "Annexing")
    assert e["final_result"] == "carried"


def test_voting_record_counts_contested_vote():
    pm = parse_minutes(HEAD + 'RESOLUTION - Something. Dr. Aldrich moved to adopt, seconded by Mr. White. Motion carried. '
                              'Voting "yes" – all members of the governing body with the exception of Mr. Moody voting "no". (#6600)')
    vr = voting_record([{"date": "2026-01-01", "kind": "City Council Meeting", "parsed": pm}])
    assert len(vr["contested"]) == 1 and vr["contested"][0]["no"] == ["Moody"]


def test_executive_session_basis_parsing():
    assert exec_basis("pursuant to Wyoming Statute §16- 4- \n405(a)(vii), seconded") == [7]
    sp = exec_spoken("Mr. Mayor, pursuant to Wyoming statute section 164405A7, I move that the governing body meet in "
                     "executive session to consider or receive any information classified [clears throat] as confidential by law.")
    assert sp["numbers"] == [7] and sp["purpose_language"] == [9]
    sp2 = exec_spoken("pursuant to Wyoming statute section 164405, I move that the governing body meet in executive session")
    assert sp2["numbers"] == [] and sp2["cited_without_subsection"]


def test_title_similarity_ignores_reading_prefix():
    assert title_sim("ORDINANCE-1st READING - Creating Chapter 1.28, Administrative Inspection Warrants",
                     "ORDINANCE - 3rd READING - Creating Chapter 1.28, Administrative Inspection Warrants") == 1.0


def test_lexicon_exclusions():
    p = RegulatoryAuditPipeline()
    assert "detention" not in p.classify_record_deterministic("The detention pond will be regraded.")["enforcement_classification"]
    assert "detention" in p.classify_record_deterministic("He was held in detention overnight.")["enforcement_classification"]
    assert p.classify_record_deterministic("That does not warrant further review.")["procedural_deviations"] == ["None identified"]


def test_roles_and_claims():
    segs = [("00:00:01", "Item 5. Ordinance third reading creating chapter 1.28."),
            ("00:00:20", "We'll go out to the audience on this. My name is Jane Example and I live on Pine Street."),
            ("00:01:00", "This ordinance is unconstitutional and violates the Fourth Amendment."),
            ("00:02:00", "Anybody else? Seeing none. Dr. Rinne, may we have a motion, please?"),
            ("00:02:30", "I move to approve. The city attorney has reviewed it and it does not violate the constitution.")]
    roles = label_roles(segs, {"00:00:01"})
    assert roles[1] == "public_comment" and roles[2] == "public_comment" and roles[4] == "official"
    cl = extract_claims(segs, roles)
    pub = [c for c in cl if c["role"] == "public_comment"]
    assert pub and pub[0]["strength"] == "strong" and "unconstitutional" in pub[0]["assertion_types"]
    off = [c for c in cl if c["role"] == "official"]
    assert off and off[0]["polarity"] == "deny"


def test_alignment_finds_spoken_item():
    segs = [("00:00:00", "Call to order."), ("00:05:00", "Next item is number 7 on page 3, ordinance creating chapter 1.28 "
                                                           "administrative inspection warrants."), ("00:30:00", "Next item is number 8.")]
    items = [{"item_no": "7", "title": "ORDINANCE-3rd READING - Creating Chapter 1.28, Administrative Inspection Warrants",
              "consent": False}, {"item_no": "8", "title": "RESOLUTION - Something else entirely", "consent": False}]
    al = align(segs, items)
    assert al and al[0].item_no == "7" and al[0].start == "00:05:00"


def test_report_redacts_members_of_the_public():
    import report
    report.set_redactions({"Jane Example", "Rob Sample"}, {"Moody"})
    out = report._t("For the permanent administrative record, Jane Example, my testimony. Mr. Sample agreed. "
                    "My name is Pat Person. Mr. Moody voted no.", 300)
    assert "Jane" not in out and "Sample" not in out and "Pat Person" not in out
    assert "Moody" in out
