from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_redteam.analyzer import analyze_case
from legal_redteam.citator import check_case_authority
from legal_redteam.drafting import (
    OpenAICompatibleDraftingProvider,
    build_drafting_request,
    draft_issue,
    validate_structured_draft,
)
from legal_redteam.ingest import load_case
from legal_redteam.issue_packs import load_issue_rules
from legal_redteam.models import Authority, CaseRecord
from legal_redteam.providers_uscode import UsCodeProvider
from legal_redteam.providers import (
    CourtListenerProvider,
    EcfrProvider,
    LocalFolderProvider,
    NationalArchivesConstitutionProvider,
    SearchHit,
    SearchRequest,
    WyomingStatutesProvider,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeTransport:
    def __init__(self, routes: dict[str, bytes]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, *, headers=None, timeout=20.0) -> bytes:
        self.calls.append(url)
        for prefix, body in self.routes.items():
            if url.startswith(prefix):
                return body
        raise RuntimeError(f"No fake response configured for {url}")


class IngestionExtensionTests(unittest.TestCase):
    def test_timestamped_markdown_transcript_retains_time_locators_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meeting.md"
            raw = (
                "# Meeting title\n\n"
                "[00:01:02] The chair called the meeting to order.\n\n"
                "[00:01:10] A member moved to approve the agenda.\n"
            ).encode("utf-8")
            path.write_bytes(raw)
            case = load_case(path)
        self.assertEqual(case.documents[0].content_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(case.documents[0].kind, "timestamped_transcript")
        self.assertEqual([fact.locator for fact in case.facts], ["00:01:02", "00:01:10"])
        self.assertTrue(all(fact.status == "unclassified" for fact in case.facts))
        self.assertEqual(case.facts[0].extraction_confidence, "native_timestamp_markers")

    def test_markdown_export_keeps_heading_page_label_and_derivative_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "property-report.pdf.md"
            path.write_text(
                "# Property Report\n\n[Page 1]\n\n## Evidence Log\n\n"
                "The evidence log records an item received on January 26.\n",
                encoding="utf-8",
            )
            case = load_case(path)
        self.assertEqual(case.documents[0].kind, "markdown_export_of_pdf")
        self.assertIn("original PDF is not present", case.documents[0].extraction_warnings[0])
        self.assertIn("source page label 1", case.facts[0].locator)
        self.assertIn("Property Report > Evidence Log", case.facts[0].locator)
        self.assertEqual(case.facts[0].status, "unclassified")

    def test_directory_ingestion_keeps_each_uploaded_markdown_source_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "uploaded-case-files"
            (root / "records").mkdir(parents=True)
            (root / "research").mkdir()
            first = root / "records" / "primary-record.pdf.md"
            first.write_text("# Property Record\n\nThe property sheet lists an item.\n", encoding="utf-8")
            second = root / "research" / "secondary-notes.md.md"
            second.write_text("## Evidentiary Review\n\nThe memo discusses evidence handling.\n", encoding="utf-8")
            (root / "metadata.json").write_text("{}", encoding="utf-8")
            (root / "unhandled.bin").write_bytes(b"binary")
            (root / ".hidden.md").write_text("Should not be ingested.", encoding="utf-8")
            archive = Path(directory) / "preserved-sources"
            case = load_case(root, preserve_sources_dir=archive)

        self.assertEqual(len(case.documents), 2)
        self.assertEqual([document.id for document in case.documents], ["source-1", "source-2"])
        self.assertEqual(case.documents[0].original_filename, "records/primary-record.pdf.md")
        self.assertEqual(len({fact.id for fact in case.facts}), len(case.facts))
        self.assertEqual({fact.source_id for fact in case.facts}, {"source-1", "source-2"})
        self.assertTrue(all(fact.status == "unclassified" for fact in case.facts))
        self.assertTrue(all(document.archived_path for document in case.documents))
        self.assertTrue(any("metadata.json" in warning for warning in case.ingestion_warnings))
        self.assertTrue(any("unhandled.bin" in warning for warning in case.ingestion_warnings))
        result = analyze_case(case)
        self.assertTrue(any("metadata.json" in warning for warning in result["completeness_warnings"]))
        round_trip = CaseRecord.from_dict(case.to_dict())
        self.assertEqual(round_trip.ingestion_warnings, case.ingestion_warnings)

    def test_original_source_can_be_archived_by_hash_without_modifying_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notice.txt"
            archive = Path(directory) / "source-archive"
            raw = b"The official notice states a hearing date.\\n"
            source.write_bytes(raw)
            case = load_case(source, preserve_sources_dir=archive)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(case.documents[0].archived_path, f"{digest}.txt")
            self.assertEqual((archive / f"{digest}.txt").read_bytes(), raw)
            self.assertEqual(source.read_bytes(), raw)

    def test_webvtt_cues_are_ingested_without_dropping_time_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meeting.vtt"
            path.write_text(
                "WEBVTT\n\n"
                "00:00:01.000 --> 00:00:02.000 align:start\nThe clerk called the roll.\n\n"
                "00:00:03.000 --> 00:00:04.500\nThe chair stated the motion passed.\n",
                encoding="utf-8",
            )
            case = load_case(path)
        self.assertEqual(len(case.facts), 2)
        self.assertEqual(case.facts[0].locator, "00:00:01.000–00:00:02.000")
        self.assertIn("motion passed", case.facts[1].statement)

    def test_pdf_text_extraction_is_page_located_and_hash_preserving(self) -> None:
        fake_page_1 = types.SimpleNamespace(extract_text=lambda: "First page paragraph.\nSecond line.")
        fake_page_2 = types.SimpleNamespace(extract_text=lambda: "Second page statement.")
        fake_module = types.SimpleNamespace(PdfReader=lambda stream: types.SimpleNamespace(pages=[fake_page_1, fake_page_2]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.pdf"
            raw = b"%PDF-fake-test-bytes"
            path.write_bytes(raw)
            with patch.dict(sys.modules, {"pypdf": fake_module}):
                case = load_case(path)
        self.assertEqual(case.documents[0].content_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(case.facts[0].locator, "page 1, lines 1-2")
        self.assertEqual(case.facts[1].locator, "page 2, lines 1")
        self.assertEqual(case.documents[0].extraction_confidence, "native_text_layer_unreviewed")

    def test_pdf_scan_without_ocr_records_page_warning(self) -> None:
        fake_page = types.SimpleNamespace(extract_text=lambda: "")
        fake_module = types.SimpleNamespace(PdfReader=lambda stream: types.SimpleNamespace(pages=[fake_page]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scan.pdf"
            path.write_bytes(b"%PDF-test")
            with patch.dict(sys.modules, {"pypdf": fake_module}):
                case = load_case(path)
        self.assertEqual(case.documents[0].extraction_confidence, "no_text_found")
        self.assertTrue(any("no digital text layer" in warning for warning in case.documents[0].extraction_warnings))

    def test_docx_extraction_records_paragraph_locator_without_claiming_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.docx"
            path.write_bytes(b"fake-docx")
            with patch("legal_redteam.ingest._docx_blocks", return_value=[("A notice was issued.", "paragraph 4")]):
                case = load_case(path)
        self.assertEqual(case.facts[0].locator, "paragraph 4")
        self.assertIn("layout-dependent", case.documents[0].extraction_warnings[0])
        self.assertEqual(case.facts[0].status, "unclassified")


class ProviderTests(unittest.TestCase):
    def test_search_request_requires_valid_iso_as_of_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid calendar date"):
            SearchRequest("test", as_of="2026-02-30")
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            SearchRequest("test", as_of="20260228")

    def test_official_uscode_provider_resolves_exact_olrc_citation(self) -> None:
        html = b"<html><body><h1>Section 1983. Civil action for deprivation of rights</h1><p>Every person who, under color of law, causes a deprivation of rights may be liable.</p></body></html>"
        transport = FakeTransport({"https://uscode.house.gov/view.xhtml": html})
        hit = UsCodeProvider(transport=transport).search(SearchRequest("42 U.S.C. § 1983", as_of="2020-01-01"))[0]
        self.assertEqual(hit.citation, "42 U.S.C. § 1983")
        self.assertEqual(hit.layer, "federal_statute")
        self.assertEqual(hit.metadata["granule_id"], "USC-prelim-title42-section1983")
        self.assertIn("Official OLRC", hit.primary_source_status)
        self.assertFalse(hit.metadata["as_of_applied"])
        self.assertTrue(any("as-of date" in warning for warning in hit.warnings))

    def test_uscode_provider_does_not_pretend_to_support_keyword_search(self) -> None:
        provider = UsCodeProvider(transport=FakeTransport({}))
        with self.assertRaisesRegex(Exception, "exact citations only"):
            provider.search(SearchRequest("civil rights"))

    def test_national_archives_provider_searches_constitution_text(self) -> None:
        html = b"<html><body><h2>Amendment I</h2><p>Congress shall make no law respecting an establishment of religion or prohibiting the free exercise thereof.</p></body></html>"
        provider = NationalArchivesConstitutionProvider(FakeTransport({"https://www.archives.gov/founding-docs/constitution-transcript": html}))
        hits = provider.search(SearchRequest("free exercise", limit=2))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].citation, "U.S. Const. amend. I")
        self.assertEqual(hits[0].layer, "federal_constitution")

    def test_ecfr_provider_maps_sections_and_preserves_historical_url(self) -> None:
        payload = {
            "results": [{
                "starts_on": "2016-12-30",
                "ends_on": None,
                "type": "Section",
                "hierarchy": {"title": "21", "section": "1316.09"},
                "headings": {"title": "Food and Drugs", "section": "Application for inspection warrant."},
                "full_text_excerpt": "A warrant shall issue only on a proper showing.",
                "structure_index": 10,
                "change_types": ["effective"],
            }]
        }
        transport = FakeTransport({"https://www.ecfr.gov/api/search/v1/results": json.dumps(payload).encode()})
        hit = EcfrProvider(transport).search(SearchRequest("inspection warrant", as_of="2024-01-01"))[0]
        self.assertEqual(hit.citation, "21 C.F.R. § 1316.09")
        self.assertEqual(hit.layer, "federal_regulation")
        self.assertIn("/on/2024-01-01/", hit.source_url)
        self.assertIn("verify", hit.warnings[0])

    def test_wyoming_official_download_provider_fetches_only_selected_title(self) -> None:
        index = b"""
        <p>This version reflects the statutes as they exist as of July 1, 2026.</p>
        <a href=\"https://wyoleg.gov/statutes/compress/title15.pdf\">Title 15 Cities and Towns</a>
        <a href=\"https://wyoleg.gov/statutes/compress/title16.pdf\">Title 16 City, County, State and Local Powers</a>
        """
        transport = FakeTransport({
            "https://www.wyoleg.gov/stateStatutes/StatutesDownload": index,
            "https://wyoleg.gov/statutes/compress/title15.pdf": b"%PDF-fake-title-15",
        })
        with tempfile.TemporaryDirectory() as directory:
            provider = WyomingStatutesProvider(
                ["15"],
                cache_dir=Path(directory) / "cache",
                transport=transport,
                pdf_extractor=lambda raw: ["§ 15-1-101. Cities and towns may adopt an ordinance after public notice."],
            )
            hits = provider.search(SearchRequest("Title 15 cities", limit=5, as_of="2020-01-01"))
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].citation, "Wyo. Stat. § 15-1-101")
            self.assertEqual(hits[0].layer, "state_statute")
            self.assertEqual(hits[0].metadata["edition_note_from_official_index"], "official index describes the edition as of July 1, 2026")
            self.assertFalse(hits[0].metadata["as_of_applied"])
            self.assertTrue(any("historical Wyoming edition" in warning for warning in hits[0].warnings))
            self.assertTrue(any("title15.pdf" in call for call in transport.calls))
            cached_pdf = Path(directory) / "cache" / "title15.pdf"
            self.assertTrue(cached_pdf.is_file())
            cached_pdf.write_bytes(b"%PDF-corrupted-cache")
            provider.search(SearchRequest("Title 15 cities", limit=5))
            self.assertEqual(cached_pdf.read_bytes(), b"%PDF-fake-title-15")

    def test_wyoming_provider_refuses_unqualified_partial_title_search(self) -> None:
        provider = WyomingStatutesProvider([], transport=FakeTransport({}))
        with self.assertRaisesRegex(Exception, "Select titles explicitly"):
            provider.search(SearchRequest("permit", limit=1))

    def test_local_folder_provider_searches_user_files_with_manifest_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sources"
            root.mkdir()
            (root / "ordinance.txt").write_text("The city ordinance requires public notice before a hearing.\n", encoding="utf-8")
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({
                "ordinance.txt": {
                    "citation": "Cheyenne Ordinance 1234",
                    "layer": "municipal_code",
                    "jurisdiction": "Cheyenne, Wyoming",
                    "official_url": "https://example.gov/ordinance/1234",
                    "primary_source_status": "official_enactment_copy_as_entered",
                }
            }), encoding="utf-8")
            provider = LocalFolderProvider(root, manifest_path=manifest)
            hits = provider.search(SearchRequest("ordinance public notice", limit=5))
        self.assertTrue(hits)
        self.assertEqual(hits[0].layer, "municipal_code")
        self.assertEqual(hits[0].citation, "Cheyenne Ordinance 1234")
        self.assertTrue(hits[0].metadata["manifest_entry_present"])

    def test_courtlistener_discovery_requires_explicit_token(self) -> None:
        provider = CourtListenerProvider(transport=FakeTransport({}))
        with self.assertRaisesRegex(Exception, "LEGAL_REDTEAM_COURTLISTENER_TOKEN"):
            provider.search(SearchRequest("inspection warrant"))


class ResearchGraphAndCitatorTests(unittest.TestCase):
    def test_reviewed_fact_and_authority_edges_populate_element_map(self) -> None:
        case = CaseRecord.from_dict({
            "case_id": "graph-test",
            "title": "Graph test",
            "questions": ["Was an administrative warrant required for this inspection?"],
            "documents": [{"id": "doc-1", "title": "Record"}],
            "facts": [{"id": "fact-1", "statement": "The inspection occurred without consent.", "source_id": "doc-1", "locator": "page 1"}],
            "authorities": [{"id": "auth-1", "citation": "A recorded case", "layer": "state_case", "issue_tags": []}],
            "research_links": [
                {
                    "id": "link-fact",
                    "from_type": "fact",
                    "from_id": "fact-1",
                    "to_type": "element",
                    "to_id": "administrative_search::e1",
                    "relation": "supports",
                    "review_status": "reviewed",
                    "reviewer": "Researcher A",
                    "rationale": "The statement describes the place and conduct for this element.",
                },
                {
                    "id": "link-authority",
                    "from_type": "authority",
                    "from_id": "auth-1",
                    "to_type": "element",
                    "to_id": "administrative_search::e1",
                    "relation": "undercuts",
                    "review_status": "reviewed",
                    "reviewer": "Researcher A",
                    "rationale": "The holding may limit this theory.",
                },
            ],
        })
        result = analyze_case(case)
        issue = next(item for item in result["candidate_issues"] if item["issue_id"] == "administrative_search")
        element = issue["element_fact_map"][0]
        self.assertEqual(element["status"], "researcher_reviewed")
        self.assertEqual(element["reviewed_fact_links"][0]["from_id"], "fact-1")
        self.assertEqual(element["reviewed_authority_links"][0]["from_id"], "auth-1")
        self.assertEqual([item["id"] for item in issue["mapped_authorities"]], ["auth-1"])
        self.assertEqual(result["research_graph"]["reviewed_edge_count"], 2)

    def test_assessed_evidence_requires_reviewer_and_rationale(self) -> None:
        with self.assertRaisesRegex(ValueError, "needs reviewer and rationale"):
            CaseRecord.from_dict({
                "facts": [{
                    "statement": "A record exists.",
                    "evidence_assessment": {"strength": "moderate"},
                }]
            })
        case = CaseRecord.from_dict({
            "facts": [{
                "statement": "A record exists.",
                "evidence_assessment": {
                    "strength": "moderate",
                    "authenticity": "authenticated",
                    "directness": "documentary",
                    "corroboration": "single_source",
                    "reviewer": "Researcher A",
                    "rationale": "The source is a signed record; independent corroboration is absent.",
                },
            }]
        })
        self.assertEqual(case.facts[0].evidence_assessment.strength, "moderate")

    def test_custom_issue_pack_extends_builtin_catalog(self) -> None:
        rules = load_issue_rules(ROOT / "examples" / "custom_issue_pack.json")
        case = CaseRecord.from_dict({
            "case_id": "custom-rule-test",
            "title": "Zoning review",
            "questions": ["Does the zoning variance comply with the adopted code?"],
        })
        result = analyze_case(case, issue_rules=rules)
        self.assertIn("local_zoning_variance", result["issue_catalog"]["rule_ids"])
        self.assertIn("local_zoning_variance", {item["issue_id"] for item in result["candidate_issues"]})

    def test_citator_marks_hits_as_candidates_and_does_not_change_authority(self) -> None:
        authority = Authority.from_dict({
            "id": "case-1",
            "citation": "Example v. City, 123 F.3d 456",
            "layer": "federal_case",
        })

        class FakeCitingProvider:
            provider_id = "fake-citator"

            def search(self, request):
                return [SearchHit(
                    provider=self.provider_id,
                    record_id="cluster-1",
                    title="Example v. City",
                    citation=authority.citation,
                    layer="federal_case",
                    snippet="Example v. City, 123 F.3d 456.",
                    metadata={"cluster_id": 123, "official_opinion_url": "https://court.example/opinion"},
                    captured_at="2026-10-06T12:00:00+00:00",
                )]

            def search_citing(self, cluster_id, *, limit=100):
                return [SearchHit(
                    provider=self.provider_id,
                    record_id="later-1",
                    title="Later Opinion",
                    citation="Later Opinion",
                    snippet="The earlier decision was expressly overruled on this point.",
                    metadata={"cluster_id": 456, "docket_number": "No. 24-1"},
                )]

        result = check_case_authority(authority, FakeCitingProvider())
        self.assertEqual(result["status"], "potential_negative_treatment_candidates_found")
        self.assertIn("overruled", result["candidate_negative_treatment_hits"][0]["possible_treatment_terms"])
        self.assertEqual(result["candidate_negative_treatment_hits"][0]["docket_number"], "No. 24-1")
        self.assertEqual(authority.subsequent_history_check, "not_checked")
        self.assertEqual(result["automatic_verification_change"], "none")


class DraftingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = CaseRecord.from_dict({
            "case_id": "draft-test",
            "title": "Structured drafting test",
            "as_of": "2026-10-06",
            "jurisdiction": {"country": "United States", "state": "Wyoming"},
            "forum": {"name": "Example court"},
            "procedural_posture": "Research stage",
            "questions": ["Was an administrative warrant required for an inspection?"],
            "documents": [{"id": "doc-1", "title": "Record", "text": "RAW SOURCE TEXT THAT MUST NOT BE SENT"}],
            "facts": [{
                "id": "fact-1",
                "statement": "The agency record describes an inspection without consent.",
                "source_quote": "The inspector entered without consent.",
                "status": "alleged",
                "source_id": "doc-1",
                "locator": "page 2, lines 4-5",
            }],
            "authorities": [{
                "id": "auth-1",
                "citation": "Example v. City, 123 F.3d 456",
                "layer": "federal_case",
                "jurisdiction": "United States",
                "court_or_body": "Example Court of Appeals",
                "issue_tags": ["administrative_search"],
                "proposition": "The opinion addresses administrative inspection standards.",
                "source_excerpt": "A neutral decision-maker must review the application under the governing standard.",
                "pinpoint": "123 F.3d at 460",
                "official_opinion_url": "https://court.example/opinion/123",
                "reporter_citation": "123 F.3d 456",
                "docket_number": "No. 24-123",
                "precedential_status": "published",
                "source_capture_sha256": "a" * 64,
                "verification_checks": {
                    "citation": "checked",
                    "primary_text": "checked",
                    "currentness": "checked",
                    "subsequent_history": "checked",
                },
            }],
        })

    def _valid_draft(self, request):
        fact_ids = request["output_constraints"]["allowed_fact_refs"]
        authority_ids = request["output_constraints"]["allowed_authority_refs"]
        return {
            "issue_id": request["issue_id"],
            "neutral_statement": "The issue depends on the operative inspection facts and verified source excerpts.",
            "element_analysis": [
                {
                    "element_id": element["element_id"],
                    "status": "uncertain",
                    "fact_refs": fact_ids[:1],
                    "authority_refs": authority_ids[:1],
                    "analysis": "The supplied record should be compared with the source excerpt and forum-specific rule.",
                }
                for element in request["elements"]
            ],
            "candidate_theory": {
                "status": "hypothesis_only",
                "existing_rule": "The supplied excerpt describes a review requirement.",
                "analogical_bridge": "Compare the challenged process with the conditions in the source excerpt.",
                "strongest_disanalogy": "The actual inspection setting or governing procedure may differ.",
                "falsifier": "A controlling source or undisputed record fact could defeat the comparison.",
            },
            "red_team": {
                "best_opposing_account": "The agency may rely on consent, an exception, or a different statutory procedure.",
                "strongest_legal_counterargument": "The cited source may be limited by the forum or the facts.",
                "likely_defenses": "Standing, finality, immunity, exhaustion, and remedy remain open.",
            },
            "procedural_and_remedy_gates": ["Verify forum, finality, preservation, deadlines, immunity, and remedy."],
            "research_gaps": ["Compare current primary law and adverse authority."],
            "citation_refs": authority_ids[:1],
        }

    def test_drafting_request_sends_only_allowlisted_structured_material(self) -> None:
        request = build_drafting_request(self.case, "administrative_search")
        serialized = json.dumps(request)
        self.assertNotIn("RAW SOURCE TEXT THAT MUST NOT BE SENT", serialized)
        self.assertIn("The inspector entered without consent.", serialized)
        self.assertEqual(request["output_constraints"]["allowed_authority_refs"], ["auth-1"])

    def test_structured_draft_passes_allowlist_validation(self) -> None:
        class FakeProvider:
            provider_id = "fake"
            model = "test"

            def generate(inner_self, request):
                return self._valid_draft(request)

        result = draft_issue(self.case, "administrative_search", FakeProvider())
        self.assertEqual(result["draft_status"], "machine_draft_requires_human_review")
        self.assertEqual(result["citations"]["auth-1"]["citation"], "Example v. City, 123 F.3d 456")
        self.assertIn("auth-1", result["draft"]["citation_refs"])

    def test_draft_rejects_unknown_authority_ids_and_free_form_citations(self) -> None:
        request = build_drafting_request(self.case, "administrative_search")
        invalid = self._valid_draft(request)
        invalid["citation_refs"] = ["invented-case"]
        with self.assertRaisesRegex(ValueError, "allowlist"):
            validate_structured_draft(invalid, request)
        invalid = self._valid_draft(request)
        invalid["neutral_statement"] += " See 999 F.3d 888."
        with self.assertRaisesRegex(ValueError, "free-form legal citation"):
            validate_structured_draft(invalid, request)
        invalid = self._valid_draft(request)
        invalid["neutral_statement"] += " Compare Made-Up Case v. Another City."
        with self.assertRaisesRegex(ValueError, "free-form legal citation"):
            validate_structured_draft(invalid, request)

    def test_drafting_requires_researcher_verified_primary_excerpt(self) -> None:
        payload = self.case.to_dict()
        payload["authorities"][0]["primary_text_check"] = "not_checked"
        case = CaseRecord.from_dict(payload)
        with self.assertRaisesRegex(ValueError, "until at least one mapped authority"):
            build_drafting_request(case, "administrative_search")

    def test_openai_compatible_endpoint_configuration_requires_endpoint_and_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "endpoint is required"):
            OpenAICompatibleDraftingProvider(endpoint="", model="model")


if __name__ == "__main__":
    unittest.main()
