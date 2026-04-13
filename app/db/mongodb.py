import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        serverSelectionTimeoutMS=10000,
    )
    _db = _client[settings.MONGODB_DB_NAME]

    # 연결 확인
    try:
        await _client.admin.command("ping")
        logger.info("MongoDB 연결 성공")
    except Exception as e:
        logger.error(f"MongoDB 연결 실패: {e}")
        raise

    # 인덱스 생성 (실패해도 앱은 시작)
    try:
        await _create_indexes(_db)
    except Exception as e:
        logger.warning(f"인덱스 생성 실패 (무시): {e}")


async def close_mongo_connection() -> None:
    global _client
    if _client:
        _client.close()


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB connection not initialized")
    return _db


async def _create_indexes(db: AsyncIOMotorDatabase) -> None:
    """워크플로우 실행 컬렉션 인덱스를 생성합니다."""
    collection = db.workflow_executions
    await collection.create_index("id", unique=True)
    await collection.create_index("workflow_id")
    await collection.create_index("user_id")
    await collection.create_index("started_at")
