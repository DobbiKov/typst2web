# typst-to-web

Converts a Typst `.typ` document into a self-contained HTML page with a sidebar TOC, dark/light theme, and fully rendered math. No CDN dependencies.

## Pipeline (in order)

```
cli.py::main()
  1. Collect math.op names from raw *.typ files (preamble.typ etc.)
  2. preprocess_file(source_transform=_rewrite_mathop_textmode)
       → replaces $...$ and canvas blocks with html.elem placeholders
       → rewrites #Bern($x$) → $Bern(x)$ before extraction
  3. _inject_thm_overrides() on each source file
       → replaces theorem env functions (#thm, #defn, #rmk …) with figure()-
         wrapped html.elem divs so they survive Typst HTML export
  4. compile_to_html()  — calls typst compile --format html
  5. compile_math_to_svgs()  — batch-compiles all math to SVG (one typst run)
  6. compile_figures_to_svg()  — compiles #figure blocks that contain cetz
  7. compile_canvases_to_svgs()  — compiles extracted canvas blocks
  8. build_web_page()  — stitches everything into _TEMPLATE
```

## Module map

| File | Role |
|---|---|
| `cli.py` | Entry point, math.op rewrite, theorem override injection, orchestration |
| `preprocessor.py` | Replaces math/canvas with `html.elem` placeholders; `preprocess_file()` recurses into `#include`d files |
| `compiler.py` | Thin wrapper around the `typst` CLI binary |
| `math_renderer.py` | Batch-compiles math expressions to SVG; `_clean_svg()` strips white bg, sets `fill="currentColor"`, converts pt→em |
| `figure_renderer.py` | `compile_figures_to_svg()` for cetz figures; `compile_canvases_to_svgs()` for canvas blocks |
| `postprocessor.py` | `build_web_page()`: injects SVGs into HTML, builds TOC, renders `_TEMPLATE` |
| `parser.py` | Extracts headings/title/authors/labels from raw `.typ` source |
| `builder.py` | (older HTML assembler, largely superseded by postprocessor) |

## Key design constraints

**Why `figure()` for theorem environments**: `html.elem` divs inside plain content survive Typst HTML export. But they must be wrapped in `figure(kind: "_tw-" + kind)` to be labelable via `@label` and get auto-incrementing counters via `counter(figure.where(kind:...)).display()`.

**Why `source_transform` before preprocessing**: math.op calls like `#Bern ($theta$)` need rewriting to `$Bern(theta)$` *before* math extraction, so the operator name is included in the SVG, not dropped.

**Why inject theorem overrides after first import block only**: some files have `#import "figures/..."` mid-document. Inserting overrides after the *last* import would push them past all theorem calls. `_inject_thm_overrides` scans only the initial consecutive import block.

**Math SVG sizing**: compiled at `_MATH_FONT_PT = 11pt`; dimensions converted to `em` so math scales with surrounding text. `vertical-align` is moved from the SVG to the `<span>` wrapper so `display:inline-block` expands the line box correctly.

**Dark theme**: math SVG glyphs use `fill="currentColor"` → inherit `color` CSS. Canvas/figure SVGs (cetz diagrams) get `filter: invert(1) hue-rotate(180deg)` in dark mode.

**Math placeholder regex**: uses backreference `<(span|div)[^>]*\bdata-math="N"[^>]*>.*?</\1>` (not `</(?:span|div)>`) to avoid a display-math `<div>` consuming the first `</span>` of nested inline content.

## Theorem environments supported

`defn thm lem prop cor rmk ex proof soln claim notation conj insight exer exerstar prob ques fact rmnd todo`
Languages: `en`, `fr`, `ua` (detected from `language: "XX"` in the main `.typ` file).

## Typical test command

```
python -m typst_web.cli /path/to/main.typ
```
