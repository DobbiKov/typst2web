"""
Typst source preprocessor.

Scans markup-level math ($...$) and canvas blocks (#canvas({...})) and
replaces each with a unique placeholder html.elem so Typst's HTML export
preserves a hook for SVG injection.

Math and canvas inside {…} code blocks is left untouched (not valid markup
context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MathExpr:
    index: int
    body: str        # raw Typst math body (without $ delimiters)
    display: bool    # True for display math ($ ... $), False for inline ($...$)
    label: str = ""  # optional label like "eq-gaussian"
    numbered: bool = False  # True if wrapped in #math.equation(numbering:...)


@dataclass
class CanvasExpr:
    index: int
    body: str              # full source of the #canvas({...}) call (with leading #)
    source_path: Path = field(default_factory=Path)  # .typ file that contains this canvas


@dataclass
class PreprocessResult:
    source: str                      # modified Typst source with placeholders
    expressions: list[MathExpr] = field(default_factory=list)
    canvases: list[CanvasExpr] = field(default_factory=list)
    # Included files that were preprocessed: original_path → modified_source
    included: dict[Path, str] = field(default_factory=dict)


# Typst HTML-encodes raw <!-- --> comments, so we use html.elem with a data attribute.
# For inline: #html.elem("span", attrs: ("data-math": "N"), [])
# For display: #html.elem("div",  attrs: ("data-math": "N"), [])
def _placeholder(n: int, display: bool) -> str:
    tag = "div" if display else "span"
    return f'#html.elem("{tag}", attrs: ("data-math": "{n}"), [])'


def _canvas_placeholder(n: int) -> str:
    return f'#html.elem("div", attrs: ("data-canvas": "{n}"), [])'


def preprocess(source: str) -> PreprocessResult:
    """
    Scan Typst source and replace math at markup level with placeholder comments.

    Context tracking:
      brace_depth > 0  →  inside {} code block  →  skip (not markup)
      bracket_depth    →  inside [] content block → process (markup mode)

    Math is replaced when: brace_depth == 0  or  bracket_depth > 0
    """
    out: list[str] = []
    expressions: list[MathExpr] = []
    canvases: list[CanvasExpr] = []
    i = 0
    n = len(source)
    brace_depth = 0      # depth inside {} code blocks
    bracket_depth = 0    # depth inside [] content blocks
    call_paren_depth = 0 # depth inside #func(...) argument parens
    next_paren_is_call = False  # True right after we see #identifier

    # in_markup: True when the current position is in Typst markup mode.
    # Rules:
    #   - {} code blocks always override to code (brace_depth > 0 → not markup)
    #   - Inside #func(...) args without any [] → code
    #   - Top level or inside [] content block (and no {} override) → markup
    def in_markup() -> bool:
        return brace_depth == 0 and (call_paren_depth == 0 or bracket_depth > 0)

    while i < n:
        c = source[i]

        # ── skip string literals (in any code context) ────────────────────
        # Must come before comment detection so "https://..." isn't treated as comment.
        if c == '"' and call_paren_depth > 0:
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == '"':
                    j += 1
                    break
                j += 1
            out.append(source[i:j])
            i = j
            continue

        # ── skip line comments ────────────────────────────────────────────
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            end = source.find("\n", i)
            end = end if end != -1 else n
            out.append(source[i:end])
            i = end
            next_paren_is_call = False
            continue

        # ── skip block comments ───────────────────────────────────────────
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            end = (end + 2) if end != -1 else n
            out.append(source[i:end])
            i = end
            next_paren_is_call = False
            continue

        # ── skip raw code blocks (``` ... ```) ────────────────────────────
        if source[i:i+3] == "```":
            end = source.find("```", i + 3)
            if end == -1:
                out.append(source[i:])
                i = n
            else:
                out.append(source[i:end + 3])
                i = end + 3
            next_paren_is_call = False
            continue

        # ── skip inline raw (`...`) ───────────────────────────────────────
        if c == "`":
            end = source.find("`", i + 1)
            if end == -1:
                out.append(source[i:])
                i = n
            else:
                out.append(source[i:end + 1])
                i = end + 1
            next_paren_is_call = False
            continue

        # ── detect #identifier to flag the next ( as a code-mode call ────
        if c == "#":
            # Scan past the identifier (may be dotted, e.g. math.equation)
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] in "._"):
                j += 1
            ident = source[i + 1:j]

            # ── intercept #align(...)[ #canvas({...}) ] ──────────────────
            # #align wraps content in a bracket block that Typst HTML export
            # drops entirely (align is ignored in HTML mode). Detect the
            # common pattern #align(...)[\n#canvas({...})\n] and replace the
            # entire #align block with a placeholder.
            if ident == "align" and in_markup() and brace_depth == 0:
                # Skip past #align(...) call args
                k = j
                while k < n and source[k] in " \t\n":
                    k += 1
                if k < n and source[k] == "(":
                    _align_args, args_end = _extract_balanced(source, k, "(", ")")
                    if _align_args is not None:
                        # Skip whitespace between ) and [
                        k2 = args_end
                        while k2 < n and source[k2] in " \t\n":
                            k2 += 1
                        if k2 < n and source[k2] == "[":
                            bracket_body, bracket_end = _extract_balanced(source, k2, "[", "]")
                            if bracket_body is not None:
                                # Check if the bracket body contains ONLY a canvas call
                                inner = bracket_body[1:-1].strip()  # strip leading [ and trailing ]
                                if inner.startswith("#canvas("):
                                    canvas_src = inner  # includes leading #
                                    # Extract just the #canvas(...) call
                                    kk = 0
                                    while kk < len(inner) and inner[kk] in " \t\n":
                                        kk += 1
                                    canvas_ident_end = kk + 1
                                    while canvas_ident_end < len(inner) and (inner[canvas_ident_end].isalnum() or inner[canvas_ident_end] in "._"):
                                        canvas_ident_end += 1
                                    # find the ( for the canvas call
                                    kk2 = canvas_ident_end
                                    while kk2 < len(inner) and inner[kk2] in " \t\n":
                                        kk2 += 1
                                    if kk2 < len(inner) and inner[kk2] == "(":
                                        cbody, cend = _extract_balanced(inner, kk2, "(", ")")
                                        if cbody is not None:
                                            # inner[kk-1] is the '#', inner[kk:cend] is canvas(...)
                                            canvas_full = inner[kk:cend]  # from # through end of (...)
                                            idx = len(canvases)
                                            canvases.append(CanvasExpr(idx, canvas_full))
                                            out.append(_canvas_placeholder(idx))
                                            i = bracket_end
                                            next_paren_is_call = False
                                            continue

            # ── intercept #math.equation(numbering:..., block:true, $...$) ──
            # Typst HTML export silently drops math.equation content when
            # numbering is set.  We detect this pattern, extract the body,
            # register it as a numbered display math expression, and emit our
            # own placeholder so postprocessor can inject SVG + equation number.
            if ident == "math.equation" and in_markup():
                k = j
                while k < n and source[k] in " \t\n":
                    k += 1
                if k < n and source[k] == "(":
                    args_body, args_end = _extract_balanced(source, k, "(", ")")
                    if args_body is not None and "numbering" in args_body:
                        inner = args_body[1:-1]  # strip outer ( )
                        # Find the display-math body: $ \n ... \n $
                        dm = re.search(r'\$\s+([\s\S]*?)\s+\$', inner)
                        if dm:
                            math_body = dm.group(1)
                            # Consume optional <label> after )
                            rest = source[args_end:]
                            skip = 0
                            while skip < len(rest) and rest[skip] in " \t":
                                skip += 1
                            lm = re.match(r"<([\w:-]+)>", rest[skip:])
                            label = ""
                            label_end = args_end
                            if lm:
                                label = lm.group(1)
                                label_end = args_end + skip + lm.end()
                            idx = len(expressions)
                            expressions.append(MathExpr(idx, math_body, display=True,
                                                        label=label, numbered=True))
                            out.append(_placeholder(idx, display=True))
                            i = label_end
                            next_paren_is_call = False
                            continue

            # ── intercept #canvas({...}) in markup mode ───────────────────
            # canvas({...}) produces no output in Typst HTML export.
            # Replace the whole call with a placeholder div so we can inject
            # an SVG later.
            if (ident == "canvas" or ident.endswith(".canvas")) and in_markup():
                # skip whitespace between identifier and (
                k = j
                while k < n and source[k] in " \t\n":
                    k += 1
                if k < n and source[k] == "(":
                    canvas_start = i  # position of leading #
                    body, end_pos = _extract_balanced(source, k, "(", ")")
                    if body is not None:
                        idx = len(canvases)
                        canvases.append(CanvasExpr(idx, source[canvas_start:end_pos]))
                        out.append(_canvas_placeholder(idx))
                        i = end_pos
                        next_paren_is_call = False
                        continue

            out.append(c)
            out.append(ident)
            i = j
            # Skip optional whitespace before (
            k = i
            while k < n and source[k] in " \t":
                k += 1
            if k < n and source[k] == "(":
                next_paren_is_call = True
            continue

        # ── skip string literals in code context (prevent "(1)" from affecting depth)
        # ── context tracking ──────────────────────────────────────────────
        if c == "(":
            if next_paren_is_call or call_paren_depth > 0:
                call_paren_depth += 1
            next_paren_is_call = False
            out.append(c); i += 1; continue
        if c == ")":
            if call_paren_depth > 0:
                call_paren_depth -= 1
            out.append(c); i += 1; continue

        next_paren_is_call = False

        if c == "{":
            brace_depth += 1
            out.append(c); i += 1; continue
        if c == "}":
            brace_depth = max(0, brace_depth - 1)
            out.append(c); i += 1; continue
        if c == "[":
            bracket_depth += 1
            out.append(c); i += 1; continue
        if c == "]":
            bracket_depth = max(0, bracket_depth - 1)
            out.append(c); i += 1; continue

        # ── math ──────────────────────────────────────────────────────────
        if c == "$":
            if not in_markup():
                out.append(c); i += 1; continue

            next_c = source[i + 1] if i + 1 < n else ""

            if next_c in (" ", "\n", "\t"):
                # Display math
                body, end_pos = _extract_display(source, i)
                if body is None:
                    out.append(c); i += 1; continue

                # Consume optional trailing label <eq-foo>
                rest = source[end_pos:]
                label = ""
                skip = 0
                while skip < len(rest) and rest[skip] in (" ", "\t"):
                    skip += 1
                lm = re.match(r"<([\w:-]+)>", rest[skip:])
                if lm:
                    label = lm.group(1)
                    end_pos += skip + lm.end()

                idx = len(expressions)
                expressions.append(MathExpr(idx, body, display=True, label=label))
                out.append(_placeholder(idx, display=True))
                i = end_pos

            else:
                # Inline math
                body, end_pos = _extract_inline(source, i)
                if body is None:
                    out.append(c); i += 1; continue

                idx = len(expressions)
                expressions.append(MathExpr(idx, body, display=False))
                out.append(_placeholder(idx, display=False))
                i = end_pos
            continue

        out.append(c)
        i += 1

    # Replace @label references to consumed display math labels with plain text.
    # Numbered equations (@eq:foo) get their equation counter, others get index.
    result_src = "".join(out)
    # Build equation counter (1-based) for numbered expressions, in index order
    eq_counter: dict[str, int] = {}
    num = 0
    for e in sorted(expressions, key=lambda e: e.index):
        if e.label and e.numbered:
            num += 1
            eq_counter[e.label] = num
    label_map = {e.label: e.index for e in expressions if e.label}
    for lbl, idx in label_map.items():
        if lbl in eq_counter:
            n = eq_counter[lbl]
            ref_text = f'#html.elem("a", attrs: ("href": "#math-{lbl}", "class": "eq-ref"), [({n})])'
        else:
            ref_text = f"(eq. {idx + 1})"
        result_src = re.sub(
            r"@" + re.escape(lbl) + r"(?![\w:-])",
            ref_text,
            result_src,
        )

    return PreprocessResult(source=result_src, expressions=expressions, canvases=canvases)


# ── Recursive entry point ─────────────────────────────────────────────────────

_INCLUDE_RE = re.compile(r'(#?)include\s+"([^"]+)"')


def preprocess_file(
    typ_path: Path,
    source_transform=None,
) -> PreprocessResult:
    """
    Preprocess a .typ file and all its #include'd files recursively.

    Returns a PreprocessResult whose `included` dict maps each included
    file's resolved path to its preprocessed source, sharing a single
    expressions list (so placeholder indices are globally unique).

    The caller is responsible for writing the preprocessed sources to disk
    and cleaning them up afterward.

    `source_transform`, if provided, is called as `source_transform(source)`
    on each file's raw text before math extraction, allowing callers to
    rewrite source patterns (e.g. text-mode math.op calls) before the
    preprocessor sees them.
    """
    expressions: list[MathExpr] = []
    canvases: list[CanvasExpr] = []
    included: dict[Path, str] = {}
    _preprocess_recursive(
        typ_path.resolve(), expressions, canvases, included, set(),
        source_transform=source_transform,
    )
    # The main file's preprocessed source is stored in included[typ_path]
    main_source = included.pop(typ_path.resolve())
    return PreprocessResult(
        source=main_source, expressions=expressions, canvases=canvases, included=included
    )


def _preprocess_recursive(
    path: Path,
    expressions: list[MathExpr],
    canvases: list[CanvasExpr],
    included: dict[Path, str],
    seen: set[Path],
    *,
    source_transform=None,
) -> None:
    """Depth-first preprocessing of path and all its #include'd children."""
    if path in seen:
        return
    seen.add(path)

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return  # file missing or unreadable — leave as-is, Typst will error

    if source_transform is not None:
        source = source_transform(source)

    # Preprocess this file's math + canvases, sharing the global lists
    pp = _preprocess_with_shared_lists(source, expressions, canvases, path)

    # Now recurse into #include'd files found in the original source
    # and rewrite include paths to point at the temp preprocessed versions
    def _patch_include(m: re.Match) -> str:
        prefix = m.group(1)  # "#" or ""
        rel = m.group(2)
        child_path = (path.parent / rel).resolve()
        _preprocess_recursive(
            child_path, expressions, canvases, included, seen,
            source_transform=source_transform,
        )
        if child_path in included:
            # The temp file sits next to the original child file.
            # Rebuild a relative path from the *current* file's dir to the temp file.
            temp_path = child_path.parent / f"_typst_web_pp_{child_path.name}"
            rel = temp_path.relative_to(path.parent)
            return f'{prefix}include "{rel.as_posix()}"'
        return m.group(0)  # couldn't preprocess, keep original path

    patched = _INCLUDE_RE.sub(_patch_include, pp)
    included[path] = patched


def _preprocess_with_shared_lists(
    source: str,
    expressions: list[MathExpr],
    canvases: list[CanvasExpr],
    source_path: Path | None = None,
) -> str:
    """
    Like preprocess() but appends to existing shared expression and canvas lists
    so indices are globally unique across all files.
    """
    pp = preprocess(source)

    # ── Re-index math expressions ─────────────────────────────────────────
    math_offset = len(expressions)
    adjusted_source = pp.source
    for expr in reversed(pp.expressions):
        old_idx = expr.index
        new_idx = old_idx + math_offset
        tag = "div" if expr.display else "span"
        old = f'#html.elem("{tag}", attrs: ("data-math": "{old_idx}"), [])'
        new = f'#html.elem("{tag}", attrs: ("data-math": "{new_idx}"), [])'
        adjusted_source = adjusted_source.replace(old, new, 1)
        expr.index = new_idx
    expressions.extend(pp.expressions)

    # ── Re-index canvas expressions ───────────────────────────────────────
    canvas_offset = len(canvases)
    for cv in reversed(pp.canvases):
        old_idx = cv.index
        new_idx = old_idx + canvas_offset
        old = f'#html.elem("div", attrs: ("data-canvas": "{old_idx}"), [])'
        new = f'#html.elem("div", attrs: ("data-canvas": "{new_idx}"), [])'
        adjusted_source = adjusted_source.replace(old, new, 1)
        cv.index = new_idx
        # Annotate with the source file path so the renderer can find preamble
        if source_path is not None:
            cv.source_path = source_path  # type: ignore[attr-defined]
    canvases.extend(pp.canvases)

    return adjusted_source


def _extract_display(source: str, start: int) -> tuple[str | None, int]:
    """Find closing $ preceded by whitespace.

    A $ is the display-math closing only when it is preceded by whitespace AND
    NOT immediately followed by a non-whitespace character (which would indicate
    an inline-math opening like '$expr$' rather than the end of a block).
    Returns (body, pos_after_$).
    """
    n = len(source)
    i = start + 1
    while i < n:
        pos = source.find("$", i)
        if pos == -1:
            return None, start
        after = source[pos + 1] if pos + 1 < n else ""
        if (pos > 0 and source[pos - 1] in (" ", "\n", "\t")
                and after in (" ", "\n", "\t", "", ",", ".", ")", "]", "}")):
            return source[start + 1:pos].strip(), pos + 1
        i = pos + 1
    return None, start


def _extract_inline(source: str, start: int) -> tuple[str | None, int]:
    """Find closing $ (may span lines). Returns (body, pos_after_$)."""
    n = len(source)
    i = start + 1
    while i < n:
        c = source[i]
        if c == "$":
            body = source[start + 1:i]
            if not body or body[0] in (" ", "\t"):
                return None, start
            return body, i + 1
        if c == "\\":
            i += 2
            continue
        i += 1
    return None, start


def _extract_balanced(
    source: str,
    start: int,
    open_ch: str,
    close_ch: str,
) -> tuple[str | None, int]:
    """
    Find the matching close_ch for open_ch starting at source[start].
    Returns (body_including_delimiters, pos_after_close_ch).
    Handles nested pairs and skips over string literals ("...") and line comments.
    """
    n = len(source)
    if start >= n or source[start] != open_ch:
        return None, start
    depth = 0
    i = start
    while i < n:
        c = source[i]
        # Skip line comments
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            end = source.find("\n", i)
            i = end if end != -1 else n
            continue
        # Skip block comments
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            i = (end + 2) if end != -1 else n
            continue
        # Skip string literals
        if c == '"':
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == '"':
                    j += 1
                    break
                j += 1
            i = j
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return source[start:i + 1], i + 1
        i += 1
    return None, start
