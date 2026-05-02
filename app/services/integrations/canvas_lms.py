import logging
from typing import Any

import httpx

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings
from app.services.integrations.base import BaseIntegrationService

logger = logging.getLogger(__name__)


class CanvasLmsService(BaseIntegrationService):
    """Canvas LMS API integration service."""

    @property
    def _base_url(self) -> str:
        return settings.CANVAS_LMS_API_URL.rstrip("/")

    async def get_course_files(self, token: str, course_id: str) -> list[dict]:
        """Return all files for a course."""
        url = f"{self._base_url}/courses/{course_id}/files"
        return await self._paginated_get(token, url, params={"per_page": 100})

    async def get_course_latest_file(self, token: str, course_id: str) -> dict | None:
        """Return the most recently created course file, if any."""
        data = await self._request(
            "GET",
            f"{self._base_url}/courses/{course_id}/files",
            token,
            params={"sort": "created_at", "order": "desc", "per_page": 1},
        )
        files = data if isinstance(data, list) else data.get("files", [data])
        return files[0] if files else None

    async def get_courses(
        self,
        token: str,
        *,
        include_completed: bool = False,
    ) -> list[dict]:
        """Return Canvas course list with term information."""
        url = f"{self._base_url}/courses"
        enrollment_states: str | list[str] = "active"
        if include_completed:
            enrollment_states = ["active", "completed"]

        return await self._paginated_get(
            token,
            url,
            params={
                "enrollment_state[]": enrollment_states,
                "include[]": "term",
                "per_page": 100,
            },
        )

    async def get_active_courses(self, token: str) -> list[dict]:
        """Backward-compatible helper for active courses only."""
        return await self.get_courses(token, include_completed=False)

    async def _paginated_get(
        self,
        token: str,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Follow Canvas pagination using Link headers."""
        results: list[dict] = []
        current_url = url
        current_params = params

        for _ in range(50):
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
                        detail="Canvas API token is invalid or expired.",
                    )
                if resp.status_code == 403:
                    raise FlowifyException(
                        ErrorCode.EXTERNAL_SERVICE_ERROR,
                        detail="Canvas course access is forbidden.",
                        context={"url": current_url},
                    )
                if resp.status_code == 404:
                    raise FlowifyException(
                        ErrorCode.EXTERNAL_SERVICE_ERROR,
                        detail="Canvas resource was not found.",
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
                current_params = None

            except FlowifyException:
                raise
            except Exception as e:
                raise FlowifyException(
                    ErrorCode.EXTERNAL_API_ERROR,
                    detail=f"Canvas API request failed: {current_url}",
                    context={"error": str(e)},
                ) from e

        return results

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    @staticmethod
    def to_file_item(f: dict, course_name: str | None = None) -> dict:
        filename = _safe_filename(f.get("display_name", f.get("filename", "unknown")))
        if course_name:
            safe_course_name = _safe_filename(course_name)
            if safe_course_name:
                filename = f"{safe_course_name}/{filename}"
        return {
            "filename": filename,
            "mime_type": f.get("content-type", "application/octet-stream"),
            "size": f.get("size", 0),
            "url": f.get("url", ""),
        }


def _safe_filename(name: str) -> str:
    """Remove characters invalid in file or folder names."""
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip()
