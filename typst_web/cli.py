"""Command-line interface for typst-to-web."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .builder import build_html
from .compiler import compile_to_svgs, get_typst_version, query_heading_pages
from .parser import parse
from .search import build_search_index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="typst-web",
        description="Convert a Typst document into a self-contained HTML website.",
    )
    ap.add_argument("input", metavar="INPUT.typ", nargs="?", help="Typst source file")
    ap.add_argument(
        "-o", "--output",
        metavar="OUTPUT.html",
        help="Output HTML file (default: INPUT.html)",
    )
    ap.add_argument(
        "--root",
        metavar="DIR",
        help="Typst project root directory (for absolute imports)",
    )
    ap.add_argument(
        "--font-path",
        metavar="DIR",
        action="append",
        dest="font_paths",
        help="Additional font directories (repeatable)",
    )
    ap.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit",
    )
    args = ap.parse_args(argv)

    if args.version:
        from . import __version__
        print(f"typst-to-web {__version__}")
        try:
            print(get_typst_version())
        except RuntimeError as e:
            print(f"  warning: {e}")
        return 0

    if not args.input:
        ap.error("INPUT.typ is required")

    typ_path = Path(args.input)
    if not typ_path.exists():
        print(f"error: file not found: {typ_path}", file=sys.stderr)
        return 1
    if typ_path.suffix.lower() != ".typ":
        print(f"warning: expected a .typ file, got: {typ_path}", file=sys.stderr)

    out_path   = Path(args.output) if args.output else typ_path.with_suffix(".html")
    root       = Path(args.root) if args.root else None
    font_paths = [Path(p) for p in (args.font_paths or [])]

    t0 = time.perf_counter()

    print(f"[1/4] Compiling {typ_path.name} → SVG pages…", flush=True)
    try:
        svgs = compile_to_svgs(typ_path, root=root, font_paths=font_paths)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"      {len(svgs)} page(s) compiled.", flush=True)

    print("[2/4] Querying heading page numbers…", flush=True)
    heading_pages = query_heading_pages(typ_path, root=root, font_paths=font_paths)
    if heading_pages:
        print(f"      {len(heading_pages)} heading(s) located.", flush=True)
    else:
        print("      (could not locate headings; search will use heuristics)", flush=True)

    print("[3/4] Parsing document structure & building search index…", flush=True)
    structure = parse(typ_path)
    search_index = build_search_index(typ_path, heading_pages, len(svgs))
    if structure.meta.title:
        print(f"      title: {structure.meta.title}")
    if structure.headings:
        print(f"      {len(structure.headings)} heading(s) found.")

    print("[4/4] Building HTML…", flush=True)
    html = build_html(svgs, structure, search_index, source_name=typ_path.stem)

    out_path.write_text(html, encoding="utf-8")
    elapsed = time.perf_counter() - t0
    size_kb = out_path.stat().st_size / 1024
    print(f"\nDone in {elapsed:.1f}s  →  {out_path}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
