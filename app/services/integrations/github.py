import logging
from typing import Any

import httpx

from app.common.errors import ErrorCode, FlowifyException

logger = logging.getLogger(__name__)


class GitHubService:
    """GitHub REST API integration for PR source workflows."""

    _BASE_URL = "https://api.github.com"
    _DEFAULT_TIMEOUT = 30.0
    _DEFAULT_HEADERS = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Flowify-GitHub-Node",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    @staticmethod
    def parse_repository_target(target: str) -> tuple[str, str]:
        normalized = target.strip().strip("/")
        parts = normalized.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="GitHub source target must be in owner/repo format.",
            )
        return parts[0], parts[1]

    async def list_open_pull_requests(
        self,
        token: str,
        owner: str,
        repo: str,
    ) -> list[dict[str, Any]]:
        url = f"{self._BASE_URL}/repos/{owner}/{repo}/pulls"
        return await self._paginated_get(
            token,
            url,
            params={
                "state": "open",
                "sort": "created",
                "direction": "asc",
                "per_page": 100,
            },
        )

    async def get_pull_request(
        self,
        token: str,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> dict[str, Any]:
        url = f"{self._BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        response = await self._request_response(token, url)
        return self._parse_json_object(response, url)

    async def list_pull_request_files(
        self,
        token: str,
        owner: str,
        repo: str,
        pr_number: int,
        *,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        url = f"{self._BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        current_url = url
        current_params: dict[str, Any] | None = {"per_page": 100}
        results: list[dict[str, Any]] = []
        truncated = False

        for _ in range(10):
            response = await self._request_response(token, current_url, params=current_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise FlowifyException(
                    ErrorCode.EXTERNAL_API_ERROR,
                    detail=f"Unexpected GitHub PR files response: {current_url}",
                )

            for file_item in payload:
                if len(results) >= limit:
                    truncated = True
                    break
                results.append(self._normalize_changed_file(file_item))

            if truncated:
                break

            next_url = self._parse_next_link(response.headers.get("link", ""))
            if not next_url:
                break
            current_url = next_url
            current_params = None

        return results, truncated

    async def _paginated_get(
        self,
        token: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        current_url = url
        current_params = params

        for _ in range(10):
            response = await self._request_response(token, current_url, params=current_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise FlowifyException(
                    ErrorCode.EXTERNAL_API_ERROR,
                    detail=f"Unexpected GitHub list response: {current_url}",
                )
            results.extend(item for item in payload if isinstance(item, dict))

            next_url = self._parse_next_link(response.headers.get("link", ""))
            if not next_url:
                break
            current_url = next_url
            current_params = None

        return results

    async def _request_response(
        self,
        token: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {
            **self._DEFAULT_HEADERS,
            "Authorization": f"Bearer {token}",
        }

        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.get(url, headers=headers, params=params)
        except Exception as exc:  # pragma: no cover - network failure mapping
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"GitHub API request failed: {url}",
                context={"error": str(exc)},
            ) from exc

        if response.status_code == 401:
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail="GitHub token is invalid or expired.",
                context={"url": url, "status": 401},
            )
        if response.status_code == 403:
            if self._is_rate_limited(response):
                raise FlowifyException(
                    ErrorCode.EXTERNAL_RATE_LIMITED,
                    detail="GitHub API rate limit exceeded.",
                    context={"url": url, "status": 403},
                )
            raise FlowifyException(
                ErrorCode.EXTERNAL_SERVICE_ERROR,
                detail="GitHub resource access is forbidden.",
                context={"url": url, "status": 403},
            )
        if response.status_code == 404:
            raise FlowifyException(
                ErrorCode.EXTERNAL_SERVICE_ERROR,
                detail="GitHub repository or pull request was not found.",
                context={"url": url, "status": 404},
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"GitHub API request failed: {url}",
                context={"status": response.status_code, "error": str(exc)},
            ) from exc

        return response

    @staticmethod
    def _parse_json_object(response: httpx.Response, url: str) -> dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"Unexpected GitHub object response: {url}",
            )
        return payload

    @staticmethod
    def _normalize_changed_file(file_item: dict[str, Any]) -> dict[str, Any]:
        return {
            "filename": file_item.get("filename") or "",
            "status": file_item.get("status") or "",
            "additions": int(file_item.get("additions") or 0),
            "deletions": int(file_item.get("deletions") or 0),
            "changes": int(file_item.get("changes") or 0),
            "sha": file_item.get("sha") or "",
            "blob_url": file_item.get("blob_url") or "",
            "raw_url": file_item.get("raw_url") or "",
            "previous_filename": file_item.get("previous_filename") or "",
        }

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining == "0":
            return True

        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        if isinstance(payload, dict):
            message = str(payload.get("message") or "").lower()
            return "rate limit" in message

        return "rate limit" in str(payload).lower()
