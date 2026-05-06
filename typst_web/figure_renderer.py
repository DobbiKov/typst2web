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
    extra_paths: list[Path] | None = None,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> dict[str, str]:
    """
    Compile every #figure block in typ_path (and any extra_paths) to SVG.
    Returns a dict mapping label (or "fig-N") → SVG string.
    """
    from .compiler import find_typst
    typst = find_typst()
    typ_path = Path(typ_path).resolve()

    # Gather all (file_path, source) pairs to scan for #figure blocks
    all_sources: list[tuple[Path, str]] = []
    all_sources.append((typ_path, typ_path.read_text(encoding="utf-8")))
    for ep in (extra_paths or []):
        ep = Path(ep).resolve()
        try:
            all_sources.append((ep, ep.read_text(encoding="utf-8")))
        except OSError:
            pass

    result: dict[str, str] = {}
    global_idx = 0

    for file_path, source in all_sources:
        # Collect ALL #import, #set, #show lines from this file as preamble
        preamble_lines: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if re.match(r"#(import|set|show|let)\b", stripped):
                preamble_lines.append(line)
        preamble = "\n".join(preamble_lines) + "\n"

        figures = _find_figures(source)

        for fig in figures:
            label = fig["label"] or f"fig-{global_idx + 1}"
            fig_source = (
                preamble
                + "#set page(width: auto, height: auto, margin: 8pt)\n"
                + fig["body"]
                + "\n"
            )

            with tempfile.TemporaryDirectory() as tmp:
                src_file = file_path.parent / f"_typst_web_fig_{global_idx}.typ"
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

            global_idx += 1

    return result


def _collect_preamble_for(typ_file: Path) -> str:
    """
    Collect #import and #let blocks from a .typ file to use as preamble.
    Handles multi-line #let blocks by tracking brace depth.
    """
    try:
        source = typ_file.read_text(encoding="utf-8")
    except OSError:
        return ""

    preamble_parts: list[str] = []
    lines = source.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if re.match(r"#import\b", stripped):
            preamble_parts.append(line)
            i += 1
        elif re.match(r"#let\b", stripped):
            # Collect the full let block (may span multiple lines via braces)
            block = [line]
            # Count open/close braces to know when the block ends
            depth = line.count("{") - line.count("}")
            i += 1
            while i < len(lines) and depth > 0:
                block.append(lines[i])
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            preamble_parts.append("".join(block))
        else:
            i += 1

    return "".join(preamble_parts)


def compile_canvases_to_svgs(
    canvases,           # list[CanvasExpr]
    *,
    typ_dir: Path,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> list[str]:
    """
    Compile each CanvasExpr to SVG.
    Returns a list of SVG strings (empty string if compilation failed).
    """
    from .compiler import find_typst
    typst = find_typst()
    result: list[str] = [""] * len(canvases)

    for cv in canvases:
        # Collect imports/lets from the file that contains this canvas
        src_file_path = getattr(cv, "source_path", None)
        preamble = ""
        if src_file_path and Path(src_file_path).exists():
            preamble = _collect_preamble_for(Path(src_file_path))
            compile_dir = Path(src_file_path).parent
        else:
            compile_dir = typ_dir

        canvas_source = (
            preamble
            + "#set page(width: auto, height: auto, margin: 8pt)\n"
            + "#align(center)[\n"
            + cv.body
            + "\n]\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            src_file = compile_dir / f"_typst_web_canvas_{cv.index}.typ"
            out_file = Path(tmp) / "canvas.svg"
            try:
                src_file.write_text(canvas_source, encoding="utf-8")
                cmd = [typst, "compile", str(src_file), str(out_file), "--format", "svg"]
                if root:
                    cmd += ["--root", str(root)]
                if font_paths:
                    for fp in font_paths:
                        cmd += ["--font-path", str(fp)]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and out_file.exists():
                    svg = out_file.read_text(encoding="utf-8")
                    svg = re.sub(r"<\?xml[^?]*\?>", "", svg)
                    svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg)
                    svg = svg.replace('class="typst-doc"', 'class="typst-canvas-svg"')
                    result[cv.index] = svg
            except Exception:
                pass
            finally:
                src_file.unlink(missing_ok=True)

    return result
