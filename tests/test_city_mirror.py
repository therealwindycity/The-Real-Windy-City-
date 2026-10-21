import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('sync_city', Path(__file__).parents[1] / 'tools/sync_city.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
ORIGIN = 'https://www.cheyennecity.org'
CONFIG = json.loads((Path(__file__).parents[1] / 'city/mirror-config.json').read_text())


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.routes = {
            '/robots.txt': (200, {}, b'User-agent: *\nDisallow: /secret\nSitemap: https://www.cheyennecity.org/sitemap.xml'),
            '/sitemap.xml': (200, {}, b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://www.cheyennecity.org/news</loc></url></urlset>'),
            '/': (200, {'content-type': 'text/html', 'etag': 'one'}, b'<title>City Home</title><h1>Welcome</h1><script>evil()</script><form>Private fields</form><a href="/news">News</a><a href="/packet.pdf">Packet</a><a href="/secret">Secret</a><a href="https://outside.example/">External</a>'),
            '/news': (200, {'content-type': 'text/html'}, b'<title>News &amp; notices</title><p>Public text &lt;script&gt;.</p><a href="/">Home</a>'),
            '/packet.pdf': (200, {'content-type': 'application/pdf'}, b'%PDF-1.7\nfixture'),
        }

    def transport(self, url, headers):
        self.calls.append((url, headers))
        return self.routes.get(url.removeprefix(ORIGIN), (404, {}, b'not found'))

    def mirror(self, **overrides):
        return module.Mirror({**CONFIG, **overrides}, self.root / 'state', self.root / 'out', self.transport, sleep=lambda _: None)

    def test_crawl_render_and_scope(self):
        mirror = self.mirror()
        report = mirror.run()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(len(mirror.records), 3)
        self.assertEqual(report['blocked'], 1)
        self.assertFalse(any('/secret' in url or 'outside.example' in url for url, _ in self.calls))
        page = (self.root / 'out' / mirror.records[ORIGIN + '/']['path']).read_text()
        self.assertNotIn('evil()', page)
        self.assertNotIn('Private fields', page)
        self.assertIn('../pages/' + module.key(ORIGIN + '/news'), page)
        self.assertIn('INDEPENDENT ARCHIVE', page)
        news = (self.root / 'out' / mirror.records[ORIGIN + '/news']['path']).read_text()
        self.assertIn('&lt;script&gt;', news)
        self.assertTrue((self.root / 'out/documents' / (module.key(ORIGIN + '/packet.pdf') + '.pdf')).exists())

    def test_conditional_refresh_and_change_log(self):
        first = self.mirror(); first.run()
        self.routes['/'] = (304, {}, b'')
        self.routes['/news'] = (200, {'content-type': 'text/html'}, b'<title>Updated</title><p>Revised</p>')
        second = self.mirror(); second.run()
        self.assertTrue(any(headers.get('If-None-Match') == 'one' for _, headers in self.calls))
        self.assertEqual(second.records[ORIGIN + '/']['source_status'], 304)
        self.assertEqual(len(second.state['changes']), 4)
        self.assertIsNotNone(second.state['changes'][-1]['before'])

    def test_robots_failure_retains_previous_pages(self):
        first = self.mirror(); first.run()
        self.calls.clear()
        self.routes['/robots.txt'] = (403, {}, b'blocked')
        second = self.mirror(); report = second.run()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(second.records), 3)
        self.assertIn('failed', (self.root / 'out/status.html').read_text())

    def test_external_redirect_not_followed(self):
        self.routes['/news'] = (302, {'location': 'https://outside.example/private'}, b'')
        mirror = self.mirror(); report = mirror.run()
        self.assertEqual(report['status'], 'partial')
        self.assertFalse(any('outside.example' in url for url, _ in self.calls))

    def test_budget_and_resume(self):
        mirror = self.mirror(max_pages_per_run=1); report = mirror.run()
        self.assertEqual(report['status'], 'partial')
        self.assertGreater(report['pending'], 0)
        second = self.mirror(); second.run()
        self.assertEqual(len(second.records), 3)

    def test_disappeared_source_retained_and_labeled(self):
        self.mirror().run()
        self.routes['/news'] = (410, {}, b'gone')
        mirror = self.mirror(); mirror.run()
        self.assertEqual(mirror.records[ORIGIN + '/news']['source_status'], 410)
        self.assertIn('Source status: 410', (self.root / 'out' / mirror.records[ORIGIN + '/news']['path']).read_text())

    def test_url_normalization(self):
        mirror = self.mirror()
        self.assertIsNone(mirror.canonical('https://www.cheyennecity.org.evil.example/a'))
        self.assertIsNone(mirror.canonical('https://user:pass@www.cheyennecity.org/a'))
        self.assertIsNone(mirror.canonical('/login'))
        self.assertIsNone(mirror.canonical('javascript:alert(1)'))
        self.assertEqual(mirror.canonical('/news?utm_source=spam#top'), ORIGIN + '/news')

    def test_render_without_network(self):
        mirror = self.mirror(); mirror.render()
        self.assertFalse(self.calls)
        self.assertIn('No city content has been fetched yet', (self.root / 'out/index.html').read_text())

    def test_total_archive_budget(self):
        mirror = self.mirror(max_archive_bytes=1)
        report = mirror.run()
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(len(mirror.records), 0)
        self.assertTrue(any('archive budget' in e['error'] for e in report['errors']))

    def test_pending_work_not_starved_by_seed(self):
        self.mirror(max_pages_per_run=1).run()
        second = self.mirror(max_pages_per_run=1)
        second.run()
        self.assertIn(ORIGIN + '/news', second.records)

    def test_robots_missing_allows_public_crawl(self):
        self.routes['/robots.txt'] = (404, {}, b'')
        mirror = self.mirror()
        mirror.run()
        self.assertIn(ORIGIN + '/', mirror.records)

    def test_same_host_redirect_still_checks_robots(self):
        self.routes['/news'] = (302, {'location': '/secret'}, b'')
        mirror = self.mirror()
        mirror.run()
        self.assertFalse(any(url.endswith('/secret') for url, _ in self.calls))

    def test_pdf_signature(self):
        self.routes['/packet.pdf'] = (200, {'content-type': 'application/pdf'}, b'<script>bad</script>')
        mirror = self.mirror(); report = mirror.run()
        self.assertEqual(report['status'], 'partial')
        self.assertNotIn(ORIGIN + '/packet.pdf', mirror.records)

if __name__ == '__main__':
    unittest.main()
