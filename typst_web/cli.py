"""Command-line interface for typst-to-web."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from .compiler import compile_to_html, get_typst_version
from .figure_renderer import compile_canvases_to_svgs, compile_figures_to_svg
from .math_renderer import compile_math_to_svgs
from .parser import parse
from .postprocessor import build_web_page
from .preprocessor import preprocess_file


_IMPORT_OR_LET_RE = re.compile(r"^(#import\b|#let\b)")


def _extract_preamble(typ_path: Path) -> str:
    """
    Collect #import and #let lines from the main .typ file so that custom math
    operators (e.g. #let Var = math.op("Var")) are available when compiling
    math expressions in isolation.  #set/#show lines are excluded because they
    often reference template functions that aren't relevant for standalone math.
    """
    try:
        lines = typ_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    preamble_lines: list[str] = []
    for line in lines[:300]:
        if _IMPORT_OR_LET_RE.match(line.lstrip()):
            preamble_lines.append(line)
    return "\n".join(preamble_lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="typst-web",
        description="Convert a Typst document into a MyST-style website.",
    )
    ap.add_argument("input", metavar="INPUT.typ", nargs="?")
    ap.add_argument("-o", "--output", metavar="OUTPUT.html")
    ap.add_argument("--root", metavar="DIR")
    ap.add_argument("--font-path", metavar="DIR", action="append", dest="font_paths")
    ap.add_argument("--version", action="store_true")
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

    typ_path   = Path(args.input)
    if not typ_path.exists():
        print(f"error: file not found: {typ_path}", file=sys.stderr)
        return 1

    out_path   = Path(args.output) if args.output else typ_path.with_suffix(".html")
    root       = Path(args.root) if args.root else None
    font_paths = [Path(p) for p in (args.font_paths or [])]

    t0 = time.perf_counter()

    # ── 1. Preprocess: extract math from main + all #include'd files ─────────
    print(f"[1/4] Preprocessing {typ_path.name}…", flush=True)
    pp = preprocess_file(typ_path)
    n_inline  = sum(1 for e in pp.expressions if not e.display)
    n_display = sum(1 for e in pp.expressions if e.display)
    n_files   = 1 + len(pp.included)
    print(f"      {n_files} file(s), {n_inline} inline + {n_display} display math expressions.", flush=True)

    # Write all preprocessed sources next to their originals so relative
    # imports and includes resolve correctly during typst compilation.
    temp_files: list[Path] = []
    pp_path = typ_path.parent / f"_typst_web_pp_{typ_path.name}"
    try:
        pp_path.write_text(pp.source, encoding="utf-8")
        temp_files.append(pp_path)

        for orig_path, src in pp.included.items():
            tp = orig_path.parent / f"_typst_web_pp_{orig_path.name}"
            tp.write_text(src, encoding="utf-8")
            temp_files.append(tp)

        # ── 2. Compile HTML ───────────────────────────────────────────────────
        print("[2/4] Compiling to HTML…", flush=True)
        try:
            typst_html = compile_to_html(pp_path, root=root, font_paths=font_paths)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    finally:
        for tp in temp_files:
            tp.unlink(missing_ok=True)

    # ── 3. Render math + figures to SVG ──────────────────────────────────────
    print("[3/4] Rendering math and figures to SVG…", flush=True)
    math_svgs: list[str] = []
    if pp.expressions:
        exprs = [(e.body, e.display) for e in pp.expressions]
        preamble = _extract_preamble(typ_path)
        math_svgs = compile_math_to_svgs(
            exprs,
            typ_dir=typ_path.parent,
            font_paths=font_paths,
            preamble=preamble,
        )
        print(f"      {sum(1 for s in math_svgs if s)} math SVGs rendered.", flush=True)

    figure_svgs = compile_figures_to_svg(typ_path, root=root, font_paths=font_paths)
    if figure_svgs:
        print(f"      {len(figure_svgs)} figure(s) compiled.", flush=True)

    canvas_svgs: list[str] = []
    if pp.canvases:
        canvas_svgs = compile_canvases_to_svgs(pp.canvases, typ_dir=typ_path.parent, root=root, font_paths=font_paths)
        n_rendered = sum(1 for s in canvas_svgs if s)
        print(f"      {n_rendered}/{len(pp.canvases)} canvas figure(s) compiled.", flush=True)

    # ── 4. Assemble web page ──────────────────────────────────────────────────
    print("[4/4] Assembling web page…", flush=True)
    structure = parse(typ_path)
    meta = structure.meta

    html = build_web_page(
        typst_html,
        figure_svgs,
        math_svgs,
        pp.expressions,
        canvas_svgs=canvas_svgs,
        title=meta.title or typ_path.stem,
        authors=meta.authors,
        date=meta.date,
        source_name=typ_path.stem,
    )

    out_path.write_text(html, encoding="utf-8")
    elapsed = time.perf_counter() - t0
    size_kb = out_path.stat().st_size / 1024
    print(f"\nDone in {elapsed:.1f}s  →  {out_path}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
