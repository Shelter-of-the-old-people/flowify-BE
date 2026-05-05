"""패스스루 노드 실행 전략."""

import copy
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy


class PassthroughNodeStrategy(NodeStrategy):
    """입력 canonical payload를 변경 없이 다음 노드로 전달합니다."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        """이전 노드의 출력 payload를 그대로 반환합니다."""
        if not input_data:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="패스스루 노드는 입력 데이터가 필요합니다.",
                context={"node_id": node.get("id")},
            )

        return copy.deepcopy(input_data)

    def validate(self, node: dict[str, Any]) -> bool:
        """패스스루 노드는 별도 설정 없이 유효합니다."""
        return True
