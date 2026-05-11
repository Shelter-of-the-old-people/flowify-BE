"""Source checkpoint service for new-item workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.workflow import NodeDefinition

FRESHNESS_SOURCE_MODES = frozenset(
    {
        ("naver_news", "new_articles"),
        ("web_news", "seboard_new_posts"),
    }
)
MAX_SEEN_ITEM_KEYS = 200
_RESULT_SHAPING_CONFIG_KEYS = frozenset(
    {
        "includeContent",
        "include_content",
        "limit",
        "maxResults",
        "max_results",
    }
)


@dataclass(frozen=True)
class SourceCheckpointCommit:
    """MongoDB checkpoint update to commit after workflow success."""

    query: dict[str, Any]
    document: dict[str, Any]


@dataclass(frozen=True)
class SourceFreshnessDecision:
    """Filtered source payload and deferred checkpoint update."""

    payload: dict[str, Any]
    pending_commit: SourceCheckpointCommit | None
    no_new_items: bool


class SourceFreshnessService:
    """Filter source payloads to only new items using stored checkpoints."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._collection = db.source_checkpoints

    async def filter_output(
        self,
        *,
        user_id: str,
        workflow_id: str,
        node: NodeDefinition,
        payload: dict[str, Any],
    ) -> SourceFreshnessDecision:
        """Return a payload containing only items not seen by this source node."""
        runtime_source = node.runtime_source
        if runtime_source is None:
            return SourceFreshnessDecision(payload, None, False)

        service = runtime_source.service
        mode = runtime_source.mode
        if (service, mode) not in FRESHNESS_SOURCE_MODES:
            return SourceFreshnessDecision(payload, None, False)

        items = payload.get("items")
        if not isinstance(items, list):
            return SourceFreshnessDecision(payload, None, False)

        item_keys = [self._item_key(item) for item in items]
        indexed_items = [
            (item, item_key)
            for item, item_key in zip(items, item_keys, strict=False)
            if item_key
        ]
        current_keys = [item_key for _, item_key in indexed_items]
        if items and not current_keys:
            return SourceFreshnessDecision(payload, None, False)

        checkpoint_query = self._checkpoint_query(
            user_id=user_id,
            workflow_id=workflow_id,
            node=node,
            service=service,
            mode=mode,
            target=runtime_source.target,
        )
        checkpoint = await self._collection.find_one(checkpoint_query)

        if checkpoint is None:
            pending_commit = self._build_commit(
                checkpoint_query,
                previous_seen_keys=[],
                current_keys=current_keys,
            )
            return SourceFreshnessDecision(
                self._with_freshness_metadata(
                    payload,
                    [],
                    status="initialized",
                    checked_count=len(items),
                ),
                pending_commit,
                True,
            )

        cursor_value = str(checkpoint.get("cursorValue") or "")
        seen_keys = [
            str(item_key)
            for item_key in checkpoint.get("seenItemKeys", [])
            if item_key
        ]
        seen_key_set = set(seen_keys)
        new_items: list[dict[str, Any]] = []

        for item, item_key in indexed_items:
            if cursor_value and item_key == cursor_value:
                break
            if item_key not in seen_key_set:
                new_items.append(item)

        pending_commit = self._build_commit(
            checkpoint_query,
            previous_seen_keys=seen_keys,
            current_keys=current_keys,
        )
        return SourceFreshnessDecision(
            self._with_freshness_metadata(
                payload,
                new_items,
                status="new_items" if new_items else "no_new_items",
                checked_count=len(items),
            ),
            pending_commit,
            not new_items,
        )

    async def commit_pending(self, commits: list[SourceCheckpointCommit]) -> None:
        """Persist deferred checkpoint updates after successful workflow execution."""
        for commit in commits:
            await self._collection.update_one(
                commit.query,
                {"$set": commit.document, "$setOnInsert": {"createdAt": datetime.now(UTC)}},
                upsert=True,
            )

    @staticmethod
    def is_freshness_node(node: NodeDefinition) -> bool:
        """Return whether a node uses a source mode that requires checkpointing."""
        runtime_source = node.runtime_source
        if runtime_source is None:
            return False
        return (runtime_source.service, runtime_source.mode) in FRESHNESS_SOURCE_MODES

    def _checkpoint_query(
        self,
        *,
        user_id: str,
        workflow_id: str,
        node: NodeDefinition,
        service: str,
        mode: str,
        target: str,
    ) -> dict[str, Any]:
        return {
            "userId": user_id,
            "workflowId": workflow_id,
            "nodeId": node.id,
            "service": service,
            "mode": mode,
            "targetHash": self._target_hash(target, node.config),
        }

    @staticmethod
    def _target_hash(target: str, config: dict[str, Any]) -> str:
        stable_config = {
            key: value
            for key, value in config.items()
            if key not in _RESULT_SHAPING_CONFIG_KEYS
        }
        raw_value = json.dumps(
            {"target": target, "config": stable_config},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()

    @staticmethod
    def _item_key(item: Any) -> str | None:
        if not isinstance(item, dict):
            return None

        for key in ("id", "url", "originallink", "link"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        title = item.get("title")
        published_at = item.get("published_at")
        if isinstance(title, str) and title.strip():
            if isinstance(published_at, str) and published_at.strip():
                return f"{title.strip()}::{published_at.strip()}"
            return title.strip()

        return None

    @staticmethod
    def _build_commit(
        query: dict[str, Any],
        *,
        previous_seen_keys: list[str],
        current_keys: list[str],
    ) -> SourceCheckpointCommit | None:
        if not current_keys:
            return None

        seen_keys = list(dict.fromkeys([*current_keys, *previous_seen_keys]))[
            :MAX_SEEN_ITEM_KEYS
        ]
        return SourceCheckpointCommit(
            query=query,
            document={
                **query,
                "cursorType": "item_key",
                "cursorValue": current_keys[0],
                "seenItemKeys": seen_keys,
                "updatedAt": datetime.now(UTC),
            },
        )

    @staticmethod
    def _with_freshness_metadata(
        payload: dict[str, Any],
        items: list[dict[str, Any]],
        *,
        status: str,
        checked_count: int,
    ) -> dict[str, Any]:
        metadata = dict(payload.get("metadata") or {})
        metadata.update(
            {
                "count": len(items),
                "freshness": {
                    "status": status,
                    "checked_count": checked_count,
                    "new_count": len(items),
                },
            }
        )
        return {
            **payload,
            "items": items,
            "metadata": metadata,
        }
