from app.core.engine.state import WorkflowState, WorkflowStateManager
from app.core.nodes.base import NodeStrategy
from app.core.nodes.factory import NodeFactory


class WorkflowExecutor:
    """워크플로우 실행 엔진"""

    def __init__(self):
        self._state_manager = WorkflowStateManager()
        self._factory = NodeFactory()

    async def execute(self, workflow_definition: dict) -> dict:
        self._state_manager.transition(WorkflowState.RUNNING)
        results = []

        try:
            nodes = workflow_definition.get("nodes", [])
            data = {}

            for node_def in nodes:
                node: NodeStrategy = self._factory.create(node_def["type"], node_def.get("config", {}))
                data = await node.execute(data)
                results.append({"node_id": node_def.get("id"), "output": data})

            self._state_manager.transition(WorkflowState.SUCCESS)
            return {"status": "success", "results": results}

        except Exception as e:
            self._state_manager.transition(WorkflowState.FAILED)
            return {"status": "failed", "error": str(e), "results": results}
