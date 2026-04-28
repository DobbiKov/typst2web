"""
Convert Typst math source strings to KaTeX-compatible LaTeX.

This handles the most common Typst math constructs:
- Named symbols without backslash (nabla → \\nabla)
- Function calls with parens  (frac(a,b) → \\frac{a}{b})
- Dotted names (plus.minus → \\pm)
- Blackboard bold (RR → \\mathbb{R})
- Superscript/subscript grouping (^(x+y) → ^{x+y})
- Multiline aligned equations
"""

from __future__ import annotations

import re

# ── Symbol tables ─────────────────────────────────────────────────────────────

_GREEK = {
    "alpha": r"\alpha", "beta": r"\beta", "gamma": r"\gamma",
    "delta": r"\delta", "epsilon": r"\epsilon", "varepsilon": r"\varepsilon",
    "zeta": r"\zeta", "eta": r"\eta", "theta": r"\theta", "vartheta": r"\vartheta",
    "iota": r"\iota", "kappa": r"\kappa", "lambda": r"\lambda",
    "mu": r"\mu", "nu": r"\nu", "xi": r"\xi",
    "pi": r"\pi", "varpi": r"\varpi", "rho": r"\rho", "varrho": r"\varrho",
    "sigma": r"\sigma", "varsigma": r"\varsigma", "tau": r"\tau",
    "upsilon": r"\upsilon", "phi": r"\phi", "varphi": r"\varphi",
    "chi": r"\chi", "psi": r"\psi", "omega": r"\omega",
    "Gamma": r"\Gamma", "Delta": r"\Delta", "Theta": r"\Theta",
    "Lambda": r"\Lambda", "Xi": r"\Xi", "Pi": r"\Pi",
    "Sigma": r"\Sigma", "Upsilon": r"\Upsilon", "Phi": r"\Phi",
    "Psi": r"\Psi", "Omega": r"\Omega",
}

_OPS = {
    "nabla": r"\nabla", "partial": r"\partial",
    "infinity": r"\infty", "infty": r"\infty", "oo": r"\infty",
    "integral": r"\int",
    "integral.double": r"\iint", "integral.triple": r"\iiint",
    "integral.cont": r"\oint",
    "sum": r"\sum", "product": r"\prod",
    "lim": r"\lim", "limsup": r"\limsup", "liminf": r"\liminf",
    "sup": r"\sup", "inf": r"\inf",
    "max": r"\max", "min": r"\min",
    "sin": r"\sin", "cos": r"\cos", "tan": r"\tan",
    "sec": r"\sec", "csc": r"\csc", "cot": r"\cot",
    "arcsin": r"\arcsin", "arccos": r"\arccos", "arctan": r"\arctan",
    "sinh": r"\sinh", "cosh": r"\cosh", "tanh": r"\tanh",
    "exp": r"\exp", "log": r"\log", "ln": r"\ln",
    "det": r"\det", "dim": r"\dim", "ker": r"\ker",
    "gcd": r"\gcd", "deg": r"\deg",
    "dif": r"\mathrm{d}",
    "Re": r"\operatorname{Re}", "Im": r"\operatorname{Im}",
    "ell": r"\ell", "wp": r"\wp",
    "hbar": r"\hbar",
    "forall": r"\forall", "exists": r"\exists",
    "top": r"\top", "bot": r"\bot",
    "emptyset": r"\emptyset", "nothing": r"\emptyset",
    "in": r"\in", "notin": r"\notin",
    "times": r"\times", "div": r"\div",
    "approx": r"\approx", "equiv": r"\equiv", "cong": r"\cong",
    "subset": r"\subset", "supset": r"\supset",
    "subseteq": r"\subseteq", "supseteq": r"\supseteq",
    "union": r"\cup", "sect": r"\cap",
    "land": r"\land", "lor": r"\lor", "lnot": r"\lnot",
    "perp": r"\perp", "parallel": r"\parallel",
    "angle": r"\angle", "square": r"\square",
    "bullet": r"\bullet", "circ": r"\circ",
    "star": r"\star", "diamond": r"\diamond",
    "oplus": r"\oplus", "otimes": r"\otimes",
    "prec": r"\prec", "succ": r"\succ",
}

_BLACKBOARD = {
    "RR": r"\mathbb{R}", "NN": r"\mathbb{N}", "ZZ": r"\mathbb{Z}",
    "QQ": r"\mathbb{Q}", "CC": r"\mathbb{C}", "FF": r"\mathbb{F}",
    "HH": r"\mathbb{H}", "PP": r"\mathbb{P}",
}

_DOTTED = {
    "plus.minus": r"\pm", "minus.plus": r"\mp",
    "plus.circle": r"\oplus", "minus.circle": r"\ominus",
    "times.circle": r"\otimes", "div.circle": r"\oslash",
    "dot.op": r"\cdot", "dot.c": r"\cdot",
    "lt.eq": r"\le", "gt.eq": r"\ge",
    "lt.eq.slant": r"\leqslant", "gt.eq.slant": r"\geqslant",
    "lt.double": r"\ll", "gt.double": r"\gg",
    "eq.not": r"\ne", "eq.triple": r"\equiv",
    "tilde.op": r"\sim", "tilde.eq": r"\simeq",
    "prec.eq": r"\preceq", "succ.eq": r"\succeq",
    "in.not": r"\notin", "in.rev": r"\ni",
    "subset.eq": r"\subseteq", "supset.eq": r"\supseteq",
    "union.big": r"\bigcup", "sect.big": r"\bigcap",
    "arrow.r": r"\to", "arrow.l": r"\leftarrow",
    "arrow.r.long": r"\longrightarrow", "arrow.l.long": r"\longleftarrow",
    "arrow.r.double": r"\Rightarrow", "arrow.l.double": r"\Leftarrow",
    "arrow.l.r": r"\leftrightarrow", "arrow.l.r.double": r"\Leftrightarrow",
    "arrow.b": r"\downarrow", "arrow.t": r"\uparrow",
    "arrow.l.r.long": r"\longleftrightarrow",
    "arrow.squiggly": r"\rightsquigarrow",
    "planck.reduce": r"\hbar",
    "star.op": r"\star",
}

# All plain-name symbols, sorted longest-first for greedy matching
_ALL_SYMBOLS: list[tuple[str, str]] = sorted(
    list(_DOTTED.items()) + list(_BLACKBOARD.items()) + list(_GREEK.items()) + list(_OPS.items()),
    key=lambda x: len(x[0]),
    reverse=True,
)

# Single-argument math functions: name(x) → \cmd{x}
_FUNCS_1 = {
    "bold": r"\boldsymbol",
    "italic": r"\mathit",
    "cal": r"\mathcal",
    "frak": r"\mathfrak",
    "mono": r"\texttt",
    "bb": r"\mathbb",
    "sans": r"\mathsf",
    "upright": r"\mathrm",
    "sqrt": r"\sqrt",
    "hat": r"\hat",
    "bar": r"\bar",
    "tilde": r"\tilde",
    "vec": r"\vec",
    "dot": r"\dot",
    "ddot": r"\ddot",
    "overline": r"\overline",
    "underline": r"\underline",
    "overbrace": r"\overbrace",
    "underbrace": r"\underbrace",
    "cancel": r"\cancel",
}


# ── Core conversion ───────────────────────────────────────────────────────────

def to_latex(typst_math: str, *, display: bool = False) -> str:
    """
    Convert a Typst math body (without surrounding $) to LaTeX.
    `display` controls whether to add aligned environment.
    """
    s = typst_math.strip()

    # Handle multiline (aligned) equations
    # Typst: lines separated by \ at end, or just newlines with & alignment
    is_multiline = "\n" in s or (s.count("\\") > 0 and "&" in s)
    if is_multiline and display:
        s = _convert_multiline(s)
        return s

    return _convert_expr(s)


def _convert_multiline(s: str) -> str:
    """Convert multiline Typst math to \\begin{aligned}...\\end{aligned}."""
    # Split on explicit \\ linebreaks in Typst (a single \ on its own)
    # or on newlines
    raw_lines: list[str] = []
    for line in re.split(r"\\\s*\n|\n", s):
        stripped = line.strip()
        if stripped:
            raw_lines.append(stripped)

    if len(raw_lines) <= 1:
        return _convert_expr(s)

    converted = [_convert_expr(line) for line in raw_lines]
    body = " \\\\\n  ".join(converted)
    return r"\begin{aligned}" + "\n  " + body + "\n" + r"\end{aligned}"


def _convert_expr(s: str) -> str:
    """Convert a single-line Typst math expression to LaTeX."""
    # 1. Dotted & blackboard names (longest first, handled in _ALL_SYMBOLS)
    #    But handle the ones with dots first as they'd be disrupted by word-boundary.
    for name, latex in _ALL_SYMBOLS:
        if "." in name:
            s = s.replace(name, latex)
        else:
            # Use letter-only boundaries so integral_0 and alpha^2 also match.
            # (?<!\\) avoids re-matching already-converted \cmd sequences.
            s = re.sub(
                r"(?<!\\)(?<![a-zA-Z])" + re.escape(name) + r"(?![a-zA-Z])",
                lambda m, _l=latex: _l,
                s,
            )

    # 2. Named function calls: frac(a,b) → \frac{a}{b}, root(n,x) → \sqrt[n]{x}
    s = _apply_frac(s)
    s = _apply_root(s)

    # 3. Single-arg functions: bold(x) → \boldsymbol{x}
    for name, latex in _FUNCS_1.items():
        s = _apply_func1(s, name, latex)

    # 4. Subscript/superscript grouping: ^(...) → ^{...}, _(...) → _{...}
    s = _apply_script_parens(s)

    # 5. Fraction via slash: (A) / (B) → \frac{A}{B}
    s = _apply_slash_frac(s)

    # 6. Clean up leftover Typst line-continuation backslashes
    s = re.sub(r"\\\s*$", "", s, flags=re.MULTILINE)

    return s


def _find_matching_paren(s: str, start: int) -> int:
    """Return index AFTER the matching ) for the ( at s[start]."""
    assert s[start] == "("
    depth = 0
    i = start
    while i < len(s):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)  # unmatched


def _apply_func1(s: str, name: str, latex: str) -> str:
    """Replace name(...) with latex{...}."""
    pattern = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    result: list[str] = []
    pos = 0
    for m in pattern.finditer(s):
        result.append(s[pos:m.start()])
        paren_pos = m.end() - 1  # position of '('
        end = _find_matching_paren(s, paren_pos)
        inner = s[paren_pos + 1:end - 1]
        result.append(latex + "{" + _convert_expr(inner) + "}")
        pos = end
    result.append(s[pos:])
    return "".join(result)


def _apply_frac(s: str) -> str:
    """Replace frac(a, b) with \\frac{a}{b}."""
    pattern = re.compile(r"\bfrac\s*\(")
    result: list[str] = []
    pos = 0
    for m in pattern.finditer(s):
        result.append(s[pos:m.start()])
        paren_pos = m.end() - 1
        end = _find_matching_paren(s, paren_pos)
        inner = s[paren_pos + 1:end - 1]
        # Split on the first comma at depth 0
        parts = _split_args(inner)
        if len(parts) >= 2:
            num = _convert_expr(parts[0].strip())
            den = _convert_expr(parts[1].strip())
            result.append(r"\frac{" + num + "}{" + den + "}")
        else:
            result.append(r"\frac{" + _convert_expr(inner) + "}{}")
        pos = end
    result.append(s[pos:])
    return "".join(result)


def _apply_root(s: str) -> str:
    """Replace root(n, x) with \\sqrt[n]{x}."""
    pattern = re.compile(r"\broot\s*\(")
    result: list[str] = []
    pos = 0
    for m in pattern.finditer(s):
        result.append(s[pos:m.start()])
        paren_pos = m.end() - 1
        end = _find_matching_paren(s, paren_pos)
        inner = s[paren_pos + 1:end - 1]
        parts = _split_args(inner)
        if len(parts) >= 2:
            idx = _convert_expr(parts[0].strip())
            rad = _convert_expr(parts[1].strip())
            result.append(r"\sqrt[" + idx + "]{" + rad + "}")
        else:
            result.append(r"\sqrt{" + _convert_expr(inner) + "}")
        pos = end
    result.append(s[pos:])
    return "".join(result)


def _apply_script_parens(s: str) -> str:
    """Convert ^(...) and _(...) to ^{...} and _{...}."""
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] in ("^", "_") and i + 1 < len(s) and s[i + 1] == "(":
            result.append(s[i])
            end = _find_matching_paren(s, i + 1)
            inner = s[i + 2:end - 1]
            result.append("{" + _convert_expr(inner) + "}")
            i = end
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _apply_slash_frac(s: str) -> str:
    """
    Convert (A) / (B) patterns to \\frac{A}{B}.
    Only when both sides are parenthesized groups.
    """
    pattern = re.compile(r"\(([^()]*)\)\s*/\s*\(([^()]*)\)")
    def replacer(m: re.Match) -> str:
        num = _convert_expr(m.group(1))
        den = _convert_expr(m.group(2))
        return r"\frac{" + num + "}{" + den + "}"
    return pattern.sub(replacer, s)


def _split_args(s: str) -> list[str]:
    """Split s on top-level commas (not inside parentheses)."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return parts
