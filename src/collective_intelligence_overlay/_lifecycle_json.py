"""Finite lifecycle material; these checks do not normalize signed originals."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import Any

MAX_JSON_BYTES = 1048576
MAX_JSON_DEPTH = 64


def validate_json_tree(value: Any) -> None:
    """Bound traversal before serialization/model validation, without mutation."""
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_BYTES:
            raise ValueError("lifecycle JSON node bound exceeded")
        if isinstance(item, dict | list | tuple):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("lifecycle JSON depth bound exceeded")
            if len(item) > MAX_JSON_BYTES:
                raise ValueError("lifecycle JSON node bound exceeded")
            children: Iterable[Any]
            if isinstance(item, dict):
                if any(not isinstance(key, str) for key in item):
                    raise ValueError("lifecycle JSON keys must be strings")
                children = item.values()
            else:
                children = item
            pending.extend((child, depth) for child in children)
        elif isinstance(item, str):
            if len(item) > MAX_JSON_BYTES:
                raise ValueError("lifecycle JSON byte bound exceeded")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("nonfinite JSON number")
        elif item is not None and not isinstance(item, int | bool):
            raise ValueError("lifecycle material must contain JSON values")


def check_json_bytes(data: bytes) -> None:
    """Bound raw JSON nesting without decoding any source fields."""
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("lifecycle JSON byte bound exceeded")
    depth = 0
    in_string = escaped = False
    for char in data.decode(json.detect_encoding(data)):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("lifecycle JSON depth bound exceeded")
        elif char in "]}":
            depth -= 1


def load_json(data: bytes) -> Any:
    """Check byte/depth bounds before decode; reject ambiguous/non-JSON numbers."""
    check_json_bytes(data)

    def pairs(entries: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in entries:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError("nonfinite JSON number: " + value)

    result = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    validate_json_tree(result)
    return result
