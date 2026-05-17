"""Document content canonical payload helpers."""

from __future__ import annotations

from typing import Any

CONTENT_STATUS_AVAILABLE = "available"
CONTENT_STATUS_EMPTY = "empty"
CONTENT_STATUS_UNSUPPORTED = "unsupported"
CONTENT_STATUS_TOO_LARGE = "too_large"
CONTENT_STATUS_FAILED = "failed"
CONTENT_STATUS_NOT_REQUESTED = "not_requested"

CONTENT_KIND_NONE = "none"
EXTRACTION_METHOD_NONE = "none"

MAX_LOG_CONTENT_CHARS = 4000
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 60000
MAX_LLM_INPUT_CHARS = 60000

DEFAULT_CONTENT_LIMITS: dict[str, int] = {
    "max_download_bytes": MAX_DOWNLOAD_BYTES,
    "max_extracted_chars": MAX_EXTRACTED_CHARS,
    "max_llm_input_chars": MAX_LLM_INPUT_CHARS,
}

_SAFE_CONTENT_ERROR_MESSAGES = {
    CONTENT_STATUS_EMPTY: "파일에서 읽을 수 있는 텍스트를 찾지 못했습니다.",
    CONTENT_STATUS_FAILED: "파일 본문을 읽는 중 오류가 발생했습니다.",
    CONTENT_STATUS_NOT_REQUESTED: "본문 추출이 요청되지 않았습니다.",
    CONTENT_STATUS_TOO_LARGE: "파일이 현재 처리 가능한 크기를 초과했습니다.",
    CONTENT_STATUS_UNSUPPORTED: "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다.",
}


def default_content_limits() -> dict[str, int]:
    return dict(DEFAULT_CONTENT_LIMITS)


def safe_content_error(content_status: str, content_error: Any = None) -> str | None:
    if content_status == CONTENT_STATUS_AVAILABLE:
        return None
    if content_status in _SAFE_CONTENT_ERROR_MESSAGES:
        return _SAFE_CONTENT_ERROR_MESSAGES[content_status]

    if content_error is None:
        return None

    message = str(content_error).strip()
    if not message:
        return None
    if "\n" in message or "\r" in message or "Traceback" in message or len(message) > 160:
        return _SAFE_CONTENT_ERROR_MESSAGES[CONTENT_STATUS_FAILED]
    return message


def default_content_metadata(
    *,
    extraction_method: str = EXTRACTION_METHOD_NONE,
    content_kind: str = CONTENT_KIND_NONE,
    truncated: bool = False,
    char_count: int = 0,
    original_char_count: int = 0,
    limits: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_limits = default_content_limits()
    if limits:
        normalized_limits.update(limits)
    metadata: dict[str, Any] = {
        "extraction_method": extraction_method,
        "content_kind": content_kind,
        "truncated": truncated,
        "char_count": char_count,
        "original_char_count": original_char_count,
        "limits": normalized_limits,
    }
    if extra:
        metadata.update(extra)
    return metadata


def default_file_content_fields() -> dict[str, Any]:
    return {
        "content": None,
        "content_status": CONTENT_STATUS_NOT_REQUESTED,
        "content_error": None,
        "content_metadata": default_content_metadata(),
        # Legacy fields kept while FE/Spring migrate to content_*.
        "extracted_text": None,
        "extraction_status": "not_requested",
    }


def legacy_status_for_content_status(content_status: str, *, truncated: bool = False) -> str:
    if content_status == CONTENT_STATUS_AVAILABLE:
        return "truncated" if truncated else "success"
    if content_status in {
        CONTENT_STATUS_UNSUPPORTED,
        CONTENT_STATUS_FAILED,
        CONTENT_STATUS_NOT_REQUESTED,
    }:
        return content_status
    if content_status == CONTENT_STATUS_TOO_LARGE:
        return "failed"
    if content_status == CONTENT_STATUS_EMPTY:
        return "success"
    return "failed"


def build_extraction_result(
    *,
    content: str | None = None,
    content_status: str = CONTENT_STATUS_AVAILABLE,
    content_error: str | None = None,
    extraction_method: str = EXTRACTION_METHOD_NONE,
    content_kind: str = CONTENT_KIND_NONE,
    truncated: bool = False,
    original_char_count: int | None = None,
    limits: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = content or ""
    char_count = len(text)
    original_count = original_char_count if original_char_count is not None else char_count
    if content_status == CONTENT_STATUS_AVAILABLE and not text:
        content_status = CONTENT_STATUS_EMPTY
    content_error = safe_content_error(content_status, content_error)

    metadata = default_content_metadata(
        extraction_method=extraction_method,
        content_kind=content_kind,
        truncated=truncated,
        char_count=char_count,
        original_char_count=original_count,
        limits=limits,
        extra=metadata,
    )
    legacy_status = legacy_status_for_content_status(content_status, truncated=truncated)
    return {
        # Legacy extraction shape.
        "text": text,
        "status": legacy_status,
        "truncated": truncated,
        "error": content_error,
        # Canonical content shape.
        "content": text or None,
        "content_status": content_status,
        "content_error": content_error,
        "content_metadata": metadata,
    }


def apply_extraction_to_file_payload(payload: dict[str, Any], extraction: dict[str, Any]) -> None:
    content = extraction.get("content")
    if content is None:
        content = extraction.get("text") or None
    content_status = extraction.get("content_status") or _content_status_from_legacy(
        extraction.get("status"),
        bool(extraction.get("truncated")),
        content,
    )
    content_metadata = extraction.get("content_metadata") or default_content_metadata(
        truncated=bool(extraction.get("truncated")),
        char_count=len(content or ""),
        original_char_count=len(content or ""),
    )
    if isinstance(content_metadata, dict):
        content_metadata = dict(content_metadata)
        content_metadata.setdefault("limits", default_content_limits())
    content_error = safe_content_error(
        content_status,
        extraction.get("content_error") or extraction.get("error"),
    )

    payload["content"] = content
    payload["content_status"] = content_status
    payload["content_error"] = content_error
    payload["content_metadata"] = content_metadata
    payload["extracted_text"] = content
    payload["extraction_status"] = extraction.get("status") or legacy_status_for_content_status(
        content_status,
        truncated=bool(content_metadata.get("truncated")),
    )
    if payload["content_error"]:
        payload["extraction_error"] = payload["content_error"]


def ensure_file_content_fields(payload: dict[str, Any]) -> dict[str, Any]:
    defaults = default_file_content_fields()
    for key, value in defaults.items():
        payload.setdefault(key, value)
    return payload


def truncate_content_for_log(data: Any, *, max_chars: int = MAX_LOG_CONTENT_CHARS) -> Any:
    if isinstance(data, list):
        return [truncate_content_for_log(item, max_chars=max_chars) for item in data]
    if not isinstance(data, dict):
        return data

    cleaned = {
        key: truncate_content_for_log(value, max_chars=max_chars) for key, value in data.items()
    }
    content = cleaned.get("content")
    if isinstance(content, str) and len(content) > max_chars:
        cleaned["content"] = content[:max_chars]
        metadata = cleaned.get("content_metadata")
        if not isinstance(metadata, dict):
            metadata = default_content_metadata()
        else:
            metadata = dict(metadata)
            metadata.setdefault("limits", default_content_limits())
        metadata["truncated_for_log"] = True
        metadata["stored_content_truncated"] = True
        metadata["stored_char_count"] = len(cleaned["content"])
        metadata.setdefault("original_char_count", len(content))
        cleaned["content_metadata"] = metadata
    return cleaned


def _content_status_from_legacy(
    legacy_status: Any,
    truncated: bool,
    content: str | None,
) -> str:
    if legacy_status in ("success", "truncated"):
        return CONTENT_STATUS_AVAILABLE if content else CONTENT_STATUS_EMPTY
    if legacy_status == CONTENT_STATUS_UNSUPPORTED:
        return CONTENT_STATUS_UNSUPPORTED
    if legacy_status == CONTENT_STATUS_FAILED:
        return CONTENT_STATUS_FAILED
    if legacy_status == CONTENT_STATUS_NOT_REQUESTED:
        return CONTENT_STATUS_NOT_REQUESTED
    if truncated:
        return CONTENT_STATUS_AVAILABLE
    return CONTENT_STATUS_FAILED
