from app.config import settings


class LLMService:
    """LangChain + LLM 통합 서비스"""

    def __init__(self):
        self._model_name = settings.LLM_MODEL_NAME
        # TODO: LangChain LLM 초기화

    async def process(self, prompt: str, context: str | None = None) -> str:
        """프롬프트 처리"""
        # TODO: LangChain chain 실행
        return ""

    async def summarize(self, text: str) -> str:
        """문서 요약"""
        prompt = f"다음 내용을 요약해주세요:\n\n{text}"
        return await self.process(prompt)

    async def classify(self, text: str, categories: list[str] | None = None) -> str:
        """데이터 분류"""
        cats = ", ".join(categories) if categories else "자동 감지"
        prompt = f"다음 내용을 분류해주세요 (카테고리: {cats}):\n\n{text}"
        return await self.process(prompt)
