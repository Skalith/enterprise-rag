"""Integration tests: auth -> upload (S3 stubbed) -> chat (provider stubbed)."""

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from app.models import Document, LLMConfig, Message, User
from app.rag.provider_interface import LLMProvider


class StubProvider(LLMProvider):
    provider_name = "stub"

    async def generate(
        self,
        system_prompt: str,
        question: str,
        context: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        return "Stub answer grounded in document data about annual leave."

    def health(self) -> bool:
        return True


class FakeS3Client:
    def head_bucket(self, Bucket):
        raise ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}}, "HeadBucket"
        )

    def create_bucket(self, Bucket):
        return {}

    def put_object(self, Bucket, Key, Body):
        return {}


@pytest.fixture()
def stub_s3(monkeypatch):
    import app.routers.documents as documents_router
    import app.workers.tasks as tasks_module

    monkeypatch.setattr(documents_router, "s3_client", lambda: FakeS3Client())
    monkeypatch.setattr(documents_router, "ensure_bucket", lambda client: None)
    # The route imports process_document from app.workers.tasks at call time.
    monkeypatch.setattr(
        tasks_module,
        "process_document",
        SimpleNamespace(delay=lambda *a, **k: None),
    )


@pytest.fixture()
def stub_rag(monkeypatch):
    import app.services.rag_service as rag_service
    import app.rag.retriever as retriever

    monkeypatch.setattr(rag_service, "get_provider", lambda name, model=None: StubProvider())
    monkeypatch.setattr(rag_service, "embed_query", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        rag_service,
        "retrieve",
        lambda vector, allowed, top_k=5, min_score=None: [
            SimpleNamespace(
                score=0.95,
                payload={
                    "text": "Annual leave: new employees receive 20 days per year.",
                    "document_id": allowed[0] if allowed else 1,
                    "chunk_index": 0,
                    "page": 2,
                    "sheet": None,
                },
            )
        ],
    )
    monkeypatch.setattr(retriever, "ensure_collection", lambda force=False: None)


def test_register_and_me(client, register_user):
    email, _, token = register_user()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == email
    assert "perform_chat" in body["permissions"]


def test_register_cannot_mint_admin(client):
    email = f"admin_attempt_{__import__('uuid').uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "role": "super_admin"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert "super_admin" not in me.get("roles", [])
    assert "manage_users" not in me.get("permissions", [])


def test_login_wrong_password(client, register_user):
    email, password, _ = register_user()
    bad = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    assert bad.status_code == 401
    good = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert good.status_code == 200
    assert "access_token" in good.json()


def test_chat_without_documents_returns_honest_message(client, register_user):
    _, _, token = register_user()
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How many vacation days do I get?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "do not have access" in body["answer"].lower() or "could not find" in body["answer"].lower()
    assert body["sources"] == []


def test_upload_invalid_mime_rejected(client, register_user):
    _, _, token = register_user()
    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_upload_empty_file_rejected(client, register_user):
    _, _, token = register_user()
    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_and_chat_with_stubbed_pipeline(client, register_user, stub_s3, stub_rag, db_session):
    email, _, token = register_user()
    headers = {"Authorization": f"Bearer {token}"}

    upload = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("handbook.txt", b"Annual leave policy for new employees.", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    doc_id = upload.json()["id"]
    assert upload.json()["status"] == "queued"

    # Mark indexed so RBAC retrieval would include it if rag path runs fully.
    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    doc.status = "indexed"
    db_session.commit()

    chat = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "How many days of annual leave do I get? Please cite your sources"},
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["answer"]
    assert body["conversation_id"]
    assert body["message_id"]

    messages = (
        db_session.query(Message)
        .filter(Message.id == body["message_id"])
        .first()
    )
    assert messages is not None
    assert messages.role == "assistant"

    listed = client.get("/api/v1/documents", headers=headers)
    assert listed.status_code == 200
    assert any(d["id"] == doc_id for d in listed.json())


def test_duplicate_upload_rejected(client, register_user, stub_s3):
    _, _, token = register_user()
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("dup.txt", b"unique content for checksum", "text/plain")}
    first = client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert second.status_code == 409


def test_chat_persists_conversation(client, register_user):
    _, _, token = register_user()
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "What is the vacation policy?"},
    )
    assert first.status_code == 200
    conv_id = first.json()["conversation_id"]

    second = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "How many days is that?", "conversation_id": conv_id},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conv_id

    history = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert len(messages) >= 2
