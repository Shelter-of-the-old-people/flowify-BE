from app.core.nodes.base import NodeStrategy


class OutputNodeStrategy(NodeStrategy):
    """출력 노드 - Notion, Slack, Gmail 등 외부 서비스로 결과 전달"""

    async def execute(self, input_data: dict) -> dict:
        target = self.config.get("target", "console")
        # TODO: target에 따라 Notion, Slack, Gmail 등으로 데이터 전송
        return {**input_data, "output_target": target, "delivered": True}

    def validate(self) -> bool:
        return "target" in self.config
