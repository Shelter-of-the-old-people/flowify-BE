from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database


async def get_db() -> AsyncIOMotorDatabase:
    return get_database()


def get_user_id(request: Request) -> str:
    """인증 미들웨어가 주입한 user_id를 반환합니다."""
    return getattr(request.state, "user_id", "")
