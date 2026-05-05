"""Input node strategy for runtime source collection.

Reads ``runtime_source`` metadata from a workflow node, fetches data from the
matching external service, and returns a canonical payload that matches the
declared input type.
"""

import logging
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy
from app.services.integrations.canvas_lms import CanvasLmsService
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.slack import SlackService

logger = logging.getLogger(__name__)

# Phase 1 supported source modes only.
SUPPORTED_SOURCES: dict[str, set[str]] = {
    "google_drive": {
        "single_file",
        "file_changed",
        "new_file",
        "folder_new_file",
        "folder_all_files",
    },
    "gmail": {
        "single_email",
        "new_email",
        "sender_email",
        "starred_email",
        "label_emails",
        "attachment_email",
    },
    "google_sheets": {"sheet_all", "new_row", "row_updated"},
    "slack": {"channel_messages"},
    "canvas_lms": {"course_files", "course_new_file", "term_all_files"},
}


class InputNodeStrategy(NodeStrategy):
    """Fetch external source data and normalize it into canonical payloads."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_source = node.get("runtime_source")
        if not runtime_source:
            # Transitional fallback for older config-based nodes.
            return {"type": "TEXT", "content": self.config.get("data", "")}

        service = runtime_source["service"]
        mode = runtime_source["mode"]
        target = runtime_source.get("target", "")
        canonical_type = runtime_source.get("canonical_input_type", "TEXT")
        config = node.get("config") or {}

        token = service_tokens.get(service, "")
        if not token and service not in ("web_crawl",):
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{service}' 서비스의 토큰이 없습니다.",
            )

        if service == "google_drive":
            return await self._fetch_google_drive(token, mode, target, canonical_type)
        if service == "gmail":
            return await self._fetch_gmail(
                token,
                mode,
                target,
                canonical_type,
                self._resolve_max_results(config),
            )
        if service == "google_sheets":
            return await self._fetch_google_sheets(token, mode, target, canonical_type)
        if service == "slack":
            return await self._fetch_slack(token, mode, target)
        if service == "canvas_lms":
            return await self._fetch_canvas_lms(token, mode, target)

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service={service}, mode={mode} is not supported in current runtime phase",
        )

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_source = node.get("runtime_source")
        if not runtime_source:
            return False

        service = runtime_source.get("service", "")
        mode = runtime_source.get("mode", "")
        supported_modes = SUPPORTED_SOURCES.get(service)
        if supported_modes is None:
            return False
        return mode in supported_modes

    # Google Drive

    async def _fetch_google_drive(
        self, token: str, mode: str, target: str, canonical_type: str
    ) -> dict[str, Any]:
        svc = GoogleDriveService()

        if mode == "single_file":
            file_data = await svc.download_file(token, target)
            return {
                "type": "SINGLE_FILE",
                "file_id": target,
                "filename": file_data.get("name", ""),
                "content": file_data.get("content", ""),
                "mime_type": file_data.get("mimeType", ""),
                "created_time": file_data.get("createdTime", ""),
                "modified_time": file_data.get("modifiedTime", ""),
                "url": f"https://drive.google.com/file/d/{target}",
            }

        if mode in ("file_changed", "new_file", "folder_new_file"):
            files = await svc.list_files(
                token,
                folder_id=target,
                max_results=1,
                order_by="createdTime desc",
            )
            if not files:
                return {
                    "type": "SINGLE_FILE",
                    "file_id": "",
                    "filename": "",
                    "content": "",
                    "mime_type": "",
                    "url": "",
                    "created_time": "",
                    "modified_time": "",
                }

            latest_file = files[0]
            file_data = await svc.download_file(token, latest_file["id"])
            return {
                "type": "SINGLE_FILE",
                "file_id": latest_file["id"],
                "filename": latest_file.get("name", ""),
                "content": file_data.get("content", ""),
                "mime_type": latest_file.get("mimeType", ""),
                "created_time": latest_file.get("createdTime", ""),
                "modified_time": latest_file.get("modifiedTime", ""),
                "url": f"https://drive.google.com/file/d/{latest_file['id']}",
            }

        if mode == "folder_all_files":
            files = await svc.list_files(token, folder_id=target)
            return {
                "type": "FILE_LIST",
                "items": [
                    {
                        "file_id": drive_file.get("id", ""),
                        "filename": drive_file.get("name", ""),
                        "mime_type": drive_file.get("mimeType", ""),
                        "size": drive_file.get("size"),
                        "created_time": drive_file.get("createdTime", ""),
                        "modified_time": drive_file.get("modifiedTime", ""),
                        "url": f"https://drive.google.com/file/d/{drive_file['id']}",
                    }
                    for drive_file in files
                ],
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_drive, mode={mode} is not supported",
        )

    # Gmail

    async def _fetch_gmail(
        self,
        token: str,
        mode: str,
        target: str,
        canonical_type: str,
        max_results: int,
    ) -> dict[str, Any]:
        svc = GmailService()

        if mode == "single_email":
            msg = await svc.get_message(token, target)
            return self._to_single_email(msg)

        if mode == "new_email":
            msgs = await svc.list_messages(token, query="", max_results=1)
            if not msgs:
                return {
                    "type": "SINGLE_EMAIL",
                    "subject": "",
                    "from": "",
                    "date": "",
                    "body": "",
                    "attachments": [],
                }
            return self._to_single_email(msgs[0])

        if mode == "sender_email":
            msgs = await svc.list_messages(token, query=f"from:{target}", max_results=1)
            if not msgs:
                return {
                    "type": "SINGLE_EMAIL",
                    "subject": "",
                    "from": "",
                    "date": "",
                    "body": "",
                    "attachments": [],
                }
            return self._to_single_email(msgs[0])

        if mode == "starred_email":
            msgs = await svc.list_messages(token, query="is:starred", max_results=1)
            if not msgs:
                return {
                    "type": "SINGLE_EMAIL",
                    "subject": "",
                    "from": "",
                    "date": "",
                    "body": "",
                    "attachments": [],
                }
            return self._to_single_email(msgs[0])

        if mode == "label_emails":
            msgs = await svc.list_messages(
                token,
                query=f"label:{target}",
                max_results=max_results,
            )
            return {
                "type": "EMAIL_LIST",
                "items": [
                    {
                        "subject": msg.get("subject", ""),
                        "from": msg.get("from", ""),
                        "date": msg.get("date", ""),
                        "body": msg.get("body", ""),
                    }
                    for msg in msgs
                ],
            }

        if mode == "attachment_email":
            msgs = await svc.list_messages(token, query="has:attachment", max_results=1)
            items = []
            for msg in msgs:
                items.extend(self._to_file_items(msg.get("attachments", [])))
            return {
                "type": "FILE_LIST",
                "items": items,
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=gmail, mode={mode} is not supported",
        )

    @staticmethod
    def _resolve_max_results(config: dict[str, Any]) -> int:
        raw_value = config.get("maxResults")
        if raw_value in (None, ""):
            return 20

        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            logger.warning("Invalid maxResults value for Gmail source: %s", raw_value)
            return 20

        return max(1, value)

    @staticmethod
    def _to_single_email(msg: dict) -> dict[str, Any]:
        return {
            "type": "SINGLE_EMAIL",
            "subject": msg.get("subject", ""),
            "from": msg.get("from", ""),
            "date": msg.get("date", ""),
            "body": msg.get("body", ""),
            "attachments": InputNodeStrategy._to_file_items(msg.get("attachments", [])),
        }

    @staticmethod
    def _to_file_items(attachments: list[dict]) -> list[dict[str, Any]]:
        return [
            {
                "filename": attachment.get("filename", ""),
                "mime_type": attachment.get("mime_type", attachment.get("mimeType", "")),
                "size": attachment.get("size"),
                "url": attachment.get("url", ""),
            }
            for attachment in attachments
        ]

    # Google Sheets

    async def _fetch_google_sheets(
        self, token: str, mode: str, target: str, canonical_type: str
    ) -> dict[str, Any]:
        svc = GoogleSheetsService()

        if mode in ("sheet_all", "new_row", "row_updated"):
            # target = spreadsheet_id, default sheet name is "Sheet1"
            values = await svc.read_range(token, target, "Sheet1")
            headers = values[0] if values else []
            rows = values[1:] if len(values) > 1 else []
            return {
                "type": "SPREADSHEET_DATA",
                "headers": headers,
                "rows": rows,
                "sheet_name": "Sheet1",
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_sheets, mode={mode} is not supported",
        )

    # Slack

    async def _fetch_slack(self, token: str, mode: str, target: str) -> dict[str, Any]:
        if mode == "channel_messages":
            svc = SlackService()
            data = await svc._request(
                "GET",
                "https://slack.com/api/conversations.history",
                token,
                params={"channel": target, "limit": 20},
            )
            messages = data.get("messages", [])
            content = "\n".join(message.get("text", "") for message in messages)
            return {"type": "TEXT", "content": content}

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=slack, mode={mode} is not supported",
        )

    # Canvas LMS

    async def _fetch_canvas_lms(
        self, token: str, mode: str, target: str
    ) -> dict[str, Any]:
        svc = CanvasLmsService()

        if mode == "course_files":
            files = await svc.get_course_files(token, target)
            return {
                "type": "FILE_LIST",
                "items": [svc.to_file_item(file_item) for file_item in files],
            }

        if mode == "course_new_file":
            latest_file = await svc.get_course_latest_file(token, target)
            if not latest_file:
                return {
                    "type": "SINGLE_FILE",
                    "filename": "",
                    "content": None,
                    "mime_type": "",
                    "url": "",
                }
            return {
                "type": "SINGLE_FILE",
                "filename": latest_file.get("display_name", latest_file.get("filename", "")),
                "content": None,
                "mime_type": latest_file.get("content-type", "application/octet-stream"),
                "url": latest_file.get("url", ""),
            }

        if mode == "term_all_files":
            courses = await svc.get_courses(token, include_completed=True)
            matching = [
                course
                for course in courses
                if course.get("term", {}).get("name") == target and course.get("name")
            ]
            if not matching:
                raise FlowifyException(
                    ErrorCode.NODE_EXECUTION_FAILED,
                    detail=f"학기 '{target}'에 해당하는 과목이 없습니다.",
                )

            all_items: list[dict] = []
            for course in matching:
                try:
                    files = await svc.get_course_files(token, str(course["id"]))
                    all_items.extend(
                        svc.to_file_item(file_item, course_name=course["name"])
                        for file_item in files
                    )
                except Exception as e:
                    logger.warning(
                        "Canvas LMS 과목 '%s' 파일 조회 실패: %s",
                        course.get("name"),
                        e,
                    )
                    continue
            return {"type": "FILE_LIST", "items": all_items}

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=canvas_lms, mode={mode} is not supported",
        )
