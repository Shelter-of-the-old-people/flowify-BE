import json

from app.core.nodes.base import NodeStrategy
from app.services.llm_service import LLMService


class LLMNodeStrategy(NodeStrategy):
    """LLM 처리 노드 - config.action에 따라 LLMService 메소드를 라우팅."""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._llm_service = LLMService()

    async def execute(self, input_data: dict) -> dict:
        action = self.config.get("action", "process")

        if action == "summarize":
            text = self._extract_text(input_data)
            result = await self._llm_service.summarize(text)
        elif action == "classify":
            text = self._extract_text(input_data)
            categories = self.config.get("categories")
            result = await self._llm_service.classify(text, categories)
        else:  # "process" (기본)
            prompt = self.config.get("prompt", "")
            context = json.dumps(input_data, ensure_ascii=False, default=str)
            result = await self._llm_service.process(prompt, context=context)

        return {**input_data, "llm_result": result}

    def validate(self) -> bool:
        action = self.config.get("action", "process")
        if action == "process":
            return bool(self.config.get("prompt"))
        return action in ("summarize", "classify")

    @staticmethod
    def _extract_text(input_data: dict) -> str:
        """input_data에서 텍스트를 추출. llm_result > text > 전체 직렬화 순서."""
        if "llm_result" in input_data:
            return str(input_data["llm_result"])
        if "text" in input_data:
            return str(input_data["text"])
        return json.dumps(input_data, ensure_ascii=False, default=str)
