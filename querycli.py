"""querycli — universal query harness for JSON, YAML, TOML, CSV, and KV text."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    tomllib = None  # type: ignore[assignment]

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - yaml is optional in this MVP
    yaml = None  # type: ignore[assignment]


def _load_json(raw: str) -> Any:
    return json.loads(raw)


def _load_toml(raw: str) -> Any:
    if tomllib is None:
        raise RuntimeError(
            "tomllib unavailable; "
            "Python 3.11+ required for TOML support"
        )
    return tomllib.loads(raw)


def _load_yaml(raw: str) -> Any:
    if yaml is None:
        raise RuntimeError(
            "PyYAML not installed; "
            "install querycli[dev] for YAML support"
        )
    return yaml.safe_load(raw)


def _load_csv_table(raw: str, header: list[str] | None = None) -> list[dict[str, str]]:
    if header is None:
        reader = csv.DictReader(io.StringIO(raw))
        return list(reader)
    reader = csv.DictReader(io.StringIO(raw), fieldnames=header)
    return list(reader)


def _load_kv(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


class QueryEngine:
    def __init__(self, data: Any) -> None:
        self.data = data

    def resolve(self, path: str) -> Any:
        cur: Any = self.data
        for segment in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(segment)
            elif isinstance(cur, list):
                try:
                    idx = int(segment)
                except ValueError:
                    return None
                if idx < 0 or idx >= len(cur):
                    return None
                cur = cur[idx]
            else:
                return None
            if cur is None:
                return None
        return cur

    def exists(self, path: str) -> bool:
        return self.resolve(path) is not None

    def equals(self, path: str, value: Any) -> bool:
        got = self.resolve(path)
        if got is None:
            return False
        return got == value

    def find_first(self, predicate: Any) -> Any:
        rows = self.data
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict):
                match = True
                if isinstance(predicate, dict):
                    for key, wanted in predicate.items():
                        if str(row.get(key)) != str(wanted):
                            match = False
                            break
                if match:
                    return row
        return None


def _parse_query(query: str) -> tuple[str, str | None, Any]:
    query = query.strip()
    if "==" in query:
        left, _, right = query.partition("==")
        return left.strip(), "equals", _coerce(right.strip())
    if query.endswith(".exists"):
        return query, "exists", None
    return query, "resolve", None


def _coerce(value: str) -> Any:
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def _format_plain(result: Any) -> str:
    if result is None:
        return "null"
    if isinstance(result, bool):
        return str(result).lower()
    if isinstance(result, (int, float)):
        return str(result)
    if isinstance(result, list):
        return "\n".join(_format_plain(item) for item in result)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def _detect_format(path: str, raw: str = "") -> str:
    p = Path(path)
    if p.suffix == ".json":
        return "json"
    if p.suffix in {".yaml", ".yml"}:
        return "yaml"
    if p.suffix == ".toml":
        return "toml"
    if p.suffix == ".csv":
        return "csv"
    # When reading from stdin, sniff the content to pick a sensible default.
    if path == "-":
        stripped = raw.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return "json"
        if stripped.startswith("#") or "=" in stripped.split("\n", 1)[0]:
            return "kv"
        return "kv"
    return "kv"


def run_query(
    raw: str,
    query: str,
    fmt: str,
    csv_header: list[str] | None = None,
    csv_column: str | None = None,
) -> dict[str, Any]:
    if fmt == "json":
        data = _load_json(raw)
    elif fmt == "toml":
        data = _load_toml(raw)
    elif fmt == "yaml":
        data = _load_yaml(raw)
    elif fmt == "csv":
        data = _load_csv_table(raw, header=csv_header)
    elif fmt == "kv":
        data = _load_kv(raw)
    else:
        raise ValueError(f"unsupported format: {fmt}")

    engine = QueryEngine(data)
    expr, op, payload = _parse_query(query)

    if fmt == "csv" and csv_column:
        expr = csv_column
        if op == "resolve":
            out: list[str] = []
            for row in data:
                if isinstance(row, dict):
                    val = row.get(csv_column)
                    if val is not None:
                        out.append(val)
            return {
                "matched": bool(out),
                "value": out,
                "format": fmt,
            }

    if op == "resolve":
        value = engine.resolve(expr)
        return {"matched": value is not None, "value": value, "format": fmt}
    if op == "exists":
        base_path = expr.removesuffix(".exists")
        matched = engine.exists(base_path)
        return {"matched": matched, "value": matched, "format": fmt}
    if op == "equals":
        equal = engine.equals(expr, payload)
        return {
            "matched": equal,
            "value": engine.resolve(expr),
            "format": fmt,
        }
    return {"matched": False, "value": None, "format": fmt}


def _rebuild_argv(argv: list[str] | None) -> list[str]:
    """Reorder argv so known optionals come before positionals.

    argparse with nargs='*' treats any positional token appearing after
    an optional as 'unrecognized' unless the optional comes last.
    This helper moves --json, --check, --format, --csv-header,
    --csv-column, and -f to the front so both orderings work:

        querycli x file.json --json      # flag after file
        querycli x --json file.json      # flag before file  (now works)
    """
    if argv is None:
        argv = sys.argv[1:]

    # Flags that take a value (and their value must follow immediately)
    value_flags = {"--format", "-f", "--csv-header", "--csv-column"}

    optionals: list[str] = []
    positionals: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags and i + 1 < len(argv):
            # Consume flag + its value as a unit
            optionals.append(a)
            optionals.append(argv[i + 1])
            i += 2
        elif a in {"--json", "-j", "--check"}:
            optionals.append(a)
            i += 1
        else:
            positionals.append(a)
            i += 1

    return optionals + positionals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="querycli",
        description=(
            "Query JSON, YAML, TOML, CSV, "
            "and key=value text from the terminal.\n\n"
            "Positional arguments: QUERY EXPRESSION, then FILES.\n"
            "Option flags (--json, --check, --format, --csv-header, --csv-column)\n"
            "can appear before or after the file argument.\n"
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Query expression, e.g. store.bundle.version.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        default=None,
        help="Files to query. Use - for stdin.",
    )
    parser.add_argument(
        "-f",
        "--format",
        default=None,
        choices=["json", "yaml", "toml", "csv", "kv"],
        help="Force input format.",
    )
    parser.add_argument(
        "--csv-header",
        default=None,
        help="Comma-separated header for CSV when the file has none.",
    )
    parser.add_argument(
        "--csv-column",
        default=None,
        help="For CSV, query by column name instead of row path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero when the query does not match.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit result as JSON.",
    )

    args = parser.parse_args(_rebuild_argv(argv))

    if args.query is None:
        parser.print_help()
        return 0

    # When --csv-column / --format csv is used without an explicit
    # query expression, argparse may have consumed the file path as
    # the query positional. Detect that and swap it back.
    files = list(args.files or [])
    query = args.query
    if query and not files:
        p = Path(query)
        if p.is_file():
            files.append(query)
            query = None

    if query is None and not files:
        sys.stderr.write(
            "querycli: missing path; "
            "pass a file or - for stdin\n"
        )
        return 2

    path = files[0] if files else None

    if path is None:
        sys.stderr.write(
            "querycli: missing path; "
            "pass a file or - for stdin\n"
        )
        return 2

    if path == "-":
        raw = sys.stdin.read()
    else:
        p = Path(path)
        if not p.is_file():
            sys.stderr.write(f"querycli: {path}: No such file\n")
            return 2
        raw = p.read_text(encoding="utf-8")

    fmt = args.format or _detect_format(path or "input", raw)

    csv_header = None
    if args.csv_header:
        csv_header = [
            h.strip() for h in args.csv_header.split(",") if h.strip()
        ]

    try:
        result = run_query(
            raw,
            args.query,
            fmt,
            csv_header=csv_header,
            csv_column=args.csv_column,
        )
    except RuntimeError as exc:
        sys.stderr.write(f"querycli: {exc}\n")
        return 2
    except Exception as exc:
        sys.stderr.write(f"querycli: failed to query: {exc}\n")
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["format"] == "csv" and isinstance(result["value"], list):
            print("\n".join(result["value"]))
        else:
            print(_format_plain(result["value"]))

    if args.check:
        return 0 if result["matched"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
