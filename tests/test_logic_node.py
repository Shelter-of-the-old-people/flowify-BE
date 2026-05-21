import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.logic_node import IfElseNodeStrategy


def _file_type_runtime_config(
    branch_rules: list[dict] | None = None,
    fallback_key: str = "other",
) -> dict:
    return {
        "branch_type": "file_type",
        "branch_rules": branch_rules if branch_rules is not None else _file_type_branch_rules(),
        "fallback_branch": {"key": fallback_key, "label": "Other"},
    }


def _file_type_branch_rules() -> list[dict]:
    return [
        {
            "key": "pdf",
            "label": "PDF",
            "matcher": {
                "type": "file_type",
                "extensions": ["pdf"],
                "mime_types": ["application/pdf"],
                "mime_prefixes": [],
            },
        },
        {
            "key": "image",
            "label": "Image",
            "matcher": {
                "type": "file_type",
                "extensions": ["jpg", "jpeg", "png"],
                "mime_types": [],
                "mime_prefixes": ["image/"],
            },
        },
    ]


def _content_branch_runtime_config() -> dict:
    return {
        "branch_type": "content_classification",
        "branch_rules": [
            {
                "key": "important",
                "label": "Important",
                "matcher": {
                    "type": "content_classification",
                    "keywords": ["urgent", "critical", "important"],
                },
            },
            {
                "key": "reference",
                "label": "Reference",
                "matcher": {
                    "type": "content_classification",
                    "keywords": ["reference", "note"],
                },
            },
        ],
        "fallback_branch": {"key": "other", "label": "Other"},
    }


class TestIfElseNodeStrategy:
    @pytest.mark.asyncio
    async def test_boolean_branch_true(self):
        strategy = IfElseNodeStrategy()

        result = await strategy.execute(
            node={
                "runtime_config": {
                    "condition_field": "status",
                    "expected_value": "ready",
                }
            },
            input_data={"type": "TEXT", "status": "ready"},
            service_tokens={},
        )

        assert result["branch"] == "true"

    @pytest.mark.asyncio
    async def test_boolean_branch_false(self):
        strategy = IfElseNodeStrategy()

        result = await strategy.execute(
            node={
                "runtime_config": {
                    "condition_field": "status",
                    "expected_value": "ready",
                }
            },
            input_data={"type": "TEXT", "status": "pending"},
            service_tokens={},
        )

        assert result["branch"] == "false"

    @pytest.mark.asyncio
    async def test_file_type_branch_splits_items_by_rule(self):
        strategy = IfElseNodeStrategy()
        input_data = {
            "type": "FILE_LIST",
            "items": [
                {"filename": "lecture.pdf", "mime_type": "application/pdf"},
                {"filename": "photo.png", "mime_type": "image/png"},
                {"filename": "memo.bin", "mime_type": "application/octet-stream"},
            ],
        }

        result = await strategy.execute(
            node={"id": "branch_1", "runtime_config": _file_type_runtime_config()},
            input_data=input_data,
            service_tokens={},
        )

        assert result["branch"] == "multi"
        assert result["branch_outputs"]["pdf"]["items"] == [input_data["items"][0]]
        assert result["branch_outputs"]["image"]["items"] == [input_data["items"][1]]
        assert result["branch_outputs"]["other"]["items"] == [input_data["items"][2]]
        assert result["branch_counts"] == {"pdf": 1, "image": 1, "other": 1}

    @pytest.mark.asyncio
    async def test_file_type_branch_accepts_other_only_selection(self):
        strategy = IfElseNodeStrategy()
        input_data = {
            "type": "FILE_LIST",
            "items": [
                {"filename": "lecture.pdf", "mime_type": "application/pdf"},
                {"filename": "photo.png", "mime_type": "image/png"},
            ],
        }

        result = await strategy.execute(
            node={
                "id": "branch_1",
                "runtime_config": _file_type_runtime_config(branch_rules=[]),
            },
            input_data=input_data,
            service_tokens={},
        )

        assert list(result["branch_outputs"].keys()) == ["other"]
        assert result["branch_outputs"]["other"]["items"] == input_data["items"]
        assert result["branch_counts"] == {"other": 2}

    @pytest.mark.asyncio
    async def test_file_type_branch_requires_file_list_input(self):
        strategy = IfElseNodeStrategy()

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(
                node={"id": "branch_1", "runtime_config": _file_type_runtime_config()},
                input_data={"type": "TEXT", "content": "hello"},
                service_tokens={},
            )

        assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_content_branch_routes_text_by_keyword(self):
        strategy = IfElseNodeStrategy()
        input_data = {
            "type": "TEXT",
            "content": "Urgent article summary for today's workflow.",
        }

        result = await strategy.execute(
            node={"id": "branch_1", "runtime_config": _content_branch_runtime_config()},
            input_data=input_data,
            service_tokens={},
        )

        assert result["type"] == "TEXT"
        assert result["branch"] == "multi"
        assert result["branch_type"] == "content_classification"
        assert result["branch_outputs"]["important"]["content"] == input_data["content"]
        assert result["branch_outputs"]["important"]["items"][0]["content"] == input_data["content"]
        assert result["branch_outputs"]["reference"]["items"] == []
        assert result["branch_counts"] == {"important": 1, "reference": 0, "other": 0}
        assert result["branch_edge_order"] == ["important", "reference", "other"]

    @pytest.mark.asyncio
    async def test_content_branch_prefers_explicit_classification(self):
        strategy = IfElseNodeStrategy()
        input_data = {
            "type": "TEXT",
            "classification": "reference",
            "content": "This text does not need keyword matching.",
        }

        result = await strategy.execute(
            node={"id": "branch_1", "runtime_config": _content_branch_runtime_config()},
            input_data=input_data,
            service_tokens={},
        )

        assert result["branch_outputs"]["reference"]["items"][0]["classification"] == "reference"
        assert result["branch_counts"] == {"important": 0, "reference": 1, "other": 0}

    @pytest.mark.asyncio
    async def test_content_branch_falls_back_when_no_rule_matches(self):
        strategy = IfElseNodeStrategy()

        result = await strategy.execute(
            node={"id": "branch_1", "runtime_config": _content_branch_runtime_config()},
            input_data={"type": "TEXT", "content": "A neutral update."},
            service_tokens={},
        )

        assert result["branch_outputs"]["other"]["items"][0]["content"] == "A neutral update."
        assert result["branch_counts"] == {"important": 0, "reference": 0, "other": 1}

    def test_file_type_branch_validate_accepts_fallback_only(self):
        strategy = IfElseNodeStrategy()

        assert strategy.validate(
            {
                "runtime_config": _file_type_runtime_config(
                    branch_rules=[],
                    fallback_key="other",
                )
            }
        )

    def test_content_branch_validate_accepts_rules(self):
        strategy = IfElseNodeStrategy()

        assert strategy.validate({"runtime_config": _content_branch_runtime_config()})
