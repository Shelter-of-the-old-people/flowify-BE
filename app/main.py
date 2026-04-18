from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.middleware import InternalAuthMiddleware
from app.api.v1.router import api_router
from app.common.errors import FlowifyException, flowify_exception_handler, generic_exception_handler
from app.config import settings
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.services.scheduler_service import SchedulerService


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    scheduler = SchedulerService()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()
    await close_mongo_connection()


app = FastAPI(
    title="Flowify API",
    description="AI 워크플로우 자동화 플랫폼 백엔드",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
)

app.add_exception_handler(FlowifyException, flowify_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.add_middleware(InternalAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
