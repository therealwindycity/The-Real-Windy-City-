"""Offline fixtures: the SAME crawler pointed at three different towns.

Town A runs CivicPlus Agenda Center on its own domain and outsources its
school board to BoardDocs; Town B is on Granicus; Town C is a generic
WordPress small-town site.  No town gets hand-written code -- each gets a
fingerprinted profile plus an induced wrapper, then a focused harvest.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "anycity", Path(__file__).parents[1] / "tools/anycity_crawler.py")
anycity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(anycity)

PDF = b"%PDF-1.7\nfixture body"


def html(body, title="Town"):
    return (200, {"content-type": "text/html"},
            f"<title>{title}</title>{body}".encode())


def make_transport(routes, calls):
    def transport(url, headers):
        calls.append((url, dict(headers)))
        if url in routes:
            return routes[url]
        if url.endswith("/robots.txt"):
            return (200, {}, b"User-agent: *\nAllow: /\n")
        return (404, {}, b"not found")
    return transport


def config(**overrides):
    return anycity.default_config(delay_seconds=0, **overrides)


# --- Town A: CivicPlus + off-domain BoardDocs ------------------------------
A = "https://www.exampleville.gov"
BD = "https://go.boarddocs.com"
TOWN_A = {
    A + "/robots.txt": (200, {}, f"User-agent: *\nDisallow: /private\nSitemap: {A}/sitemap.xml".encode()),
    A + "/sitemap.xml": (200, {}, (
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{A}/AgendaCenter/</loc></url><url><loc>{A}/jobs</loc></url></urlset>").encode()),
    A + "/": html(
        '<h1>Exampleville</h1><a href="/AgendaCenter/">Agendas &amp; Minutes</a>'
        f'<a href="{BD}/example/school/Board.nsf/Public">School Board Agendas</a>'
        '<a href="/news">News</a><a href="/private">Private</a>'
        "<footer>Powered by CivicPlus</footer>", "Exampleville"),
    A + "/AgendaCenter/": html(
        '<a href="/AgendaCenter/ViewFile/Item/101">January 13, 2026 City Council Agenda</a>'
        '<a href="/AgendaCenter/ViewFile/Item/102">January 13, 2026 City Council Minutes</a>'
        '<a href="/AgendaCenter/ViewFile/Item/103">January 27, 2026 Agenda Packet</a>',
        "Agenda Center"),
    A + "/AgendaCenter/ViewFile/Item/101": (200, {"content-type": "application/pdf", "etag": "a101"}, PDF),
    A + "/AgendaCenter/ViewFile/Item/102": (200, {"content-type": "application/pdf", "etag": "a102"}, PDF),
    A + "/AgendaCenter/ViewFile/Item/103": (200, {"content-type": "application/pdf", "etag": "a103"}, PDF),
    A + "/news": html("<p>Road closure Friday.</p>", "News"),
    A + "/jobs": html("<p>Apply today.</p>", "Jobs"),
    BD + "/example/school/Board.nsf/Public": html(
        f'<a href="{BD}/example/school/files/agenda-2026-02-03.pdf">'
        "February 3, 2026 School Board Agenda</a>", "BoardDocs"),
    BD + "/example/school/files/agenda-2026-02-03.pdf":
        (200, {"content-type": "application/pdf"}, PDF),
}

# --- Town B: Granicus -------------------------------------------------------
B = "https://springfield.example.gov"
GR = "https://springfield.granicus.com"
TOWN_B = {
    B + "/": html(
        f'<a href="{GR}/ViewPublisher.php?view_id=2">Meetings &amp; Agendas</a>', "Springfield"),
    GR + "/ViewPublisher.php?view_id=2": html(
        f'<a href="{GR}/MetaViewer.php?event_id=501&meta_id=99">March 9, 2026 Council Agenda</a>'
        "<p>Powered by Granicus</p>", "Granicus"),
    GR + "/MetaViewer.php?event_id=501&meta_id=99":
        (200, {"content-type": "application/pdf"}, PDF),
}

# --- Town C: generic WordPress small town -----------------------------------
C = "https://smalltown.example.org"
TOWN_C = {
    C + "/": html(
        '<link rel="stylesheet" href="/wp-content/themes/town/style.css">'
        '<a href="/meetings/">Town Board Meetings</a>', "Small town"),
    C + "/meetings/": html(
        '<a href="/wp-content/uploads/2026/01/agenda-2026-01-05.pdf">January 5, 2026 Agenda</a>'
        '<a href="/wp-content/uploads/2026/01/minutes-2026-01-05.pdf">January 5, 2026 Minutes</a>'
        '<a href="/wp-content/uploads/2026/02/agenda-2026-02-02.pdf">February 2, 2026 Agenda</a>',
        "Meetings"),
    C + "/wp-content/uploads/2026/01/agenda-2026-01-05.pdf":
        (200, {"content-type": "application/pdf", "etag": "c1"}, PDF),
    C + "/wp-content/uploads/2026/01/minutes-2026-01-05.pdf":
        (200, {"content-type": "application/pdf", "etag": "c2"}, PDF),
    C + "/wp-content/uploads/2026/02/agenda-2026-02-02.pdf":
        (200, {"content-type": "application/pdf", "etag": "c3"}, PDF),
}


class Helpers(unittest.TestCase):
    def test_templatize(self):
        self.assertEqual(
            anycity.templatize_url(A + "/AgendaCenter/ViewFile/Item/101"),
            "www.exampleville.gov/AgendaCenter/ViewFile/Item/{id}")
        self.assertEqual(
            anycity.templatize_url(C + "/wp-content/uploads/2026/01/agenda-2026-01-05.pdf"),
            "smalltown.example.org/wp-content/uploads/{year}/{id}/agenda-{date}.pdf")

    def test_classify_and_dates(self):
        self.assertEqual(anycity.classify_document("Jan Agenda Packet", ""), "agenda-packet")
        self.assertEqual(anycity.classify_document("Minutes", ""), "minutes")
        self.assertEqual(anycity.extract_date("January 13, 2026 Council Agenda"), "2026-01-13")
        self.assertEqual(anycity.extract_date("", "/files/agenda-2026-02-03.pdf"), "2026-02-03")
        self.assertIsNone(anycity.extract_date("no date here"))

    def test_scope_admits_subdomains_and_platforms_only(self):
        scope = anycity.Scope(A + "/")
        self.assertTrue(scope.allowed("https://agenda.exampleville.gov/x"))
        self.assertTrue(scope.allowed(BD + "/x"))            # fingerprinted vendor
        self.assertFalse(scope.allowed("https://www.exampleville.gov.evil.example/x"))
        self.assertFalse(scope.allowed("https://random.example/x"))
        self.assertFalse(scope.allowed("https://www.youtube.com/watch?v=1"))  # recorded, not crawled


class ReconTests(unittest.TestCase):
    def recon(self, routes, seed):
        calls = []
        profile = anycity.Recon(seed, config(),
                                transport=make_transport(routes, calls),
                                sleep=lambda _: None).run()
        return profile, calls

    def test_town_a_fingerprints_two_platforms_and_induces_wrapper(self):
        profile, calls = self.recon(dict(TOWN_A), A + "/")
        found = {p["id"]: p for p in profile["platforms_detected"]}
        self.assertIn("civicplus", found)
        self.assertIn("boarddocs", found)
        self.assertEqual(found["boarddocs"]["confidence"], "high")  # exact vendor host
        hosts = {h["host"] for h in profile["scope"]["discovered_external_hosts"]}
        self.assertIn("go.boarddocs.com", hosts)
        listings = [p["url"] for p in profile["wrapper"]["listing_pages"]]
        self.assertIn(A + "/AgendaCenter/", listings)
        templates = {t["template"] for t in profile["wrapper"]["document_templates"]}
        self.assertTrue(any("ViewFile/Item/{id}" in t for t in templates))
        self.assertFalse(any("/private" in url for url, _ in calls))  # robots honoured

    def test_town_b_detects_granicus_not_civicplus(self):
        profile, _ = self.recon(dict(TOWN_B), B + "/")
        found = {p["id"] for p in profile["platforms_detected"]}
        self.assertIn("granicus", found)
        self.assertNotIn("civicplus", found)

    def test_town_c_unknown_platform_still_gets_a_wrapper(self):
        profile, _ = self.recon(dict(TOWN_C), C + "/")
        found = {p["id"] for p in profile["platforms_detected"]}
        self.assertIn("wordpress", found)
        self.assertNotIn("municode", found)  # a bare /meetings/ path is not evidence
        templates = {t["template"]: t for t in profile["wrapper"]["document_templates"]}
        uploads = [t for t in templates if "/wp-content/uploads/" in t]
        self.assertTrue(uploads)
        self.assertEqual(profile["wrapper"]["candidate_documents_seen_in_recon"], 3)


class HarvestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def harvest(self, routes, seed):
        calls = []
        transport = make_transport(routes, calls)
        profile = anycity.Recon(seed, config(), transport=transport,
                                sleep=lambda _: None).run()
        harvester = anycity.Harvester(profile, self.root / "state", self.root / "out",
                                      transport=transport, sleep=lambda _: None)
        return harvester, harvester.run(), calls

    def test_town_a_harvests_across_hosts_with_kinds_and_dates(self):
        harvester, report, _ = self.harvest(dict(TOWN_A), A + "/")
        self.assertEqual(report["status"], "completed")
        docs = [r for r in harvester.records.values() if r["kind"] == "document"]
        self.assertEqual(len(docs), 4)  # 3 CivicPlus items + 1 BoardDocs PDF
        by_kind = {(d["doc_kind"], d["meeting_date"]) for d in docs}
        self.assertIn(("agenda", "2026-01-13"), by_kind)
        self.assertIn(("minutes", "2026-01-13"), by_kind)
        self.assertIn(("agenda-packet", "2026-01-27"), by_kind)
        self.assertIn(("agenda", "2026-02-03"), by_kind)
        lines = (self.root / "out/documents.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(json.loads(line)["sha256"] for line in lines))
        self.assertTrue(all((self.root / "out" / d["path"]).exists() for d in docs))

    def test_town_c_same_code_no_platform_adapter(self):
        harvester, report, _ = self.harvest(dict(TOWN_C), C + "/")
        self.assertEqual(report["documents"], 3)
        dates = sorted(d["meeting_date"] for d in harvester.records.values()
                       if d["kind"] == "document")
        self.assertEqual(dates, ["2026-01-05", "2026-01-05", "2026-02-02"])

    def test_incremental_second_run_conditional_and_change_log(self):
        routes = dict(TOWN_C)
        harvester, first, _ = self.harvest(routes, C + "/")
        self.assertEqual(first["documents"], 3)
        calls = []
        routes[C + "/wp-content/uploads/2026/01/agenda-2026-01-05.pdf"] = (304, {}, b"")
        routes[C + "/meetings/"] = html(
            '<a href="/wp-content/uploads/2026/01/agenda-2026-01-05.pdf">January 5, 2026 Agenda</a>'
            '<a href="/wp-content/uploads/2026/01/minutes-2026-01-05.pdf">January 5, 2026 Minutes</a>'
            '<a href="/wp-content/uploads/2026/02/agenda-2026-02-02.pdf">February 2, 2026 Agenda</a>'
            '<a href="/wp-content/uploads/2026/03/agenda-2026-03-02.pdf">March 2, 2026 Agenda</a>',
            "Meetings")
        routes[C + "/wp-content/uploads/2026/03/agenda-2026-03-02.pdf"] = (
            200, {"content-type": "application/pdf", "etag": "c4"}, PDF)
        transport = make_transport(routes, calls)
        second = anycity.Harvester(harvester.profile, self.root / "state",
                                   self.root / "out", transport=transport,
                                   sleep=lambda _: None)
        report = second.run()
        self.assertTrue(any(h.get("If-None-Match") == "c1" for _, h in calls))
        record = second.records[C + "/wp-content/uploads/2026/01/agenda-2026-01-05.pdf"]
        self.assertEqual(record["source_status"], 304)
        self.assertIn(C + "/wp-content/uploads/2026/03/agenda-2026-03-02.pdf", second.records)
        self.assertGreater(len(second.state["changes"]), len(harvester.state["changes"]))

    def test_bad_pdf_and_robots_block_are_not_harvested(self):
        routes = dict(TOWN_C)
        routes[C + "/wp-content/uploads/2026/01/minutes-2026-01-05.pdf"] = (
            200, {"content-type": "application/pdf"}, b"<script>not a pdf</script>")
        harvester, report, _ = self.harvest(routes, C + "/")
        self.assertNotIn(C + "/wp-content/uploads/2026/01/minutes-2026-01-05.pdf",
                         harvester.records)
        self.assertEqual(report["documents"], 2)


if __name__ == "__main__":
    unittest.main()
