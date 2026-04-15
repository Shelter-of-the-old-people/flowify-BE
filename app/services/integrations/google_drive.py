from app.services.integrations.base import BaseIntegrationService

DRIVE_API = "https://www.googleapis.com/drive/v3"


class GoogleDriveService(BaseIntegrationService):
    """Google Drive API 연동 서비스 (DC-F0401)."""

    async def list_files(
        self, token: str, folder_id: str | None = None, max_results: int = 50
    ) -> list[dict]:
        """폴더 내 파일 목록을 조회합니다."""
        query = f"'{folder_id}' in parents and trashed=false" if folder_id else "trashed=false"
        data = await self._request(
            "GET", f"{DRIVE_API}/files", token,
            params={
                "q": query,
                "pageSize": max_results,
                "fields": "files(id,name,mimeType,size,modifiedTime)",
            },
        )
        return data.get("files", [])

    async def download_file(self, token: str, file_id: str) -> dict:
        """파일 메타데이터와 텍스트 내용을 반환합니다.

        Google Docs/Sheets/Slides는 export, 일반 파일은 직접 다운로드.
        """
        # 먼저 메타데이터 조회
        meta = await self._request(
            "GET", f"{DRIVE_API}/files/{file_id}", token,
            params={"fields": "id,name,mimeType,size"},
        )
        mime = meta.get("mimeType", "")

        # Google Docs 계열은 텍스트로 export
        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }

        if mime in export_map:
            content = await self._request(
                "GET", f"{DRIVE_API}/files/{file_id}/export", token,
                params={"mimeType": export_map[mime]},
            )
        else:
            content = await self._request(
                "GET", f"{DRIVE_API}/files/{file_id}", token,
                params={"alt": "media"},
            )

        return {
            "id": meta.get("id"),
            "name": meta.get("name"),
            "mimeType": mime,
            "content": content if isinstance(content, str) else str(content),
        }

    async def upload_file(
        self, token: str, name: str, content: bytes, folder_id: str | None = None
    ) -> dict:
        """파일을 업로드합니다 (메타데이터 전용, 간이 업로드)."""
        metadata: dict = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]

        return await self._request(
            "POST", f"{DRIVE_API}/files", token,
            json=metadata,
            params={"uploadType": "multipart"},
        )
