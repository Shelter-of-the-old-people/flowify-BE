"""OutputNodeStrategy for runtime_sink based external service delivery."""

import base64
import csv
from datetime import UTC, datetime
import io
import json
import logging
from typing import Any

import httpx

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_calendar import GoogleCalendarService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.notion import NotionService
from app.services.integrations.slack import SlackService

logger = logging.getLogger(__name__)

SUPPORTED_SINKS = {"slack", "gmail", "notion", "google_drive", "google_sheets", "google_calendar"}

ACCEPTED_INPUT_TYPES: dict[str, set[str]] = {
    "slack": {"TEXT"},
    "gmail": {"TEXT", "SINGLE_FILE", "FILE_LIST"},
    "notion": {"TEXT", "SPREADSHEET_DATA", "API_RESPONSE"},
    "google_drive": {"TEXT", "SINGLE_FILE", "FILE_LIST", "SPREADSHEET_DATA"},
    "google_sheets": {"TEXT", "SPREADSHEET_DATA", "API_RESPONSE"},
    "google_calendar": {"TEXT", "SCHEDULE_DATA"},
}

REQUIRED_CONFIG: dict[str, list[str]] = {
    "slack": ["channel"],
    "gmail": ["to", "subject", "action"],
    "notion": ["target_type", "target_id"],
    "google_drive": ["folder_id"],
    "google_sheets": ["spreadsheet_id", "write_mode"],
    "google_calendar": ["calendar_id", "event_title_template", "action"],
}


class OutputNodeStrategy(NodeStrategy):
    """Deliver canonical payloads to runtime sinks."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_sink = node.get("runtime_sink")
        if not runtime_sink:
            logger.info("OutputNode fallback: %s", input_data)
            return {"status": "sent", "service": "console", "detail": {}}

        service = runtime_sink["service"]
        sink_config = runtime_sink.get("config", {})

        if service not in SUPPORTED_SINKS:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SINK,
                detail=f"service={service} is not supported in current runtime phase",
            )

        if input_data:
            data_type = input_data.get("type", "")
            accepted = ACCEPTED_INPUT_TYPES.get(service, set())
            if data_type and data_type not in accepted:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail=f"Sink '{service}' does not accept input type '{data_type}'. Accepted: {accepted}",
                )

        token = service_tokens.get(service, "")
        if not token:
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{service}' service token is missing.",
            )

        if service == "slack":
            result = await self._send_slack(token, sink_config, input_data or {})
        elif service == "gmail":
            result = await self._send_gmail(token, sink_config, input_data or {})
        elif service == "notion":
            result = await self._send_notion(token, sink_config, input_data or {})
        elif service == "google_drive":
            result = await self._send_google_drive(
                token, sink_config, input_data or {}, service_tokens
            )
        elif service == "google_sheets":
            result = await self._send_google_sheets(token, sink_config, input_data or {})
        elif service == "google_calendar":
            result = await self._send_google_calendar(token, sink_config, input_data or {})
        else:
            result = {}

        return {"status": "sent", "service": service, "detail": result}

    def validate(self, node: dict[str, Any]) -> bool:
        rk = node.get("runtime_sink")
        if not rk:
            return False
        service = rk.get("service", "")
        if service not in SUPPORTED_SINKS:
            return False
        config = rk.get("config", {})
        required = REQUIRED_CONFIG.get(service, [])
        return all(config.get(f) for f in required)

    async def _send_slack(self, token: str, config: dict, input_data: dict) -> dict:
        channel = config["channel"]
        message = input_data.get("content", "")
        svc = SlackService()
        return await svc.send_message(token, channel, message)

    async def _send_gmail(self, token: str, config: dict, input_data: dict) -> dict:
        to = config["to"]
        subject = config["subject"]
        action = config.get("action", "send").lower()
        if action not in {"send", "draft"}:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"Gmail action must be 'send' or 'draft', got '{action}'.",
            )

        body, attachments = self._gmail_body_and_attachments(config, input_data)
        svc = GmailService()
        if action == "send":
            if attachments:
                return await svc.send_message(token, to, subject, body, attachments)
            return await svc.send_message(token, to, subject, body)

        if attachments:
            return await svc.create_draft(token, to, subject, body, attachments)
        return await svc.create_draft(token, to, subject, body)

    async def _send_notion(self, token: str, config: dict, input_data: dict) -> dict:
        target_type = config["target_type"]
        target_id = config["target_id"]
        data_type = input_data.get("type", "TEXT")

        svc = NotionService()
        if data_type == "TEXT":
            content = input_data.get("content", "")
            title = self._resolve_notion_title(config, input_data, "Flowify Output")
            if target_type == "page":
                return await svc.create_page(token, target_id, title, content)
            return await svc.create_page(token, target_id, title, content)
        if data_type == "SPREADSHEET_DATA":
            rows = input_data.get("rows", [])
            content = "\n".join(", ".join(str(c) for c in row) for row in rows)
            title = self._resolve_notion_title(config, input_data, "Flowify Data")
            return await svc.create_page(token, target_id, title, content)
        title = self._resolve_notion_title(config, input_data, "Flowify Output")
        return await svc.create_page(token, target_id, title, str(input_data))

    async def _send_google_drive(
        self,
        token: str,
        config: dict,
        input_data: dict,
        service_tokens: dict[str, str],
    ) -> dict:
        folder_id = config.get("folder_id")
        data_type = input_data.get("type", "TEXT")
        svc = GoogleDriveService()

        if data_type == "SINGLE_FILE":
            raw_filename = input_data.get("filename", "output.txt")
            destination_folder_id, filename = await self._resolve_google_drive_destination(
                svc,
                token,
                folder_id,
                raw_filename,
            )
            mime_type = input_data.get("mime_type") or "application/octet-stream"
            content = await self._get_single_file_bytes(input_data, service_tokens)
            return await svc.upload_file(
                token,
                filename,
                content,
                destination_folder_id,
                mime_type,
            )

        if data_type == "TEXT":
            content = self._to_bytes(input_data.get("content", ""))
            file_format = config.get("file_format", "txt")
            mime_type = config.get("mime_type", "text/plain")
            return await svc.upload_file(token, f"output.{file_format}", content, folder_id, mime_type)

        if data_type == "FILE_LIST":
            results = []
            for index, item in enumerate(input_data.get("items", []), start=1):
                raw_filename = item.get("filename") or f"file_{index}"
                destination_folder_id, fallback_filename = (
                    await self._resolve_google_drive_destination(
                        svc,
                        token,
                        folder_id,
                        raw_filename,
                    )
                )
                filename, mime_type, content = await self._get_file_list_item_upload_data(
                    fallback_filename,
                    item, service_tokens
                )
                results.append(
                    await svc.upload_file(
                        token,
                        filename,
                        content,
                        destination_folder_id,
                        mime_type,
                    )
                )
            return {"uploaded": results, "count": len(results)}

        if data_type == "SPREADSHEET_DATA":
            sheet_name = input_data.get("sheet_name") or "spreadsheet"
            filename = config.get("filename") or f"{sheet_name}.csv"
            content = self._spreadsheet_to_csv(input_data).encode("utf-8")
            return await svc.upload_file(token, filename, content, folder_id, "text/csv")

        return {}

    async def _send_google_sheets(self, token: str, config: dict, input_data: dict) -> dict:
        spreadsheet_id = config["spreadsheet_id"]
        write_mode = config.get("write_mode", "append")
        sheet_name = config.get("sheet_name", "Sheet1")
        data_type = input_data.get("type", "TEXT")
        svc = GoogleSheetsService()

        if data_type == "SPREADSHEET_DATA":
            headers = input_data.get("headers")
            rows = input_data.get("rows", [])
            values = ([headers] + rows) if headers else rows
        elif data_type == "TEXT":
            values = [[input_data.get("content", "")]]
        else:
            values = [[str(input_data)]]

        if write_mode == "overwrite":
            return await svc.write_range(token, spreadsheet_id, sheet_name, values)
        return await svc.append_rows(token, spreadsheet_id, sheet_name, values)

    async def _send_google_calendar(self, token: str, config: dict, input_data: dict) -> dict:
        calendar_id = config.get("calendar_id", "primary")
        action = config.get("action", "create").lower()
        data_type = input_data.get("type", "TEXT")
        svc = GoogleCalendarService()

        if action not in {"create", "update"}:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"Calendar action must be 'create' or 'update', got '{action}'.",
            )

        if data_type == "SCHEDULE_DATA":
            results = []
            for item in input_data.get("items", []):
                event = self._calendar_event_from_schedule_item(config, item)
                if action == "update":
                    event_id = item.get("event_id") or item.get("id") or config.get("event_id")
                    if not event_id:
                        raise FlowifyException(
                            ErrorCode.INVALID_REQUEST,
                            detail="Calendar update requires event_id in config or schedule item.",
                        )
                    results.append(await svc.update_event(token, calendar_id, event_id, event))
                else:
                    results.append(await svc.create_event(token, calendar_id, event))
            result_key = "events_updated" if action == "update" else "events_created"
            return {result_key: len(results), "results": results}

        if data_type == "TEXT":
            event = {
                "summary": config.get("event_title_template", "Flowify Event"),
                "description": input_data.get("content", ""),
                "start": {"dateTime": config.get("start_time", "")},
                "end": {"dateTime": config.get("end_time", "")},
            }
            if action == "update":
                event_id = config.get("event_id")
                if not event_id:
                    raise FlowifyException(
                        ErrorCode.INVALID_REQUEST,
                        detail="Calendar update requires runtime_sink.config.event_id.",
                    )
                return await svc.update_event(token, calendar_id, event_id, event)
            return await svc.create_event(token, calendar_id, event)

        return {}

    @staticmethod
    def _gmail_body_and_attachments(config: dict, input_data: dict) -> tuple[str, list[dict]]:
        data_type = input_data.get("type", "TEXT")
        if data_type == "TEXT":
            return input_data.get("content", ""), []

        if data_type == "SINGLE_FILE":
            filename = input_data.get("filename", "attachment")
            body = config.get("body") or f"Attached file: {filename}"
            return body, [
                {
                    "filename": filename,
                    "mime_type": input_data.get("mime_type") or "application/octet-stream",
                    "content": input_data.get("content", ""),
                }
            ]

        if data_type == "FILE_LIST":
            items = input_data.get("items", [])
            attachments = [
                {
                    "filename": item.get("filename") or "attachment",
                    "mime_type": item.get("mime_type") or "application/octet-stream",
                    "content": item["content"],
                }
                for item in items
                if item.get("content") is not None
            ]
            body = config.get("body") or OutputNodeStrategy._file_list_summary(items)
            return body, attachments

        return str(input_data), []

    @staticmethod
    def _file_list_summary(items: list[dict]) -> str:
        if not items:
            return ""
        lines = ["Files:"]
        for item in items:
            filename = item.get("filename", "")
            mime_type = item.get("mime_type", "")
            size = item.get("size")
            lines.append(f"- {filename} ({mime_type}, {size} bytes)")
        return "\n".join(lines)

    @staticmethod
    def _calendar_event_from_schedule_item(config: dict, item: dict) -> dict:
        return {
            "summary": item.get("title") or config.get("event_title_template", "Flowify Event"),
            "start": {"dateTime": item.get("start_time", "")},
            "end": {"dateTime": item.get("end_time", item.get("start_time", ""))},
            "location": item.get("location", ""),
            "description": item.get("description", ""),
        }

    @staticmethod
    def _spreadsheet_to_csv(input_data: dict) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        headers = input_data.get("headers") or []
        if headers:
            writer.writerow(headers)
        writer.writerows(input_data.get("rows", []))
        return buffer.getvalue()

    @staticmethod
    def _resolve_notion_title(
        config: dict[str, Any],
        input_data: dict[str, Any],
        default_title: str,
    ) -> str:
        template = str(config.get("title_template") or "").strip()
        if not template:
            return default_title

        replacements = {
            "date": datetime.now(UTC).date().isoformat(),
            "filename": str(input_data.get("filename", "")),
            "mime_type": str(input_data.get("mime_type", "")),
            "sheet_name": str(input_data.get("sheet_name", "")),
            "source_url": str(input_data.get("url", "")),
        }

        title = template
        for key, value in replacements.items():
            title = title.replace(f"{{{{{key}}}}}", value)

        resolved = title.strip()
        return resolved or default_title

    @staticmethod
    def _metadata_filename(filename: str) -> str:
        if filename.endswith(".json"):
            return filename
        return f"{filename}.metadata.json"

    async def _get_single_file_bytes(
        self,
        input_data: dict[str, Any],
        service_tokens: dict[str, str],
    ) -> bytes:
        content = input_data.get("content")
        if content is not None:
            return self._to_bytes(content)

        url = input_data.get("url")
        if url:
            return await self._download_file_from_url(url, service_tokens)

        return b""

    async def _get_file_list_item_upload_data(
        self,
        filename: str,
        item: dict[str, Any],
        service_tokens: dict[str, str],
    ) -> tuple[str, str, bytes]:
        mime_type = item.get("mime_type") or "application/octet-stream"
        content = item.get("content")
        if content is not None:
            return filename, mime_type, self._to_bytes(content)

        url = item.get("url")
        if url:
            return filename, mime_type, await self._download_file_from_url(url, service_tokens)

        return self._metadata_filename(filename), "application/json", self._to_bytes(
            json.dumps(item)
        )

    async def _download_file_from_url(
        self,
        url: str,
        service_tokens: dict[str, str],
    ) -> bytes:
        token = self._resolve_download_token(url, service_tokens)
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)

            if resp.status_code == 401:
                raise FlowifyException(
                    ErrorCode.OAUTH_TOKEN_INVALID,
                    detail="OAuth 토큰이 만료되었거나 유효하지 않습니다.",
                    context={"url": url, "status": 401},
                )
            if resp.status_code == 403:
                raise FlowifyException(
                    ErrorCode.EXTERNAL_SERVICE_ERROR,
                    detail="파일 다운로드 권한이 없습니다.",
                    context={"url": url, "status": 403},
                )
            if resp.status_code == 404:
                raise FlowifyException(
                    ErrorCode.EXTERNAL_SERVICE_ERROR,
                    detail="다운로드할 파일을 찾을 수 없습니다.",
                    context={"url": url, "status": 404},
                )

            resp.raise_for_status()
            return resp.content
        except FlowifyException:
            raise
        except Exception as e:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"파일 다운로드 실패: {url}",
                context={"url": url, "error": str(e)},
            ) from e

    @staticmethod
    def _resolve_download_token(url: str, service_tokens: dict[str, str]) -> str | None:
        lower_url = url.lower()
        if "canvas" in lower_url:
            return service_tokens.get("canvas_lms")
        if "googleapis.com" in lower_url or "drive.google.com" in lower_url:
            return service_tokens.get("google_drive")
        return None

    async def _resolve_google_drive_destination(
        self,
        svc: GoogleDriveService,
        token: str,
        root_folder_id: str | None,
        filename: str,
    ) -> tuple[str | None, str]:
        normalized_filename = str(filename).replace("\\", "/")
        path_segments = [segment.strip() for segment in normalized_filename.split("/") if segment.strip()]
        if len(path_segments) <= 1:
            return root_folder_id, path_segments[0] if path_segments else filename

        destination_folder_id = await svc.ensure_folder_path(
            token,
            root_folder_id,
            path_segments[:-1],
        )
        return destination_folder_id, path_segments[-1]

    @staticmethod
    def _to_bytes(content: bytes | str | None) -> bytes:
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        try:
            return base64.b64decode(content, validate=True)
        except Exception:
            return content.encode("utf-8")
