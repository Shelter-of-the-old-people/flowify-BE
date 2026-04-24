"""Canonical Payload 타입 정의.

모든 노드 간 데이터 전달은 canonical payload 형식을 사용한다.
각 payload는 "type" discriminator를 포함하며, 이를 통해 다음 노드가 입력 형식을 판별한다.

참조: FASTAPI_IMPLEMENTATION_GUIDE.md 섹션 8
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CanonicalType(StrEnum):
    SINGLE_FILE = "SINGLE_FILE"
    FILE_LIST = "FILE_LIST"
    SINGLE_EMAIL = "SINGLE_EMAIL"
    EMAIL_LIST = "EMAIL_LIST"
    SPREADSHEET_DATA = "SPREADSHEET_DATA"
    SCHEDULE_DATA = "SCHEDULE_DATA"
    API_RESPONSE = "API_RESPONSE"
    TEXT = "TEXT"


# ── SINGLE_FILE ──


class SingleFilePayload(BaseModel):
    type: str = CanonicalType.SINGLE_FILE
    filename: str
    content: str | None = None
    mime_type: str | None = None
    url: str | None = None


# ── FILE_LIST ──


class FileItem(BaseModel):
    filename: str
    mime_type: str | None = None
    size: int | None = None
    url: str | None = None


class FileListPayload(BaseModel):
    type: str = CanonicalType.FILE_LIST
    items: list[FileItem] = Field(default_factory=list)


# ── SINGLE_EMAIL ──


class EmailAttachment(BaseModel):
    filename: str
    mime_type: str | None = None
    size: int | None = None


class SingleEmailPayload(BaseModel):
    type: str = CanonicalType.SINGLE_EMAIL
    subject: str
    from_: str = Field(alias="from", default="")
    date: str = ""
    body: str = ""
    attachments: list[EmailAttachment] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── EMAIL_LIST ──


class EmailItem(BaseModel):
    subject: str
    from_: str = Field(alias="from", default="")
    date: str = ""
    body: str | None = None

    model_config = {"populate_by_name": True}


class EmailListPayload(BaseModel):
    type: str = CanonicalType.EMAIL_LIST
    items: list[EmailItem] = Field(default_factory=list)


# ── SPREADSHEET_DATA ──


class SpreadsheetDataPayload(BaseModel):
    type: str = CanonicalType.SPREADSHEET_DATA
    rows: list[list[Any]] = Field(default_factory=list)
    headers: list[str] | None = None
    sheet_name: str | None = None


# ── SCHEDULE_DATA ──


class ScheduleItem(BaseModel):
    title: str
    start_time: str
    end_time: str | None = None
    location: str | None = None
    description: str | None = None


class ScheduleDataPayload(BaseModel):
    type: str = CanonicalType.SCHEDULE_DATA
    items: list[ScheduleItem] = Field(default_factory=list)


# ── API_RESPONSE ──


class ApiResponsePayload(BaseModel):
    type: str = CanonicalType.API_RESPONSE
    data: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None


# ── TEXT ──


class TextPayload(BaseModel):
    type: str = CanonicalType.TEXT
    content: str = ""
