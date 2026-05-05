# Settings file (`typst-web.toml`)

Place a `typst-web.toml` file next to your main `.typ` file to configure document metadata without repeating CLI flags.

## Priority chain

Settings are resolved in this order (higher wins):

1. CLI flags
2. `typst-web.toml`
3. Metadata parsed from the `.typ` source (`#set document(...)`)

## Full example

```toml
[document]
title    = "Measure Theory"
subtitle = "Lecture Notes, Spring 2026"
date     = "2026-05-05"

authors = [
    "Plain Name",
    {name = "Alice Dupont", email = "alice@example.com"},
    {name = "Bob Smith",    website = "https://bob.dev"},
    {name = "Carol White",  email = "carol@uni.edu", website = "https://carol.dev"},
]
```

## Fields

| Field | Type | Description |
|---|---|---|
| `title` | string | Document title shown in the page header and browser tab |
| `subtitle` | string | Subtitle shown below the title in the header and sidebar |
| `date` | string | Freeform date string shown in the document meta line |
| `authors` | array | List of authors — plain strings or inline tables (see below) |

## Authors

Each entry in `authors` can be a plain string or an inline table with `name`, `email`, and/or `website`:

```toml
authors = [
    "Plain Name",
    {name = "Alice", email = "alice@example.com"},
    {name = "Bob",   website = "https://bob.dev"},
    {name = "Carol", email = "carol@uni.edu", website = "https://carol.dev"},
]
```

Rendering rules:
- `website` set → name is a link to the website (opens in new tab)
- `email` set (no website) → name is a `mailto:` link
- Neither set → plain text

## CLI flags

All fields can be overridden per-run via CLI flags:

```
--title "..."
--subtitle "..."
--date "..."
--author "Name"   # repeat for multiple authors (names only)
```

CLI `--author` only supports plain names. For email/website, use `typst-web.toml`.

## Notes

- TOML support requires Python 3.11+. On Python 3.10 the file is silently ignored and metadata falls back to the `.typ` source.
- If no `title` is set anywhere, the `.typ` filename stem is used as a fallback.
