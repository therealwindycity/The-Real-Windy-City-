import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EvidenceSiteTests(unittest.TestCase):
    def test_coverage_metrics_are_limited_to_catalog_and_transcript_files(self):
        coverage = json.loads((ROOT / "city/coverage.json").read_text())
        catalog = json.loads((ROOT / "cheyenne-2026-transcripts/meetings.json").read_text())
        markdown = list((ROOT / "cheyenne-2026-transcripts").glob("**/*.md"))
        self.assertEqual(coverage["metrics"]["meetings_indexed"], len(catalog))
        self.assertEqual(coverage["metrics"]["stored_markdown_files"], len(markdown))
        self.assertEqual(coverage["metrics"]["auto_generated_caption_transcripts"], 82)
        self.assertEqual(coverage["metrics"]["other_or_unlabeled_caption_sources"], 2)
        self.assertIn("excludes external archive repositories", coverage["scope"])
        self.assertIsNone(coverage["metrics"]["image_review_or_ocr_pending"])

    def test_freshness_never_uses_deployment_time_as_collection_time(self):
        freshness = json.loads((ROOT / "city/freshness.json").read_text())
        self.assertIsNone(freshness["meeting_information_last_checked"])
        self.assertIsNone(freshness["latest_verified_outcome"])
        self.assertEqual(freshness["latest_meeting_indexed"], "2026-09-22")

    def test_october_outcome_is_qualified_and_not_described_as_law(self):
        page = (ROOT / "city/data-center-amendment-2026-10-19.html").read_text()
        self.assertIn("official minutes/audio verification pending", page)
        self.assertIn("not an enacted ordinance", page)
        self.assertIn("Postponed as amended", page)
        self.assertIn("final revised wording", page)

    def test_homepage_does_not_make_unverified_upcoming_claims(self):
        page = (ROOT / "city/index.html").read_text()
        script = (ROOT / "city/city.js").read_text()
        self.assertIn("outcome not yet verified", script)
        self.assertIn("Upcoming · agenda not verified", script)
        self.assertNotIn("upcoming array", page.lower())
        self.assertIn("not a live meeting schedule", page)


if __name__ == "__main__":
    unittest.main()
