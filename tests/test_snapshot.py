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
