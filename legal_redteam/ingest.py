"""Source-preserving ingestion with page, paragraph, line, and time locators.

PDF and DOCX parsing use optional dependencies. OCR is always opt-in because it
can introduce recognition errors and requires a local Tesseract installation.
"""

from __future__ import annotations

import hashlib
import html
import importlib
import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable

from .models import CaseRecord, Fact, SourceDocument

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}
SUPPORTED_TRANSCRIPT_SUFFIXES = {".vtt", ".srt"}
SUPPORTED_SUFFIXES = SUPPORTED_TEXT_SUFFIXES | SUPPORTED_TRANSCRIPT_SUFFIXES | {".json", ".pdf", ".docx"}

_MD_TIMESTAMP = re.compile(
    r"^\s*\[(?P<time>\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)\]\s*(?P<text>.*)$"
)
_CUE_TIMESTAMP = re.compile(
    r"(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3})"
)
_MD_HEADING = re.compile(r"^\s{0,3}(?P<marks>#{1,6})\s+(?P<title>.*?)\s*#*\s*$")
_MD_PAGE_LABEL = re.compile(r"^\[?\s*(?:page|p\.?)\s*#?\s*(\d+)(?:\s*(?:of|/)\s*\d+)?\s*\]?$", re.I)
_MD_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)")
_MD_RULE = re.compile(r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_DIRECTORY_IGNORED_PARTS = {".git", "__pycache__", ".legal_redteam_cache", "node_modules"}


def _captured_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _paragraph_facts(
    text: str,
    source_id: str,
    *,
    start_index: int = 1,
    extraction_method: str = "utf8-text",
    extraction_confidence: str = "utf8_text_decoded",
    locator_prefix: str = "line",
) -> list[Fact]:
    facts: list[Fact] = []
    lines = text.splitlines()
    start: int | None = None
    block: list[str] = []

    def flush(end_line: int) -> None:
        nonlocal start, block
        statement = "\n".join(block).strip()
        if statement:
            line_range = f"{start}-{end_line}" if start != end_line else str(start)
            facts.append(Fact(
                id=f"fact-{start_index + len(facts)}",
                statement=statement,
                status="unclassified",
                source_id=source_id,
                locator=f"{locator_prefix} {line_range}",
                extraction_method=extraction_method,
                extraction_confidence=extraction_confidence,
            ))
        start = None
        block = []

    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            if start is None:
                start = line_number
            block.append(line.rstrip())
        elif start is not None:
            flush(line_number - 1)
    if start is not None:
        flush(len(lines))
    return facts


def _markdown_facts(text: str, source_id: str) -> list[Fact]:
    """Split Markdown into paragraph/caption facts with explicit heading/page context."""
    facts: list[Fact] = []
    heading_stack: dict[int, str] = {}
    page_label: str | None = None
    block_start: int | None = None
    block: list[str] = []
    block_headings: tuple[str, ...] = ()
    in_fence = False

    def flush(end_line: int) -> None:
        nonlocal block_start, block, block_headings
        statement = "\n".join(block).strip()
        if statement and block_start is not None:
            line_range = f"{block_start}-{end_line}" if block_start != end_line else str(block_start)
            locator = f"Markdown lines {line_range}"
            if page_label:
                locator = f"source page label {page_label}, {locator}"
            if block_headings:
                locator += " (section: " + " > ".join(block_headings) + ")"
            facts.append(Fact(
                id=f"fact-{len(facts) + 1}",
                statement=statement,
                status="unclassified",
                source_id=source_id,
                locator=locator,
                extraction_method="markdown-paragraph-parser",
                extraction_confidence="markdown_text_unreviewed",
            ))
        block_start = None
        block = []
        block_headings = ()

    for line_number, line in enumerate(text.splitlines(), start=1):
        if _MD_FENCE.match(line):
            if block_start is None:
                block_start = line_number
                block_headings = tuple(heading_stack[level] for level in sorted(heading_stack))
            block.append(line.rstrip())
            in_fence = not in_fence
            continue
        if not in_fence:
            heading = _MD_HEADING.match(line)
            if heading:
                flush(line_number - 1)
                level = len(heading.group("marks"))
                title = heading.group("title").strip()
                page_match = _MD_PAGE_LABEL.match(title)
                if page_match:
                    page_label = page_match.group(1)
                else:
                    heading_stack = {key: value for key, value in heading_stack.items() if key < level}
                    heading_stack[level] = title
                continue
            page_match = _MD_PAGE_LABEL.match(line.strip())
            if page_match:
                flush(line_number - 1)
                page_label = page_match.group(1)
                continue
            if _MD_RULE.match(line):
                flush(line_number - 1)
                continue
        if line.strip():
            if block_start is None:
                block_start = line_number
                block_headings = tuple(heading_stack[level] for level in sorted(heading_stack))
            block.append(line.rstrip())
        elif block_start is not None:
            flush(line_number - 1)
    if block_start is not None:
        flush(len(text.splitlines()))
    return facts


def _clean_transcript_text(value: str) -> str:
    text = re.sub(r"<[^>]*>", "", value)
    text = html.unescape(text).replace("\ufeff", "")
    return " ".join(text.split()).strip()


def _timestamped_markdown_facts(text: str, source_id: str) -> list[Fact]:
    facts: list[Fact] = []
    current_time: str | None = None
    block: list[str] = []

    def flush() -> None:
        nonlocal current_time, block
        statement = _clean_transcript_text(" ".join(block))
        if current_time and statement:
            facts.append(Fact(
                id=f"fact-{len(facts) + 1}",
                statement=statement,
                status="unclassified",
                source_id=source_id,
                locator=f"{current_time}",
                extraction_method="timestamped-markdown",
                extraction_confidence="native_timestamp_markers",
            ))
        current_time = None
        block = []

    for line in text.splitlines():
        match = _MD_TIMESTAMP.match(line)
        if match:
            flush()
            current_time = match.group("time").replace(",", ".")
            if match.group("text").strip():
                block.append(match.group("text"))
        elif current_time and line.strip():
            block.append(line.strip())
    flush()
    return facts


def _timed_subtitle_facts(text: str, source_id: str, *, kind: str) -> list[Fact]:
    facts: list[Fact] = []
    for block in re.split(r"\r?\n\s*\r?\n", text):
        match = _CUE_TIMESTAMP.search(block)
        if not match:
            continue
        lines = block[match.end():].splitlines()
        statement = _clean_transcript_text(" ".join(lines))
        if not statement:
            continue
        start = match.group("start").replace(",", ".")
        end = match.group("end").replace(",", ".")
        facts.append(Fact(
            id=f"fact-{len(facts) + 1}",
            statement=statement,
            status="unclassified",
            source_id=source_id,
            locator=f"{start}–{end}",
            extraction_method=kind,
            extraction_confidence="native_timestamp_markers",
        ))
    return facts


def _pdf_pages_from_bytes(raw: bytes) -> tuple[list[str], str]:
    """Extract digital PDF text, using pypdf or PyMuPDF if installed."""
    try:
        pypdf = importlib.import_module("pypdf")
        reader = pypdf.PdfReader(BytesIO(raw))
        return [page.extract_text() or "" for page in reader.pages], "pypdf"
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        raise ValueError(f"Could not extract PDF text with pypdf: {exc}") from exc
    try:
        fitz = importlib.import_module("fitz")
        document = fitz.open(stream=raw, filetype="pdf")
        return [page.get_text("text") or "" for page in document], "pymupdf"
    except ModuleNotFoundError as exc:
        raise ValueError(
            "PDF ingestion requires pypdf or PyMuPDF. Install optional dependencies with "
            "`python -m pip install -r legal_redteam/requirements-optional.txt`."
        ) from exc
    except Exception as exc:
        raise ValueError(f"Could not extract PDF text with PyMuPDF: {exc}") from exc


def extract_pdf_pages(raw: bytes) -> list[str]:
    """Public digital-text extractor used by the Wyoming statute connector."""
    pages, _method = _pdf_pages_from_bytes(raw)
    return pages


def _ocr_page(path: Path, page_index: int, language: str) -> str:
    try:
        fitz = importlib.import_module("fitz")
        pytesseract = importlib.import_module("pytesseract")
        image_module = importlib.import_module("PIL.Image")
    except ModuleNotFoundError as exc:
        raise ValueError(
            "OCR requires PyMuPDF, Pillow, pytesseract, and the Tesseract executable. "
            "Install Python extras from legal_redteam/requirements-optional.txt and install Tesseract separately."
        ) from exc
    try:
        document = fitz.open(str(path))
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(dpi=220, alpha=False)
        image = image_module.open(BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=language) or ""
    except Exception as exc:
        raise ValueError(f"OCR failed on PDF page {page_index + 1}: {exc}") from exc


def _pdf_facts_and_text(
    path: Path,
    raw: bytes,
    source_id: str,
    *,
    enable_ocr: bool,
    ocr_language: str,
) -> tuple[list[Fact], str, str, str, list[str]]:
    pages, parser_name = _pdf_pages_from_bytes(raw)
    facts: list[Fact] = []
    rendered_pages: list[str] = []
    warnings: list[str] = []
    extraction_methods: set[str] = set()

    for page_number, page_text in enumerate(pages, start=1):
        text = page_text or ""
        method = parser_name
        if not text.strip() and enable_ocr:
            text = _ocr_page(path, page_number - 1, ocr_language)
            method = "tesseract-ocr"
        if text.strip():
            extraction_methods.add(method)
            rendered_pages.append(f"[Page {page_number}]\n{text.strip()}")
            page_facts = _paragraph_facts(
                text,
                source_id,
                start_index=len(facts) + 1,
                extraction_method=method,
                extraction_confidence=(
                    "ocr_unreviewed" if method == "tesseract-ocr" else "native_text_layer_unreviewed"
                ),
                locator_prefix=f"page {page_number}, lines",
            )
            # _paragraph_facts already emits `page N, lines start-end` because
            # its locator prefix is intentionally a complete human-readable stem.
            facts.extend(page_facts)
        elif enable_ocr:
            warnings.append(f"Page {page_number}: OCR returned no text; inspect the original page image.")
        else:
            warnings.append(f"Page {page_number}: no digital text layer detected; use --ocr if OCR is appropriate.")
            rendered_pages.append(f"[Page {page_number}] [No text extracted]")

    if not facts:
        confidence = "no_text_found"
    elif "tesseract-ocr" in extraction_methods and len(extraction_methods) > 1:
        confidence = "mixed_text_and_ocr_unreviewed"
    elif "tesseract-ocr" in extraction_methods:
        confidence = "ocr_unreviewed"
    else:
        confidence = "native_text_layer_unreviewed"
    method_summary = "+".join(sorted(extraction_methods)) if extraction_methods else parser_name
    return facts, "\n\n".join(rendered_pages), method_summary, confidence, warnings


def _docx_blocks(path: Path) -> list[tuple[str, str]]:
    try:
        docx = importlib.import_module("docx")
        paragraph_module = importlib.import_module("docx.text.paragraph")
        table_module = importlib.import_module("docx.table")
    except ModuleNotFoundError as exc:
        raise ValueError(
            "DOCX ingestion requires python-docx. Install optional dependencies with "
            "`python -m pip install -r legal_redteam/requirements-optional.txt`."
        ) from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise ValueError(f"Could not extract DOCX text: {exc}") from exc
    Paragraph = paragraph_module.Paragraph
    Table = table_module.Table
    blocks: list[tuple[str, str]] = []
    paragraph_number = 0
    table_number = 0
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph_number += 1
            value = Paragraph(child, document).text.strip()
            if value:
                blocks.append((value, f"paragraph {paragraph_number}"))
        elif child.tag.endswith("}tbl"):
            table_number += 1
            table = Table(child, document)
            for row_number, row in enumerate(table.rows, start=1):
                cells = [" ".join(cell.text.split()) for cell in row.cells]
                value = " | ".join(cell for cell in cells if cell)
                if value:
                    blocks.append((value, f"table {table_number}, row {row_number}"))
    return blocks


def _document_for_file(
    *,
    source_id: str,
    path: Path,
    raw: bytes,
    kind: str,
    text: str,
    extraction_method: str,
    extraction_confidence: str,
    warnings: Iterable[str] = (),
    archived_path: str | None = None,
) -> SourceDocument:
    return SourceDocument(
        id=source_id,
        title=path.name,
        kind=kind,
        text=text,
        captured_at=_captured_now(),
        primary_source_status="unverified",
        original_filename=path.name,
        archived_path=archived_path,
        content_sha256=_sha256(raw),
        byte_size=len(raw),
        extraction_method=extraction_method,
        extraction_confidence=extraction_confidence,
        extraction_warnings=list(warnings),
    )


def _archive_original(raw: bytes, path: Path, archive_dir: str | Path) -> str:
    digest = _sha256(raw)
    directory = Path(archive_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{digest}{path.suffix.lower()}"
    destination = directory / filename
    if destination.exists():
        if _sha256(destination.read_bytes()) != digest:
            raise ValueError(f"Source archive collision or integrity mismatch at {destination}")
    else:
        destination.write_bytes(raw)
        if _sha256(destination.read_bytes()) != digest:
            raise ValueError(f"Could not verify archived source copy at {destination}")
    return filename


def load_case(
    path: str | Path,
    *,
    enable_ocr: bool = False,
    ocr_language: str = "eng",
    preserve_sources_dir: str | Path | None = None,
) -> CaseRecord:
    """Load a case packet or a source file without changing the original.

    For a single source file, the original filename, SHA-256, byte size, capture
    time, extractor, extraction status, and any warnings are retained. Extracted
    passages remain unclassified and receive a source locator. A directory is
    recursively ingested as a multi-document source bundle; JSON files are not
    mistaken for evidence documents. The original files are never overwritten.
    If ``preserve_sources_dir`` is explicitly provided, hash-named, verified
    copies are written there and their relative archive names are stored.
    """
    input_path = Path(path)
    if input_path.is_dir():
        return load_source_directory(
            input_path,
            enable_ocr=enable_ocr,
            ocr_language=ocr_language,
            preserve_sources_dir=preserve_sources_dir,
        )
    if not input_path.is_file():
        raise ValueError(f"Input file does not exist or is not a file: {input_path}")
    suffix = input_path.suffix.lower()
    try:
        raw = input_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Could not read input file: {exc}") from exc

    if suffix == ".json":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not parse UTF-8 JSON case packet: {exc}") from exc
        return CaseRecord.from_dict(payload)

    if suffix not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported input type '{suffix or '(no extension)'}'. Supported: {allowed}.")

    archived_path = (
        _archive_original(raw, input_path, preserve_sources_dir)
        if preserve_sources_dir is not None else None
    )
    source_id = "source-1"
    if suffix == ".pdf":
        facts, text, method, confidence, warnings = _pdf_facts_and_text(
            input_path,
            raw,
            source_id,
            enable_ocr=enable_ocr,
            ocr_language=ocr_language,
        )
        document = _document_for_file(
            source_id=source_id,
            path=input_path,
            raw=raw,
            kind="pdf",
            text=text,
            extraction_method=method,
            extraction_confidence=confidence,
            warnings=warnings,
            archived_path=archived_path,
        )
    elif suffix == ".docx":
        blocks = _docx_blocks(input_path)
        facts = [Fact(
            id=f"fact-{index}",
            statement=statement,
            status="unclassified",
            source_id=source_id,
            locator=locator,
            extraction_method="python-docx",
            extraction_confidence="structured_docx_text_unreviewed",
        ) for index, (statement, locator) in enumerate(blocks, start=1)]
        text = "\n\n".join(f"[{locator}] {statement}" for statement, locator in blocks)
        document = _document_for_file(
            source_id=source_id,
            path=input_path,
            raw=raw,
            kind="docx",
            text=text,
            extraction_method="python-docx",
            extraction_confidence="structured_docx_text_unreviewed",
            warnings=(
                "DOCX pagination is layout-dependent; paragraph/table locators are used instead of page numbers.",
                "Headers, footers, comments, footnotes, and tracked-change interpretation may require separate review.",
            ),
            archived_path=archived_path,
        )
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Text/transcript input must be UTF-8; convert it explicitly rather than guessing an encoding.") from exc
        if not text.strip():
            raise ValueError("Input text is empty")

        if suffix == ".vtt":
            facts = _timed_subtitle_facts(text, source_id, kind="webvtt")
            kind = "webvtt_transcript"
            method = "webvtt-cue-parser"
            confidence = "native_timestamp_markers"
        elif suffix == ".srt":
            facts = _timed_subtitle_facts(text, source_id, kind="srt")
            kind = "srt_transcript"
            method = "srt-cue-parser"
            confidence = "native_timestamp_markers"
        else:
            timed_facts = _timestamped_markdown_facts(text, source_id)
            if timed_facts:
                facts = timed_facts
                kind = "timestamped_transcript"
                method = "timestamped-markdown-parser"
                confidence = "native_timestamp_markers"
            elif suffix in {".md", ".markdown"}:
                facts = _markdown_facts(text, source_id)
                kind = "markdown_source"
                method = "markdown-paragraph-parser"
                confidence = "markdown_text_unreviewed"
            else:
                facts = _paragraph_facts(text, source_id)
                kind = "text_or_markdown"
                method = "utf8-decoding"
                confidence = "utf8_text_decoded"
        if suffix in SUPPORTED_TRANSCRIPT_SUFFIXES and not facts:
            raise ValueError(f"No timestamped transcript cues were found in {input_path.name}")
        document_warnings: list[str] = []
        lower_filename = input_path.name.lower()
        if lower_filename.endswith(".pdf.md"):
            kind = "markdown_export_of_pdf"
            document_warnings.append(
                "Filename ends in .pdf.md: only the Markdown export was ingested; the original PDF is not present here. "
                "Locators refer to exported Markdown lines and any explicit page labels, not verified PDF pagination."
            )
        elif lower_filename.endswith(".docx.md"):
            kind = "markdown_export_of_docx"
            document_warnings.append(
                "Filename ends in .docx.md: only the Markdown export was ingested; verify it against the original DOCX for omissions and layout."
            )
        if "gemini notebook" in lower_filename:
            document_warnings.append(
                "Filename identifies Gemini Notebook material; treat it as derivative/AI-generated notes, not primary evidence or authority, and verify claims against underlying sources."
            )
        document = _document_for_file(
            source_id=source_id,
            path=input_path,
            raw=raw,
            kind=kind,
            text=text,
            extraction_method=method,
            extraction_confidence=confidence,
            warnings=document_warnings,
            archived_path=archived_path,
        )

    return CaseRecord(
        case_id=re.sub(r"[^a-zA-Z0-9_-]+", "-", input_path.stem).strip("-").lower() or "ingested-case",
        title=input_path.stem.replace("_", " ").replace("-", " ").strip() or input_path.name,
        documents=[document],
        facts=facts,
        narrative_text="",
    )


def load_source_directory(
    path: str | Path,
    *,
    enable_ocr: bool = False,
    ocr_language: str = "eng",
    preserve_sources_dir: str | Path | None = None,
) -> CaseRecord:
    """Load a folder of source files as one auditable, multi-document case packet.

    Supported source files are processed independently so each keeps its own
    filename, SHA-256, extraction method, warnings, and fact locators. Hidden
    files, generated caches, JSON packets, and unsupported binary types are not
    silently treated as factual material; skipped/unreadable files are reported.
    """
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"Source directory does not exist: {root}")
    root_resolved = root.resolve()
    archive_resolved: Path | None = None
    if preserve_sources_dir is not None:
        archive_resolved = Path(preserve_sources_dir).resolve()
        if archive_resolved == root_resolved or root_resolved in archive_resolved.parents:
            raise ValueError("The source archive directory must be outside the input source directory")

    candidates: list[Path] = []
    warnings: list[str] = []
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root)
        if any(part in _DIRECTORY_IGNORED_PARTS or part == "__MACOSX" for part in relative.parts):
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        if candidate.is_symlink():
            warnings.append(f"Skipped symbolic link `{relative.as_posix()}`; linked files/directories are not followed.")
            continue
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.lower()
        if suffix == ".json":
            warnings.append(
                f"Skipped `{relative.as_posix()}`: JSON files are case packets/manifests, not source documents for folder ingestion; pass a case JSON file directly."
            )
        elif suffix in SUPPORTED_SUFFIXES:
            candidates.append(candidate)
        else:
            warnings.append(f"Skipped `{relative.as_posix()}`: unsupported source-file extension `{suffix or '(none)'}`.")
    candidates.sort(key=lambda item: item.relative_to(root).as_posix().casefold())
    if not candidates:
        details = " " + " ".join(warnings[:5]) if warnings else ""
        raise ValueError(
            "No supported source documents were found in the directory. Supported types: "
            + ", ".join(sorted(SUPPORTED_SUFFIXES - {".json"}))
            + "."
            + details
        )

    documents: list[SourceDocument] = []
    facts: list[Fact] = []
    for candidate in candidates:
        relative = candidate.relative_to(root).as_posix()
        try:
            parsed = load_case(
                candidate,
                enable_ocr=enable_ocr,
                ocr_language=ocr_language,
                preserve_sources_dir=preserve_sources_dir,
            )
        except (OSError, ValueError) as exc:
            message = str(exc).replace(str(candidate), relative).replace(str(root), "<source directory>")
            warnings.append(f"Could not ingest `{relative}`: {type(exc).__name__}: {message}")
            continue
        if not parsed.documents:
            warnings.append(f"Could not ingest `{relative}`: parser returned no source-document record.")
            continue
        source_document = parsed.documents[0]
        source_id = f"source-{len(documents) + 1}"
        source_document.id = source_id
        source_document.title = relative
        source_document.original_filename = relative
        documents.append(source_document)
        for fact in parsed.facts:
            fact.id = f"fact-{len(facts) + 1}"
            fact.source_id = source_id
            facts.append(fact)
        warnings.extend(parsed.ingestion_warnings)

    if not documents:
        details = " " + " ".join(warnings[:8]) if warnings else ""
        raise ValueError("No source documents could be ingested." + details)

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", root.name).strip("-").lower() or "source-bundle"
    return CaseRecord(
        case_id=f"source-bundle-{slug}",
        title=f"Source bundle: {root.name or root_resolved.name}",
        documents=documents,
        facts=facts,
        narrative_text="",
        ingestion_warnings=warnings,
    )
