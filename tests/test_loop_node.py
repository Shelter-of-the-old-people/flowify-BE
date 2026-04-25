"""LoopNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
canonical payload 타입별 items 추출 (FILE_LIST→items, SPREADSHEET_DATA→rows).
conftest.py의 service_tokens fixture 사용 가능.
"""

import pytest

from app.core.nodes.logic_node import LoopNodeStrategy


@pytest.mark.asyncio
async def test_file_list_iteration() -> None:
    """FILE_LIST payload의 items를 순회해 반복 횟수를 계산합니다."""
    strategy = LoopNodeStrategy({})
    node = {"runtime_config": {"max_iterations": 10}}
    input_data = {
        "type": "FILE_LIST",
        "items": [{"filename": "a.txt"}, {"filename": "b.txt"}],
    }

    result = await strategy.execute(node, input_data, {})

    assert result == {
        "type": "FILE_LIST",
        "items": [{"filename": "a.txt"}, {"filename": "b.txt"}],
        "loop_results": [{"filename": "a.txt"}, {"filename": "b.txt"}],
        "iterations": 2,
    }


@pytest.mark.asyncio
async def test_spreadsheet_rows_iteration() -> None:
    """SPREADSHEET_DATA payload는 rows를 기준으로 반복합니다."""
    strategy = LoopNodeStrategy({})
    node = {"runtime_config": {}}
    input_data = {
        "type": "SPREADSHEET_DATA",
        "headers": ["name", "age"],
        "rows": [["Alice", 30], ["Bob", 25]],
    }

    result = await strategy.execute(node, input_data, {})

    assert result["type"] == "SPREADSHEET_DATA"
    assert result["items"] == [["Alice", 30], ["Bob", 25]]
    assert result["loop_results"] == [["Alice", 30], ["Bob", 25]]
    assert result["iterations"] == 2


@pytest.mark.asyncio
async def test_max_iterations_limit() -> None:
    """max_iterations를 넘는 항목은 처리하지 않습니다."""
    strategy = LoopNodeStrategy({})
    node = {"runtime_config": {"max_iterations": 2}}
    input_data = {
        "type": "FILE_LIST",
        "items": [{"f": 1}, {"f": 2}, {"f": 3}, {"f": 4}],
    }

    result = await strategy.execute(node, input_data, {})

    assert result["items"] == [{"f": 1}, {"f": 2}]
    assert result["loop_results"] == [{"f": 1}, {"f": 2}]
    assert result["iterations"] == 2


@pytest.mark.asyncio
async def test_empty_input_returns_zero_iterations() -> None:
    """입력이 없으면 빈 결과와 0회 반복을 반환합니다."""
    strategy = LoopNodeStrategy({})

    result = await strategy.execute({"runtime_config": {}}, None, {})

    assert result == {
        "type": "TEXT",
        "items": [],
        "loop_results": [],
        "iterations": 0,
    }


@pytest.mark.asyncio
async def test_transform_field_extracts_values() -> None:
    """transform_field가 있으면 dict item에서 해당 값만 추출합니다."""
    strategy = LoopNodeStrategy({})
    node = {"runtime_config": {"transform_field": "name"}}
    input_data = {
        "type": "EMAIL_LIST",
        "items": [{"name": "Alice"}, {"name": "Bob"}],
    }

    result = await strategy.execute(node, input_data, {})

    assert result["items"] == ["Alice", "Bob"]
    assert result["loop_results"] == ["Alice", "Bob"]
    assert result["iterations"] == 2


def test_validate() -> None:
    """runtime_config 또는 fallback config 기준으로 validate를 판정합니다."""
    strategy = LoopNodeStrategy({})

    assert strategy.validate({"runtime_config": {"node_type": "loop"}}) is True
    assert LoopNodeStrategy({"items_field": "custom_items"}).validate({}) is True
    assert strategy.validate({}) is False
