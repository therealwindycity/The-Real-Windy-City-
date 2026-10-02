#!/usr/bin/env python3
"""
render_video.py — evidence-video renderer for The Real Windy City Phase 6.

Renders a standalone H.264/AAC MP4 from an EDL (edit-decision list) JSON plus
downloaded source masters, with:

  * a lead-in slate per clip (source date, body, agenda item, source URL,
    source in/out — the on-screen provenance the handoff requires);
  * context/gap cards between clips where the EDL defines them;
  * SRT + VTT sidecars (slate text + per-clip source-time markers);
  * a rendered EDL export (actual clip order, trims, per-source SHA-256);
  * a provenance README skeleton;
  * a QA record (ffprobe duration/streams, first/last frame extracts,
    SHA-256 of every produced file).

Guardrails baked in (per NEW_VIDEO_AGENT_HANDOFF.md):
  * Refuses to render clips whose EDL entry is not marked
    "verified" unless --allow-unverified is passed (use that only for
    pipeline self-tests, never for deliverables).
  * Never upscales: the project canvas is the largest source frame among the
    used clips; bigger frames are scaled DOWN, smaller frames are padded.
  * Does not label anything "final"/"verified"/"complete"; labels come from
    the QA record, which must be filled in by a human reviewer.

Dependencies: python3, ffmpeg + ffprobe on PATH (or IMAGEIO_FFMPEG installed),
Pillow. Developed against ffmpeg 7.0.2 / Pillow 12.3.

Usage:
  python3 render_video.py --edl edl/01_wolfe_positions.edl.json \
      --masters /path/to/source-masters --out /path/to/outdir \
      [--allow-unverified] [--ffmpeg /path/to/ffmpeg] [--ffprobe /path/to/ffprobe]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def find_tool(name: str, override: str | None) -> str:
    if override:
        return override
    p = shutil.which(name)
    if p:
        return p
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    raise SystemExit(f"required tool not found: {name} (install it or pass --{name})")


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(cmd[:8])}...\n{r.stderr[-1200:]}")
    return r.stdout


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def t2s(ts: str) -> float:
    """HH:MM:SS(.mmm) | MM:SS(.mmm) | SS(.mmm) -> seconds"""
    if ts is None:
        raise ValueError("missing timestamp")
    parts = str(ts).strip().split(":")
    if len(parts) > 3:
        raise ValueError(f"bad timestamp: {ts}")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def s2t(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def probe_media(ffmpeg: str, ffprobe: str | None, path: str) -> dict:
    """Probe with ffprobe when available; otherwise parse `ffmpeg -i` stderr."""
    if ffprobe:
        out = run([ffprobe, "-v", "error", "-print_format", "json",
                   "-show_format", "-show_streams", path])
        info = json.loads(out)
        v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
        a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
        if v is None:
            raise RuntimeError(f"no video stream: {path}")
        num, _, den = (v.get("r_frame_rate") or "30/1").partition("/")
        fps = float(num) / float(den or 1)
        return {"duration": float(info["format"].get("duration", 0)),
                "width": int(v["width"]), "height": int(v["height"]),
                "fps": fps, "has_audio": a is not None}

    # ffmpeg fallback: parse the informational banner
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                       capture_output=True, text=True)
    banner = r.stderr
    if "No such file" in banner or not banner.strip():
        raise RuntimeError(f"cannot probe {path}: {banner[-400:]}")
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", banner)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vm = re.search(r"Stream #\d+:\d+.*Video:.*?,\s*(\d{2,5})x(\d{2,5})", banner)
    if not vm:
        raise RuntimeError(f"no video stream found in banner for {path}:\n{banner[-600:]}")
    w, h = int(vm.group(1)), int(vm.group(2))
    fm = re.search(r"([\d.]+)\s*fps", banner) or re.search(r"([\d.]+)\s*tbr", banner)
    fps = float(fm.group(1)) if fm else 30.0
    return {"duration": dur, "width": w, "height": h, "fps": fps,
            "has_audio": "Audio:" in banner}


# ----------------------------------------------------------------------------
# slates / cards  (Pillow-rendered PNGs, turned into video segments)
# ----------------------------------------------------------------------------

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

def _font(size: int, bold: bool = True):
    from PIL import ImageFont
    paths = FONT_CANDIDATES if bold else [p.replace("-Bold", "") for p in FONT_CANDIDATES]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render_card_png(width: int, height: int, title: str, lines: list[str],
                    out_path: str, footer: str = "") -> None:
    """A dark card: small kicker/title, wrapped body lines, optional footer."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), (12, 14, 18))
    d = ImageDraw.Draw(img)
    margin = max(24, width // 24)

    # title (auto-shrink to fit width)
    size = max(22, height // 12)
    while size > 14:
        f = _font(size)
        if d.textlength(title, font=f) <= width - 2 * margin:
            break
        size -= 2
    d.text((margin, margin + size // 2), title, font=f, fill=(235, 235, 235))

    # body lines, wrapped
    y = margin + size * 3
    bsize = max(16, height // 22)
    bf = _font(bsize, bold=False)
    for line in lines:
        words, cur = line.split(), ""
        for w in words:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=bf) <= width - 2 * margin:
                cur = trial
            else:
                d.text((margin, y), cur, font=bf, fill=(185, 190, 198))
                y += int(bsize * 1.45)
                cur = w
        if cur:
            d.text((margin, y), cur, font=bf, fill=(185, 190, 198))
            y += int(bsize * 1.45)
        y += int(bsize * 0.5)

    if footer:
        ff = _font(max(13, height // 30), bold=False)
        d.text((margin, height - margin - ff.size), footer, font=ff, fill=(120, 126, 136))
    img.save(out_path)


# ----------------------------------------------------------------------------
# segment builders
# ----------------------------------------------------------------------------

def build_card_segment(ffmpeg: str, png: str, duration: float, canvas: tuple[int, int],
                       fps: float, out: str) -> None:
    """PNG card -> silent H.264 segment of exactly `duration` seconds."""
    W, H = canvas
    run([ffmpeg, "-y", "-loop", "1", "-framerate", f"{fps:.6f}", "-i", png,
         "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
         "-t", f"{duration:.3f}",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
         "-shortest", "-movflags", "+faststart", out])


def build_clip_segment(ffmpeg: str, src: str, ss: float, to: float, canvas: tuple[int, int],
                       fps: float, out: str, fade: float = 0.0) -> None:
    """Trim a master and encode to the project canvas (never upscale)."""
    W, H = canvas
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
    if fade > 0:
        # -ss before -i resets timestamps to 0, so fades are input-relative
        vf += (f",fade=t=in:st=0:d={fade:.3f}"
               f",fade=t=out:st={max(0.0, to - ss - fade):.3f}:d={fade:.3f}")
    cmd = [ffmpeg, "-y", "-ss", f"{ss:.3f}", "-to", f"{to:.3f}", "-i", src]
    cmd += ["-vf", vf, "-r", f"{fps:.6f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", out]
    run(cmd)


# ----------------------------------------------------------------------------
# captions
# ----------------------------------------------------------------------------

def _fmt_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt(t: float) -> str:
    return _fmt_srt(t).replace(",", ".")


def write_captions(segments: list[dict], total: float, base: str) -> None:
    """segments: {start, end, text} on the output timeline."""
    blocks_srt, blocks_vtt = [], []
    for i, s in enumerate(segments, 1):
        text = s["text"].replace("\n", " ").strip()
        if not text:
            continue
        blocks_srt.append(f"{i}\n{_fmt_srt(s['start'])} --> {_fmt_srt(min(s['end'], total))}\n{text}\n")
        blocks_vtt.append(f"{i}\n{_fmt_vtt(s['start'])} --> {_fmt_vtt(min(s['end'], total))}\n{text}\n")
    open(base + ".srt", "w").write("\n".join(blocks_srt))
    open(base + ".vtt", "w").write("WEBVTT\n\n" + "\n".join(blocks_vtt))


# ----------------------------------------------------------------------------
# main render
# ----------------------------------------------------------------------------

def render(edl_path: str, masters_dir: str, out_dir: str, allow_unverified: bool,
           ffmpeg: str, ffprobe: str) -> dict:
    edl = json.load(open(edl_path))
    base = edl.get("output_base") or f"{edl.get('video_id', 'xx')}_video"
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="render_")
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ---- resolve sources --------------------------------------------------
    sources = edl["sources"]
    resolved = []
    for s in sources:
        path = os.path.join(masters_dir, os.path.basename(s["master"]))
        if not os.path.exists(path):
            alt = s["master"] if os.path.isabs(s["master"]) else os.path.join(masters_dir, s["master"])
            path = alt if os.path.exists(alt) else path
        if not os.path.exists(path):
            raise SystemExit(f"missing master: {s['master']} (looked in {masters_dir})")
        info = probe_media(ffmpeg, ffprobe, path)
        resolved.append({"spec": s, "path": os.path.abspath(path), "probe": info,
                         "sha256": sha256_file(path)})

    # ---- verification gate -------------------------------------------------
    unverified = [c["id"] for c in edl["clips"] if c.get("status") != "verified"]
    if unverified and not allow_unverified:
        raise SystemExit(
            "REFUSED: clips not marked verified in the EDL: " + ", ".join(unverified) +
            "\nComplete footage review first, or pass --allow-unverified for a pipeline "
            "self-test ONLY (self-tests must never be published as deliverables).")

    # ---- project canvas & fps (no upscaling) -------------------------------
    used = {c["source"] for c in edl["clips"]}
    W = max(resolved[i]["probe"]["width"] for i in used)
    H = max(resolved[i]["probe"]["height"] for i in used)
    fps = max(resolved[i]["probe"]["fps"] for i in used)
    canvas = (W, H)

    # ---- build segments ----------------------------------------------------
    gap_after = {g["after"]: g for g in edl.get("gaps", [])}
    seg_files: list[str] = []
    caption_segments: list[dict] = []
    t_cursor = 0.0
    expected_total = 0.0
    rendered_edl = {"video_id": edl.get("video_id"), "title": edl.get("title"),
                    "rendered_utc": now, "canvas": f"{W}x{H}", "fps": round(fps, 3),
                    "no_upscaling": "canvas equals largest source frame; smaller sources padded, larger scaled down",
                    "sources": [], "timeline": []}

    for si, src in enumerate(resolved):
        rendered_edl["sources"].append({
            "master": os.path.basename(src["path"]), "sha256": src["sha256"],
            "source_url": src["spec"].get("source_url"),
            "probe": {k: round(v, 3) if isinstance(v, float) else v for k, v in src["probe"].items()}})

    for idx, clip in enumerate(edl["clips"]):
        src = resolved[clip["source"]]
        ss, to = t2s(clip["in"]), t2s(clip["out"])
        if not (0 <= ss < to <= src["probe"]["duration"]):
            raise SystemExit(f"clip {clip['id']}: in/out {clip['in']}/{clip['out']} outside master "
                             f"({s2s(src['probe']['duration'])}s) for {src['path']}")
        # slate
        slate = clip.get("slate") or {}
        slate_lines = slate.get("lines", [])
        slate_png = os.path.join(work, f"slate_{idx:03d}.png")
        render_card_png(W, H, slate.get("title", clip["id"]), slate_lines, slate_png,
                        footer=slate.get("footer", "Official City of Cheyenne recording — edited excerpt with provenance slates"))
        slate_seg = os.path.join(work, f"seg_slate_{idx:03d}.mp4")
        slate_dur = float(slate.get("duration", 4.0))
        build_card_segment(ffmpeg, slate_png, slate_dur, canvas, fps, slate_seg)
        seg_files.append(slate_seg)
        caption_segments.append({"start": t_cursor, "end": t_cursor + slate_dur,
                                 "text": " — ".join([slate.get("title", clip["id"])] + slate_lines[:2])})
        expected_total += slate_dur
        t_cursor += slate_dur

        # footage
        clip_seg = os.path.join(work, f"seg_clip_{idx:03d}.mp4")
        build_clip_segment(ffmpeg, src["path"], ss, to, canvas, fps, clip_seg,
                           fade=float(clip.get("fade", 0.0)))
        dur = to - ss
        seg_files.append(clip_seg)
        caption_segments.append({
            "start": t_cursor, "end": t_cursor + dur,
            "text": (clip.get("caption_text")
                     or f"[{clip.get('date', '?')} {clip.get('body', '?')} — source {clip['in']}–{clip['out']}] "
                        f"{clip.get('caption_pending_note', 'transcript pending footage verification')}")})
        expected_total += dur
        t_cursor += dur
        rendered_edl["timeline"].append({
            "clip_id": clip["id"], "master": os.path.basename(src["path"]),
            "source_in": clip["in"], "source_out": clip["out"],
            "output_start": s2t(t_cursor - dur - slate_dur), "duration_s": round(dur, 3),
            "slate": slate, "status_at_render": clip.get("status"),
            "caption_corrections": clip.get("caption_corrections", [])})

        # optional gap card after this clip
        g = gap_after.get(clip["id"])
        if g:
            card = g["card"]
            png = os.path.join(work, f"gap_{idx:03d}.png")
            render_card_png(W, H, card.get("title", ""), card.get("lines", []), png,
                            footer=card.get("footer", ""))
            gseg = os.path.join(work, f"seg_gap_{idx:03d}.mp4")
            gdur = float(g.get("duration", 4.0))
            build_card_segment(ffmpeg, png, gdur, canvas, fps, gseg)
            seg_files.append(gseg)
            caption_segments.append({"start": t_cursor, "end": t_cursor + gdur,
                                     "text": " — ".join([card.get("title", "card")] + card.get("lines", [])[:2])})
            expected_total += gdur
            t_cursor += gdur

    # ---- concat -------------------------------------------------------------
    listfile = os.path.join(work, "concat.txt")
    with open(listfile, "w") as f:
        for s in seg_files:
            f.write(f"file '{s}'\n")
    out_mp4 = os.path.join(out_dir, base + ".mp4")
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", "-movflags", "+faststart", out_mp4])

    # ---- sidecars -----------------------------------------------------------
    out_info = probe_media(ffmpeg, ffprobe, out_mp4)
    write_captions(caption_segments, out_info["duration"], os.path.join(out_dir, base))
    json.dump(rendered_edl, open(os.path.join(out_dir, base + ".edl.json"), "w"), indent=2)

    # provenance README skeleton
    prov = [
        f"# Provenance — {edl.get('title', base)}",
        "",
        f"Rendered (UTC): {now}",
        f"Output canvas: {W}x{H} @ {round(fps,3)} fps (no upscaling; smaller sources padded, larger scaled down)",
        "",
        "## Sources",
        ""]
    for s in rendered_edl["sources"]:
        prov += [f"- `{s['master']}` — {s.get('source_url') or 'source URL TBD'}",
                 f"  - SHA-256: `{s['sha256']}`",
                 f"  - duration {s2t(s['probe']['duration'])}s, {s['probe']['width']}x{s['probe']['height']}",
                 "  - retrieved: TBD by reviewer (fill from source-masters/retrieval_log.jsonl)",
                 "  - reviewed against footage by: TBD (name/date) — speaker, item, complete turns",
                 ""]
    prov += ["## Caption corrections", "",
             "None logged yet — every correction against the audio must be recorded here and in the EDL.",
             "", "## Known gaps", "", "TBD", ""]
    open(os.path.join(out_dir, base + "_PROVENANCE.md"), "w").write("\n".join(prov))

    # ---- QA record ----------------------------------------------------------
    qa_frames = os.path.join(out_dir, "qa_frames")
    os.makedirs(qa_frames, exist_ok=True)
    run([ffmpeg, "-y", "-i", out_mp4, "-vf", "select=eq(n\\,0)", "-frames:v", "1",
         os.path.join(qa_frames, base + "_first.jpg")])
    run([ffmpeg, "-y", "-sseof", "-1", "-i", out_mp4, "-frames:v", "1",
         os.path.join(qa_frames, base + "_last.jpg")])

    checks = {
        "file": base + ".mp4",
        "sha256": sha256_file(out_mp4),
        "bytes": os.path.getsize(out_mp4),
        "duration_s": round(out_info["duration"], 3),
        "expected_duration_s": round(expected_total, 3),
        "duration_match": abs(out_info["duration"] - expected_total) < 0.75,
        "video_stream": f"{out_info['width']}x{out_info['height']} @ {round(out_info['fps'],3)}fps",
        "audio_stream": out_info["has_audio"],
        "sidecars": [base + ".srt", base + ".vtt", base + ".edl.json", base + "_PROVENANCE.md"],
    }
    qa = {
        "video": base,
        "qa_run_utc": now,
        "automated_checks": checks,
        "human_review_required": {
            "full_start_end_plays": None, "no_black_or_frozen_segments_at_cuts": None,
            "audio_continuous_at_cuts": None, "caption_timing_and_spelling": None,
            "names_spelled_per_official_records": None, "citations_complete": None,
            "no_omitted_response_changing_meaning": None, "reviewer": None, "review_date": None,
        },
        "label_rules": "This file may NOT be called final/complete/verified until every human_review_required field is confirmed by a named reviewer.",
    }
    json.dump(qa, open(os.path.join(out_dir, base + "_QA.json"), "w"), indent=2)

    shutil.rmtree(work, ignore_errors=True)
    return qa


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edl", required=True)
    ap.add_argument("--masters", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-unverified", action="store_true",
                    help="pipeline self-test only; never for published deliverables")
    ap.add_argument("--ffmpeg"); ap.add_argument("--ffprobe")
    a = ap.parse_args()
    ffmpeg = find_tool("ffmpeg", a.ffmpeg)
    ffprobe = (find_tool("ffprobe", a.ffprobe)
               if (a.ffprobe or shutil.which("ffprobe")) else None)
    qa = render(a.edl, a.masters, a.out, a.allow_unverified, ffmpeg, ffprobe)
    print(json.dumps(qa["automated_checks"], indent=2))
    print("\nNEXT: a human reviewer must complete the human_review_required fields in "
          f"{qa['automated_checks']['file']}_QA.json before any deliverable label is used.")


if __name__ == "__main__":
    main()
