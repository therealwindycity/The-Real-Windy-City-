from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from legal_redteam.upload_preview import (
    analyze_upload_batch,
    delete_upload_batch,
    parse_multipart_files,
    safe_relative_upload_name,
    save_upload_batch,
)


class UploadPreviewTests(unittest.TestCase):
    def test_upload_names_preserve_relative_folders_and_reject_traversal(self) -> None:
        self.assertEqual(
            safe_relative_upload_name("case-files/research notes.pdf.md"),
            Path("case-files") / "research notes.pdf.md",
        )
        self.assertEqual(
            safe_relative_upload_name(r"C:\fakepath\source.md"),
            Path("fakepath") / "source.md",
        )
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            safe_relative_upload_name("../../outside.md")
        with self.assertRaisesRegex(ValueError, "Absolute"):
            safe_relative_upload_name("/etc/passwd")

    def test_multipart_parser_keeps_markdown_export_filename(self) -> None:
        boundary = "----legal-redteam-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="nested/report.pdf.md"\r\n'
            "Content-Type: text/markdown; charset=utf-8\r\n\r\n"
            "# Report\n\nA source passage.\n\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        uploads = parse_multipart_files(f"multipart/form-data; boundary={boundary}", body)
        self.assertEqual(uploads, [("nested/report.pdf.md", b"# Report\n\nA source passage.\n")])

    def test_private_batch_upload_runs_offline_analyzer_and_can_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / "private" / "uploads"
            batch_id, names = save_upload_batch(storage, [
                ("records/police-report.pdf.md", b"# Report\n\n[Page 1]\n\nAn officer took property.\n"),
                ("research/notes.md.md", b"# Notes\n\nA separate source discusses the record.\n"),
            ])
            self.assertEqual(len(names), 2)
            self.assertEqual((storage / batch_id / names[0]).read_bytes(), b"# Report\n\n[Page 1]\n\nAn officer took property.\n")
            result = analyze_upload_batch(storage, batch_id)
            self.assertEqual(result["source_count"], 2)
            self.assertEqual(result["fact_count"], 2)
            self.assertIn("Research graph", result["report_markdown"])
            self.assertIn("source-bundle", result["report_json"]["case_id"])
            delete_upload_batch(storage, batch_id)
            self.assertFalse((storage / batch_id).exists())

    def test_batch_ids_cannot_escape_storage_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Invalid upload batch ID"):
                analyze_upload_batch(Path(directory), "../../anything")


if __name__ == "__main__":
    unittest.main()
