import json
from uuid import uuid4

from app.services.integrations.base import BaseIntegrationService

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


class GoogleDriveService(BaseIntegrationService):
    """Google Drive API integration service."""

    async def list_files(
        self, token: str, folder_id: str | None = None, max_results: int = 50
    ) -> list[dict]:
        """List files in a Drive folder."""
        query = f"'{folder_id}' in parents and trashed=false" if folder_id else "trashed=false"
        data = await self._request(
            "GET",
            f"{DRIVE_API}/files",
            token,
            params={
                "q": query,
                "pageSize": max_results,
                "fields": "files(id,name,mimeType,size,modifiedTime)",
            },
        )
        return data.get("files", [])

    async def download_file(self, token: str, file_id: str) -> dict:
        """Return Drive file metadata and text-like content."""
        meta = await self._request(
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            token,
            params={"fields": "id,name,mimeType,size"},
        )
        mime = meta.get("mimeType", "")

        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }

        if mime in export_map:
            content = await self._request(
                "GET",
                f"{DRIVE_API}/files/{file_id}/export",
                token,
                params={"mimeType": export_map[mime]},
            )
        else:
            content = await self._request(
                "GET",
                f"{DRIVE_API}/files/{file_id}",
                token,
                params={"alt": "media"},
            )

        return {
            "id": meta.get("id"),
            "name": meta.get("name"),
            "mimeType": mime,
            "content": content if isinstance(content, str) else str(content),
        }

    async def upload_file(
        self,
        token: str,
        name: str,
        content: bytes,
        folder_id: str | None = None,
        mime_type: str = "application/octet-stream",
    ) -> dict:
        """Upload Drive metadata and file content with multipart upload."""
        metadata: dict = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]

        boundary = f"flowify_{uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

        return await self._request(
            "POST",
            f"{DRIVE_UPLOAD_API}/files",
            token,
            content=body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            params={"uploadType": "multipart", "fields": "id,name,mimeType,webViewLink"},
        )
