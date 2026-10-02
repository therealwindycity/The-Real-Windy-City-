#!/usr/bin/env python3
"""Generate EDL skeletons for videos 01 and 02 from the Phase 1 clip manifest.

Output: production/edl/01_wolfe_positions.edl.json and 02_laybourn_positions.edl.json

Every clip is emitted with status "pending-footage-review": render_video.py will
REFUSE to render until a human reviewer has watched the master at the cue and
marked the clip "verified" (and filled the verification fields). Slate content
follows the handoff rule: source date, body, agenda item, original URL, and
source in/out on screen before every clip.

Run:  python3 generate_edl_batch01.py   (from the production/ directory)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "reference", "phase-01_clip_manifest.json")

BODY_SLUG = {
    "City Council": "city-council",
    "Public Services Committee": "public-services-committee",
    "City Council Work Session": "work-session",
}

GAP_CARDS = {
    "wolf-position-timeline": [
        {"after": "W-01", "duration": 5, "card": {
            "title": "DIFFERENT BODY, DIFFERENT PROJECT",
            "lines": ["Next: July 6, 2026 — Public Services Committee — Microsoft annexation item.",
                      "This is NOT the June 22 Swan Ranch / Industrial Siting Act discussion.",
                      "Do not present the two as one conversation."]}},
        {"after": "W-02B", "duration": 5, "card": {
            "title": "DIFFERENT SETTING",
            "lines": ["Next: August 28, 2026 — City Council WORK SESSION on the Cox Ranch annexation update.",
                      "Work session: council discussion, no public input.",
                      "A negotiation proposal here is not an adopted agreement and not a ruling on the June 22 state-authority question."]}},
        {"after": "W-03", "duration": 5, "card": {
            "title": "SECOND READING",
            "lines": ["Next: September 14, 2026 — City Council — Cox Ranch annexation, second reading.",
                      "Preserve Wolfe's full statement, intervening council comments, and the roll call/result.",
                      "A no vote is not a finding that any legal claim was correct."]}}
    ],
    "laybourn-position-timeline": [
        {"after": "L-01", "duration": 5, "card": {
            "title": "DIFFERENT BODY, DIFFERENT ITEM",
            "lines": ["Next: June 15, 2026 — Public Services Committee — rezoning/planning item and comment procedure.",
                      "This is NOT the June 22 Swan Ranch item and NOT Cox Ranch.",
                      "Verify the actual timer on footage before any lost-time or time-limit claim."]}},
        {"after": "L-02", "duration": 5, "card": {
            "title": "WORK SESSION",
            "lines": ["Next: August 28, 2026 — Cox Ranch update work session.",
                      "Show Laybourn's argument to discuss the proposed agreement in a work session and the chair's contrary scope ruling.",
                      "Do not imply the room was taking public comments."]}},
        {"after": "L-03", "duration": 5, "card": {
            "title": "SECOND READING — ROLL CALL",
            "lines": ["Next: September 14, 2026 — Cox Ranch annexation, second reading.",
                      "Auto-captions mis-spell names in the roll call ('Mr. Leborn, Mr. Moody, Mr. Wolf').",
                      "Verify each name against the recording and official minutes before graphics use."]}}
    ],
}


def master_for(date: str, body: str) -> str:
    return f"{date}-{BODY_SLUG[body]}.mp4"


def build(film: str, video_id: str, base: str, title: str) -> dict:
    with open(MANIFEST) as f:
        p1 = json.load(f)
    segs = sorted([s for s in p1["segments"] if s["film"] == film],
                  key=lambda s: s["sequence"])

    # unique masters in sequence order
    masters, midx = [], {}
    for s in segs:
        key = (s["date"], s["body"])
        if key not in midx:
            midx[key] = len(masters)
            masters.append({"master": master_for(s["date"], s["body"]),
                            "source_url": s["source_url"],
                            "youtube_id": s["youtube_id"],
                            "date": s["date"], "body": s["body"]})

    clips = []
    for s in segs:
        clips.append({
            "id": s["id"],
            "source": midx[(s["date"], s["body"])],
            "date": s["date"], "body": s["body"],
            "agenda_scope": s["agenda_scope"],
            "in": s["source_in"], "out": s["source_out"],
            "status": "pending-footage-review",
            "fade": 0.0,
            "slate": {
                "title": f"{s['date']} — {s['body']}",
                "duration": 5,
                "lines": [
                    f"Agenda item: {s['agenda_scope']}",
                    f"On camera: {', '.join(s['speaker_focus'])}",
                    f"Source: {s['source_url']}",
                    f"Source in/out: {s['source_in']} – {s['source_out']} (official recording)",
                ],
            },
            "verification": {
                "required_text_on_audio": s["required_text"],
                "editorial_note": s["editorial_note"],
                "speaker_identity_confirmed": None,
                "complete_turns_preserved": None,
                "context_lead_lag_reviewed": None,
                "caption_corrections": [],
                "reviewer": None, "review_date": None,
            },
            "caption_pending_note": "Transcript pending verification against audio; corrections will be logged in the EDL.",
        })

    edl = {
        "video_id": video_id,
        "title": title,
        "output_base": base,
        "status": "pending-footage-review",
        "handoff_rules": [
            "Confirm identity from the recording and/or reliable contemporaneous records before using official-name spellings in graphics.",
            "Keep unlike agenda items separate; never juxtapose separate dates/items as one conversation.",
            "Preserve complete turns, questions/prompts, chair rulings, responses, relevant roll call/outcome, and context before/after each cut.",
            "A no vote or a negotiation proposal does not prove adoption of Miller's legal position.",
        ],
        "sources": masters,
        "clips": clips,
        "gaps": GAP_CARDS[film],
    }
    return edl


def main() -> None:
    jobs = [
        ("wolf-position-timeline", "01", "01_wolfe_positions",
         "Lawrence J. Wolfe — position timeline (statements about Miller, delegated state authority, and later local negotiating choices)"),
        ("laybourn-position-timeline", "02", "02_laybourn_positions",
         "Pete Laybourn — position timeline (early criticism of Miller and later statements/actions)"),
    ]
    for film, vid, base, title in jobs:
        edl = build(film, vid, base, title)
        out = os.path.join(HERE, "edl", base + ".edl.json")
        with open(out, "w") as f:
            json.dump(edl, f, indent=2)
        print(f"wrote {out}  ({len(edl['clips'])} clips, {len(edl['sources'])} masters)")


if __name__ == "__main__":
    main()
