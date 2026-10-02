#!/usr/bin/env python3
"""extract_review_windows.py — build a human footage-review kit from an EDL.

For every EDL clip still marked "pending-footage-review", this cuts a REVIEW
copy from the downloaded master (window + lead/lag), burns the MASTER
timestamp into the picture (so the reviewer can propose exact adjusted
in/out points), exports draft captions for the window from the caption-derived
transcript (clearly labeled DRAFT), and writes a pre-filled verification form
with the window's required text and editorial note.

Why this exists: footage verification is a human step (watch/listen at the cue
with enough lead/lag, confirm words/speaker/item/turns). This tool packages
everything the reviewer needs per window into one folder so verification is
minutes, not an evening. It never marks anything verified itself.

Outputs (per window, under --out):
  review/<CLIPID>_review.mp4        window+lead/lag, master-time burn-in
  review/<CLIPID>_draft.srt         caption-derived DRAFT cues for the window
  review/<CLIPID>_form.md           verification form to fill in

After review, transfer the form's answers into the EDL (verification block,
status -> "verified", adjusted in/out, caption corrections) and render with
render_video.py.

Usage:
  python3 extract_review_windows.py --edl production/edl/01_wolfe_positions.edl.json \
      --masters source-masters --transcripts cheyenne-2026-transcripts \
      --out review_kit [--lead 120] [--lag 60] [--ffmpeg /path/to/ffmpeg]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys

if sys.version_info >= (3, 9):
    from importlib import util as _ilu
else:
    import importlib.util as _ilu


def _import_render(ffmpeg_hint: str | None):
    """Import render_video.py from the same directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "render_video.py")
    spec = _ilu.spec_from_file_location("render_video", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def t2s(ts: str) -> float:
    parts = [float(p) for p in str(ts).split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def s2t(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


TS_RE = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]")


def transcript_cues(path: str, start: float, end: float) -> list[dict]:
    """Pull caption-derived cues with timestamps within [start, end] from a
    transcript .md file. Robust to both blank-line-separated and single-line
    formats: cues are delimited by their own [HH:MM:SS] markers."""
    data = open(path, encoding="utf-8").read()
    parts = TS_RE.split(data)          # [pre, ts1, text1, ts2, text2, ...]
    cues = []
    for i in range(1, len(parts) - 1, 2):
        ts = t2s(parts[i])
        text = " ".join(parts[i + 1].split())
        if text and start - 5.0 <= ts <= end + 5.0:
            cues.append({"time": ts, "text": text[:800]})
    return cues


def ass_timestamp_track(path: str, rstart: float, length: float, w: int, h: int) -> None:
    """Write an .ass file showing the MASTER clock once per second (bottom center).
    (The minimal ffmpeg builds used here ship libass but not drawtext.)"""
    def hms(t: float) -> str:
        t = int(t)
        return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"

    def ass_t(t: float) -> str:
        t = max(0.0, t)
        hh = int(t // 3600); mm = int((t % 3600) // 60); ss = t % 60
        return f"{hh:d}:{mm:02d}:{ss:05.2f}"

    events = []
    k = 0.0
    while k < length:
        events.append(f"Dialogue: 0,{ass_t(k)},{ass_t(min(k + 1.0, length))},Clock,,0,0,0,,"
                      f"MASTER {hms(rstart + k)}")
        k += 1.0
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # BorderStyle 3 = opaque box; colours are &HAABBGGRR
        "Style: Clock,DejaVu Sans,22,&H00FFFFFF,&H00FFFFFF,&H88000000,&H88000000,"
        "-1,0,0,0,100,100,0,0,3,1,1,2,20,20,12,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    with open(path, "w") as f:
        f.write(header + "\n".join(events) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edl", required=True)
    ap.add_argument("--masters", required=True)
    ap.add_argument("--transcripts", required=True,
                    help="path to cheyenne-2026-transcripts/ (for draft captions)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lead", type=float, default=120.0)
    ap.add_argument("--lag", type=float, default=60.0)
    ap.add_argument("--only", help="only this clip id")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    rv = _import_render(a.ffmpeg)
    ffmpeg = rv.find_tool("ffmpeg", a.ffmpeg)
    ffprobe = shutil.which("ffprobe")

    edl = json.load(open(a.edl))
    catalog = {}
    cat_path = os.path.join(a.transcripts, "meetings.json")
    if os.path.exists(cat_path):
        for mrow in json.load(open(cat_path)):
            catalog[(mrow["date"], mrow["body"])] = mrow["file"]

    os.makedirs(a.out, exist_ok=True)
    pending = [c for c in edl["clips"] if c.get("status") != "verified"]
    if a.only:
        pending = [c for c in pending if c["id"] == a.only]
    print(f"{len(pending)} window(s) to prepare for review")

    index = ["# Review kit — " + edl.get("title", ""),
             "",
             f"Prepared {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
             f"lead {a.lead:.0f}s / lag {a.lag:.0f}s · master timestamps burned into the picture",
             "",
             "For each window: watch the review file (NOT just the draft captions), then fill "
             "the form. Draft captions are caption-derived and WILL contain errors — correct "
             "against the audio and log every correction.",
             ""]

    for clip in pending:
        src_spec = edl["sources"][clip["source"]]
        master = os.path.join(a.masters, os.path.basename(src_spec["master"]))
        if not os.path.exists(master):
            print(f"  SKIP {clip['id']}: master missing ({master})")
            continue
        info = rv.probe_media(ffmpeg, ffprobe, master)
        cin, cout = t2s(clip["in"]), t2s(clip["out"])
        rstart = max(0.0, cin - a.lead)
        rend = min(info["duration"], cout + a.lag)
        rid = clip["id"]

        # ---- review cut with master-time burn-in -------------------------
        # Burn the MASTER clock via libass (drawtext is absent from the
        # minimal ffmpeg builds used here). Input-side -ss resets output
        # timestamps to 0, so ASS event t=0 == master time rstart.
        out_mp4 = os.path.join(a.out, f"{rid}_review.mp4")
        ass_path = os.path.join(a.out, f"{rid}_clock.ass")
        ass_timestamp_track(ass_path, rstart, rend - rstart, info["width"], info["height"])
        ass_arg = ass_path.replace("\\", "/").replace(":", "\\:")
        try:
            rv.run([ffmpeg, "-y",
                    "-ss", f"{rstart:.3f}", "-i", master,
                    "-t", f"{rend - rstart:.3f}",
                    "-vf", f"ass={ass_arg}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", out_mp4])
        except RuntimeError as e:
            print(f"  FAIL {rid}: {e}")
            continue

        # ---- draft captions from the transcript --------------------------
        srt_path = os.path.join(a.out, f"{rid}_draft.srt")
        tfile = os.path.join(a.transcripts, catalog.get((clip["date"], clip["body"]), ""))
        draft_blocks = []
        if os.path.exists(tfile):
            cues = transcript_cues(tfile, rstart, rend)
            for i, cue in enumerate(cues, 1):
                t0, t1 = cue["time"], cue["time"] + max(4.0, min(9.0, len(cue["text"]) / 14.0))
                draft_blocks.append(
                    f"{i}\n{rv._fmt_srt(t0 - rstart)} --> {rv._fmt_srt(min(t1, rend) - rstart)}\n"
                    f"[DRAFT caption-derived — verify against audio] {cue['text']}\n")
        with open(srt_path, "w") as f:
            f.write("\n".join(draft_blocks) if draft_blocks else
                    "1\n00:00:00,000 --> 00:00:04,000\n[DRAFT] no transcript cues found for this window\n")

        # ---- verification form -------------------------------------------
        v = clip.get("verification", {})
        form = [
            f"# Verification form — {rid}",
            "",
            f"- **Meeting:** {clip.get('date')} {clip.get('body')} — {clip.get('agenda_scope', '')}",
            f"- **Planned window:** {clip['in']} – {clip['out']} (review file covers {s2t(rstart)} – {s2t(rend)})",
            f"- **Master:** `{os.path.basename(master)}` ({src_spec.get('source_url', '')})",
            f"- **Speaker focus:** {', '.join(src_spec.get('speaker_focus', clip.get('speaker_focus', [])) or []) or '—'}",
            "",
            "## Required text (must be confirmed on audio)",
            "",
            *[f"- [ ] “{t}”" for t in (v.get("required_text_on_audio") or [])],
            "",
            "## Editorial note (scope rules for this window)",
            "",
            (v.get("editorial_note") or "—"),
            "",
            "## Reviewer findings",
            "",
            f"- Speaker identity confirmed (who says the key lines): ",
            f"- Complete turn(s) present, incl. prompt and response: yes/no — notes: ",
            f"- Adjusted source IN (master time, if trim needed): ",
            f"- Adjusted source OUT (master time): ",
            f"- Timer visible? Start/stop/credit observed (if relevant): ",
            f"- Caption corrections (cue → what was actually said): ",
            f"- Anything in lead/lag that changes the meaning: ",
            f"- Verdict (include / include-with-trim / exclude + reason): ",
            f"- Reviewer / date: ",
            "",
            "Transfer these answers into the EDL clip block (verification.*), set "
            f"`\"status\": \"verified\"`, then render.",
        ]
        with open(os.path.join(a.out, f"{rid}_form.md"), "w") as f:
            f.write("\n".join(form) + "\n")

        size_mb = os.path.getsize(out_mp4) / 1e6
        print(f"  OK {rid}: review cut {s2t(rstart)}–{s2t(rend)} ({rend - rstart:.0f}s, "
              f"{size_mb:.1f} MB), draft SRT + form written")
        index.append(f"- [{rid}]({os.path.basename(out_mp4)}) — {clip.get('date')} "
                     f"{clip.get('body')} — planned {clip['in']}–{clip['out']} — "
                     f"[form]({rid}_form.md) — [draft captions]({rid}_draft.srt)")

    with open(os.path.join(a.out, "INDEX.md"), "w") as f:
        f.write("\n".join(index) + "\n")
    print(f"\nkit index: {os.path.join(a.out, 'INDEX.md')}")


if __name__ == "__main__":
    main()
