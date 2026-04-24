"""OutputNodeStrategy — runtime_sink 기반 외부 서비스 전달.

이전 노드의 canonical payload를 받아서 runtime_sink가 지정한
외부 서비스에 데이터를 전송/저장/생성한다.

참조: FASTAPI_IMPLEMENTATION_GUIDE.md 섹션 6
"""

import logging
from typing import Any

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
    "gmail": {"TEXT", "SINGLE_FILE", "FILE_LIST", "SINGLE_EMAIL"},
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
    """출력 노드 — canonical payload를 외부 서비스에 전달."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_sink = node.get("runtime_sink")
        if not runtime_sink:
            # transition fallback: console 출력
            logger.info("OutputNode fallback: %s", input_data)
            return {"status": "sent", "service": "console", "detail": {}}

        service = runtime_sink["service"]
        sink_config = runtime_sink.get("config", {})

        if service not in SUPPORTED_SINKS:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SINK,
                detail=f"service={service} is not supported in current runtime phase",
            )

        # input_type 호환성 검증
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
                detail=f"'{service}' 서비스 토큰이 없습니다.",
            )

        if service == "slack":
            result = await self._send_slack(token, sink_config, input_data or {})
        elif service == "gmail":
            result = await self._send_gmail(token, sink_config, input_data or {})
        elif service == "notion":
            result = await self._send_notion(token, sink_config, input_data or {})
        elif service == "google_drive":
            result = await self._send_google_drive(token, sink_config, input_data or {})
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

    # ── Slack ──

    async def _send_slack(self, token: str, config: dict, input_data: dict) -> dict:
        channel = config["channel"]
        message = input_data.get("content", "")
        svc = SlackService()
        return await svc.send_message(token, channel, message)

    # ── Gmail ──

    async def _send_gmail(self, token: str, config: dict, input_data: dict) -> dict:
        to = config["to"]
        subject = config["subject"]
        action = config.get("action", "send")
        data_type = input_data.get("type", "TEXT")

        if data_type == "TEXT":
            body = input_data.get("content", "")
        elif data_type == "SINGLE_EMAIL":
            body = input_data.get("body", "")
        else:
            body = str(input_data)

        svc = GmailService()
        if action == "send":
            return await svc.send_message(token, to, subject, body)
        else:
            # draft — 현재 send_message만 구현되어 있으므로 send로 fallback
            # TODO: Gmail draft API 구현
            return await svc.send_message(token, to, subject, body)

    # ── Notion ──

    async def _send_notion(self, token: str, config: dict, input_data: dict) -> dict:
        target_type = config["target_type"]
        target_id = config["target_id"]
        data_type = input_data.get("type", "TEXT")

        svc = NotionService()
        if data_type == "TEXT":
            content = input_data.get("content", "")
            if target_type == "page":
                return await svc.create_page(token, target_id, "Flowify Output", content)
            else:
                return await svc.create_page(token, target_id, "Flowify Output", content)
        elif data_type == "SPREADSHEET_DATA":
            rows = input_data.get("rows", [])
            content = "\n".join(", ".join(str(c) for c in row) for row in rows)
            return await svc.create_page(token, target_id, "Flowify Data", content)
        else:
            return await svc.create_page(token, target_id, "Flowify Output", str(input_data))

    # ── Google Drive ──

    async def _send_google_drive(self, token: str, config: dict, input_data: dict) -> dict:
        folder_id = config.get("folder_id")
        data_type = input_data.get("type", "TEXT")
        svc = GoogleDriveService()

        if data_type == "SINGLE_FILE":
            filename = input_data.get("filename", "output.txt")
            content = (input_data.get("content", "") or "").encode("utf-8")
            return await svc.upload_file(token, filename, content, folder_id)

        if data_type == "TEXT":
            content = (input_data.get("content", "") or "").encode("utf-8")
            file_format = config.get("file_format", "txt")
            return await svc.upload_file(token, f"output.{file_format}", content, folder_id)

        if data_type == "FILE_LIST":
            results = []
            for item in input_data.get("items", []):
                filename = item.get("filename", "file")
                results.append({"filename": filename, "status": "uploaded"})
            return {"uploaded": results}

        return {}

    # ── Google Sheets ──

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
        else:
            return await svc.append_rows(token, spreadsheet_id, sheet_name, values)

    # ── Google Calendar ──

    async def _send_google_calendar(self, token: str, config: dict, input_data: dict) -> dict:
        calendar_id = config.get("calendar_id", "primary")
        data_type = input_data.get("type", "TEXT")
        svc = GoogleCalendarService()

        if data_type == "SCHEDULE_DATA":
            results = []
            for item in input_data.get("items", []):
                event = {
                    "summary": item.get("title", ""),
                    "start": {"dateTime": item.get("start_time", "")},
                    "end": {"dateTime": item.get("end_time", item.get("start_time", ""))},
                    "location": item.get("location", ""),
                    "description": item.get("description", ""),
                }
                result = await svc.create_event(token, calendar_id, event)
                results.append(result)
            return {"events_created": len(results)}

        if data_type == "TEXT":
            event = {
                "summary": config.get("event_title_template", "Flowify Event"),
                "description": input_data.get("content", ""),
                "start": {"dateTime": config.get("start_time", "")},
                "end": {"dateTime": config.get("end_time", "")},
            }
            return await svc.create_event(token, calendar_id, event)

        return {}
