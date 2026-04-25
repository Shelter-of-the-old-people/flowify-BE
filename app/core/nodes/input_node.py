"""InputNodeStrategy — runtime_source 기반 외부 데이터 수집.

runtime_source의 service/mode/target 정보를 바탕으로 외부 서비스에서
데이터를 수집하고, canonical_input_type에 맞는 canonical payload로 반환한다.

참조: FASTAPI_IMPLEMENTATION_GUIDE.md 섹션 5
"""

from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.slack import SlackService

# Phase 1 지원 source 맵
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
}


class InputNodeStrategy(NodeStrategy):
    """입력 노드 — 외부 서비스에서 데이터를 수집하여 canonical payload를 반환."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_source = node.get("runtime_source")
        if not runtime_source:
            # transition fallback: config 기반
            return {"type": "TEXT", "content": self.config.get("data", "")}

        service = runtime_source["service"]
        mode = runtime_source["mode"]
        target = runtime_source.get("target", "")
        canonical_type = runtime_source.get("canonical_input_type", "TEXT")

        token = service_tokens.get(service, "")
        if not token and service not in ("web_crawl",):
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{service}' 서비스 토큰이 없습니다.",
            )

        if service == "google_drive":
            return await self._fetch_google_drive(token, mode, target, canonical_type)
        elif service == "gmail":
            return await self._fetch_gmail(token, mode, target, canonical_type)
        elif service == "google_sheets":
            return await self._fetch_google_sheets(token, mode, target, canonical_type)
        elif service == "slack":
            return await self._fetch_slack(token, mode, target)
        else:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service={service}, mode={mode} is not supported in current runtime phase",
            )

    def validate(self, node: dict[str, Any]) -> bool:
        rs = node.get("runtime_source")
        if not rs:
            return False
        service = rs.get("service", "")
        mode = rs.get("mode", "")
        supported_modes = SUPPORTED_SOURCES.get(service)
        if supported_modes is None:
            return False
        return mode in supported_modes

    # ── Google Drive ──

    async def _fetch_google_drive(
        self, token: str, mode: str, target: str, canonical_type: str
    ) -> dict[str, Any]:
        svc = GoogleDriveService()

        if mode == "single_file":
            file_data = await svc.download_file(token, target)
            return {
                "type": "SINGLE_FILE",
                "filename": file_data.get("name", ""),
                "content": file_data.get("content", ""),
                "mime_type": file_data.get("mimeType", ""),
                "url": f"https://drive.google.com/file/d/{target}",
            }

        if mode in ("file_changed", "new_file", "folder_new_file"):
            files = await svc.list_files(token, folder_id=target, max_results=1)
            if not files:
                return {"type": "SINGLE_FILE", "filename": "", "content": ""}
            f = files[0]
            file_data = await svc.download_file(token, f["id"])
            return {
                "type": "SINGLE_FILE",
                "filename": f.get("name", ""),
                "content": file_data.get("content", ""),
                "mime_type": f.get("mimeType", ""),
                "url": f"https://drive.google.com/file/d/{f['id']}",
            }

        if mode == "folder_all_files":
            files = await svc.list_files(token, folder_id=target)
            return {
                "type": "FILE_LIST",
                "items": [
                    {
                        "filename": f.get("name", ""),
                        "mime_type": f.get("mimeType", ""),
                        "size": f.get("size"),
                        "url": f"https://drive.google.com/file/d/{f['id']}",
                    }
                    for f in files
                ],
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_drive, mode={mode} is not supported",
        )

    # ── Gmail ──

    async def _fetch_gmail(
        self, token: str, mode: str, target: str, canonical_type: str
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
            msgs = await svc.list_messages(token, query=f"label:{target}", max_results=20)
            return {
                "type": "EMAIL_LIST",
                "items": [
                    {
                        "subject": m.get("subject", ""),
                        "from": m.get("from", ""),
                        "date": m.get("date", ""),
                        "body": m.get("body", ""),
                    }
                    for m in msgs
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

    # ── Google Sheets ──

    async def _fetch_google_sheets(
        self, token: str, mode: str, target: str, canonical_type: str
    ) -> dict[str, Any]:
        svc = GoogleSheetsService()

        if mode in ("sheet_all", "new_row", "row_updated"):
            # target = spreadsheet_id, 기본 시트 "Sheet1"
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

    # ── Slack ──

    async def _fetch_slack(self, token: str, mode: str, target: str) -> dict[str, Any]:
        if mode == "channel_messages":
            svc = SlackService()
            # conversations.history API 호출
            data = await svc._request(
                "GET",
                "https://slack.com/api/conversations.history",
                token,
                params={"channel": target, "limit": 20},
            )
            messages = data.get("messages", [])
            content = "\n".join(m.get("text", "") for m in messages)
            return {"type": "TEXT", "content": content}

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=slack, mode={mode} is not supported",
        )
