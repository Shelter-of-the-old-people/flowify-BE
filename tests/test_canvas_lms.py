"""Canvas LMS 연동 테스트.

CanvasLmsService 단위 테스트 + InputNodeStrategy canvas_lms 분기 테스트.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.input_node import InputNodeStrategy
from app.services.integrations.canvas_lms import CanvasLmsService, _safe_filename


# ── 헬퍼 ──


def _canvas_node(mode: str, target: str = "12345") -> dict:
    return {
        "runtime_source": {
            "service": "canvas_lms",
            "mode": mode,
            "target": target,
            "canonical_input_type": "FILE_LIST",
        }
    }


SAMPLE_FILES = [
    {
        "id": 67890,
        "display_name": "Week01_Introduction.pdf",
        "filename": "Week01_Introduction.pdf",
        "url": "https://canvas.kumoh.ac.kr/files/67890/download?token=abc",
        "content-type": "application/pdf",
        "size": 1048576,
    },
    {
        "id": 67891,
        "display_name": "Week02_Variables.pdf",
        "filename": "Week02_Variables.pdf",
        "url": "https://canvas.kumoh.ac.kr/files/67891/download?token=def",
        "content-type": "application/pdf",
        "size": 524288,
    },
]


# ── CanvasLmsService 단위 테스트 ──


class TestCanvasLmsService:
    """CanvasLmsService의 API 호출과 페이지네이션을 검증한다."""

    async def test_get_course_files(self):
        """과목 파일 조회 시 페이지네이션을 처리하고 전체 파일을 반환한다."""
        svc = CanvasLmsService()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_FILES
        mock_resp.headers = {"link": ""}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.integrations.canvas_lms.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            files = await svc.get_course_files("test-token", "12345")

        assert len(files) == 2
        assert files[0]["display_name"] == "Week01_Introduction.pdf"

    async def test_get_course_latest_file(self):
        """최신 파일 조회 시 1개 파일만 반환한다."""
        svc = CanvasLmsService()

        with patch.object(svc, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [SAMPLE_FILES[0]]

            result = await svc.get_course_latest_file("test-token", "12345")

        assert result is not None
        assert result["display_name"] == "Week01_Introduction.pdf"

    async def test_get_course_latest_file_empty(self):
        """파일이 없으면 None을 반환한다."""
        svc = CanvasLmsService()

        with patch.object(svc, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []

            result = await svc.get_course_latest_file("test-token", "12345")

        assert result is None

    async def test_get_active_courses(self):
        """수강 과목 목록을 조회한다."""
        svc = CanvasLmsService()
        courses = [
            {"id": 1, "name": "소프트웨어공학", "term": {"name": "2026-1학기"}},
            {"id": 2, "name": "데이터베이스", "term": {"name": "2026-1학기"}},
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = courses
        mock_resp.headers = {"link": ""}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.integrations.canvas_lms.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            result = await svc.get_active_courses("test-token")

        assert len(result) == 2

    async def test_paginated_get_follows_next_link(self):
        """Link 헤더의 rel=next를 따라 페이지네이션을 처리한다."""
        svc = CanvasLmsService()

        resp_page1 = MagicMock()
        resp_page1.status_code = 200
        resp_page1.json.return_value = [SAMPLE_FILES[0]]
        resp_page1.headers = {
            "link": '<https://canvas.kumoh.ac.kr/api/v1/courses/12345/files?page=2>; rel="next"'
        }
        resp_page1.raise_for_status = MagicMock()

        resp_page2 = MagicMock()
        resp_page2.status_code = 200
        resp_page2.json.return_value = [SAMPLE_FILES[1]]
        resp_page2.headers = {"link": ""}
        resp_page2.raise_for_status = MagicMock()

        with patch("app.services.integrations.canvas_lms.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[resp_page1, resp_page2])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            files = await svc.get_course_files("test-token", "12345")

        assert len(files) == 2
        assert mock_client.get.await_count == 2

    async def test_401_raises_oauth_error(self):
        """Canvas API 401 응답 시 OAUTH_TOKEN_INVALID를 발생시킨다."""
        svc = CanvasLmsService()

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("app.services.integrations.canvas_lms.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(FlowifyException) as exc_info:
                await svc.get_course_files("bad-token", "12345")

        assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID

    async def test_404_raises_external_service_error(self):
        """Canvas API 404 응답 시 EXTERNAL_SERVICE_ERROR를 발생시킨다."""
        svc = CanvasLmsService()

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("app.services.integrations.canvas_lms.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(FlowifyException) as exc_info:
                await svc.get_course_files("test-token", "99999")

        assert exc_info.value.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR


class TestParseNextLink:
    """Link 헤더 파싱을 검증한다."""

    def test_parse_next_link(self):
        header = '<https://example.com/api?page=2>; rel="next", <https://example.com/api?page=1>; rel="prev"'
        assert CanvasLmsService._parse_next_link(header) == "https://example.com/api?page=2"

    def test_parse_no_next(self):
        header = '<https://example.com/api?page=1>; rel="prev"'
        assert CanvasLmsService._parse_next_link(header) is None

    def test_parse_empty(self):
        assert CanvasLmsService._parse_next_link("") is None


class TestToFileItem:
    """Canvas 파일 → canonical FILE_LIST item 변환을 검증한다."""

    def test_basic_conversion(self):
        item = CanvasLmsService.to_file_item(SAMPLE_FILES[0])
        assert item == {
            "filename": "Week01_Introduction.pdf",
            "mime_type": "application/pdf",
            "size": 1048576,
            "url": "https://canvas.kumoh.ac.kr/files/67890/download?token=abc",
        }

    def test_with_course_name(self):
        item = CanvasLmsService.to_file_item(SAMPLE_FILES[0], course_name="소프트웨어공학")
        assert item["filename"] == "소프트웨어공학/Week01_Introduction.pdf"


class TestSafeFilename:
    """파일명 특수문자 제거를 검증한다."""

    def test_removes_special_chars(self):
        assert _safe_filename('test<>:"/\\|?*.pdf') == "test.pdf"

    def test_keeps_korean(self):
        assert _safe_filename("과제1_제출.pdf") == "과제1_제출.pdf"

    def test_strips_whitespace(self):
        assert _safe_filename("  file.txt  ") == "file.txt"


# ── InputNodeStrategy canvas_lms 분기 테스트 ──


class TestInputNodeCanvasLms:
    """InputNodeStrategy에서 canvas_lms 서비스 분기를 검증한다."""

    async def test_course_files(self):
        """course_files 모드에서 FILE_LIST를 반환한다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("course_files", "12345")
        tokens = {"canvas_lms": "test-token"}

        with patch("app.core.nodes.input_node.CanvasLmsService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.get_course_files = AsyncMock(return_value=SAMPLE_FILES)
            mock_svc.to_file_item = CanvasLmsService.to_file_item

            result = await strategy.execute(node, None, tokens)

        assert result["type"] == "FILE_LIST"
        assert len(result["items"]) == 2
        assert result["items"][0]["filename"] == "Week01_Introduction.pdf"

    async def test_course_new_file(self):
        """course_new_file 모드에서 SINGLE_FILE을 반환한다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("course_new_file", "12345")
        tokens = {"canvas_lms": "test-token"}

        with patch("app.core.nodes.input_node.CanvasLmsService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.get_course_latest_file = AsyncMock(return_value=SAMPLE_FILES[0])

            result = await strategy.execute(node, None, tokens)

        assert result["type"] == "SINGLE_FILE"
        assert result["filename"] == "Week01_Introduction.pdf"
        assert result["url"] == "https://canvas.kumoh.ac.kr/files/67890/download?token=abc"

    async def test_course_new_file_empty(self):
        """파일이 없으면 빈 SINGLE_FILE을 반환한다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("course_new_file", "12345")
        tokens = {"canvas_lms": "test-token"}

        with patch("app.core.nodes.input_node.CanvasLmsService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.get_course_latest_file = AsyncMock(return_value=None)

            result = await strategy.execute(node, None, tokens)

        assert result["type"] == "SINGLE_FILE"
        assert result["filename"] == ""

    async def test_term_all_files(self):
        """term_all_files 모드에서 학기 전체 과목 파일을 FILE_LIST로 반환한다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("term_all_files", "2026-1학기")
        tokens = {"canvas_lms": "test-token"}

        courses = [
            {"id": 1, "name": "소프트웨어공학", "term": {"name": "2026-1학기"}},
            {"id": 2, "name": "데이터베이스", "term": {"name": "2026-1학기"}},
        ]

        with patch("app.core.nodes.input_node.CanvasLmsService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.get_active_courses = AsyncMock(return_value=courses)
            mock_svc.get_course_files = AsyncMock(return_value=[SAMPLE_FILES[0]])
            mock_svc.to_file_item = CanvasLmsService.to_file_item

            result = await strategy.execute(node, None, tokens)

        assert result["type"] == "FILE_LIST"
        assert len(result["items"]) == 2
        assert result["items"][0]["filename"] == "소프트웨어공학/Week01_Introduction.pdf"
        assert result["items"][1]["filename"] == "데이터베이스/Week01_Introduction.pdf"

    async def test_term_all_files_no_matching_courses(self):
        """학기에 해당하는 과목이 없으면 NODE_EXECUTION_FAILED를 발생시킨다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("term_all_files", "2099-1학기")
        tokens = {"canvas_lms": "test-token"}

        with patch("app.core.nodes.input_node.CanvasLmsService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.get_active_courses = AsyncMock(return_value=[
                {"id": 1, "name": "과목A", "term": {"name": "2026-1학기"}},
            ])

            with pytest.raises(FlowifyException) as exc_info:
                await strategy.execute(node, None, tokens)

        assert exc_info.value.error_code == ErrorCode.NODE_EXECUTION_FAILED

    async def test_missing_token_raises_error(self):
        """canvas_lms 토큰이 없으면 OAUTH_TOKEN_INVALID를 발생시킨다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("course_files", "12345")

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, None, {})

        assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID

    def test_validate_canvas_lms_modes(self):
        """canvas_lms의 3가지 모드가 모두 validate를 통과한다."""
        strategy = InputNodeStrategy({})
        for mode in ("course_files", "course_new_file", "term_all_files"):
            node = _canvas_node(mode, "12345")
            assert strategy.validate(node) is True

    def test_validate_unsupported_mode(self):
        """지원하지 않는 모드는 validate가 False를 반환한다."""
        strategy = InputNodeStrategy({})
        node = _canvas_node("invalid_mode", "12345")
        assert strategy.validate(node) is False
