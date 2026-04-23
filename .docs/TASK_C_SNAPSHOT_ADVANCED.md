# 작업자 C — 스냅샷/롤백 & 고급 기능

> 작성일: 2026-04-17 | **v2 업데이트: 2026-04-23** | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17

---

## v2 런타임 컨트랙트 변경 요약

> **핵심**: 작업자 C의 담당 영역(스냅샷, 롤백, VectorService)은 v2 변경의 직접적인 영향을 적게 받았습니다. 다만 executor.py와 workflow.py가 크게 바뀌었으므로 아래 변경 사항을 인지하고 작업해야 합니다.

### 작업자 C에 영향을 주는 v2 변경 사항

| 항목 | 변경 내용 | C 작업에 미치는 영향 |
|------|-----------|-------------------|
| `_strip_credentials()` → `_sanitize_for_log()` | 이름 변경 + None 안전 처리 | 스냅샷에 저장되는 데이터 형식은 동일 |
| canonical payload 도입 | 노드 간 데이터가 `{"type": "TEXT", "content": ...}` 형태 | 스냅샷 `stateData`에 canonical payload가 저장됨 |
| `EdgeDefinition.label` 추가 | ✅ 이미 완료됨 | - |
| `node_outputs` per-node 저장 | flat dict 누적 → 노드별 독립 dict | 롤백 시 복원 대상이 `node_outputs[node_id]` |
| `ExecutionResult` 간소화 | `execution_id`만 반환 | rollback 응답 형식에는 영향 없음 |

---

## 담당 파일

| 파일 | 상태 |
|------|------|
| `app/core/engine/snapshot.py` | ✅ **완료** — DB 조회 메서드 추가됨 (get_snapshot_from_db, get_last_success_snapshot) |
| `app/api/v1/endpoints/execution.py` | ✅ **완료** — rollback 개선 (errorMessage/finishedAt 초기화) |
| `app/models/workflow.py` | ✅ **완료** — EdgeDefinition에 `label: str | None = None` 추가됨 |
| `app/services/vector_service.py` | ❌ 전체 TODO |
| `tests/test_snapshot.py` | ⚠️ in-memory 동작만 테스트 — 보완 필요 |
| `tests/test_vector_service.py` | ❌ 없음 — 신규 작성 |

---

## ✅ C-1. [완료] Snapshot — DB 조회 메서드 추가

**v2 구현 시 함께 완료됨.** `app/core/engine/snapshot.py`에 `get_snapshot_from_db()`, `get_last_success_snapshot()` static 메서드 추가됨.

### 참고: 현재 구조

```
executor.py → snapshot_manager.save(node_def.id, input_data)
              (in-memory에만 저장)

executor.py → NodeExecutionLog.snapshot = NodeSnapshot(stateData=snapshot_data)
              (MongoDB workflow_executions.nodeLogs[].snapshot 에 저장됨)
```

**v2 변경 참고**: `snapshot_data`는 `_sanitize_for_log(input_data)`의 결과이며, `input_data`는 이전 노드의 **canonical payload** (예: `{"type": "TEXT", "content": "..."}`)입니다. 기존과 달리 credentials가 input_data에 포함되지 않으므로 sanitize 결과는 canonical payload 그 자체입니다.

### 개선: SnapshotManager에 DB 조회 메서드 추가

```python
from motor.motor_asyncio import AsyncIOMotorDatabase


class SnapshotManager:
    # ... 기존 in-memory 메서드 유지 ...

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

## ✅ C-2. [완료] Rollback — 설계 확정 및 개선

**v2 구현 시 함께 완료됨.** `app/api/v1/endpoints/execution.py`에서 rollback 시 `errorMessage`/`finishedAt` 초기화, 마지막 성공 노드 자동 탐색 등 구현됨.

### 개선

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

### v2 참고: 롤백 후 재실행의 credentials 문제

v2에서는 `service_tokens`가 input_data에 포함되지 않고 별도 파라미터로 전달됩니다. 따라서 스냅샷 `stateData`에는 처음부터 토큰이 포함되지 않습니다. 롤백 후 재실행 시 Spring Boot가 새로운 `/execute` 요청에 `service_tokens`를 다시 포함해야 합니다.

---

## ✅ C-3. [완료] EdgeDefinition — label 필드 추가

v2 구현에서 완료됨. 현재 `app/models/workflow.py`:

```python
class EdgeDefinition(BaseModel):
    id: str | None = None
    source: str
    target: str
    label: str | None = None  # "true" | "false" | None
```

`executor.py`의 `_build_branch_map()`도 이미 label 기반 분기를 우선 처리하도록 구현됨.

---

## C-4. [🟠 Medium] VectorService — ChromaDB 구현

**최종 발표용 — 6/17 전 완료**

### 현재 상태 (`app/services/vector_service.py`)

전체 TODO. RAG(Retrieval-Augmented Generation) 파이프라인을 위한 벡터 검색 기능.

### 기술 선택

**권장: OpenAI Embedding API** — 이미 `LLMService`에서 OpenAI를 사용 중이므로 통일성 유지.

### 구현 (`app/services/vector_service.py`)

```python
import chromadb
from langchain_openai import OpenAIEmbeddings
from app.config import settings


class VectorService:
    def __init__(self):
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
langchain-openai>=0.1.0
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

현재 테스트는 in-memory 동작만 확인. DB 조회 메서드 테스트 추가:

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
             "snapshot": {"stateData": {"type": "TEXT", "content": "hello"}}},
        ]
    })
    result = await manager.get_snapshot_from_db(mock_db, "exec_1", "node_1")
    assert result == {"type": "TEXT", "content": "hello"}


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
             "snapshot": {"stateData": {"type": "SINGLE_FILE", "filename": "a.txt"}}},
            {"nodeId": "node_2", "status": "failed", "snapshot": None},
        ]
    })
    result = await manager.get_last_success_snapshot(mock_db, "exec_1")
    assert result == {"type": "SINGLE_FILE", "filename": "a.txt"}
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
```

---

## 잠재적 오류 & 주의사항

### 1. 롤백 후 재실행 흐름

v2에서 `service_tokens`는 input_data가 아닌 별도 파라미터로 전달됩니다. 스냅샷에는 토큰이 포함되지 않습니다. 롤백 후 재실행 시 Spring Boot가 다시 `service_tokens`를 포함한 `/execute` 요청을 보내야 합니다.

### 2. ChromaDB 영속성 경로

Docker 환경에서는 컨테이너 재시작 시 데이터 손실. volume mount 설정 필수.

### 3. OpenAI Embedding API 비용

`text-embedding-3-small` 모델은 토큰당 비용 발생. 개발 환경에서 과도한 호출 주의.

### 4. SnapshotManager의 in-memory `_snapshots` 역할

`_snapshots`는 현재 실행 세션 내에서만 유효. `NodeExecutionLog.snapshot`을 통해 MongoDB에도 저장되므로 중복이지만, 동일 실행 내 빠른 접근용으로 유지.

---

## 작업 체크리스트

**중간 발표 (4/29) 전:**
- [x] `snapshot.py` DB 조회 메서드 추가 ✅ 완료 (get_snapshot_from_db, get_last_success_snapshot)
- [x] `execution.py` rollback에서 `errorMessage`, `finishedAt` 초기화 추가 ✅ 완료
- [ ] `test_snapshot.py` DB 조회 테스트 추가

**최종 제출 (6/17) 전:**
- [x] `workflow.py` EdgeDefinition에 `label: str | None = None` 추가 ✅ v2 완료
- [ ] `vector_service.py` ChromaDB + OpenAI Embedding 구현
- [ ] `docker-compose.yml`에 chroma_data volume 추가
- [x] `pyproject.toml`에 chromadb 추가 ✅ 완료
- [ ] `tests/test_vector_service.py` 작성 — 스켈레톤 생성됨
- [ ] Spring Boot 담당자와 롤백 후 재실행 흐름 확인
