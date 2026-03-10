from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class LLMRequest(BaseModel):
    prompt: str
    context: str | None = None
    max_tokens: int = 1024


class LLMResponse(BaseModel):
    result: str
    tokens_used: int = 0


@router.post("/process", response_model=LLMResponse)
async def process_llm(request: LLMRequest):
    """LLM 프롬프트 처리"""
    return LLMResponse(result="", tokens_used=0)


@router.post("/summarize", response_model=LLMResponse)
async def summarize(request: LLMRequest):
    """문서 요약"""
    return LLMResponse(result="", tokens_used=0)


@router.post("/classify", response_model=LLMResponse)
async def classify(request: LLMRequest):
    """데이터 분류"""
    return LLMResponse(result="", tokens_used=0)
