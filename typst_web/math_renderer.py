"""
Server-side math rendering: compile all math expressions to SVG using Typst.

Strategy:
- Batch all math expressions into one .typ document (one per page, auto-sized)
- Run typst compile once → multiple SVG files
- Post-process SVGs: strip absolute pt units, embed em-relative sizing
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# The font size used when compiling math. Must match the #set text() call below.
_MATH_FONT_PT = 11.0


def _parse_dim(val: str) -> float:
    """Parse a 'Xpt' SVG attribute to float pt value."""
    return float(re.sub(r"[a-z%]+$", "", val.strip()))


def _clean_svg(svg: str, idx: int, display: bool) -> str:
    """
    Prepare an SVG for inline HTML embedding.

    - Remove XML/DOCTYPE declarations
    - Namespace all ids to avoid collisions
    - Replace absolute pt width/height with em-relative sizing via style attribute
      so the math scales with the surrounding text
    """
    svg = re.sub(r"<\?xml[^?]*\?>", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg)

    # Namespace ids
    svg = re.sub(r'\bid="', f'id="m{idx}-', svg)
    svg = re.sub(r'(xlink:href|href)="#', rf'\1="#m{idx}-', svg)
    svg = re.sub(r"url\(#", f"url(#m{idx}-", svg)

    # Extract natural dimensions from the root <svg> tag
    root_m = re.match(r'<svg([^>]*)>', svg.strip())
    if root_m:
        attrs = root_m.group(1)
        w_m = re.search(r'\bwidth="([^"]+)"', attrs)
        h_m = re.search(r'\bheight="([^"]+)"', attrs)
        if w_m and h_m:
            w_pt = _parse_dim(w_m.group(1))
            h_pt = _parse_dim(h_m.group(1))

            # Convert to em: 1em = _MATH_FONT_PT pt
            w_em = w_pt / _MATH_FONT_PT
            h_em = h_pt / _MATH_FONT_PT

            if display:
                # Display math: full natural size, centered via CSS
                style = f'width:{w_em:.4f}em;height:{h_em:.4f}em;max-width:100%;'
            else:
                # Inline math: scale height to em, let width follow aspect ratio.
                # vertical-align shifts the SVG so the math axis (≈ center of SVG
                # minus bottom margin) aligns with the surrounding text baseline.
                # The 3pt bottom margin in the rendered SVG = 3/_MATH_FONT_PT em.
                bottom_margin_em = 3.0 / _MATH_FONT_PT
                # Shift down so the content sits at the text baseline
                va = -(h_em / 2 - bottom_margin_em)
                style = (
                    f'width:{w_em:.4f}em;height:{h_em:.4f}em;'
                    f'vertical-align:{va:.4f}em;'
                )

            # Replace width/height attrs with just viewBox + style
            new_attrs = re.sub(r'\s*\bwidth="[^"]+"', '', attrs)
            new_attrs = re.sub(r'\s*\bheight="[^"]+"', '', new_attrs)
            new_attrs += f' style="{style}"'
            svg = svg.replace(root_m.group(0), f'<svg{new_attrs}>', 1)

    return svg.strip()


def compile_math_to_svgs(
    expressions: list[tuple[str, bool]],  # (typst_source, is_display)
    *,
    typ_dir: Path,
    font_paths: list[Path] | None = None,
    preamble: str = "",
) -> list[str]:
    """
    Compile a list of Typst math expressions to SVG strings.

    Returns a list of SVG strings in the same order.
    `preamble` is prepended to every page so custom #let / #import definitions
    from the source document are available during math rendering.
    """
    if not expressions:
        return []

    from .compiler import find_typst
    typst = find_typst()

    page_header = (
        "#set page(width: auto, height: auto, margin: (x: 0pt, y: 3pt))\n"
        f"#set text(size: {_MATH_FONT_PT}pt)\n"
    )
    preamble_block = (preamble + "\n") if preamble else ""

    pages: list[str] = []
    for body, is_display in expressions:
        math = f"$ {body.strip()} $" if is_display else f"${body.strip()}$"
        # Use zero x-margin so display width matches content exactly.
        # Use small y-margin so inline expressions have a little breathing room
        # for ascenders/descenders (3pt = same as the _clean_svg constant above).
        pages.append(page_header + preamble_block + math)

    doc = "\n#pagebreak()\n".join(pages)

    # Write the batch file next to the source document so relative #import
    # paths in the preamble resolve correctly.
    src = typ_dir / "_typst_web_math_batch.typ"
    svg_dir = typ_dir / "_typst_web_math_svgs"
    svg_dir.mkdir(exist_ok=True)
    out_pattern = svg_dir / "math-{p}.svg"
    try:
        src.write_text(doc, encoding="utf-8")

        cmd = [typst, "compile", str(src), str(out_pattern), "--format", "svg"]
        if font_paths:
            for fp in font_paths:
                cmd += ["--font-path", str(fp)]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return [""] * len(expressions)

        result: list[str] = []
        for i, (_, is_display) in enumerate(expressions):
            svg_file = svg_dir / f"math-{i + 1}.svg"
            if svg_file.exists():
                result.append(_clean_svg(
                    svg_file.read_text(encoding="utf-8"), i + 1, is_display
                ))
            else:
                result.append("")
    finally:
        src.unlink(missing_ok=True)
        if svg_dir.exists():
            for f in svg_dir.iterdir():
                f.unlink(missing_ok=True)
            svg_dir.rmdir()

    return result
