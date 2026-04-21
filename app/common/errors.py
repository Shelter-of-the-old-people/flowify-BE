import traceback
from enum import Enum

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings


class ErrorCode(Enum):
    """Flowify 에러 코드 체계. (http_status, message) 튜플."""

    INTERNAL_ERROR = (500, "내부 서버 오류가 발생했습니다")
    INVALID_REQUEST = (400, "잘못된 요청입니다")
    UNAUTHORIZED = (401, "인증되지 않은 요청입니다")
    WORKFLOW_NOT_FOUND = (404, "워크플로우를 찾을 수 없습니다")
    EXECUTION_NOT_FOUND = (404, "실행 이력을 찾을 수 없습니다")
    INVALID_STATE_TRANSITION = (400, "잘못된 상태 전환입니다")
    NODE_EXECUTION_FAILED = (500, "노드 실행에 실패했습니다")
    LLM_API_ERROR = (502, "LLM API 호출에 실패했습니다")
    LLM_GENERATION_FAILED = (422, "워크플로우 자동 생성에 실패했습니다")
    EXTERNAL_API_ERROR = (502, "외부 서비스 연결에 실패했습니다")
    OAUTH_TOKEN_INVALID = (400, "서비스 인증 토큰이 유효하지 않습니다")
    CRAWL_FAILED = (502, "웹 수집에 실패했습니다")
    DATA_CONVERSION_FAILED = (422, "데이터 변환에 실패했습니다")
    ROLLBACK_UNAVAILABLE = (400, "롤백할 수 없는 상태입니다")
    UNSUPPORTED_RUNTIME_SOURCE = (400, "미지원 런타임 소스입니다")
    UNSUPPORTED_RUNTIME_SINK = (400, "미지원 런타임 싱크입니다")
    TOKEN_EXPIRED = (401, "OAuth 토큰이 만료되었습니다")
    EXTERNAL_SERVICE_ERROR = (502, "외부 서비스 호출에 실패했습니다")

    @property
    def http_status(self) -> int:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class FlowifyException(Exception):
    """Flowify 비즈니스 예외 기본 클래스."""

    def __init__(
        self,
        error_code: ErrorCode,
        detail: str | None = None,
        context: dict | None = None,
    ):
        self.error_code = error_code
        self.detail = detail or error_code.message
        self.context = context or {}
        super().__init__(self.detail)


class ApiErrorResponse(BaseModel):
    """에러 응답 스키마 (OpenAPI 문서용)."""

    success: bool = False
    error_code: str
    message: str
    detail: dict | None = None


async def flowify_exception_handler(request: Request, exc: FlowifyException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.error_code.http_status,
        content={
            "success": False,
            "error_code": exc.error_code.name,
            "message": exc.detail,
            "detail": exc.context,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = {"stack_trace": traceback.format_exc()} if settings.APP_DEBUG else None
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "message": "내부 서버 오류가 발생했습니다.",
            "detail": detail,
        },
    )
