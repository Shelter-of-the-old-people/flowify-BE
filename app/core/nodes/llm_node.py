"""AI 처리 노드의 LLM 실행 전략."""

import json
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.document_content import (
    CONTENT_STATUS_EMPTY,
    CONTENT_STATUS_FAILED,
    CONTENT_STATUS_NOT_REQUESTED,
    CONTENT_STATUS_TOO_LARGE,
    CONTENT_STATUS_UNSUPPORTED,
    apply_extraction_to_file_payload,
)
from app.core.nodes.base import NodeStrategy
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.llm_service import LLMService

PROMPT_REQUIRED_ACTIONS = frozenset({"process", "extract", "translate", "custom"})
PROMPT_OPTIONAL_ACTIONS = frozenset({"summarize", "classify"})
CONTENT_DEPENDENT_ACTIONS = frozenset(
    {
        "summarize",
        "extract",
        "extract_info",
        "translate",
        "classify_by_content",
        "describe_image",
        "ocr",
        "ai_summarize",
        "ai_analyze",
    }
)
SUPPORTED_ACTIONS = PROMPT_REQUIRED_ACTIONS | PROMPT_OPTIONAL_ACTIONS | CONTENT_DEPENDENT_ACTIONS
CONTENT_FAILURE_STATUSES = frozenset(
    {
        CONTENT_STATUS_UNSUPPORTED,
        CONTENT_STATUS_TOO_LARGE,
        CONTENT_STATUS_FAILED,
        CONTENT_STATUS_EMPTY,
    }
)
DEFAULT_ACTION_PROMPTS = {
    "extract_info": "문서 본문에서 중요한 정보와 결정 사항을 항목별로 추출하세요.",
    "ai_analyze": "문서 본문을 분석하고 핵심 인사이트와 후속 조치를 정리하세요.",
    "describe_image": "입력된 이미지 설명 또는 OCR 텍스트를 바탕으로 내용을 설명하세요.",
    "ocr": "입력에서 읽힌 텍스트를 정리하고 주요 내용을 요약하세요.",
}


GITHUB_PR_DEFAULT_TEXT_PROMPT = """You are preparing a GitHub pull request digest for a teammate.
Write the result in Korean as plain text only.
Do not use markdown headings, bold markers like **, numbered markdown lists, code fences, or emojis.
Use short Korean section labels and '-' bullets only.

Follow this structure:
기본 정보
- 저장소: ...
- PR 번호: ...
- 작성자: ...
- 브랜치: base -> head
- 링크: ...

한 줄 요약
- 이 PR이 무엇을 바꾸는지 한 문장으로 요약한다.

주요 변경점
- 최대 3개 bullet로 정리한다.
- 파일명을 길게 나열하지 말고, 무엇이 바뀌었는지 중심으로 쓴다.

확인 포인트
- 최대 3개 bullet로 정리한다.
- 리뷰 시 확인할 위험, 호환성, 테스트 포인트가 없으면 이 섹션은 생략한다.

Rules:
- Keep it concise, factual, and easy to scan.
- Use only information present in the provided PR context.
- Do not speculate or invent missing details.
- Prefer impact-oriented wording over copying the PR body.
- Keep URLs as raw text.
"""



class LLMNodeStrategy(NodeStrategy):
    """설정된 LLM 작업을 실행하고 canonical payload를 반환합니다."""

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._llm_service = LLMService()

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        output_data_type = runtime_config.get("output_data_type", "TEXT")
        explicit_prompt = self._resolve_explicit_prompt(runtime_config)
        prompt = self._resolve_prompt(runtime_config)
        github_default_prompt = self._resolve_github_default_prompt(
            input_data,
            action,
            output_data_type,
            explicit_prompt,
        )
        if github_default_prompt:
            prompt = github_default_prompt

        self._ensure_executable_prompt(node, action, output_data_type, prompt)

        requires_content = self._requires_content(runtime_config, action)
        text = await self._resolve_llm_input_text(
            input_data,
            service_tokens,
            requires_content=requires_content,
            content_action=action,
        )

        if output_data_type == "SPREADSHEET_DATA":
            result = await self._llm_service.process_json(prompt, context=text)
            return self._to_spreadsheet_payload(result)

        if action in {"summarize", "ai_summarize"}:
            if github_default_prompt:
                result = await self._llm_service.process(prompt, context=text)
            else:
                result = await self._llm_service.summarize(text)
        elif action in {"classify", "classify_by_content"}:
            categories = runtime_config.get("categories") or self.config.get("categories")
            result = await self._llm_service.classify(text, categories)
        else:  # process, extract, translate, custom
            result = await self._llm_service.process(prompt, context=text)

        return self._build_output_payload(output_data_type, result, input_data)

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_config = node.get("runtime_config") or {}
        action = runtime_config.get("action") or self.config.get("action", "process")
        output_data_type = runtime_config.get("output_data_type", "TEXT")
        prompt = self._resolve_prompt(runtime_config)
        if output_data_type == "SPREADSHEET_DATA":
            return bool(prompt)
        if action in PROMPT_REQUIRED_ACTIONS:
            return bool(prompt)
        return action in PROMPT_OPTIONAL_ACTIONS or action in CONTENT_DEPENDENT_ACTIONS

    def _resolve_explicit_prompt(self, runtime_config: dict[str, Any]) -> str:
        prompt = runtime_config.get("prompt")
        if prompt is None:
            prompt = self.config.get("prompt", "")
        return str(prompt).strip()

    def _resolve_prompt(self, runtime_config: dict[str, Any]) -> str:
        """runtime_config? fallback config?? ????? ?????."""
        prompt = self._resolve_explicit_prompt(runtime_config)
        if prompt:
            return prompt
        action = runtime_config.get("action") or self.config.get("action", "")
        return DEFAULT_ACTION_PROMPTS.get(str(action), "")

    @staticmethod
    def _resolve_github_default_prompt(
        input_data: dict[str, Any] | None,
        action: str,
        output_data_type: str,
        explicit_prompt: str,
    ) -> str:
        if explicit_prompt:
            return ""
        if output_data_type != "TEXT":
            return ""
        if action not in {"process", "summarize", "ai_summarize", "ai_analyze"}:
            return ""
        if not isinstance(input_data, dict):
            return ""
        if input_data.get("type") != "API_RESPONSE":
            return ""
        if input_data.get("source_service") != "github":
            return ""
        if input_data.get("event") != "new_pr":
            return ""
        return GITHUB_PR_DEFAULT_TEXT_PROMPT

    def _requires_content(self, runtime_config: dict[str, Any], action: str) -> bool:
        explicit = runtime_config.get("requires_content")
        if explicit is None:
            explicit = runtime_config.get("requiresContent")
        if explicit is None:
            explicit = self.config.get("requires_content", self.config.get("requiresContent"))
        if explicit is not None:
            return self._coerce_bool(explicit)
        return action in CONTENT_DEPENDENT_ACTIONS

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    async def _resolve_llm_input_text(
        self,
        input_data: dict | None,
        service_tokens: dict[str, str],
        requires_content: bool = False,
        content_action: str | None = None,
    ) -> str:
        if not input_data:
            return ""

        if input_data.get("type") == "SINGLE_FILE":
            return await self._resolve_single_file_text(
                input_data,
                service_tokens,
                requires_content=requires_content,
                content_action=content_action,
            )

        if input_data.get("type") == "FILE_LIST":
            return await self._resolve_file_list_text(
                input_data,
                service_tokens,
                requires_content=requires_content,
                content_action=content_action,
            )

        return self._extract_text_from_canonical(input_data)

    async def _resolve_single_file_text(
        self,
        input_data: dict[str, Any],
        service_tokens: dict[str, str],
        requires_content: bool = False,
        content_action: str | None = None,
    ) -> str:
        content = input_data.get("content")
        if content:
            return self._format_single_file_text(input_data, str(content))

        extracted_text = input_data.get("extracted_text")
        if extracted_text:
            return self._format_single_file_text(input_data, str(extracted_text))

        content_status = input_data.get("content_status")
        if requires_content and content_status in CONTENT_FAILURE_STATUSES:
            self._raise_content_unavailable(input_data, str(content_status))

        if (
            input_data.get("source_service") == "google_drive"
            and input_data.get("file_id")
            and content_status in (None, CONTENT_STATUS_NOT_REQUESTED)
        ):
            token = service_tokens.get("google_drive", "")
            if token:
                svc = GoogleDriveService()
                extraction_kwargs = {}
                if content_action in {"ocr", "describe_image", "ai_analyze"}:
                    extraction_kwargs["extraction_action"] = content_action
                extraction = await svc.extract_file_text(
                    token,
                    input_data["file_id"],
                    input_data.get("mime_type", ""),
                    input_data.get("filename", ""),
                    input_data.get("size"),
                    **extraction_kwargs,
                )
                apply_extraction_to_file_payload(input_data, extraction)
                if input_data.get("content"):
                    return self._format_single_file_text(input_data, str(input_data["content"]))
                if requires_content:
                    self._raise_content_unavailable(
                        input_data,
                        str(input_data.get("content_status") or CONTENT_STATUS_FAILED),
                    )
                return self._format_single_file_text(
                    input_data,
                    self._format_extraction_failure(extraction),
                )

        if (
            (input_data.get("source_service") == "gmail" or input_data.get("source") == "gmail")
            and (input_data.get("message_id") or input_data.get("messageId"))
            and (input_data.get("attachment_id") or input_data.get("attachmentId"))
            and content_status in (None, CONTENT_STATUS_NOT_REQUESTED)
        ):
            token = service_tokens.get("gmail", "")
            if token:
                extraction_kwargs = {}
                if content_action in {"ocr", "describe_image", "ai_analyze"}:
                    extraction_kwargs["extraction_action"] = content_action
                svc = GmailService()
                extraction = await svc.extract_attachment_text(
                    token,
                    message_id=input_data.get("message_id") or input_data.get("messageId"),
                    attachment_id=input_data.get("attachment_id") or input_data.get("attachmentId"),
                    mime_type=input_data.get("mime_type") or input_data.get("mimeType", ""),
                    filename=input_data.get("filename", ""),
                    file_size=input_data.get("size"),
                    inline=bool(input_data.get("inline")),
                    **extraction_kwargs,
                )
                apply_extraction_to_file_payload(input_data, extraction)
                if input_data.get("content"):
                    return self._format_single_file_text(input_data, str(input_data["content"]))
                if requires_content:
                    self._raise_content_unavailable(
                        input_data,
                        str(input_data.get("content_status") or CONTENT_STATUS_FAILED),
                    )
                return self._format_single_file_text(
                    input_data,
                    self._format_extraction_failure(extraction),
                )

        if requires_content:
            self._raise_content_unavailable(
                input_data,
                str(content_status or CONTENT_STATUS_NOT_REQUESTED),
            )

        return self._format_single_file_metadata(input_data)

    async def _resolve_file_list_text(
        self,
        input_data: dict[str, Any],
        service_tokens: dict[str, str],
        requires_content: bool = False,
        content_action: str | None = None,
    ) -> str:
        formatted_items = []
        for item in input_data.get("items", []):
            if not isinstance(item, dict):
                continue
            item_payload = dict(item)
            item_payload.setdefault("type", "SINGLE_FILE")
            await self._resolve_single_file_text(
                item_payload,
                service_tokens,
                requires_content=requires_content,
                content_action=content_action,
            )
            formatted_items.append(self._format_file_list_item(item_payload))
        return "\n\n---\n\n".join(formatted_items)

    def _ensure_executable_prompt(
        self,
        node: dict[str, Any],
        action: str,
        output_data_type: str,
        prompt: str,
    ) -> None:
        """LLM 호출 전 프롬프트 필수 조건을 검증합니다."""
        if action not in SUPPORTED_ACTIONS:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"지원하지 않는 AI 처리 방식입니다: {action}",
                context={"node_id": node.get("id"), "action": action},
            )

        requires_prompt = (
            output_data_type == "SPREADSHEET_DATA" or action in PROMPT_REQUIRED_ACTIONS
        )
        if requires_prompt and not prompt:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="AI 처리 프롬프트가 없어 노드를 실행할 수 없습니다.",
                context={"node_id": node.get("id"), "action": action},
            )

    @staticmethod
    def _extract_text_from_canonical(input_data: dict | None) -> str:
        """canonical payload에서 LLM 입력용 텍스트를 추출합니다."""
        if not input_data:
            return ""

        data_type = input_data.get("type", "")

        if data_type == "TEXT":
            return input_data.get("content", "")
        if data_type == "SINGLE_FILE":
            return LLMNodeStrategy._format_single_file_text(
                input_data,
                str(input_data.get("content") or ""),
            )
        if data_type == "SINGLE_EMAIL":
            email = (
                input_data.get("email") if isinstance(input_data.get("email"), dict) else input_data
            )
            return f"Subject: {email.get('subject', '')}\n\n{email.get('body') or email.get('bodyPreview', '')}"
        if data_type == "SPREADSHEET_DATA":
            headers = input_data.get("headers", [])
            rows = input_data.get("rows", [])
            lines = [", ".join(str(header) for header in headers)] if headers else []
            lines.extend(", ".join(str(cell) for cell in row) for row in rows)
            return "\n".join(lines)
        if data_type == "FILE_LIST":
            items = input_data.get("items", [])
            return "\n".join(LLMNodeStrategy._format_file_list_item(item) for item in items)
        if data_type == "ARTICLE_LIST":
            items = input_data.get("items", [])
            return "\n\n---\n\n".join(
                LLMNodeStrategy._format_article_item(item, index)
                for index, item in enumerate(items, start=1)
                if isinstance(item, dict)
            )
        if data_type == "EMAIL_LIST":
            items = input_data.get("items", [])
            formatted_items = []
            for index, item in enumerate(items, start=1):
                formatted_items.append(
                    "\n".join(
                        [
                            f"[Email {index}]",
                            f"From: {item.get('from', '')}",
                            f"Date: {item.get('date', '')}",
                            f"Subject: {item.get('subject', '')}",
                            "Body:",
                            item.get("body") or item.get("bodyPreview", ""),
                        ]
                    )
                )
            return "\n\n---\n\n".join(formatted_items)
        if data_type == "SCHEDULE_DATA":
            items = input_data.get("items", [])
            return "\n".join(
                f"{item.get('title', '')}: {item.get('start_time', '')} - {item.get('end_time', '')}"
                for item in items
            )
        if data_type == "API_RESPONSE":
            if input_data.get("source_service") == "github" and input_data.get("event") == "new_pr":
                return LLMNodeStrategy._format_github_pr_text(input_data)
            return json.dumps(input_data.get("data", {}), ensure_ascii=False, default=str)

        # Fallback: serialize the whole payload.
        return json.dumps(input_data, ensure_ascii=False, default=str)

    @staticmethod
    def _format_github_pr_text(input_data: dict[str, Any]) -> str:
        pr = input_data.get("pr") if isinstance(input_data.get("pr"), dict) else input_data
        lines = [
            f"Repository: {pr.get('repository', '')}",
            f"PR Number: {pr.get('pr_number', '')}",
            f"Title: {pr.get('title', '')}",
            f"Author: {pr.get('author', '')}",
            f"State: {pr.get('state', '')}",
            f"Draft: {pr.get('draft', False)}",
            f"Created At: {pr.get('created_at', '')}",
            f"Updated At: {pr.get('updated_at', '')}",
            f"Base Branch: {pr.get('base_branch', '')}",
            f"Head Branch: {pr.get('head_branch', '')}",
            f"URL: {pr.get('url', '')}",
        ]

        labels = pr.get("labels") or []
        if labels:
            lines.append(f"Labels: {', '.join(str(label) for label in labels if label)}")

        reviewers = pr.get("requested_reviewers") or []
        if reviewers:
            lines.append(
                f"Requested Reviewers: {', '.join(str(reviewer) for reviewer in reviewers if reviewer)}"
            )

        lines.append(f"Changed Files Count: {pr.get('changed_files_count', 0)}")
        if pr.get("changed_files_truncated"):
            lines.append("Changed Files Truncated: True")

        body = pr.get("body")
        if body:
            lines.extend(["", "PR Body:", str(body)])

        changed_files = pr.get("changed_files") or []
        if changed_files:
            lines.extend(["", "Changed Files:"])
            for item in changed_files:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename") or ""
                status = item.get("status") or ""
                additions = item.get("additions") or 0
                deletions = item.get("deletions") or 0
                changes = item.get("changes") or (int(additions) + int(deletions))
                lines.append(
                    f"- {filename} (status: {status}, additions: {additions}, deletions: {deletions}, changes: {changes})"
                )

        return "\n".join(line for line in lines if line is not None).strip()

    @staticmethod
    def _format_single_file_metadata(input_data: dict[str, Any]) -> str:
        parts = [
            f"Filename: {input_data.get('filename', '')}",
            f"MIME Type: {input_data.get('mime_type', '')}",
        ]
        if input_data.get("created_time"):
            parts.append(f"Created Time: {input_data.get('created_time', '')}")
        if input_data.get("url"):
            parts.append(f"Source URL: {input_data.get('url', '')}")
        return "\n".join(parts).strip()

    @staticmethod
    def _format_single_file_text(input_data: dict[str, Any], text: str) -> str:
        metadata = LLMNodeStrategy._format_single_file_metadata(input_data)
        if not text:
            return metadata
        return f"{metadata}\n\n{text}".strip()

    @staticmethod
    def _format_extraction_failure(extraction: dict[str, Any]) -> str:
        status = extraction.get("content_status") or extraction.get("status", "failed")
        reason = extraction.get("content_error") or extraction.get("error") or "unsupported"
        return "\n".join(
            [
                "File content could not be extracted.",
                f"Status: {status}",
                f"Reason: {reason}",
            ]
        )

    @staticmethod
    def _format_file_list_item(item: dict[str, Any]) -> str:
        parts = [f"- Filename: {item.get('filename', '')}"]
        if item.get("mime_type"):
            parts.append(f"  MIME Type: {item.get('mime_type', '')}")
        if item.get("size") is not None:
            parts.append(f"  Size: {item.get('size')}")
        if item.get("created_time"):
            parts.append(f"  Created Time: {item.get('created_time', '')}")
        if item.get("modified_time"):
            parts.append(f"  Modified Time: {item.get('modified_time', '')}")
        if item.get("url"):
            parts.append(f"  Source URL: {item.get('url', '')}")
        if item.get("content_status"):
            parts.append(f"  Content Status: {item.get('content_status', '')}")
        if item.get("content_error"):
            parts.append(f"  Content Error: {item.get('content_error', '')}")
        if item.get("content"):
            parts.append("  Content:")
            parts.append(str(item.get("content", "")))
        return "\n".join(parts)

    @staticmethod
    def _raise_content_unavailable(input_data: dict[str, Any], status: str) -> None:
        if status == CONTENT_STATUS_UNSUPPORTED:
            code = ErrorCode.DOCUMENT_CONTENT_UNSUPPORTED
        elif status == CONTENT_STATUS_TOO_LARGE:
            code = ErrorCode.DOCUMENT_CONTENT_TOO_LARGE
        elif status == CONTENT_STATUS_EMPTY:
            code = ErrorCode.DOCUMENT_CONTENT_EMPTY
        elif status == CONTENT_STATUS_NOT_REQUESTED:
            code = ErrorCode.DOCUMENT_CONTENT_NOT_REQUESTED
        else:
            code = ErrorCode.DOCUMENT_CONTENT_EXTRACTION_FAILED

        error = input_data.get("content_error")
        raise FlowifyException(
            code,
            detail=error or code.message,
            context={
                "filename": input_data.get("filename", ""),
                "message_id": input_data.get("message_id") or input_data.get("messageId", ""),
                "attachment_id": input_data.get("attachment_id")
                or input_data.get("attachmentId", ""),
                "content_status": status,
                "content_error": error,
            },
        )

    @staticmethod
    def _format_article_item(item: dict[str, Any], index: int) -> str:
        parts = [
            f"[Article {index}]",
            f"Title: {item.get('title', '')}",
        ]
        if item.get("source"):
            parts.append(f"Source: {item.get('source', '')}")
        if item.get("author"):
            parts.append(f"Author: {item.get('author', '')}")
        if item.get("published_at"):
            parts.append(f"Published At: {item.get('published_at', '')}")
        if item.get("url"):
            parts.append(f"URL: {item.get('url', '')}")

        summary = item.get("summary")
        if summary:
            parts.extend(["Summary:", str(summary)])

        content = item.get("content")
        if content:
            parts.extend(["Content:", str(content)])

        return "\n".join(parts).strip()

    @staticmethod
    def _build_output_payload(
        output_data_type: str,
        result: str,
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": output_data_type, "content": result}
        if output_data_type != "TEXT" or not input_data:
            return payload

        passthrough_keys = (
            "file_id",
            "filename",
            "mime_type",
            "url",
            "created_time",
            "modified_time",
        )
        for key in passthrough_keys:
            value = input_data.get(key)
            if value not in (None, ""):
                payload[key] = value
        return payload

    @staticmethod
    def _to_spreadsheet_payload(result: dict[str, Any]) -> dict[str, Any]:
        headers = result.get("headers", [])
        rows = result.get("rows", [])

        normalized_headers = (
            [str(header) for header in headers] if isinstance(headers, list) else []
        )
        normalized_rows: list[list[str]] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, list):
                    normalized_rows.append([str(cell) for cell in row])

        return {
            "type": "SPREADSHEET_DATA",
            "headers": normalized_headers,
            "rows": normalized_rows,
        }
