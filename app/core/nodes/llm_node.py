"""AI 처리 노드의 LLM 실행 전략."""

import json
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy
from app.services.integrations.google_drive import GoogleDriveService
from app.services.llm_service import LLMService

PROMPT_REQUIRED_ACTIONS = frozenset({"process", "extract", "translate", "custom"})
PROMPT_OPTIONAL_ACTIONS = frozenset({"summarize", "classify"})
SUPPORTED_ACTIONS = PROMPT_REQUIRED_ACTIONS | PROMPT_OPTIONAL_ACTIONS


class LLMNodeStrategy(NodeStrategy):
    """설정된 LLM 작업을 실행하고 canonical payload를 반환합니다."""

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._llm_service = LLMService()

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        output_data_type = runtime_config.get("output_data_type", "TEXT")
        prompt = self._resolve_prompt(runtime_config)

        self._ensure_executable_prompt(node, action, output_data_type, prompt)

        text = await self._resolve_llm_input_text(input_data, service_tokens)

        if output_data_type == "SPREADSHEET_DATA":
            result = await self._llm_service.process_json(prompt, context=text)
            return self._to_spreadsheet_payload(result)

        if action == "summarize":
            result = await self._llm_service.summarize(text)
        elif action == "classify":
            categories = runtime_config.get("categories") or self.config.get("categories")
            result = await self._llm_service.classify(text, categories)
        else:  # process, extract, translate, custom
            result = await self._llm_service.process(prompt, context=text)

        return self._build_output_payload(output_data_type, result, input_data)

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        output_data_type = runtime_config.get("output_data_type", "TEXT")
        prompt = self._resolve_prompt(runtime_config)
        if output_data_type == "SPREADSHEET_DATA":
            return bool(prompt)
        if action in PROMPT_REQUIRED_ACTIONS:
            return bool(prompt)
        return action in PROMPT_OPTIONAL_ACTIONS

    def _resolve_prompt(self, runtime_config: dict[str, Any]) -> str:
        """runtime_config와 fallback config에서 프롬프트를 조회합니다."""
        prompt = runtime_config.get("prompt") or self.config.get("prompt", "")
        return str(prompt).strip()

    async def _resolve_llm_input_text(
        self,
        input_data: dict | None,
        service_tokens: dict[str, str],
    ) -> str:
        if not input_data:
            return ""

        if input_data.get("type") == "SINGLE_FILE":
            return await self._resolve_single_file_text(input_data, service_tokens)

        return self._extract_text_from_canonical(input_data)

    async def _resolve_single_file_text(
        self,
        input_data: dict[str, Any],
        service_tokens: dict[str, str],
    ) -> str:
        extracted_text = input_data.get("extracted_text")
        if extracted_text:
            return self._format_single_file_text(input_data, str(extracted_text))

        content = input_data.get("content")
        if content:
            return self._format_single_file_text(input_data, str(content))

        if input_data.get("source_service") == "google_drive" and input_data.get("file_id"):
            token = service_tokens.get("google_drive", "")
            if token:
                svc = GoogleDriveService()
                extraction = await svc.extract_file_text(
                    token,
                    input_data["file_id"],
                    input_data.get("mime_type", ""),
                )
                if extraction.get("text"):
                    return self._format_single_file_text(input_data, extraction["text"])
                return self._format_single_file_text(
                    input_data,
                    self._format_extraction_failure(extraction),
                )

        return self._format_single_file_metadata(input_data)

    def _ensure_executable_prompt(
        self,
        node: dict[str, Any],
        action: str,
        output_data_type: str,
        prompt: str,
    ) -> None:
        """LLM 호출 전 프롬프트 필수 조건을 검증합니다."""
        if action not in SUPPORTED_ACTIONS:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"지원하지 않는 AI 처리 방식입니다: {action}",
                context={"node_id": node.get("id"), "action": action},
            )

        requires_prompt = (
            output_data_type == "SPREADSHEET_DATA" or action in PROMPT_REQUIRED_ACTIONS
        )
        if requires_prompt and not prompt:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="AI 처리 프롬프트가 없어 노드를 실행할 수 없습니다.",
                context={"node_id": node.get("id"), "action": action},
            )

    @staticmethod
    def _extract_text_from_canonical(input_data: dict | None) -> str:
        """canonical payload에서 LLM 입력용 텍스트를 추출합니다."""
        if not input_data:
            return ""

        data_type = input_data.get("type", "")

        if data_type == "TEXT":
            return input_data.get("content", "")
        if data_type == "SINGLE_FILE":
            return LLMNodeStrategy._format_single_file_text(
                input_data,
                str(input_data.get("content") or ""),
            )
        if data_type == "SINGLE_EMAIL":
            return f"Subject: {input_data.get('subject', '')}\n\n{input_data.get('body', '')}"
        if data_type == "SPREADSHEET_DATA":
            headers = input_data.get("headers", [])
            rows = input_data.get("rows", [])
            lines = [", ".join(str(header) for header in headers)] if headers else []
            lines.extend(", ".join(str(cell) for cell in row) for row in rows)
            return "\n".join(lines)
        if data_type == "FILE_LIST":
            items = input_data.get("items", [])
            return "\n".join(LLMNodeStrategy._format_file_list_item(item) for item in items)
        if data_type == "EMAIL_LIST":
            items = input_data.get("items", [])
            formatted_items = []
            for index, item in enumerate(items, start=1):
                formatted_items.append(
                    "\n".join(
                        [
                            f"[Email {index}]",
                            f"From: {item.get('from', '')}",
                            f"Date: {item.get('date', '')}",
                            f"Subject: {item.get('subject', '')}",
                            "Body:",
                            item.get("body", ""),
                        ]
                    )
                )
            return "\n\n---\n\n".join(formatted_items)
        if data_type == "SCHEDULE_DATA":
            items = input_data.get("items", [])
            return "\n".join(
                f"{item.get('title', '')}: {item.get('start_time', '')} - {item.get('end_time', '')}"
                for item in items
            )
        if data_type == "API_RESPONSE":
            return json.dumps(input_data.get("data", {}), ensure_ascii=False, default=str)

        # Fallback: serialize the whole payload.
        return json.dumps(input_data, ensure_ascii=False, default=str)

    @staticmethod
    def _format_single_file_metadata(input_data: dict[str, Any]) -> str:
        parts = [
            f"Filename: {input_data.get('filename', '')}",
            f"MIME Type: {input_data.get('mime_type', '')}",
        ]
        if input_data.get("created_time"):
            parts.append(f"Created Time: {input_data.get('created_time', '')}")
        if input_data.get("url"):
            parts.append(f"Source URL: {input_data.get('url', '')}")
        return "\n".join(parts).strip()

    @staticmethod
    def _format_single_file_text(input_data: dict[str, Any], text: str) -> str:
        metadata = LLMNodeStrategy._format_single_file_metadata(input_data)
        if not text:
            return metadata
        return f"{metadata}\n\n{text}".strip()

    @staticmethod
    def _format_extraction_failure(extraction: dict[str, Any]) -> str:
        status = extraction.get("status", "failed")
        reason = extraction.get("error") or "unsupported"
        return "\n".join(
            [
                "File content could not be extracted.",
                f"Status: {status}",
                f"Reason: {reason}",
            ]
        )

    @staticmethod
    def _format_file_list_item(item: dict[str, Any]) -> str:
        parts = [f"- Filename: {item.get('filename', '')}"]
        if item.get("mime_type"):
            parts.append(f"  MIME Type: {item.get('mime_type', '')}")
        if item.get("size") is not None:
            parts.append(f"  Size: {item.get('size')}")
        if item.get("created_time"):
            parts.append(f"  Created Time: {item.get('created_time', '')}")
        if item.get("modified_time"):
            parts.append(f"  Modified Time: {item.get('modified_time', '')}")
        if item.get("url"):
            parts.append(f"  Source URL: {item.get('url', '')}")
        return "\n".join(parts)

    @staticmethod
    def _build_output_payload(
        output_data_type: str,
        result: str,
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": output_data_type, "content": result}
        if output_data_type != "TEXT" or not input_data:
            return payload

        passthrough_keys = (
            "file_id",
            "filename",
            "mime_type",
            "url",
            "created_time",
            "modified_time",
        )
        for key in passthrough_keys:
            value = input_data.get(key)
            if value not in (None, ""):
                payload[key] = value
        return payload

    @staticmethod
    def _to_spreadsheet_payload(result: dict[str, Any]) -> dict[str, Any]:
        headers = result.get("headers", [])
        rows = result.get("rows", [])

        normalized_headers = (
            [str(header) for header in headers] if isinstance(headers, list) else []
        )
        normalized_rows: list[list[str]] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, list):
                    normalized_rows.append([str(cell) for cell in row])

        return {
            "type": "SPREADSHEET_DATA",
            "headers": normalized_headers,
            "rows": normalized_rows,
        }
