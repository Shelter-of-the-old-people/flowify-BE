import copy
from datetime import datetime


class SnapshotManager:
    """노드 실행 전후 스냅샷 관리 (롤백 지원)"""

    def __init__(self):
        self._snapshots: list[dict] = []

    def save(self, node_id: str, data: dict) -> None:
        self._snapshots.append({
            "node_id": node_id,
            "data": copy.deepcopy(data),
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_snapshot(self, node_id: str) -> dict | None:
        for snapshot in reversed(self._snapshots):
            if snapshot["node_id"] == node_id:
                return snapshot["data"]
        return None

    def get_all_snapshots(self) -> list[dict]:
        return list(self._snapshots)

    def rollback_to(self, node_id: str) -> dict | None:
        target_idx = None
        for i, snapshot in enumerate(self._snapshots):
            if snapshot["node_id"] == node_id:
                target_idx = i
                break

        if target_idx is not None:
            data = self._snapshots[target_idx]["data"]
            self._snapshots = self._snapshots[: target_idx + 1]
            return copy.deepcopy(data)
        return None

    def get_last_success_node_id(self) -> str | None:
        """마지막으로 스냅샷이 저장된 노드 ID를 반환합니다."""
        if self._snapshots:
            return self._snapshots[-1]["node_id"]
        return None

    @staticmethod
    async def get_snapshot_from_db(db, execution_id: str, node_id: str) -> dict | None:
        """MongoDB에서 특정 노드의 스냅샷 데이터를 조회합니다."""
        doc = await db.workflow_executions.find_one({"_id": execution_id})
        if not doc:
            return None
        for log in doc.get("nodeLogs", []):
            if log.get("nodeId") == node_id and log.get("snapshot"):
                return log["snapshot"].get("stateData")
        return None

    @staticmethod
    async def get_last_success_snapshot(db, execution_id: str) -> tuple[str, dict] | None:
        """MongoDB에서 마지막 성공 노드의 (node_id, snapshot_data)를 반환합니다."""
        doc = await db.workflow_executions.find_one({"_id": execution_id})
        if not doc:
            return None
        for log in reversed(doc.get("nodeLogs", [])):
            if log.get("status") == "success" and log.get("snapshot"):
                return log.get("nodeId"), log["snapshot"].get("stateData")
        return None
