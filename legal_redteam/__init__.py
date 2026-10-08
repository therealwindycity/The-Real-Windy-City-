"""Civic Legal Research Red-Team Engine."""

from .analyzer import ENGINE_VERSION, analyze_case
from .ingest import load_case, load_source_directory
from .issue_packs import BUILTIN_ISSUE_RULES, load_issue_rules
from .models import Authority, CaseRecord, EvidenceAssessment, Fact, ResearchLink, SourceDocument

__all__ = [
    "ENGINE_VERSION",
    "Authority",
    "BUILTIN_ISSUE_RULES",
    "CaseRecord",
    "EvidenceAssessment",
    "Fact",
    "ResearchLink",
    "SourceDocument",
    "analyze_case",
    "load_case",
    "load_issue_rules",
    "load_source_directory",
]
