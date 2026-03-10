from abc import ABC, abstractmethod


class NodeStrategy(ABC):
    """Strategy 패턴 - 노드 실행 로직 추상 클래스"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, input_data: dict) -> dict:
        """노드 실행. input_data를 받아 처리 후 output_data를 반환."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """노드 설정 유효성 검사"""
        pass
