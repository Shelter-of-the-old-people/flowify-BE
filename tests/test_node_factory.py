from unittest.mock import patch

from app.core.nodes.data_filter_node import DataFilterNodeStrategy
from app.core.nodes.factory import NodeFactory, resolve_strategy_key
from app.core.nodes.integration_node import IntegrationNodeStrategy
from app.core.nodes.input_node import InputNodeStrategy
from app.core.nodes.llm_node import LLMNodeStrategy
from app.core.nodes.passthrough_node import PassthroughNodeStrategy
from app.models.workflow import NodeDefinition


def test_factory_routes_passthrough_subtype_to_passthrough_strategy():
    node_def = NodeDefinition(
        id="node_pass",
        type="PASSTHROUGH",
        config={},
        runtime_type="llm",
        runtime_config={"node_type": "PASSTHROUGH"},
    )

    strategy = NodeFactory.create_from_node_def(node_def)

    assert isinstance(strategy, PassthroughNodeStrategy)
    assert resolve_strategy_key(node_def) == "passthrough"


def test_factory_routes_passthrough_type_fallback_to_passthrough_strategy():
    node_def = NodeDefinition(id="node_pass", type="PASSTHROUGH", config={})

    strategy = NodeFactory.create_from_node_def(node_def)

    assert isinstance(strategy, PassthroughNodeStrategy)
    assert resolve_strategy_key(node_def) == "passthrough"


def test_factory_keeps_ai_subtype_on_llm_strategy():
    node_def = NodeDefinition(
        id="node_ai",
        type="AI",
        config={},
        runtime_type="llm",
        runtime_config={"node_type": "AI"},
    )

    with patch("app.core.nodes.llm_node.LLMService"):
        strategy = NodeFactory.create_from_node_def(node_def)

    assert isinstance(strategy, LLMNodeStrategy)
    assert resolve_strategy_key(node_def) == "llm"


def test_factory_routes_data_filter_subtype_to_data_filter_strategy():
    node_def = NodeDefinition(
        id="node_filter",
        type="DATA_FILTER",
        config={},
        runtime_type="llm",
        runtime_config={"node_type": "DATA_FILTER"},
    )

    strategy = NodeFactory.create_from_node_def(node_def)

    assert isinstance(strategy, DataFilterNodeStrategy)
    assert resolve_strategy_key(node_def) == "data_filter"


def test_factory_keeps_runtime_type_primary_for_non_llm_nodes():
    node_def = NodeDefinition(
        id="node_input",
        type="PASSTHROUGH",
        config={},
        role="start",
        runtime_type="input",
        runtime_config={"node_type": "PASSTHROUGH"},
    )

    strategy = NodeFactory.create_from_node_def(node_def)

    assert isinstance(strategy, InputNodeStrategy)
    assert resolve_strategy_key(node_def) == "input"


def test_factory_routes_integration_runtime_type_to_integration_strategy():
    node_def = NodeDefinition(
        id="node_sheets_mid",
        type="google_sheets",
        config={"service": "google_sheets", "action": "search_text"},
        runtime_type="integration",
        runtime_action={"service": "google_sheets", "action": "search_text"},
    )

    strategy = NodeFactory.create_from_node_def(node_def)

    assert isinstance(strategy, IntegrationNodeStrategy)
    assert resolve_strategy_key(node_def) == "integration"
