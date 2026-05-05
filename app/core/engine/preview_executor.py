"""Workflow node preview executor.

This module returns user-facing preview payloads without creating execution
logs or calling output-node write operations.
"""

from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.models.preview import NodePreviewResponse
from app.models.workflow import NodeDefinition
from app.services.integrations.canvas_lms import CanvasLmsService
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService


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
                },
            )

        return NodePreviewResponse(
            workflow_id=workflow_id,
            node_id=node_id,
            status="unavailable",
            available=False,
            reason="PREVIEW_NOT_IMPLEMENTED",
            metadata={"preview_scope": "source_metadata"},
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
        if not token and service not in ("web_crawl",):
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
        if service == "canvas_lms":
            return await self._preview_canvas_lms(
                token,
                runtime_source.mode,
                runtime_source.target,
                limit,
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
            if include_content:
                file_data = await svc.download_file(token, target)
                return self._to_drive_single_file(file_data, include_content=True)

            metadata = await svc.get_file_metadata(token, target)
            return self._to_drive_single_file(metadata, include_content=False)

        if mode in ("file_changed", "new_file", "folder_new_file"):
            files = await svc.list_files(
                token,
                folder_id=target,
                max_results=1,
                order_by="createdTime desc",
            )
            if not files:
                return self._empty_single_file()

            latest_file = files[0]
            if include_content:
                file_data = await svc.download_file(token, latest_file["id"])
                return self._to_drive_single_file(file_data, include_content=True)

            return self._to_drive_single_file(latest_file, include_content=False)

        if mode == "folder_all_files":
            files = await svc.list_files(token, folder_id=target, max_results=limit)
            return {
                "type": "FILE_LIST",
                "items": [self._to_drive_file_item(file_item) for file_item in files],
                "truncated": len(files) >= limit,
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_drive, mode={mode} preview is not supported",
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
            return self._to_single_email(msg, include_content)

        if mode == "new_email":
            msgs = await svc.list_messages(token, query="", max_results=1)
            return self._to_single_email(msgs[0], include_content) if msgs else self._empty_email()

        if mode == "sender_email":
            msgs = await svc.list_messages(token, query=f"from:{target}", max_results=1)
            return self._to_single_email(msgs[0], include_content) if msgs else self._empty_email()

        if mode == "starred_email":
            msgs = await svc.list_messages(token, query="is:starred", max_results=1)
            return self._to_single_email(msgs[0], include_content) if msgs else self._empty_email()

        if mode == "label_emails":
            msgs = await svc.list_messages(
                token,
                query=f"label:{target}",
                max_results=limit,
            )
            return {
                "type": "EMAIL_LIST",
                "items": [self._to_email_item(msg, include_content) for msg in msgs],
                "truncated": len(msgs) >= limit,
            }

        if mode == "attachment_email":
            msgs = await svc.list_messages(token, query="has:attachment", max_results=1)
            items: list[dict[str, Any]] = []
            for msg in msgs:
                items.extend(self._to_file_items(msg.get("attachments", [])))
            return {"type": "FILE_LIST", "items": items, "truncated": False}

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

    @staticmethod
    def _find_node(nodes: list[NodeDefinition], node_id: str) -> NodeDefinition:
        for node in nodes:
            if node.id == node_id:
                return node
        raise FlowifyException(ErrorCode.INVALID_REQUEST, detail=f"Node '{node_id}' was not found.")

    @staticmethod
    def _to_drive_single_file(
        file_data: dict[str, Any],
        *,
        include_content: bool,
    ) -> dict[str, Any]:
        file_id = file_data.get("id", "")
        result = {
            "type": "SINGLE_FILE",
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "content": file_data.get("content") if include_content else None,
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        }
        return result

    @staticmethod
    def _to_drive_file_item(file_data: dict[str, Any]) -> dict[str, Any]:
        file_id = file_data.get("id", "")
        return {
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        }

    @staticmethod
    def _empty_single_file() -> dict[str, Any]:
        return {
            "type": "SINGLE_FILE",
            "file_id": "",
            "filename": "",
            "content": None,
            "mime_type": "",
            "url": "",
            "created_time": "",
            "modified_time": "",
        }

    @staticmethod
    def _to_single_email(msg: dict[str, Any], include_content: bool) -> dict[str, Any]:
        return {
            "type": "SINGLE_EMAIL",
            "subject": msg.get("subject", ""),
            "from": msg.get("from", ""),
            "date": msg.get("date", ""),
            "body": msg.get("body", "") if include_content else "",
            "attachments": WorkflowPreviewExecutor._to_file_items(msg.get("attachments", [])),
        }

    @staticmethod
    def _to_email_item(msg: dict[str, Any], include_content: bool) -> dict[str, Any]:
        return {
            "subject": msg.get("subject", ""),
            "from": msg.get("from", ""),
            "date": msg.get("date", ""),
            "body": msg.get("body", "") if include_content else "",
        }

    @staticmethod
    def _empty_email() -> dict[str, Any]:
        return {
            "type": "SINGLE_EMAIL",
            "subject": "",
            "from": "",
            "date": "",
            "body": "",
            "attachments": [],
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
