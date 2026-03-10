from app.core.nodes.base import NodeStrategy
from app.core.nodes.input_node import InputNodeStrategy
from app.core.nodes.llm_node import LLMNodeStrategy
from app.core.nodes.logic_node import IfElseNodeStrategy, LoopNodeStrategy
from app.core.nodes.output_node import OutputNodeStrategy

_NODE_REGISTRY: dict[str, type[NodeStrategy]] = {
    "input": InputNodeStrategy,
    "llm": LLMNodeStrategy,
    "if_else": IfElseNodeStrategy,
    "loop": LoopNodeStrategy,
    "output": OutputNodeStrategy,
}


class NodeFactory:
    """Factory 패턴 - 노드 타입 문자열로부터 Strategy 인스턴스 생성"""

    @staticmethod
    def create(node_type: str, config: dict | None = None) -> NodeStrategy:
        node_class = _NODE_REGISTRY.get(node_type)
        if node_class is None:
            raise ValueError(f"Unknown node type: {node_type}")
        return node_class(config)

    @staticmethod
    def register(node_type: str, node_class: type[NodeStrategy]) -> None:
        _NODE_REGISTRY[node_type] = node_class
