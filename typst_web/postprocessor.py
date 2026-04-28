"""
Post-processor: takes Typst HTML export and assembles a MyST-style web page.

Math is rendered server-side as SVG (via Typst) and injected as inline SVGs.
No CDN dependencies, no JavaScript math rendering.
"""

from __future__ import annotations

import re


# ── Heading utilities ─────────────────────────────────────────────────────────

def _extract_headings(html: str) -> list[dict]:
    headings = []
    slug_counts: dict[str, int] = {}
    for m in re.finditer(r"<h([1-6])[^>]*>(.*?)</h\1>", html, re.IGNORECASE | re.DOTALL):
        level = int(m.group(1))
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-") or "section"
        count = slug_counts.get(slug, 0)
        slug_counts[slug] = count + 1
        headings.append({"level": level, "text": text, "id": slug if count == 0 else f"{slug}-{count}"})
    return headings


def _inject_heading_anchors(html: str) -> str:
    slug_counts: dict[str, int] = {}

    def replace(m: re.Match) -> str:
        tag, inner = m.group(1), m.group(2)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-") or "section"
        count = slug_counts.get(slug, 0)
        slug_counts[slug] = count + 1
        final = slug if count == 0 else f"{slug}-{count}"
        anchor = f'<a class="heading-anchor" href="#{final}" aria-label="Link to this section">#</a>'
        return f'<{tag} id="{final}">{inner}{anchor}</{tag}>'

    return re.sub(r"<(h[1-6])>(.*?)</h[1-6]>", replace, html, flags=re.IGNORECASE | re.DOTALL)


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
            replacement = f'<div class="math-display"{label_attr}>{svg}</div>'
        else:
            replacement = f'<span class="math-inline">{svg}</span>'

        # Match either <span data-math="N"></span> or <div data-math="N"></div>
        html = re.sub(
            rf'<(?:span|div)[^>]*\bdata-math="{n}"[^>]*>.*?</(?:span|div)>',
            replacement,
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
    title: str = "",
    authors: list[str] | None = None,
    date: str = "",
    source_name: str = "document",
) -> str:
    authors = authors or []
    authors_str = ", ".join(authors)

    body_m = re.search(r"<body>([\s\S]*)</body>", typst_html, re.IGNORECASE)
    content = body_m.group(1).strip() if body_m else typst_html

    content = _inject_heading_anchors(content)
    content = _inject_figures(content, figure_svgs)
    content = _inject_math_svgs(content, math_svgs, expressions)

    headings = _extract_headings(content)
    toc_html = _build_toc_html(headings)

    doc_title = title or source_name
    authors_html = f'<span class="doc-authors">{authors_str}</span>' if authors_str else ""
    date_html    = f'<span class="doc-date">{date}</span>' if date else ""

    return (
        _TEMPLATE
        .replace("{{TITLE}}",       doc_title)
        .replace("{{AUTHORS_HTML}}", authors_html)
        .replace("{{DATE_HTML}}",    date_html)
        .replace("{{TOC_HTML}}",     toc_html)
        .replace("{{CONTENT}}",      content)
        .replace("{{SOURCE_NAME}}",  source_name)
        .replace('"{{AUTHORS_STR}}"', f'"{authors_str}"')
        .replace('"{{DATE_STR}}"',    f'"{date}"')
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
  overflow-y: auto; z-index: 50;
  transition: transform var(--transition);
}
#sidebar.hidden { transform: translateX(-100%); }
.sidebar-header {
  padding: 20px 16px 14px;
  border-bottom: 1px solid rgba(255,255,255,.08);
  flex-shrink: 0;
}
.sidebar-title {
  font-family: var(--font-ui); font-size: 13px; font-weight: 600;
  color: #7aa2f7; text-transform: uppercase; letter-spacing: .06em;
}
.sidebar-doc-title {
  font-size: 14px; font-weight: 500; color: var(--sidebar-txt);
  margin-top: 6px; line-height: 1.4;
}
.toc-section-label {
  font-family: var(--font-ui); font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .08em;
  color: #4a5280; padding: 14px 16px 6px;
}
.toc-link {
  display: block; font-family: var(--font-ui); font-size: 13px;
  color: var(--sidebar-txt); text-decoration: none;
  padding: 5px 16px 5px 10px; border-radius: 4px; margin: 1px 8px;
  transition: background var(--transition), color var(--transition);
  line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.toc-link:hover { background: var(--sidebar-hover); }
.toc-link.active { color: var(--sidebar-active); background: rgba(122,162,247,.1); }
.toc-h1 { font-weight: 600; font-size: 13.5px; }
.toc-h2 { font-size: 12.5px; }
.toc-h3 { font-size: 12px; color: #6b7aaa; }
.toc-h4, .toc-h5, .toc-h6 { font-size: 11.5px; color: #5a6a9a; }
.toc-empty { padding: 12px 16px; font-size: 13px; color: #4a5280; }

/* ── Main ─────────────────────────────────────────────────────────────── */
#main { margin-left: var(--sidebar-w); flex: 1; min-width: 0; display: flex; flex-direction: column; }

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
.doc-header h1 { font-size: 2.2rem; font-weight: 700; line-height: 1.2; margin-bottom: 12px; }
.doc-meta { display: flex; gap: 16px; font-family: var(--font-ui); font-size: 13px; color: var(--text-muted); flex-wrap: wrap; }

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
  display: inline;
  white-space: nowrap;
}
.math-inline svg {
  display: inline;
  /* width/height/vertical-align are set as inline style by math_renderer */
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

/* ── Figure SVG ──────────────────────────────────────────────────────── */
.typst-figure-svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }

/* ── Scrollbar ───────────────────────────────────────────────────────── */
#sidebar::-webkit-scrollbar { width: 5px; }
#sidebar::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 3px; }

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
    <div class="sidebar-title">{{SOURCE_NAME}}</div>
    <div class="sidebar-doc-title">{{TITLE}}</div>
  </div>
  <div class="toc-section-label">Contents</div>
  {{TOC_HTML}}
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
function toggleSidebar() {
  sidebar.classList.toggle("open");
  sidebar.classList.toggle("hidden");
  localStorage.setItem("typst-web-sidebar", sidebar.classList.contains("hidden") ? "hidden" : "open");
}
if (window.innerWidth <= 900) sidebar.classList.add("hidden");

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
  const headings = links.map(l => document.getElementById(l.getAttribute("href").slice(1)));
  const obs = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (e.isIntersecting) {
        links.forEach(l => l.classList.remove("active"));
        const idx = headings.indexOf(e.target);
        if (idx >= 0) { links[idx].classList.add("active"); links[idx].scrollIntoView({ block: "nearest" }); }
      }
    }
  }, { rootMargin: "-10% 0px -80% 0px", threshold: 0 });
  headings.forEach(h => h && obs.observe(h));
})();
</script>
</body>
</html>
"""
