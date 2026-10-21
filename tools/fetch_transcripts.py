#!/usr/bin/env python3
"""Fetch YouTube captions for catalogued Cheyenne meetings and convert them
to the archive's Markdown transcript format.

Two modes:

  python3 tools/fetch_transcripts.py convert <video.vtt> <out.md> \
      --body city-council --date 2026-09-28 --youtube-id nwoFTXVqsH8 \
      [--topic "..."] [--captions-label "English (auto-generated)"]

  python3 tools/fetch_transcripts.py fetch [--only ID,ID] [--dry-run]
      Reads cheyenne-2026-transcripts/meetings.json, finds entries whose
      transcript file is missing (file is null or the file is absent),
      downloads their captions with yt-dlp into raw/, converts each to a
      Markdown transcript, and records the file path in meetings.json.
      Entries whose note says captions were verified absent are skipped.

Conversion matches the existing archive: repeated rolling caption windows
are de-duplicated at line level; the surviving lines are grouped into
paragraphs that keep the [HH:MM:SS] start time of their first line.
Wording is unchanged from the captions.

Requires: yt-dlp (fetch mode only), network access to youtube.com.
Designed to run locally or in GitHub Actions
(.github/workflows/fetch-transcripts.yml). Nothing here verifies a
transcript against the audio; outputs are caption transcripts, not minutes.
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "cheyenne-2026-transcripts"
CATALOG = ARCHIVE / "meetings.json"
RAW = ARCHIVE / "raw"

# body -> (display name, directory, filename slug)
BODIES = {
    "city-council": ("Cheyenne City Council", "city-council", "city-council"),
    "finance-committee": ("Cheyenne Finance Committee", "finance-committee", "finance-committee"),
    "public-services-committee": (
        "Cheyenne Public Services Committee",
        "public-services-committee",
        "public-services-committee",
    ),
    "planning-commission": (
        "Cheyenne Planning Commission",
        "planning-commission",
        "planning-commission",
    ),
    "board-of-adjustment": (
        "Cheyenne Board of Adjustment",
        "board-of-adjustment",
        "board-of-adjustment",
    ),
    "historic-preservation-board": (
        "Cheyenne Historic Preservation Board",
        "historic-preservation-board",
        "historic-preservation-board",
    ),
    "urban-renewal-authority": (
        "Cheyenne Urban Renewal Authority",
        "urban-renewal-authority",
        "urban-renewal-authority",
    ),
    "work-session": ("Cheyenne City Council Work Session", "work-sessions", None),
}

PROCESSING_NOTE = (
    "> Processing: repeated rolling caption windows were de-duplicated; cues were "
    "grouped into paragraphs with `[HH:MM:SS]` timestamps. Wording is unchanged "
    "from the captions. Auto-generated captions contain errors (especially names); "
    "verify quotations against the video."
)

TIMING_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)
TAG_RE = re.compile(r"<[^>]*>")


def parse_ts(ts: str) -> float:
    h, m, rest = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def fmt_ts(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", line))).strip()


def emitted_lines(vtt_text: str) -> list[tuple[float, str]]:
    """De-duplicated (start_seconds, line) stream from a YouTube rolling VTT.

    Each cue carries a two-line window: the previous line repeated and the
    newest line (with inline word timings). A line is emitted the first
    time it appears, stamped with that cue's start time.
    """
    emitted: list[tuple[float, str]] = []
    prev_lines: list[str] = []
    last_emitted: str | None = None
    for block in re.split(r"\n\s*\n", vtt_text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        timing_at = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_at is None:
            continue
        match = TIMING_RE.match(lines[timing_at].strip())
        if not match:
            continue
        start = parse_ts(match.group("start"))
        cleaned = [c for c in (clean_line(ln) for ln in lines[timing_at + 1 :]) if c]
        # The window rolls forward: the cue's leading lines repeat the tail
        # of the previous cue. Emit only the non-overlapping suffix. This
        # keeps genuinely repeated short lines (a cue can legitimately read
        # [">> Concur.", ">> Concur."] when two members concur in a row).
        overlap = 0
        for k in range(min(len(cleaned), len(prev_lines)), 0, -1):
            if cleaned[:k] == prev_lines[-k:]:
                overlap = k
                break
        for line in cleaned[overlap:]:
            emitted.append((start, line))
            last_emitted = line
        if cleaned:
            prev_lines = cleaned
    return emitted


def paragraphs(lines: list[tuple[float, str]], max_chars: int = 120) -> list[tuple[float, str]]:
    """Group emitted lines into paragraphs (existing files: median ~70,
    p90 ~190 characters per paragraph). A paragraph keeps the start time
    of its first line; lines are joined with a single space, wording intact.
    """
    paras: list[tuple[float, str]] = []
    current: list[str] = []
    current_start: float | None = None
    current_len = 0
    for start, line in lines:
        if current and current_len + 1 + len(line) > max_chars:
            paras.append((current_start, " ".join(current)))  # type: ignore[arg-type]
            current, current_start, current_len = [], None, 0
        if not current:
            current_start = start
        current.append(line)
        current_len += (1 if current_len else 0) + len(line)
    if current:
        paras.append((current_start, " ".join(current)))  # type: ignore[arg-type]
    return paras


def long_date(iso_date: str) -> str:
    parsed = datetime.date.fromisoformat(iso_date)
    return f"{parsed:%B} {parsed.day}, {parsed.year}"


def render_markdown(
    *,
    body: str,
    iso_date: str,
    youtube_id: str,
    captions_label: str,
    paras: list[tuple[float, str]],
    topic: str | None = None,
) -> str:
    display = BODIES[body][0]
    when = long_date(iso_date)
    title_suffix = f" ({topic})" if topic and body == "work-session" else ""
    header = "\n".join(
        [
            f"# {display} — {when}{title_suffix}",
            "",
            f"**Verbatim transcript** of the {display} meeting held {when} in Cheyenne, Wyoming.",
            "",
            f"- **Video:** [https://www.youtube.com/watch?v={youtube_id}]"
            f"(https://www.youtube.com/watch?v={youtube_id})",
            f"- **YouTube ID:** `{youtube_id}`",
            "- **Source:** City of Cheyenne official YouTube channel (@TheCityofCheyenne)",
            f"- **Captions:** {captions_label}",
            "",
            PROCESSING_NOTE,
            "",
            "---",
        ]
    )
    body_text = "\n\n".join(f"[{fmt_ts(start)}] {text}" for start, text in paras)
    return f"{header}\n{body_text}\n"


def convert_vtt(vtt_path: Path, **kwargs) -> str:
    lines = emitted_lines(vtt_path.read_text(encoding="utf-8"))
    if not lines:
        raise ValueError(f"no caption lines could be extracted from {vtt_path}")
    return render_markdown(paras=paragraphs(lines), **kwargs)


def target_file(entry: dict) -> str:
    """Catalog-relative Markdown path for an entry, e.g.
    planning-commission/2026-09-08-planning-commission-a.md"""
    if entry.get("expected_file"):
        return str(entry["expected_file"])
    body = entry["body"]
    _, directory, slug = BODIES[body]
    if slug is None:  # work-session: slug comes from the topic
        topic = entry.get("topic") or "work-session"
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return f"{directory}/{entry['date']}-{slug}.md"


def run_yt_dlp(args: list[str]) -> bool:
    cmd = ["yt-dlp", "--no-warnings", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-6:])
        print(f"  yt-dlp failed ({result.returncode}):\n{tail}", file=sys.stderr)
        return False
    return True


def download_captions(youtube_id: str) -> tuple[Path, str] | None:
    """Download English captions to raw/{id}.en.vtt.

    Returns (path, captions_label) or None. Manual (creator-provided)
    captions are tried before auto-generated ones so the header label
    can say which kind the transcript came from.
    """
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    out = str(RAW / f"{youtube_id}.%(ext)s")
    common = [
        "--skip-download",
        "--sub-format",
        "vtt",
        "--extractor-args",
        "youtube:player_client=android,tv,web",
        "-o",
        out,
        url,
    ]
    expected = RAW / f"{youtube_id}.en.vtt"
    attempts = [
        (["--write-subs", "--sub-langs", "en"], "English (creator-provided)"),
        (["--write-auto-subs", "--sub-langs", "en.*"], "English (auto-generated)"),
    ]
    for flags, label in attempts:
        if expected.exists():
            expected.unlink()
        if run_yt_dlp([*flags, *common]) and expected.is_file() and expected.stat().st_size > 0:
            return expected, label
        # yt-dlp may write e.g. {id}.en-US.vtt; normalize to {id}.en.vtt
        for candidate in sorted(RAW.glob(f"{youtube_id}.en*.vtt")):
            if candidate.stat().st_size > 0:
                candidate.replace(expected)
                return expected, label
    return None


def fetch_pending(only: set[str] | None, dry_run: bool) -> int:
    meetings = json.loads(CATALOG.read_text(encoding="utf-8"))
    pending = []
    for entry in meetings:
        if only and entry.get("youtube_id") not in only:
            continue
        current = entry.get("file")
        if current and (ARCHIVE / current).is_file():
            continue
        note = (entry.get("note") or "").lower()
        if "no captions" in note:
            print(f"skip {entry.get('date')} {entry.get('body')}: captions verified absent")
            continue
        if not entry.get("youtube_id"):
            print(f"skip {entry.get('date')} {entry.get('body')}: no youtube_id")
            continue
        pending.append(entry)

    print(f"{len(pending)} pending transcript(s)")
    failures: list[str] = []
    changed = False
    for entry in pending:
        youtube_id = entry["youtube_id"]
        label = f"{entry['date']} {entry['body']} ({youtube_id})"
        if dry_run:
            print(f"would fetch {label} -> {target_file(entry)}")
            continue
        print(f"fetching {label} ...", flush=True)
        got = download_captions(youtube_id)
        if not got:
            failures.append(label)
            print(f"  FAILED: no captions downloaded for {label}", file=sys.stderr)
            continue
        vtt_path, captions_label = got
        try:
            markdown = convert_vtt(
                vtt_path,
                body=entry["body"],
                iso_date=entry["date"],
                youtube_id=youtube_id,
                captions_label=captions_label,
                topic=entry.get("topic"),
            )
        except Exception as error:  # keep the VTT; report and move on
            failures.append(label)
            print(f"  FAILED to convert {label}: {error}", file=sys.stderr)
            continue
        rel = target_file(entry)
        dest = ARCHIVE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(markdown, encoding="utf-8")
        entry["file"] = rel
        changed = True
        print(f"  wrote {rel} ({len(markdown)} chars, {captions_label})")

    if changed and not dry_run:
        CATALOG.write_text(
            json.dumps(meetings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        print("updated meetings.json")
    if failures:
        print(f"\n{len(failures)} failure(s):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
    # Partial success still exits 0 so the workflow commits what landed;
    # total failure (nothing fetched) is a hard error.
    if pending and not dry_run and len(failures) == len(pending):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)

    conv = sub.add_parser("convert", help="Convert one VTT file to archive Markdown")
    conv.add_argument("vtt", type=Path)
    conv.add_argument("out", type=Path)
    conv.add_argument("--body", required=True, choices=sorted(BODIES))
    conv.add_argument("--date", required=True, help="YYYY-MM-DD")
    conv.add_argument("--youtube-id", required=True)
    conv.add_argument("--topic")
    conv.add_argument("--captions-label", default="English (auto-generated)")

    fetch = sub.add_parser("fetch", help="Download + convert all pending catalog entries")
    fetch.add_argument("--only", help="Comma-separated YouTube IDs to limit the run")
    fetch.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.mode == "convert":
        markdown = convert_vtt(
            args.vtt,
            body=args.body,
            iso_date=args.date,
            youtube_id=args.youtube_id,
            captions_label=args.captions_label,
            topic=args.topic,
        )
        args.out.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.out} ({len(markdown)} chars)")
        return 0
    only = {item.strip() for item in args.only.split(",")} if args.only else None
    return fetch_pending(only, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
