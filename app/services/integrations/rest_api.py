import httpx


class RestAPIService:
    """범용 REST API 호출 서비스"""

    async def call(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        params: dict | None = None,
        body: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=body,
            )
            response.raise_for_status()
            return {"status_code": response.status_code, "data": response.json()}
