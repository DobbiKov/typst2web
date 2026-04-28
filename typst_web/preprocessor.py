"""
Typst source preprocessor.

Scans markup-level math ($...$) and replaces each expression with a unique
placeholder comment <!-- MATH-N --> in the Typst source, while recording
the original Typst math body and display/inline flag for later SVG rendering.

Math inside {…} code blocks is left untouched (not valid markup context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MathExpr:
    index: int
    body: str        # raw Typst math body (without $ delimiters)
    display: bool    # True for display math ($ ... $), False for inline ($...$)
    label: str = ""  # optional label like "eq-gaussian"


@dataclass
class PreprocessResult:
    source: str                 # modified Typst source with placeholders
    expressions: list[MathExpr] = field(default_factory=list)


# Typst HTML-encodes raw <!-- --> comments, so we use html.elem with a data attribute.
# For inline: #html.elem("span", attrs: ("data-math": "N"), [])
# For display: #html.elem("div",  attrs: ("data-math": "N"), [])
def _placeholder(n: int, display: bool) -> str:
    tag = "div" if display else "span"
    return f'#html.elem("{tag}", attrs: ("data-math": "{n}"), [])'


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
    i = 0
    n = len(source)
    brace_depth = 0
    bracket_depth = 0

    while i < n:
        c = source[i]

        # ── skip line comments ────────────────────────────────────────────
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            end = source.find("\n", i)
            end = end if end != -1 else n
            out.append(source[i:end])
            i = end
            continue

        # ── skip block comments ───────────────────────────────────────────
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            end = (end + 2) if end != -1 else n
            out.append(source[i:end])
            i = end
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
            continue

        # ── context tracking ──────────────────────────────────────────────
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
            in_markup = (brace_depth == 0) or (bracket_depth > 0)
            if not in_markup:
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
                lm = re.match(r"<([\w-]+)>", rest[skip:])
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

    # Replace @label references to consumed display math labels with plain text
    result_src = "".join(out)
    label_map = {e.label: e.index for e in expressions if e.label}
    for lbl, idx in label_map.items():
        result_src = re.sub(
            r"@" + re.escape(lbl) + r"\b",
            f"(eq. {idx + 1})",
            result_src,
        )

    return PreprocessResult(source=result_src, expressions=expressions)


def _extract_display(source: str, start: int) -> tuple[str | None, int]:
    """Find closing $ preceded by whitespace. Returns (body, pos_after_$)."""
    n = len(source)
    i = start + 1
    while i < n:
        pos = source.find("$", i)
        if pos == -1:
            return None, start
        if pos > 0 and source[pos - 1] in (" ", "\n", "\t"):
            return source[start + 1:pos].strip(), pos + 1
        i = pos + 1
    return None, start


def _extract_inline(source: str, start: int) -> tuple[str | None, int]:
    """Find closing $ on same line. Returns (body, pos_after_$)."""
    n = len(source)
    i = start + 1
    while i < n:
        c = source[i]
        if c == "\n":
            return None, start
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
