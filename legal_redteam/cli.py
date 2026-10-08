"""Command-line interface for the legal research red-team prototype."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .analyzer import analyze_case
from .citator import check_case_authorities
from .drafting import OpenAICompatibleDraftingProvider, draft_issue
from .ingest import load_case
from .issue_packs import load_issue_rules
from .providers import SearchRequest, default_provider
from .report import render_markdown


def _emit(payload: Any, output: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="legal-redteam",
        description="Create auditable issue-spotting, source-search, and counteranalysis outputs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="analyze a case packet or source document offline")
    analyze.add_argument("input", type=Path, help="case JSON, source file, or folder of source documents")
    analyze.add_argument(
        "--format", choices=("markdown", "json"), default="markdown",
        help="output format (default: markdown)",
    )
    analyze.add_argument("--output", "-o", type=Path, help="write report to this path instead of stdout")
    analyze.add_argument("--rules", type=Path, help="append a validated JSON issue pack to the built-in catalog")
    analyze.add_argument("--ocr", action="store_true", help="explicitly OCR textless PDF pages (optional local dependencies required)")
    analyze.add_argument("--ocr-language", default="eng", help="Tesseract language code used only with --ocr (default: eng)")
    analyze.add_argument("--preserve-sources-dir", type=Path, help="copy the original non-JSON input to a SHA-256-named file in this directory")

    research = subparsers.add_parser("research", help="search selected official or discovery providers")
    research.add_argument("query", help="search terms; queries are sent only to providers explicitly selected")
    research.add_argument(
        "--provider", action="append",
        choices=("us-constitution", "uscode", "ecfr", "federal-register", "wyoming-statutes", "courtlistener", "local-folder"),
        help="provider to query; repeat as needed (default: ecfr and federal-register)",
    )
    research.add_argument("--as-of", help="date filter for historical search where supported (YYYY-MM-DD)")
    research.add_argument("--uscode-edition", default="prelim", help="OLRC U.S. Code edition: prelim or a four-digit year")
    research.add_argument("--limit", type=int, default=10, help="maximum results per provider, 1–100")
    research.add_argument("--wyoming-titles", help="comma-separated Wyoming title numbers, e.g. 1,15,16,18,97")
    research.add_argument("--local-corpus", type=Path, help="local folder for the local-folder provider")
    research.add_argument("--local-manifest", type=Path, help="JSON metadata manifest for local files")
    research.add_argument("--local-ocr", action="store_true", help="explicitly OCR textless PDFs in local corpus")
    research.add_argument("--cache-dir", type=Path, help="cache directory for downloaded Wyoming statute PDFs")
    research.add_argument("--output", "-o", type=Path, help="write JSON results to this path instead of stdout")

    cite = subparsers.add_parser("cite-check", help="run an optional case-law cited-by/negative-treatment discovery search")
    cite.add_argument("input", type=Path, help="case JSON packet containing case-law authorities")
    cite.add_argument("--limit", type=int, default=100, help="maximum citing-opinion records requested per authority")
    cite.add_argument("--output", "-o", type=Path, help="write JSON results to this path instead of stdout")

    draft = subparsers.add_parser("draft", help="explicitly request a source-grounded, structured LLM draft")
    draft.add_argument("input", type=Path, help="case JSON packet")
    draft.add_argument("--issue-id", required=True, help="surfaced issue identifier to draft")
    draft.add_argument("--rules", type=Path, help="append a validated JSON issue pack")
    draft.add_argument("--output", "-o", type=Path, help="write JSON draft to this path instead of stdout")

    return parser


def _provider_options(provider_id: str, args: argparse.Namespace) -> dict[str, Any]:
    if provider_id == "uscode":
        return {"edition": args.uscode_edition}
    if provider_id == "wyoming-statutes":
        titles = [item.strip() for item in (args.wyoming_titles or "").split(",") if item.strip()]
        return {"title_numbers": titles, "cache_dir": args.cache_dir}
    if provider_id == "courtlistener":
        return {"token": os.environ.get("LEGAL_REDTEAM_COURTLISTENER_TOKEN")}
    if provider_id == "local-folder":
        if not args.local_corpus:
            raise ValueError("--local-corpus is required when selecting --provider local-folder")
        return {
            "root": args.local_corpus,
            "manifest_path": args.local_manifest,
            "enable_ocr": args.local_ocr,
        }
    return {}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            case = load_case(
                args.input,
                enable_ocr=args.ocr,
                ocr_language=args.ocr_language,
                preserve_sources_dir=args.preserve_sources_dir,
            )
            rules = load_issue_rules(args.rules)
            result = analyze_case(case, issue_rules=rules)
            rendered = (
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
                if args.format == "json"
                else render_markdown(result)
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0

        if args.command == "research":
            if not 1 <= args.limit <= 100:
                raise ValueError("--limit must be between 1 and 100")
            provider_ids = args.provider or ["ecfr", "federal-register"]
            results = []
            errors = []
            request = SearchRequest(query=args.query, limit=args.limit, as_of=args.as_of)
            for provider_id in provider_ids:
                try:
                    provider = default_provider(provider_id, **_provider_options(provider_id, args))
                    hits = provider.search(request)
                    results.append({
                        "provider": provider_id,
                        "status": "completed",
                        "result_count": len(hits),
                        "provider_warnings": list(getattr(provider, "search_warnings", [])),
                        "results": [hit.to_dict() for hit in hits],
                    })
                except Exception as exc:
                    errors.append({
                        "provider": provider_id,
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            payload = {
                "query": args.query,
                "as_of": args.as_of,
                "run_mode": "explicit_provider_search",
                "results_by_provider": results,
                "provider_errors": errors,
                "warning": (
                    "Search results are research leads. Confirm primary text, official version, jurisdiction, "
                    "effective date, precedential status, and subsequent history before reliance."
                ),
            }
            _emit(payload, args.output)
            return 0 if results or not errors else 2

        if args.command == "cite-check":
            if not 1 <= args.limit <= 500:
                raise ValueError("--limit must be between 1 and 500")
            case = load_case(args.input)
            provider = default_provider(
                "courtlistener",
                token=os.environ.get("LEGAL_REDTEAM_COURTLISTENER_TOKEN"),
            )
            payload = check_case_authorities(case, provider, limit=args.limit)
            _emit(payload, args.output)
            if any(item["status"].endswith("error") for item in payload["authority_checks"]):
                return 2
            return 0

        if args.command == "draft":
            case = load_case(args.input)
            rules = load_issue_rules(args.rules)
            provider = OpenAICompatibleDraftingProvider.from_environment()
            payload = draft_issue(case, args.issue_id, provider, issue_rules=rules)
            _emit(payload, args.output)
            return 0

        parser.error(f"Unknown command {args.command}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"legal-redteam: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
