from app.services.integrations.base import BaseIntegrationService

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class GoogleSheetsService(BaseIntegrationService):
    """Google Sheets API 연동 서비스 (DC-F0407)."""

    async def read_range(
        self, token: str, spreadsheet_id: str, range: str
    ) -> list[list]:
        """스프레드시트의 지정 범위를 읽습니다."""
        data = await self._request(
            "GET", f"{SHEETS_API}/{spreadsheet_id}/values/{range}", token,
        )
        return data.get("values", [])

    async def write_range(
        self, token: str, spreadsheet_id: str, range: str, values: list[list]
    ) -> dict:
        """스프레드시트의 지정 범위에 데이터를 씁니다."""
        return await self._request(
            "PUT", f"{SHEETS_API}/{spreadsheet_id}/values/{range}", token,
            json={"values": values},
            params={"valueInputOption": "USER_ENTERED"},
        )

    async def append_rows(
        self, token: str, spreadsheet_id: str, range: str, values: list[list]
    ) -> dict:
        """스프레드시트 끝에 행을 추가합니다."""
        return await self._request(
            "POST", f"{SHEETS_API}/{spreadsheet_id}/values/{range}:append", token,
            json={"values": values},
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        )

    async def list_sheets(self, token: str, spreadsheet_id: str) -> list[dict]:
        """스프레드시트 내 시트 목록을 조회합니다."""
        data = await self._request(
            "GET", f"{SHEETS_API}/{spreadsheet_id}", token,
            params={"fields": "sheets.properties"},
        )
        return [
            {"id": s["properties"]["sheetId"], "title": s["properties"]["title"]}
            for s in data.get("sheets", [])
        ]
