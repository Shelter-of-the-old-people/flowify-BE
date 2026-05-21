"""Logic 노드 — IfElse 분기 및 Loop 반복 처리.

참조: FASTAPI_IMPLEMENTATION_GUIDE.md 섹션 7.2, 7.3
"""

import json
from pathlib import PurePosixPath
import time
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy

MAX_LOOP_ITERATIONS = 1000
DEFAULT_TIMEOUT_SECONDS = 300
FILE_TYPE_BRANCH = "file_type"
CONTENT_CLASSIFICATION_BRANCH = "content_classification"
FALLBACK_BRANCH_KEY = "other"


class IfElseNodeStrategy(NodeStrategy):
    """If/Else 조건 분기 노드.

    runtime_config의 condition을 평가하여 branch: "true"/"false"를 반환.
    canonical payload를 그대로 전달하면서 branch 정보를 추가.
    """

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_config = node.get("runtime_config") or {}
        if self._is_file_type_branch(runtime_config):
            return self._execute_file_type_branch(node, runtime_config, input_data)
        if self._is_content_classification_branch(runtime_config):
            return self._execute_content_classification_branch(node, runtime_config, input_data)

        return self._execute_boolean_branch(runtime_config, input_data)

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        if self._is_file_type_branch(runtime_config):
            fallback_branch = runtime_config.get("fallback_branch") or {}
            return bool(runtime_config.get("branch_rules")) or bool(fallback_branch.get("key"))
        if self._is_content_classification_branch(runtime_config):
            fallback_branch = runtime_config.get("fallback_branch") or {}
            return bool(runtime_config.get("branch_rules")) or bool(fallback_branch.get("key"))
        return bool(runtime_config.get("condition_field") or self.config.get("condition_field"))

    @staticmethod
    def _is_file_type_branch(runtime_config: dict[str, Any]) -> bool:
        return runtime_config.get("branch_type") == FILE_TYPE_BRANCH

    @staticmethod
    def _is_content_classification_branch(runtime_config: dict[str, Any]) -> bool:
        return runtime_config.get("branch_type") == CONTENT_CLASSIFICATION_BRANCH

    def _execute_boolean_branch(
        self,
        runtime_config: dict[str, Any],
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        condition_field = runtime_config.get("condition_field") or self.config.get(
            "condition_field", ""
        )
        expected_value = runtime_config.get("expected_value") or self.config.get("expected_value")

        # canonical payload에서 조건 평가
        actual_value = None
        if input_data:
            actual_value = input_data.get(condition_field)

        branch = "true" if actual_value == expected_value else "false"

        # canonical payload에 branch 정보 추가하여 반환
        result = dict(input_data) if input_data else {}
        result["branch"] = branch
        return result

    def _execute_file_type_branch(
        self,
        node: dict[str, Any],
        runtime_config: dict[str, Any],
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not input_data or input_data.get("type") != "FILE_LIST":
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="File type branch requires FILE_LIST input.",
                context={"node_id": node.get("id")},
            )

        items = input_data.get("items", [])
        if not isinstance(items, list):
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="File type branch requires list items.",
                context={"node_id": node.get("id")},
            )

        branch_rules = self._to_branch_rules(runtime_config.get("branch_rules"))
        fallback_key = self._fallback_branch_key(runtime_config)
        branch_outputs = self._empty_branch_outputs(branch_rules, fallback_key)

        for item in items:
            if not isinstance(item, dict):
                branch_outputs[fallback_key]["items"].append(item)
                continue

            branch_key = self._resolve_file_type_branch_key(
                item,
                branch_rules,
                fallback_key,
            )
            branch_outputs[branch_key]["items"].append(item)

        result = dict(input_data)
        result["branch"] = "multi"
        result["branch_outputs"] = branch_outputs
        result["branch_counts"] = {
            key: len(payload["items"]) for key, payload in branch_outputs.items()
        }
        return result

    def _execute_content_classification_branch(
        self,
        node: dict[str, Any],
        runtime_config: dict[str, Any],
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not input_data:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Content classification branch requires input data.",
                context={"node_id": node.get("id")},
            )

        branch_rules = self._to_branch_rules(runtime_config.get("branch_rules"))
        fallback_key = self._fallback_branch_key(runtime_config)
        branch_outputs = self._empty_content_branch_outputs(branch_rules, fallback_key)
        branch_key = self._resolve_content_branch_key(input_data, branch_rules, fallback_key)

        if branch_key not in branch_outputs:
            branch_outputs[branch_key] = self._empty_content_branch_payload()

        content = self._extract_content_text(input_data)
        branch_outputs[branch_key]["items"].append(
            self._to_content_branch_item(input_data, content)
        )
        branch_outputs[branch_key]["content"] = content

        result = dict(input_data)
        result["type"] = "TEXT"
        result["content"] = content
        result["branch"] = "multi"
        result["branch_type"] = CONTENT_CLASSIFICATION_BRANCH
        result["branch_outputs"] = branch_outputs
        result["branch_counts"] = {
            key: len(payload["items"]) for key, payload in branch_outputs.items()
        }
        result["branch_edge_order"] = list(branch_outputs.keys())
        return result

    @staticmethod
    def _to_branch_rules(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [rule for rule in value if isinstance(rule, dict)]

    @staticmethod
    def _fallback_branch_key(runtime_config: dict[str, Any]) -> str:
        fallback_branch = runtime_config.get("fallback_branch") or {}
        if isinstance(fallback_branch, dict):
            key = str(fallback_branch.get("key") or "").strip()
            if key:
                return key
        return FALLBACK_BRANCH_KEY

    @staticmethod
    def _empty_branch_outputs(
        branch_rules: list[dict[str, Any]],
        fallback_key: str,
    ) -> dict[str, dict[str, Any]]:
        branch_outputs: dict[str, dict[str, Any]] = {}
        for rule in branch_rules:
            key = str(rule.get("key") or "").strip()
            if key:
                branch_outputs[key] = {"type": "FILE_LIST", "items": []}

        branch_outputs.setdefault(fallback_key, {"type": "FILE_LIST", "items": []})
        return branch_outputs

    @staticmethod
    def _empty_content_branch_outputs(
        branch_rules: list[dict[str, Any]],
        fallback_key: str,
    ) -> dict[str, dict[str, Any]]:
        branch_outputs: dict[str, dict[str, Any]] = {}
        for rule in branch_rules:
            key = str(rule.get("key") or "").strip()
            if key:
                branch_outputs[key] = IfElseNodeStrategy._empty_content_branch_payload()

        branch_outputs.setdefault(fallback_key, IfElseNodeStrategy._empty_content_branch_payload())
        return branch_outputs

    @staticmethod
    def _empty_content_branch_payload() -> dict[str, Any]:
        return {"type": "TEXT", "content": "", "items": []}

    @classmethod
    def _resolve_content_branch_key(
        cls,
        input_data: dict[str, Any],
        branch_rules: list[dict[str, Any]],
        fallback_key: str,
    ) -> str:
        explicit_value = cls._extract_explicit_content_branch_value(input_data)
        explicit_key = cls._match_content_branch_value(explicit_value, branch_rules, fallback_key)
        if explicit_key:
            return explicit_key

        content = cls._extract_content_text(input_data).lower()
        for rule in branch_rules:
            key = str(rule.get("key") or "").strip()
            if not key:
                continue

            candidates = [key, str(rule.get("label") or "")]
            matcher = rule.get("matcher")
            if isinstance(matcher, dict):
                candidates.extend(cls._to_string_list(matcher.get("keywords")))

            if any(candidate and candidate.lower() in content for candidate in candidates):
                return key

        return fallback_key

    @classmethod
    def _extract_explicit_content_branch_value(cls, input_data: dict[str, Any]) -> Any:
        for key in (
            "branch_key",
            "branchKey",
            "classification",
            "category",
            "label",
            "branch",
        ):
            value = input_data.get(key)
            if value not in (None, ""):
                return value

        data = input_data.get("data")
        if isinstance(data, dict):
            return cls._extract_explicit_content_branch_value(data)

        return None

    @classmethod
    def _match_content_branch_value(
        cls,
        value: Any,
        branch_rules: list[dict[str, Any]],
        fallback_key: str,
    ) -> str | None:
        normalized = cls._normalize_branch_key(value)
        if not normalized:
            return None

        if normalized == cls._normalize_branch_key(fallback_key):
            return fallback_key

        for rule in branch_rules:
            key = str(rule.get("key") or "").strip()
            label = str(rule.get("label") or "").strip()
            if normalized in {
                cls._normalize_branch_key(key),
                cls._normalize_branch_key(label),
            }:
                return key

        return None

    @staticmethod
    def _normalize_branch_key(value: Any) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    @classmethod
    def _extract_content_text(cls, input_data: dict[str, Any]) -> str:
        for key in ("content", "text", "summary", "title", "body", "bodyPreview"):
            value = input_data.get(key)
            if value not in (None, ""):
                return str(value)

        article = input_data.get("article")
        if isinstance(article, dict):
            article_text = cls._extract_content_text(article)
            if article_text:
                return article_text

        data = input_data.get("data")
        if isinstance(data, dict):
            data_text = cls._extract_content_text(data)
            if data_text:
                return data_text
        if data not in (None, ""):
            return json.dumps(data, ensure_ascii=False, sort_keys=True)

        return json.dumps(input_data, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _to_content_branch_item(input_data: dict[str, Any], content: str) -> dict[str, Any]:
        item = dict(input_data)
        for key in ("branch_outputs", "branch_counts", "branch_edge_order"):
            item.pop(key, None)
        item["type"] = "TEXT"
        item["content"] = content
        return item

    @classmethod
    def _resolve_file_type_branch_key(
        cls,
        item: dict[str, Any],
        branch_rules: list[dict[str, Any]],
        fallback_key: str,
    ) -> str:
        for rule in branch_rules:
            key = str(rule.get("key") or "").strip()
            matcher = rule.get("matcher")
            if key and isinstance(matcher, dict) and cls._matches_file_type_rule(item, matcher):
                return key
        return fallback_key

    @classmethod
    def _matches_file_type_rule(cls, item: dict[str, Any], matcher: dict[str, Any]) -> bool:
        mime_type = str(item.get("mime_type") or item.get("mimeType") or "").lower()
        filename = str(item.get("filename") or item.get("name") or "")
        extension = cls._file_extension(filename)

        mime_types = cls._to_string_set(matcher.get("mime_types"))
        if mime_type and mime_type in mime_types:
            return True

        mime_prefixes = cls._to_string_list(matcher.get("mime_prefixes"))
        if mime_type and any(mime_type.startswith(prefix) for prefix in mime_prefixes):
            return True

        extensions = cls._to_string_set(matcher.get("extensions"))
        return bool(extension and extension in extensions)

    @staticmethod
    def _file_extension(filename: str) -> str:
        normalized = filename.replace("\\", "/")
        suffix = PurePosixPath(normalized).suffix
        return suffix[1:].lower() if suffix.startswith(".") else ""

    @staticmethod
    def _to_string_set(value: Any) -> set[str]:
        return set(IfElseNodeStrategy._to_string_list(value))

    @staticmethod
    def _to_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip().lower() for item in value if str(item).strip()]


class LoopNodeStrategy(NodeStrategy):
    """Loop 반복 노드 (무한 루프 방지 내장).

    리스트형 canonical payload (FILE_LIST, EMAIL_LIST 등)의 items를 순회.
    """

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_config = node.get("runtime_config") or {}
        max_iterations = min(
            runtime_config.get("max_iterations")
            or self.config.get("max_iterations", MAX_LOOP_ITERATIONS),
            MAX_LOOP_ITERATIONS,
        )
        transform_field = runtime_config.get("transform_field") or self.config.get(
            "transform_field"
        )

        # canonical payload에서 items 추출
        items = []
        if input_data:
            data_type = input_data.get("type", "")
            if data_type in ("FILE_LIST", "EMAIL_LIST", "SCHEDULE_DATA"):
                items = input_data.get("items", [])
            elif data_type == "SPREADSHEET_DATA":
                items = input_data.get("rows", [])
            else:
                # fallback: items_field 기반
                items_field = self.config.get("items_field", "items")
                items = input_data.get(items_field, [])

        results = []
        start_time = time.monotonic()
        for i, item in enumerate(items):
            if i >= max_iterations:
                break
            if time.monotonic() - start_time > DEFAULT_TIMEOUT_SECONDS:
                break
            if transform_field and isinstance(item, dict):
                results.append(item.get(transform_field, item))
            else:
                results.append(item)

        return {
            "type": input_data.get("type", "TEXT") if input_data else "TEXT",
            "items": results,
            "loop_results": results,
            "iterations": len(results),
        }

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        return bool(runtime_config.get("node_type") or self.config.get("items_field"))
