"""LLM node strategy for AI processing nodes."""

import json
from typing import Any

from app.core.nodes.base import NodeStrategy
from app.services.llm_service import LLMService


class LLMNodeStrategy(NodeStrategy):
    """Run the configured LLM action and return canonical output payloads."""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._llm_service = LLMService()

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        # Prefer runtime_config values and fall back to static config.
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        output_data_type = runtime_config.get("output_data_type", "TEXT")

        text = self._extract_text_from_canonical(input_data)

        if output_data_type == "SPREADSHEET_DATA":
            prompt = runtime_config.get("prompt") or self.config.get("prompt", "")
            result = await self._llm_service.process_json(prompt, context=text)
            return self._to_spreadsheet_payload(result)

        if action == "summarize":
            result = await self._llm_service.summarize(text)
        elif action == "classify":
            categories = runtime_config.get("categories") or self.config.get("categories")
            result = await self._llm_service.classify(text, categories)
        else:  # process, extract, translate, custom
            prompt = runtime_config.get("prompt") or self.config.get("prompt", "")
            result = await self._llm_service.process(prompt, context=text)

        return self._build_output_payload(output_data_type, result, input_data)

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        if action == "process":
            return bool(runtime_config.get("prompt") or self.config.get("prompt"))
        return action in ("summarize", "classify", "extract", "translate", "custom")

    @staticmethod
    def _extract_text_from_canonical(input_data: dict | None) -> str:
        """Extract plain text from a canonical payload."""
        if not input_data:
            return ""

        data_type = input_data.get("type", "")

        if data_type == "TEXT":
            return input_data.get("content", "")
        if data_type == "SINGLE_FILE":
            parts = [
                f"Filename: {input_data.get('filename', '')}",
                f"MIME Type: {input_data.get('mime_type', '')}",
            ]
            if input_data.get("created_time"):
                parts.append(f"Created Time: {input_data.get('created_time', '')}")
            if input_data.get("url"):
                parts.append(f"Source URL: {input_data.get('url', '')}")
            parts.append("")
            parts.append(input_data.get("content", ""))
            return "\n".join(parts).strip()
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

        normalized_headers = [str(header) for header in headers] if isinstance(headers, list) else []
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
