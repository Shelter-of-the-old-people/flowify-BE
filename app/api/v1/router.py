from fastapi import APIRouter

from app.api.v1.endpoints import health, llm, workflow

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(workflow.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])
