import time

from app.core.nodes.base import NodeStrategy

MAX_LOOP_ITERATIONS = 1000
DEFAULT_TIMEOUT_SECONDS = 300


class IfElseNodeStrategy(NodeStrategy):
    """If/Else 조건 분기 노드"""

    async def execute(self, input_data: dict) -> dict:
        condition_field = self.config.get("condition_field", "")
        expected_value = self.config.get("expected_value")

        actual_value = input_data.get(condition_field)
        branch = "true" if actual_value == expected_value else "false"

        return {**input_data, "branch": branch}

    def validate(self) -> bool:
        return bool(self.config.get("condition_field"))


class LoopNodeStrategy(NodeStrategy):
    """Loop 반복 노드 (무한 루프 방지 내장)"""

    async def execute(self, input_data: dict) -> dict:
        items = input_data.get(self.config.get("items_field", "items"), [])
        max_iterations = min(self.config.get("max_iterations", MAX_LOOP_ITERATIONS), MAX_LOOP_ITERATIONS)
        transform_field = self.config.get("transform_field")
        results = []

        start_time = time.monotonic()
        for i, item in enumerate(items):
            if i >= max_iterations:
                break
            if time.monotonic() - start_time > DEFAULT_TIMEOUT_SECONDS:
                break
            if transform_field and isinstance(item, dict):
                results.append(item.get(transform_field, item))
            else:
                results.append(item)

        return {**input_data, "loop_results": results, "iterations": len(results)}

    def validate(self) -> bool:
        return bool(self.config.get("items_field"))
