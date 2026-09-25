# querycli — Universal Query Harness

**querycli** is a zero-dependency Python CLI that runs a structured query expression against JSON, YAML, TOML, CSV, and plain key=value text. It is a single interface for asking "does this file contain X?" without writing a bespoke one-off script for each format.

## About

Developers often need to answer small structured questions across heterogeneous files: check a config for a key, confirm a field exists in a JSON payload, grep CSV rows by a column, or verify a `KEY=VALUE` environment dump. **querycli** gives you one command that normalizes each supported format into a queryable view and runs the same expression language against all of them.

It is not a full spreadsheet. It is a small, fast, offline query harness for the questions that appear dozens of times a week and usually get answered with a mix of `jq`, `yq`, `grep`, and `python -c`.

## Features

- **Multi-format input** — JSON, YAML, TOML, CSV, and key=value text all accepted via `--format` or auto-detection by extension.
- **Query expressions** — simple `path` lookups (`store.bundle.version`), boolean checks (`store.exists`), and equality tests (`store.bundle.version == 1.2.3`).
- **Exit-code semantics** — `--check` returns nonzero when the query does not match, suitable for CI guards.
- **JSON output** — `--json` emits a machine-readable result with `matched`, `value`, and `format`.
- **Stdin and file input** — pass a path or pipe content; use `-` for stdin.
- **Tabular output for CSV** — when the query is a column lookup, `querycli` can emit the matched column values in order.
- **Zero runtime dependencies** — stdlib only; works on Python 3.11+.

## Installation

```bash
python -m pip install querycli
```

Or run from a checkout:

```bash
git clone <repo-url>
cd querycli
python -m pip install -e .
```

## Usage

```bash
querycli [options] <query> <path> [<path> ...]
```

### Positional

| Arg   | Description                                                    |
|-------|----------------------------------------------------------------|
| query | Query expression, e.g. `store.bundle.version` or `store.exists`. |
| path  | File(s) to query. Use `-` for stdin.                              |

### Options

| Flag                   | Description                                                                       |
|------------------------|-----------------------------------------------------------------------------------|
| `-f, --format <fmt>`  | Force input format: `json`, `yaml`, `toml`, `csv`, `kv`.                          |
| `--csv-header <h>`     | Comma-separated header for CSV when the file has none.                            |
| `--csv-column <c>`     | For CSV, query by column name instead of row path.                                |
| `--check`              | Exit nonzero when the query does not match.                                       |
| `--json`               | Emit result as JSON instead of plain text.                                        |
| `--help`               | Show help and exit.                                                               |

### Examples

```bash
# Does this JSON have a nested key?
querycli store.bundle.version package.json

# Boolean existence check
querycli store.exists package.json

# Equality check
querycli 'store.bundle.version == 1.2.3' package.json

# Query a YAML file
querycli database.url config.yaml

# Query a TOML file
querycli tool.poetry.version pyproject.toml

# Query CSV by column
querycli --format csv --csv-column name users.csv

# Key=value text
querycli DB_HOST env.txt

# Stdin mode
cat artifact.json | querycli store.sha --format json -

# CI guard
querycli --check 'store.version == 2.0.0' release-manifest.json
```

### Supported query shapes

- `path` — dot-separated lookup into nested dicts/lists.
- `path.exists` — true when the path is present, false otherwise.
- `path == value` — shallow equality against a scalar.
- `csv column` — when `--format csv` and `--csv-column` are set, returns all values in that column.

## Project Structure

```
querycli/
├── querycli.py      # CLI entrypoint, parsers, format handlers
├── pyproject.toml   # Package metadata, entrypoint, tool config
├── README.md        # This file
└── .gitignore       # Python build artifacts and common noise
```

- `querycli.py` — flat single-module implementation: format detection, query parser, runners
- `pyproject.toml` — packaging, console script, ruff config
- `README.md` — user-facing documentation
- `.gitignore` — keeps build metadata and editor noise out of the repo

## Tech Stack

- Python 3.11+
- Standard library only (`argparse`, `json`, `csv`, `sys`, `pathlib`)
- `pyproject.toml` packaging with a `querycli` console script entrypoint
- Flat single-module layout

## Tags / Keywords

`cli`, `query`, `json`, `yaml`, `toml`, `csv`, `developer-tools`, `terminal`, `zero-dependency`, `python`

## License

MIT
