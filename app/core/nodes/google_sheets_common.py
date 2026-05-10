from __future__ import annotations

import hashlib
import json
from typing import Any


def build_sheet_range(config: dict[str, Any]) -> str:
    range_a1 = str(config.get("range_a1") or "").strip()
    if range_a1:
        return range_a1

    sheet_name = str(config.get("sheet_name") or "Sheet1").strip()
    return sheet_name or "Sheet1"


def coerce_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def extract_headers_and_rows(
    values: list[list[Any]],
    header_row: int,
    data_start_row: int,
) -> tuple[list[str], list[list[Any]]]:
    if not values:
        return [], []

    header_index = max(header_row - 1, 0)
    data_index = max(data_start_row - 1, header_index + 1)

    if header_index >= len(values):
        return [], []

    headers = [str(cell).strip() for cell in values[header_index]]
    rows = values[data_index:] if data_index < len(values) else []
    return headers, rows


def pad_row(row: list[Any], size: int) -> list[Any]:
    normalized = list(row[:size])
    if len(normalized) < size:
        normalized.extend("" for _ in range(size - len(normalized)))
    return normalized


def row_to_record(headers: list[str], row: list[Any]) -> dict[str, str]:
    normalized_row = pad_row(row, len(headers))
    return {
        header: normalize_cell(normalized_row[index])
        for index, header in enumerate(headers)
        if header
    }


def records_to_rows(headers: list[str], records: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for record in records:
        rows.append([normalize_cell(record.get(header, "")) for header in headers])
    return rows


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def hash_record(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_field_path(payload: Any, path: str) -> Any:
    current = payload
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (TypeError, ValueError, IndexError):
                return None
            continue
        return None
    return current


def matches_text(
    value: Any,
    query: str,
    *,
    match_mode: str = "contains",
    case_sensitive: bool = False,
) -> bool:
    left = normalize_cell(value)
    right = normalize_cell(query)

    if not case_sensitive:
        left = left.lower()
        right = right.lower()

    if match_mode == "exact":
        return left == right
    if match_mode == "starts_with":
        return left.startswith(right)
    return right in left


def resolve_bound_value(
    config: dict[str, Any],
    input_data: dict[str, Any] | None,
    *,
    value_key: str,
    source_key: str,
    field_key: str,
) -> str:
    direct_value = config.get(value_key)
    if direct_value not in (None, ""):
        return normalize_cell(direct_value)

    source = normalize_cell(config.get(source_key))
    field = normalize_cell(config.get(field_key))
    if source == "input_field" and field:
        return normalize_cell(resolve_field_path(input_data or {}, field))

    return ""
