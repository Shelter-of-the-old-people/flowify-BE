from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

MAX_SHEET_COLUMN_INDEX = 18278  # ZZZ
MAX_SHEET_ROW_INDEX = 10_000_000
CELL_REFERENCE_PATTERN = re.compile(r"^(?P<column>[A-Za-z]+)(?P<row>\d+)$")


@dataclass(frozen=True)
class ParsedSheetRange:
    sheet_name: str
    start_column_index: int | None = None
    start_row_index: int | None = None
    end_column_index: int | None = None
    end_row_index: int | None = None

    @property
    def is_sheet_only(self) -> bool:
        return self.start_column_index is None or self.start_row_index is None


def build_sheet_range(config: dict[str, Any]) -> str:
    range_a1 = str(config.get("range_a1") or "").strip()
    sheet_name = str(config.get("sheet_name") or "Sheet1").strip() or "Sheet1"

    if range_a1:
        if "!" not in range_a1:
            escaped_sheet_name = sheet_name.replace("'", "''")
            return f"'{escaped_sheet_name}'!{range_a1}"
        return range_a1

    return sheet_name or "Sheet1"


def quote_sheet_name(sheet_name: str) -> str:
    escaped_sheet_name = str(sheet_name).replace("'", "''")
    return f"'{escaped_sheet_name}'"


def column_letter(column_index: int) -> str:
    index = max(column_index, 1)
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def parse_sheet_range(range_a1: str) -> ParsedSheetRange:
    normalized = str(range_a1 or "").strip()
    if not normalized:
        return ParsedSheetRange("Sheet1")

    if "!" in normalized:
        sheet_part, range_part = normalized.split("!", 1)
    else:
        sheet_part, range_part = normalized, ""

    sheet_name = _unquote_sheet_name(sheet_part.strip())
    range_part = range_part.strip()
    if not range_part:
        return ParsedSheetRange(sheet_name=sheet_name)

    if ":" in range_part:
        start_ref, end_ref = (part.strip() for part in range_part.split(":", 1))
    else:
        start_ref, end_ref = range_part, ""

    start_column_index, start_row_index = _parse_cell_reference(start_ref)
    end_column_index = end_row_index = None
    if end_ref:
        end_column_index, end_row_index = _parse_cell_reference(end_ref)

    return ParsedSheetRange(
        sheet_name=sheet_name,
        start_column_index=start_column_index,
        start_row_index=start_row_index,
        end_column_index=end_column_index,
        end_row_index=end_row_index,
    )


def build_table_read_range(range_a1: str) -> str:
    parsed = parse_sheet_range(range_a1)
    if parsed.is_sheet_only:
        return parsed.sheet_name

    if parsed.end_column_index is not None and parsed.end_row_index is not None:
        return _format_sheet_range(
            parsed.sheet_name,
            parsed.start_column_index,
            parsed.start_row_index,
            parsed.end_column_index,
            parsed.end_row_index,
        )

    return _format_sheet_range(
        parsed.sheet_name,
        parsed.start_column_index,
        parsed.start_row_index,
        MAX_SHEET_COLUMN_INDEX,
        MAX_SHEET_ROW_INDEX,
    )


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


def _parse_cell_reference(reference: str) -> tuple[int, int]:
    match = CELL_REFERENCE_PATTERN.match(reference)
    if not match:
        raise ValueError(f"Unsupported A1 cell reference: {reference}")
    return _column_index(match.group("column")), int(match.group("row"))


def _column_index(column_letters: str) -> int:
    index = 0
    for letter in column_letters.upper():
        index = index * 26 + (ord(letter) - 64)
    return index


def _format_sheet_range(
    sheet_name: str,
    start_column_index: int,
    start_row_index: int,
    end_column_index: int,
    end_row_index: int,
) -> str:
    start_cell = f"{column_letter(start_column_index)}{start_row_index}"
    end_cell = f"{column_letter(end_column_index)}{end_row_index}"
    return f"{quote_sheet_name(sheet_name)}!{start_cell}:{end_cell}"


def _unquote_sheet_name(sheet_name: str) -> str:
    stripped = str(sheet_name or "").strip()
    if len(stripped) >= 2 and stripped[0] == "'" and stripped[-1] == "'":
        return stripped[1:-1].replace("''", "'")
    return stripped
