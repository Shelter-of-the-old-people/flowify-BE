from urllib.parse import quote

from app.services.integrations.base import BaseIntegrationService

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class GoogleSheetsService(BaseIntegrationService):
    """Google Sheets API integration helpers."""

    async def read_range(self, token: str, spreadsheet_id: str, range_a1: str) -> list[list]:
        data = await self._request(
            "GET",
            f"{SHEETS_API}/{spreadsheet_id}/values/{quote(range_a1, safe='!:$,')}",
            token,
        )
        return data.get("values", [])

    async def write_range(
        self, token: str, spreadsheet_id: str, range_a1: str, values: list[list]
    ) -> dict:
        return await self._request(
            "PUT",
            f"{SHEETS_API}/{spreadsheet_id}/values/{quote(range_a1, safe='!:$,')}",
            token,
            json={"values": values},
            params={"valueInputOption": "USER_ENTERED"},
        )

    async def clear_range(self, token: str, spreadsheet_id: str, range_a1: str) -> dict:
        return await self._request(
            "POST",
            f"{SHEETS_API}/{spreadsheet_id}/values/{quote(range_a1, safe='!:$,')}:clear",
            token,
            json={},
        )

    async def append_rows(
        self, token: str, spreadsheet_id: str, range_a1: str, values: list[list]
    ) -> dict:
        return await self._request(
            "POST",
            f"{SHEETS_API}/{spreadsheet_id}/values/{quote(range_a1, safe='!:$,')}:append",
            token,
            json={"values": values},
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        )

    async def list_sheets(self, token: str, spreadsheet_id: str) -> list[dict]:
        data = await self._request(
            "GET",
            f"{SHEETS_API}/{spreadsheet_id}",
            token,
            params={"fields": "sheets.properties"},
        )
        return [
            {"id": sheet["properties"]["sheetId"], "title": sheet["properties"]["title"]}
            for sheet in data.get("sheets", [])
        ]
