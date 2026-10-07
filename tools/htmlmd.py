"""Lightweight HTML -> Markdown converter + helpers.

Stdlib only. Written for Google Takeout "My Activity" exports and saved
chat pages, where the important structures are headings, paragraphs,
lists, tables, links, emphasis and code.
"""
from __future__ import annotations

import html as _html
import re

_TAG = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)>")
_BLOCK = {
    "p", "div", "section", "article", "header", "footer", "tr", "table",
    "ul", "ol", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
}


def _attrs(raw: str) -> dict:
    out = {}
    for m in re.finditer(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"', raw or ""):
        out[m.group(1).lower()] = _html.unescape(m.group(2))
    for m in re.finditer(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*'([^']*)'", raw or ""):
        out.setdefault(m.group(1).lower(), _html.unescape(m.group(2)))
    return out


def html_to_markdown(fragment: str, *, keep_links: bool = True) -> str:
    """Convert an HTML fragment to compact Markdown."""
    if not fragment:
        return ""
    s = fragment
    # Drop script/style/comments entirely.
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    # Images -> alt text marker.
    s = re.sub(
        r"(?is)<img[^>]*>",
        lambda m: f"![{_attrs(m.group(0)).get('alt', 'image')}]",
        s,
    )
    # Inline code / strong / em.
    s = re.sub(r"(?is)<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", s)
    s = re.sub(r"(?is)<(i|em)[^>]*>(.*?)</\1>", r"*\2*", s)
    s = re.sub(r"(?is)<code[^>]*>(.*?)</code>", r"`\1`", s)
    # Links.
    if keep_links:
        s = re.sub(
            r"(?is)<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
            lambda m: f"[{re.sub(r'<[^>]+>', '', m.group(2)).strip() or m.group(1)}]({m.group(1)})",
            s,
        )
    else:
        s = re.sub(r"(?is)<a[^>]*>(.*?)</a>", r"\1", s)
    # Headings.
    for level in range(1, 7):
        s = re.sub(
            rf"(?is)<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, lv=level: "\n\n" + "#" * lv + " " + m.group(1).strip() + "\n\n",
            s,
        )
    # Lists.
    s = re.sub(r"(?is)<li[^>]*>(.*?)</li>", lambda m: "\n- " + m.group(1).strip(), s)
    s = re.sub(r"(?is)</?(ul|ol)[^>]*>", "\n", s)
    # Tables -> pipe rows (cheap but readable).
    def _table(m: re.Match) -> str:
        body = m.group(0)
        rows = []
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", body):
            cells = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", tr)
            ]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        return "\n\n" + "\n".join(rows) + "\n\n" if rows else " "

    s = re.sub(r"(?is)<table[^>]*>.*?</table>", _table, s)
    # Line breaks and block boundaries.
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</?(p|div|tr|section|article)[^>]*>", "\n\n", s)
    # Strip whatever is left.
    s = _TAG.sub(" ", s)
    s = _html.unescape(s)
    s = s.replace("\u202f", " ").replace("\u00a0", " ")
    s = re.sub(r"[ \t\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def text_of(fragment: str) -> str:
    """Plain text, single-spaced."""
    return re.sub(r"\s+", " ", html_to_markdown(fragment, keep_links=False)).strip()


def find_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\)\]\>\"',}]+", text or "")
    seen, out = set(), []
    for u in urls:
        u = u.rstrip(".,;:")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
