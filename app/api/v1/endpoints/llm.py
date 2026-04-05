from fastapi import APIRouter

from app.models.requests import (
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    LLMProcessRequest,
    LLMProcessResponse,
)
from app.services.llm_service import LLMService

router = APIRouter()


def _get_llm_service() -> LLMService:
    return LLMService()


@router.post("/process", response_model=LLMProcessResponse)
async def process_llm(request: LLMProcessRequest):
    """단일 LLM 프롬프트 처리 (UC-A01)."""
    service = _get_llm_service()
    result = await service.process(request.prompt, context=request.context)
    return LLMProcessResponse(result=result, tokens_used=0)


@router.post("/summarize", response_model=LLMProcessResponse)
async def summarize(request: LLMProcessRequest):
    """문서 요약."""
    service = _get_llm_service()
    result = await service.summarize(request.prompt)
    return LLMProcessResponse(result=result, tokens_used=0)


@router.post("/classify", response_model=LLMProcessResponse)
async def classify(request: LLMProcessRequest):
    """데이터 분류."""
    service = _get_llm_service()
    result = await service.classify(request.prompt)
    return LLMProcessResponse(result=result, tokens_used=0)


@router.post("/generate-workflow", response_model=GenerateWorkflowResponse)
async def generate_workflow(request: GenerateWorkflowRequest):
    """LLM 기반 워크플로우 자동 생성 (UC-W02)."""
    service = _get_llm_service()
    result = await service.generate_workflow(request.prompt, context=request.context)
    return GenerateWorkflowResponse(result=result)
