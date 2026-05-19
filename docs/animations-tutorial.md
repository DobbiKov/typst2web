# Interactive Animations in typst-to-web

typst-to-web supports embedding live, interactive p5.js sketches directly in
your Typst documents using the `#sketch` block. Sketches run in the reader's
browser — no server, no compilation step.

---

## Quick start

```typst
#sketch[
  ```js
  p.setup = function() {
    p.createCanvas(400, 300);
  };

  p.draw = function() {
    p.background(240);
    p.fill(100, 150, 255);
    p.circle(p.mouseX, p.mouseY, 50);
  };
  ```
]
```

That's it. The `p` object gives you the full
[p5.js API](https://p5js.org/reference/). Compile with:

```
python -m typst_web.cli main.typ
```

---

## How it works

The preprocessor detects `#sketch[` and extracts the JavaScript before Typst
even sees the block. It emits an `html.elem` placeholder that survives the
Typst HTML export, then the postprocessor replaces it with:

1. A `<div id="p5-sketch-N">` container
2. An inline `<script>` that calls `new p5(fn, "p5-sketch-N")` in instance mode
3. p5.js itself, bundled once into `<head>` (only when the document has sketches)

---

## Writing sketches: instance mode

All sketches run in **p5.js instance mode**. Instead of bare globals, every
p5 function is called on the `p` object:

| Global mode (won't work) | Instance mode (correct) |
|---|---|
| `createCanvas(400, 300)` | `p.createCanvas(400, 300)` |
| `background(220)` | `p.background(220)` |
| `fill(255, 0, 0)` | `p.fill(255, 0, 0)` |
| `random(0, 1)` | `p.random(0, 1)` |
| `mouseX` | `p.mouseX` |
| `HALF_PI` | `p.HALF_PI` |

The lifecycle methods are assigned as properties of `p`:

```js
p.setup = function() { ... };
p.draw  = function() { ... };
p.mousePressed  = function() { ... };
p.keyPressed    = function() { ... };
```

Helper functions and state variables live in the sketch's own scope — no
`p.` prefix needed for your own code:

```js
let angle = 0;

function spiral(t) {        // plain function — fine
  return { x: t * p.cos(t), y: t * p.sin(t) };
}

p.draw = function() {
  angle += 0.02;            // plain variable — fine
  let pt = spiral(angle);   // call your own function — fine
  p.point(200 + pt.x, 200 + pt.y);
};
```

---

## Adding UI controls

`createSlider`, `createButton`, and other DOM elements are automatically
placed inside the sketch container (not scattered in the page body):

```js
let speedSlider;

p.setup = function() {
  p.createCanvas(500, 200);

  speedSlider = p.createSlider(0, 10, 3, 0.1);
  speedSlider.style('width', '200px');
  speedSlider.style('accent-color', '#7c3aed');

  let resetBtn = p.createButton('Reset');
  resetBtn.style('margin-left', '10px');
  resetBtn.mousePressed(function() { angle = 0; });
};
```

The slider or button appears directly below the canvas, inside the sketch
container div.

---

## Patterns

### Animation loop

```js
let t = 0;

p.setup = function() {
  p.createCanvas(500, 300);
};

p.draw = function() {
  p.background(15, 15, 30);
  p.stroke(120, 200, 255);
  p.strokeWeight(2);
  p.noFill();

  p.beginShape();
  for (let x = 0; x <= 500; x += 2) {
    let y = 150 + 80 * p.sin(x * 0.02 + t);
    p.vertex(x, y);
  }
  p.endShape();

  t += 0.05;
};
```

### Slider-driven static plot

```js
let slider;

p.setup = function() {
  p.createCanvas(500, 280);
  slider = p.createSlider(1, 20, 5, 1);
  slider.style('width', '400px');
};

p.draw = function() {
  let n = slider.value();
  p.background(250);
  // ... draw something that depends on n
};
```

### Mouse interaction

```js
let pts = [];

p.setup = function() {
  p.createCanvas(500, 300);
  p.background(255);
};

p.draw = function() {
  if (p.mouseIsPressed) {
    pts.push({ x: p.mouseX, y: p.mouseY });
  }
  p.background(255, 255, 255, 10);  // fading trail
  p.fill(80, 120, 220);
  p.noStroke();
  for (let pt of pts) p.circle(pt.x, pt.y, 8);
};
```

### Using `drawingContext` for canvas features p5 doesn't expose

```js
p.draw = function() {
  // Dashed lines
  p.drawingContext.setLineDash([6, 4]);
  p.line(50, 100, 450, 100);
  p.drawingContext.setLineDash([]);

  // Drop shadow
  p.drawingContext.shadowColor = 'rgba(0,0,0,0.3)';
  p.drawingContext.shadowBlur = 8;
  p.rect(200, 120, 100, 60);
  p.drawingContext.shadowBlur = 0;
};
```

### Timed events (adding data over time)

```js
let data = [];
let lastMs = -1000;

p.draw = function() {
  if (p.millis() - lastMs > 500) {   // every 500 ms
    data.push(p.random(50, 250));
    lastMs = p.millis();
  }
  // draw data...
};
```

---

## Multiple sketches

You can have as many `#sketch` blocks as you like in a document. Each one
is fully isolated — variables, state, and DOM elements from one sketch
cannot interfere with another.

```typst
= First demo

#sketch[
  ```js
  p.setup = function() { p.createCanvas(300, 200); };
  p.draw  = function() { p.background(220); };
  ```
]

= Second demo

#sketch[
  ```js
  p.setup = function() { p.createCanvas(300, 200); };
  p.draw  = function() { p.background(180, 200, 255); };
  ```
]
```

p5.js is only bundled once regardless of how many sketches the document has.

---

## Limitations

**No global mode.** You must use `p.xxx` for all p5 API calls. Bare calls
like `background(220)` will throw `ReferenceError` at runtime.

**No p5 sound/dom add-ons.** Only the core p5.js library is bundled. If you
need p5.sound, you'd have to add it to `typst_web/static/` and extend the
postprocessor.

**Sketch code is not validated at build time.** Syntax errors in the JS will
silently produce a broken sketch in the browser. Check the browser console if
a sketch doesn't appear.

**`</script>` in string literals.** If your JS contains the literal string
`</script>` (e.g. in a comment), it will be automatically escaped to
`<\/script>` by the preprocessor — this is handled for you transparently.

**Canvas width is capped automatically.** If you pass a width larger than the
container to `p.createCanvas()`, it is silently clamped to the container's
actual width — so sketches never overflow on narrow screens. Use the injected
`_containerWidth` variable to make your drawing code adapt too:

```js
p.setup = function() {
  p.createCanvas(_containerWidth, 300);  // always fits
};
p.draw = function() {
  p.line(0, 150, _containerWidth, 150);  // full width line
};
```

---

## Reference: `#sketch` syntax

```
#sketch[
  ```js
  <your JavaScript here>
  ```
]
```

- The language tag must be `js` or `javascript` (case-sensitive).
- The opening ` ```js ` must be on its own line after `[`.
- The closing ` ``` ` must be on its own line before `]`.
- Whitespace between `#sketch` and `[` is allowed.
- The block can appear anywhere in markup context (top level, inside sections,
  inside theorem environments, etc.).
