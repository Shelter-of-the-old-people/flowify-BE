"""Workflow node preview executor.

This module returns user-facing preview payloads without creating execution
logs or calling output-node write operations.
"""

from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.document_content import (
    CONTENT_STATUS_AVAILABLE,
    apply_extraction_to_file_payload,
    ensure_file_content_fields,
)
from app.core.nodes.google_sheets_common import (
    build_sheet_range,
    coerce_int,
    extract_headers_and_rows,
)
from app.models.preview import NodePreviewResponse
from app.models.workflow import NodeDefinition
from app.services.integrations.canvas_lms import CanvasLmsService
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.naver_news import NaverNewsService
from app.services.integrations.web_news import WebNewsService

TOKENLESS_SOURCES = frozenset({"web_news", "naver_news"})


class WorkflowPreviewExecutor:
    """Build preview data for one workflow node without persisting execution state."""

    async def preview_node(
        self,
        *,
        workflow_id: str,
        node_id: str,
        nodes: list[NodeDefinition],
        service_tokens: dict[str, str],
        limit: int,
        include_content: bool,
        runtime_context: dict[str, Any] | None = None,
    ) -> NodePreviewResponse:
        """Return preview data for a target node."""
        node = self._find_node(nodes, node_id)

        if node.runtime_type == "input" or node.role == "start":
            preview_data = await self._preview_source_node(
                node,
                service_tokens,
                limit,
                include_content,
            )
            return NodePreviewResponse(
                workflow_id=workflow_id,
                node_id=node_id,
                status="available",
                available=True,
                output_data=preview_data,
                preview_data=preview_data,
                metadata={
                    "limit": limit,
                    "include_content": include_content,
                    "preview_scope": "source_metadata",
                    "content_policy": self._resolve_preview_content_policy(
                        preview_data,
                        include_content,
                    ),
                },
            )

        return NodePreviewResponse(
            workflow_id=workflow_id,
            node_id=node_id,
            status="unavailable",
            available=False,
            reason="PREVIEW_NOT_IMPLEMENTED",
            metadata={
                "preview_scope": "source_metadata",
                "content_policy": "metadata_only",
            },
        )

    async def _preview_source_node(
        self,
        node: NodeDefinition,
        service_tokens: dict[str, str],
        limit: int,
        include_content: bool,
    ) -> dict[str, Any]:
        runtime_source = node.runtime_source
        if runtime_source is None:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="시작 노드의 runtime_source 정보가 없습니다.",
            )

        service = runtime_source.service
        token = service_tokens.get(service, "")
        if not token and service not in TOKENLESS_SOURCES:
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{service}' 서비스의 토큰이 없습니다.",
            )

        if service == "google_drive":
            return await self._preview_google_drive(
                token,
                runtime_source.mode,
                runtime_source.target,
                limit,
                include_content,
            )
        if service == "gmail":
            return await self._preview_gmail(
                token,
                runtime_source.mode,
                runtime_source.target,
                limit,
                include_content,
            )
        if service == "google_sheets":
            return await self._preview_google_sheets(
                token,
                runtime_source.mode,
                runtime_source.target,
                runtime_source.config or node.config,
                limit,
            )
        if service == "canvas_lms":
            return await self._preview_canvas_lms(
                token,
                runtime_source.mode,
                runtime_source.target,
                limit,
            )
        if service == "naver_news":
            return await self._preview_naver_news(
                runtime_source.mode,
                runtime_source.target,
                limit,
            )
        if service == "web_news":
            return await self._preview_web_news(
                runtime_source.mode,
                runtime_source.target,
                node.config,
                limit,
                include_content,
            )

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service={service} source preview is not supported",
        )

    async def _preview_google_drive(
        self,
        token: str,
        mode: str,
        target: str,
        limit: int,
        include_content: bool,
    ) -> dict[str, Any]:
        svc = GoogleDriveService()

        if mode == "single_file":
            metadata = await svc.get_file_metadata(token, target)
            payload = self._to_drive_single_file(metadata, include_content=False)
            if include_content:
                await self._attach_drive_text_preview(svc, token, payload)
            return payload

        if mode in ("file_changed", "new_file", "folder_new_file"):
            files = await svc.list_files(
                token,
                folder_id=target,
                max_results=1,
                order_by="createdTime desc",
                include_folders=False,
            )
            if not files:
                return self._empty_single_file()

            latest_file = files[0]
            payload = self._to_drive_single_file(latest_file, include_content=False)
            if include_content:
                await self._attach_drive_text_preview(svc, token, payload)
            return payload

        if mode == "folder_all_files":
            files = await svc.list_files(
                token,
                folder_id=target,
                max_results=limit,
                include_folders=False,
            )
            return {
                "type": "FILE_LIST",
                "items": [self._to_drive_file_item(file_item) for file_item in files],
                "truncated": len(files) >= limit,
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_drive, mode={mode} preview is not supported",
        )

    async def _preview_google_sheets(
        self,
        token: str,
        mode: str,
        target: str,
        config: dict[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        svc = GoogleSheetsService()
        spreadsheet_id = str(config.get("spreadsheet_id") or target or "").strip()
        if not spreadsheet_id:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Google Sheets source preview requires spreadsheet_id.",
            )

        sheet_name = str(config.get("sheet_name") or "Sheet1").strip() or "Sheet1"
        range_a1 = build_sheet_range(config)
        header_row = coerce_int(config.get("header_row"), 1)
        data_start_row = coerce_int(config.get("data_start_row"), max(header_row + 1, 2))
        values = await svc.read_range(token, spreadsheet_id, range_a1)
        headers, rows = extract_headers_and_rows(values, header_row, data_start_row)

        if mode == "sheet_all":
            return self._to_google_sheets_preview(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                mode=mode,
                headers=headers,
                rows=rows,
                sampled_rows=rows[:limit],
                sample_strategy="head",
            )

        if mode == "new_row":
            return self._to_google_sheets_preview(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                mode=mode,
                headers=headers,
                rows=rows,
                sampled_rows=rows[-limit:],
                sample_strategy="tail",
            )

        if mode == "row_updated":
            key_column = str(config.get("key_column") or "").strip()
            if not key_column:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail="Google Sheets row_updated preview requires key_column.",
                )
            if key_column not in headers:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail=f"Google Sheets key_column '{key_column}' is not present in headers.",
                )
            return self._to_google_sheets_preview(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                mode=mode,
                headers=headers,
                rows=rows,
                sampled_rows=rows[-limit:],
                sample_strategy="tail",
                extra_metadata={"key_column": key_column},
            )

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_sheets, mode={mode} preview is not supported",
        )

    async def _preview_gmail(
        self,
        token: str,
        mode: str,
        target: str,
        limit: int,
        include_content: bool,
    ) -> dict[str, Any]:
        svc = GmailService()

        if mode == "single_email":
            msg = await svc.get_message(token, target)
            payload = self._to_single_email(msg, include_content)
            if include_content:
                await self._attach_gmail_attachment_text_preview(svc, token, payload["attachments"])
            return payload

        if mode == "new_email":
            msgs = await svc.list_messages(token, query="", max_results=1)
            if not msgs:
                return self._empty_email()
            payload = self._to_single_email(msgs[0], include_content)
            if include_content:
                await self._attach_gmail_attachment_text_preview(svc, token, payload["attachments"])
            return payload

        if mode == "sender_email":
            msgs = await svc.list_messages(token, query=f"from:{target}", max_results=1)
            if not msgs:
                return self._empty_email()
            payload = self._to_single_email(msgs[0], include_content)
            if include_content:
                await self._attach_gmail_attachment_text_preview(svc, token, payload["attachments"])
            return payload

        if mode == "starred_email":
            msgs = await svc.list_messages(token, query="is:starred", max_results=1)
            if not msgs:
                return self._empty_email()
            payload = self._to_single_email(msgs[0], include_content)
            if include_content:
                await self._attach_gmail_attachment_text_preview(svc, token, payload["attachments"])
            return payload

        if mode == "label_emails":
            msgs = await svc.list_messages(
                token,
                query=f"label:{target}",
                max_results=limit,
            )
            emails = [self._to_email_item(msg, include_content) for msg in msgs]
            return {
                "type": "EMAIL_LIST",
                "emails": emails,
                "items": emails,
                "metadata": {
                    "count": len(emails),
                    "truncated": len(emails) >= limit,
                    "sourceMode": mode,
                },
                "truncated": len(emails) >= limit,
            }

        if mode == "attachment_email":
            msgs = await svc.list_messages(token, query="has:attachment", max_results=1)
            files: list[dict[str, Any]] = []
            for msg in msgs:
                files.extend(self._to_file_items(msg.get("attachments", [])))
            if include_content:
                await self._attach_gmail_attachment_text_preview(svc, token, files)
            return {
                "type": "FILE_LIST",
                "files": files,
                "items": files,
                "metadata": {"count": len(files), "truncated": False},
                "truncated": False,
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=gmail, mode={mode} preview is not supported",
        )

    async def _preview_canvas_lms(
        self,
        token: str,
        mode: str,
        target: str,
        limit: int,
    ) -> dict[str, Any]:
        svc = CanvasLmsService()

        if mode == "course_files":
            files = await svc.get_course_files(token, target)
            preview_items = files[:limit]
            return {
                "type": "FILE_LIST",
                "items": [svc.to_file_item(file_item) for file_item in preview_items],
                "truncated": len(files) > len(preview_items),
            }

        if mode == "course_new_file":
            latest_file = await svc.get_course_latest_file(token, target)
            if not latest_file:
                return self._empty_single_file()
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
            items: list[dict[str, Any]] = []
            for course in matching:
                files = await svc.get_course_files(token, str(course["id"]))
                for file_item in files:
                    items.append(svc.to_file_item(file_item, course_name=course["name"]))
                    if len(items) >= limit:
                        return {"type": "FILE_LIST", "items": items, "truncated": True}
            return {"type": "FILE_LIST", "items": items, "truncated": False}

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=canvas_lms, mode={mode} preview is not supported",
        )

    async def _preview_web_news(
        self,
        mode: str,
        target: str,
        config: dict[str, Any],
        limit: int,
        include_content: bool,
    ) -> dict[str, Any]:
        svc = WebNewsService()
        fetch_mode = "seboard_posts" if mode == "seboard_new_posts" else mode
        return await svc.fetch_articles(
            fetch_mode,
            target,
            limit=limit,
            include_content=include_content,
            keyword=self._source_keyword(config),
        )

    async def _preview_naver_news(
        self,
        mode: str,
        target: str,
        limit: int,
    ) -> dict[str, Any]:
        if mode not in {"article_search", "new_articles"}:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service=naver_news, mode={mode} preview is not supported",
            )

        svc = NaverNewsService()
        return await svc.search_articles(target, limit=limit)

    @staticmethod
    def _source_keyword(config: dict[str, Any]) -> str | None:
        value = config.get("keyword")
        if not isinstance(value, str):
            return None

        keyword = value.strip()
        return keyword or None

    @staticmethod
    def _find_node(nodes: list[NodeDefinition], node_id: str) -> NodeDefinition:
        for node in nodes:
            if node.id == node_id:
                return node
        raise FlowifyException(ErrorCode.INVALID_REQUEST, detail=f"Node '{node_id}' was not found.")

    @staticmethod
    def _to_google_sheets_preview(
        *,
        spreadsheet_id: str,
        sheet_name: str,
        mode: str,
        headers: list[str],
        rows: list[list[Any]],
        sampled_rows: list[list[Any]],
        sample_strategy: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        truncated = len(rows) > len(sampled_rows)
        metadata = {
            "mode": mode,
            "sourceMode": mode,
            "row_count": len(sampled_rows),
            "total_rows": len(rows),
            "truncated": truncated,
            "sample_strategy": sample_strategy,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        return {
            "type": "SPREADSHEET_DATA",
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "headers": headers,
            "rows": sampled_rows,
            "metadata": metadata,
            "truncated": truncated,
        }

    @staticmethod
    def _to_drive_single_file(
        file_data: dict[str, Any],
        *,
        include_content: bool,
    ) -> dict[str, Any]:
        file_id = file_data.get("id", "")
        result = ensure_file_content_fields({
            "type": "SINGLE_FILE",
            "source_service": "google_drive",
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "extracted_text": file_data.get("extracted_text") if include_content else None,
            "extraction_status": file_data.get("extraction_status", "not_requested"),
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        })
        return result

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

    @staticmethod
    def _empty_single_file() -> dict[str, Any]:
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

    @staticmethod
    async def _attach_drive_text_preview(
        svc: GoogleDriveService,
        token: str,
        payload: dict[str, Any],
    ) -> None:
        extraction = await svc.extract_file_text(
            token,
            payload.get("file_id", ""),
            payload.get("mime_type", ""),
            payload.get("filename", ""),
            payload.get("size"),
        )
        apply_extraction_to_file_payload(payload, extraction)
        payload["truncated"] = extraction.get("truncated", False)

    @staticmethod
    async def _attach_gmail_attachment_text_preview(
        svc: GmailService,
        token: str,
        attachments: list[dict[str, Any]],
    ) -> None:
        for attachment in attachments:
            extraction = await svc.extract_attachment_text(
                token,
                message_id=attachment.get("message_id") or attachment.get("messageId", ""),
                attachment_id=attachment.get("attachment_id") or attachment.get("attachmentId", ""),
                mime_type=attachment.get("mime_type") or attachment.get("mimeType", ""),
                filename=attachment.get("filename", ""),
                file_size=attachment.get("size"),
                inline=bool(attachment.get("inline")),
            )
            apply_extraction_to_file_payload(attachment, extraction)
            attachment["truncated"] = extraction.get("truncated", False)

    @staticmethod
    def _resolve_preview_content_policy(preview_data: Any, include_content: bool) -> str:
        if not include_content:
            return "metadata_only"
        if WorkflowPreviewExecutor._has_included_content(preview_data):
            return "content_included"
        if WorkflowPreviewExecutor._has_content_status(preview_data):
            return "content_status_only"
        return "metadata_only"

    @staticmethod
    def _has_included_content(value: Any) -> bool:
        if isinstance(value, list):
            return any(WorkflowPreviewExecutor._has_included_content(item) for item in value)
        if not isinstance(value, dict):
            return False
        content_status = value.get("content_status")
        content = value.get("content")
        if content_status == CONTENT_STATUS_AVAILABLE:
            return True
        if isinstance(content, str) and bool(content.strip()):
            return True
        return any(
            WorkflowPreviewExecutor._has_included_content(item) for item in value.values()
        )

    @staticmethod
    def _has_content_status(value: Any) -> bool:
        if isinstance(value, list):
            return any(WorkflowPreviewExecutor._has_content_status(item) for item in value)
        if not isinstance(value, dict):
            return False
        if "content_status" in value:
            return True
        return any(WorkflowPreviewExecutor._has_content_status(item) for item in value.values())

    @staticmethod
    def _to_single_email(msg: dict[str, Any], include_content: bool) -> dict[str, Any]:
        email = WorkflowPreviewExecutor._to_email_detail(msg, include_content)
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
    def _to_email_item(msg: dict[str, Any], include_content: bool) -> dict[str, Any]:
        return WorkflowPreviewExecutor._to_email_detail(msg, include_content)

    @staticmethod
    def _to_email_detail(msg: dict[str, Any], include_content: bool) -> dict[str, Any]:
        from_value = msg.get("from", "")
        return {
            "id": msg.get("id", ""),
            "threadId": msg.get("threadId", ""),
            "subject": msg.get("subject", ""),
            "from": from_value,
            "sender": msg.get("sender", from_value),
            "to": WorkflowPreviewExecutor._normalize_email_recipients(msg.get("to", [])),
            "date": msg.get("date", ""),
            "body": msg.get("body", "") if include_content else "",
            "bodyPreview": msg.get("bodyPreview")
            or msg.get("snippet")
            or msg.get("body", "")[:200],
            "labels": msg.get("labels", msg.get("labelIds", [])),
            "attachments": WorkflowPreviewExecutor._to_file_items(msg.get("attachments", [])),
        }

    @staticmethod
    def _empty_email() -> dict[str, Any]:
        return WorkflowPreviewExecutor._to_single_email({}, include_content=False)

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

    @staticmethod
    def _normalize_email_recipients(raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            return [str(value) for value in raw_value if value]
        if raw_value:
            return [str(raw_value)]
        return []
