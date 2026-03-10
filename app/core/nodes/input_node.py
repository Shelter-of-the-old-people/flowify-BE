from app.core.nodes.base import NodeStrategy


class InputNodeStrategy(NodeStrategy):
    """입력 노드 - 파일, 이메일, 시트 등 데이터 수집 및 정규화"""

    async def execute(self, input_data: dict) -> dict:
        source = self.config.get("source", "manual")
        # TODO: source 타입에 따라 Google Drive, Gmail 등에서 데이터 가져오기
        return {**input_data, "source": source, "raw_data": self.config.get("data", "")}

    def validate(self) -> bool:
        return "source" in self.config
