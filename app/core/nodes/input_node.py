"""Input node strategy for runtime source collection.

Reads ``runtime_source`` metadata from a workflow node, fetches data from the
matching external service, and returns a canonical payload that matches the
declared input type.
"""

import logging
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.document_content import ensure_file_content_fields
from app.core.nodes.base import NodeStrategy
from app.core.nodes.google_sheets_common import (
    build_sheet_range,
    coerce_int,
    extract_headers_and_rows,
    hash_record,
    row_to_record,
)
from app.services.integrations.canvas_lms import CanvasLmsService
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.naver_news import NaverNewsService
from app.services.integrations.slack import SlackService
from app.services.integrations.web_news import WebNewsService

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
    "naver_news": {"article_search", "new_articles"},
    "web_news": {"seboard_posts", "seboard_new_posts", "website_feed"},
}

TOKENLESS_SOURCES = frozenset({"web_crawl", "web_news", "naver_news"})


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
        runtime_source_config = runtime_source.get("config") or {}
        runtime_source_state = runtime_source.get("state") or {}
        config = node.get("config") or {}

        token = service_tokens.get(service, "")
        if not token and service not in TOKENLESS_SOURCES:
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
            return await self._fetch_google_sheets(
                token,
                mode,
                target,
                canonical_type,
                runtime_source_config or config,
                runtime_source_state,
            )
        if service == "slack":
            return await self._fetch_slack(token, mode, target)
        if service == "canvas_lms":
            return await self._fetch_canvas_lms(token, mode, target)
        if service == "naver_news":
            return await self._fetch_naver_news(mode, target, config)
        if service == "web_news":
            return await self._fetch_web_news(mode, target, config)

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
            metadata = await svc.get_file_metadata(token, target)
            return self._to_drive_single_file(metadata, target)

        if mode in ("file_changed", "new_file", "folder_new_file"):
            files = await svc.list_files(
                token,
                folder_id=target,
                max_results=1,
                order_by="createdTime desc",
                include_folders=False,
            )
            if not files:
                return ensure_file_content_fields({
                    "type": "SINGLE_FILE",
                    "source_service": "google_drive",
                    "file_id": "",
                    "filename": "",
                    "mime_type": "",
                    "size": None,
                    "url": "",
                    "created_time": "",
                    "modified_time": "",
                })

            latest_file = files[0]
            return self._to_drive_single_file(latest_file)

        if mode == "folder_all_files":
            files = await svc.list_files(token, folder_id=target, include_folders=False)
            return {
                "type": "FILE_LIST",
                "items": [self._to_drive_file_item(drive_file) for drive_file in files],
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_drive, mode={mode} is not supported",
        )

    @staticmethod
    def _to_drive_single_file(
        file_data: dict[str, Any], fallback_file_id: str = ""
    ) -> dict[str, Any]:
        file_id = file_data.get("id") or fallback_file_id
        return ensure_file_content_fields({
            "type": "SINGLE_FILE",
            "source_service": "google_drive",
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        })

    @staticmethod
    def _to_drive_file_item(file_data: dict[str, Any]) -> dict[str, Any]:
        file_id = file_data.get("id", "")
        return ensure_file_content_fields({
            "source_service": "google_drive",
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        })

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
                return self._empty_single_email()
            return self._to_single_email(msgs[0])

        if mode == "sender_email":
            msgs = await svc.list_messages(token, query=f"from:{target}", max_results=1)
            if not msgs:
                return self._empty_single_email()
            return self._to_single_email(msgs[0])

        if mode == "starred_email":
            msgs = await svc.list_messages(token, query="is:starred", max_results=1)
            if not msgs:
                return self._empty_single_email()
            return self._to_single_email(msgs[0])

        if mode == "label_emails":
            msgs = await svc.list_messages(
                token,
                query=f"label:{target}",
                max_results=max_results,
            )
            emails = [self._to_email_item(msg) for msg in msgs]
            return {
                "type": "EMAIL_LIST",
                "emails": emails,
                "items": emails,
                "metadata": {
                    "count": len(emails),
                    "truncated": len(emails) >= max_results,
                    "sourceMode": mode,
                },
            }

        if mode == "attachment_email":
            msgs = await svc.list_messages(token, query="has:attachment", max_results=1)
            files = []
            for msg in msgs:
                files.extend(self._to_file_items(msg.get("attachments", [])))
            return {
                "type": "FILE_LIST",
                "files": files,
                "items": files,
                "metadata": {
                    "count": len(files),
                    "truncated": False,
                },
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
        email = InputNodeStrategy._to_email_detail(msg, include_body=True)
        return {
            "type": "SINGLE_EMAIL",
            "email": email,
            "id": email["id"],
            "threadId": email["threadId"],
            "subject": email["subject"],
            "from": email["from"],
            "sender": email["sender"],
            "to": email["to"],
            "date": email["date"],
            "body": email["body"],
            "bodyPreview": email["bodyPreview"],
            "labels": email["labels"],
            "attachments": email["attachments"],
        }

    @staticmethod
    def _empty_single_email() -> dict[str, Any]:
        return InputNodeStrategy._to_single_email({})

    @staticmethod
    def _to_email_item(msg: dict[str, Any]) -> dict[str, Any]:
        return InputNodeStrategy._to_email_detail(msg, include_body=False)

    @staticmethod
    def _to_email_detail(msg: dict[str, Any], include_body: bool) -> dict[str, Any]:
        from_value = msg.get("from", "")
        body = msg.get("body", "") if include_body else ""
        return {
            "id": msg.get("id", ""),
            "threadId": msg.get("threadId", ""),
            "subject": msg.get("subject", ""),
            "from": from_value,
            "sender": msg.get("sender", from_value),
            "to": InputNodeStrategy._normalize_email_recipients(msg.get("to", [])),
            "date": msg.get("date", ""),
            "body": body,
            "bodyPreview": msg.get("bodyPreview")
            or msg.get("snippet")
            or msg.get("body", "")[:200],
            "labels": msg.get("labels", msg.get("labelIds", [])),
            "attachments": InputNodeStrategy._to_file_items(msg.get("attachments", [])),
        }

    @staticmethod
    def _normalize_email_recipients(raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            return [str(value) for value in raw_value if value]
        if raw_value:
            return [str(raw_value)]
        return []

    @staticmethod
    def _to_file_items(attachments: list[dict]) -> list[dict[str, Any]]:
        items = []
        for attachment in attachments:
            item = {
                "id": attachment.get("id", ""),
                "name": attachment.get("name", attachment.get("filename", "")),
                "filename": attachment.get("filename", ""),
                "mimeType": attachment.get("mimeType", attachment.get("mime_type", "")),
                "mime_type": attachment.get("mime_type", attachment.get("mimeType", "")),
                "size": attachment.get("size"),
                "source": attachment.get("source", "gmail"),
                "source_service": attachment.get("source_service", attachment.get("source", "gmail")),
                "messageId": attachment.get("messageId", ""),
                "message_id": attachment.get("message_id", attachment.get("messageId", "")),
                "attachmentId": attachment.get("attachmentId", ""),
                "attachment_id": attachment.get("attachment_id", attachment.get("attachmentId", "")),
                "inline": attachment.get("inline", False),
                "content": attachment.get("content"),
                "downloadUrl": attachment.get("downloadUrl"),
                "url": attachment.get("url", ""),
            }
            items.append(ensure_file_content_fields(item))
        return items

    # Google Sheets

    async def _fetch_google_sheets(
        self,
        token: str,
        mode: str,
        target: str,
        canonical_type: str,
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        svc = GoogleSheetsService()
        spreadsheet_id = str(config.get("spreadsheet_id") or target or "").strip()
        if not spreadsheet_id:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Google Sheets source requires spreadsheet_id.",
            )

        sheet_name = str(config.get("sheet_name") or "Sheet1").strip() or "Sheet1"
        range_a1 = build_sheet_range(config)
        header_row = coerce_int(config.get("header_row"), 1)
        data_start_row = coerce_int(config.get("data_start_row"), max(header_row + 1, 2))

        values = await svc.read_range(token, spreadsheet_id, range_a1)
        headers, rows = extract_headers_and_rows(values, header_row, data_start_row)

        if mode == "sheet_all":
            return self._build_google_sheets_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                mode=mode,
                headers=headers,
                rows=rows,
                metadata={"row_count": len(rows)},
            )

        if mode == "new_row":
            return self._build_google_sheets_new_row_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                rows=rows,
                config=config,
                state=state,
            )

        if mode == "row_updated":
            return self._build_google_sheets_row_updated_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                rows=rows,
                config=config,
                state=state,
            )

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_sheets, mode={mode} is not supported",
        )

    def _build_google_sheets_payload(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        mode: str,
        headers: list[str],
        rows: list[list[Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "SPREADSHEET_DATA",
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "headers": headers,
            "rows": rows,
            "metadata": {"mode": mode, **(metadata or {})},
        }

    def _build_google_sheets_new_row_payload(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
        rows: list[list[Any]],
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        initial_sync_mode = str(config.get("initial_sync_mode") or "skip_existing").strip()
        prior_last_seen = state.get("last_seen_row_index")
        current_last_seen = len(rows)

        if prior_last_seen in (None, ""):
            emitted_rows = rows if initial_sync_mode == "emit_existing" else []
        else:
            try:
                emitted_rows = rows[int(prior_last_seen) :]
            except (TypeError, ValueError):
                emitted_rows = rows

        payload = self._build_google_sheets_payload(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            mode="new_row",
            headers=headers,
            rows=emitted_rows,
            metadata={
                "row_count": len(emitted_rows),
                "total_rows": len(rows),
                "initial_sync_mode": initial_sync_mode,
            },
        )
        payload["node_state_update"] = {
            "service": "google_sheets",
            "state": {"last_seen_row_index": current_last_seen},
        }
        return payload

    def _build_google_sheets_row_updated_payload(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
        rows: list[list[Any]],
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        key_column = str(config.get("key_column") or "").strip()
        if not key_column:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Google Sheets row_updated requires key_column.",
            )
        if key_column not in headers:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"Google Sheets key_column '{key_column}' is not present in headers.",
            )

        initial_sync_mode = str(config.get("initial_sync_mode") or "skip_existing").strip()
        previous_snapshot = state.get("row_snapshot") if isinstance(state, dict) else {}
        previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}

        current_snapshot: dict[str, str] = {}
        changed_rows: list[list[Any]] = []
        changed_keys: list[str] = []

        for row in rows:
            record = row_to_record(headers, row)
            row_key = record.get(key_column, "")
            if not row_key:
                continue

            row_hash = hash_record(record)
            current_snapshot[row_key] = row_hash

            if not previous_snapshot:
                if initial_sync_mode == "emit_existing":
                    changed_rows.append(row)
                    changed_keys.append(row_key)
                continue

            if previous_snapshot.get(row_key) != row_hash:
                changed_rows.append(row)
                changed_keys.append(row_key)

        payload = self._build_google_sheets_payload(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            mode="row_updated",
            headers=headers,
            rows=changed_rows,
            metadata={
                "row_count": len(changed_rows),
                "changed_keys": changed_keys,
                "initial_sync_mode": initial_sync_mode,
            },
        )
        payload["node_state_update"] = {
            "service": "google_sheets",
            "state": {
                "last_seen_row_index": len(rows),
                "row_snapshot": current_snapshot,
            },
        }
        return payload

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

    async def _fetch_canvas_lms(self, token: str, mode: str, target: str) -> dict[str, Any]:
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

    # Web news

    async def _fetch_naver_news(
        self,
        mode: str,
        target: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if mode not in {"article_search", "new_articles"}:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service=naver_news, mode={mode} is not supported",
            )

        svc = NaverNewsService()
        return await svc.search_articles(
            target,
            limit=self._resolve_article_limit(config),
        )

    async def _fetch_web_news(
        self,
        mode: str,
        target: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        svc = WebNewsService()
        fetch_mode = "seboard_posts" if mode == "seboard_new_posts" else mode
        return await svc.fetch_articles(
            fetch_mode,
            target,
            limit=self._resolve_article_limit(config),
            include_content=bool(config.get("includeContent") or config.get("include_content")),
        )

    @staticmethod
    def _resolve_article_limit(config: dict[str, Any]) -> int:
        raw_value = config.get("maxResults", config.get("limit"))
        if raw_value in (None, ""):
            return 10

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            logger.warning("Invalid article limit value for web_news source: %s", raw_value)
            return 10
