#!/usr/bin/env python3
"""Generate reproducible coverage counts for the checked-in 2026 transcript catalog.

This deliberately does not treat CI/build time as a collection timestamp and does
not claim coverage of external archive repositories or PDF attachments.

After writing coverage.json / freshness.json, the same values are copied into the
static HTML so crawlers and no-JS browsers never see a "Loading…" placeholder for
record-based freshness. JavaScript remains a progressive enhancement.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "cheyenne-2026-transcripts"
CATALOG = ARCHIVE / "meetings.json"
OUTPUT = ROOT / "city" / "coverage.json"
FRESHNESS = ROOT / "city" / "freshness.json"

METRIC_LABELS = {
    "meetings_indexed": "Meetings indexed",
    "unique_document_contents": "Unique document contents",
    "stored_markdown_files": "Stored Markdown files",
    "searchable_catalog_documents": "Searchable catalog documents",
    "caption_transcripts": "Caption transcripts",
    "auto_generated_caption_transcripts": "Auto-generated caption transcripts",
    "other_or_unlabeled_caption_sources": "Other / unlabeled caption sources",
    "catalog_entries_without_transcript_file": "Catalog entries without transcript file",
    "audio_checked_excerpts": "Audio-checked excerpts",
    "original_source_checks": "Original-source checks",
    "image_review_or_ocr_pending": "Image-review / OCR pending",
}

METRIC_DEFINITIONS_FALLBACK = {
    "meetings_indexed": "Meeting entries in the JSON catalog; not necessarily unique dates or complete meetings.",
    "catalog_entries_without_transcript_file": "Catalog entries without a corresponding transcript Markdown file.",
}


def set_inner_by_id(page: str, element_id: str, inner: str, tags: tuple[str, ...] = ("dd", "p", "span")) -> str:
    tag_alt = "|".join(tags)
    pattern = rf'(<(?:{tag_alt})\b[^>]*\sid="{re.escape(element_id)}"[^>]*>)(.*?)(</(?:{tag_alt})>)'
    updated, count = re.subn(pattern, lambda match: match.group(1) + inner + match.group(3), page, count=1, flags=re.S)
    if count != 1:
        raise ValueError(f'expected exactly one element id="{element_id}", found {count}')
    return updated


def set_ul_by_id(page: str, element_id: str, items: list[str]) -> str:
    inner = "".join(f"<li>{html.escape(item)}</li>" for item in items) or "<li>See coverage page</li>"
    pattern = rf'(<ul\b[^>]*\sid="{re.escape(element_id)}"[^>]*>)(.*?)(</ul>)'
    updated, count = re.subn(pattern, lambda match: match.group(1) + inner + match.group(3), page, count=1, flags=re.S)
    if count != 1:
        raise ValueError(f'expected exactly one ul id="{element_id}", found {count}')
    return updated


def set_tbody_by_id(page: str, element_id: str, inner: str) -> str:
    pattern = rf'(<tbody\b[^>]*\sid="{re.escape(element_id)}"[^>]*>)(.*?)(</tbody>)'
    updated, count = re.subn(pattern, lambda match: match.group(1) + inner + match.group(3), page, count=1, flags=re.S)
    if count != 1:
        raise ValueError(f'expected exactly one tbody id="{element_id}", found {count}')
    return updated


def checked_label(value) -> str:
    return "Not recorded" if not value else str(value)


def indexed_label(value, *, catalog_note: bool = True) -> str:
    if not value:
        return "Not recorded"
    return f"{value} (catalog maximum)" if catalog_note else f"{value} — catalog maximum; not a completeness claim."


def outcome_label(value) -> str:
    return value or "None documented as verified"


def gaps_sentence(gaps: list[str]) -> str:
    if not gaps:
        return "See coverage page"
    return f"{len(gaps)} known gaps — {gaps[0]}"


def embed_freshness(freshness: dict, coverage: dict) -> None:
    gaps = list(freshness.get("known_gaps") or [])
    checked = html.escape(checked_label(freshness.get("meeting_information_last_checked")))
    indexed_short = html.escape(indexed_label(freshness.get("latest_meeting_indexed"), catalog_note=True))
    indexed_long = html.escape(indexed_label(freshness.get("latest_meeting_indexed"), catalog_note=False))
    outcome = html.escape(outcome_label(freshness.get("latest_verified_outcome")))
    gaps_short = html.escape(gaps_sentence(gaps))

    homepage = (ROOT / "index.html").read_text(encoding="utf-8")
    homepage = set_inner_by_id(homepage, "portal-checked", checked)
    homepage = set_inner_by_id(homepage, "portal-indexed", indexed_short)
    homepage = set_inner_by_id(homepage, "portal-outcome", outcome)
    homepage = set_inner_by_id(homepage, "portal-gaps", gaps_short)
    (ROOT / "index.html").write_text(homepage, encoding="utf-8")

    city_home = (ROOT / "city" / "index.html").read_text(encoding="utf-8")
    city_home = set_inner_by_id(city_home, "home-checked", checked)
    city_home = set_inner_by_id(city_home, "home-indexed", indexed_short)
    city_home = set_inner_by_id(city_home, "home-outcome", outcome)
    city_home = set_inner_by_id(city_home, "home-gaps", html.escape(f"{len(gaps)} known gaps · {gaps[0]}" if gaps else "See coverage page"))
    (ROOT / "city" / "index.html").write_text(city_home, encoding="utf-8")

    rules = coverage.get("rules") or {}
    rows = []
    for key, value in (coverage.get("metrics") or {}).items():
        label = METRIC_LABELS.get(key, key)
        display = "Not measured" if value is None else str(value)
        definition = rules.get(key) or METRIC_DEFINITIONS_FALLBACK.get(key, "See coverage index.")
        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{html.escape(display)}</td>"
            f"<td>{html.escape(definition)}</td>"
            "</tr>"
        )

    coverage_html = (ROOT / "city" / "coverage.html").read_text(encoding="utf-8")
    coverage_html = set_inner_by_id(coverage_html, "checked-at", checked)
    coverage_html = set_inner_by_id(coverage_html, "latest-indexed", indexed_long)
    coverage_html = set_inner_by_id(coverage_html, "latest-outcome", outcome)
    coverage_html = set_ul_by_id(coverage_html, "known-gaps", gaps)
    coverage_html = set_tbody_by_id(coverage_html, "metrics", "".join(rows) or "<tr><td colspan=\"3\">Coverage data unavailable.</td></tr>")
    coverage_html = set_inner_by_id(coverage_html, "scope", html.escape(coverage.get("scope") or ""), tags=("p",))
    coverage_html = set_inner_by_id(coverage_html, "count-note", html.escape(coverage.get("verification_note") or ""), tags=("p",))
    (ROOT / "city" / "coverage.html").write_text(coverage_html, encoding="utf-8")


def main() -> None:
    meetings = json.loads(CATALOG.read_text(encoding="utf-8"))
    files = sorted(ARCHIVE.glob("**/*.md"))
    hashes = {p.relative_to(ARCHIVE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    catalog_files = {m["file"] for m in meetings if m.get("file") and m["file"] in hashes}
    searchable = {
        name for name in catalog_files
        if (ARCHIVE / name).read_text(encoding="utf-8").strip()
    }
    unique_content = {hashes[name] for name in catalog_files}
    caption_sources = {}
    for name in searchable:
        text = (ARCHIVE / name).read_text(encoding="utf-8")
        match = re.search(r"^- \*\*Captions:\*\*\s*(.+)$", text, re.MULTILINE)
        caption_sources[name] = match.group(1).strip() if match else "source label not recorded"
    auto_caption_count = sum("auto-generated" in source.lower() for source in caption_sources.values())
    other_caption_count = len(caption_sources) - auto_caption_count
    dated_meetings = [m["date"] for m in meetings if isinstance(m.get("date"), str) and len(m["date"]) == 10]
    freshness = json.loads(FRESHNESS.read_text(encoding="utf-8"))
    freshness["latest_meeting_indexed"] = max(dated_meetings) if dated_meetings else None
    freshness["latest_meeting_indexed_basis"] = "Maximum full meeting date in cheyenne-2026-transcripts/meetings.json; generated by this script. It is not a claim that all meetings through this date are indexed."
    FRESHNESS.write_text(json.dumps(freshness, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    data = {
        "scope": "Checked-in cheyenne-2026-transcripts catalog and Markdown files only; excludes external archive repositories and uncollected city records.",
        "generated_by": "python3 tools/build_archive_coverage.py",
        "metrics": {
            "meetings_indexed": len(meetings),
            "unique_document_contents": len(unique_content),
            "stored_markdown_files": len(files),
            "searchable_catalog_documents": len(searchable),
            "caption_transcripts": len(searchable),
            "auto_generated_caption_transcripts": auto_caption_count,
            "other_or_unlabeled_caption_sources": other_caption_count,
            "catalog_entries_without_transcript_file": sum(1 for m in meetings if not m.get("file") or m.get("file") not in hashes),
            "audio_checked_excerpts": 0,
            "original_source_checks": 0,
            "image_review_or_ocr_pending": None,
        },
        "rules": {
            "unique_document_contents": "Distinct SHA-256 hashes among transcript files referenced by catalog entries; identical content counts once.",
            "stored_markdown_files": "Every Markdown file under cheyenne-2026-transcripts, including unreferenced variants; this is not a count of all stored files or attachments.",
            "searchable_catalog_documents": "Referenced Markdown files with non-empty extracted text. This does not establish that an associated PDF or source is searchable.",
            "caption_transcripts": "Searchable transcript files in this archive. Transcript is not minutes.",
            "auto_generated_caption_transcripts": "Catalogued searchable transcripts whose Markdown source header explicitly labels the captions auto-generated.",
            "other_or_unlabeled_caption_sources": "Caption transcripts whose header does not explicitly say auto-generated; this does not prove captions were human-created.",
            "audio_checked_excerpts": "Zero recorded excerpt-level audio checks in this repository's current verification register; absence of a check record is not proof no one listened.",
            "original_source_checks": "Zero documented comparisons against original publisher files in the current verification register.",
            "image_review_or_ocr_pending": "Not measured: this repository's checked-in 2026 transcript catalog does not include a complete inventory of PDF page images or a linked page-level extraction audit queue.",
        },
        "verification_note": "A successful site build or deployment is not evidence that new government records were collected or verified.",
    }
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    embed_freshness(freshness, data)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(meetings)} catalog entries, {len(files)} Markdown files")
    print("Embedded freshness into index.html, city/index.html, and city/coverage.html")


if __name__ == "__main__":
    main()
