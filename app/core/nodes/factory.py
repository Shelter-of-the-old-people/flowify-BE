from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy
from app.core.nodes.input_node import InputNodeStrategy
from app.core.nodes.llm_node import LLMNodeStrategy
from app.core.nodes.logic_node import IfElseNodeStrategy, LoopNodeStrategy
from app.core.nodes.output_node import OutputNodeStrategy
from app.core.nodes.passthrough_node import PassthroughNodeStrategy

_NODE_REGISTRY: dict[str, type[NodeStrategy]] = {
    "input": InputNodeStrategy,
    "llm": LLMNodeStrategy,
    "if_else": IfElseNodeStrategy,
    "loop": LoopNodeStrategy,
    "output": OutputNodeStrategy,
    "passthrough": PassthroughNodeStrategy,
}

_LLM_SUBTYPE_STRATEGY_KEYS: dict[str, str] = {
    "PASSTHROUGH": "passthrough",
}


def infer_runtime_type(node_def) -> str:
    """runtime_type이 없을 때 role/type으로 추론 (transition 기간 fallback).

    가이드 섹션 4.2 참조.
    """
    role = getattr(node_def, "role", None)
    if role == "start":
        return "input"
    if role == "end":
        return "output"

    node_type = (getattr(node_def, "type", "") or "").upper()
    if node_type == "LOOP":
        return "loop"
    if node_type in ("CONDITION_BRANCH", "IF_ELSE"):
        return "if_else"

    return "llm"


def _runtime_config_value(node_def, key: str) -> str:
    runtime_config = getattr(node_def, "runtime_config", None)
    value = None
    if isinstance(runtime_config, dict):
        value = runtime_config.get(key)
    elif runtime_config is not None:
        value = getattr(runtime_config, key, None)

    if value in (None, "") and key == "node_type":
        value = getattr(node_def, "type", "")

    return str(value or "").upper()


def resolve_strategy_key(node_def) -> str:
    """NodeDefinition에서 실제 실행 전략 키를 결정합니다."""
    runtime_type = getattr(node_def, "runtime_type", None)
    if not runtime_type:
        runtime_type = infer_runtime_type(node_def)

    if runtime_type == "llm":
        node_type = _runtime_config_value(node_def, "node_type")
        return _LLM_SUBTYPE_STRATEGY_KEYS.get(node_type, "llm")

    return runtime_type


class NodeFactory:
    """Factory 패턴 - runtime_type 문자열로부터 Strategy 인스턴스 생성.

    v2: runtime_type을 PRIMARY 키로 사용하고,
    없으면 role + type에서 추론 (transition fallback).
    """

    @staticmethod
    def create(node_type: str, config: dict | None = None) -> NodeStrategy:
        node_class = _NODE_REGISTRY.get(node_type)
        if node_class is None:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"알 수 없는 노드 타입입니다: {node_type}",
            )
        return node_class(config)

    @staticmethod
    def create_from_node_def(node_def) -> NodeStrategy:
        """NodeDefinition으로부터 runtime_type 기반 전략 생성."""
        runtime_type = resolve_strategy_key(node_def)

        node_class = _NODE_REGISTRY.get(runtime_type)
        if node_class is None:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"알 수 없는 런타임 타입입니다: {runtime_type}",
            )
        return node_class(getattr(node_def, "config", None))

    @staticmethod
    def register(node_type: str, node_class: type[NodeStrategy]) -> None:
        _NODE_REGISTRY[node_type] = node_class
