"""
HTML assembler.

Takes processed SVG pages + document structure and produces
a single self-contained HTML file (zero external dependencies).
"""

from __future__ import annotations

import json

from .parser import TypstStructure
from .svg_proc import get_page_size, prepare_svg


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_toc(structure: TypstStructure) -> str:
    if not structure.headings:
        return '<p class="toc-empty">No headings found</p>'
    parts: list[str] = []
    for h in structure.headings:
        indent = (h.level - 1) * 16
        parts.append(
            f'<a class="toc-item toc-level-{h.level}" '
            f'href="#{h.slug}" '
            f'style="padding-left:{indent + 8}px" '
            f'data-slug="{h.slug}">'
            f"{_esc(h.text)}"
            f"</a>"
        )
    return "\n".join(parts)


def build_html(
    svgs: list[str],
    structure: TypstStructure,
    search_index: list[dict],
    *,
    source_name: str = "document",
) -> str:
    """Return the full HTML string for the web viewer."""
    prepared_svgs: list[str] = []

    for i, raw_svg in enumerate(svgs):
        page_num = i + 1
        prepared = prepare_svg(raw_svg, page_num)
        prepared_svgs.append(prepared)

    toc_html = _build_toc(structure)
    meta = structure.meta
    title = meta.title or source_name
    authors_str = ", ".join(meta.authors) if meta.authors else ""

    authors_meta_tags = "\n".join(
        f'<meta name="author" content="{_esc(a)}">' for a in meta.authors
    ) if meta.authors else ""

    search_index_js = (
        f"const SEARCH_INDEX = {json.dumps(search_index, ensure_ascii=False)};"
    )
    headings_js = json.dumps(
        [{"level": h.level, "text": h.text, "slug": h.slug} for h in structure.headings],
        ensure_ascii=False,
    )

    pages_html_parts: list[str] = []
    for i, svg in enumerate(prepared_svgs):
        page_num = i + 1
        pages_html_parts.append(
            f'<div class="page-wrapper" id="page-{page_num}" data-page="{page_num}">'
            f'<div class="page-number-label">Page {page_num}</div>'
            f"{svg}"
            f"</div>"
        )
    pages_html = "\n".join(pages_html_parts)
    total_pages = len(svgs)

    return _render_template(
        title=title,
        authors_str=authors_str,
        authors_meta_tags=authors_meta_tags,
        date_str=meta.date,
        source_name=source_name,
        total_pages=total_pages,
        toc_html=toc_html,
        pages_html=pages_html,
        search_index_js=search_index_js,
        headings_js=headings_js,
    )


def _render_template(
    *,
    title: str,
    authors_str: str,
    authors_meta_tags: str,
    date_str: str,
    source_name: str,
    total_pages: int,
    toc_html: str,
    pages_html: str,
    search_index_js: str,
    headings_js: str,
) -> str:
    # We build this as a regular string (no .format()) so that SVG content with
    # curly braces doesn't break anything.
    parts = [
        _TEMPLATE_HEAD_1,
        _esc(title),
        _TEMPLATE_HEAD_2,
        authors_meta_tags,
        _TEMPLATE_HEAD_3,
        _TEMPLATE_CSS,
        _TEMPLATE_HEAD_4,  # close <style>, open <body>/<div id=app>
        _TEMPLATE_TOPBAR.replace("__TOTAL__", str(total_pages)),
        _TEMPLATE_BODY_OPEN,
        toc_html,
        _TEMPLATE_SIDEBAR_CLOSE,
        pages_html,
        _TEMPLATE_BODY_CLOSE,
        _TEMPLATE_SCRIPT_OPEN,
        search_index_js,
        "\nconst HEADINGS = ",
        headings_js,
        ";\n",
        "const TOTAL_PAGES = ",
        str(total_pages),
        ";\n",
        _TEMPLATE_SCRIPT_VARS.replace("__TITLE__", _esc(title))
                              .replace("__AUTHORS__", _esc(authors_str))
                              .replace("__DATE__", _esc(date_str)),
        _TEMPLATE_SCRIPT_BODY,
        _TEMPLATE_CLOSE,
    ]
    return "".join(parts)


# ── template fragments ────────────────────────────────────────────────────────

_TEMPLATE_HEAD_1 = """\
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>"""

_TEMPLATE_HEAD_2 = """</title>
<meta name="generator" content="typst-to-web">
"""

_TEMPLATE_HEAD_3 = """
<style>
"""

_TEMPLATE_CSS = """\
/* ── reset & base ──────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f5f5f4;
  --surface: #ffffff;
  --sidebar-bg: #1e1e2e;
  --sidebar-text: #cdd6f4;
  --sidebar-hover: #313244;
  --sidebar-active: #89b4fa;
  --accent: #7c3aed;
  --accent-light: #ede9fe;
  --text: #1c1c1e;
  --text-muted: #6b7280;
  --border: #e5e7eb;
  --shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.08);
  --shadow-lg: 0 10px 25px rgba(0,0,0,.15);
  --sidebar-w: 280px;
  --topbar-h: 52px;
  --radius: 6px;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --transition: 0.2s ease;
}
[data-theme="dark"] {
  --bg: #11111b;
  --surface: #1e1e2e;
  --text: #cdd6f4;
  --text-muted: #a6adc8;
  --border: #313244;
  --accent: #89b4fa;
  --accent-light: #1e2035;
}

html, body { height: 100%; overflow: hidden; background: var(--bg); color: var(--text); font-family: var(--font-ui); }

/* ── layout ────────────────────────────────────────────── */
#app { display: flex; flex-direction: column; height: 100vh; }

#topbar {
  height: var(--topbar-h); flex-shrink: 0;
  background: var(--sidebar-bg); color: var(--sidebar-text);
  display: flex; align-items: center; gap: 12px; padding: 0 16px;
  z-index: 100; box-shadow: var(--shadow);
}
#topbar .title {
  font-size: 15px; font-weight: 600; flex: 1;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
#topbar .meta { font-size: 12px; color: #89b4fa; white-space: nowrap; }

#body { display: flex; flex: 1; overflow: hidden; }

/* ── sidebar ───────────────────────────────────────────── */
#sidebar {
  width: var(--sidebar-w); flex-shrink: 0;
  background: var(--sidebar-bg); color: var(--sidebar-text);
  display: flex; flex-direction: column; overflow: hidden;
  transition: width var(--transition);
  border-right: 1px solid rgba(255,255,255,0.05);
}
#sidebar.collapsed { width: 0; }

#search-box {
  padding: 12px; border-bottom: 1px solid rgba(255,255,255,.08);
  flex-shrink: 0;
}
#search-input {
  width: 100%; padding: 7px 10px; border-radius: var(--radius);
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.07); color: var(--sidebar-text);
  font-size: 13px; outline: none; transition: border-color var(--transition);
}
#search-input:focus { border-color: var(--accent); }
#search-input::placeholder { color: #6c7086; }

#search-results { overflow-y: auto; flex: 1; display: none; }
#search-results.visible { display: block; }

.search-result {
  padding: 8px 12px; cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,.05); font-size: 12px;
}
.search-result:hover { background: var(--sidebar-hover); }
.search-result .sr-page { color: #89b4fa; font-weight: 600; font-size: 11px; margin-bottom: 3px; }
.search-result .sr-snippet { color: #a6adc8; line-height: 1.4; }
.search-result mark { background: #f9e2af44; color: #f9e2af; border-radius: 2px; padding: 0 2px; }

#toc-panel { overflow-y: auto; flex: 1; padding: 8px 0; }
#toc-panel.hidden { display: none; }

.toc-label {
  font-size: 10px; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: #6c7086;
  padding: 10px 12px 6px;
}
.toc-item {
  display: block; padding: 5px 8px; text-decoration: none;
  color: var(--sidebar-text); font-size: 13px; line-height: 1.4;
  border-radius: 4px; margin: 1px 6px; transition: background var(--transition);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.toc-item:hover { background: var(--sidebar-hover); }
.toc-item.active { background: var(--sidebar-hover); color: var(--sidebar-active); }
.toc-level-1 { font-weight: 600; font-size: 13px; }
.toc-level-2 { font-size: 12.5px; }
.toc-level-3 { font-size: 12px; color: #a6adc8; }
.toc-empty { padding: 12px; font-size: 12px; color: #6c7086; }

/* ── main viewer ───────────────────────────────────────── */
#viewer {
  flex: 1; overflow-y: auto; overflow-x: auto;
  background: var(--bg); padding: 24px 32px 80px;
  scroll-behavior: smooth;
}

.page-wrapper {
  position: relative; margin: 0 auto 24px;
  max-width: 900px; width: fit-content;
  background: var(--surface); border-radius: var(--radius);
  box-shadow: var(--shadow-lg); overflow: hidden;
  transition: box-shadow var(--transition);
}
.page-wrapper:hover { box-shadow: 0 15px 35px rgba(0,0,0,.2); }

.page-number-label {
  position: absolute; top: 6px; right: 10px; z-index: 10;
  font-size: 10px; color: var(--text-muted); background: var(--surface);
  padding: 2px 6px; border-radius: 10px; opacity: 0;
  transition: opacity var(--transition); pointer-events: none;
}
.page-wrapper:hover .page-number-label { opacity: 1; }

.typst-page { display: block; width: 100%; height: auto; }

/* zoom levels */
#viewer.zoom-75  .page-wrapper { max-width: 675px; }
#viewer.zoom-100 .page-wrapper { max-width: 900px; }
#viewer.zoom-125 .page-wrapper { max-width: 1125px; }
#viewer.zoom-150 .page-wrapper { max-width: 1350px; }
#viewer.zoom-fit .page-wrapper { max-width: calc(100% - 64px); }

/* ── toolbar buttons ───────────────────────────────────── */
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 6px 10px; border-radius: var(--radius); border: none;
  background: rgba(255,255,255,.1); color: var(--sidebar-text);
  cursor: pointer; font-size: 13px; transition: background var(--transition);
  white-space: nowrap; gap: 5px;
}
.btn:hover { background: rgba(255,255,255,.2); }
.btn svg { width: 15px; height: 15px; fill: currentColor; }

#page-nav { display: flex; align-items: center; gap: 6px; font-size: 13px; }
#page-nav input {
  width: 40px; text-align: center; padding: 4px;
  border-radius: var(--radius); border: 1px solid rgba(255,255,255,.2);
  background: rgba(255,255,255,.08); color: var(--sidebar-text); font-size: 13px;
  -moz-appearance: textfield;
}
#page-nav input::-webkit-outer-spin-button,
#page-nav input::-webkit-inner-spin-button { -webkit-appearance: none; }

/* ── search highlight ──────────────────────────────────── */
.page-highlight { outline: 3px solid var(--accent); outline-offset: -3px; border-radius: var(--radius); }

/* ── scrollbars ────────────────────────────────────────── */
#viewer::-webkit-scrollbar { width: 8px; }
#viewer::-webkit-scrollbar-track { background: transparent; }
#viewer::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
#viewer::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
#toc-panel::-webkit-scrollbar { width: 4px; }
#toc-panel::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 2px; }

/* ── responsive ────────────────────────────────────────── */
@media (max-width: 768px) {
  :root { --sidebar-w: 240px; }
  #viewer { padding: 16px 12px 60px; }
  .page-wrapper { margin-bottom: 16px; }
}

/* ── print ─────────────────────────────────────────────── */
@media print {
  #topbar, #sidebar { display: none !important; }
  #body { display: block; }
  #viewer { overflow: visible; padding: 0; background: white; }
  .page-wrapper { box-shadow: none; margin: 0 0 20px; page-break-after: always; }
  .page-number-label { display: none; }
}
"""

_TEMPLATE_HEAD_4 = """\
</style>
</head>
<body>
<div id="app">
"""

_TEMPLATE_TOPBAR = """\
<div id="topbar">
  <button class="btn" id="btn-sidebar" title="Toggle sidebar (S)">
    <svg viewBox="0 0 20 20"><path d="M2 5h16v1.5H2zm0 4h16v1.5H2zm0 4h16v1.5H2z"/></svg>
  </button>
  <span class="title" id="doc-title"></span>
  <span class="meta" id="doc-meta"></span>
  <div id="page-nav">
    <button class="btn" id="btn-prev" title="Previous page (\u2190)">\u2190</button>
    <input type="number" id="page-input" value="1" min="1" max="__TOTAL__">
    <span style="color:#6c7086; font-size:12px;">/ __TOTAL__</span>
    <button class="btn" id="btn-next" title="Next page (\u2192)">\u2192</button>
  </div>
  <button class="btn" id="btn-zoom-out" title="Zoom out (-)">\u2212</button>
  <span id="zoom-label" style="font-size:12px; min-width:36px; text-align:center;">100%</span>
  <button class="btn" id="btn-zoom-in" title="Zoom in (+)">+</button>
  <button class="btn" id="btn-zoom-fit" title="Fit to window (F)">Fit</button>
  <button class="btn" id="btn-theme" title="Toggle dark/light mode">\u2600</button>
  <button class="btn" id="btn-print" title="Print">\U0001f5ce</button>
</div>
"""

_TEMPLATE_BODY_OPEN = """\
<div id="body">
  <div id="sidebar">
    <div id="search-box">
      <input type="search" id="search-input" placeholder="\U0001f50d Search document..." autocomplete="off">
    </div>
    <div id="search-results"></div>
    <div id="toc-panel">
      <div class="toc-label">Contents</div>
"""

_TEMPLATE_SIDEBAR_CLOSE = """\
    </div>
  </div>
  <div id="viewer" class="zoom-100">
"""

_TEMPLATE_BODY_CLOSE = """\
  </div>
</div>
</div>
"""

_TEMPLATE_SCRIPT_OPEN = """\
<script>
"use strict";
"""

_TEMPLATE_SCRIPT_VARS = """\
const DOC_TITLE   = "__TITLE__";
const DOC_AUTHORS = "__AUTHORS__";
const DOC_DATE    = "__DATE__";
"""

_TEMPLATE_SCRIPT_BODY = """\
// ── state ──────────────────────────────────────────────────────────────────
let currentPage = 1;
const ZOOM_STEPS = [75, 100, 125, 150];
let zoomIdx = 1;

// ── element refs ───────────────────────────────────────────────────────────
const viewer        = document.getElementById("viewer");
const sidebar       = document.getElementById("sidebar");
const tocPanel      = document.getElementById("toc-panel");
const searchResults = document.getElementById("search-results");
const searchInput   = document.getElementById("search-input");
const pageInput     = document.getElementById("page-input");
const zoomLabel     = document.getElementById("zoom-label");

// ── init ───────────────────────────────────────────────────────────────────
(function init() {
  document.getElementById("doc-title").textContent = DOC_TITLE;
  const metaParts = [];
  if (DOC_AUTHORS) metaParts.push(DOC_AUTHORS);
  if (DOC_DATE)    metaParts.push(DOC_DATE);
  document.getElementById("doc-meta").textContent = metaParts.join(" \u00b7 ");

  const savedTheme = localStorage.getItem("typst-web-theme");
  if (savedTheme) document.documentElement.setAttribute("data-theme", savedTheme);

  if (localStorage.getItem("typst-web-sidebar") === "collapsed")
    sidebar.classList.add("collapsed");

  const savedZoom = localStorage.getItem("typst-web-zoom");
  if (savedZoom !== null) { zoomIdx = parseInt(savedZoom, 10); applyZoom(); }

  setupPageObserver();
})();

// ── sidebar toggle ─────────────────────────────────────────────────────────
document.getElementById("btn-sidebar").addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  localStorage.setItem("typst-web-sidebar",
    sidebar.classList.contains("collapsed") ? "collapsed" : "open");
});

// ── theme ──────────────────────────────────────────────────────────────────
document.getElementById("btn-theme").addEventListener("click", () => {
  const cur  = document.documentElement.getAttribute("data-theme");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("typst-web-theme", next);
});

// ── print ──────────────────────────────────────────────────────────────────
document.getElementById("btn-print").addEventListener("click", () => window.print());

// ── zoom ───────────────────────────────────────────────────────────────────
function applyZoom() {
  if (zoomIdx < 0) {
    viewer.className = "zoom-fit";
    zoomLabel.textContent = "Fit";
  } else {
    viewer.className = "zoom-" + ZOOM_STEPS[zoomIdx];
    zoomLabel.textContent = ZOOM_STEPS[zoomIdx] + "%";
  }
  localStorage.setItem("typst-web-zoom", zoomIdx);
}

document.getElementById("btn-zoom-in").addEventListener("click", () => {
  if (zoomIdx < ZOOM_STEPS.length - 1) { zoomIdx++; applyZoom(); }
});
document.getElementById("btn-zoom-out").addEventListener("click", () => {
  if (zoomIdx > 0) { zoomIdx--; applyZoom(); }
});
document.getElementById("btn-zoom-fit").addEventListener("click", () => {
  zoomIdx = (zoomIdx === -1) ? 1 : -1;
  applyZoom();
});

// ── page navigation ────────────────────────────────────────────────────────
function scrollToPage(n) {
  n = Math.max(1, Math.min(TOTAL_PAGES, n));
  const el = document.getElementById("page-" + n);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  currentPage = n;
  pageInput.value = n;
}

document.getElementById("btn-prev").addEventListener("click", () => scrollToPage(currentPage - 1));
document.getElementById("btn-next").addEventListener("click", () => scrollToPage(currentPage + 1));
pageInput.addEventListener("change", () => scrollToPage(parseInt(pageInput.value, 10) || 1));

// ── TOC navigation ─────────────────────────────────────────────────────────
document.querySelectorAll(".toc-item").forEach(link => {
  link.addEventListener("click", e => {
    e.preventDefault();
    const slug = link.dataset.slug;
    const heading = HEADINGS.find(h => h.slug === slug);
    if (!heading) return;
    const q = heading.text.toLowerCase();
    for (let i = 0; i < SEARCH_INDEX.length; i++) {
      if (SEARCH_INDEX[i].text.toLowerCase().includes(q)) {
        scrollToPage(SEARCH_INDEX[i].page);
        return;
      }
    }
  });
});

// ── page observer ──────────────────────────────────────────────────────────
function setupPageObserver() {
  const pages = document.querySelectorAll(".page-wrapper");
  if (!pages.length) return;
  const obs = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting && entry.intersectionRatio >= 0.3) {
        const n = parseInt(entry.target.dataset.page, 10);
        if (n !== currentPage) {
          currentPage = n;
          pageInput.value = n;
          updateTocActive(n);
        }
      }
    }
  }, { root: viewer, threshold: 0.3 });
  pages.forEach(p => obs.observe(p));
}

function updateTocActive(pageNum) {
  const pageText = (SEARCH_INDEX[pageNum - 1]?.text || "").toLowerCase();
  document.querySelectorAll(".toc-item").forEach(item => item.classList.remove("active"));
  let bestMatch = null;
  document.querySelectorAll(".toc-item").forEach(item => {
    const h = HEADINGS.find(x => x.slug === item.dataset.slug);
    if (h && pageText.includes(h.text.toLowerCase())) bestMatch = item;
  });
  if (bestMatch) {
    bestMatch.classList.add("active");
    bestMatch.scrollIntoView({ block: "nearest" });
  }
}

// ── search ─────────────────────────────────────────────────────────────────
let searchTimeout = null;

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(doSearch, 200);
});
searchInput.addEventListener("search", doSearch);

function doSearch() {
  const q = searchInput.value.trim().toLowerCase();
  document.querySelectorAll(".page-highlight").forEach(el => el.classList.remove("page-highlight"));

  if (q.length < 2) {
    searchResults.classList.remove("visible");
    tocPanel.classList.remove("hidden");
    searchResults.innerHTML = "";
    return;
  }

  tocPanel.classList.add("hidden");
  searchResults.classList.add("visible");

  const results = [];
  for (const entry of SEARCH_INDEX) {
    const idx = entry.text.toLowerCase().indexOf(q);
    if (idx !== -1) {
      const start = Math.max(0, idx - 40);
      const end   = Math.min(entry.text.length, idx + q.length + 60);
      let snippet = (start > 0 ? "\u2026" : "") + entry.text.slice(start, end) + (end < entry.text.length ? "\u2026" : "");
      const re = new RegExp("(" + q.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&") + ")", "gi");
      snippet = snippet.replace(re, "<mark>$1</mark>");
      results.push({ page: entry.page, snippet });
    }
  }

  if (!results.length) {
    searchResults.innerHTML = '<div class="search-result"><div class="sr-snippet">No results found.</div></div>';
    return;
  }

  searchResults.innerHTML = results.slice(0, 50).map(r =>
    `<div class="search-result" data-page="${r.page}">` +
    `<div class="sr-page">Page ${r.page}</div>` +
    `<div class="sr-snippet">${r.snippet}</div>` +
    `</div>`
  ).join("");

  results.forEach(r => {
    const el = document.getElementById("page-" + r.page);
    if (el) el.classList.add("page-highlight");
  });

  searchResults.querySelectorAll(".search-result").forEach(el => {
    el.addEventListener("click", () => scrollToPage(parseInt(el.dataset.page, 10)));
  });
}

// ── keyboard shortcuts ─────────────────────────────────────────────────────
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;
  switch (e.key) {
    case "ArrowRight": case "ArrowDown": case "PageDown":
      e.preventDefault(); scrollToPage(currentPage + 1); break;
    case "ArrowLeft": case "ArrowUp": case "PageUp":
      e.preventDefault(); scrollToPage(currentPage - 1); break;
    case "Home": e.preventDefault(); scrollToPage(1); break;
    case "End":  e.preventDefault(); scrollToPage(TOTAL_PAGES); break;
    case "s": case "S":
      sidebar.classList.toggle("collapsed"); break;
    case "f": case "F":
      searchInput.focus(); e.preventDefault(); break;
    case "+": case "=":
      if (zoomIdx < ZOOM_STEPS.length - 1) { zoomIdx++; applyZoom(); } break;
    case "-":
      if (zoomIdx > 0) { zoomIdx--; applyZoom(); } break;
  }
});
"""

_TEMPLATE_CLOSE = """\
</script>
</body>
</html>
"""
