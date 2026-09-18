"""
验证 RadarNewsChunkStore.ensure_collection 在同一实例上只真正检查一次。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.infrastructure.milvus.radar_news_chunk_store import RadarNewsChunkStore


def test_ensure_collection_short_circuits_after_first_success() -> None:
    """
        首次 ensure 会连客户端并校验；之后 delete/upsert 路径再调 ensure 应短路。
    """
    store = RadarNewsChunkStore(
        uri="http://127.0.0.1:19530",
        user="u",
        password="p",
        db_name="test_db",
        collection="radar_company_news_chunk",
        dim=8,
    )
    mock_client = MagicMock()
    mock_client.has_collection.return_value = True
    mock_client.describe_collection.return_value = {
        "fields": [
            {"name": "chunk_id"},
            {"name": "content_grade"},
            {"name": "source_kind"},
        ]
    }

    with patch.object(store, "_get_client", return_value=mock_client) as get_client:
        assert store.ensure_collection() is False
        calls_after_first = get_client.call_count
        assert mock_client.has_collection.call_count == 1
        assert store._ensured is True

        assert store.ensure_collection() is False
        assert store.ensure_collection() is False

        # 后续短路：不再访问客户端 / has_collection
        assert get_client.call_count == calls_after_first
        assert mock_client.has_collection.call_count == 1


def test_delete_then_upsert_only_ensures_once() -> None:
    """同一次写入链路里 delete + upsert 各调 ensure，但远程检查只发生一次。"""
    store = RadarNewsChunkStore(
        uri="http://127.0.0.1:19530",
        user="u",
        password="p",
        db_name="test_db",
        collection="radar_company_news_chunk",
        dim=2,
    )
    mock_client = MagicMock()
    mock_client.has_collection.return_value = True
    mock_client.describe_collection.return_value = {
        "fields": [
            {"name": "chunk_id"},
            {"name": "content_grade"},
            {"name": "source_kind"},
        ]
    }

    with patch.object(store, "_get_client", return_value=mock_client):
        store.delete_by_doc_id(1)
        store.upsert_chunks(
            [
                {
                    "doc_id": 1,
                    "company_id": 10,
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "char_start": 0,
                    "char_end": 1,
                    "title": "t",
                    "summary": "s",
                    "url": "http://x",
                    "embed_text": "t\ns",
                    "embedding": [0.1, 0.2],
                    "content_grade": "stub",
                    "source_kind": "news_html",
                }
            ]
        )

    assert mock_client.has_collection.call_count == 1
    mock_client.delete.assert_called_once()
    mock_client.upsert.assert_called_once()
