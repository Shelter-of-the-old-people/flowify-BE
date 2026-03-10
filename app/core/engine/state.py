from enum import Enum


class WorkflowState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLBACK_AVAILABLE = "rollback_available"


class WorkflowStateManager:
    """State 패턴 기반 워크플로우 상태 관리"""

    VALID_TRANSITIONS = {
        WorkflowState.PENDING: {WorkflowState.RUNNING},
        WorkflowState.RUNNING: {WorkflowState.SUCCESS, WorkflowState.FAILED},
        WorkflowState.FAILED: {WorkflowState.ROLLBACK_AVAILABLE, WorkflowState.PENDING},
        WorkflowState.ROLLBACK_AVAILABLE: {WorkflowState.PENDING},
        WorkflowState.SUCCESS: set(),
    }

    def __init__(self):
        self._state = WorkflowState.PENDING

    @property
    def state(self) -> WorkflowState:
        return self._state

    def transition(self, new_state: WorkflowState) -> None:
        if new_state not in self.VALID_TRANSITIONS.get(self._state, set()):
            raise ValueError(f"Invalid transition: {self._state} -> {new_state}")
        self._state = new_state
