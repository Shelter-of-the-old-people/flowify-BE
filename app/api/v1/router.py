from fastapi import APIRouter

from app.api.v1.endpoints import execution, health, llm, trigger, workflow

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(workflow.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(execution.router, prefix="/executions", tags=["executions"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])
api_router.include_router(trigger.router, prefix="/triggers", tags=["triggers"])
