"""LLMNodeStrategy — AI 처리 노드.

canonical payload를 입력받아 LLM으로 처리하고,
output_data_type에 맞는 canonical payload를 반환한다.

참조: FASTAPI_IMPLEMENTATION_GUIDE.md 섹션 7.1
"""

import json
from typing import Any

from app.core.nodes.base import NodeStrategy
from app.services.llm_service import LLMService


class LLMNodeStrategy(NodeStrategy):
    """LLM 처리 노드 — runtime_config의 action에 따라 LLMService 메소드를 라우팅."""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._llm_service = LLMService()

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        # v2: runtime_config에서 설정 읽기 (fallback: self.config)
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        output_data_type = runtime_config.get("output_data_type", "TEXT")

        text = self._extract_text_from_canonical(input_data)

        if action == "summarize":
            result = await self._llm_service.summarize(text)
        elif action == "classify":
            categories = runtime_config.get("categories") or self.config.get("categories")
            result = await self._llm_service.classify(text, categories)
        else:  # "process" (기본), "extract", "translate", "custom"
            prompt = runtime_config.get("prompt") or self.config.get("prompt", "")
            context = text
            result = await self._llm_service.process(prompt, context=context)

        # canonical payload로 반환
        return {"type": output_data_type, "content": result}

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        if action == "process":
            return bool(runtime_config.get("prompt") or self.config.get("prompt"))
        return action in ("summarize", "classify", "extract", "translate", "custom")

    @staticmethod
    def _extract_text_from_canonical(input_data: dict | None) -> str:
        """canonical payload에서 텍스트를 추출."""
        if not input_data:
            return ""

        data_type = input_data.get("type", "")

        if data_type == "TEXT":
            return input_data.get("content", "")
        if data_type == "SINGLE_FILE":
            return input_data.get("content", "")
        if data_type == "SINGLE_EMAIL":
            return f"Subject: {input_data.get('subject', '')}\n\n{input_data.get('body', '')}"
        if data_type == "SPREADSHEET_DATA":
            headers = input_data.get("headers", [])
            rows = input_data.get("rows", [])
            lines = [", ".join(str(h) for h in headers)] if headers else []
            lines.extend(", ".join(str(c) for c in row) for row in rows)
            return "\n".join(lines)
        if data_type == "FILE_LIST":
            items = input_data.get("items", [])
            return "\n".join(f"- {i.get('filename', '')}" for i in items)
        if data_type == "EMAIL_LIST":
            items = input_data.get("items", [])
            return "\n---\n".join(
                f"Subject: {i.get('subject', '')}\n{i.get('body', '')}" for i in items
            )
        if data_type == "SCHEDULE_DATA":
            items = input_data.get("items", [])
            return "\n".join(
                f"{i.get('title', '')}: {i.get('start_time', '')} - {i.get('end_time', '')}"
                for i in items
            )
        if data_type == "API_RESPONSE":
            return json.dumps(input_data.get("data", {}), ensure_ascii=False, default=str)

        # fallback: 전체 직렬화
        return json.dumps(input_data, ensure_ascii=False, default=str)
