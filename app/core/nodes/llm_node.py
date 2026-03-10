from app.core.nodes.base import NodeStrategy


class LLMNodeStrategy(NodeStrategy):
    """LLM 처리 노드 - 자연어 프롬프트 기반 AI 처리"""

    async def execute(self, input_data: dict) -> dict:
        prompt = self.config.get("prompt", "")
        # TODO: LangChain + LLM 서비스 연동
        return {**input_data, "llm_result": "", "prompt_used": prompt}

    def validate(self) -> bool:
        return bool(self.config.get("prompt"))
