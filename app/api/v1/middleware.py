from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

EXCLUDED_PATHS = {"/api/v1/health", "/docs", "/redoc", "/openapi.json"}


class InternalAuthMiddleware(BaseHTTPMiddleware):
    """Spring Boot ↔ FastAPI 내부 인증 미들웨어.

    X-Internal-Token 헤더를 검증하고 X-User-ID를 request.state에 주입합니다.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        token = request.headers.get("X-Internal-Token")
        if not token or token != settings.INTERNAL_API_SECRET:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error_code": "UNAUTHORIZED",
                    "message": "유효하지 않은 내부 인증 토큰입니다.",
                    "detail": None,
                },
            )

        request.state.user_id = request.headers.get("X-User-ID", "")
        return await call_next(request)
