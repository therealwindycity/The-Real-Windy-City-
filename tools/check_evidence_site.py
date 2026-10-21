#!/usr/bin/env python3
"""Validate the assembled static-site artifact before it is uploaded to Pages.

All checks are offline and standard-library only. They confirm that the
evidence-first homepage, coverage pages, freshness semantics, and every newly
added internal link are actually present in the directory that will be
deployed — not merely present in the working tree.

Usage:
    python3 tools/check_evidence_site.py --site site
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse as urlparse
from html.parser import HTMLParser
from pathlib import Path

REQUIRED_FILES = [
    'index.html',
    'robots.txt',
    'sitemap.xml',
    'city/index.html',
    'city/coverage.html',
    'city/corrections.html',
    'city/citizen-connect-methodology.html',
    'city/data-center-amendment-2026-10-19.html',
    'city/freshness.json',
    'city/coverage.json',
    'city/city.css',
    'city/city.js',
    'city/portal.js',
    'city/coverage.js',
    'city/mirror-search.js',
    'city/mirror/index.html',
    'city/mirror/status.html',
    'city/mirror/status.json',
    'cheyenne-2026-transcripts/meetings.json',
]

# Markers proving the deployed root page is the evidence-first homepage, not
# an older minimal revision.
HOMEPAGE_MARKERS = [
    'FRESHNESS · RECORD-BASED',
    'Meeting information last checked',
    'city/coverage.html',
    'city/corrections.html',
    'portal.js',
]

# Runtime fetch targets used by the browser scripts (page-relative). These are
# not visible as href/src attributes, so they are asserted explicitly.
RUNTIME_FETCHES = {
    'index.html': ['city/freshness.json'],
    'city/index.html': ['freshness.json', '../cheyenne-2026-transcripts/meetings.json'],
    'city/coverage.html': ['freshness.json', 'coverage.json'],
    'city/mirror/index.html': ['catalog.json'],
}

# The limited-scope audit sentence that must never be broadened into a
# repository-wide OCR claim.
AUDIT_SCOPE_SENTENCE = 'only that audited local set'

# Record-based freshness fields that must be present in static HTML. A JS-only
# "Loading…" placeholder is not a truthful no-JS / crawler fallback.
FRESHNESS_ELEMENT_IDS = {
    'index.html': ('portal-checked', 'portal-indexed', 'portal-outcome', 'portal-gaps'),
    'city/index.html': ('home-checked', 'home-indexed', 'home-outcome', 'home-gaps'),
    'city/coverage.html': ('checked-at', 'latest-indexed', 'latest-outcome', 'known-gaps', 'metrics'),
}


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.targets = []

    def handle_starttag(self, tag, attrs):
        attr = {'a': 'href', 'link': 'href', 'script': 'src', 'img': 'src'}.get(tag)
        if attr:
            for name, value in attrs:
                if name == attr and value:
                    self.targets.append(value)


def is_external_or_fragment(target):
    if not target or target.startswith(('#', 'mailto:', 'tel:', 'javascript:', 'data:')):
        return True
    parsed = urlparse.urlsplit(target)
    return bool(parsed.scheme or parsed.netloc)


def resolve(page, target, site):
    """Resolve a page-relative link to a file inside site/, or None."""
    clean = urlparse.urlsplit(target)._replace(query='', fragment='').geturl()
    if not clean:
        return None
    candidate = (page.parent / urlparse.unquote(clean)).resolve()
    try:
        candidate.relative_to(site.resolve())
    except ValueError:
        return None
    if candidate.is_dir():
        candidate = candidate / 'index.html'
    return candidate


def check_file(path, problems, label=None):
    label = label or str(path)
    if not path.is_file():
        problems.append(f'missing required file: {label}')
        return None
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as error:
        problems.append(f'unreadable file {label}: {error}')
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', default='site', help='Assembled site directory to validate')
    args = parser.parse_args()
    site = Path(args.site)
    problems = []

    if not site.is_dir():
        print(f'site directory not found: {site}', file=sys.stderr)
        return 1

    for name in REQUIRED_FILES:
        check_file(site / name, problems, label=name)

    homepage = (site / 'index.html').read_text(encoding='utf-8') if (site / 'index.html').is_file() else ''
    for marker in HOMEPAGE_MARKERS:
        if marker not in homepage:
            problems.append(f'evidence-first homepage marker missing from index.html: {marker!r}')

    catalog = []
    meetings_path = site / 'cheyenne-2026-transcripts/meetings.json'
    if meetings_path.is_file():
        try:
            catalog = json.loads(meetings_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            problems.append(f'meetings.json does not parse: {error}')

    freshness_path = site / 'city/freshness.json'
    if freshness_path.is_file():
        try:
            freshness = json.loads(freshness_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            problems.append(f'city/freshness.json does not parse: {error}')
        else:
            # Build/assembly must never substitute its own timestamp for a
            # collection check or invent a verified outcome.
            if freshness.get('meeting_information_last_checked') is not None:
                problems.append('freshness.json: meeting_information_last_checked must stay null until a real collection check is recorded')
            if freshness.get('latest_verified_outcome') is not None:
                problems.append('freshness.json: latest_verified_outcome must stay null until a verified outcome is recorded')
            dated = [m.get('date') for m in catalog if isinstance(m, dict) and isinstance(m.get('date'), str) and len(m.get('date')) == 10]
            expected_latest = max(dated) if dated else None
            if freshness.get('latest_meeting_indexed') != expected_latest:
                problems.append(
                    f"freshness.json: latest_meeting_indexed is {freshness.get('latest_meeting_indexed')!r}, "
                    f'catalog maximum is {expected_latest!r}')
            if not freshness.get('known_gaps'):
                problems.append('freshness.json: known_gaps must be a non-empty list')

    coverage_path = site / 'city/coverage.json'
    if coverage_path.is_file():
        try:
            coverage = json.loads(coverage_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            problems.append(f'city/coverage.json does not parse: {error}')
        else:
            if 'excludes external archive repositories' not in str(coverage.get('scope', '')):
                problems.append('coverage.json: scope must keep excluding external archive repositories')
            metrics = coverage.get('metrics', {})
            if metrics.get('meetings_indexed') != len(catalog):
                problems.append('coverage.json: meetings_indexed does not match the catalog length')
            if metrics.get('image_review_or_ocr_pending') is not None:
                problems.append('coverage.json: image_review_or_ocr_pending must stay unmeasured (null)')

    coverage_html_path = site / 'city/coverage.html'
    if coverage_html_path.is_file():
        coverage_html = coverage_html_path.read_text(encoding='utf-8')
        if AUDIT_SCOPE_SENTENCE not in coverage_html:
            problems.append('city/coverage.html: limited-scope audit wording is missing or was broadened')
        if 'does not claim an overall OCR-pending count' not in coverage_html:
            problems.append('city/coverage.html: OCR-pending disclaimer is missing')

    # Static HTML must already contain record-based freshness, not "Loading…".
    latest = None
    if freshness_path.is_file():
        try:
            latest = json.loads(freshness_path.read_text(encoding='utf-8')).get('latest_meeting_indexed')
        except (ValueError, OSError):
            latest = None
    for page_name, element_ids in FRESHNESS_ELEMENT_IDS.items():
        page_path = site / page_name
        if not page_path.is_file():
            continue
        page = page_path.read_text(encoding='utf-8')
        for element_id in element_ids:
            match = re.search(
                rf'<(?:dd|p|span|ul|tbody)\b[^>]*\sid="{re.escape(element_id)}"[^>]*>(.*?)</(?:dd|p|span|ul|tbody)>',
                page,
                flags=re.S,
            )
            if not match:
                problems.append(f'{page_name}: missing static freshness element id={element_id!r}')
                continue
            inner = match.group(1)
            if re.search(r'Loading(?:…|\.\.\.| from )', inner, flags=re.I):
                problems.append(f'{page_name}: #{element_id} still contains a Loading placeholder in static HTML')
        if latest and latest not in page and page_name != 'city/coverage.html':
            # Coverage page states the date in latest-indexed; the other two must too.
            problems.append(f'{page_name}: static HTML does not include catalog latest {latest!r}')
        elif latest and page_name == 'city/coverage.html' and latest not in page:
            problems.append(f'{page_name}: static HTML does not include catalog latest {latest!r}')

    # Every catalog transcript referenced by the reader must be deployed.
    archive = site / 'cheyenne-2026-transcripts'
    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        name = entry.get('file')
        if name and not (archive / name).is_file():
            problems.append(f'catalog transcript missing from artifact: cheyenne-2026-transcripts/{name}')

    # Every internal link in the evidence pages and rendered mirror pages.
    pages = [site / 'index.html', *sorted((site / 'city').glob('*.html')),
             *sorted((site / 'city' / 'mirror').glob('*.html'))]
    for page in pages:
        if not page.is_file():
            continue
        collector = LinkCollector()
        try:
            collector.feed(page.read_text(encoding='utf-8'))
        except Exception as error:  # noqa: BLE001 - report, don't crash
            problems.append(f'{page.relative_to(site)}: HTML parse failed: {error}')
            continue
        for target in collector.targets:
            if is_external_or_fragment(target):
                continue
            resolved = resolve(page, target, site)
            if resolved is None or not resolved.is_file():
                problems.append(f'{page.relative_to(site)}: broken internal link: {target}')

    for page_name, targets in RUNTIME_FETCHES.items():
        page = site / page_name
        for target in targets:
            resolved = resolve(page, target, site)
            if resolved is None or not resolved.is_file():
                problems.append(f'{page_name}: runtime fetch target missing from artifact: {target}')

    # The mirror render always writes catalog.json alongside the pages.
    if (site / 'city/mirror/index.html').is_file() and not (site / 'city/mirror/catalog.json').is_file():
        problems.append('city/mirror/catalog.json missing from artifact')

    if problems:
        print(f'{len(problems)} artifact problem(s) in {site}:')
        for problem in problems:
            print(f'  - {problem}')
        return 1
    print(f'evidence artifact OK: {site} '
          f'({len(REQUIRED_FILES)} required files, {len(catalog)} catalog entries, internal links resolve)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
