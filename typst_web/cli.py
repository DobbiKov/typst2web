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

# ── Theorem environment HTML overrides ───────────────────────────────────────

# Maps language code → {env-name → display label}
_THM_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "defn": "Definition", "thm": "Theorem", "lem": "Lemma",
        "prop": "Proposition", "cor": "Corollary", "rmk": "Remark",
        "ex": "Example", "proof": "Proof", "soln": "Solution",
        "claim": "Claim", "notation": "Notation", "conj": "Conjecture",
        "insight": "Insight", "exer": "Exercise", "exerstar": "Exercise (*)",
        "prob": "Problem", "ques": "Question", "fact": "Fact",
        "rmnd": "Reminder", "todo": "TODO",
    },
    "fr": {
        "defn": "D\u00e9finition", "thm": "Th\u00e9or\u00e8me", "lem": "Lemme",
        "prop": "Proposition", "cor": "Corollaire", "rmk": "Remarque",
        "ex": "Exemple", "proof": "Preuve", "soln": "Solution",
        "claim": "Assertion", "notation": "Notation", "conj": "Conjecture",
        "insight": "Intuition", "exer": "Exercice", "exerstar": "Exercice (*)",
        "prob": "Probl\u00e8me", "ques": "Question", "fact": "Fait",
        "rmnd": "Rappel", "todo": "TODO",
    },
    "ua": {
        "defn": "\u041e\u0437\u043d\u0430\u0447\u0435\u043d\u043d\u044f",
        "thm": "\u0422\u0435\u043e\u0440\u0435\u043c\u0430",
        "lem": "\u041b\u0435\u043c\u0430",
        "prop": "\u041f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044f",
        "cor": "\u041d\u0430\u0441\u043b\u0456\u0434\u043e\u043a",
        "rmk": "\u0417\u0430\u0443\u0432\u0430\u0436\u0435\u043d\u043d\u044f",
        "ex": "\u041f\u0440\u0438\u043a\u043b\u0430\u0434",
        "proof": "\u0414\u043e\u0432\u0435\u0434\u0435\u043d\u043d\u044f",
        "soln": "\u0420\u043e\u0437\u0432\u2019\u044f\u0437\u043e\u043a",
        "claim": "\u0422\u0432\u0435\u0440\u0434\u0436\u0435\u043d\u043d\u044f",
        "notation": "\u041f\u043e\u0437\u043d\u0430\u0447\u0435\u043d\u043d\u044f",
        "conj": "\u0413\u0456\u043f\u043e\u0442\u0435\u0437\u0430",
        "insight": "\u0406\u043d\u0442\u0443\u0456\u0446\u0456\u044f",
        "exer": "\u0412\u043f\u0440\u0430\u0432\u0430",
        "exerstar": "\u0412\u043f\u0440\u0430\u0432\u0430 (*)",
        "prob": "\u0417\u0430\u0434\u0430\u0447\u0430",
        "ques": "\u041f\u0438\u0442\u0430\u043d\u043d\u044f",
        "fact": "\u0424\u0430\u043a\u0442",
        "rmnd": "\u041d\u0430\u0433\u0430\u0434\u0443\u0432\u0430\u043d\u043d\u044f",
        "todo": "TODO",
    },
}

_LANG_RE = re.compile(r'language:\s*"([a-z]{2})"')


def _detect_language(typ_path: Path) -> str:
    """Detect document language from dobbikov template call."""
    try:
        text = typ_path.read_text(encoding="utf-8")
        m = _LANG_RE.search(text)
        return m.group(1) if m else "en"
    except OSError:
        return "en"


def _build_thm_overrides(lang: str) -> str:
    """
    Build Typst source that overrides all known theorem environments to emit
    html.elem divs so their content survives Typst HTML export.
    """
    labels = _THM_LABELS.get(lang, _THM_LABELS["en"])

    env_overrides = "\n".join(
        f'#let {kind}(..args) = _tw-env("{kind}", "{label}", ..args)'
        for kind, label in labels.items()
    )
    return (
        '// typst-to-web: theorem environment HTML overrides\n'
        '#let _tw-env(kind, lbl, ..args) = {\n'
        '  let pos-args = args.pos()\n'
        '  let named-args = args.named()\n'
        '  let body = pos-args.last()\n'
        '  let opt-name = if pos-args.len() > 1 {\n'
        '    pos-args.first()\n'
        '  } else if "info" in named-args {\n'
        '    named-args.at("info")\n'
        '  } else { none }\n'
        '  // figure() auto-increments the per-kind counter and IS labelable\n'
        '  figure(\n'
        '    html.elem("div", attrs: ("class": "typst-thm typst-" + kind), [\n'
        '      #html.elem("span", attrs: ("class": "thm-head"), strong([\n'
        '        #lbl #context counter(figure.where(kind: "_tw-" + kind)).display()'
        '#if opt-name != none [ (#opt-name)].\n'
        '      ]))\n'
        '      #linebreak()\n'
        '      #body\n'
        '    ]),\n'
        '    kind: "_tw-" + kind,\n'
        '    supplement: lbl,\n'
        '    outlined: false,\n'
        '    caption: none,\n'
        '  )\n'
        '}\n'
        '// Render @label references to theorem environments as linked "Lbl N"\n'
        '#show ref: it => {\n'
        '  if it.element != none and it.element.func() == figure {\n'
        '    let k = it.element.kind\n'
        '    if k.starts-with("_tw-") {\n'
        '      let lbl = it.element.supplement\n'
        '      let n = it.element.counter.display(it.element.numbering)\n'
        '      html.elem("span", attrs: ("class": "thm-ref"), [#lbl #n])\n'
        '    } else { it }\n'
        '  } else { it }\n'
        '}\n'
    ) + env_overrides + "\n"


def _inject_thm_overrides(source: str, lang: str) -> str:
    """
    Inject theorem override definitions into preprocessed Typst source,
    right after the last top-level #import line so they shadow the imports.
    """
    override_block = "\n" + _build_thm_overrides(lang) + "\n"
    lines = source.splitlines(keepends=True)
    # Inject after the FIRST top-level import block (consecutive #import lines
    # at the start of the file).  Do NOT use the last import, which may be a
    # mid-document `#import "figures/..."` that comes after content.
    first_import_idx = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*#import\b", line):
            if first_import_idx == -1:
                first_import_idx = i
        elif first_import_idx != -1 and line.strip() and not line.strip().startswith("//"):
            # First non-blank, non-comment line after imports → stop scanning
            break
    # Find the end of the initial import block
    last_top_import = first_import_idx
    if first_import_idx >= 0:
        for i in range(first_import_idx, len(lines)):
            s = lines[i].strip()
            if re.match(r"^\s*#import\b", lines[i]) or not s or s.startswith("//"):
                if re.match(r"^\s*#import\b", lines[i]):
                    last_top_import = i
            else:
                break
    insert_at = last_top_import + 1 if last_top_import >= 0 else 0
    lines.insert(insert_at, override_block)
    return "".join(lines)


_MATHOP_DEF_RE = re.compile(
    r'#let\s+(\w+)\s*=\s*math\.op\(\s*"([^"]+)"'
)


def _collect_mathop_names(sources: list[str]) -> dict[str, str]:
    """
    Scan source texts for `#let NAME = math.op("TEXT" ...)` definitions.
    Returns {NAME: TEXT}.
    """
    result: dict[str, str] = {}
    for src in sources:
        for m in _MATHOP_DEF_RE.finditer(src):
            result[m.group(1)] = m.group(2)
    return result


def _rewrite_mathop_textmode(source: str, mathop_names: dict[str, str]) -> str:
    """
    Rewrite `#NAME ($expr$)` text-mode calls (with optional space before `(`)
    to `$NAME(expr)$` so Typst HTML export doesn't silently drop the operator
    name.  Only handles the common pattern where the argument is a single
    inline math expression.

    Also rewrites bare `#NAME` (used as content value, no call) to `$NAME$`.
    """
    for name in mathop_names:
        # #NAME ($expr$) → $NAME(expr)$   (space before ( is the usual bug)
        source = re.sub(
            rf'#(?:{re.escape(name)})\s*\(\$([^$]*)\$\)',
            lambda m, n=name: f'${n}({m.group(1)})$',
            source,
        )
        # Bare #NAME not followed by ( → $NAME$
        source = re.sub(
            rf'#(?:{re.escape(name)})(?!\s*\()',
            f'${name}$',
            source,
        )
    return source


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

    # Collect math.op definitions from raw .typ files (including #import'ed
    # ones like preamble.typ) so we can rewrite text-mode calls like
    # `#Bern ($theta$)` → `$Bern(theta)$` BEFORE math extraction.
    raw_sources: list[str] = []
    for p in typ_path.parent.glob("*.typ"):
        try:
            raw_sources.append(p.read_text(encoding="utf-8"))
        except OSError:
            pass
    mathop_names = _collect_mathop_names(raw_sources)

    def _source_transform(src: str) -> str:
        return _rewrite_mathop_textmode(src, mathop_names)

    pp = preprocess_file(typ_path, source_transform=_source_transform if mathop_names else None)
    n_inline  = sum(1 for e in pp.expressions if not e.display)
    n_display = sum(1 for e in pp.expressions if e.display)
    n_files   = 1 + len(pp.included)
    print(f"      {n_files} file(s), {n_inline} inline + {n_display} display math expressions.", flush=True)

    # Inject HTML overrides for theorem environments (they are dropped by
    # Typst HTML export unless their function definitions are replaced).
    lang = _detect_language(typ_path)

    def _prepare_source(src: str) -> str:
        return _inject_thm_overrides(src, lang)

    main_source = _prepare_source(pp.source)

    # Write all preprocessed sources next to their originals so relative
    # imports and includes resolve correctly during typst compilation.
    temp_files: list[Path] = []
    pp_path = typ_path.parent / f"_typst_web_pp_{typ_path.name}"
    try:
        pp_path.write_text(main_source, encoding="utf-8")
        temp_files.append(pp_path)

        for orig_path, src in pp.included.items():
            tp = orig_path.parent / f"_typst_web_pp_{orig_path.name}"
            tp.write_text(_prepare_source(src), encoding="utf-8")
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
