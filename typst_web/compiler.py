"""Typst CLI wrapper."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def find_typst() -> str:
    exe = shutil.which("typst")
    if not exe:
        raise RuntimeError(
            "typst CLI not found. Install from https://github.com/typst/typst"
        )
    return exe


def compile_to_html(
    typ_path: Path,
    *,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> str:
    """
    Compile a .typ file to HTML using Typst's experimental HTML export.
    Returns the raw HTML string.
    """
    typ_path = Path(typ_path).resolve()
    typst = find_typst()

    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / "out.html"
        cmd = [
            typst, "compile", str(typ_path), str(out_file),
            "--format", "html", "--features", "html",
        ]
        if root:
            cmd += ["--root", str(root)]
        if font_paths:
            for fp in font_paths:
                cmd += ["--font-path", str(fp)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"typst compile failed:\n{result.stderr}")

        return out_file.read_text(encoding="utf-8")


def query_heading_pages(
    typ_path: Path,
    *,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> list[dict]:
    """Query heading page numbers via a wrapper file placed next to the source."""
    typ_path = Path(typ_path).resolve()
    typst = find_typst()

    wrapper = (
        f'#include "{typ_path.name}"\n\n'
        "#context {\n"
        "  for h in query(heading) {\n"
        "    let body = h.body\n"
        '    let t = if "text" in body.fields() { body.text } else { "" }\n'
        "    metadata((text: t, page: h.location().page(), level: h.level))\n"
        "  }\n"
        "}\n"
    )

    wrapper_path = typ_path.parent / "_typst_web_query_tmp.typ"
    try:
        wrapper_path.write_text(wrapper, encoding="utf-8")
        cmd = [typst, "query", str(wrapper_path), "metadata", "--field", "value"]
        if root:
            cmd += ["--root", str(root)]
        if font_paths:
            for fp in font_paths:
                cmd += ["--font-path", str(fp)]
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        wrapper_path.unlink(missing_ok=True)

    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def get_typst_version() -> str:
    typst = find_typst()
    r = subprocess.run([typst, "--version"], capture_output=True, text=True)
    return r.stdout.strip()
