"""
Settings resolution for typst-to-web.

Priority chain: CLI flags > typst-web.toml > parsed .typ metadata.

TOML authors support both plain strings and inline tables:
    authors = [
        "Plain Name",
        {name = "Alice", email = "alice@example.com", website = "https://alice.dev"},
    ]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None  # type: ignore[assignment]


@dataclass
class Author:
    name: str
    email: str = ""
    website: str = ""


@dataclass
class Settings:
    title: str = ""
    subtitle: str = ""
    authors: list[Author] = field(default_factory=list)
    date: str = ""


def _parse_author(raw) -> Author:
    """Accept a string or a dict with name/email/website keys."""
    if isinstance(raw, str):
        return Author(name=raw)
    return Author(
        name=str(raw.get("name", "")),
        email=str(raw.get("email", "")),
        website=str(raw.get("website", "")),
    )


def _load_toml_document_section(path: Path) -> dict:
    if tomllib is None:
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("document", {})


def resolve_settings(
    typ_path: Path,
    *,
    cli_title: str = "",
    cli_subtitle: str = "",
    cli_authors: list[str] | None = None,
    cli_date: str = "",
    meta_title: str = "",
    meta_authors: list[str] | None = None,
    meta_date: str = "",
) -> Settings:
    """Return Settings with priority: CLI flags > typst-web.toml > parsed .typ metadata."""
    toml: dict = {}
    toml_path = typ_path.parent / "typst-web.toml"
    if toml_path.exists():
        toml = _load_toml_document_section(toml_path)

    def pick(cli_val: str, toml_key: str, meta_val: str = "") -> str:
        if cli_val:
            return cli_val
        if toml_key in toml:
            return str(toml[toml_key])
        return meta_val

    title    = pick(cli_title,    "title",    meta_title)
    subtitle = pick(cli_subtitle, "subtitle")
    date     = pick(cli_date,     "date",     meta_date)

    if cli_authors:
        authors = [Author(name=n) for n in cli_authors]
    elif "authors" in toml:
        authors = [_parse_author(a) for a in toml["authors"]]
    elif meta_authors:
        authors = [Author(name=n) for n in meta_authors]
    else:
        authors = []

    return Settings(title=title, subtitle=subtitle, authors=authors, date=date)
