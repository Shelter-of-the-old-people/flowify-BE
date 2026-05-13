import csv
import io
import json
import re
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx

from app.common.errors import ErrorCode, FlowifyException
from app.core.document_content import (
    CONTENT_STATUS_FAILED,
    CONTENT_STATUS_TOO_LARGE,
    CONTENT_STATUS_UNSUPPORTED,
    DEFAULT_CONTENT_LIMITS,
    MAX_DOWNLOAD_BYTES,
    MAX_EXTRACTED_CHARS,
    build_extraction_result,
)
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
CSV_MIME_TYPES = {"text/csv", "text/tab-separated-values"}
DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PPTX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
HWPX_MIME_TYPES = {
    "application/vnd.hancom.hwpx",
    "application/x-hwpx",
}
EXTRACTION_LIMITS = dict(DEFAULT_CONTENT_LIMITS)


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

    async def extract_file_text(
        self,
        token: str,
        file_id: str,
        mime_type: str,
        filename: str = "",
        file_size: int | str | None = None,
    ) -> dict:
        """Extract text for LLM input without storing original file bytes."""
        try:
            if self._is_size_over_download_limit(file_size):
                return self._too_large_result(file_size)

            if mime_type in GOOGLE_EXPORT_MIME_TYPES:
                raw = await self._request_bytes(
                    token,
                    f"{DRIVE_API}/files/{file_id}/export",
                    params={"mimeType": GOOGLE_EXPORT_MIME_TYPES[mime_type]},
                )
                if self._is_size_over_download_limit(len(raw)):
                    return self._too_large_result(len(raw))
                text = self._decode_text(raw)
                if GOOGLE_EXPORT_MIME_TYPES[mime_type] == "text/csv":
                    return self._csv_result(text)
                return self._text_result(text, extraction_method="google_export")

            raw = await self.download_file_bytes(token, file_id)
            if self._is_size_over_download_limit(len(raw)):
                return self._too_large_result(len(raw))
            if self._is_docx_mime_type(mime_type, filename):
                return self._docx_result(raw)
            if self._is_pptx_mime_type(mime_type, filename):
                return self._pptx_result(raw)
            if self._is_hwpx_mime_type(mime_type, filename):
                return self._hwpx_result(raw)
            if self._is_csv_mime_type(mime_type, filename):
                return self._csv_result(self._decode_text(raw))
            if self._is_text_mime_type(mime_type):
                return self._text_result(self._decode_text(raw))
            if mime_type == "application/pdf":
                text = self._extract_pdf_text(raw)
                if not text:
                    return self._extraction_result(
                        status="unsupported",
                        content_status=CONTENT_STATUS_UNSUPPORTED,
                        error="스캔 PDF/OCR 문서는 아직 지원하지 않습니다.",
                    )
                return self._text_result(text, extraction_method="pdf_text")
            return self._extraction_result(
                status="unsupported",
                content_status=CONTENT_STATUS_UNSUPPORTED,
                error="This file type is not supported for text extraction yet.",
            )
        except FlowifyException:
            raise
        except Exception as e:
            return self._extraction_result(
                status="failed",
                content_status=CONTENT_STATUS_FAILED,
                error=str(e),
            )

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
    def _is_csv_mime_type(mime_type: str, filename: str = "") -> bool:
        suffix = Path(filename or "").suffix.lower()
        return mime_type in CSV_MIME_TYPES or suffix in {".csv", ".tsv"}

    @staticmethod
    def _is_docx_mime_type(mime_type: str, filename: str = "") -> bool:
        return mime_type in DOCX_MIME_TYPES or Path(filename or "").suffix.lower() == ".docx"

    @staticmethod
    def _is_pptx_mime_type(mime_type: str, filename: str = "") -> bool:
        return mime_type in PPTX_MIME_TYPES or Path(filename or "").suffix.lower() == ".pptx"

    @staticmethod
    def _is_hwpx_mime_type(mime_type: str, filename: str = "") -> bool:
        return mime_type in HWPX_MIME_TYPES or Path(filename or "").suffix.lower() == ".hwpx"

    @staticmethod
    def _decode_text(raw: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _coerce_size(value: int | str | None) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_size_over_download_limit(value: int | str | None) -> bool:
        size = GoogleDriveService._coerce_size(value)
        return size is not None and size > MAX_DOWNLOAD_BYTES

    @staticmethod
    def _too_large_result(size: int | str | None = None) -> dict:
        size_value = GoogleDriveService._coerce_size(size)
        metadata = {"observed_size_bytes": size_value} if size_value is not None else None
        return GoogleDriveService._extraction_result(
            status="failed",
            content_status=CONTENT_STATUS_TOO_LARGE,
            error="파일이 현재 처리 가능한 크기를 초과했습니다.",
            limits=metadata,
        )

    @staticmethod
    def _docx_result(raw: bytes) -> dict:
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                document_xml = archive.read("word/document.xml")
        except (BadZipFile, KeyError, ElementTree.ParseError):
            return GoogleDriveService._extraction_result(
                status="failed",
                content_status=CONTENT_STATUS_FAILED,
                error="DOCX 문서 본문을 읽는 중 오류가 발생했습니다.",
            )

        try:
            root = ElementTree.fromstring(document_xml)
        except ElementTree.ParseError:
            return GoogleDriveService._extraction_result(
                status="failed",
                content_status=CONTENT_STATUS_FAILED,
                error="DOCX 문서 본문을 읽는 중 오류가 발생했습니다.",
            )

        body = GoogleDriveService._first_descendant(root, "body")
        lines: list[str] = []
        for child in list(body) if body is not None else []:
            tag = GoogleDriveService._local_name(child.tag)
            if tag == "p":
                text = GoogleDriveService._xml_text(child)
                if text:
                    lines.append(text)
            elif tag == "tbl":
                lines.extend(GoogleDriveService._docx_table_lines(child))

        return GoogleDriveService._text_result(
            "\n".join(lines),
            extraction_method="docx_xml",
            content_kind="plain_text",
        )

    @staticmethod
    def _pptx_result(raw: bytes) -> dict:
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                slide_names = sorted(
                    (
                        name
                        for name in archive.namelist()
                        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                    ),
                    key=GoogleDriveService._slide_number,
                )
                lines: list[str] = []
                for index, slide_name in enumerate(slide_names, start=1):
                    slide_text = GoogleDriveService._xml_text_bytes(archive.read(slide_name))
                    note_name = f"ppt/notesSlides/notesSlide{GoogleDriveService._slide_number(slide_name)}.xml"
                    note_text = (
                        GoogleDriveService._xml_text_bytes(archive.read(note_name))
                        if note_name in archive.namelist()
                        else ""
                    )
                    parts = [f"Slide {index}:"]
                    if slide_text:
                        parts.append(slide_text)
                    if note_text:
                        parts.append(f"Notes: {note_text}")
                    lines.append("\n".join(parts))
        except (BadZipFile, KeyError, ElementTree.ParseError):
            return GoogleDriveService._extraction_result(
                status="failed",
                content_status=CONTENT_STATUS_FAILED,
                error="PPTX 문서 본문을 읽는 중 오류가 발생했습니다.",
            )

        return GoogleDriveService._text_result(
            "\n\n".join(lines),
            extraction_method="pptx_xml",
            content_kind="slide_text",
        )

    @staticmethod
    def _hwpx_result(raw: bytes) -> dict:
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                section_names = sorted(
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"Contents/section\d+\.xml", name, flags=re.IGNORECASE)
                )
                if not section_names:
                    section_names = sorted(
                        name
                        for name in archive.namelist()
                        if name.lower().startswith("contents/") and name.lower().endswith(".xml")
                    )
                text = "\n".join(
                    value
                    for value in (
                        GoogleDriveService._xml_text_bytes(archive.read(name))
                        for name in section_names
                    )
                    if value
                )
        except (BadZipFile, KeyError, ElementTree.ParseError):
            return GoogleDriveService._extraction_result(
                status="failed",
                content_status=CONTENT_STATUS_FAILED,
                error="HWPX 문서 본문을 읽는 중 오류가 발생했습니다.",
            )

        return GoogleDriveService._text_result(
            text,
            extraction_method="hwpx_xml",
            content_kind="plain_text",
        )

    @staticmethod
    def _extract_pdf_text(raw: bytes) -> str:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _first_descendant(root: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
        for element in root.iter():
            if GoogleDriveService._local_name(element.tag) == local_name:
                return element
        return None

    @staticmethod
    def _xml_text_bytes(raw: bytes) -> str:
        root = ElementTree.fromstring(raw)
        return GoogleDriveService._xml_text(root)

    @staticmethod
    def _xml_text(root: ElementTree.Element) -> str:
        parts = []
        for element in root.iter():
            if GoogleDriveService._local_name(element.tag) == "t" and element.text:
                parts.append(element.text)
        return " ".join(part.strip() for part in parts if part and part.strip()).strip()

    @staticmethod
    def _docx_table_lines(table: ElementTree.Element) -> list[str]:
        lines = []
        for row in table.iter():
            if GoogleDriveService._local_name(row.tag) != "tr":
                continue
            cells = [
                GoogleDriveService._xml_text(cell)
                for cell in row
                if GoogleDriveService._local_name(cell.tag) == "tc"
            ]
            cells = [cell for cell in cells if cell]
            if cells:
                lines.append(" | ".join(cells))
        return lines

    @staticmethod
    def _slide_number(path: str) -> int:
        match = re.search(r"(\d+)\.xml$", path)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _text_result(
        text: str,
        *,
        extraction_method: str = "plain_text",
        content_kind: str = "plain_text",
    ) -> dict:
        truncated = len(text) > MAX_EXTRACTED_CHARS
        original_char_count = len(text)
        if truncated:
            text = text[:MAX_EXTRACTED_CHARS]
        return GoogleDriveService._extraction_result(
            text=text,
            status="truncated" if truncated else "success",
            truncated=truncated,
            extraction_method=extraction_method,
            content_kind=content_kind,
            original_char_count=original_char_count,
        )

    @staticmethod
    def _csv_result(text: str) -> dict:
        dialect = csv.excel_tab if "\t" in text[:2048] else csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect=dialect))
        lines = []
        if rows:
            lines.append("Headers: " + ", ".join(rows[0]))
            for idx, row in enumerate(rows[1:101], start=1):
                lines.append(f"Row {idx}: " + ", ".join(row))
            if len(rows) > 101:
                lines.append(f"... {len(rows) - 101} more rows")
        table_text = "\n".join(lines) if lines else text
        return GoogleDriveService._text_result(
            table_text,
            extraction_method="csv_parse",
            content_kind="table_text",
        )

    @staticmethod
    def _extraction_result(
        text: str = "",
        status: str = "success",
        truncated: bool = False,
        error: str | None = None,
        content_status: str | None = None,
        extraction_method: str = "plain_text",
        content_kind: str = "plain_text",
        original_char_count: int | None = None,
        limits: dict | None = None,
    ) -> dict:
        return build_extraction_result(
            content=text or None,
            content_status=content_status or "available",
            content_error=error,
            extraction_method=extraction_method if text else "none",
            content_kind=content_kind if text else "none",
            truncated=truncated,
            original_char_count=original_char_count,
            limits={**EXTRACTION_LIMITS, **(limits or {})},
        )
