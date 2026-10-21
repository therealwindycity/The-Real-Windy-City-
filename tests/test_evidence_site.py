import datetime
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EvidenceSiteTests(unittest.TestCase):
    def test_coverage_metrics_are_limited_to_catalog_and_transcript_files(self):
        coverage = json.loads((ROOT / "city/coverage.json").read_text())
        catalog = json.loads((ROOT / "cheyenne-2026-transcripts/meetings.json").read_text())
        archive = ROOT / "cheyenne-2026-transcripts"
        markdown = list(archive.glob("**/*.md"))
        self.assertEqual(coverage["metrics"]["meetings_indexed"], len(catalog))
        self.assertEqual(coverage["metrics"]["stored_markdown_files"], len(markdown))
        # Caption-source counts must be derivable from the transcript files
        # the catalog points at; they legitimately grow as transcripts are
        # added, so this recomputes them instead of pinning a snapshot.
        auto = other = 0
        for entry in catalog:
            name = entry.get("file")
            if not name or not (archive / name).is_file():
                continue
            text = (archive / name).read_text()
            match = re.search(r"^- \*\*Captions:\*\*\s*(.+)$", text, re.MULTILINE)
            label = match.group(1).strip() if match else ""
            if "auto-generated" in label.lower():
                auto += 1
            else:
                other += 1
        self.assertEqual(coverage["metrics"]["auto_generated_caption_transcripts"], auto)
        self.assertEqual(coverage["metrics"]["other_or_unlabeled_caption_sources"], other)
        self.assertEqual(
            coverage["metrics"]["catalog_entries_without_transcript_file"],
            sum(1 for e in catalog if not e.get("file") or not (archive / e["file"]).is_file()),
        )
        self.assertIn("excludes external archive repositories", coverage["scope"])
        self.assertIsNone(coverage["metrics"]["image_review_or_ocr_pending"])

    def test_freshness_never_uses_deployment_time_as_collection_time(self):
        freshness = json.loads((ROOT / "city/freshness.json").read_text())
        catalog = json.loads((ROOT / "cheyenne-2026-transcripts/meetings.json").read_text())
        dated = [m["date"] for m in catalog if isinstance(m.get("date"), str) and len(m["date"]) == 10]
        # Latest indexed is always the catalog maximum, never a build time.
        self.assertEqual(freshness["latest_meeting_indexed"], max(dated))
        # A collection-check date is a human collection event: either not
        # recorded, or a plain YYYY-MM-DD date on/after the newest indexed
        # meeting and not in the future. (A full timestamp here would smell
        # like a deployment timestamp substituted for collection.)
        checked = freshness["meeting_information_last_checked"]
        if checked is not None:
            self.assertRegex(checked, r"^\d{4}-\d{2}-\d{2}$")
            self.assertGreaterEqual(checked, freshness["latest_meeting_indexed"])
            today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            self.assertLessEqual(checked, today)
        outcome = freshness["latest_verified_outcome"]
        if outcome is not None:
            self.assertTrue(str(outcome).strip())

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
