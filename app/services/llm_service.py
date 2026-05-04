import asyncio
import logging

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """LangChain LCEL 기반 LLM 통합 서비스."""

    def __init__(self):
        self._model_name = settings.LLM_MODEL_NAME
        self._llm = ChatOpenAI(
            model=self._model_name,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE_URL or None,
            temperature=0.7,
            max_tokens=2048,
        )

    async def process(self, prompt: str, context: str | None = None) -> str:
        """범용 프롬프트 처리."""
        if context:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", "주어진 컨텍스트를 참고하여 사용자의 요청을 처리하세요."),
                    ("human", "컨텍스트:\n{context}\n\n요청:\n{prompt}"),
                ]
            )
            chain = template | self._llm | StrOutputParser()
            return await self._invoke_with_retry(chain, {"prompt": prompt, "context": context})
        else:
            template = ChatPromptTemplate.from_messages(
                [
                    ("human", "{prompt}"),
                ]
            )
            chain = template | self._llm | StrOutputParser()
            return await self._invoke_with_retry(chain, {"prompt": prompt})

    async def process_json(self, prompt: str, context: str | None = None) -> dict:
        """JSON 구조 출력을 기대하는 범용 프롬프트 처리."""
        if context:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", "주어진 컨텍스트를 참고하여 사용자의 요청을 처리하세요. 반드시 JSON만 반환하세요."),
                    ("human", "컨텍스트:\n{context}\n\n요청:\n{prompt}"),
                ]
            )
            variables = {"prompt": prompt, "context": context}
        else:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", "사용자의 요청을 처리하세요. 반드시 JSON만 반환하세요."),
                    ("human", "{prompt}"),
                ]
            )
            variables = {"prompt": prompt}

        chain = template | self._llm | JsonOutputParser()
        return await self._invoke_with_retry(chain, variables)

    async def summarize(self, text: str) -> str:
        """텍스트 요약."""
        template = ChatPromptTemplate.from_messages(
            [
                ("system", "당신은 문서 요약 전문가입니다. 핵심 내용을 3줄 이내로 요약해주세요."),
                ("human", "다음 내용을 요약해주세요:\n\n{text}"),
            ]
        )
        chain = template | self._llm | StrOutputParser()
        return await self._invoke_with_retry(chain, {"text": text})

    async def classify(self, text: str, categories: list[str] | None = None) -> str:
        """텍스트 분류."""
        cats = ", ".join(categories) if categories else "자동 감지"
        template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "당신은 텍스트 분류 전문가입니다. 주어진 카테고리 중 가장 적합한 것을 선택해주세요.",
                ),
                ("human", "다음 내용을 [{categories}] 중 하나로 분류해주세요:\n\n{text}"),
            ]
        )
        chain = template | self._llm | StrOutputParser()
        return await self._invoke_with_retry(chain, {"text": text, "categories": cats})

    async def generate_workflow(self, prompt: str, context: str | None = None) -> dict:
        """LLM 기반 워크플로우 자동 생성. JsonOutputParser 사용.

        반환 구조는 Spring Boot WorkflowCreateRequest 호환 형식입니다:
            { "name", "description", "nodes", "edges", "trigger" }
        """
        system_prompt = (
            "당신은 워크플로우 설계 전문가입니다. "
            "사용자의 요구사항을 분석하여 자동화 워크플로우를 설계하세요.\n\n"
            "반드시 다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이 JSON만):\n"
            "{{\n"
            '  "name": "워크플로우 이름 (필수, 비워두면 안 됨)",\n'
            '  "description": "워크플로우 설명",\n'
            '  "nodes": [\n'
            "    {{\n"
            '      "id": "node_abc12345",\n'
            '      "category": "trigger | service | logic | output",\n'
            '      "type": "gmail | slack | condition | http_request 등",\n'
            '      "label": "노드 표시 이름",\n'
            '      "config": {{}},\n'
            '      "position": {{ "x": 0, "y": 0 }},\n'
            '      "dataType": null,\n'
            '      "outputDataType": null,\n'
            '      "role": "start | end | null",\n'
            '      "authWarning": false\n'
            "    }}\n"
            "  ],\n"
            '  "edges": [\n'
            '    {{ "id": "edge_abc12345", "source": "node_abc12345", "target": "node_def67890" }}\n'
            "  ],\n"
            '  "trigger": {{\n'
            '    "type": "manual | schedule | webhook",\n'
            '    "config": {{}}\n'
            "  }}\n"
            "}}"
        )

        if context:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "컨텍스트:\n{context}\n\n요구사항:\n{prompt}"),
                ]
            )
            variables = {"prompt": prompt, "context": context}
        else:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "요구사항:\n{prompt}"),
                ]
            )
            variables = {"prompt": prompt}

        chain = template | self._llm | JsonOutputParser()

        try:
            return await self._invoke_with_retry(chain, variables)
        except FlowifyException:
            raise
        except Exception as e:
            raise FlowifyException(
                ErrorCode.LLM_GENERATION_FAILED,
                detail=f"워크플로우 JSON 생성/파싱에 실패했습니다: {e}",
            ) from e

    async def _invoke_with_retry(self, chain, variables: dict):
        """재시도 로직: Rate Limit 1회, Server Error 2회 지수 백오프."""
        last_error = None

        for attempt in range(3):  # 최대 3회 시도 (초기 1 + 재시도 2)
            try:
                return await chain.ainvoke(variables)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Rate Limit (429) - 1회만 재시도
                if "rate" in error_str and "limit" in error_str:
                    if attempt >= 1:
                        break
                    retry_after = self._extract_retry_after(e)
                    logger.warning("LLM rate limit hit, retrying after %ss", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                # Server Error (5xx) - 최대 2회 재시도, 지수 백오프
                if (
                    "server" in error_str
                    or "500" in error_str
                    or "502" in error_str
                    or "503" in error_str
                ):
                    if attempt >= 2:
                        break
                    wait = 2**attempt  # 1s, 2s
                    logger.warning(
                        "LLM server error (attempt %d), retrying in %ss: %s", attempt + 1, wait, e
                    )
                    await asyncio.sleep(wait)
                    continue

                # 그 외 에러는 즉시 실패
                break

        raise FlowifyException(
            ErrorCode.LLM_API_ERROR,
            detail=f"LLM API 호출 실패: {last_error}",
            context={"model": self._model_name, "attempts": attempt + 1},
        )

    @staticmethod
    def _extract_retry_after(error: Exception) -> float:
        """Rate limit 응답에서 Retry-After 값을 추출. 없으면 기본 1초."""
        error_str = str(error)
        try:
            if "retry" in error_str.lower() and "after" in error_str.lower():
                # 'Retry-After: N' 패턴에서 숫자 추출 시도
                import re

                match = re.search(r"retry[- ]?after[:\s]*(\d+\.?\d*)", error_str, re.IGNORECASE)
                if match:
                    return float(match.group(1))
        except (ValueError, AttributeError):
            pass
        return 1.0
