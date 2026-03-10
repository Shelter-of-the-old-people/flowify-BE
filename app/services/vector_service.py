class VectorService:
    """FAISS/Chroma 기반 벡터 검색 서비스"""

    def __init__(self):
        # TODO: FAISS or Chroma 벡터 스토어 초기화
        pass

    async def add_documents(self, documents: list[str], metadata: list[dict] | None = None) -> None:
        """문서를 벡터 스토어에 추가"""
        # TODO: 임베딩 생성 후 벡터 스토어에 저장
        pass

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """유사도 검색"""
        # TODO: 쿼리 임베딩 → 벡터 검색
        return []
