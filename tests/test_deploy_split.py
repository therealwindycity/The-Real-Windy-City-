"""Regression tests for the publish/crawl deployment split.

A slow city website must never block a static homepage fix, hung requests must
resolve to truthful error states, and the deployed artifact must actually
contain the evidence pages — not just the working tree.
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SPEC = importlib.util.spec_from_file_location('sync_city', ROOT / 'tools/sync_city.py')
sync_city = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_city)
CONFIG = json.loads((ROOT / 'city/mirror-config.json').read_text())


def workflow_jobs(text):
    """Split a workflow file into {job_name: job_text} by top-level job headers."""
    jobs = {}
    current = None
    for line in text.splitlines(keepends=True):
        header = re.match(r'^  ([A-Za-z0-9_-]+):\s*$', line)
        if header:
            current = header.group(1)
            jobs[current] = line
        elif current is not None:
            jobs[current] += line
    return jobs


class WorkflowSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / '.github/workflows/pages.yml').read_text()
        cls.jobs = workflow_jobs(cls.text)

    def test_publish_and_crawl_jobs_exist_and_old_build_is_gone(self):
        self.assertIn('publish', self.jobs)
        self.assertIn('crawl', self.jobs)
        self.assertIn('deploy', self.jobs)
        self.assertNotIn('build', self.jobs)

    def test_publish_job_performs_no_network_crawl(self):
        publish = self.jobs['publish']
        self.assertIn('--render-only', publish)
        for line in publish.splitlines():
            if 'tools/sync_city.py' in line:
                self.assertIn('--render-only', line, f'network crawl inside publish: {line.strip()}')

    def test_crawl_job_runs_the_network_sync(self):
        crawl = self.jobs['crawl']
        self.assertRegex(crawl, r'(?m)^\s*run: python3 tools/sync_city\.py\s*$')

    def test_crawl_job_never_runs_on_push(self):
        crawl = self.jobs['crawl']
        condition = re.search(r'^\s*if:\s*(.+)$', crawl, re.MULTILINE)
        self.assertIsNotNone(condition, 'crawl job needs an event guard')
        guard = condition.group(1)
        self.assertIn("github.event_name == 'schedule'", guard)
        self.assertIn("github.event_name == 'workflow_dispatch'", guard)
        self.assertNotIn('push', guard)

    def test_crawl_job_is_time_bounded(self):
        crawl = self.jobs['crawl']
        self.assertIn('timeout-minutes', crawl)
        step_bound = re.search(r'timeout-minutes:\s*(\d+)', crawl)
        self.assertIsNotNone(step_bound)
        self.assertLessEqual(int(step_bound.group(1)), 100)

    def test_deploy_waits_for_publish_only(self):
        deploy = self.jobs['deploy']
        needs = re.search(r'^\s*needs:\s*(.+)$', deploy, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertIn('publish', needs.group(1))
        self.assertNotIn('crawl', needs.group(1))

    def test_crawl_cannot_gate_publish_through_shared_concurrency(self):
        header = self.text.split('\njobs:')[0]
        self.assertNotIn('concurrency:', header, 'top-level concurrency would serialize crawl behind publish')
        self.assertIn('group: pages', self.jobs['publish'])
        self.assertIn('group: pages', self.jobs['deploy'])
        crawl_group = re.search(r'group:\s*(\S+)', self.jobs['crawl'])
        self.assertIsNotNone(crawl_group)
        self.assertNotEqual(crawl_group.group(1), 'pages')

    def test_publish_validates_evidence_artifact_before_upload(self):
        publish = self.jobs['publish']
        self.assertIn('tools/check_evidence_site.py --site site', publish)
        self.assertLess(publish.index('check_evidence_site.py'), publish.index('upload-pages-artifact'))

    def test_mirror_tests_cover_all_browser_scripts_and_no_stale_branch(self):
        text = (ROOT / '.github/workflows/city-mirror-tests.yml').read_text()
        self.assertNotIn('arena/', text)
        for script in ('city/city.js', 'city/mirror-search.js', 'city/portal.js', 'city/coverage.js'):
            self.assertIn(script, text)


class NoScriptFallbackTests(unittest.TestCase):
    def test_root_homepage_has_noscript_fallback(self):
        page = (ROOT / 'index.html').read_text()
        self.assertIn('<noscript>', page)
        self.assertIn('city/coverage.html', page)

    def test_city_homepage_freshness_has_noscript_fallback(self):
        page = (ROOT / 'city/index.html').read_text()
        self.assertIn('<noscript>', page)
        self.assertIn('freshness.json', page)

    def test_coverage_page_has_noscript_fallback(self):
        page = (ROOT / 'city/coverage.html').read_text()
        self.assertIn('<noscript>', page)
        self.assertIn('coverage.json', page)

    def test_every_loading_placeholder_ships_with_a_fallback(self):
        for name in ('index.html', 'city/index.html', 'city/coverage.html'):
            page = (ROOT / name).read_text()
            if 'Loading' in page:
                self.assertIn('<noscript>', page, f'{name} shows Loading with no no-JS fallback')


class FetchTimeoutTests(unittest.TestCase):
    SCRIPTS = ('city/city.js', 'city/portal.js', 'city/coverage.js', 'city/mirror-search.js')

    def test_browser_fetches_are_time_bounded(self):
        for name in self.SCRIPTS:
            with self.subTest(script=name):
                text = (ROOT / name).read_text()
                self.assertIn('AbortController', text)
                self.assertIn('fetchWithTimeout', text)
                # Exactly one raw fetch call: inside the timeout helper itself.
                self.assertEqual(text.count('fetch('), 1)


class CorruptSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_corrupt_state_is_quarantined_and_renders_empty_state(self):
        state_dir = self.root / 'state'
        state_dir.mkdir()
        (state_dir / 'state.json').write_text('{truncated garbage', encoding='utf-8')
        mirror = sync_city.Mirror(CONFIG, state_dir, self.root / 'out',
                                  transport=lambda url, headers: (404, {}, b''),
                                  sleep=lambda _: None)
        mirror.render()
        # Bad snapshot moved out of the cached directory; nothing invented.
        self.assertFalse((state_dir / 'state.json').exists())
        quarantine = state_dir.parent / 'city-mirror-quarantine'
        salvaged = list(quarantine.glob('state-*.json'))
        self.assertEqual(len(salvaged), 1)
        self.assertEqual(salvaged[0].read_text(), '{truncated garbage')
        self.assertEqual(mirror.records, {})
        status = json.loads((self.root / 'out/status.json').read_text())
        self.assertIn('state_recovery', status)
        self.assertIn('failed validation', status['state_recovery']['reason'])
        self.assertIn('No city content has been fetched yet', (self.root / 'out/index.html').read_text())

    def test_misshapen_state_is_quarantined(self):
        state_dir = self.root / 'state'
        state_dir.mkdir()
        (state_dir / 'state.json').write_text('{"records": []}', encoding='utf-8')
        mirror = sync_city.Mirror(CONFIG, state_dir, self.root / 'out',
                                  transport=lambda url, headers: (404, {}, b''),
                                  sleep=lambda _: None)
        self.assertEqual(mirror.records, {})
        self.assertIn('state_recovery', mirror.state)

    def test_valid_state_still_loads_without_quarantine(self):
        state_dir = self.root / 'state'
        state_dir.mkdir()
        (state_dir / 'state.json').write_text(
            json.dumps({'records': {}, 'changes': [],
                        'latest_run': {'status': 'completed'}}), encoding='utf-8')
        mirror = sync_city.Mirror(CONFIG, state_dir, self.root / 'out',
                                  transport=lambda url, headers: (404, {}, b''),
                                  sleep=lambda _: None)
        mirror.render()
        self.assertNotIn('state_recovery', mirror.state)
        self.assertFalse((state_dir.parent / 'city-mirror-quarantine').exists())


def minimal_site(root):
    """Build the smallest site tree the artifact checker accepts."""
    (root / 'city/mirror').mkdir(parents=True, exist_ok=True)
    (root / 'cheyenne-2026-transcripts/docs').mkdir(parents=True, exist_ok=True)
    (root / 'index.html').write_text(
        '<!doctype html><html><head><script src="city/portal.js" defer></script></head><body>'
        '<p>FRESHNESS · RECORD-BASED</p><p>Meeting information last checked</p>'
        '<a href="city/coverage.html">coverage</a><a href="city/corrections.html">corrections</a>'
        '</body></html>', encoding='utf-8')
    for name in ('city/index.html', 'city/corrections.html',
                 'city/citizen-connect-methodology.html',
                 'city/data-center-amendment-2026-10-19.html',
                 'city/mirror/index.html', 'city/mirror/status.html'):
        (root / name).write_text('<!doctype html><html><body><a href="../">home</a></body></html>', encoding='utf-8')
    (root / 'city/coverage.html').write_text(
        '<!doctype html><html><body><p>only that audited local set</p>'
        '<p>does not claim an overall OCR-pending count</p></body></html>', encoding='utf-8')
    for name in ('robots.txt', 'sitemap.xml', 'city/city.css', 'city/city.js',
                 'city/portal.js', 'city/coverage.js', 'city/mirror-search.js'):
        (root / name).write_text('ok', encoding='utf-8')
    (root / 'city/freshness.json').write_text(json.dumps({
        'meeting_information_last_checked': None,
        'latest_meeting_indexed': '2026-09-22',
        'latest_verified_outcome': None,
        'known_gaps': ['gap one'],
    }), encoding='utf-8')
    (root / 'city/coverage.json').write_text(json.dumps({
        'scope': 'excludes external archive repositories',
        'metrics': {'meetings_indexed': 1, 'image_review_or_ocr_pending': None},
    }), encoding='utf-8')
    (root / 'city/mirror/status.json').write_text(json.dumps({'latest_run': {'status': 'completed'}}), encoding='utf-8')
    (root / 'city/mirror/catalog.json').write_text('[]', encoding='utf-8')
    (root / 'cheyenne-2026-transcripts/meetings.json').write_text(json.dumps([
        {'body': 'city-council', 'date': '2026-09-22', 'file': 'docs/one.md', 'youtube_id': 'x'}]), encoding='utf-8')
    (root / 'cheyenne-2026-transcripts/docs/one.md').write_text('transcript', encoding='utf-8')
    return root


class EvidenceArtifactCheckerTests(unittest.TestCase):
    def run_checker(self, site):
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'tools/check_evidence_site.py'), '--site', str(site)],
            capture_output=True, text=True, timeout=60)
        return proc

    def test_checker_accepts_minimal_valid_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_checker(minimal_site(Path(tmp)))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_checker_rejects_missing_evidence_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = minimal_site(Path(tmp))
            (site / 'city/coverage.html').unlink()
            proc = self.run_checker(site)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('city/coverage.html', proc.stdout)

    def test_checker_rejects_build_time_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = minimal_site(Path(tmp))
            freshness = json.loads((site / 'city/freshness.json').read_text())
            freshness['meeting_information_last_checked'] = '2026-10-21T13:00:00+00:00'
            (site / 'city/freshness.json').write_text(json.dumps(freshness))
            proc = self.run_checker(site)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('meeting_information_last_checked', proc.stdout)

    def test_checker_rejects_broken_internal_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = minimal_site(Path(tmp))
            (site / 'city/corrections.html').write_text(
                '<!doctype html><html><body><a href="no-such-page.html">broken</a></body></html>')
            proc = self.run_checker(site)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('broken internal link', proc.stdout)

    def test_checker_rejects_missing_catalog_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = minimal_site(Path(tmp))
            (site / 'cheyenne-2026-transcripts/docs/one.md').unlink()
            proc = self.run_checker(site)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('missing from artifact', proc.stdout)


class ScopePreservationTests(unittest.TestCase):
    def test_audit_scope_stays_limited(self):
        page = (ROOT / 'city/coverage.html').read_text()
        self.assertIn('only that audited local set', page)
        self.assertIn('does not claim an overall OCR-pending count', page)
        coverage = json.loads((ROOT / 'city/coverage.json').read_text())
        self.assertIsNone(coverage['metrics']['image_review_or_ocr_pending'])


if __name__ == '__main__':
    unittest.main()
