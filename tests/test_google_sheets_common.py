from app.core.nodes.google_sheets_common import (
    build_sheet_range,
    build_table_read_range,
    parse_sheet_range,
)


def test_build_sheet_range_uses_selected_sheet_for_bare_a1_range():
    config = {"sheet_name": "MailSubset", "range_a1": "A1:B4"}

    assert build_sheet_range(config) == "'MailSubset'!A1:B4"


def test_build_sheet_range_preserves_already_qualified_range():
    config = {"sheet_name": "MailSubset", "range_a1": "'Sheet1'!A1:B4"}

    assert build_sheet_range(config) == "'Sheet1'!A1:B4"


def test_build_sheet_range_quotes_sheet_name_with_space():
    config = {"sheet_name": "Summary Stage", "range_a1": "A1"}

    assert build_sheet_range(config) == "'Summary Stage'!A1"


def test_build_table_read_range_expands_single_cell_anchor():
    assert build_table_read_range("'Results'!A1") == "'Results'!A1:ZZZ10000000"


def test_build_table_read_range_preserves_bounded_range():
    assert build_table_read_range("'Results'!B3:D20") == "'Results'!B3:D20"


def test_parse_sheet_range_supports_offset_range():
    parsed = parse_sheet_range("'Results'!B3:D20")

    assert parsed.sheet_name == "Results"
    assert parsed.start_column_index == 2
    assert parsed.start_row_index == 3
    assert parsed.end_column_index == 4
    assert parsed.end_row_index == 20
