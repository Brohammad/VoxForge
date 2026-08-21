"""Integration tests for knowledge base API."""

import io

import pytest

from voxforge.config import get_settings


@pytest.fixture(autouse=True)
def enable_knowledge(monkeypatch, tmp_path):
    monkeypatch.setenv("KNOWLEDGE_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("KNOWLEDGE_WORKER_ENABLED", "false")
    monkeypatch.setenv("KNOWLEDGE_BLOB_PATH", str(tmp_path / "kb"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_knowledge_upload_search_flow(test_client):
    coll = await test_client.post(
        "/api/v1/knowledge/collections",
        json={"name": "support-docs"},
    )
    assert coll.status_code == 201
    collection_id = coll.json()["id"]

    content = (
        b"# Refund Policy\n\n"
        b"Customers may request a full refund within 30 days of purchase. "
        b"Contact billing for enterprise accounts."
    )
    upload = await test_client.post(
        f"/api/v1/knowledge/collections/{collection_id}/documents",
        files={"file": ("refund.md", io.BytesIO(content), "text/markdown")},
        data={"title": "Refund Policy"},
    )
    assert upload.status_code == 202
    document_id = upload.json()["document_id"]

    doc = await test_client.get(f"/api/v1/knowledge/documents/{document_id}")
    assert doc.status_code == 200
    assert doc.json()["status"] == "ready"

    search = await test_client.post(
        "/api/v1/knowledge/search",
        json={
            "query": (
                "Customers may request a full refund within 30 days of purchase. "
                "Contact billing for enterprise accounts."
            ),
            "limit": 3,
            "min_similarity": 0.0,
        },
    )
    assert search.status_code == 200
    body = search.json()
    assert body["total"] >= 1
    assert body["results"][0]["citation"]["document_title"] == "Refund Policy"


@pytest.mark.asyncio
async def test_knowledge_org_isolation(test_client):
    import uuid

    resp = await test_client.get(f"/api/v1/knowledge/documents/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_list_and_delete_documents(test_client):
    coll = await test_client.post(
        "/api/v1/knowledge/collections",
        json={"name": "delete-me"},
    )
    collection_id = coll.json()["id"]

    upload = await test_client.post(
        f"/api/v1/knowledge/collections/{collection_id}/documents",
        files={"file": ("note.txt", io.BytesIO(b"hello world"), "text/plain")},
        data={"title": "Note"},
    )
    document_id = upload.json()["document_id"]

    listed = await test_client.get("/api/v1/knowledge/documents")
    assert listed.status_code == 200
    assert any(item["id"] == document_id for item in listed.json())

    by_collection = await test_client.get(
        f"/api/v1/knowledge/collections/{collection_id}/documents"
    )
    assert by_collection.status_code == 200
    assert len(by_collection.json()) == 1

    deleted = await test_client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    missing = await test_client.get(f"/api/v1/knowledge/documents/{document_id}")
    assert missing.status_code == 404

    coll_deleted = await test_client.delete(f"/api/v1/knowledge/collections/{collection_id}")
    assert coll_deleted.status_code == 200
    assert coll_deleted.json()["documents_removed"] == 0
