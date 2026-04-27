"""
SVG post-processor.

Patches SVG output from the Typst CLI for clean embedding in HTML:
- Remove XML declaration and DOCTYPE
- Namespace all ids to avoid collisions between pages
- Add a CSS class for styling
"""

from __future__ import annotations

import re


# ── SVG patching for HTML embedding ─────────────────────────────────────────

_XML_DECL_RE = re.compile(r"<\?xml[^?]*\?>")
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>")
# Match the opening <svg ...> tag to inject extra attributes
_SVG_OPEN_RE = re.compile(r"(<svg)(\s)", re.IGNORECASE)


def _namespace_ids(svg: str, page_idx: int) -> str:
    """Prefix all id= and href=#/url(# values with a page namespace."""
    ns = f"p{page_idx}-"

    # id="foo"  →  id="p1-foo"
    svg = re.sub(r'\bid="', f'id="{ns}', svg)
    # href="#foo" / xlink:href="#foo"
    svg = re.sub(r'(xlink:href|href)="#', rf'\1="#{ns}', svg)
    # url(#foo)
    svg = re.sub(r"url\(#", f"url(#{ns}", svg)
    return svg


def prepare_svg(svg: str, page_idx: int) -> str:
    """
    Clean and prepare an SVG string for inline HTML embedding.

    - Remove XML declaration and DOCTYPE
    - Namespace all ids to avoid collisions between pages
    - Add preserveAspectRatio and a class for styling
    """
    svg = _XML_DECL_RE.sub("", svg)
    svg = _DOCTYPE_RE.sub("", svg)
    svg = _namespace_ids(svg, page_idx)

    # Inject class and ensure viewBox-based scaling
    def patch_svg_tag(m: re.Match) -> str:
        return m.group(1) + f' class="typst-page" ' + m.group(2)

    svg = _SVG_OPEN_RE.sub(patch_svg_tag, svg, count=1)
    return svg.strip()


# ── dimension extraction ─────────────────────────────────────────────────────

_WIDTH_RE = re.compile(r'<svg[^>]+\bwidth="([^"]+)"', re.IGNORECASE)
_HEIGHT_RE = re.compile(r'<svg[^>]+\bheight="([^"]+)"', re.IGNORECASE)


def get_page_size(svg: str) -> tuple[str, str]:
    """Return (width, height) strings from the SVG root element."""
    wm = _WIDTH_RE.search(svg)
    hm = _HEIGHT_RE.search(svg)
    return (wm.group(1) if wm else "100%", hm.group(1) if hm else "auto")
