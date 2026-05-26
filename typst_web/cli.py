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
from .settings import resolve_settings


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


_GRID_OVERRIDE = (
    '// typst-to-web: grid HTML override\n'
    '#let grid(..args) = {\n'
    '  let pos = args.pos()\n'
    '  let named = args.named()\n'
    '  let columns = named.at("columns", default: 1)\n'
    '  let col-css = if type(columns) == int {\n'
    '    "repeat(" + str(columns) + ", 1fr)"\n'
    '  } else if type(columns) == array {\n'
    '    columns.map(c => repr(c)).join(" ")\n'
    '  } else {\n'
    '    repr(columns)\n'
    '  }\n'
    '  let gap = named.at("gutter", default: none)\n'
    '  let col-gap = named.at("column-gutter", default: none)\n'
    '  let row-gap = named.at("row-gutter", default: none)\n'
    '  let style = "display:grid;grid-template-columns:" + col-css + ";"\n'
    '  if gap != none { style = style + "gap:" + repr(gap) + ";" }\n'
    '  if col-gap != none { style = style + "column-gap:" + repr(col-gap) + ";" }\n'
    '  if row-gap != none { style = style + "row-gap:" + repr(row-gap) + ";" }\n'
    '  html.elem("div", attrs: ("class": "tw-grid", "style": style), {\n'
    '    for cell in pos {\n'
    '      html.elem("div", attrs: ("class": "tw-grid-cell"), cell)\n'
    '    }\n'
    '  })\n'
    '}\n'
)


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
        '    if type(k) == str and k.starts-with("_tw-") {\n'
        '      let lbl = it.element.supplement\n'
        '      let n = it.element.counter.display(it.element.numbering)\n'
        '      let anchor = str(it.target)\n'
        '      html.elem("a", attrs: ("href": "#" + anchor, "class": "thm-ref"), [#lbl #n])\n'
        '    } else { it }\n'
        '  } else { it }\n'
        '}\n'
    ) + env_overrides + "\n" + _GRID_OVERRIDE


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
    ap.add_argument("--title",    metavar="TEXT", default="")
    ap.add_argument("--subtitle", metavar="TEXT", default="")
    ap.add_argument("--author",   metavar="NAME", action="append", dest="authors")
    ap.add_argument("--date",     metavar="TEXT", default="")
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
    n_sketches = len(pp.sketches)
    sketch_info = f", {n_sketches} sketch(es)" if n_sketches else ""
    print(f"      {n_files} file(s), {n_inline} inline + {n_display} display math expressions{sketch_info}.", flush=True)

    # Inject HTML overrides for theorem environments (they are dropped by
    # Typst HTML export unless their function definitions are replaced).
    lang = _detect_language(typ_path)

    _HAS_OUTLINE_RE = re.compile(r'#(?:outline|toc)\s*\(')

    # Heading show rule: overrides any template's PDF-only heading renderer so
    # headings survive Typst HTML export as proper <h1>–<h6> elements.
    # We embed both a stable id (tw-sec-N-M) and the display number (data-num)
    # so postprocessor can inject the number span without needing the outline nav.
    _HEADING_OVERRIDE = (
        "\n// typst-to-web: heading HTML override\n"
        "#show heading: it => context {\n"
        "  let cnt = counter(heading).at(it.location())\n"
        '  let id = "tw-sec-" + cnt.map(str).join("-")\n'
        '  let num = cnt.map(str).join(".")\n'
        '  html.elem("h" + str(it.level), attrs: ("id": id, "data-num": num), it.body)\n'
        "}\n"
    )

    # Matches the end of a `#show: fn.with(...)` or `#show: fn` call, so we can
    # inject heading overrides immediately inside the show scope.
    _SHOW_RULE_RE = re.compile(r'^#show\s*:\s*\w+', re.MULTILINE)

    def _inject_heading_override(src: str) -> str:
        """
        Insert the heading show-rule override right after the FIRST top-level
        `#show: fn(...)` call (the template call, e.g. `#show: dobbikov.with(...)`).
        We scan from the start of the match and track paren depth to find where
        the full multi-line call ends, then insert after that line.
        If no such line is found, append at end.
        """
        m = _SHOW_RULE_RE.search(src)
        if not m:
            return src + _HEADING_OVERRIDE

        # Scan from the beginning of this #show: line tracking paren depth.
        # We end when depth returns to 0 AND we're on a newline boundary.
        i = m.start()
        depth = 0
        started = False
        while i < len(src):
            c = src[i]
            if c == '(':
                depth += 1
                started = True
            elif c == ')':
                depth -= 1
            elif c == '\n' and (not started or depth == 0):
                # End of line and parens are balanced — insert here
                i += 1  # include the newline itself
                break
            i += 1
        return src[:i] + _HEADING_OVERRIDE + src[i:]

    def _prepare_source(src: str) -> str:
        src = _inject_thm_overrides(src, lang)
        # Inject heading override right after the template #show: call so it is
        # the innermost show rule for headings, shadowing any PDF-only renderer.
        src = _inject_heading_override(src)
        # Ensure an #outline() exists so Typst emits <nav role="doc-toc">,
        # which gives us heading text + numbering metadata.
        # The nav is stripped from the body in build_web_page.
        if not _HAS_OUTLINE_RE.search(src):
            src += "\n// typst-to-web: synthetic outline for heading extraction\n#outline()\n"
        return src

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

    figure_svgs = compile_figures_to_svg(
        typ_path,
        extra_paths=list(pp.included.keys()),
        root=root,
        font_paths=font_paths,
    )
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

    settings = resolve_settings(
        typ_path,
        cli_title=args.title,
        cli_subtitle=args.subtitle,
        cli_authors=args.authors or [],
        cli_date=args.date,
        meta_title=meta.title,
        meta_authors=meta.authors,
        meta_date=meta.date,
    )

    html = build_web_page(
        typst_html,
        figure_svgs,
        math_svgs,
        pp.expressions,
        canvas_svgs=canvas_svgs,
        sketches=pp.sketches,
        title=settings.title or typ_path.stem,
        subtitle=settings.subtitle,
        authors=settings.authors,
        date=settings.date,
        source_name=typ_path.stem,
    )

    out_path.write_text(html, encoding="utf-8")
    elapsed = time.perf_counter() - t0
    size_kb = out_path.stat().st_size / 1024
    print(f"\nDone in {elapsed:.1f}s  →  {out_path}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
