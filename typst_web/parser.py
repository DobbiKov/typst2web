"""
Lightweight Typst source parser.

Extracts structural information (headings, title, author, labels, links)
without implementing a full Typst language parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Heading:
    level: int          # 1 = top, 2 = sub, ...
    text: str
    slug: str           # url-safe id


@dataclass
class DocMeta:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    date: str = ""
    description: str = ""


@dataclass
class TypstStructure:
    meta: DocMeta
    headings: list[Heading]
    labels: set[str]    # all #label("name") / <name> occurrences


# ── helpers ──────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = text.strip("-")
    return text or "section"


def _strip_markup(text: str) -> str:
    """Remove common Typst inline markup to get plain text."""
    # remove #func(...) calls (non-nested)
    text = re.sub(r"#\w+\([^)]*\)", "", text)
    # remove *bold*, _italic_, `code`
    text = re.sub(r"[*_`]", "", text)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_meta(source: str) -> DocMeta:
    meta = DocMeta()

    # #set document(title: "...", author: "..." | ("...", "..."), date: ...)
    doc_block = re.search(
        r"#set\s+document\s*\(([^)]*(?:\([^)]*\)[^)]*)*)\)", source, re.DOTALL
    )
    if doc_block:
        block = doc_block.group(1)

        m = re.search(r'title\s*:\s*"([^"]*)"', block)
        if m:
            meta.title = m.group(1)

        # author: "single" or ("a", "b")
        m = re.search(r'author\s*:\s*\(([^)]*)\)', block)
        if m:
            meta.authors = re.findall(r'"([^"]*)"', m.group(1))
        else:
            m = re.search(r'author\s*:\s*"([^"]*)"', block)
            if m:
                meta.authors = [m.group(1)]

        m = re.search(r'date\s*:\s*"([^"]*)"', block)
        if m:
            meta.date = m.group(1)

    # also look for // Title: ... style comments (less common)
    if not meta.title:
        m = re.search(r"^//\s*[Tt]itle:\s*(.+)$", source, re.MULTILINE)
        if m:
            meta.title = m.group(1).strip()

    return meta


def _is_in_code_block(source: str, pos: int) -> bool:
    """Very rough check: count backtick fences before position."""
    before = source[:pos]
    fences = before.count("```")
    return fences % 2 == 1


def _parse_headings(source: str) -> list[Heading]:
    headings: list[Heading] = []
    slug_counts: dict[str, int] = {}

    for m in re.finditer(r"^(={1,6})\s+(.+)$", source, re.MULTILINE):
        if _is_in_code_block(source, m.start()):
            continue
        level = len(m.group(1))
        raw_text = m.group(2).rstrip()
        text = _strip_markup(raw_text)
        base_slug = _slugify(text)
        count = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count}"
        headings.append(Heading(level=level, text=text, slug=slug))

    return headings


def _parse_labels(source: str) -> set[str]:
    labels: set[str] = set()
    # <label-name> syntax
    for m in re.finditer(r"<([\w-]+)>", source):
        labels.add(m.group(1))
    # #label("name") syntax
    for m in re.finditer(r'#label\s*\(\s*"([\w-]+)"\s*\)', source):
        labels.add(m.group(1))
    return labels


# ── public API ────────────────────────────────────────────────────────────────

def parse(typ_path: Path | str) -> TypstStructure:
    source = Path(typ_path).read_text(encoding="utf-8")
    return parse_source(source)


def parse_source(source: str) -> TypstStructure:
    return TypstStructure(
        meta=_parse_meta(source),
        headings=_parse_headings(source),
        labels=_parse_labels(source),
    )
