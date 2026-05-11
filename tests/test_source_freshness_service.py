from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.workflow import NodeDefinition
from app.services.source_freshness_service import SourceFreshnessService


def _source_node(mode: str = "seboard_new_posts") -> NodeDefinition:
    return NodeDefinition(
        id="source_1",
        type="web_news",
        config={"source_mode": mode, "maxResults": 10},
        runtime_type="input",
        runtime_source={
            "service": "web_news",
            "mode": mode,
            "target": "2",
            "canonical_input_type": "ARTICLE_LIST",
        },
    )


def _payload(*ids: str) -> dict:
    return {
        "type": "ARTICLE_LIST",
        "items": [
            {
                "id": item_id,
                "title": f"title-{item_id}",
                "url": f"https://example.com/{item_id}",
            }
            for item_id in ids
        ],
        "metadata": {"provider": "seboard", "count": len(ids)},
    }


@pytest.fixture()
def mock_db() -> MagicMock:
    db = MagicMock()
    collection = MagicMock()
    collection.find_one = AsyncMock()
    collection.update_one = AsyncMock()
    db.source_checkpoints = collection
    return db


@pytest.mark.asyncio
async def test_first_run_initializes_checkpoint_without_emitting_items(mock_db: MagicMock) -> None:
    """첫 실행은 현재 목록을 기준점으로 저장하고 기존 글을 통과시키지 않습니다."""
    mock_db.source_checkpoints.find_one.return_value = None
    service = SourceFreshnessService(mock_db)

    decision = await service.filter_output(
        user_id="user_1",
        workflow_id="workflow_1",
        node=_source_node(),
        payload=_payload("post_2", "post_1"),
    )

    assert decision.no_new_items is True
    assert decision.payload["items"] == []
    assert decision.payload["metadata"]["freshness"]["status"] == "initialized"
    assert decision.pending_commit is not None
    assert decision.pending_commit.document["cursorValue"] == "post_2"


@pytest.mark.asyncio
async def test_existing_checkpoint_filters_only_new_items(mock_db: MagicMock) -> None:
    """저장된 cursor 이전 항목은 제외하고 새 항목만 남깁니다."""
    mock_db.source_checkpoints.find_one.return_value = {
        "cursorValue": "post_2",
        "seenItemKeys": ["post_2", "post_1"],
    }
    service = SourceFreshnessService(mock_db)

    decision = await service.filter_output(
        user_id="user_1",
        workflow_id="workflow_1",
        node=_source_node(),
        payload=_payload("post_3", "post_2", "post_1"),
    )

    assert decision.no_new_items is False
    assert [item["id"] for item in decision.payload["items"]] == ["post_3"]
    assert decision.payload["metadata"]["freshness"]["status"] == "new_items"
    assert decision.pending_commit is not None
    assert decision.pending_commit.document["cursorValue"] == "post_3"


@pytest.mark.asyncio
async def test_non_freshness_source_returns_payload_unchanged(mock_db: MagicMock) -> None:
    """신규 감지 대상이 아닌 source mode는 checkpoint를 사용하지 않습니다."""
    service = SourceFreshnessService(mock_db)
    payload = _payload("post_1")

    decision = await service.filter_output(
        user_id="user_1",
        workflow_id="workflow_1",
        node=_source_node("seboard_posts"),
        payload=payload,
    )

    assert decision.payload is payload
    assert decision.no_new_items is False
    assert decision.pending_commit is None
    mock_db.source_checkpoints.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_payload_without_item_keys_does_not_filter_items(mock_db: MagicMock) -> None:
    """항목 key를 만들 수 없는 payload는 안전하게 원본을 유지합니다."""
    service = SourceFreshnessService(mock_db)
    payload = {
        "type": "ARTICLE_LIST",
        "items": [{"content": "no stable id"}],
        "metadata": {"provider": "custom"},
    }

    decision = await service.filter_output(
        user_id="user_1",
        workflow_id="workflow_1",
        node=_source_node(),
        payload=payload,
    )

    assert decision.payload is payload
    assert decision.no_new_items is False
    assert decision.pending_commit is None
    mock_db.source_checkpoints.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_pending_upserts_checkpoint(mock_db: MagicMock) -> None:
    """성공한 워크플로우의 pending checkpoint를 저장합니다."""
    mock_db.source_checkpoints.find_one.return_value = None
    service = SourceFreshnessService(mock_db)
    decision = await service.filter_output(
        user_id="user_1",
        workflow_id="workflow_1",
        node=_source_node(),
        payload=_payload("post_1"),
    )

    await service.commit_pending([decision.pending_commit])

    mock_db.source_checkpoints.update_one.assert_awaited_once()
    assert mock_db.source_checkpoints.update_one.await_args.kwargs["upsert"] is True
