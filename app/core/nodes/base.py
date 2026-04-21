from abc import ABC, abstractmethod
from typing import Any


class NodeStrategy(ABC):
    """Strategy 패턴 - 노드 실행 로직 추상 클래스.

    v2 runtime contract:
      - node: 노드 전체 정보 dict (runtime_type, runtime_source/sink/config 포함)
      - input_data: 이전 노드의 canonical payload (첫 노드는 None)
      - service_tokens: 서비스별 OAuth access token dict
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        """노드 실행. canonical payload를 받아 처리 후 canonical payload를 반환."""
        pass

    @abstractmethod
    def validate(self, node: dict[str, Any]) -> bool:
        """노드 설정 유효성 검사. runtime 필드 기반으로 검증."""
        pass
