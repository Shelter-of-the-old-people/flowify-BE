from enum import Enum

from app.common.errors import ErrorCode, FlowifyException


class WorkflowState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLBACK_AVAILABLE = "rollback_available"


_TERMINAL_STATES = {WorkflowState.SUCCESS}


class WorkflowStateManager:
    """State 패턴 기반 워크플로우 상태 관리"""

    VALID_TRANSITIONS = {
        WorkflowState.PENDING: {WorkflowState.RUNNING},
        WorkflowState.RUNNING: {WorkflowState.SUCCESS, WorkflowState.FAILED},
        WorkflowState.FAILED: {WorkflowState.ROLLBACK_AVAILABLE, WorkflowState.PENDING},
        WorkflowState.ROLLBACK_AVAILABLE: {WorkflowState.PENDING},
        WorkflowState.SUCCESS: set(),
    }

    def __init__(self, initial_state: WorkflowState = WorkflowState.PENDING):
        self._state = initial_state

    @property
    def state(self) -> WorkflowState:
        return self._state

    def transition(self, new_state: WorkflowState) -> None:
        if new_state not in self.VALID_TRANSITIONS.get(self._state, set()):
            raise FlowifyException(
                ErrorCode.INVALID_STATE_TRANSITION,
                detail=f"잘못된 상태 전환: {self._state.value} -> {new_state.value}",
                context={"from": self._state.value, "to": new_state.value},
            )
        self._state = new_state

    def is_terminal(self) -> bool:
        return self._state in _TERMINAL_STATES
