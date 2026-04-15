from app.services.integrations.base import BaseIntegrationService


class RestAPIService(BaseIntegrationService):
    """범용 REST API 호출 서비스 (DC-F0405).

    BaseIntegrationService의 재시도/에러 래핑을 상속합니다.
    token이 필요 없는 경우 빈 문자열을 전달하면 됩니다.
    """

    async def call(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        params: dict | None = None,
        body: dict | None = None,
        token: str = "",
        timeout: float = 30.0,
    ) -> dict:
        if token:
            return await self._request(
                method, url, token,
                json=body, params=params, headers=headers, timeout=timeout,
            )

        # 토큰 없는 공개 API 호출
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=body,
            )
            resp.raise_for_status()
            if resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
            return {"status_code": resp.status_code, "text": resp.text}
