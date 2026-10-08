from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from legal_redteam.analyzer import analyze_case
from legal_redteam.cli import main
from legal_redteam.ingest import load_case
from legal_redteam.models import CaseRecord


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "legal_redteam" / "examples" / "synthetic_inspection_matter.json"


class LegalRedTeamEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = load_case(SAMPLE)
        self.result = analyze_case(self.case)
        self.issues = {item["issue_id"]: item for item in self.result["candidate_issues"]}

    def test_synthetic_example_surfaces_relevant_issue_questions(self) -> None:
        self.assertIn("administrative_search", self.issues)
        issue = self.issues["administrative_search"]
        self.assertIn("inspection", issue["matched_terms"])
        self.assertEqual(issue["research_status"], "unresearched_by_engine")
        self.assertEqual(issue["novelty_status"], "unassessed")
        self.assertTrue(issue["fact_links"])
        self.assertIn("fact-1", {fact["id"] for fact in issue["fact_links"]})
        self.assertEqual(issue["candidate_hypothesis"]["status"], "unassessed")
        self.assertIn("fact-1", issue["candidate_hypothesis"]["basis_fact_refs"])
        self.assertIn("not a recognized cause of action", issue["candidate_hypothesis"]["not_a_finding"])

    def test_engine_does_not_invent_authorities_or_win_probabilities(self) -> None:
        self.assertEqual(self.result["authority_coverage"]["layers"]["federal_case"], 0)
        self.assertEqual(self.issues["administrative_search"]["mapped_authorities"], [])
        self.assertIn("No authority tagged", self.issues["administrative_search"]["no_authority_note"])
        self.assertNotIn("win_probability", self.result)
        self.assertTrue(any("will not invent citations" in warning for warning in self.result["completeness_warnings"]))

    def test_issue_signal_is_not_treated_as_fact_or_legal_conclusion(self) -> None:
        issue = self.issues["administrative_search"]
        self.assertTrue(all("does not prove" in fact["note"] for fact in issue["fact_links"]))
        self.assertTrue(any(flag["category"] == "conclusory_legal_label" for flag in self.result["quality_flags"]))
        self.assertTrue(any("does not determine that the statement is false" in flag["meaning"] for flag in self.result["quality_flags"]))

    def test_adverse_and_supporting_authorities_are_not_collapsed(self) -> None:
        payload = self.case.to_dict()
        payload["authorities"] = [
            {
                "id": "auth-support",
                "citation": "Example Authority A",
                "layer": "state_case",
                "jurisdiction": "Wyoming",
                "court_or_body": "Example state court",
                "bindingness": "unknown",
                "treatment": "supports",
                "issue_tags": ["administrative_search"],
                "verification_status": "unverified",
            },
            {
                "id": "auth-adverse",
                "citation": "Example Authority B",
                "layer": "federal_case",
                "jurisdiction": "United States",
                "court_or_body": "Example federal court",
                "bindingness": "unknown",
                "treatment": "contrary",
                "issue_tags": ["administrative_search"],
                "verification_status": "unverified",
            },
        ]
        result = analyze_case(CaseRecord.from_dict(payload))
        issue = {item["issue_id"]: item for item in result["candidate_issues"]}["administrative_search"]
        self.assertEqual(len(issue["supporting_authorities_as_entered"]), 1)
        self.assertEqual(len(issue["contrary_or_adverse_authorities_as_entered"]), 1)
        self.assertEqual(issue["mapped_authorities"][0]["applicability_review"]["territorial_scope"], "potentially_in_scope")
        self.assertEqual(issue["mapped_authorities"][0]["applicability_review"]["bindingness_as_entered"], "unknown")

    def test_authorities_without_a_matching_issue_are_preserved(self) -> None:
        payload = self.case.to_dict()
        payload["authorities"] = [{
            "citation": "Unmapped authority reference supplied for testing",
            "layer": "state_statute",
            "issue_tags": ["custom_research_lane"],
        }]
        result = analyze_case(CaseRecord.from_dict(payload))
        self.assertEqual(len(result["unmapped_authorities"]), 1)
        self.assertEqual(result["unmapped_authorities"][0]["issue_tags"], ["custom_research_lane"])

    def test_authority_verification_checks_are_independent(self) -> None:
        payload = self.case.to_dict()
        payload["authorities"] = [{
            "id": "auth-checks",
            "citation": "Unspecified case reference supplied for testing",
            "layer": "state_case",
            "jurisdiction": "Wyoming",
            "issue_tags": ["administrative_search"],
            "verification_checks": {
                "citation": "checked",
                "primary_text": "checked",
                "currentness": "unresolved",
                "subsequent_history": "not_checked",
            },
        }]
        result = analyze_case(CaseRecord.from_dict(payload))
        issue = {item["issue_id"]: item for item in result["candidate_issues"]}["administrative_search"]
        checks = issue["mapped_authorities"][0]["applicability_review"]["verification_checks_as_entered"]
        self.assertEqual(checks["citation"], "checked")
        self.assertEqual(checks["primary_text"], "checked")
        self.assertEqual(checks["currentness"], "unresolved")
        self.assertEqual(checks["subsequent_history"], "not_checked")
        self.assertTrue(any("checks incomplete" in warning for warning in result["completeness_warnings"]))

    def test_choice_of_law_and_tribal_or_foreign_law_get_separate_lane(self) -> None:
        payload = {
            "case_id": "conflicts-test",
            "title": "Choice-of-law test",
            "questions": ["Which law governs, and does tribal jurisdiction or foreign law apply?"],
            "facts": [],
            "documents": [],
            "authorities": [],
        }
        result = analyze_case(CaseRecord.from_dict(payload))
        issues = {item["issue_id"]: item for item in result["candidate_issues"]}
        issue = issues["choice_of_law_and_sovereign_jurisdiction"]
        self.assertIn("tribal_law", issue["authority_lanes_to_check"])
        self.assertIn("foreign_law", issue["authority_lanes_to_check"])

    def test_international_law_is_gated_not_assumed_enforceable(self) -> None:
        payload = {
            "case_id": "treaty-example",
            "title": "International-law gate test",
            "jurisdiction": {"country": "United States", "state": "Wyoming"},
            "forum": {},
            "questions": ["Does an international human rights treaty create an enforceable claim here?"],
            "facts": [],
            "documents": [],
            "authorities": [],
        }
        issue = analyze_case(CaseRecord.from_dict(payload))["candidate_issues"][0]
        self.assertEqual(issue["issue_id"], "international_law_gate")
        self.assertIn("treaty", issue["authority_lanes_to_check"])
        self.assertEqual(issue["novelty_status"], "unassessed")
        self.assertIn("do not assume", issue["issue_question"])

    def test_plain_text_ingest_keeps_facts_unclassified_and_adds_locators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            text_path = Path(directory) / "packet.md"
            text_path.write_text(
                "# Draft\n\nThe city proposed an inspection without consent.\n\nA resident requested a hearing.\n",
                encoding="utf-8",
            )
            case = load_case(text_path)
        self.assertEqual(len(case.facts), 2)
        self.assertTrue(all(fact.status == "unclassified" for fact in case.facts))
        self.assertTrue(all(fact.source_id == "source-1" for fact in case.facts))
        self.assertEqual(case.facts[0].locator, "Markdown lines 3 (section: Draft)")
        self.assertIn("administrative_search", {item["issue_id"] for item in analyze_case(case)["candidate_issues"]})

    def test_unknown_or_missing_sources_are_reported(self) -> None:
        payload = {
            "case_id": "missing-source-test",
            "facts": [{"id": "f1", "statement": "A hearing was denied.", "source_id": "missing-doc"}],
            "documents": [],
            "authorities": [],
        }
        result = analyze_case(CaseRecord.from_dict(payload))
        self.assertTrue(any("references missing source" in warning for warning in result["completeness_warnings"]))
        self.assertTrue(any("no page/line/timestamp locator" in warning for warning in result["completeness_warnings"]))

    def test_cli_emits_json(self) -> None:
        import contextlib
        import io

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["analyze", str(SAMPLE), "--format", "json"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["engine_version"], "0.2.0")


if __name__ == "__main__":
    unittest.main()
