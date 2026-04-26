from unittest.mock import MagicMock

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.vector_service import VectorService


@pytest.fixture()
def vector_service():
    """테스트용 VectorService와 mock 의존성을 생성합니다."""
    collection = MagicMock()
    embeddings = MagicMock()
    client = MagicMock()
    client.get_or_create_collection.return_value = collection

    service = VectorService(client=client, embeddings=embeddings)
    return service, collection, embeddings, client


async def test_add_documents_upserts_embeddings(vector_service):
    """문서 추가 시 임베딩 생성 후 ChromaDB upsert가 호출되는지 검증합니다."""
    service, collection, embeddings, _ = vector_service
    documents = ["첫 번째 문서", "두 번째 문서"]
    metadatas = [{"source": "test"}, {"source": "test"}]
    ids = ["doc_1", "doc_2"]
    embeddings.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]

    await service.add_documents(documents, metadata=metadatas, ids=ids)

    embeddings.embed_documents.assert_called_once_with(documents)
    collection.upsert.assert_called_once_with(
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )


async def test_add_documents_empty_documents_noop(vector_service):
    """문서 목록이 비어 있으면 외부 호출 없이 종료되는지 검증합니다."""
    service, collection, embeddings, _ = vector_service

    await service.add_documents([])

    embeddings.embed_documents.assert_not_called()
    collection.upsert.assert_not_called()


async def test_add_documents_metadata_length_mismatch_raises(vector_service):
    """metadata 개수가 documents 개수와 다르면 INVALID_REQUEST가 발생합니다."""
    service, _, _, _ = vector_service

    with pytest.raises(FlowifyException) as exc_info:
        await service.add_documents(["문서 1", "문서 2"], metadata=[{"source": "test"}])

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_add_documents_ids_length_mismatch_raises(vector_service):
    """ids 개수가 documents 개수와 다르면 INVALID_REQUEST가 발생합니다."""
    service, _, _, _ = vector_service

    with pytest.raises(FlowifyException) as exc_info:
        await service.add_documents(["문서 1", "문서 2"], ids=["doc_1"])

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_search_returns_formatted_results(vector_service):
    """검색 결과를 document, metadata, distance 딕셔너리 목록으로 변환합니다."""
    service, collection, embeddings, _ = vector_service
    collection.count.return_value = 2
    embeddings.embed_query.return_value = [0.1, 0.2]
    collection.query.return_value = {
        "documents": [["문서 A", "문서 B"]],
        "metadatas": [[{"source": "a"}, {"source": "b"}]],
        "distances": [[0.12, 0.34]],
    }

    results = await service.search("검색어", top_k=5)

    embeddings.embed_query.assert_called_once_with("검색어")
    collection.query.assert_called_once_with(
        query_embeddings=[[0.1, 0.2]],
        n_results=2,
    )
    assert results == [
        {"document": "문서 A", "metadata": {"source": "a"}, "distance": 0.12},
        {"document": "문서 B", "metadata": {"source": "b"}, "distance": 0.34},
    ]


async def test_search_empty_collection_returns_empty_list(vector_service):
    """저장된 문서가 없으면 빈 리스트를 반환합니다."""
    service, collection, embeddings, _ = vector_service
    collection.count.return_value = 0

    results = await service.search("검색어")

    assert results == []
    embeddings.embed_query.assert_not_called()
    collection.query.assert_not_called()


async def test_search_empty_query_returns_empty_list(vector_service):
    """검색어가 비어 있으면 외부 호출 없이 빈 리스트를 반환합니다."""
    service, collection, embeddings, _ = vector_service

    results = await service.search("   ")

    assert results == []
    collection.count.assert_not_called()
    embeddings.embed_query.assert_not_called()


async def test_search_invalid_top_k_raises(vector_service):
    """top_k가 1보다 작으면 INVALID_REQUEST가 발생합니다."""
    service, _, _, _ = vector_service

    with pytest.raises(FlowifyException) as exc_info:
        await service.search("검색어", top_k=0)

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_search_external_error_is_wrapped(vector_service):
    """벡터 저장소 검색 실패는 EXTERNAL_API_ERROR로 래핑됩니다."""
    service, collection, _, _ = vector_service
    collection.count.side_effect = RuntimeError("chroma unavailable")

    with pytest.raises(FlowifyException) as exc_info:
        await service.search("검색어")

    assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR


async def test_delete_document_deletes_by_id(vector_service):
    """문서 ID로 벡터 저장소 delete가 호출되는지 검증합니다."""
    service, collection, _, _ = vector_service

    await service.delete_document("doc_1")

    collection.delete.assert_called_once_with(ids=["doc_1"])


async def test_delete_document_empty_id_raises(vector_service):
    """문서 ID가 비어 있으면 INVALID_REQUEST가 발생합니다."""
    service, _, _, _ = vector_service

    with pytest.raises(FlowifyException) as exc_info:
        await service.delete_document(" ")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
