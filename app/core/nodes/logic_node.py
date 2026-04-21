"""Logic 노드 — IfElse 분기 및 Loop 반복 처리.

참조: FASTAPI_IMPLEMENTATION_GUIDE.md 섹션 7.2, 7.3
"""

import time
from typing import Any

from app.core.nodes.base import NodeStrategy

MAX_LOOP_ITERATIONS = 1000
DEFAULT_TIMEOUT_SECONDS = 300


class IfElseNodeStrategy(NodeStrategy):
    """If/Else 조건 분기 노드.

    runtime_config의 condition을 평가하여 branch: "true"/"false"를 반환.
    canonical payload를 그대로 전달하면서 branch 정보를 추가.
    """

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_config = node.get("runtime_config") or {}
        condition_field = runtime_config.get("condition_field") or self.config.get("condition_field", "")
        expected_value = runtime_config.get("expected_value") or self.config.get("expected_value")

        # canonical payload에서 조건 평가
        actual_value = None
        if input_data:
            actual_value = input_data.get(condition_field)

        branch = "true" if actual_value == expected_value else "false"

        # canonical payload에 branch 정보 추가하여 반환
        result = dict(input_data) if input_data else {}
        result["branch"] = branch
        return result

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        return bool(
            runtime_config.get("condition_field") or self.config.get("condition_field")
        )


class LoopNodeStrategy(NodeStrategy):
    """Loop 반복 노드 (무한 루프 방지 내장).

    리스트형 canonical payload (FILE_LIST, EMAIL_LIST 등)의 items를 순회.
    """

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_config = node.get("runtime_config") or {}
        max_iterations = min(
            runtime_config.get("max_iterations") or self.config.get("max_iterations", MAX_LOOP_ITERATIONS),
            MAX_LOOP_ITERATIONS,
        )
        transform_field = runtime_config.get("transform_field") or self.config.get("transform_field")

        # canonical payload에서 items 추출
        items = []
        if input_data:
            data_type = input_data.get("type", "")
            if data_type in ("FILE_LIST", "EMAIL_LIST", "SCHEDULE_DATA"):
                items = input_data.get("items", [])
            elif data_type == "SPREADSHEET_DATA":
                items = input_data.get("rows", [])
            else:
                # fallback: items_field 기반
                items_field = self.config.get("items_field", "items")
                items = input_data.get(items_field, [])

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

        return {
            "type": input_data.get("type", "TEXT") if input_data else "TEXT",
            "items": results,
            "loop_results": results,
            "iterations": len(results),
        }

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        return bool(
            runtime_config.get("node_type") or self.config.get("items_field")
        )
