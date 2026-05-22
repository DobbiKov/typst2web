# typst-to-web

Converts a Typst `.typ` document into a self-contained HTML page — sidebar TOC,
dark/light theme, fully rendered math, and interactive p5.js animations. No CDN
dependencies, no JavaScript math rendering.

## Features

- **Math** — every `$...$` expression is compiled to SVG by Typst and injected inline; scales with text, works in dark mode
- **Cetz figures** — `#canvas({...})` blocks are compiled to SVG separately and embedded
- **Theorem environments** — `#thm`, `#defn`, `#lem`, and 17 others, with auto-counters and `@label` cross-references
- **Interactive sketches** — embed live p5.js animations with `#sketch[```js ... ```]`
- **Settings** — title/subtitle/authors via CLI flags, `typst-web.toml`, or parsed from the `.typ` source
- **Self-contained output** — one `.html` file, no external assets

## Installation

```sh
pip install -e .
```

Requires Python ≥ 3.10 and the [`typst` CLI](https://github.com/typst/typst) on your `PATH`.

## Usage

```sh
python -m typst_web.cli path/to/main.typ
# or, after pip install:
typst-web path/to/main.typ
```

Output is written next to the input file as `main.html`.

### Options

```
-o OUTPUT           output path (default: input with .html extension)
--root DIR          typst root directory
--font-path DIR     extra font search path (repeatable)
--title TEXT        override document title
--subtitle TEXT     override subtitle
--author NAME       override author (repeatable)
--date TEXT         override date
--version           print versions
```

## Quick examples

### Math

```typst
The sample mean $overline(X)$ satisfies

$ overline(X) approx cal(N)(mu, sigma^2 / n) . $
```

### Interactive animation

```typst
#sketch[
  ````js
  p.setup = function() { p.createCanvas(500, 300); };
  p.draw  = function() {
    p.background(15, 15, 30);
    p.fill(120, 200, 255);
    p.circle(p.mouseX, p.mouseY, 40);
  };
  ````
]
```

All p5.js calls use the `p.` prefix (instance mode). Sliders and buttons
created with `p.createSlider()` / `p.createButton()` are automatically placed
inside the sketch container. See [`docs/animations-tutorial.md`](docs/animations-tutorial.md) for full docs.

Create animations interactively with Claude using [the artifact](https://claude.ai/public/artifacts/4b8710d1-22d3-44ca-848d-d0340d170825)

### Settings file

Drop a `typst-web.toml` next to your `.typ` file:

```toml
[document]
title    = "Lecture Notes"
subtitle = "Spring 2026"
authors  = ["Alice", "Bob"]
```

## Project layout

```
typst_web/
  cli.py            entry point
  preprocessor.py   extract math / canvas / sketch blocks → placeholders
  compiler.py       thin wrapper around typst CLI
  math_renderer.py  batch-compile math to SVG
  figure_renderer.py  compile cetz figures/canvases to SVG
  postprocessor.py  inject SVGs, bundle p5.js, assemble final HTML
  static/
    p5.min.js       vendored p5.js v1.11.3
examples/
  conf-int/         confidence interval demo with two interactive sketches
docs/
  animations-tutorial.md
```

## Development

```sh
# run on an example
python -m typst_web.cli examples/conf-int/main.typ

# check versions
typst-web --version
```

Architecture and design decisions are documented in [`CLAUDE.md`](CLAUDE.md).
