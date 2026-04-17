# 작업자 C — 스냅샷/롤백 & 고급 기능

> 작성일: 2026-04-17 | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17

---

## 담당 파일

| 파일 | 상태 |
|------|------|
| `app/core/engine/snapshot.py` | ⚠️ in-memory 전용 — 롤백 복원 로직과 연결 미흡 |
| `app/api/v1/endpoints/execution.py` | ⚠️ rollback 상태만 변경, 실제 복원 없음 |
| `app/models/workflow.py` | 🟡 EdgeDefinition에 `label` 필드 없음 |
| `app/services/vector_service.py` | ❌ 전체 TODO |
| `tests/test_snapshot.py` | ⚠️ in-memory 동작만 테스트 — 보완 필요 |
| `tests/test_vector_service.py` | ❌ 없음 — 신규 작성 |

---

## C-1. [🟡 High] Snapshot — 현황 재분석 및 개선

### 현재 구조 이해

`SnapshotManager`는 in-memory 리스트만 사용하지만, 실제로는 스냅샷 데이터가 이미 MongoDB에 저장됨:

```
executor.py:201  → snapshot_manager.save(node_def.id, input_data)
                   (in-memory에만 저장)

executor.py:211  → NodeExecutionLog.snapshot = NodeSnapshot(stateData=snapshot_data)
                   (MongoDB workflow_executions.nodeLogs[].snapshot 에 저장됨)
```

즉, 스냅샷 데이터 자체는 MongoDB에 있지만, 롤백 시 이 데이터를 읽어오는 메서드가 `SnapshotManager`에 없음.

### 개선: SnapshotManager에 DB 조회 메서드 추가

```python
# app/core/engine/snapshot.py
from motor.motor_asyncio import AsyncIOMotorDatabase


class SnapshotManager:
    def __init__(self):
        self._snapshots: list[dict] = []

    def save(self, node_id: str, data: dict) -> None:
        self._snapshots.append({
            "node_id": node_id,
            "data": data,
        })

    def get_latest(self) -> dict | None:
        return self._snapshots[-1] if self._snapshots else None

    def get_for_node(self, node_id: str) -> dict | None:
        for snap in reversed(self._snapshots):
            if snap["node_id"] == node_id:
                return snap["data"]
        return None

    async def get_snapshot_from_db(
        self,
        db: AsyncIOMotorDatabase,
        execution_id: str,
        node_id: str,
    ) -> dict | None:
        """MongoDB에서 특정 노드의 스냅샷 데이터를 조회합니다."""
        doc = await db.workflow_executions.find_one({"_id": execution_id})
        if not doc:
            return None
        for log in doc.get("nodeLogs", []):
            if log.get("nodeId") == node_id and log.get("snapshot"):
                return log["snapshot"].get("stateData")
        return None

    async def get_last_success_snapshot(
        self,
        db: AsyncIOMotorDatabase,
        execution_id: str,
    ) -> dict | None:
        """마지막 성공 노드의 스냅샷을 MongoDB에서 조회합니다."""
        doc = await db.workflow_executions.find_one({"_id": execution_id})
        if not doc:
            return None
        for log in reversed(doc.get("nodeLogs", [])):
            if log.get("status") == "success" and log.get("snapshot"):
                return log["snapshot"].get("stateData")
        return None
```

---

## C-2. [🟡 High] Rollback — 설계 확정 및 개선

### 현재 구현 (`app/api/v1/endpoints/execution.py:122-126`)

```python
# 상태를 PENDING으로 전환만 함
await db.workflow_executions.update_one(
    {"_id": execution_id},
    {"$set": {"state": WorkflowState.PENDING.value}},
)
```

### 설계 결정: 방식 A (현재 방식 유지 + 개선)

Spring Boot 명세에서 `POST /executions/{id}/rollback`의 응답은 "HTTP 2xx이면 성공"으로만 명시됨. 실제 재실행은 Spring Boot가 별도 `/execute` 호출로 수행하는 구조.

현재 구현이 명세와 일치하므로 방식 A 유지. 단, 롤백 후 실행 이력을 정리하는 로직 추가:

```python
@router.post("/{execution_id}/rollback")
async def rollback_execution(
    execution_id: str,
    body: RollbackRequest | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> RollbackResponse:
    doc = await _get_execution_doc(db, execution_id)

    current_state = doc.get("state")
    if current_state not in _ROLLBACK_ALLOWED_STATES:
        raise FlowifyException(
            ErrorCode.ROLLBACK_UNAVAILABLE,
            detail=f"현재 상태({current_state})에서는 롤백할 수 없습니다.",
        )

    node_logs = doc.get("nodeLogs", [])
    target_node_id = body.node_id if body else None

    if not target_node_id:
        for log in reversed(node_logs):
            if log.get("status") == "success":
                target_node_id = log.get("nodeId")
                break

    if not target_node_id:
        raise FlowifyException(
            ErrorCode.ROLLBACK_UNAVAILABLE,
            detail="롤백할 수 있는 성공 노드가 없습니다.",
        )

    # 상태 리셋 + 에러 정보 초기화
    await db.workflow_executions.update_one(
        {"_id": execution_id},
        {
            "$set": {
                "state": WorkflowState.PENDING.value,
                "errorMessage": None,
                "finishedAt": None,
            }
        },
    )

    return RollbackResponse(
        execution_id=execution_id,
        status="pending",
        rollback_point=target_node_id,
        message=f"Rolled back to {target_node_id}. Ready for re-execution.",
    )
```

### 중요 주의사항

스냅샷의 `stateData`에는 credentials(service tokens)가 포함되지 않음 (`executor.py:200`에서 `_strip_credentials()` 적용). 따라서 롤백 후 재실행 시 Spring Boot가 새로운 `/execute` 요청을 보낼 때 다시 `service_tokens`를 포함해야 함. Spring Boot 담당자와 이 흐름 확인 필요.

---

## C-3. [🟠 Medium] EdgeDefinition — label 필드 추가

### 현재 문제 (`app/models/workflow.py:28-32`)

```python
class EdgeDefinition(BaseModel):
    id: str | None = None
    source: str
    target: str
    # label 필드 없음
```

IfElse 분기에서 어느 edge가 "true" 경로이고 어느 edge가 "false" 경로인지 구분하는 정보가 없음. 현재는 edge 순서(첫 번째=true, 두 번째=false)로 처리.

### 수정

```python
class EdgeDefinition(BaseModel):
    id: str | None = None
    source: str
    target: str
    label: str | None = None  # "true" | "false" | None
```

### 작업자 B와 연동

label 필드 추가 후 `executor.py`의 `_build_branch_map()`에서 label 기반 분기를 사용하도록 수정 가능. label이 None이면 기존 순서 기반 폴백 처리:

```python
# executor.py _build_branch_map() 에서 (작업자 B가 수정)
for edge in edges:
    if edge.source in if_else_node_ids:
        if edge.label in ("true", "false"):
            # label 기반 (정확)
            if edge.source not in branch_map:
                branch_map[edge.source] = {}
            branch_map[edge.source][edge.label] = edge.target
        elif edge.source not in branch_map:
            # label 없으면 순서 기반 폴백
            ...
```

Spring Boot가 edge에 label을 보내는지 확인 필요. 보내지 않는다면 label 필드 추가만 하고 순서 기반 유지.

---

## C-4. [🟠 Medium] VectorService — ChromaDB 구현

**최종 발표용 — 6/17 전 완료**

### 현재 상태 (`app/services/vector_service.py`)

전체 TODO. RAG(Retrieval-Augmented Generation) 파이프라인을 위한 벡터 검색 기능.

### 기술 선택

| 옵션 | 장점 | 단점 |
|------|------|------|
| ChromaDB + sentence-transformers | 로컬 실행, 무료 | 모델 다운로드 필요(수백 MB), Docker 빌드 느림 |
| ChromaDB + OpenAI Embedding API | 고품질 임베딩, 설정 간단 | API 비용, 외부 의존성 |

**권장: OpenAI Embedding API** — 이미 `LLMService`에서 OpenAI를 사용 중이므로 통일성 유지.

### 구현 (`app/services/vector_service.py`)

```python
import chromadb
from langchain_openai import OpenAIEmbeddings
from app.config import settings


class VectorService:
    def __init__(self):
        # 영속화: Docker volume에 마운트된 경로 사용
        self._client = chromadb.PersistentClient(path="./chroma_data")
        self._collection = self._client.get_or_create_collection(
            name="flowify_docs",
            metadata={"hnsw:space": "cosine"},
        )
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.LLM_API_KEY,
        )

    async def add_documents(
        self,
        documents: list[str],
        metadata: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        if not documents:
            return
        embeddings = self._embeddings.embed_documents(documents)
        doc_ids = ids or [f"doc_{i}_{hash(doc)}" for i, doc in enumerate(documents)]
        self._collection.upsert(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadata or [{} for _ in documents],
            ids=doc_ids,
        )

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_embedding = self._embeddings.embed_query(query)
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
        )
        if not results["documents"]:
            return []
        return [
            {
                "document": doc,
                "metadata": meta,
                "distance": dist,
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    async def delete_document(self, doc_id: str) -> None:
        self._collection.delete(ids=[doc_id])
```

### `requirements.txt`에 추가 필요

```
chromadb>=0.4.0
langchain-openai>=0.1.0   # 이미 있을 수 있음 — 확인 필요
```

### Docker 설정

`docker-compose.yml`에 volume 추가:

```yaml
services:
  fastapi:
    volumes:
      - chroma_data:/app/chroma_data

volumes:
  chroma_data:
```

---

## C-5. [🟠 Medium] 테스트 보완

### `tests/test_snapshot.py` 보완 항목

현재 테스트는 in-memory `SnapshotManager` 동작만 확인. 신규 DB 조회 메서드 테스트 추가:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.engine.snapshot import SnapshotManager


@pytest.mark.asyncio
async def test_get_snapshot_from_db_success():
    manager = SnapshotManager()
    mock_db = MagicMock()
    mock_db.workflow_executions.find_one = AsyncMock(return_value={
        "_id": "exec_1",
        "nodeLogs": [
            {"nodeId": "node_1", "status": "success",
             "snapshot": {"stateData": {"key": "value"}}},
        ]
    })
    result = await manager.get_snapshot_from_db(mock_db, "exec_1", "node_1")
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_get_snapshot_from_db_not_found():
    manager = SnapshotManager()
    mock_db = MagicMock()
    mock_db.workflow_executions.find_one = AsyncMock(return_value=None)
    result = await manager.get_snapshot_from_db(mock_db, "exec_missing", "node_1")
    assert result is None


@pytest.mark.asyncio
async def test_get_last_success_snapshot():
    manager = SnapshotManager()
    mock_db = MagicMock()
    mock_db.workflow_executions.find_one = AsyncMock(return_value={
        "nodeLogs": [
            {"nodeId": "node_1", "status": "success",
             "snapshot": {"stateData": {"step": 1}}},
            {"nodeId": "node_2", "status": "failed", "snapshot": None},
        ]
    })
    result = await manager.get_last_success_snapshot(mock_db, "exec_1")
    assert result == {"step": 1}
```

### `tests/test_vector_service.py` (신규)

```python
import pytest
from unittest.mock import MagicMock, patch
from app.services.vector_service import VectorService


@pytest.mark.asyncio
async def test_add_and_search():
    with patch("app.services.vector_service.chromadb") as mock_chroma, \
         patch("app.services.vector_service.OpenAIEmbeddings") as mock_emb:
        mock_collection = MagicMock()
        mock_chroma.PersistentClient.return_value.get_or_create_collection.return_value = mock_collection
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "documents": [["테스트 문서"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }
        mock_emb.return_value.embed_documents.return_value = [[0.1, 0.2]]
        mock_emb.return_value.embed_query.return_value = [0.1, 0.2]

        svc = VectorService()
        await svc.add_documents(["테스트 문서"])
        results = await svc.search("테스트")

    assert len(results) == 1
    assert results[0]["document"] == "테스트 문서"


@pytest.mark.asyncio
async def test_search_empty_collection():
    with patch("app.services.vector_service.chromadb") as mock_chroma, \
         patch("app.services.vector_service.OpenAIEmbeddings"):
        mock_collection = MagicMock()
        mock_chroma.PersistentClient.return_value.get_or_create_collection.return_value = mock_collection
        mock_collection.count.return_value = 0

        svc = VectorService()
        results = await svc.search("쿼리")

    assert results == []
```

---

## 잠재적 오류 & 주의사항

### 1. 롤백 후 재실행의 credentials 문제

`executor.py:200`에서 `_strip_credentials(input_data)`를 스냅샷에 저장하므로, 스냅샷 `stateData`에는 service tokens가 없음. 롤백 후 재실행 시 Spring Boot가 다시 `service_tokens`를 포함해서 `/execute` 요청을 보내야 함.

Spring Boot 담당자에게 이 흐름 확인 필요:
- 롤백 응답을 받으면 Spring Boot가 자동으로 재실행 요청을 보내는가?
- 사용자가 수동으로 재실행 버튼을 눌러야 하는가?

### 2. ChromaDB 영속성 경로

`chromadb.PersistentClient(path="./chroma_data")`는 현재 작업 디렉토리 기준 경로. Docker 환경에서는 컨테이너 재시작 시 데이터 손실. volume mount 설정 필수.

### 3. OpenAI Embedding API 비용

`text-embedding-3-small` 모델은 토큰당 비용 발생. 개발 환경에서 과도한 호출에 주의. `add_documents()`는 배치 처리로 비용 최소화 가능.

### 4. EdgeDefinition label 추가 후 하위 호환

Spring Boot가 label을 보내지 않는 경우 `None`으로 처리됨. 기존 워크플로우가 label 없이 동작하던 것이 label 추가 후에도 동일하게 동작해야 함. executor의 분기 로직에서 label이 None이면 기존 순서 기반 폴백 처리 확인 필요.

### 5. SnapshotManager의 in-memory `_snapshots` 리스트 역할

`_snapshots`는 현재 실행 세션 내에서만 유효. 이미 `NodeExecutionLog.snapshot`을 통해 MongoDB에 저장되므로 중복이지만, 동일 실행 내에서 빠른 접근이 필요하면 유지. 불필요하면 제거하고 MongoDB 조회만 사용.

---

## 작업 체크리스트

**중간 발표 (4/29) 전:**
- [ ] `snapshot.py` DB 조회 메서드 추가 (`get_snapshot_from_db`, `get_last_success_snapshot`)
- [ ] `execution.py` rollback에서 `errorMessage`, `finishedAt` 초기화 추가
- [ ] `test_snapshot.py` DB 조회 테스트 추가

**최종 제출 (6/17) 전:**
- [ ] `workflow.py` EdgeDefinition에 `label: str | None = None` 추가
- [ ] `vector_service.py` ChromaDB + OpenAI Embedding 구현
- [ ] `docker-compose.yml`에 chroma_data volume 추가
- [ ] `requirements.txt`에 chromadb 추가
- [ ] `tests/test_vector_service.py` 작성
- [ ] Spring Boot 담당자와 롤백 후 재실행 흐름 확인
