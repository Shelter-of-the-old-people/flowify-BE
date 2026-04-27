from unittest.mock import AsyncMock, MagicMock

from app.core.engine.snapshot import SnapshotManager


class TestSnapshotManager:
    def test_save_and_get(self):
        sm = SnapshotManager()
        sm.save("node_1", {"key": "value"})
        result = sm.get_snapshot("node_1")
        assert result == {"key": "value"}

    def test_get_nonexistent_returns_none(self):
        sm = SnapshotManager()
        assert sm.get_snapshot("node_x") is None

    def test_get_returns_latest(self):
        sm = SnapshotManager()
        sm.save("node_1", {"v": 1})
        sm.save("node_1", {"v": 2})
        assert sm.get_snapshot("node_1") == {"v": 2}

    def test_rollback_to(self):
        sm = SnapshotManager()
        sm.save("node_1", {"a": 1})
        sm.save("node_2", {"b": 2})
        sm.save("node_3", {"c": 3})

        result = sm.rollback_to("node_2")
        assert result == {"b": 2}
        # node_3 스냅샷은 제거됨
        assert sm.get_snapshot("node_3") is None
        assert sm.get_snapshot("node_2") is not None

    def test_rollback_nonexistent_returns_none(self):
        sm = SnapshotManager()
        assert sm.rollback_to("node_x") is None

    def test_get_all_snapshots(self):
        sm = SnapshotManager()
        sm.save("node_1", {"a": 1})
        sm.save("node_2", {"b": 2})
        snapshots = sm.get_all_snapshots()
        assert len(snapshots) == 2
        assert snapshots[0]["node_id"] == "node_1"
        assert snapshots[1]["node_id"] == "node_2"

    def test_get_last_success_node_id(self):
        sm = SnapshotManager()
        assert sm.get_last_success_node_id() is None
        sm.save("node_1", {})
        sm.save("node_2", {})
        assert sm.get_last_success_node_id() == "node_2"

    def test_deep_copy_isolation(self):
        sm = SnapshotManager()
        data = {"list": [1, 2, 3]}
        sm.save("node_1", data)
        data["list"].append(4)
        assert sm.get_snapshot("node_1") == {"list": [1, 2, 3]}

    async def test_get_snapshot_from_db_success(self):
        """MongoDB에서 특정 노드의 스냅샷 데이터를 조회합니다."""
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(
            return_value={
                "_id": "exec_1",
                "nodeLogs": [
                    {
                        "nodeId": "node_1",
                        "status": "success",
                        "snapshot": {"stateData": {"type": "TEXT", "content": "hello"}},
                    },
                ],
            }
        )

        result = await SnapshotManager.get_snapshot_from_db(mock_db, "exec_1", "node_1")

        assert result == {"type": "TEXT", "content": "hello"}

    async def test_get_snapshot_from_db_not_found(self):
        """실행 문서가 없으면 None을 반환합니다."""
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=None)

        result = await SnapshotManager.get_snapshot_from_db(mock_db, "exec_missing", "node_1")

        assert result is None

    async def test_get_snapshot_from_db_missing_snapshot_returns_none(self):
        """대상 노드에 스냅샷이 없으면 None을 반환합니다."""
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(
            return_value={
                "_id": "exec_1",
                "nodeLogs": [
                    {"nodeId": "node_1", "status": "success", "snapshot": None},
                ],
            }
        )

        result = await SnapshotManager.get_snapshot_from_db(mock_db, "exec_1", "node_1")

        assert result is None

    async def test_get_last_success_snapshot(self):
        """마지막 성공 노드의 스냅샷 데이터를 반환합니다."""
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(
            return_value={
                "_id": "exec_1",
                "nodeLogs": [
                    {
                        "nodeId": "node_1",
                        "status": "success",
                        "snapshot": {"stateData": {"type": "TEXT", "content": "old"}},
                    },
                    {
                        "nodeId": "node_2",
                        "status": "failed",
                        "snapshot": {"stateData": {"type": "TEXT", "content": "failed"}},
                    },
                    {
                        "nodeId": "node_3",
                        "status": "success",
                        "snapshot": {"stateData": {"type": "SINGLE_FILE", "filename": "a.txt"}},
                    },
                ],
            }
        )

        result = await SnapshotManager.get_last_success_snapshot(mock_db, "exec_1")

        assert result == {"type": "SINGLE_FILE", "filename": "a.txt"}

    async def test_get_last_success_snapshot_without_success_returns_none(self):
        """성공 노드 스냅샷이 없으면 None을 반환합니다."""
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(
            return_value={
                "_id": "exec_1",
                "nodeLogs": [
                    {"nodeId": "node_1", "status": "failed", "snapshot": None},
                ],
            }
        )

        result = await SnapshotManager.get_last_success_snapshot(mock_db, "exec_1")

        assert result is None
