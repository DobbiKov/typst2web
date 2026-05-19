#set document(title: "Confidence Intervals", author: "typst-to-web")
#set page(paper: "a4", margin: (x: 2.5cm, y: 3cm))
#set text(font: "New Computer Modern", size: 11pt)
#set heading(numbering: "1.")
#set math.equation(numbering: "(1)")

#align(center)[
  #text(size: 24pt, weight: "bold")[Confidence Intervals]
  #v(0.5em)
  #text(size: 13pt, fill: gray)[A visual introduction to interval estimation]
  #v(2em)
]

= Setup

Suppose we observe a random sample $X_1, X_2, dots, X_n$ drawn i.i.d. from a
population with *unknown mean* $mu$ and *known standard deviation* $sigma$.
Our goal is not to guess $mu$ with a single number, but to produce an
*interval* that is likely to contain the true value.

By the Central Limit Theorem, the sample mean

$ overline(X) = 1/n sum_(i=1)^n X_i $

is approximately normally distributed:

$ overline(X) approx cal(N) lr((mu, sigma^2 / n)) . $

Standardising gives the *pivot statistic*

$ Z = (overline(X) - mu) / (sigma \/ sqrt(n)) tilde cal(N)(0, 1) , $ <eq-pivot>

which follows a standard normal regardless of $mu$ — a fact we exploit below.

= Constructing the Interval

Fix a *significance level* $alpha in (0, 1)$. Let $z_(alpha\/2)$ denote the
upper $alpha\/2$ quantile of the standard normal, i.e. the value satisfying

$ P(Z > z_(alpha\/2)) = alpha/2 . $

By symmetry of $cal(N)(0,1)$ around zero,

$ P(-z_(alpha\/2) <= Z <= z_(alpha\/2)) = 1 - alpha . $ <eq-coverage>

Substituting the pivot @eq-pivot into @eq-coverage and solving for $mu$:

$ P lr((overline(X) - z_(alpha\/2) dot sigma/sqrt(n) <= mu <= overline(X) + z_(alpha\/2) dot sigma/sqrt(n))) = 1 - alpha . $

The *$(1-alpha)$ confidence interval* for $mu$ is therefore

$ [overline(X) - z_(alpha\/2) dot sigma/sqrt(n), quad overline(X) + z_(alpha\/2) dot sigma/sqrt(n)] . $ <eq-ci>

The half-width $z_(alpha\/2) dot sigma\/sqrt(n)$ is called the *margin of error*.

= Interactive Visualization

The demo below shows the standard normal density. The *blue region* is the
$(1-alpha)$ probability mass — the values $Z$ falls into with that probability.
The *red tails* each carry $alpha\/2$ mass. The dashed lines mark $plus.minus z_(alpha\/2)$.

Drag the slider to change $alpha$ and watch how the interval widens as you
demand higher confidence.

#sketch[
  ```js
  // ── helpers ────────────────────────────────────────────────────────────
  function phi(x) {
    return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
  }

  function normalCDF(x) {
    // Abramowitz & Stegun rational approximation — max error 7.5e-8
    let s = x < 0 ? -1 : 1, a = Math.abs(x);
    let t = 1 / (1 + 0.3275911 * a);
    let poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741
               + t * (-1.453152027 + t * 1.061405429))));
    return 0.5 + 0.5 * s * (1 - poly * Math.exp(-a * a));
  }

  function quantile(prob) {
    let lo = -8, hi = 8;
    for (let i = 0; i < 64; i++) {
      let m = (lo + hi) / 2;
      if (normalCDF(m) < prob) lo = m; else hi = m;
    }
    return (lo + hi) / 2;
  }

  // ── state ───────────────────────────────────────────────────────────────
  let slider;

  // ── setup ───────────────────────────────────────────────────────────────
  p.setup = function() {
    p.createCanvas(640, 300);
    p.textFont('system-ui, sans-serif');

    slider = p.createSlider(1, 49, 10, 1);
    slider.style('width', '510px');
    slider.style('display', 'block');
    slider.style('margin', '8px 65px 0');
    slider.style('accent-color', '#3d6fd4');
    slider.style('cursor', 'pointer');
  };

  // ── draw ────────────────────────────────────────────────────────────────
  p.draw = function() {
    let alpha = slider.value() / 100;
    let z     = quantile(1 - alpha / 2);
    let conf  = (1 - alpha) * 100;

    p.background(250, 249, 253);

    // plot coordinate bounds
    let L = 65, R = 575, T = 42, B = 222;

    let sx = v => p.map(v, -4, 4, L, R);
    let sy = v => p.map(v, 0, 0.42, B, T);

    // ── rejection tails (red) ─────────────────────────────────────────────
    p.noStroke();
    let step = 0.02;
    for (let side of [-1, 1]) {
      let x0 = side < 0 ? -4 : z;
      let x1 = side < 0 ? -z : 4;
      p.fill(215, 60, 55, 85);
      p.beginShape();
      p.vertex(sx(x0), B);
      for (let x = x0; x <= x1 + step / 2; x += step)
        p.vertex(sx(Math.min(x, x1)), sy(phi(Math.min(x, x1))));
      p.vertex(sx(x1), B);
      p.endShape(p.CLOSE);
    }

    // ── confidence region (blue) ──────────────────────────────────────────
    p.fill(50, 110, 210, 60);
    p.beginShape();
    p.vertex(sx(-z), B);
    for (let x = -z; x <= z + step / 2; x += step)
      p.vertex(sx(Math.min(x, z)), sy(phi(Math.min(x, z))));
    p.vertex(sx(z), B);
    p.endShape(p.CLOSE);

    // ── normal curve ──────────────────────────────────────────────────────
    p.stroke(20, 40, 130);
    p.strokeWeight(2.2);
    p.noFill();
    p.beginShape();
    for (let x = -4; x <= 4; x += 0.015)
      p.vertex(sx(x), sy(phi(x)));
    p.endShape();

    // ── x-axis ────────────────────────────────────────────────────────────
    p.stroke(150, 150, 170);
    p.strokeWeight(1);
    p.line(L, B, R, B);
    p.noStroke();
    p.fill(100, 100, 120);
    p.textSize(11);
    p.textAlign(p.CENTER);
    for (let k = -4; k <= 4; k++) {
      p.stroke(150, 150, 170);
      p.strokeWeight(1);
      p.line(sx(k), B, sx(k), B + 4);
      p.noStroke();
      p.fill(100, 100, 120);
      p.text(k, sx(k), B + 16);
    }
    p.fill(90);
    p.textSize(12);
    p.text('z', (L + R) / 2, B + 30);

    // ── critical-value dashed lines ───────────────────────────────────────
    p.drawingContext.setLineDash([5, 4]);
    p.stroke(180, 38, 38);
    p.strokeWeight(1.5);
    p.line(sx(-z), T, sx(-z), B);
    p.line(sx(z),  T, sx(z),  B);
    p.drawingContext.setLineDash([]);

    // ── critical-value labels ─────────────────────────────────────────────
    p.noStroke();
    p.fill(160, 28, 28);
    p.textSize(12.5);
    p.textAlign(p.CENTER);
    // Clamp so labels never run off the plot edges
    let lx = Math.max(sx(-z), L + 22);
    let rx = Math.min(sx(z),  R - 22);
    p.text('\u2212' + z.toFixed(2), lx, T - 6);
    p.text('+' + z.toFixed(2), rx, T - 6);

    // ── tail and centre labels ────────────────────────────────────────────
    p.fill(185, 50, 50);
    p.textSize(11.5);
    if (alpha < 0.30) {   // enough room in tails
      p.text('\u03B1/2', sx(-3.2), sy(0.038));
      p.text('\u03B1/2', sx(3.2),  sy(0.038));
    }
    p.fill(35, 85, 195);
    p.textSize(13.5);
    p.text(conf.toFixed(0) + '% confidence', sx(0), sy(0.235));

    // ── status bar ────────────────────────────────────────────────────────
    let barY = 262;
    p.fill(45, 45, 65);
    p.textSize(13);
    p.textAlign(p.LEFT);
    p.text('\u03B1 = ' + (alpha * 100).toFixed(0) + '%', L, barY);
    p.textAlign(p.CENTER);
    p.text('z\u2090\u2041\u2082 = \u00B1' + z.toFixed(3), (L + R) / 2, barY);
    p.textAlign(p.RIGHT);
    p.text('Confidence level: ' + conf.toFixed(0) + '%', R, barY);

    // ── slider label ──────────────────────────────────────────────────────
    p.fill(110, 110, 130);
    p.textSize(11.5);
    p.textAlign(p.LEFT);
    p.text('\u03B1 (significance level)  \u2014  1% ←', L, 285);
    p.textAlign(p.RIGHT);
    p.text('\u2192 49%', R, 285);
  };
  ```
]

= Interpretation

A $(1-alpha)$ confidence interval does *not* mean there is a $(1-alpha)$
probability that $mu$ lies in this particular interval. The true $mu$ is fixed;
it either is or is not in the interval.

The correct interpretation is *frequentist*: if we repeated the experiment many
times and computed a fresh CI each time, approximately $(1-alpha)$% of those
intervals would contain the true $mu$.

== Effect of $alpha$

Adjusting the slider reveals the trade-off:

- *Decreasing $alpha$* (higher confidence) widens the interval — we are more
  conservative, demanding that the interval capture $mu$ in more repetitions,
  so we must cast a wider net.

- *Increasing $alpha$* (lower confidence) narrows the interval — we make a more
  precise claim, but accept a higher risk of being wrong.

The standard choices are $alpha = 0.05$ (95% CI, $z_(alpha\/2) approx 1.96$)
and $alpha = 0.01$ (99% CI, $z_(alpha\/2) approx 2.576$).

== Reducing the Margin of Error

For a fixed $alpha$, the margin of error from equation @eq-ci is

$ E = z_(alpha\/2) dot sigma / sqrt(n) . $

To halve $E$ without changing the confidence level, you must *quadruple the
sample size* $n$ — the familiar $sqrt(n)$ cost of precision in statistics.

= Simulation: Polling Coverage

The visualization below makes the frequentist claim concrete. Imagine a
polling firm trying to estimate the true support $mu = 0.54$ for a candidate.
Every half-second a new poll of $n = 100$ voters is drawn and a
$(1-alpha)$ confidence interval for the proportion is computed.

*Green* bars contain the true $mu$; *red* bars miss it. Over many polls,
the fraction of green intervals converges to exactly $1-alpha$.

Use the slider to change $alpha$: watch the bars narrow and more turn red as
$alpha$ rises, and widen with more green as $alpha$ falls. The count at
the top tracks the running coverage rate.

#sketch[
  ```js
  // ── constants ──────────────────────────────────────────────────────────
  const MU      = 0.54;   // true population proportion
  const N       = 100;    // voters sampled per poll
  const ROWS    = 28;     // polls shown at once (older ones scroll off)
  const TICK_MS = 500;    // milliseconds between polls

  // ── state ──────────────────────────────────────────────────────────────
  let polls    = [];      // array of sample proportions (p-hat values)
  let lastTick = -(TICK_MS + 1);
  let alphaSlider, resetBtn;

  // ── helpers ────────────────────────────────────────────────────────────
  function normalCDF(x) {
    let s = x < 0 ? -1 : 1, a = Math.abs(x);
    let t = 1 / (1 + 0.3275911 * a);
    let e = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741
            + t * (-1.453152027 + t * 1.061405429))));
    return 0.5 + 0.5 * s * (1 - e * Math.exp(-a * a));
  }

  function quantile(prob) {
    let lo = -8, hi = 8;
    for (let i = 0; i < 64; i++) {
      let m = (lo + hi) / 2;
      if (normalCDF(m) < prob) lo = m; else hi = m;
    }
    return (lo + hi) / 2;
  }

  // ── setup ──────────────────────────────────────────────────────────────
  p.setup = function() {
    p.createCanvas(660, 445);
    p.textFont('system-ui, sans-serif');

    alphaSlider = p.createSlider(1, 25, 5, 1);
    alphaSlider.style('width', '200px');
    alphaSlider.style('accent-color', '#3d6fd4');
    alphaSlider.style('vertical-align', 'middle');
    alphaSlider.style('cursor', 'pointer');

    resetBtn = p.createButton('\u21BA  Reset');
    resetBtn.style('margin-left', '12px');
    resetBtn.style('padding', '3px 12px');
    resetBtn.style('cursor', 'pointer');
    resetBtn.style('font-size', '12px');
    resetBtn.mousePressed(function() {
      polls = [];
      lastTick = p.millis() - TICK_MS - 1;
    });
  };

  // ── draw ───────────────────────────────────────────────────────────────
  p.draw = function() {
    let alpha = alphaSlider.value() / 100;
    let z = quantile(1 - alpha / 2);

    // Add a new poll every TICK_MS ms
    let now = p.millis();
    if (now - lastTick > TICK_MS) {
      let x = 0;
      for (let i = 0; i < N; i++) if (p.random() < MU) x++;
      polls.push(x / N);
      lastTick = now;
    }

    p.background(250, 249, 253);

    // Plot bounds
    let L = 90, R = 578, T = 60, B = 395;
    let xLo = 0.28, xHi = 0.80;
    let sx = v => p.map(v, xLo, xHi, L, R);

    let visible = polls.slice(-ROWS);
    let rowH    = (B - T) / ROWS;

    // ── true μ line ───────────────────────────────────────────────────────
    p.drawingContext.setLineDash([6, 4]);
    p.stroke(30, 50, 190, 160);
    p.strokeWeight(1.8);
    p.line(sx(MU), T - 14, sx(MU), B + 5);
    p.drawingContext.setLineDash([]);

    p.noStroke();
    p.fill(30, 50, 190);
    p.textSize(12.5);
    p.textAlign(p.CENTER);
    p.text('true \u03BC = ' + MU, sx(MU), T - 20);

    // ── x-axis ────────────────────────────────────────────────────────────
    p.stroke(185, 185, 200);
    p.strokeWeight(1);
    p.line(L, B + 3, R, B + 3);
    for (let v = 0.30; v < 0.80; v = Math.round((v + 0.10) * 100) / 100) {
      p.stroke(185, 185, 200);
      p.strokeWeight(1);
      p.line(sx(v), B + 3, sx(v), B + 8);
      p.noStroke();
      p.fill(130);
      p.textSize(11);
      p.textAlign(p.CENTER);
      p.text(v.toFixed(1), sx(v), B + 21);
    }
    p.noStroke();
    p.fill(110);
    p.textSize(11.5);
    p.textAlign(p.CENTER);
    p.text('sample proportion', (L + R) / 2, B + 35);

    // ── confidence interval bars ──────────────────────────────────────────
    for (let i = 0; i < visible.length; i++) {
      let phat = visible[i];
      let se   = Math.sqrt(phat * (1 - phat) / N);
      let lo   = phat - z * se;
      let hi   = phat + z * se;
      let ok   = lo <= MU && MU <= hi;

      let y  = T + (i + 0.5) * rowH;
      let th = rowH * 0.38;
      let c  = ok ? p.color(34, 160, 70, 230) : p.color(205, 45, 45, 225);

      // Horizontal CI bar
      p.stroke(c);
      p.strokeWeight(Math.max(2.5, rowH * 0.50));
      p.line(p.constrain(sx(lo), L, R), y, p.constrain(sx(hi), L, R), y);

      // End-caps
      p.strokeWeight(1.5);
      if (sx(lo) > L) p.line(sx(lo), y - th, sx(lo), y + th);
      if (sx(hi) < R) p.line(sx(hi), y - th, sx(hi), y + th);

      // p-hat dot
      p.fill(c);
      p.noStroke();
      p.circle(sx(phat), y, Math.max(4, rowH * 0.65));

      // Poll index label every 5 rows
      let idx = polls.length - visible.length + i + 1;
      if (idx === 1 || idx % 5 === 0) {
        p.fill(145);
        p.textSize(9);
        p.textAlign(p.RIGHT);
        p.noStroke();
        p.text(idx, L - 5, y + 3);
      }
    }

    // ── running coverage count ────────────────────────────────────────────
    let nOk  = 0;
    for (let phat of polls) {
      let se = Math.sqrt(phat * (1 - phat) / N);
      if (phat - z * se <= MU && MU <= phat + z * se) nOk++;
    }
    let total    = polls.length;
    let pct      = total > 0 ? (nOk / total * 100).toFixed(1) : '\u2014';
    let expected = ((1 - alpha) * 100).toFixed(0);

    // Header
    p.noStroke();
    p.fill(45, 45, 65);
    p.textSize(13);
    p.textAlign(p.LEFT);
    p.text('n = ' + N + '  \u00B7  CI level = ' + expected + '%'
           + '  (\u03B1 = ' + (alpha * 100).toFixed(0) + '%)', L, 22);
    p.textAlign(p.RIGHT);
    p.text(nOk + ' / ' + total + ' contain \u03BC  (' + pct + '%)'
           + '   expected \u2248 ' + expected + '%', R, 22);

    // Legend
    p.textSize(11.5);
    p.textAlign(p.LEFT);
    p.fill(34, 160, 70);
    p.noStroke();
    p.rect(L, 35, 11, 11, 2);
    p.fill(60, 60, 80);
    p.text('  contains \u03BC', L + 11, 46);
    p.fill(205, 45, 45);
    p.rect(L + 125, 35, 11, 11, 2);
    p.fill(60, 60, 80);
    p.text('  misses \u03BC', L + 136, 46);
    p.fill(110);
    p.textAlign(p.RIGHT);
    p.text('\u03B1 :', R, 46);
  };
  ```
]
