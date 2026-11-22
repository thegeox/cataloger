"""Tiny placeholder language for templates.

    {{campo}}                    value of metadata field `campo`
    {{campo|upper}}              filters: upper, lower, title, trim
    {{precio|money}}             1234.5 -> 1,234.50   (money:€ adds a symbol prefix)
    {{precio|number:0}}          fixed decimals
    {{campo|default:Sin dato}}   fallback when empty
    {{fecha|date:%d/%m/%Y}}      reformat ISO dates
    {{_name}} {{_stem}} {{_index}} {{_count}} {{_width}} {{_height}}   built-ins
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

PLACEHOLDER = re.compile(r"\{\{\s*([^{}|]+?)\s*((?:\|[^{}|]*)*)\}\}")


def _apply_filter(value: Any, name: str, arg: str | None) -> Any:
    empty = value is None or value == ""
    if name == "default":
        return arg if empty else value
    if empty:
        return value
    if name == "upper":
        return str(value).upper()
    if name == "lower":
        return str(value).lower()
    if name == "title":
        return str(value).title()
    if name == "trim":
        return str(value).strip()
    if name in ("number", "money"):
        try:
            n = float(value)
        except (TypeError, ValueError):
            return value
        if name == "money":
            return f"{arg or ''}{n:,.2f}"
        decimals = int(arg) if arg and arg.isdigit() else 2
        return f"{n:,.{decimals}f}"
    if name == "date":
        try:
            return date.fromisoformat(str(value)).strftime(arg or "%d/%m/%Y")
        except ValueError:
            return value
    if name == "yesno":
        yes, _, no = (arg or "Sí,No").partition(",")
        return yes if value is True or str(value).lower() == "true" else no
    return value


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render_text(template: str, context: dict[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        value = context.get(m.group(1).strip())
        for part in filter(None, m.group(2).split("|")):
            name, _, arg = part.partition(":")
            value = _apply_filter(value, name.strip(), arg if _ else None)
        return _fmt(value)

    return PLACEHOLDER.sub(repl, template)


def find_placeholders(template: str) -> list[str]:
    return [m.group(1).strip() for m in PLACEHOLDER.finditer(template)]


def build_context(image: Any, index: int = 1, count: int = 1) -> dict[str, Any]:
    stem = image.name.rsplit(".", 1)[0]
    return {
        **(image.meta or {}),
        "_name": image.name,
        "_stem": stem,
        "_index": index,
        "_count": count,
        "_width": image.width,
        "_height": image.height,
    }
