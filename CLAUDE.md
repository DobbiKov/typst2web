# typst-to-web

Converts a Typst `.typ` document into a self-contained HTML page with a sidebar TOC, dark/light theme, and fully rendered math. No CDN dependencies.

## Pipeline (in order)

```
cli.py::main()
  1. Collect math.op names from raw *.typ files (preamble.typ etc.)
  2. preprocess_file(source_transform=_rewrite_mathop_textmode)
       → replaces $...$ and canvas blocks with html.elem placeholders
       → extracts #sketch[```js...```] blocks (pre-pass regex, before state machine)
       → rewrites #Bern($x$) → $Bern(x)$ before extraction
  3. _inject_thm_overrides() on each source file
       → replaces theorem env functions (#thm, #defn, #rmk …) with figure()-
         wrapped html.elem divs so they survive Typst HTML export
  4. compile_to_html()  — calls typst compile --format html
  5. compile_math_to_svgs()  — batch-compiles all math to SVG (one typst run)
  6. compile_figures_to_svg()  — compiles #figure blocks that contain cetz
  7. compile_canvases_to_svgs()  — compiles extracted canvas blocks
  8. build_web_page()  — stitches everything into _TEMPLATE
       → injects p5.js bundle into <head> (only when sketches are present)
       → injects sketch containers + per-sketch <script> into content
```

## Module map

| File | Role |
|---|---|
| `cli.py` | Entry point, math.op rewrite, theorem override injection, orchestration |
| `preprocessor.py` | Replaces math/canvas/sketch with `html.elem` placeholders; `preprocess_file()` recurses into `#include`d files |
| `compiler.py` | Thin wrapper around the `typst` CLI binary |
| `math_renderer.py` | Batch-compiles math expressions to SVG; `_clean_svg()` strips white bg, sets `fill="currentColor"`, converts pt→em |
| `figure_renderer.py` | `compile_figures_to_svg()` for cetz figures; `compile_canvases_to_svgs()` for canvas blocks |
| `postprocessor.py` | `build_web_page()`: injects SVGs + sketches into HTML, bundles p5.js, builds TOC, renders `_TEMPLATE` |
| `parser.py` | Extracts headings/title/authors/labels from raw `.typ` source |
| `builder.py` | (older HTML assembler, largely superseded by postprocessor) |
| `static/p5.min.js` | Vendored p5.js v1.11.3 bundle; embedded inline only when document contains `#sketch` blocks |

## Key data structures

| Dataclass | Module | Fields |
|---|---|---|
| `MathExpr` | `preprocessor.py` | `index`, `body`, `display`, `label`, `numbered` |
| `CanvasExpr` | `preprocessor.py` | `index`, `body`, `source_path` |
| `SketchExpr` | `preprocessor.py` | `index`, `js_body`, `source_path` |
| `PreprocessResult` | `preprocessor.py` | `source`, `expressions`, `canvases`, `sketches`, `included` |

## Key design constraints

**Why `figure()` for theorem environments**: `html.elem` divs inside plain content survive Typst HTML export. But they must be wrapped in `figure(kind: "_tw-" + kind)` to be labelable via `@label` and get auto-incrementing counters via `counter(figure.where(kind:...)).display()`.

**Why `source_transform` before preprocessing**: math.op calls like `#Bern ($theta$)` need rewriting to `$Bern(theta)$` *before* math extraction, so the operator name is included in the SVG, not dropped.

**Why inject theorem overrides after first import block only**: some files have `#import "figures/..."` mid-document. Inserting overrides after the *last* import would push them past all theorem calls. `_inject_thm_overrides` scans only the initial consecutive import block.

**Math SVG sizing**: compiled at `_MATH_FONT_PT = 11pt`; dimensions converted to `em` so math scales with surrounding text. `vertical-align` is moved from the SVG to the `<span>` wrapper so `display:inline-block` expands the line box correctly.

**Dark theme**: math SVG glyphs use `fill="currentColor"` → inherit `color` CSS. Canvas/figure SVGs (cetz diagrams) get `filter: invert(1) hue-rotate(180deg)` in dark mode.

**Math placeholder regex**: uses backreference `<(span|div)[^>]*\bdata-math="N"[^>]*>.*?</\1>` (not `</(?:span|div)>`) to avoid a display-math `<div>` consuming the first `</span>` of nested inline content.

**Why `#sketch` uses a pre-pass regex, not the state machine**: sketch blocks contain a triple-backtick raw code block inside `[...]`. The state machine's `_extract_balanced` does not handle triple backticks, so JS code containing `[` or `]` would corrupt the bracket-depth counter. The pre-pass `_SKETCH_RE` regex runs before the state machine and consumes the entire block atomically.

**Why p5.js is in `<head>` not at `</body>`**: sketch `<script>` tags are emitted inline in the document body (right after each `<div id="p5-sketch-N">`). If p5.js were loaded at the end of `<body>`, `p5` would be undefined when those inline scripts execute. Loading in `<head>` ensures `p5` is available before any body content runs. The bundle is only injected when the document has sketches, so non-sketch documents have zero overhead.

**Why DOM elements created in a sketch are auto-parented**: p5.js instance mode only routes `createCanvas()` into the container element passed to `new p5(fn, containerId)`. All other DOM-creating methods (`createSlider`, `createButton`, etc.) default to appending to `<body>`. The sketch wrapper overrides these methods on the `p` instance to call `.parent(containerId)` automatically, keeping all sketch UI self-contained.

**p5.js instance mode**: each sketch is wrapped in `new p5(function(p){ ... }, containerId)`. Users write `p.setup`, `p.draw`, and call all p5 APIs as `p.xxx`. An IIFE around each sketch prevents variable name collisions between multiple sketches on the same page.

## Theorem environments supported

`defn thm lem prop cor rmk ex proof soln claim notation conj insight exer exerstar prob ques fact rmnd todo`
Languages: `en`, `fr`, `ua` (detected from `language: "XX"` in the main `.typ` file).

## Settings system (planned)

Document metadata (title, subtitle, authors) is resolved with this priority chain:

**CLI flags > `typst-web.toml` > parsed from `.typ` source**

### `typst-web.toml` (auto-discovered beside the input `.typ` file)
```toml
[document]
title    = "My Custom Title"
subtitle = "Lecture Notes, Spring 2026"
authors  = ["Alice", "Bob"]
```

### CLI flags (one-off overrides)
```
--title "..."  --subtitle "..."  --author "Alice" --author "Bob"
```

### Fallback: parsed from `.typ`
`parser.py` already reads `#set document(title:, author:)` and the first `= Heading` as a title fallback.

### Implementation notes
- Assemble a `Settings` dataclass in `cli.py::main()` before calling `build_web_page()`.
- `postprocessor.py` / `_TEMPLATE` already has `{{TITLE}}` and `{{AUTHORS_HTML}}`; add `{{SUBTITLE}}` rendered below the title in sidebar and topbar.
- The settings file is optional; if absent, behaviour is unchanged.

## Typical test command

```
python -m typst_web.cli /path/to/main.typ
```
