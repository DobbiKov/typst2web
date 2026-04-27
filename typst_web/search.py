"""
Build a per-page text search index from .typ source.

Strategy:
1. Parse the source into sections delimited by headings.
2. Use the heading→page map from `typst query` to assign each section
   a page number.
3. For sections between headings (or before the first heading), assign
   the page of the nearest following heading, falling back to page 1.

The result is a list like:
  [{"page": 1, "text": "Introduction This tool ..."},
   {"page": 2, "text": "Figures with CeTZ ..."},
   ...]
grouped by page.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


# ── Typst markup stripping ────────────────────────────────────────────────────

_BLOCK_COMMENT  = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT   = re.compile(r"//[^\n]*")
_CODE_BLOCK     = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE    = re.compile(r"`[^`]+`")
_MATH_BLOCK     = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_MATH_INLINE    = re.compile(r"\$[^$\n]+\$")
# Entire #keyword directive lines (set, let, show, import, include, align, etc.)
_DIRECTIVE_LINE = re.compile(r"^#(set|let|show|import|include|align|v|h|pagebreak|colbreak|figure|table|par|text|grid|columns|block|box|rect|circle|ellipse|line|polygon|image|bibliography|outline|footnote)\b[^\n]*", re.MULTILINE)
# #func(...) inline calls — including nested parens via repeated application
_FUNC_CALL      = re.compile(r"#[\w.][\w.]*\s*\([^)]*\)")
_HASH_WORD      = re.compile(r"#[\w.]+")  # remaining bare #word references
_MARKUP         = re.compile(r"[*_~\[\]]")
# Remove lines that look like pure code (no real words, just identifiers+colons)
_CODE_LINES     = re.compile(r"^[ \t]*[\w.]+\s*:.*$", re.MULTILINE)
_ANGLE_BRACKET  = re.compile(r"<[\w-]+>")  # <label> references
_EXTRA_SPACE    = re.compile(r"[ \t]+")
_BLANK_LINES    = re.compile(r"\n{3,}")

# heading pattern (= ... at start of line)
_HEADING_RE = re.compile(r"^(={1,6})\s+(.+)$", re.MULTILINE)


def _strip_markup(text: str) -> str:
    """Return plain text by stripping Typst markup."""
    text = _BLOCK_COMMENT.sub(" ", text)
    text = _LINE_COMMENT.sub(" ", text)
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _MATH_BLOCK.sub(" ", text)
    text = _MATH_INLINE.sub(" ", text)
    text = _DIRECTIVE_LINE.sub(" ", text)
    # Apply func-call stripping multiple times (handles one level of nesting)
    for _ in range(3):
        text = _FUNC_CALL.sub(" ", text)
    text = _HASH_WORD.sub(" ", text)
    text = _ANGLE_BRACKET.sub(" ", text)
    text = _MARKUP.sub("", text)
    text = _CODE_LINES.sub(" ", text)
    text = _EXTRA_SPACE.sub(" ", text)
    text = _BLANK_LINES.sub("\n", text)
    return text.strip()


# ── public API ────────────────────────────────────────────────────────────────

def build_search_index(
    typ_path: Path,
    heading_pages: list[dict],
    total_pages: int,
) -> list[dict]:
    """
    Return a list of {page: int, text: str} dicts, one per page,
    suitable for embedding as a JS search index.
    """
    source = Path(typ_path).read_text(encoding="utf-8")

    # Build heading → page lookup: heading text → page number
    h_page: dict[str, int] = {}
    for entry in heading_pages:
        h_page[entry["text"].strip().lower()] = entry["page"]

    # Split source into segments around headings
    segments: list[tuple[str | None, str]] = []  # (heading_text | None, body_text)
    prev_end = 0
    for m in _HEADING_RE.finditer(source):
        body_before = source[prev_end:m.start()]
        heading_text = m.group(2).strip()
        prev_end = m.end()
        if segments or body_before.strip():
            segments.append((None if not segments else segments[-1][0], body_before))
        segments.append((heading_text, ""))
    # remainder after last heading
    segments.append((segments[-1][0] if segments else None, source[prev_end:]))

    # Assign page numbers to segments
    # A segment's page = the page of the heading that opens the section it belongs to
    page_texts: dict[int, list[str]] = defaultdict(list)

    current_page = 1
    for i, (heading, body) in enumerate(segments):
        if heading is not None:
            p = h_page.get(heading.lower())
            if p is not None:
                current_page = p
            page_texts[current_page].append(heading)
        clean = _strip_markup(body)
        if clean:
            page_texts[current_page].append(clean)

    # Build final list, one entry per page (fill gaps)
    result: list[dict] = []
    for page_num in range(1, total_pages + 1):
        texts = page_texts.get(page_num, [])
        combined = " ".join(texts)
        # collapse whitespace
        combined = re.sub(r"\s+", " ", combined).strip()
        result.append({"page": page_num, "text": combined})

    return result
