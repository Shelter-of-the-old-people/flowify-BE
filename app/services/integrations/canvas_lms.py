import logging
from typing import Any

import httpx

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings
from app.services.integrations.base import BaseIntegrationService

logger = logging.getLogger(__name__)


class CanvasLmsService(BaseIntegrationService):
    """Canvas LMS API 연동 서비스.

    금오공대 Canvas LMS 등에서 강의자료를 조회한다.
    Canvas API는 Link 헤더 기반 페이지네이션을 사용한다.
    """

    @property
    def _base_url(self) -> str:
        return settings.CANVAS_LMS_API_URL.rstrip("/")

    async def get_course_files(self, token: str, course_id: str) -> list[dict]:
        """특정 과목의 전체 파일 목록을 조회한다 (페이지네이션 포함)."""
        url = f"{self._base_url}/courses/{course_id}/files"
        return await self._paginated_get(token, url, params={"per_page": 100})

    async def get_course_latest_file(self, token: str, course_id: str) -> dict | None:
        """특정 과목의 가장 최근 업로드된 파일 1개를 반환한다."""
        data = await self._request(
            "GET",
            f"{self._base_url}/courses/{course_id}/files",
            token,
            params={"sort": "created_at", "order": "desc", "per_page": 1},
        )
        files = data if isinstance(data, list) else data.get("files", [data])
        return files[0] if files else None

    async def get_active_courses(self, token: str) -> list[dict]:
        """사용자의 수강 중인 과목 목록을 조회한다 (term 정보 포함)."""
        url = f"{self._base_url}/courses"
        return await self._paginated_get(
            token,
            url,
            params={"enrollment_state": "active", "include[]": "term", "per_page": 100},
        )

    async def _paginated_get(
        self,
        token: str,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Canvas API Link 헤더 기반 페이지네이션을 처리한다."""
        results: list[dict] = []
        current_url = url
        current_params = params

        for _ in range(50):  # 안전 한도
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        current_url,
                        headers={"Authorization": f"Bearer {token}"},
                        params=current_params,
                    )

                if resp.status_code == 401:
                    raise FlowifyException(
                        ErrorCode.OAUTH_TOKEN_INVALID,
                        detail="Canvas API 토큰이 만료되었거나 유효하지 않습니다.",
                    )
                if resp.status_code == 403:
                    raise FlowifyException(
                        ErrorCode.EXTERNAL_SERVICE_ERROR,
                        detail="Canvas 과목 접근 권한이 없습니다.",
                        context={"url": current_url},
                    )
                if resp.status_code == 404:
                    raise FlowifyException(
                        ErrorCode.EXTERNAL_SERVICE_ERROR,
                        detail="Canvas 리소스를 찾을 수 없습니다.",
                        context={"url": current_url},
                    )
                resp.raise_for_status()

                page_data = resp.json()
                if isinstance(page_data, list):
                    results.extend(page_data)
                else:
                    results.append(page_data)

                next_url = self._parse_next_link(resp.headers.get("link", ""))
                if not next_url:
                    break
                current_url = next_url
                current_params = None  # 이후 페이지는 URL에 파라미터 포함

            except FlowifyException:
                raise
            except Exception as e:
                raise FlowifyException(
                    ErrorCode.EXTERNAL_API_ERROR,
                    detail=f"Canvas API 호출 실패: {current_url}",
                    context={"error": str(e)},
                ) from e

        return results

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        """Link 헤더에서 rel='next' URL을 추출한다."""
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    @staticmethod
    def to_file_item(f: dict, course_name: str | None = None) -> dict:
        """Canvas 파일 객체를 canonical FILE_LIST item으로 변환한다."""
        filename = _safe_filename(f.get("display_name", f.get("filename", "unknown")))
        if course_name:
            filename = f"{course_name}/{filename}"
        return {
            "filename": filename,
            "mime_type": f.get("content-type", "application/octet-stream"),
            "size": f.get("size", 0),
            "url": f.get("url", ""),
        }


def _safe_filename(name: str) -> str:
    """파일명에서 특수문자를 제거한다. 한글은 유지."""
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip()
