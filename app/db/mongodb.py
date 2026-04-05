from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _db = _client[settings.MONGODB_DB_NAME]
    await _create_indexes(_db)


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
