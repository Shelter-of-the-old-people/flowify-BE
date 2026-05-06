import io
import json
from uuid import uuid4

import httpx

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.base import BaseIntegrationService

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {"application/json", "application/xml"}
MAX_EXTRACTED_TEXT_CHARS = 60000


class GoogleDriveService(BaseIntegrationService):
    """Google Drive API integration service."""

    async def list_files(
        self,
        token: str,
        folder_id: str | None = None,
        max_results: int = 50,
        order_by: str | None = None,
        include_folders: bool = False,
    ) -> list[dict]:
        """List files in a Drive folder."""
        query_parts = ["trashed=false"]
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")
        if not include_folders:
            query_parts.append(f"mimeType != '{DRIVE_FOLDER_MIME_TYPE}'")
        query = " and ".join(query_parts)
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

    async def get_file_metadata(self, token: str, file_id: str) -> dict:
        """Return Drive file metadata without downloading content."""
        return await self._request(
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            token,
            params={"fields": ("id,name,mimeType,size,createdTime,modifiedTime,webViewLink")},
        )

    async def download_file(self, token: str, file_id: str) -> dict:
        """Return Drive file metadata and text-like content."""
        meta = await self._request(
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            token,
            params={"fields": "id,name,mimeType,size,createdTime,modifiedTime"},
        )
        mime = meta.get("mimeType", "")

        if mime in GOOGLE_EXPORT_MIME_TYPES:
            content = await self._request(
                "GET",
                f"{DRIVE_API}/files/{file_id}/export",
                token,
                params={"mimeType": GOOGLE_EXPORT_MIME_TYPES[mime]},
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
            "createdTime": meta.get("createdTime", ""),
            "modifiedTime": meta.get("modifiedTime", ""),
            "content": normalized_content,
        }

    async def download_file_bytes(self, token: str, file_id: str) -> bytes:
        """Download original Drive file bytes."""
        return await self._request_bytes(
            token,
            f"{DRIVE_API}/files/{file_id}",
            params={"alt": "media"},
        )

    async def extract_file_text(self, token: str, file_id: str, mime_type: str) -> dict:
        """Extract text for LLM input without storing original file bytes."""
        try:
            if mime_type in GOOGLE_EXPORT_MIME_TYPES:
                raw = await self._request_bytes(
                    token,
                    f"{DRIVE_API}/files/{file_id}/export",
                    params={"mimeType": GOOGLE_EXPORT_MIME_TYPES[mime_type]},
                )
                return self._text_result(raw.decode("utf-8", errors="replace"))

            raw = await self.download_file_bytes(token, file_id)
            if self._is_text_mime_type(mime_type):
                return self._text_result(raw.decode("utf-8", errors="replace"))
            if mime_type == "application/pdf":
                return self._text_result(self._extract_pdf_text(raw))
            return self._extraction_result(status="unsupported")
        except FlowifyException:
            raise
        except Exception as e:
            return self._extraction_result(status="failed", error=str(e))

    async def _request_bytes(
        self,
        token: str,
        url: str,
        params: dict | None = None,
    ) -> bytes:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers, params=params)

            if response.status_code == 401:
                raise FlowifyException(
                    ErrorCode.OAUTH_TOKEN_INVALID,
                    detail="OAuth token is invalid.",
                    context={"url": url, "status": 401},
                )
            response.raise_for_status()
            return response.content
        except FlowifyException:
            raise
        except Exception as e:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"Google Drive file download failed: {url}",
                context={"url": url, "error": str(e)},
            ) from e

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
            (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode()
        )

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

    @staticmethod
    def _is_text_mime_type(mime_type: str) -> bool:
        return mime_type.startswith(TEXT_MIME_PREFIXES) or mime_type in TEXT_MIME_TYPES

    @staticmethod
    def _extract_pdf_text(raw: bytes) -> str:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    @staticmethod
    def _text_result(text: str) -> dict:
        truncated = len(text) > MAX_EXTRACTED_TEXT_CHARS
        if truncated:
            text = text[:MAX_EXTRACTED_TEXT_CHARS]
        return GoogleDriveService._extraction_result(
            text=text,
            status="truncated" if truncated else "success",
            truncated=truncated,
        )

    @staticmethod
    def _extraction_result(
        text: str = "",
        status: str = "success",
        truncated: bool = False,
        error: str | None = None,
    ) -> dict:
        return {
            "text": text,
            "status": status,
            "truncated": truncated,
            "error": error,
        }
