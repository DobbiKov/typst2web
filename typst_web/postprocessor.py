"""
Post-processor: takes Typst HTML export and assembles a MyST-style web page.

Math is rendered server-side as SVG (via Typst) and injected as inline SVGs.
No CDN dependencies, no JavaScript math rendering.
"""

from __future__ import annotations

import re
from pathlib import Path

_P5_JS_PATH = Path(__file__).parent / "static" / "p5.min.js"


def _load_p5_js() -> str:
    try:
        return _P5_JS_PATH.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(
            f"p5.min.js not found at {_P5_JS_PATH}. "
            "Download it from https://p5js.org and place it there."
        ) from e


# ── Heading utilities ─────────────────────────────────────────────────────────

def _parse_typst_toc(html: str) -> dict[str, dict]:
    """
    Parse Typst's built-in <nav role="doc-toc"> to extract heading metadata.
    Returns {loc_id: {"level": int, "number": str, "text": str}}.
    """
    heading_map: dict[str, dict] = {}
    toc_m = re.search(r'<nav\s[^>]*role="doc-toc"[^>]*>([\s\S]*?)</nav>', html)
    if not toc_m:
        return heading_map
    toc_html = toc_m.group(0)
    for m in re.finditer(
        r'<a\s[^>]*href="#(loc-\d+)"[^>]*>'
        r'(?:<[^>]*class="prefix"[^>]*>([^<]*)</[^>]*>)?\s*(.*?)</a>',
        toc_html,
        re.DOTALL,
    ):
        loc_id = m.group(1)
        prefix = re.sub(r"\s+", " ", m.group(2) or "").strip()
        text = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        level = prefix.count(".") + 1 if prefix else 1
        heading_map[loc_id] = {"level": level, "number": prefix, "text": text}
    return heading_map


def _inject_headings_from_toc(html: str, heading_map: dict[str, dict]) -> str:
    """
    Replace <div id="loc-N">...</div> blocks with proper <h1>/<h2>/... elements.
    """
    if not heading_map:
        return html

    def _find_div_end(s: str, start: int) -> int:
        depth = 0
        i = start
        while i < len(s):
            if s[i:i+4].lower() == "<div":
                depth += 1
                i += 4
            elif s[i:i+6].lower() == "</div>":
                depth -= 1
                if depth == 0:
                    return i + 6
                i += 6
            else:
                i += 1
        return len(s)

    result = html
    loc_positions = []
    for m in re.finditer(r'<div\s[^>]*id="(loc-\d+)"[^>]*>', result):
        loc_positions.append((m.start(), m.end(), m.group(1)))

    for div_start, _div_content_start, loc_id in reversed(loc_positions):
        if loc_id not in heading_map:
            continue
        info = heading_map[loc_id]
        level = min(info["level"], 6)
        tag = f"h{level}"
        prefix = info["number"]
        text = info["text"].replace("&", "&amp;").replace("<", "&lt;")
        div_end = _find_div_end(result, div_start)
        prefix_html = f'<span class="heading-number">{prefix}</span>\u00a0' if prefix else ""
        anchor = f'<a class="heading-anchor" href="#{loc_id}" aria-label="Link to this section">#</a>'
        result = result[:div_start] + f'<{tag} id="{loc_id}">{prefix_html}{text}{anchor}</{tag}>' + result[div_end:]

    return result


def _extract_headings(html: str) -> list[dict]:
    headings = []
    for m in re.finditer(r"<h([1-6])[^>]*>(.*?)</h\1>", html, re.IGNORECASE | re.DOTALL):
        level = int(m.group(1))
        raw_inner = m.group(2)
        text = re.sub(r'<a class="heading-anchor"[^>]*>[^<]*</a>', "", raw_inner)
        text = re.sub(r"<[^>]+>", "", text).strip()
        id_m = re.search(r'\bid="([^"]+)"', m.group(0))
        if id_m:
            headings.append({"level": level, "text": text, "id": id_m.group(1)})
    return headings


# ── Theorem anchor injection ─────────────────────────────────────────────────

def _inject_thm_anchors(html: str) -> str:
    """
    The dobbikov template's #show figure rule strips Typst's label-generated ids.
    Recover them by matching each <a class="thm-ref" href="#label">Kind N</a>
    link against the theorem heading that starts with "Kind N", then prepending
    an id-bearing anchor span just before the matching .typst-thm div.

    We target the inner <div class="typst-thm …"> rather than the enclosing
    <figure> because a lazy <figure>…</figure> regex breaks when theorem content
    itself contains nested <figure> elements (e.g. cetz figures inside theorems).
    """
    # Collect all thm-ref links: {label: "Kind N"} (e.g. {"pvaleur": "Définition 36"})
    targets: dict[str, str] = {}
    for m in re.finditer(r'<a[^>]*\bhref="#([^"]+)"[^>]*\bclass="thm-ref"[^>]*>(.*?)</a>',
                         html, re.DOTALL):
        label, text = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        targets[label] = text  # "Définition 36"

    if not targets:
        return html

    # Build a map: "Kind N" → label (invert, deduplicate by first occurrence)
    text_to_label: dict[str, str] = {}
    for label, text in targets.items():
        if text not in text_to_label:
            text_to_label[text] = label

    # For each theorem div opening tag + thm-head, find the matching label and
    # inject id="label" directly on the div opening tag.
    def patch_div(m: re.Match) -> str:
        div_open = m.group(1)   # e.g. <div class="typst-thm typst-defn">
        thm_head = m.group(2)   # content of <span class="thm-head"><strong>…</strong>
        # Already labelled — leave it
        if re.search(r'\bid=', div_open):
            return m.group(0)
        head_raw = re.sub(r'<[^>]+>', '', thm_head).strip()
        # Strip trailing period or "(name)" suffix
        head_base = re.sub(r'\s*\(.*?\)\.?$|\.?$', '', head_raw).strip()
        label = text_to_label.get(head_base)
        if not label:
            return m.group(0)
        # Insert id into the div opening tag
        new_div_open = div_open.replace('<div ', f'<div id="{label}" ', 1)
        return m.group(0).replace(div_open, new_div_open, 1)

    return re.sub(
        r'(<div[^>]*\bclass="typst-thm\b[^"]*"[^>]*>)'
        r'.*?'
        r'<span[^>]*\bclass="thm-head"[^>]*>.*?<strong>(.*?)</strong>',
        patch_div,
        html,
        flags=re.DOTALL,
    )


# ── Figure SVG injection ──────────────────────────────────────────────────────

def _inject_figures(html: str, figure_svgs: dict[str, str]) -> str:
    def patch(m: re.Match) -> str:
        full = m.group(0)
        fig_id = re.search(r'id="([^"]+)"', full)
        if not fig_id:
            return full
        svg = figure_svgs.get(fig_id.group(1))
        if not svg:
            return full
        svg = re.sub(r"<\?xml[^?]*\?>", "", svg)
        svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg)
        svg = svg.replace('class="typst-doc"', 'class="typst-figure-svg"')
        return full.replace("<figcaption", f"\n{svg}\n<figcaption", 1) if "<figcaption" in full \
               else full.replace("</figure>", f"\n{svg}\n</figure>", 1)

    return re.sub(r"<figure[^>]*>[\s\S]*?</figure>", patch, html, flags=re.IGNORECASE)


# ── Math SVG injection ────────────────────────────────────────────────────────

def _inject_math_svgs(html: str, math_svgs: list[str], expressions) -> str:
    """
    Replace <span data-math="N"> / <div data-math="N"> placeholders with inline SVGs.
    Typst HTML export preserves these html.elem elements verbatim.
    """
    for expr in expressions:
        svg = math_svgs[expr.index] if expr.index < len(math_svgs) else ""
        n = expr.index

        if not svg:
            raw = expr.body.strip().replace("&", "&amp;").replace("<", "&lt;")
            replacement = f'<code class="math-fallback">${raw}$</code>'
        elif expr.display:
            label_attr = f' id="math-{expr.label}"' if expr.label else ""
            if getattr(expr, "numbered", False):
                eq_num = sum(
                    1 for e in expressions
                    if e.index <= expr.index and getattr(e, "numbered", False)
                )
                num_html = f'<span class="eq-number">({eq_num})</span>'
                replacement = f'<div class="math-display math-numbered"{label_attr}>{svg}{num_html}</div>'
            else:
                replacement = f'<div class="math-display"{label_attr}>{svg}</div>'
        else:
            # Move vertical-align from the SVG element to the <span> wrapper so
            # that display:inline-block on the span properly expands the line box.
            # Also inject overflow:visible on the SVG root so glyphs that extend
            # slightly past the Typst-generated viewBox are not clipped.
            va_m = re.search(r'vertical-align:([^;]+);', svg)
            if va_m:
                va = va_m.group(1)
                svg_clean = svg.replace(f'vertical-align:{va};', '', 1)
            else:
                va, svg_clean = '0', svg
            # Inject overflow:visible into SVG root style attribute
            svg_clean = re.sub(
                r'(<svg[^>]+style=")([^"]*)"',
                lambda m: m.group(1) + 'overflow:visible;' + m.group(2) + '"',
                svg_clean, count=1,
            )
            replacement = f'<span class="math-inline" style="vertical-align:{va}">{svg_clean}</span>'

        # Match the exact tag (span or div) with data-math="N" and close it with
        # the same tag name. Using a backreference prevents a <div data-math="N">
        # from being closed by the first </span> of nested content, which would
        # silently swallow the next placeholder.
        html = re.sub(
            rf'<(span|div)[^>]*\bdata-math="{n}"[^>]*>.*?</\1>',
            replacement,
            html,
            flags=re.DOTALL,
        )

    return html


# ── Canvas SVG injection ──────────────────────────────────────────────────────

def _inject_canvas_svgs(html: str, canvas_svgs: list[str]) -> str:
    """Replace <div data-canvas="N"> placeholders with compiled canvas SVGs."""
    for n, svg in enumerate(canvas_svgs):
        if not svg:
            continue
        replacement = f'<div class="canvas-figure">{svg}</div>'
        html = re.sub(
            rf'<div[^>]*\bdata-canvas="{n}"[^>]*>.*?</div>',
            replacement,
            html,
            count=1,
            flags=re.DOTALL,
        )
    return html


# ── p5.js sketch injection ───────────────────────────────────────────────────

def _inject_sketches(html: str, sketches) -> str:
    """Replace <div data-sketch="N"> placeholders with p5.js sketch containers."""
    for sk in sketches:
        n = sk.index
        cid = f"p5-sketch-{n}"
        # Guard against </script> appearing in user JS (would break the script tag)
        safe_js = sk.js_body.replace("</script>", r"<\/script>")
        container = f'<div id="{cid}" class="p5-sketch-container"></div>'
        # IIFE isolates variables between sketches.
        # The auto-parent wrapper redirects p.createSlider / createButton / etc.
        # into the sketch container div instead of <body> (p5.js instance-mode default).
        script = (
            f'<script>(function(){{'
            f'var _cid="{cid}";'
            # Measure container width before p5 initialises so createCanvas can use it.
            # The container div is already in the DOM at this point (it appears just above
            # this inline script), so clientWidth reflects the actual laid-out width.
            f'var _el=document.getElementById(_cid);'
            f'var _cw=(_el||{{}}).clientWidth||640;'
            f'var _userPaused=false;'
            f'var _inst=new p5(function(p){{'
            # Auto-parent any DOM elements (sliders, buttons…) into the sketch container.
            f'["createSlider","createButton","createInput","createSelect",'
            f'"createRadio","createCheckbox","createFileInput"].forEach(function(m){{'
            f'if(!p[m])return;var _o=p[m].bind(p);'
            f'p[m]=function(){{var e=_o.apply(null,arguments);e.parent(_cid);return e;}};'
            f'}});'
            # Cap createCanvas width at the container width so sketches never overflow.
            # Users can also reference _containerWidth directly in their drawing code.
            f'var _origCC=p.createCanvas.bind(p);'
            f'p.createCanvas=function(w,h,r){{return _origCC(Math.min(w,_cw),h,r);}};'
            f'var _containerWidth=_cw;'
            f'\n{safe_js}\n'
            f'}},_cid);'
            # Pause/play toggle button injected into the container.
            f'var _btn=document.createElement("button");'
            f'_btn.className="p5-sketch-btn";'
            f'_btn.title="Pause animation";'
            f'_btn.textContent="\u23f8";'
            f'_btn.addEventListener("click",function(){{'
            f'_userPaused=!_userPaused;'
            f'if(_userPaused){{_inst.noLoop();_btn.textContent="\u25b6";_btn.title="Resume animation";}}'
            f'else{{_inst.loop();_btn.textContent="\u23f8";_btn.title="Pause animation";}}'
            f'}});'
            f'if(_el)_el.appendChild(_btn);'
            # IntersectionObserver: auto-pause when scrolled out of view, resume on re-entry.
            # Only acts when the user has not manually paused.
            f'if(window.IntersectionObserver){{'
            f'var _io=new IntersectionObserver(function(entries){{'
            f'entries.forEach(function(e){{'
            f'if(_userPaused)return;'
            f'if(e.isIntersecting)_inst.loop();'
            f'else _inst.noLoop();'
            f'}});'
            f'}},{{threshold:0.1}});'
            f'if(_el)_io.observe(_el);'
            f'}}'
            f'}})();</script>'
        )
        replacement = f'{container}\n{script}'
        html = re.sub(
            rf'<div[^>]*\bdata-sketch="{n}"[^>]*>.*?</div>',
            lambda _m, r=replacement: r,
            html,
            count=1,
            flags=re.DOTALL,
        )
    return html


# ── TOC ───────────────────────────────────────────────────────────────────────

def _build_toc_html(headings: list[dict]) -> str:
    if not headings:
        return '<p class="toc-empty">No headings</p>'
    parts = []
    for h in headings:
        indent = (h["level"] - 1) * 14
        text = h["text"].replace("&", "&amp;").replace("<", "&lt;")
        parts.append(
            f'<a class="toc-link toc-h{h["level"]}" href="#{h["id"]}" '
            f'style="padding-left:{indent + 10}px">{text}</a>'
        )
    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def build_web_page(
    typst_html: str,
    figure_svgs: dict[str, str],
    math_svgs: list[str],
    expressions,            # list[MathExpr] from preprocessor
    *,
    canvas_svgs: list[str] | None = None,
    sketches=None,          # list[SketchExpr] | None
    title: str = "",
    subtitle: str = "",
    authors=None,  # list[Author] | None
    date: str = "",
    source_name: str = "document",
) -> str:
    from .settings import Author
    authors: list[Author] = authors or []

    def _author_html(a: Author) -> str:
        if a.website:
            return f'<a href="{a.website}" class="author-link" target="_blank" rel="noopener">{a.name}</a>'
        if a.email:
            return f'<a href="mailto:{a.email}" class="author-link">{a.name}</a>'
        return a.name

    authors_str = ", ".join(a.name for a in authors)
    authors_html_parts = ", ".join(_author_html(a) for a in authors)

    body_m = re.search(r"<body>([\s\S]*)</body>", typst_html, re.IGNORECASE)
    content = body_m.group(1).strip() if body_m else typst_html

    # Parse Typst's built-in TOC before any transformations
    heading_map = _parse_typst_toc(content)

    content = _inject_headings_from_toc(content, heading_map)
    content = _inject_figures(content, figure_svgs)
    content = _inject_math_svgs(content, math_svgs, expressions)
    if canvas_svgs:
        content = _inject_canvas_svgs(content, canvas_svgs)
    sketches = sketches or []
    if sketches:
        content = _inject_sketches(content, sketches)
    content = _inject_thm_anchors(content)

    headings = _extract_headings(content)
    toc_html = _build_toc_html(headings)

    doc_title = title or source_name
    authors_html  = f'<span class="doc-authors">{authors_html_parts}</span>' if authors_html_parts else ""
    date_html     = f'<span class="doc-date">{date}</span>' if date else ""
    subtitle_html = f'<div class="doc-subtitle">{subtitle}</div>' if subtitle else ""
    sidebar_subtitle_html = f'<div class="sidebar-doc-subtitle">{subtitle}</div>' if subtitle else ""

    p5_script = f'<script>\n{_load_p5_js()}\n</script>' if sketches else ""

    return (
        _TEMPLATE
        .replace("{{TITLE}}",                doc_title)
        .replace("{{SUBTITLE_HTML}}",         subtitle_html)
        .replace("{{SIDEBAR_SUBTITLE_HTML}}", sidebar_subtitle_html)
        .replace("{{AUTHORS_HTML}}",          authors_html)
        .replace("{{DATE_HTML}}",             date_html)
        .replace("{{TOC_HTML}}",              toc_html)
        .replace("{{CONTENT}}",               content)
        .replace('"{{AUTHORS_STR}}"',         f'"{authors_str}"')
        .replace('"{{DATE_STR}}"',            f'"{date}"')
        .replace("{{P5_SCRIPT}}",             p5_script)
    )


# ── Template ──────────────────────────────────────────────────────────────────

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<meta name="generator" content="typst-to-web">
{{P5_SCRIPT}}
<style>
/* ── Design tokens ─────────────────────────────────────────────────────── */
:root {
  --font-body: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
  --sidebar-w: 270px;
  --content-max: 780px;
  --header-h: 52px;
  --bg:          #ffffff;
  --bg-alt:      #f8f7f5;
  --sidebar-bg:  #1b1b2e;
  --sidebar-txt: #c9d1f0;
  --sidebar-hover: rgba(255,255,255,.08);
  --sidebar-active: #7aa2f7;
  --accent:      #7c3aed;
  --text:        #1a1a2e;
  --text-muted:  #64748b;
  --border:      #e2e8f0;
  --code-bg:     #1e2030;
  --code-text:   #c0caf5;
  --shadow:      0 1px 3px rgba(0,0,0,.1);
  --radius:      6px;
  --transition:  0.18s ease;
}
[data-theme="dark"] {
  --bg:         #1a1a2e;
  --bg-alt:     #16213e;
  --text:       #c9d1f0;
  --text-muted: #8892b0;
  --border:     #2a2a4a;
  --accent:     #7aa2f7;
}

/* ── Reset ─────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; scroll-behavior: smooth; }
body {
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--text);
  line-height: 1.75;
  overflow-x: hidden;
}

/* ── Layout ─────────────────────────────────────────────────────────────── */
#layout { display: flex; min-height: 100vh; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
#sidebar {
  width: var(--sidebar-w); flex-shrink: 0;
  background: var(--sidebar-bg); color: var(--sidebar-txt);
  display: flex; flex-direction: column;
  position: fixed; top: 0; left: 0; bottom: 0;
  overflow: hidden; z-index: 50;
  transition: transform var(--transition);
}
#sidebar.hidden { transform: translateX(-100%); }
.sidebar-header {
  padding: 20px 16px 14px;
  border-bottom: 1px solid rgba(255,255,255,.08);
  flex-shrink: 0;
}
.sidebar-doc-title {
  font-size: 14px; font-weight: 500; color: var(--sidebar-txt);
  margin-top: 6px; line-height: 1.4;
}
.sidebar-doc-subtitle {
  font-size: 12px; color: var(--sidebar-txt); opacity: .7;
  margin-top: 3px; line-height: 1.35;
}
.toc-section-label {
  font-family: var(--font-ui); font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .08em;
  color: #4a5280; padding: 14px 16px 6px;
  flex-shrink: 0;
}
/* Scrollable TOC container — flex: 1 + min-height: 0 are both required */
#toc-scroll {
  flex: 1; min-height: 0;
  overflow-y: auto; overflow-x: hidden;
  padding-bottom: 16px;
}
#toc-scroll::-webkit-scrollbar { width: 4px; }
#toc-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 2px; }
.toc-link {
  display: block; font-family: var(--font-ui); font-size: 13px;
  color: var(--sidebar-txt); text-decoration: none;
  padding: 5px 16px 5px 10px; border-radius: 4px; margin: 1px 8px;
  transition: background var(--transition), color var(--transition);
  line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.toc-link:hover { background: var(--sidebar-hover); color: #e0e8ff; }
.toc-link.active { color: var(--sidebar-active); background: rgba(122,162,247,.1); }
.toc-h1 { font-weight: 600; font-size: 13.5px; }
.toc-h2 { font-size: 12.5px; color: #bbc6e8; }
.toc-h3 { font-size: 12px; color: #9aa7cc; }
.toc-h4, .toc-h5, .toc-h6 { font-size: 11.5px; color: #8090b8; }
.toc-empty { padding: 12px 16px; font-size: 13px; color: #4a5280; }

/* ── Main ─────────────────────────────────────────────────────────────── */
#main { margin-left: var(--sidebar-w); flex: 1; min-width: 0; display: flex; flex-direction: column; transition: margin-left var(--transition); }
#main.sidebar-hidden { margin-left: 0; }

/* ── Topbar ──────────────────────────────────────────────────────────── */
#topbar {
  height: var(--header-h); background: var(--sidebar-bg); color: var(--sidebar-txt);
  display: flex; align-items: center; gap: 12px; padding: 0 24px;
  position: sticky; top: 0; z-index: 40; box-shadow: var(--shadow);
  font-family: var(--font-ui);
}
#topbar .tb-title { flex: 1; font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#topbar .tb-meta  { font-size: 12px; color: #7aa2f7; white-space: nowrap; }
.btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius);
  background: rgba(255,255,255,.1); color: var(--sidebar-txt);
  border: none; cursor: pointer; font-size: 12px; font-family: var(--font-ui);
  transition: background var(--transition); white-space: nowrap;
}
.btn:hover { background: rgba(255,255,255,.2); }

/* ── Article ─────────────────────────────────────────────────────────── */
#article { max-width: var(--content-max); margin: 0 auto; padding: 48px 40px 96px; flex: 1; }

.doc-header { margin-bottom: 40px; padding-bottom: 24px; border-bottom: 2px solid var(--border); }
.doc-header h1 { font-size: 2.2rem; font-weight: 700; line-height: 1.2; margin-bottom: 8px; }
.doc-subtitle { font-size: 1.1rem; color: var(--text-muted); margin-bottom: 12px; }
.doc-meta { display: flex; gap: 16px; font-family: var(--font-ui); font-size: 13px; color: var(--text-muted); flex-wrap: wrap; }
.author-link { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
.author-link:hover { color: var(--accent); }

/* ── Typography ──────────────────────────────────────────────────────── */
h1 { font-size: 1.9rem; font-weight: 700; margin: 2rem 0 0.8rem; line-height: 1.25; }
h2 { font-size: 1.5rem; font-weight: 600; margin: 1.8rem 0 0.7rem; line-height: 1.3;
     padding-bottom: 6px; border-bottom: 1px solid var(--border); }
h3 { font-size: 1.2rem; font-weight: 600; margin: 1.5rem 0 0.5rem; }
h4 { font-size: 1.05rem; font-weight: 600; margin: 1.2rem 0 0.4rem; }
h5, h6 { font-size: 1rem; font-weight: 600; margin: 1rem 0 0.3rem; }
p { margin: 0.7rem 0; }
strong { font-weight: 700; }
em { font-style: italic; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
ul, ol { margin: 0.75rem 0 0.75rem 1.5rem; padding: 0; }
ul { list-style: disc; }
ol { list-style: decimal; }
li { margin: 0.25rem 0; }

.heading-anchor {
  margin-left: 8px; font-size: 0.75em; color: var(--border);
  text-decoration: none; opacity: 0; transition: opacity var(--transition);
}
h1:hover .heading-anchor, h2:hover .heading-anchor,
h3:hover .heading-anchor, h4:hover .heading-anchor { opacity: 1; color: var(--accent); }

/* ── Code ─────────────────────────────────────────────────────────────── */
pre {
  background: var(--code-bg); color: var(--code-text); border-radius: var(--radius);
  padding: 1rem 1.25rem; overflow-x: auto; font-family: var(--font-mono);
  font-size: 0.85rem; line-height: 1.6; margin: 1.2rem 0; box-shadow: var(--shadow);
}
code {
  font-family: var(--font-mono); font-size: 0.88em; background: var(--bg-alt);
  color: var(--accent); padding: 2px 5px; border-radius: 3px; border: 1px solid var(--border);
}
pre code { background: none; color: inherit; padding: 0; border: none; font-size: inherit; }

/* ── Tables ──────────────────────────────────────────────────────────── */
figure { margin: 1.5rem 0; }
table {
  border-collapse: collapse; width: 100%; font-family: var(--font-ui); font-size: 0.9rem;
  margin: 1rem 0; background: var(--bg); border-radius: var(--radius);
  overflow: hidden; box-shadow: var(--shadow);
}
th { background: var(--bg-alt); font-weight: 600; text-align: left; padding: 10px 14px;
     border-bottom: 2px solid var(--border); color: var(--text); }
td { padding: 8px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--bg-alt); }
figcaption { font-family: var(--font-ui); font-size: 0.85rem; color: var(--text-muted); text-align: center; margin-top: 8px; padding: 0 8px; }

/* ── Math (server-side SVG, em-sized) ───────────────────────────────── */
.math-inline {
  display: inline-block;
  line-height: 0;     /* prevent phantom line-gap; SVG height controls line box */
  white-space: nowrap;
  overflow: visible;  /* allow SVG content that slightly overflows the span */
  /* vertical-align is set per-element as inline style by the injector */
}
.math-inline svg {
  display: block;     /* block inside inline-block: no extra inline gap below */
  overflow: visible;  /* SVG default is hidden; glyphs can extend past viewBox */
  /* width/height are set as inline style by math_renderer */
}
.math-display {
  display: block;
  text-align: center;
  margin: 1.5rem auto;
  overflow-x: auto;
  line-height: 1;
}
.math-display svg {
  display: inline-block;
  max-width: 100%;
  vertical-align: middle;
}
.math-fallback { font-size: 0.85em; color: var(--text-muted); }
.math-numbered {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 1rem;
}
.math-numbered svg { display: inline-block; max-width: 100%; vertical-align: middle; }
.eq-number { color: var(--text-muted); font-size: 0.9em; white-space: nowrap; }
.eq-ref, .thm-ref { color: var(--accent); text-decoration: none; }
.eq-ref:hover, .thm-ref:hover { text-decoration: underline; }

/* ── Figure and canvas SVG ───────────────────────────────────────────── */
.typst-figure-svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }
.typst-canvas-svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }
.canvas-figure { text-align: center; margin: 1.5rem 0; }
figure img, #article img { display: block; max-width: 100%; height: auto; margin: 0 auto; }

/* ── p5.js sketch containers ─────────────────────────────────────────── */
.p5-sketch-container {
  display: block;
  position: relative;
  margin: 1.5rem auto;
  line-height: 0;
  text-align: center;
}
.p5-sketch-container canvas {
  display: inline-block;
  max-width: 100%;
}
.p5-sketch-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 10;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(0,0,0,.35);
  color: #fff;
  font-size: 11px;
  line-height: 28px;
  cursor: pointer;
  opacity: 0;
  transition: opacity .15s;
}
.p5-sketch-container:hover .p5-sketch-btn { opacity: 1; }
[data-theme="dark"] .p5-sketch-btn { background: rgba(255,255,255,.2); }

/* ── Theorem environments ─────────────────────────────────────────────── */
.typst-thm {
  margin: 1.2rem 0;
  padding: 0.75rem 1rem;
  border-radius: var(--radius);
  border-left: 3px solid var(--accent);
  background: var(--bg-alt);
  font-size: 0.97em;
}
.typst-thm .thm-head {
  display: inline;
  color: var(--accent);
  font-family: var(--font-ui);
  font-size: 0.9em;
}
/* Per-type accent colors */
.typst-defn  { border-left-color: #2563eb; }
.typst-defn  .thm-head { color: #2563eb; }
.typst-thm-env { border-left-color: #7c3aed; }
.typst-thm-env .thm-head { color: #7c3aed; }
.typst-lem   { border-left-color: #7c3aed; }
.typst-lem   .thm-head { color: #7c3aed; }
.typst-prop  { border-left-color: #7c3aed; }
.typst-prop  .thm-head { color: #7c3aed; }
.typst-cor   { border-left-color: #9333ea; }
.typst-cor   .thm-head { color: #9333ea; }
.typst-rmk   { border-left-color: #0891b2; }
.typst-rmk   .thm-head { color: #0891b2; }
.typst-ex    { border-left-color: #059669; }
.typst-ex    .thm-head { color: #059669; }
.typst-proof, .typst-soln { border-left-color: #64748b; background: none; }
.typst-proof .thm-head, .typst-soln .thm-head { color: #64748b; }
.typst-rmnd  { border-left-color: #d97706; }
.typst-rmnd  .thm-head { color: #d97706; }
.typst-todo  { border-left-color: #dc2626; background: #fff1f2; }
.typst-todo  .thm-head { color: #dc2626; }
[data-theme="dark"] .typst-thm { background: rgba(255,255,255,.04); }

/* ── SVG dark-mode ───────────────────────────────────────────────────── */
/* Math SVGs use fill="currentColor" so they follow --text automatically.  */
/* Canvas/figure SVGs are diagrams with a white background — invert them  */
/* so they appear as dark-background diagrams in dark mode.               */
[data-theme="dark"] .typst-canvas-svg,
[data-theme="dark"] .typst-figure-svg {
  filter: invert(1) hue-rotate(180deg);
}

/* ── Heading numbers ─────────────────────────────────────────────────── */
.heading-number { color: var(--text-muted); font-size: 0.9em; }

/* (scrollbar rules are on #toc-scroll above) */

/* ── Responsive ──────────────────────────────────────────────────────── */
@media (max-width: 900px) {
  #sidebar { transform: translateX(-100%); }
  #sidebar.open { transform: translateX(0); }
  #main { margin-left: 0; }
  #article { padding: 32px 20px 64px; }
}
@media (max-width: 600px) {
  :root { --content-max: 100%; }
  #article { padding: 24px 16px 48px; }
  h1 { font-size: 1.6rem; }
  h2 { font-size: 1.3rem; }
}
@media print {
  #sidebar, #topbar { display: none !important; }
  #main { margin: 0; }
  #article { max-width: 100%; padding: 0; }
  .heading-anchor { display: none; }
}
</style>
</head>
<body>
<div id="layout">

<nav id="sidebar" aria-label="Table of contents">
  <div class="sidebar-header">
    <div class="sidebar-doc-title">{{TITLE}}</div>
    {{SIDEBAR_SUBTITLE_HTML}}
  </div>
  <div class="toc-section-label">Contents</div>
  <div id="toc-scroll">
    {{TOC_HTML}}
  </div>
</nav>

<div id="main">
  <header id="topbar">
    <button class="btn" id="btn-menu" onclick="toggleSidebar()" aria-label="Toggle sidebar">&#9776;</button>
    <span class="tb-title">{{TITLE}}</span>
    <span class="tb-meta" id="tb-meta"></span>
    <button class="btn" onclick="toggleTheme()">&#9788; Theme</button>
    <button class="btn" onclick="window.print()">&#128438; Print</button>
  </header>

  <main id="article">
    <div class="doc-header">
      <h1>{{TITLE}}</h1>
      {{SUBTITLE_HTML}}
      <div class="doc-meta">{{AUTHORS_HTML}}{{DATE_HTML}}</div>
    </div>
    {{CONTENT}}
  </main>
</div>
</div>

<script>
"use strict";
function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("typst-web-theme", next);
}
(function() {
  const t = localStorage.getItem("typst-web-theme");
  if (t) document.documentElement.setAttribute("data-theme", t);
})();

const sidebar = document.getElementById("sidebar");
const mainEl = document.getElementById("main");
function setSidebarHidden(hidden) {
  sidebar.classList.toggle("hidden", hidden);
  sidebar.classList.toggle("open", !hidden);
  mainEl.classList.toggle("sidebar-hidden", hidden);
}
function toggleSidebar() {
  const hidden = !sidebar.classList.contains("hidden");
  setSidebarHidden(hidden);
  localStorage.setItem("typst-web-sidebar", hidden ? "hidden" : "open");
}
(function() {
  const saved = localStorage.getItem("typst-web-sidebar");
  if (saved === "hidden" || (saved === null && window.innerWidth <= 900)) {
    setSidebarHidden(true);
  }
})();

(function() {
  const authors = "{{AUTHORS_STR}}";
  const date    = "{{DATE_STR}}";
  const parts = [];
  if (authors) parts.push(authors);
  if (date)    parts.push(date);
  const el = document.getElementById("tb-meta");
  if (el) el.textContent = parts.join(" \u00b7 ");
})();

(function() {
  const links = Array.from(document.querySelectorAll(".toc-link"));
  if (!links.length) return;
  const tocScroll = document.getElementById("toc-scroll");
  const headings = links.map(l => document.getElementById(l.getAttribute("href").slice(1)));
  const obs = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (e.isIntersecting) {
        links.forEach(l => l.classList.remove("active"));
        const idx = headings.indexOf(e.target);
        if (idx >= 0) {
          links[idx].classList.add("active");
          // Scroll the active link into view within the TOC panel
          if (tocScroll) {
            const linkTop = links[idx].offsetTop - tocScroll.offsetTop;
            const linkBottom = linkTop + links[idx].offsetHeight;
            const scrollTop = tocScroll.scrollTop;
            const scrollBottom = scrollTop + tocScroll.clientHeight;
            if (linkTop < scrollTop + 40) {
              tocScroll.scrollTop = linkTop - 40;
            } else if (linkBottom > scrollBottom - 40) {
              tocScroll.scrollTop = linkBottom - tocScroll.clientHeight + 40;
            }
          }
        }
      }
    }
  }, { rootMargin: "-10% 0px -80% 0px", threshold: 0 });
  headings.forEach(h => h && obs.observe(h));
})();
</script>
</body>
</html>
"""
