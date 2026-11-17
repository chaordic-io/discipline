"""YAML front matter for the method's structured markdown: decisions, proposals, work files.

Standard library only, so it reads the small subset of YAML these files use, and writes it back the
same way:

    ---
    date: 2026-11-16              # a scalar (a comment after " #" is ignored)
    kind: technical
    area: [invoicing, permissions] # a flow list
    tests:                        # or a block list
      - tests/test_rounding.py
    superseded-by:                # empty: ""
    ---

Every value is a string or a list of strings; quotes ('…' or "…") are optional and removed. Nesting,
multi-line strings and anchors are not supported: a line this parser doesn't understand is an error,
reported with its line number, rather than a silently wrong value.
"""
from __future__ import annotations

import re

Value = str | list[str]

_BLOCK = re.compile(r"\A---[ \t]*\n(.*?)\n?---[ \t]*(?:\n|\Z)", re.S)
_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")
_ITEM = re.compile(r"^[ \t]+-[ \t]*(.*)$|^-[ \t]+(.*)$")


class FrontMatterError(ValueError):
    pass


def _quoted(s: str) -> tuple[str, int] | None:
    """For `s` starting with a quote: (the unquoted text, the index after the closing quote), or None
    when it isn't closed. As in YAML, `''` is a quote inside '…', and `\\"`/`\\\\` are escapes inside "…"."""
    q, out, i = s[0], [], 1
    while i < len(s):
        ch = s[i]
        if q == "'" and ch == "'":
            if s[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        if q == '"' and ch == "\\" and i + 1 < len(s):
            out.append(s[i + 1])
            i += 2
            continue
        if q == '"' and ch == '"':
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None


def _uncomment(value: str) -> str:
    """The value without a trailing ` # comment`. As in YAML, a quote opens a quoted string only where
    a value or list item starts (`it's` is plain text), and `#` starts a comment only after a space."""
    value = value.strip()
    i, item_start = 0, True
    while i < len(value):
        ch = value[i]
        if item_start and ch in ("'", '"') and (q := _quoted(value[i:])):
            i += q[1]
            item_start = False
            continue
        if ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i].rstrip()
        item_start = ch in "[," or (item_start and ch in " \t")
        i += 1
    return value


def _scalar(value: str) -> str:
    value = value.strip()
    if value[:1] in ("'", '"'):
        q = _quoted(value)
        if q and q[1] == len(value):
            return q[0]
    return value


def _flow(value: str) -> list[str]:
    """The items of `[a, "b, c", d]`: a comma inside a quoted item doesn't split it."""
    items, rest = [], value[1:-1].strip()
    while rest:
        q = _quoted(rest) if rest[0] in ("'", '"') else None
        if q:
            items.append(q[0])
            rest = rest[q[1]:].lstrip()
            rest = rest[1:].lstrip() if rest.startswith(",") else rest
        else:
            item, _, rest = rest.partition(",")
            if item.strip():
                items.append(item.strip())
            rest = rest.lstrip()
    return items


def split(text: str) -> tuple[dict[str, Value] | None, str]:
    """(front matter, body). None when the text has no front matter; FrontMatterError when it has one
    that can't be read."""
    m = _BLOCK.match(text)
    if not m:
        return None, text
    data: dict[str, Value] = {}
    key = None
    for n, line in enumerate(m.group(1).splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _ITEM.match(line)
        if item and key is not None:
            if data[key] == "":
                data[key] = []
            if not isinstance(data[key], list):
                raise FrontMatterError(f"line {n}: a list item under `{key}`, which already has a value")
            data[key].append(_scalar(_uncomment(item.group(1) or item.group(2) or "")))
            continue
        kv = _KEY.match(line)
        if not kv:
            raise FrontMatterError(f"line {n}: not `key: value` or a `- item`: {line.strip()[:60]}")
        key, raw = kv.group(1), _uncomment(kv.group(2) or "")
        if key in data:
            raise FrontMatterError(f"line {n}: `{key}` appears twice")
        data[key] = _flow(raw) if raw.startswith("[") and raw.endswith("]") else _scalar(raw)
    return data, text[m.end():]


def read(text: str) -> dict[str, Value]:
    """The front matter, or {} when there is none or it can't be read."""
    try:
        return split(text)[0] or {}
    except FrontMatterError:
        return {}


def strip(text: str) -> str:
    """The text without its front matter."""
    m = _BLOCK.match(text)
    return text[m.end():] if m else text


def as_list(value: Value | None) -> list[str]:
    """A field as a list: a scalar becomes a one-item list, "" an empty one."""
    if value is None or value == "":
        return []
    return [value] if isinstance(value, str) else list(value)


def _quote(s: str) -> str:
    """`s` as a YAML scalar: plain when that reads back the same, otherwise single-quoted."""
    if s and s == s.strip() and not re.search(r"[#,\[\]{}:\"']|^[-?!&*|>%@`]", s):
        return s
    return "'" + s.replace("'", "''") + "'"


def dump(data: dict[str, Value], comments: dict[str, str] | None = None) -> str:
    """The front matter block for `data`, keys in order, lists as flow lists, with optional comments."""
    lines = ["---"]
    for key, value in data.items():
        text = f"[{', '.join(_quote(v) for v in value)}]" if isinstance(value, list) else (_quote(value) if value else "")
        line = f"{key}:" + (f" {text}" if text else "")
        note = (comments or {}).get(key)
        lines.append(f"{line:<28} # {note}" if note else line)
    return "\n".join(lines + ["---", ""])
