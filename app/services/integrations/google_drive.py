import json
from uuid import uuid4

from app.services.integrations.base import BaseIntegrationService

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class GoogleDriveService(BaseIntegrationService):
    """Google Drive API integration service."""

    async def list_files(
        self,
        token: str,
        folder_id: str | None = None,
        max_results: int = 50,
        order_by: str | None = None,
    ) -> list[dict]:
        """List files in a Drive folder."""
        query = f"'{folder_id}' in parents and trashed=false" if folder_id else "trashed=false"
        params = {
            "q": query,
            "pageSize": max_results,
            "fields": "files(id,name,mimeType,size,createdTime,modifiedTime)",
        }
        if order_by:
            params["orderBy"] = order_by

        data = await self._request(
            "GET",
            f"{DRIVE_API}/files",
            token,
            params=params,
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

        if isinstance(content, dict) and isinstance(content.get("text"), str):
            normalized_content = content["text"]
        elif isinstance(content, str):
            normalized_content = content
        else:
            normalized_content = str(content)

        return {
            "id": meta.get("id"),
            "name": meta.get("name"),
            "mimeType": mime,
            "content": normalized_content,
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

    async def ensure_folder_path(
        self,
        token: str,
        parent_folder_id: str | None,
        folder_names: list[str],
    ) -> str | None:
        """Ensure a nested folder path exists and return the deepest folder id."""
        current_parent_id = parent_folder_id
        for folder_name in folder_names:
            if not folder_name:
                continue

            existing_folder = await self._find_folder(token, folder_name, current_parent_id)
            if existing_folder:
                current_parent_id = existing_folder["id"]
                continue

            created_folder = await self._create_folder(token, folder_name, current_parent_id)
            current_parent_id = created_folder["id"]

        return current_parent_id

    async def _find_folder(
        self,
        token: str,
        folder_name: str,
        parent_folder_id: str | None,
    ) -> dict | None:
        escaped_name = folder_name.replace("'", r"\'")
        query_parts = [
            "trashed=false",
            f"mimeType='{DRIVE_FOLDER_MIME_TYPE}'",
            f"name='{escaped_name}'",
        ]
        if parent_folder_id:
            query_parts.append(f"'{parent_folder_id}' in parents")

        data = await self._request(
            "GET",
            f"{DRIVE_API}/files",
            token,
            params={
                "q": " and ".join(query_parts),
                "pageSize": 1,
                "fields": "files(id,name,mimeType)",
            },
        )
        files = data.get("files", [])
        return files[0] if files else None

    async def _create_folder(
        self,
        token: str,
        folder_name: str,
        parent_folder_id: str | None,
    ) -> dict:
        metadata: dict[str, object] = {
            "name": folder_name,
            "mimeType": DRIVE_FOLDER_MIME_TYPE,
        }
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]

        return await self._request(
            "POST",
            f"{DRIVE_API}/files",
            token,
            json=metadata,
            params={"fields": "id,name,mimeType,webViewLink"},
        )
