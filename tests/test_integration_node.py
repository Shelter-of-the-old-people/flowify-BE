from unittest.mock import AsyncMock, patch

from app.core.nodes.integration_node import IntegrationNodeStrategy


async def test_google_sheets_search_text(service_tokens: dict) -> None:
    strategy = IntegrationNodeStrategy({})
    node = {
        "runtime_action": {
            "service": "google_sheets",
            "action": "search_text",
            "config": {
                "spreadsheet_id": "sheet_123",
                "sheet_name": "Policies",
                "search_value": "urgent",
                "search_columns": ["title"],
            },
        }
    }

    with patch("app.core.nodes.integration_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "title"],
                ["1", "urgent ticket"],
                ["2", "normal ticket"],
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result["type"] == "SPREADSHEET_DATA"
    assert result["rows"] == [["1", "urgent ticket"]]


async def test_google_sheets_lookup_row_by_key(service_tokens: dict) -> None:
    strategy = IntegrationNodeStrategy({})
    node = {
        "runtime_action": {
            "service": "google_sheets",
            "action": "lookup_row_by_key",
            "config": {
                "spreadsheet_id": "sheet_123",
                "sheet_name": "Policies",
                "key_column": "id",
                "lookup_value": "2",
            },
        }
    }

    with patch("app.core.nodes.integration_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "title"],
                ["1", "urgent ticket"],
                ["2", "normal ticket"],
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {
        "type": "API_RESPONSE",
        "data": {"id": "2", "title": "normal ticket"},
        "metadata": {
            "service": "google_sheets",
            "action": "lookup_row_by_key",
            "sheet_name": "Policies",
            "spreadsheet_id": "sheet_123",
            "matched": True,
        },
    }
