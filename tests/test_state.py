import pytest

from app.common.errors import FlowifyException
from app.core.engine.state import WorkflowState, WorkflowStateManager


class TestWorkflowStateManager:
    def test_initial_state(self):
        sm = WorkflowStateManager()
        assert sm.state == WorkflowState.PENDING

    def test_custom_initial_state(self):
        sm = WorkflowStateManager(initial_state=WorkflowState.FAILED)
        assert sm.state == WorkflowState.FAILED

    def test_valid_transitions(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        assert sm.state == WorkflowState.RUNNING
        sm.transition(WorkflowState.SUCCESS)
        assert sm.state == WorkflowState.SUCCESS

    def test_pending_to_running_to_failed(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.FAILED)
        assert sm.state == WorkflowState.FAILED

    def test_failed_to_rollback_available(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.FAILED)
        sm.transition(WorkflowState.ROLLBACK_AVAILABLE)
        assert sm.state == WorkflowState.ROLLBACK_AVAILABLE

    def test_rollback_to_pending(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.FAILED)
        sm.transition(WorkflowState.ROLLBACK_AVAILABLE)
        sm.transition(WorkflowState.PENDING)
        assert sm.state == WorkflowState.PENDING

    def test_invalid_transition_raises(self):
        sm = WorkflowStateManager()
        with pytest.raises(FlowifyException) as exc_info:
            sm.transition(WorkflowState.SUCCESS)
        assert "잘못된 상태 전환" in exc_info.value.detail

    def test_success_is_terminal(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.SUCCESS)
        assert sm.is_terminal() is True

    def test_failed_is_not_terminal(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.FAILED)
        assert sm.is_terminal() is False

    def test_pending_is_not_terminal(self):
        sm = WorkflowStateManager()
        assert sm.is_terminal() is False

    def test_running_to_stopped(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.STOPPED)
        assert sm.state == WorkflowState.STOPPED

    def test_stopped_is_terminal(self):
        sm = WorkflowStateManager()
        sm.transition(WorkflowState.RUNNING)
        sm.transition(WorkflowState.STOPPED)
        assert sm.is_terminal() is True

    def test_stopped_has_no_outgoing_transitions(self):
        sm = WorkflowStateManager(initial_state=WorkflowState.STOPPED)
        with pytest.raises(FlowifyException):
            sm.transition(WorkflowState.PENDING)
