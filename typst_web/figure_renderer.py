"""
Compile individual figures from a Typst source to SVG.

Strategy: find #figure(...) blocks in the source that contain cetz/layout
content (which typst HTML export drops), compile each to SVG, and return
a mapping from figure label → SVG string.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


def _find_figures(source: str) -> list[dict]:
    """
    Scan source for #figure(...) blocks. Return list of:
      {"label": str | None, "source_start": int, "source_end": int}
    """
    figures: list[dict] = []
    i = 0
    n = len(source)

    while i < n:
        m = re.search(r"#figure\s*\(", source[i:])
        if not m:
            break
        abs_start = i + m.start()
        paren_start = i + m.end() - 1
        # Find matching closing paren
        depth = 0
        j = paren_start
        while j < n:
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        abs_end = j + 1  # includes the closing )

        # Look for label right after
        rest = source[abs_end:abs_end + 40].lstrip(" \t")
        lm = re.match(r"<([\w-]+)>", rest)
        label = lm.group(1) if lm else None

        figures.append({
            "label": label,
            "source_start": abs_start,
            "source_end": abs_end,
            "body": source[abs_start:abs_end],
        })
        i = abs_end

    return figures


def compile_figures_to_svg(
    typ_path: Path,
    *,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> dict[str, str]:
    """
    Compile every #figure block in typ_path to SVG.
    Returns a dict mapping label (or "fig-N") → SVG string.
    """
    from .compiler import find_typst
    typst = find_typst()
    typ_path = Path(typ_path).resolve()
    source = typ_path.read_text(encoding="utf-8")

    # Collect ALL #import, #set, #show lines from the entire source
    # (they may appear anywhere, e.g. cetz imported mid-document)
    preamble_lines: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if re.match(r"#(import|set|show|let)\b", stripped):
            preamble_lines.append(line)

    preamble = "\n".join(preamble_lines) + "\n"

    figures = _find_figures(source)
    result: dict[str, str] = {}

    for idx, fig in enumerate(figures):
        label = fig["label"] or f"fig-{idx + 1}"
        fig_source = (
            preamble
            + "#set page(width: auto, height: auto, margin: 8pt)\n"
            + fig["body"]
            + "\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            src_file = typ_path.parent / f"_typst_web_fig_{idx}.typ"
            out_file = Path(tmp) / "fig.svg"
            try:
                src_file.write_text(fig_source, encoding="utf-8")
                cmd = [typst, "compile", str(src_file), str(out_file), "--format", "svg"]
                if root:
                    cmd += ["--root", str(root)]
                if font_paths:
                    for fp in font_paths:
                        cmd += ["--font-path", str(fp)]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and out_file.exists():
                    result[label] = out_file.read_text(encoding="utf-8")
            except Exception:
                pass
            finally:
                src_file.unlink(missing_ok=True)

    return result
