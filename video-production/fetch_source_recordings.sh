#!/usr/bin/env bash
# fetch_source_recordings.sh — Phase 6 source acquisition kit
# The Real Windy City / Cheyenne 2026 video-evidence project
#
# Downloads the official public meeting recordings listed in
# source_acquisition_manifest.json into ./source-masters/ with per-file
# SHA-256 checksums, a retrieval log, and (for YouTube) the video's
# info-json and English caption tracks for verification.
#
# Requirements: bash, python3, curl, sha256sum, and yt-dlp
# (https://github.com/yt-dlp/yt-dlp — `pip install yt-dlp` or brew).
# Run this on ANY machine with normal internet egress, then hand the
# source-masters/ folder back to the production environment (see README).
#
# Public recordings only. No cookies, no accounts, no credentials.
#
# Usage:
#   ./fetch_source_recordings.sh                 # tier 1 only (7 recordings)
#   ./fetch_source_recordings.sh --tier 2        # tier 1 + tier 2
#   ./fetch_source_recordings.sh --tier all      # everything (86 rows incl. 5 no-need)
#   ./fetch_source_recordings.sh --only 2026-06-22
#   ./fetch_source_recordings.sh --verify        # probe + report on what's downloaded
set -uo pipefail

TIER=1
ONLY=""
OUT="$(dirname "$0")/source-masters"
while [ $# -gt 0 ]; do
  case "$1" in
    --tier)  TIER="$2"; shift 2 ;;
    --only)  ONLY="$2"; shift 2 ;;
    --out)   OUT="$2"; shift 2 ;;
    --verify) VERIFY=1; shift ;;
    *) echo "unknown arg: $1 (use --tier 1|2|3|all, --only DATE, --out DIR, --verify)"; exit 2 ;;
  esac
done
VERIFY="${VERIFY:-0}"
mkdir -p "$OUT"
MANIFEST="$(dirname "$0")/source_acquisition_manifest.json"
LOG="$OUT/retrieval_log.jsonl"
[ -f "$LOG" ] || : > "$LOG"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1"; exit 3; }; }
need python3; need curl; need sha256sum
have_ytdlp=0; command -v yt-dlp >/dev/null 2>&1 && have_ytdlp=1

# Select rows: date, youtube_id, granicus_mp4_url, tier, body
rows() {
  python3 - "$MANIFEST" "$TIER" "$ONLY" << 'PYEOF'
import json, sys
manifest = json.load(open(sys.argv[1]))
tier, only = sys.argv[2], sys.argv[3]
for r in manifest["recordings"]:
    if only and r["date"] != only: continue
    if not only:
        t = r.get("tier")
        if tier == "all": pass
        elif t is None or (tier != "all" and int(tier) < t): continue
    print("\t".join(str(r.get(k) or "") for k in ("date","body","youtube_id","granicus_mp4_url","source_url","tier")))
PYEOF
}

log_entry() { # date body file url sha256 size bytes_ms
  python3 - "$LOG" "$@" << 'PYEOF'
import json, sys, datetime
date, body, file, url, sha, size = sys.argv[2:8]
entry = {"retrieved_utc": datetime.datetime.utcnow().isoformat()+"Z",
         "date": date, "body": body, "file": file, "source_url": url,
         "sha256": sha, "bytes": int(size) if size else None,
         "tool": "fetch_source_recordings.sh"}
open(sys.argv[1], "a").write(json.dumps(entry, sort_keys=True) + "\n")
PYEOF
}

if [ "$VERIFY" = "1" ]; then
  echo "== verifying $OUT =="
  ( cd "$OUT" && sha256sum -c SHA256SUMS 2>/dev/null || echo "(no SHA256SUMS yet)" )
  for f in "$OUT"/*.mp4; do
    [ -f "$f" ] || continue
    if command -v ffprobe >/dev/null 2>&1; then
      d=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f" 2>/dev/null)
      echo "$(basename "$f")  ${d:-?}s"
    else
      echo "$(basename "$f")  $(stat -c%s "$f") bytes (ffprobe not installed)"
    fi
  done
  exit 0
fi

[ "$have_ytdlp" = "1" ] || echo "NOTE: yt-dlp not found — YouTube rows will be skipped (direct MP4 rows still work)."

n=0
while IFS=$'\t' read -r date body ytid mp4 srcurl tier; do
  [ -n "$date" ] || continue
  name="${date}-${body}"
  dest="$OUT/${name}.mp4"
  echo "----------------------------------------------------------------"
  echo "[$date $body] tier=${tier:-?}"
  if [ -f "$dest" ]; then echo "  already present: $dest (skip)"; continue; fi

  # Route 1: direct Granicus MP4 (no yt-dlp needed)
  if [ -n "$mp4" ]; then
    echo "  direct MP4: $mp4"
    if curl -fL --retry 3 -C - -o "$dest" "$mp4"; then
      sha=$(sha256sum "$dest" | awk '{print $1}'); sz=$(stat -c%s "$dest")
      log_entry "$date" "$body" "$dest" "$mp4" "$sha" "$sz"
      echo "$sha  ${name}.mp4" >> "$OUT/SHA256SUMS"
      n=$((n+1)); continue
    fi
    echo "  direct MP4 failed; falling back to YouTube"
    rm -f "$dest"
  fi

  # Route 2: official YouTube via yt-dlp (public, no cookies)
  if [ -n "$ytid" ]; then
    [ "$have_ytdlp" = "1" ] || { echo "  SKIP (no yt-dlp): https://www.youtube.com/watch?v=$ytid"; continue; }
    echo "  youtube: https://www.youtube.com/watch?v=$ytid"
    # best <=1080p H.264/AAC mp4 without re-encode; also save info json +
    # english (auto) caption tracks for the verification layer.
    if yt-dlp --no-cookies --no-playlist \
        -f "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/bv*[height<=1080]+ba/b" \
        --merge-output-format mp4 \
        --write-info-json --write-subs --write-auto-subs --sub-langs "en.*" --sub-format "vtt" \
        -o "$dest" "https://www.youtube.com/watch?v=$ytid"; then
      sha=$(sha256sum "$dest" | awk '{print $1}'); sz=$(stat -c%s "$dest")
      log_entry "$date" "$body" "$dest" "https://www.youtube.com/watch?v=$ytid" "$sha" "$sz"
      echo "$sha  ${name}.mp4" >> "$OUT/SHA256SUMS"
      n=$((n+1))
    else
      echo "  FAILED: https://www.youtube.com/watch?v=$ytid"
    fi
    continue
  fi

  # Route 3: Granicus player page (Sept 28) — try yt-dlp generic, else manual
  echo "  no YouTube ID and no direct MP4 in manifest."
  echo "  try:        yt-dlp '$srcurl'"
  echo "  else open the player page and capture the stream/archived mp4 manually:"
  echo "              $srcurl"
  echo "  save as:    $dest"
  if [ "$have_ytdlp" = "1" ]; then
    yt-dlp --no-cookies -o "$dest" "$srcurl" && { sha=$(sha256sum "$dest" | awk '{print $1}'); sz=$(stat -c%s "$dest"); log_entry "$date" "$body" "$dest" "$srcurl" "$sha" "$sz"; echo "$sha  ${name}.mp4" >> "$OUT/SHA256SUMS"; n=$((n+1)); } || rm -f "$dest"
  fi
done < <(rows)

echo "----------------------------------------------------------------"
echo "done: $n new recording(s) in $OUT"
echo "log:  $LOG"
echo "checksums: $OUT/SHA256SUMS"
echo "next: run with --verify to probe the files, then hand source-masters/ back"
echo "       to the production environment (see video-production/README.md)."
