#!/usr/bin/env python3
"""Generate per-video review workbooks (videos 03–17) from the phase candidate
scans on the source project branch.

Each workbook is a bounded, prioritized review queue plus the verification
checklist and comparison discipline for that deliverable. The cues are
caption-derived machine candidates — every workbook carries the standing
caveats. Nothing here is footage-verified.

Run (from production/):
  python3 generate_workbooks.py --phases-dir /path/to/video-production
(phases-dir = a checkout of branch arena/01a0fdbc-therealwindycity of
 therealwindycity/therealwindycity, or a copy of its phase-0N-* directories)
"""
import argparse
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

P2 = "phase-02-record-interactions/candidate_events.jsonl"
P3 = "phase-03-public-comment-comparators/candidate_events.jsonl"
P4 = "phase-04-institutional-disagreement/candidate_events.jsonl"

STANDING_CAVEATS = [
    "Cues are caption-derived machine candidates. Captions mis-hear names and words; verify every quote against the recording audio.",
    "Proximity in the transcript is not proof of speaker, target, response, or ruling. Never infer identity, motive, or who answered whom from a cue's position.",
    "A cue is a review lead only — it is not an event, a count, or a finding.",
]


def load(path):
    recs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return recs


def excerpt(text, n=130):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def table(recs, start=1):
    rows = ["| # | Meeting | Time | Cue (caption-derived — verify on footage) | Link |",
            "|---:|---|---|---|---|"]
    for i, r in enumerate(recs, start):
        link = r.get("source_link") or r.get("transcript", "")
        if isinstance(link, str) and link.startswith("http"):
            link = f"[open]({link})"
        elif not isinstance(link, str):
            link = ""
        rows.append(f"| {i} | {r['date']} {r['body']} | {r['timestamp']} | "
                    f"{excerpt(r.get('cue_text'))} | {link} |")
    return rows


def by_meeting(recs):
    c = Counter((r["date"], r["body"]) for r in recs)
    return [f"- {d} {b}: {n} cues" for (d, b), n in sorted(c.items())]


def pool(db, cats):
    out = []
    for r in db:
        if any(c in r.get("categories", []) for c in cats):
            out.append(r)
    return sorted(out, key=lambda r: (r["date"], r.get("timestamp", "")))


def queue_section(title, recs, cap, note=None):
    lines = [f"### {title} ({len(recs)} cues)", ""]
    if note:
        lines += [note, ""]
    shown = recs if len(recs) <= cap else recs[:cap]
    lines += table(shown)
    if len(recs) > cap:
        lines += ["", f"*…{len(recs) - cap} more — all {len(recs)} are in the phase JSONL "
                      f"(filter by the category named above).*"]
    lines += ["", "**By meeting (batch review against masters):**", ""] + by_meeting(recs) + [""]
    return lines


def head(num, slug, title, scope):
    return [
        f"# Workbook {num:02d} — {title}",
        "",
        f"**Deliverable:** `{num:02d}_{slug}.mp4` · **Status:** BLOCKED — source footage not yet acquired/reviewed; nothing in this workbook is footage-verified.",
        "",
        f"**Scope (project README, deliverable {num}):** {scope}",
        "",
        "## Standing caveats",
        "",
        *[f"- {c}" for c in STANDING_CAVEATS],
        "",
    ]


CHECK_GENERIC = [
    "Watch the recording at the cue **and enough lead/lag** to capture the complete exchange.",
    "Confirm the words against the audio (not the caption), the speaker, the speaker's role, and the agenda item.",
    "Preserve the complete turn, any question/prompt that preceded it, any chair ruling, and any response that followed.",
    "Log every caption correction in the EDL caption-corrections layer; never silently rewrite captions.",
    "Record source date, body, item, original URL, and source in/out on the slate for every cut.",
]


def checklist(items):
    return ["## Verification checklist (every included clip)", "",
            *[f"- [ ] {i}" for i in items], ""]


def edl_note():
    return ["## Output", "",
            "Render with `production/render_video.py` from an EDL whose every clip is marked "
            "`verified` (the renderer refuses unverified clips). Deliverables per the handoff: "
            "MP4 (H.264/AAC, no upscaling), SRT/VTT sidecar, EDL export, provenance README, QA record with SHA-256.",
            ""]


# ---------------------------------------------------------------- workbooks --

def wb03(p2):
    L = head(3, "in_person_requests",
             "Requests that Miller attend in person / criticism of Zoom participation",
             "Every request/demand that Miller attend in person or criticism of Zoom participation.")
    direct = pool(p2, ["possible_direct_in_person_request_or_preference",
                       "possible_remote_attendance_objection"])
    proc = [r for r in pool(p2, ["in_person_procedure_near_miller",
                                 "remote_attendance_procedure_or_reference_near_miller"])
            if r not in direct]
    L += queue_section("Direct in-person requests / remote-attendance objections (highest priority)",
                       direct, 25)
    L += queue_section("In-person / remote procedure context near Miller references",
                       proc, 20,
                       "Context class — most are procedure references, not requests. Include only footage-verified requests or criticism.")
    L += checklist(CHECK_GENERIC + [
        "Classify each verified event: explicit request that Miller attend in person, criticism of his Zoom participation, or unrelated procedure talk.",
        "Do not count a general remote-participation procedure statement as a request aimed at Miller without on-footage evidence of target."])
    L += edl_note()
    return "03_in_person_requests", L


def wb04(p3):
    L = head(4, "leads_comment_opportunities",
             "Cheyenne LEADS multiple-comment opportunities versus the public-comment cap",
             "Cheyenne LEADS multiple public-comment slots on one item versus a one-comment public cap.")
    opp = pool(p3, ["possible_number_of_public_comment_opportunities_claim"])
    capr = pool(p3, ["possible_comment_cap_or_time_rule_statement"])
    leads = pool(p3, ["cheyenne_leads_or_associated_person_reference"])
    L += queue_section("Number-of-opportunities claims (highest priority — verify proceeding, speaker, item, rule)",
                       opp, 10,
                       "The three numeric-opportunity cues occur in a work-session transcript whose catalog date is only '2026'. The panel is contextual material, not a verified public-comment event.")
    L += queue_section("Comment-cap / time-rule statements (the written rule in force)",
                       capr, 20,
                       "Establish the written rule before comparing anyone: cite the rule text (UDC § / council rules) in force on the meeting date.")
    L += queue_section("Cheyenne LEADS / associated-person references",
                       leads, 20)
    L += checklist(CHECK_GENERIC + [
        "Establish the denominator: which slots were public-comment slots under the written rule vs applicant presentation, staff response, council questioning, work-session comment.",
        "For any claim that LEADS (or anyone) received multiple slots, verify on footage: the item, each separate recognition, and the rule text; otherwise deliver 'not established'.",
        "Retain the Phase 3 300-second proximity caveat: scanner cues are not speakers, comment slots, or events."])
    L += edl_note()
    return "04_leads_comment_opportunities", L


def wb05(p3):
    L = head(5, "applicant_comment_opportunities",
             "Developer/applicant comment opportunities versus public comment",
             "Developers/private applicants receiving multiple public-comment slots.")
    dev = pool(p3, ["possible_applicant_or_developer_affiliation_near_comment_gate"])
    L += queue_section("Applicant/developer-affiliation cues near comment gates",
                       dev, 30,
                       "Leads only. Affiliation wording in captions does not establish that the speaker was the applicant or that the turn was a public-comment slot.")
    L += checklist(CHECK_GENERIC + [
        "Separate applicant presentation, staff response, council questioning, and actual public-comment periods — by footage, agenda, and the written rule.",
        "A developer speaking during presentation or Q&A is not a 'public-comment slot'; do not count it as one.",
        "Deliver 'not established' rather than a forced comparison if the footage/rules cannot support a fair denominator."])
    L += edl_note()
    return "05_applicant_comment_opportunities", L


def wb06(p3):
    L = head(6, "off_topic_over_three_minutes",
             "Off-topic / over-three-minute comments, with a defensible denominator",
             "Off-topic or over-three-minute comments, compared by speaker and viewpoint — only with a defensible speaker/item/rule denominator.")
    tl = pool(p3, ["possible_time_limit_or_call_outside_miller_window"])
    tr = pool(p3, ["possible_topic_or_relevance_ruling_outside_miller_window"])
    L += queue_section("Time-limit calls / rulings outside the Miller window", tl, 25)
    L += queue_section("Topic/relevance rulings outside the Miller window", tr, 25)
    L += checklist(CHECK_GENERIC + [
        "For timing claims, inspect the visible timer and the chair's ruling on the footage; log time consumed, stops/resets, interruptions, technical delay, and restored time. Captions cannot establish timer credit.",
        "Build the denominator first (every speaker on the item, the rule in force, each ruling), then compare — never a cherry-picked pair.",
        "Do not infer viewpoint-based enforcement from outcomes alone; log the stated reason for each ruling."])
    L += edl_note()
    return "06_off_topic_over_three_minutes", L


def wb07(p4):
    L = head(7, "admin_internal_disagreement",
             "Administration members disagreeing among themselves",
             "Administration members disagreeing among themselves.")
    ex = pool(p4, ["explicit_disagreement_language"])
    co = pool(p4, ["possible_factual_correction_or_contradiction"])
    L += queue_section("Explicit disagreement language", ex, 35)
    L += queue_section("Possible corrections/contradictions", co, 20,
                       "Shared pool with workbook 08 — split by verified roles/targets: internal (member↔member of the administration) for this video.")
    L += checklist(CHECK_GENERIC + [
        "Verify roles on footage: who is administration (mayor, council members, staff) and whether the exchange is between two administration members.",
        "Distinguish disagreement from routine clarification, a question, or reading assistance.",
        "Keep counts honest: overlapping pattern categories mean the cue totals are not event counts."])
    L += edl_note()
    return "07_admin_internal_disagreement", L


def wb08(p4):
    L = head(8, "admin_public_staff_disagreement",
             "Administration disagreement with the public or staff",
             "Administration disagreeing with the public or with staff.")
    co = pool(p4, ["possible_factual_correction_or_contradiction"])
    ex = pool(p4, ["explicit_disagreement_language"])
    L += queue_section("Possible corrections/contradictions", co, 25,
                       "Shared pool with workbook 07 — split by verified target: administration↔public or administration↔staff for this video.")
    L += queue_section("Explicit disagreement language", ex, 20)
    L += checklist(CHECK_GENERIC + [
        "Preserve the full statement answered and the complete response; never cut the rebuttal.",
        "Verify the target's status (public commenter vs staff) on footage before classifying.",
        "Known false-positive classes are documented in phase-04 candidate_screening_notes.md — re-screen each keep."])
    L += edl_note()
    return "08_admin_public_staff_disagreement", L


def wb09(p3):
    L = head(9, "public_criticism_of_administration",
             "Non-Miller public comments criticizing administration conduct or legality",
             "Public comments (not by Miller) criticizing administration conduct or legality.")
    cr = pool(p3, ["possible_public_comment_criticism_near_gate_outside_miller_window"])
    L += queue_section("Criticism/legal-language cues near comment gates, outside Miller windows",
                       cr, 25,
                       "102 cues total. Verify each is a public comment (not staff/council talk), identify its target, and preserve any response.")
    L += checklist(CHECK_GENERIC + [
        "Confirm the speaker is a member of the public (not Miller, not staff, not council) and the comment occurred in a public-comment period.",
        "Assess legal claims separately: a commenter asserting illegality is a statement, not a finding. Do not add legal overlays without counsel review.",
        "Include the administration's response, if any, in the same cut."])
    L += edl_note()
    return "09_public_criticism_of_administration", L


def wb10():
    L = head(10, "cox_ranch_legal_record_overview",
             "Cox Ranch annexation/zoning/PlanCheyenne legal-record issue overview",
             "Cox Ranch annexation, ordinances, zoning and plan changes juxtaposed with law/cases.")
    L += [
        "## Sources (document-based — no candidate scan)",
        "",
        "- `phase-05-cox-ranch-issues/issue_matrix.md` — the separately-identified annexation / assigned zoning / BP zoning / Future Land Use-USB actions and open questions (acreage, contiguity, petition, notice, protest, review period, industrial siting).",
        "- `phase-05-cox-ranch-issues/source_register.md` — C1–C9 City/Granicus sources and W1–W7 Wyoming statute/bill sources with per-source limits.",
        "- `phase-05-cox-ranch-issues/record_requests.md` — prioritized Clerk request checklist.",
        "- Footage windows already in the Batch 1 EDLs: W-03 + L-03 (Aug 28 work session) and W-04 + L-04 (Sep 14 second reading) — reuse those verified cuts; do not re-review them independently.",
        "- The September 28, 2026 Granicus recording (player clip 1137) — exists, **not yet reviewed**; needed for any third-reading footage.",
        "",
        "## Hard rules for this video",
        "",
        "- Show source status on screen for every claim: staff analysis vs draft ordinance vs secondary reporting vs signed instrument vs recorded map.",
        "- Keep each acreage/contiguity figure attached to its document (staff report 1,259.91 ac; unsigned draft 1,252.09 ac + separate 10.23 ac City parcel; BP packet ≈1,197.76 ac; FLUM packet 1,193.4 ac — all draft-stage).",
        "- Do not call draft acreage final; do not characterize any action as illegal.",
        "- The September 28 vote/outcome is secondary (news report) until confirmed by certified minutes/journal, signed action, publication, and final map — the City archive showed no linked minutes at the 2026-10-02 check.",
        "- Include contrary authority and pin cites with effective dates for every cited statute/case; counsel review before any legal conclusion.",
        "",
        "## Verification checklist",
        "",
        *[f"- [ ] {c}" for c in [
            "Re-verify every source link in the register (they were unreachable from the production sandbox this pass).",
            "Obtain and review the September 28 recording and any certified minutes before showing any third-reading footage or outcome.",
            "Confirm current statutory text (post-2023 HB0142 notice amendments; 2025 SF0016; failed 2025 SF0040 / 2026 HB0076) on the effective dates.",
            "Counsel review of the final script before render."]],
        "",
    ]
    L += edl_note()
    return "10_cox_ranch_legal_record_overview", L


def wb11(p2):
    L = head(11, "miller_introductions_greetings",
             "Jennifer/staff introductions of Miller and mayor/chair greetings",
             "All Miller introductions by Jennifer (clerk) and greetings by the mayor or chair.")
    staff = pool(p2, ["possible_staff_recognition"])
    greet = pool(p2, ["possible_greeting_phrase_near_miller"])
    intro = pool(p2, ["possible_self_introduction_or_record_identification"])
    floor = pool(p2, ["possible_floor_recognition"])
    L += queue_section("Staff-recognition cues (Jennifer et al.)", staff, 25)
    L += queue_section("Greeting phrases near Miller", greet, 15)
    L += queue_section("Self-introduction / record-identification cues", intro, 15,
                       "Most self-introductions are Miller stating his own name — relevant as bookends, not as introductions by staff.")
    L += queue_section("Floor-recognition cues (context class)", floor, 15,
                       "Large context class (111 cues). Captions cannot establish who is speaking or who is greeting whom — verify each on footage.")
    L += checklist(CHECK_GENERIC + [
        "Confirm on footage that the introducer/greeter is staff/mayor/chair (role, not just caption proximity).",
        "Note the exact form of each introduction and any procedural framing (e.g., Zoom vs in-person handling)."])
    L += edl_note()
    return "11_miller_introductions_greetings", L


def wb12(p2, legacy_path):
    L = head(12, "miller_interruptions",
             "Every interruption Miller faced",
             "Every interruption Miller faced (complete reel, not the legacy selected montage).")
    legacy = json.load(open(legacy_path))
    flags = Counter()
    meets = Counter()
    for r in legacy:
        for k in ("interrupted", "mic_cut", "point_of_order", "time_called"):
            if r.get(k):
                flags[k] += 1
        meets[r.get("date", "?")] += 1
    L += [
        "## Legacy caption-aligned index (616 rows, 20 meetings, Jan 12 – Jul 27, 2026)",
        "",
        f"Flags: {dict(flags)}. This is the starting universe, **not** an adjudicated count; it ends July 27 and does not cover every committee.",
        "",
        "Cues per meeting: " + ", ".join(f"{d} ({n})" for d, n in sorted(meets.items())),
        "",
        "Reference copy: `production/reference/miller_interventions.json` (provenance in `reference/REFERENCE_PROVENANCE.md`).",
        "",
    ]
    tl = pool(p2, ["possible_time_limit_or_interruption_near_miller"])
    oo = pool(p2, ["possible_out_of_order_or_relevance_ruling_near_miller"])
    L += queue_section("Time-limit / interruption keyword cues near Miller (Phase 2 extension)",
                       tl, 20)
    L += queue_section("Out-of-order / relevance ruling cues near Miller", oo, 15)
    L += checklist(CHECK_GENERIC + [
        "Distinguish on footage: overlapping speech, a chair ruling, a timer event, a technical fault, or a caption artifact — only the first two are interruptions in the deliverable sense.",
        "Include meetings after July 27, 2026 (the legacy index's end) from the Phase 2 pool and the transcript corpus.",
        "Do not reuse THE_CALLER_TAPE scope: this deliverable is the exhaustive reel, with each event kept in full context."])
    L += edl_note()
    return "12_miller_interruptions", L


def wb13(p2):
    L = head(13, "responses_mentions_miller",
             "Responses, mentions, and questions about Miller",
             "Every response, mention, or question about Miller (not his own turns).")
    ex = pool(p2, ["explicit_miller_reference"])
    re = pool(p2, ["possible_reply_or_correction_near_miller"])
    L += queue_section("Explicit Miller-name cues (the universe)", ex, 15,
                       "594 cues — review universe. Meeting-level batching below; list is the first 15 by date.")
    L += queue_section("Possible reply/correction keyword cues near Miller", re, 20,
                       "Two-cue context on either side is not automatically a response — verify who answered whom on footage.")
    L += checklist(CHECK_GENERIC + [
        "Exclude Miller's own turns; keep only what others said about/to him, with the prompt that produced it.",
        "Watch for the two excluded false-reference classes (Miller Lane; a separately named Brandt Miller) documented in the Phase 4 notes — the name filter already excludes them from P4, but P2 name cues still need identity checks."])
    L += edl_note()
    return "13_responses_mentions_miller", L


def wb14(p2, p3):
    L = head(14, "equal_time_limit_enforcement",
             "Equal enforcement of time limits",
             "Equal enforcement of time limits — a matched comparison, not keyword hits.")
    tl = pool(p3, ["possible_time_limit_or_call_outside_miller_window"])
    capr = pool(p3, ["possible_comment_cap_or_time_rule_statement"])
    mtl = pool(p2, ["possible_time_limit_or_interruption_near_miller"])
    L += queue_section("Time-limit calls outside Miller windows (comparison arm A)", tl, 20)
    L += queue_section("Rule statements (the written rule in force)", capr, 20)
    L += queue_section("Time-limit cues near Miller (comparison arm B)", mtl, 20,
                       "See also workbook 12/16 pools; this video needs the matched treatment, not the exhaustive reel.")
    L += checklist(CHECK_GENERIC + [
        "Build the matched denominator first: every timed speaker under the same rule on the same item/body, with actual timer start/stop measured on footage.",
        "Log for each: time consumed by the speaker vs by questions/rulings/interruptions/technical delay, and any restored time.",
        "No enforcement-disparity conclusion without the full denominator; otherwise render 'not established'.",
        "State the written rule (UDC § / council rules) and any chair discretion actually exercised, on screen."])
    L += edl_note()
    return "14_equal_time_limit_enforcement", L


def wb15(p2, p3):
    L = head(15, "out_of_order_comparisons",
             "Out-of-order rulings against Miller compared with other speakers",
             "Out-of-order rulings against Miller compared with other speakers — verify the named comparator.")
    oo = pool(p2, ["possible_out_of_order_or_relevance_ruling_near_miller"])
    tr = pool(p3, ["possible_topic_or_relevance_ruling_outside_miller_window"])
    L += queue_section("Out-of-order / relevance rulings near Miller", oo, 46)
    L += queue_section("Topic/relevance rulings outside Miller windows (comparator arm)", tr, 31)
    L += checklist(CHECK_GENERIC + [
        "For each ruling: capture the conduct that triggered it, the rule invoked, the exact ruling words, and the outcome on the speaker's time.",
        "Verify any named comparator actually exists on footage before including the comparison; if none can be verified, deliver the Miller-side reel with a 'no verified comparator located' card instead of a forced match.",
        "Do not infer viewpoint discrimination from the rulings alone."])
    L += edl_note()
    return "15_out_of_order_comparisons", L


def wb16(p2, legacy_path):
    L = head(16, "interruptions_time_consumed",
             "Interruptions that consumed Miller's time without time credit",
             "Interruptions that consumed Miller's time without time credit.")
    legacy = json.load(open(legacy_path))
    mc = [r for r in legacy if r.get("mic_cut") or r.get("time_called")]
    L += [
        "## Legacy flag starting points",
        "",
        f"`mic_cut` and `time_called` flags in the legacy index: {len(mc)} rows. Timer-credit claims cannot come from captions — every row needs the visible timer and the chair's ruling on footage.",
        "",
    ]
    ta = pool(p2, ["possible_timer_adjustment_near_miller"])
    tl = pool(p2, ["possible_time_limit_or_interruption_near_miller"])
    L += queue_section("Timer-adjustment cues (rare — highest priority)", ta, 5)
    L += queue_section("Time-limit / interruption cues near Miller", tl, 20)
    L += checklist(CHECK_GENERIC + [
        "Measure on footage: when Miller's clock started, every stop/reset, time consumed by each interruption, and whether any time was restored (and by whom).",
        "Log technical delays separately from rulings and deliberate stops.",
        "A 'no time credit' claim requires the timer display to be visible or the chair's words to be explicit; otherwise mark unverifiable."])
    L += edl_note()
    return "16_interruptions_time_consumed", L


def wb17(p4, p2):
    L = head(17, "supportive_reactions",
             "Favorable/supportive reactions toward Miller",
             "Favorable or supportive reactions toward Miller.")
    sup = pool(p4, ["possible_supportive_reaction_near_miller_reference"])
    L += queue_section("Phase 4 narrow support-pattern hits", sup, 5,
                       "Exactly one machine hit corpus-wide — the scanners were built for disagreement, not support. Do not treat this as evidence that only one supportive reaction exists.")
    L += [
        "## Honest gap and required manual pass",
        "",
        "No systematic support-scan exists in Phases 2–4. The review universe for this video is the Phase 2 `explicit_miller_reference` pool (594 cues) plus applause/laughter/thank-you patterns in the transcripts — a manual pass is required, meeting by meeting.",
        "",
        "Also note: `[applause]` markers appear in caption text; applause is not necessarily directed at the speaker or his position — verify direction and target on footage.",
        "",
    ]
    ex = pool(p2, ["explicit_miller_reference"])
    L += queue_section("Explicit Miller-name cues (manual-pass universe, first 15 by date)", ex, 15)
    L += checklist(CHECK_GENERIC + [
        "Classify each verified reaction: supportive statement, favorable ruling treatment, applause/laughter, or neutral/none — keep the classification criteria on screen or in the EDL.",
        "Do not infer support from silence, absence of objection, or a neutral ruling."])
    L += edl_note()
    return "17_supportive_reactions", L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phases-dir", required=True,
                    help="directory containing phase-02-*/…/phase-04-* candidate_events.jsonl")
    a = ap.parse_args()
    p2 = load(os.path.join(a.phases_dir, P2))
    p3 = load(os.path.join(a.phases_dir, P3))
    p4 = load(os.path.join(a.phases_dir, P4))
    legacy = os.path.join(HERE, "reference", "miller_interventions.json")
    print(f"loaded: P2={len(p2)} P3={len(p3)} P4={len(p4)}")

    builders = [
        lambda: wb03(p2), lambda: wb04(p3), lambda: wb05(p3), lambda: wb06(p3),
        lambda: wb07(p4), lambda: wb08(p4), lambda: wb09(p3), lambda: wb10(),
        lambda: wb11(p2), lambda: wb12(p2, legacy), lambda: wb13(p2),
        lambda: wb14(p2, p3), lambda: wb15(p2, p3), lambda: wb16(p2, legacy),
        lambda: wb17(p4, p2),
    ]
    outdir = os.path.join(HERE, "workbooks")
    os.makedirs(outdir, exist_ok=True)
    for b in builders:
        slug, lines = b()
        path = os.path.join(outdir, slug + ".md")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
