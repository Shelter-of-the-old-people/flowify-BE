import asyncio
from hashlib import sha256
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings

try:
    import chromadb
except ImportError:  # pragma: no cover - runtime dependency guard
    chromadb = None

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:  # pragma: no cover - runtime dependency guard
    OpenAIEmbeddings = None


DEFAULT_COLLECTION_NAME = "flowify_docs"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_PERSIST_DIRECTORY = "./chroma_data"


class VectorService:
    """ChromaDB와 OpenAI 임베딩 기반 벡터 검색 서비스."""

    def __init__(
        self,
        persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        client: Any | None = None,
        collection: Any | None = None,
        embeddings: Any | None = None,
    ) -> None:
        """벡터 저장소와 임베딩 클라이언트를 초기화합니다.

        Args:
            persist_directory: ChromaDB 영속 저장 경로
            collection_name: 사용할 ChromaDB 컬렉션 이름
            client: 테스트 또는 커스텀 실행 환경에서 주입할 Chroma client
            collection: 테스트 또는 커스텀 실행 환경에서 주입할 Chroma collection
            embeddings: 테스트 또는 커스텀 실행 환경에서 주입할 embedding client

        Raises:
            FlowifyException: 필수 벡터 검색 의존성이 설치되지 않은 경우
        """
        self._collection = collection or self._create_collection(
            client=client,
            persist_directory=persist_directory,
            collection_name=collection_name,
        )
        self._embeddings = embeddings or self._create_embeddings()

    async def add_documents(
        self,
        documents: list[str],
        metadata: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """문서를 임베딩하여 벡터 저장소에 추가합니다.

        Args:
            documents: 저장할 문서 본문 목록
            metadata: 각 문서에 연결할 메타데이터 목록
            ids: 각 문서의 고유 ID 목록

        Raises:
            FlowifyException: 입력 길이가 맞지 않거나 외부 서비스 호출이 실패한 경우
        """
        if not documents:
            return

        metadatas = metadata or [{} for _ in documents]
        doc_ids = ids or self._generate_document_ids(documents)
        self._validate_lengths(documents, metadatas, doc_ids)

        try:
            embeddings = await asyncio.to_thread(self._embeddings.embed_documents, documents)
            await asyncio.to_thread(
                self._collection.upsert,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=doc_ids,
            )
        except FlowifyException:
            raise
        except Exception as e:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="벡터 문서 저장 중 오류가 발생했습니다.",
                context={"operation": "add_documents"},
            ) from e

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """쿼리와 유사한 문서를 검색합니다.

        Args:
            query: 검색 쿼리
            top_k: 최대 검색 결과 수

        Returns:
            문서, 메타데이터, 거리 값을 포함한 검색 결과 목록

        Raises:
            FlowifyException: 검색 요청이 잘못되었거나 외부 서비스 호출이 실패한 경우
        """
        if top_k <= 0:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="top_k는 1 이상의 정수여야 합니다.",
                context={"top_k": top_k},
            )
        if not query.strip():
            return []

        try:
            count = await asyncio.to_thread(self._collection.count)
            if count <= 0:
                return []

            query_embedding = await asyncio.to_thread(self._embeddings.embed_query, query)
            results = await asyncio.to_thread(
                self._collection.query,
                query_embeddings=[query_embedding],
                n_results=min(top_k, count),
            )
        except FlowifyException:
            raise
        except Exception as e:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="벡터 문서 검색 중 오류가 발생했습니다.",
                context={"operation": "search"},
            ) from e

        return self._format_search_results(results)

    async def delete_document(self, doc_id: str) -> None:
        """벡터 저장소에서 문서를 삭제합니다.

        Args:
            doc_id: 삭제할 문서 ID

        Raises:
            FlowifyException: 문서 ID가 비었거나 외부 서비스 호출이 실패한 경우
        """
        if not doc_id.strip():
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="삭제할 문서 ID가 필요합니다.",
            )

        try:
            await asyncio.to_thread(self._collection.delete, ids=[doc_id])
        except Exception as e:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="벡터 문서 삭제 중 오류가 발생했습니다.",
                context={"operation": "delete_document", "doc_id": doc_id},
            ) from e

    @staticmethod
    def _create_collection(
        client: Any | None,
        persist_directory: str,
        collection_name: str,
    ) -> Any:
        if client is None:
            if chromadb is None:
                raise FlowifyException(
                    ErrorCode.INTERNAL_ERROR,
                    detail="chromadb 패키지가 설치되어 있지 않습니다.",
                )
            client = chromadb.PersistentClient(path=persist_directory)

        return client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _create_embeddings() -> Any:
        if OpenAIEmbeddings is None:
            raise FlowifyException(
                ErrorCode.INTERNAL_ERROR,
                detail="langchain-openai 패키지가 설치되어 있지 않습니다.",
            )

        return OpenAIEmbeddings(
            model=DEFAULT_EMBEDDING_MODEL,
            api_key=settings.LLM_API_KEY,
        )

    @staticmethod
    def _generate_document_ids(documents: list[str]) -> list[str]:
        return [
            f"doc_{index}_{sha256(document.encode('utf-8')).hexdigest()[:16]}"
            for index, document in enumerate(documents)
        ]

    @staticmethod
    def _validate_lengths(documents: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if len(metadatas) != len(documents):
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="metadata 개수는 documents 개수와 같아야 합니다.",
                context={
                    "documents": len(documents),
                    "metadata": len(metadatas),
                },
            )
        if len(ids) != len(documents):
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="ids 개수는 documents 개수와 같아야 합니다.",
                context={
                    "documents": len(documents),
                    "ids": len(ids),
                },
            )

    @staticmethod
    def _format_search_results(results: dict) -> list[dict]:
        documents = (results.get("documents") or [[]])[0]
        if not documents:
            return []

        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        formatted = []
        for index, document in enumerate(documents):
            formatted.append(
                {
                    "document": document,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return formatted
