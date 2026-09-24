"""Text extraction: HTML (stdlib), PDF (pypdf, optional), OCR hook (pytesseract, optional)."""
from __future__ import annotations

import io
import re
import urllib.parse
from html.parser import HTMLParser

from .util import clean_ws

_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "article", "table", "td", "th", "header", "footer"}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self._in_title = False
        self._href: str | None = None
        self._atext: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._atext = []
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._atext).strip()))
            self._href = None
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self._in_title:
            self.title += data
            return
        self.parts.append(data)
        if self._href is not None:
            self._atext.append(data.strip())


def parse_html(html: str, base_url: str = "") -> tuple[str, str, list[tuple[str, str]]]:
    """Return (title, text, [(absolute_url, anchor_text)])."""
    p = _Parser()
    try:
        p.feed(html)
    except Exception:
        pass
    text = clean_ws("".join(p.parts))
    links = []
    for href, label in p.links:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        links.append((urllib.parse.urljoin(base_url, href).split("#")[0], label))
    return clean_ws(p.title), text, links


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""
    if len(text.strip()) < 20:
        text = ocr_pdf(data) or text
    return clean_ws(text)


def ocr_pdf(data: bytes) -> str:
    """Scanned-PDF hook. Needs pytesseract + pdf2image + system tesseract/poppler."""
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        return ""
    try:
        return "\n\n".join(pytesseract.image_to_string(img) for img in convert_from_bytes(data))
    except Exception:
        return ""


def to_text(body: bytes, content_type: str, url: str = "") -> tuple[str, str, list]:
    """Dispatch on content type. Returns (title, text, links)."""
    ct = (content_type or "").lower()
    if "pdf" in ct or url.lower().split("?")[0].endswith(".pdf"):
        return "", pdf_to_text(body), []
    raw = body.decode("utf-8", errors="replace")
    if "html" in ct or re.search(r"<html|<body|<div", raw[:2000], re.I):
        return parse_html(raw, url)
    return "", clean_ws(raw), []
