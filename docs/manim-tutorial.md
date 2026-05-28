# Manim Animations in typst-to-web

typst-to-web supports embedding [manim-web](https://github.com/maloyan/manim-web)
animations directly in your Typst documents using the `#manim` block. Scenes play
automatically in the reader's browser — no server, no Python, no compilation step.

---

## Quick start

````typst
#manim[
  ```js
  const circle = new Circle({ radius: 1.5, color: BLUE });
  await scene.play(new Create(circle, { duration: 1 }));
  await scene.play(new FadeIn(new Text({ text: "Hello!" }), { duration: 0.8 }));
  await scene.wait(1);
  ```
]
````

Compile with:

```
python -m typst_web.cli main.typ
```

---

## How it works

The preprocessor extracts `#manim[` blocks before Typst sees them, exactly as it
does for `#sketch`. An `html.elem` placeholder survives the Typst HTML export;
the postprocessor replaces it with:

1. A `<div id="manim-N" class="manim-container">` sized to the column width
2. An inert `<script type="text/x-manim-code">` holding your JS (avoids escaping issues)
3. A `<script>` that reads `window._mw`, constructs a `Scene`, and runs your code
   via `AsyncFunction` with all manim-web exports injected as named parameters
4. The manim-web bundle (`~2.4 MB`), embedded once in `<head>` when the document
   has any `#manim` blocks

The bundle's ES-module `export { ... }` is rewritten at build time to
`window._mw = { ... }` so it loads as a plain `<script>` tag — this is what makes
it work on `file://` pages (blob-URL `import()` is blocked by most browsers when
the page has a null origin).

---

## Differences from the manim-web library docs

The manim-web [README](https://github.com/maloyan/manim-web) shows usage via npm
with TypeScript or framework components. Inside a `#manim` block you write plain
JavaScript that runs differently:

### No imports, no class

The library docs show:

```ts
// library docs — TypeScript, npm project
import { Scene, Circle, Create, BLUE } from 'manim-web';

class MyScene extends Scene {
  async construct() {
    const c = new Circle({ color: BLUE });
    await this.play(new Create(c));
  }
}
```

In a `#manim` block you write none of that:

```js
// typst-to-web — just the body of construct()
const c = new Circle({ color: BLUE });
await scene.play(new Create(c, { duration: 1 }));
```

- **No `import`** — all 587 exports are available as bare names automatically
- **No class, no `construct()`** — your code *is* the construct body
- **`scene` is pre-created** — sized to the container, passed in for you
- **Top-level `await`** — works out of the box; the whole block runs as an async function

### `duration` not `runTime`

The library uses `duration` (in seconds) as the animation option. Some
community examples use `runTime` — that does not work here:

```js
// correct
await scene.play(new Create(circle, { duration: 1.5 }));

// wrong — silently ignored, uses default duration
await scene.play(new Create(circle, { runTime: 1.5 }));
```

### `coordsToPoint` not `c2p`

The Axes object maps graph coordinates to 3-D scene coordinates:

```js
const axes = new Axes({ xRange: [-5, 5], yRange: [-3, 3] });
await scene.play(new Create(axes));

// correct
const pt = axes.coordsToPoint(2, 1.5);  // returns [x, y, z]

// wrong — method does not exist
const pt = axes.c2p(2, 1.5);
```

### Colors are constants, not `Color.fromHex()`

There is no `Color` class with a `fromHex` method. Use the exported named constants,
or pass a CSS hex string directly to any `color:` option:

```js
// named constants (recommended)
new Circle({ color: BLUE });
new Circle({ color: RED_C });
new Line({ color: WHITE });
new Text({ text: "hi", color: YELLOW });

// hex strings also work
new Circle({ color: "#3b82f6" });
```

Available named colors: `BLACK`, `WHITE`, `GRAY`, `RED`, `ORANGE`, `YELLOW`,
`GREEN`, `TEAL`, `BLUE`, `PURPLE`, `MAROON`, `GOLD`, `PINK` — each with variants
`_A` through `_E` (lightest to darkest). Direction constants: `UP`, `DOWN`,
`LEFT`, `RIGHT`, `ORIGIN`, `UL`, `UR`, `DL`, `DR`, `IN`, `OUT`.

### `Text` takes an options object, not a bare string

```js
// correct
const label = new Text({ text: "95%", fontSize: 36, color: BLUE_C });

// wrong — constructor expects an object
const label = new Text("95%");
```

### `Brace` takes a mobject as first argument

```js
// correct — mobject is positional, options are second arg
const brace = new Brace(myRectangle, { direction: DOWN });

// wrong — options object as only arg does not work
const brace = new Brace({ mobject: myRectangle, direction: DOWN });
```

### `FunctionGraph` requires `axes`

Without an `axes` reference the graph is drawn in raw scene space (units are
meters, not pixels), and will likely appear invisible. Always pass the axes:

```js
const axes = new Axes({ xRange: [-4, 4], yRange: [0, 0.5] });
await scene.play(new Create(axes));

const curve = new FunctionGraph({
  func: (x) => Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI),
  xRange: [-4, 4],
  axes: axes,      // required for correct positioning and scaling
  color: BLUE_C,
});
await scene.play(new Create(curve, { duration: 1.2 }));
```

### Filling a region under a curve

`ParametricFunction` supports `fillOpacity` as a direct property (not a
constructor option). To fill a closed region, trace the boundary as a loop —
curve up, baseline back:

```js
const region = new ParametricFunction({
  func: (t) => {
    if (t <= 1) {
      const x = -1.96 + t * 2 * 1.96;
      return [x, phi(x)];       // bell curve from -Z to +Z
    } else {
      const x = 1.96 - (t - 1) * 2 * 1.96;
      return [x, 0];            // baseline back from +Z to -Z
    }
  },
  tRange: [0, 2],
  numSamples: 120,
  axes: axes,
  strokeWidth: 0,
});
region.fillOpacity = 0.3;       // set after construction
await scene.play(new FadeIn(region, { duration: 0.6 }));
```

If you set `strokeWidth: 0` only, the region still appears but without an outline.
Setting `fillOpacity` to `0` (the default) makes it invisible — remember to set it.

---

## Common objects

| Object | Key options |
|---|---|
| `Circle` | `radius`, `color`, `fillOpacity`, `strokeWidth` |
| `Rectangle` | `width`, `height`, `color`, `fillOpacity`, `strokeWidth` |
| `Line` | `start`, `end`, `color`, `strokeWidth` |
| `DashedLine` | `start`, `end`, `color`, `strokeWidth`, `dashLength`, `dashRatio` |
| `Arrow` | `start`, `end`, `color`, `strokeWidth`, `tipLength` |
| `Dot` | `point`, `radius`, `color`, `fillOpacity` |
| `Axes` | `xRange`, `yRange`, `xLength`, `yLength`, `color`, `tipLength` |
| `FunctionGraph` | `func`, `xRange`, `axes`, `color`, `strokeWidth`, `numSamples` |
| `ParametricFunction` | `func`, `tRange`, `axes`, `color`, `strokeWidth`, `numSamples` |
| `Text` | `text`, `fontSize`, `color`, `fontFamily`, `fontWeight` |
| `Brace` | `(mobject, { direction, buff, color })` — mobject is positional |

## Common animations

| Animation | What it does |
|---|---|
| `Create(mob)` | Draw border/stroke progressively |
| `FadeIn(mob)` | Fade in from transparent |
| `FadeOut(mob)` | Fade out to transparent |
| `Write(mob)` | Write text letter by letter |
| `Transform(a, b)` | Morph one mobject into another |
| `GrowFromCenter(mob)` | Scale up from a point |
| `Shift(mob, direction)` | Translate by a vector |

All animations accept `{ duration: N }` (seconds) as an options object passed
to the constructor. Pass multiple animations to a single `scene.play()` call to
run them in parallel:

```js
// parallel
await scene.play(
  new Create(leftLine,  { duration: 0.8 }),
  new Create(rightLine, { duration: 0.8 }),
);

// sequential
await scene.play(new Create(circle, { duration: 1 }));
await scene.play(new FadeIn(label,  { duration: 0.6 }));
```

Use `await scene.wait(seconds)` to hold the frame before the next step.

---

## Positioning

Mobjects live in a 3-D scene with the camera looking down the z-axis.
Default frame is 14 units wide × 8 units tall, centred at the origin.
Move objects with `mob.moveTo([x, y, 0])`.

When using `Axes`, always convert graph coordinates to scene coordinates with
`axes.coordsToPoint(x, y)` — it returns a `[x, y, z]` triple:

```js
const axes = new Axes({
  xRange: [-5, 5, 1],
  yRange: [-3, 3, 1],
  xLength: 9,
  yLength: 5,
});
await scene.play(new Create(axes));

const dot = new Dot({ color: YELLOW });
dot.moveTo(axes.coordsToPoint(2, 1));   // places dot at graph (2, 1)
await scene.play(new FadeIn(dot));
```

---

## Patterns

### Annotated function graph

```js
const axes = new Axes({
  xRange: [-3, 3, 1],
  yRange: [-1.5, 1.5, 0.5],
  xLength: 8,
  yLength: 5,
  color: WHITE,
});
await scene.play(new Create(axes, { duration: 0.7 }));

const curve = new FunctionGraph({
  func: (x) => Math.sin(x),
  axes: axes,
  color: BLUE_C,
  strokeWidth: 3,
});
await scene.play(new Create(curve, { duration: 1.2 }));

const lbl = new Text({ text: "sin(x)", fontSize: 32, color: BLUE_C });
lbl.moveTo(axes.coordsToPoint(2.2, 1.2));
await scene.play(new Write(lbl, { duration: 0.7 }));

await scene.wait(1.5);
```

### Morphing shapes

```js
const square = new Rectangle({ width: 2, height: 2, color: RED });
await scene.play(new Create(square, { duration: 0.8 }));

const circle = new Circle({ radius: 1.2, color: BLUE });
await scene.play(new Transform(square, circle, { duration: 1.2 }));

await scene.wait(1);
```

### Step-by-step reveal

```js
const title = new Text({ text: "Central Limit Theorem", fontSize: 40 });
title.moveTo([0, 2.5, 0]);
await scene.play(new Write(title, { duration: 1 }));

const line1 = new Text({ text: "As n \u2192 \u221E,", fontSize: 32, color: YELLOW });
line1.moveTo([0, 0.5, 0]);
await scene.play(new FadeIn(line1, { duration: 0.7 }));

const line2 = new Text({ text: "X\u0305 \u2248 N(\u03BC, \u03C3\u00B2/n)", fontSize: 32, color: GREEN_C });
line2.moveTo([0, -0.8, 0]);
await scene.play(new FadeIn(line2, { duration: 0.7 }));

await scene.wait(2);
```

---

## Multiple manim blocks

You can have as many `#manim` blocks as you like. Each gets its own container
and independent `Scene` instance. The 2.4 MB bundle is only embedded once
regardless of how many scenes the document has.

---

## Limitations

**No Python Manim API parity.** manim-web covers a large subset of Manim's
API but not everything. 3-D cameras, `VGroup`, `Tex` (as opposed to `MathTex`),
and some animation types may behave differently or not exist. When in doubt,
check the exported names — all 587 exports are available as bare names in
your code.

**`MathTex` requires network fonts.** `MathTex` uses KaTeX internally, which
loads web fonts. On `file://` pages without internet access it may render as
boxes. Use `Text` with Unicode math symbols as a reliable offline alternative.

**No interactivity.** Unlike `#sketch` (p5.js), manim-web scenes run as a
one-shot timeline — there is no draw loop, no mouse input, no sliders.
Use `#sketch` when you need user interaction.

**Errors are console-only.** If your scene throws (bad constructor args,
undefined name, etc.), the container stays blank. Open the browser DevTools
console — the error is logged with the container id, e.g. `[manim-0] TypeError: ...`.

**`</script>` in string literals.** Automatically escaped to `<\/script>` —
handled transparently, same as `#sketch`.

---

## Reference: `#manim` syntax

```
#manim[
  ```js
  <your JavaScript here>
  ```
]
```

- Language tag must be `js` or `javascript`.
- The opening ` ```js ` must be on its own line after `[`.
- The closing ` ``` ` must be on its own line before `]`.
- Whitespace between `#manim` and `[` is allowed.
- The block can appear anywhere in markup context.
