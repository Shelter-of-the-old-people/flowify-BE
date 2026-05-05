import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.passthrough_node import PassthroughNodeStrategy


async def test_passthrough_node_returns_input_payload_copy():
    strategy = PassthroughNodeStrategy()
    input_data = {
        "type": "SINGLE_FILE",
        "filename": "report.txt",
        "metadata": {"tags": ["a", "b"]},
    }

    result = await strategy.execute(
        node={"id": "node_pass"},
        input_data=input_data,
        service_tokens={},
    )

    assert result == input_data
    assert result is not input_data
    result["metadata"]["tags"].append("c")
    assert input_data["metadata"]["tags"] == ["a", "b"]


async def test_passthrough_node_without_input_raises_invalid_request():
    strategy = PassthroughNodeStrategy()

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            node={"id": "node_pass"},
            input_data=None,
            service_tokens={},
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.context == {"node_id": "node_pass"}


def test_passthrough_node_validate_always_true():
    strategy = PassthroughNodeStrategy()

    assert strategy.validate({"id": "node_pass"}) is True
