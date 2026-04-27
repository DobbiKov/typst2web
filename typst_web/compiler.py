"""Typst CLI wrapper: compiles .typ files to SVG pages."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def find_typst() -> str:
    """Find the typst executable."""
    exe = shutil.which("typst")
    if not exe:
        raise RuntimeError(
            "typst CLI not found. Install from https://github.com/typst/typst"
        )
    return exe


def compile_to_svgs(
    typ_path: Path,
    *,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> list[str]:
    """
    Compile a .typ file to a list of SVG strings (one per page).

    Returns each SVG as a raw XML string so callers can inline or save them.
    """
    typ_path = Path(typ_path).resolve()
    typst = find_typst()

    with tempfile.TemporaryDirectory() as tmp:
        out_pattern = Path(tmp) / "page-{p}.svg"
        cmd = [typst, "compile", str(typ_path), str(out_pattern), "--format", "svg"]
        if root:
            cmd += ["--root", str(root)]
        if font_paths:
            for fp in font_paths:
                cmd += ["--font-path", str(fp)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"typst compile failed:\n{result.stderr}"
            )

        pages: list[str] = []
        idx = 1
        while True:
            page_file = Path(tmp) / f"page-{idx}.svg"
            if not page_file.exists():
                break
            pages.append(page_file.read_text(encoding="utf-8"))
            idx += 1

        if not pages:
            # single-page documents produce no numbered file; try direct name
            single = Path(tmp) / "page-.svg"
            if single.exists():
                pages.append(single.read_text(encoding="utf-8"))

    if not pages:
        raise RuntimeError("No SVG pages were produced by typst.")

    return pages


def query_heading_pages(
    typ_path: Path,
    *,
    root: Path | None = None,
    font_paths: list[Path] | None = None,
) -> list[dict]:
    """
    Return a list of dicts with keys: text, page, level.

    Uses a temporary wrapper .typ file placed next to the source so that
    relative imports inside the source resolve correctly.
    """
    typ_path = Path(typ_path).resolve()
    typst = find_typst()

    wrapper_content = (
        f'#include "{typ_path.name}"\n\n'
        "#context {\n"
        "  let headings = query(heading)\n"
        "  for h in headings {\n"
        "    let body = h.body\n"
        '    let t = if "text" in body.fields() { body.text } else { "" }\n'
        "    metadata((\n"
        "      text: t,\n"
        "      page: h.location().page(),\n"
        "      level: h.level,\n"
        "    ))\n"
        "  }\n"
        "}\n"
    )

    with tempfile.TemporaryDirectory() as tmp:
        wrapper_path = typ_path.parent / "_typst_web_query_tmp.typ"
        try:
            wrapper_path.write_text(wrapper_content, encoding="utf-8")
            cmd = [typst, "query", str(wrapper_path), "metadata",
                   "--field", "value"]
            if root:
                cmd += ["--root", str(root)]
            if font_paths:
                for fp in font_paths:
                    cmd += ["--font-path", str(fp)]

            result = subprocess.run(cmd, capture_output=True, text=True)
        finally:
            wrapper_path.unlink(missing_ok=True)

    if result.returncode != 0:
        # Non-fatal: return empty, search will just not have page mapping
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def get_typst_version() -> str:
    typst = find_typst()
    r = subprocess.run([typst, "--version"], capture_output=True, text=True)
    return r.stdout.strip()
