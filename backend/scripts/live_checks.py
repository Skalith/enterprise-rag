"""Live HTTP regression checks for the pending backend items.

Run against a running stack (backend on :8011, celery worker, redis, qdrant, minio):

    cd backend && venv/bin/python -m scripts.live_checks
    venv/bin/python -m scripts.live_checks --fast        # skip the LLM-backed positive control
    venv/bin/python -m scripts.live_checks --only rbac   # auth | rbac | evaluation | documents | ratelimit

Covers:
  auth        signup -> signin -> logout revokes access+refresh, forgot/reset
              rotates the password, kills old sessions and is single-use.
  rbac        employee without grants gets the "do not have access" answer, no leak
              of the protected document; granted user does retrieve it.
  evaluation  POST /evaluation/run as a user with no documents -> 409, no run persisted.
  documents   download -> reindex -> delete, with vector + object + permission cleanup.
  ratelimit   429 + Retry-After for the chat and auth scopes over real HTTP.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE = "http://localhost:8011"
API = f"{BASE}/api/v1"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin@12345"
STAMP = uuid.uuid4().hex[:8]

RESULTS: List[Tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return bool(ok)


def register(email: str, password: str, role: str = "employee") -> Dict[str, Any]:
    res = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": "Live Check", "role": role},
        timeout=30,
    )
    res.raise_for_status()
    return res.json()


def login(email: str, password: str) -> Dict[str, Any]:
    res = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    res.raise_for_status()
    return res.json()


def auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wait_for_status(token: str, doc_id: int, want: str = "indexed", timeout: float = 90) -> str:
    deadline = time.time() + timeout
    status = "?"
    while time.time() < deadline:
        res = requests.get(f"{API}/documents/{doc_id}", headers=auth(token), timeout=30)
        if res.status_code == 200:
            status = res.json().get("status", "?")
            if status == want:
                return status
            if status in {"failed", "deleted"}:
                return status
        time.sleep(2)
    return status


def qdrant_points_for(document_id: int) -> int:
    res = requests.post(
        "http://localhost:6333/collections/enterprise_docs/points/count",
        json={
            "filter": {
                "must": [{"key": "document_id", "match": {"value": int(document_id)}}]
            },
            "exact": True,
        },
        timeout=15,
    )
    res.raise_for_status()
    return int(res.json()["result"]["count"])


def new_user(role: str = "employee", prefix: str = "probe") -> Dict[str, Any]:
    email = f"{prefix}_{role}_{STAMP}_{uuid.uuid4().hex[:4]}@example.com"
    tokens = register(email, "Probe@12345", role=role)
    me = requests.get(f"{API}/auth/me", headers=auth(tokens["access_token"]), timeout=30).json()
    return {"email": email, "tokens": tokens, "me": me}


# --------------------------------------------------------------------------- rbac


def check_rbac(fast: bool) -> None:
    admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)["access_token"]

    docs = requests.get(f"{API}/documents", headers=auth(admin), timeout=30).json()
    candidates = [
        d for d in docs
        if "policy" in (d.get("original_filename") or "").lower() and d.get("status") == "indexed"
    ]
    # Older policy uploads may sit in the index without vectors; pick one that really has content.
    policy = None
    for cand in candidates:
        chunks = requests.get(
            f"{API}/documents/{cand['id']}/chunks", headers=auth(admin), timeout=30
        ).json()
        text = " ".join(c.get("content", "") for c in chunks.get("chunks", [])).lower()
        if chunks.get("total_chunks", 0) > 0 and ("annual leave" in text or "20 days" in text):
            policy = cand
            break

    if policy is None:
        check("rbac: protected policy document exists and is indexed", False, "no indexed policy doc")
        return
    doc_id = policy["id"]

    # Guard against a vacuous pass: the protected content must actually be in the index.
    chunks = requests.get(f"{API}/documents/{doc_id}/chunks", headers=auth(admin), timeout=30).json()
    chunk_text = " ".join(c.get("content", "") for c in chunks.get("chunks", []))
    check(
        "rbac: protected content is indexed",
        chunks.get("total_chunks", 0) > 0 and ("annual leave" in chunk_text.lower() or "20 days" in chunk_text),
        f"doc {doc_id}, chunks={chunks.get('total_chunks')}",
    )

    emp = new_user("employee", prefix="rbac")
    emp_token = emp["tokens"]["access_token"]
    perms = set(emp["me"].get("permissions", []))
    check(
        "rbac: employee role is least-privilege",
        "perform_chat" in perms and "manage_users" not in perms and "delete_document" not in perms,
        ",".join(sorted(perms)),
    )

    # Employee must not be able to read the protected document directly.
    res = requests.get(f"{API}/documents/{doc_id}", headers=auth(emp_token), timeout=30)
    check("rbac: employee GET /documents/{id} -> 403", res.status_code == 403, str(res.status_code))
    res = requests.get(f"{API}/documents/{doc_id}/chunks", headers=auth(emp_token), timeout=30)
    check("rbac: employee GET /documents/{id}/chunks -> 403", res.status_code == 403, str(res.status_code))
    res = requests.get(f"{API}/documents/{doc_id}/download", headers=auth(emp_token), timeout=30)
    check("rbac: employee GET /documents/{id}/download -> 403", res.status_code == 403, str(res.status_code))

    # The core claim: chat must answer with the no-access message, zero sources.
    res = requests.post(
        f"{API}/chat",
        headers=auth(emp_token),
        json={"question": "How many annual leave days do new employees get? Cite your sources."},
        timeout=240,
    )
    body = res.json() if res.status_code == 200 else {}
    answer = (body.get("answer") or "").lower()
    check("rbac: chat status 200", res.status_code == 200, str(res.status_code))
    check(
        "rbac: chat returns the no-access answer",
        "do not have access" in answer,
        (body.get("answer") or "")[:90],
    )
    check("rbac: chat leaks no sources", body.get("sources") == [], str(body.get("sources")))
    check(
        "rbac: protected answer text is absent",
        "20 days" not in answer and "twenty" not in answer,
        answer[:90],
    )

    # Employee's own document is visible to them; unrelated question must not leak doc 42.
    own = requests.post(
        f"{API}/documents/upload",
        headers=auth(emp_token),
        files={"file": ("office_notes.txt", b"The coffee machine is cleaned every Friday afternoon.", "text/plain")},
        timeout=60,
    )
    if own.status_code == 200:
        own_id = own.json()["id"]
        status = wait_for_status(emp_token, own_id)
        check("rbac: employee upload gets indexed", status == "indexed", f"doc {own_id} -> {status}")
        res = requests.post(
            f"{API}/chat",
            headers=auth(emp_token),
            json={"question": "How many annual leave days do new employees get? Cite your sources."},
            timeout=240,
        )
        body = res.json() if res.status_code == 200 else {}
        src_ids = {s.get("document_id") for s in body.get("sources", [])}
        answer = (body.get("answer") or "").lower()
        check(
            "rbac: employee retrieval is confined to their own document",
            src_ids.issubset({own_id}),
            f"sources={sorted(x for x in src_ids if x is not None)} own={own_id}",
        )
        check(
            "rbac: no policy leak with partial access",
            "20 days" not in answer and "twenty" not in answer,
            answer[:90],
        )
    else:
        check("rbac: employee upload accepted", False, f"{own.status_code} {own.text[:120]}")

    # Positive control: an explicit grant makes the same document retrievable.
    grant = requests.post(
        f"{API}/admin/document-permissions/{doc_id}",
        headers=auth(admin),
        json={"user_id": emp["me"]["id"], "can_view": True, "can_download": True},
        timeout=30,
    )
    check("rbac: admin grants access over HTTP", grant.status_code == 200, f"{grant.status_code} {grant.text[:120]}")

    listed = requests.get(
        f"{API}/admin/document-permissions/{doc_id}", headers=auth(admin), timeout=30
    ).json()
    check(
        "rbac: grant is listed",
        any(g.get("user_id") == emp["me"]["id"] for g in listed.get("grants", [])),
        str(listed.get("grants")),
    )

    if fast:
        print("SKIP  rbac: positive control (granted chat) [--fast]")
        return

    res = requests.post(
        f"{API}/chat",
        headers=auth(emp_token),
        json={"question": "How many annual leave days do new employees get? Cite your sources."},
        timeout=240,
    )
    body = res.json() if res.status_code == 200 else {}
    src_ids = {s.get("document_id") for s in body.get("sources", [])}
    check(
        "rbac: granted user retrieves the protected document",
        doc_id in src_ids,
        f"sources={sorted(x for x in src_ids if x is not None)}",
    )

    # And the grant can be revoked again.
    revoke = requests.delete(
        f"{API}/admin/document-permissions/{doc_id}",
        params={"user_id": emp["me"]["id"]},
        headers=auth(admin),
        timeout=30,
    )
    check("rbac: admin revokes access over HTTP", revoke.status_code == 200, str(revoke.status_code))
    res = requests.get(f"{API}/documents/{doc_id}", headers=auth(emp_token), timeout=30)
    check("rbac: revoked user loses document access", res.status_code == 403, str(res.status_code))


# ------------------------------------------------------------------------- auth


def check_auth() -> None:
    """signup -> signin -> forgot/reset -> logout revocation."""
    email = f"auth_{STAMP}_{uuid.uuid4().hex[:4]}@example.com"
    password = "SignupPass123"
    new_password = "ResetPass456"

    # 1. signup mints a usable token pair.
    res = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": "Live Auth"},
        timeout=30,
    )
    check("auth: signup accepted", res.status_code == 200, f"{res.status_code} {res.text[:120]}")
    if res.status_code != 200:
        return
    first = res.json()

    # 2. signin with the same credentials.
    res = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    check("auth: signin accepted", res.status_code == 200, str(res.status_code))
    signed_in = res.json() if res.status_code == 200 else first
    me = requests.get(f"{API}/auth/me", headers=auth(signed_in["access_token"]), timeout=30)
    check(
        "auth: signin token reaches /auth/me",
        me.status_code == 200 and me.json().get("email") == email,
        f"{me.status_code} {me.json().get('email') if me.status_code == 200 else me.text[:80]}",
    )

    # 3. forgot-password answers identically for known and unknown accounts.
    unknown = requests.post(
        f"{API}/auth/forgot-password", json={"email": "definitely-not-a-user@example.com"}, timeout=30
    )
    known = requests.post(f"{API}/auth/forgot-password", json={"email": email}, timeout=30)
    check(
        "auth: forgot-password does not reveal account existence",
        unknown.status_code == 200
        and known.status_code == 200
        and unknown.json().get("message") == known.json().get("message"),
        f"{unknown.status_code}/{known.status_code}",
    )
    check("auth: forgot-password hides token for unknown email", "dev_reset_token" not in unknown.json(), "")
    reset_token = known.json().get("dev_reset_token")
    check("auth: forgot-password returns the dev reset token", bool(reset_token), bool(reset_token))

    # 4. the token rotates the password.
    res = requests.post(
        f"{API}/auth/reset-password",
        json={"token": reset_token or "", "password": new_password},
        timeout=30,
    )
    check("auth: reset-password accepted", res.status_code == 200, f"{res.status_code} {res.text[:120]}")

    res = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    check("auth: old password no longer works", res.status_code == 401, str(res.status_code))

    res = requests.post(f"{API}/auth/login", json={"email": email, "password": new_password}, timeout=30)
    check("auth: new password works", res.status_code == 200, str(res.status_code))
    rotated = res.json() if res.status_code == 200 else {}

    # Sessions issued before the reset are invalidated by the token_version bump.
    res = requests.get(f"{API}/auth/me", headers=auth(first["access_token"]), timeout=30)
    check("auth: pre-reset session is invalid", res.status_code == 401, str(res.status_code))

    # Single-use link.
    res = requests.post(
        f"{API}/auth/reset-password",
        json={"token": reset_token or "", "password": "AnotherPass789"},
        timeout=30,
    )
    check("auth: reset token cannot be reused", res.status_code == 400, str(res.status_code))

    # 5. logout revokes the access token and the refresh token.
    if rotated:
        out = requests.post(
            f"{API}/auth/logout",
            headers=auth(rotated["access_token"]),
            json={"refresh_token": rotated.get("refresh_token")},
            timeout=30,
        )
        revoked = set(out.json().get("revoked", [])) if out.status_code == 200 else set()
        check(
            "auth: logout revokes access and refresh tokens",
            out.status_code == 200 and revoked == {"access", "refresh"},
            f"{out.status_code} {sorted(revoked)}",
        )
        res = requests.get(f"{API}/auth/me", headers=auth(rotated["access_token"]), timeout=30)
        check("auth: revoked access token is rejected", res.status_code == 401, str(res.status_code))
        res = requests.post(
            f"{API}/auth/refresh",
            json={"refresh_token": rotated.get("refresh_token")},
            timeout=30,
        )
        check("auth: revoked refresh token cannot be replayed", res.status_code == 401, str(res.status_code))

        # Signing in again still works: logout kills only the presented tokens.
        res = requests.post(
            f"{API}/auth/login", json={"email": email, "password": new_password}, timeout=30
        )
        fresh = res.json() if res.status_code == 200 else {}
        ok = bool(fresh.get("access_token")) and (
            requests.get(
                f"{API}/auth/me", headers=auth(fresh["access_token"]), timeout=30
            ).status_code
            == 200
        )
        check("auth: user can sign in again after logout", ok, str(res.status_code))


# --------------------------------------------------------------------- evaluation


def check_evaluation() -> None:
    admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)["access_token"]

    before = requests.get(f"{API}/evaluation/runs", headers=auth(admin), timeout=30).json()
    before_count = len(before) if isinstance(before, list) else 0

    # Self-registration only mints employee/manager, so elevate explicitly via the admin API.
    user = new_user("employee", prefix="eval")
    grant = requests.post(
        f"{API}/admin/users/{user['me']['id']}/roles/admin",
        headers=auth(admin),
        timeout=30,
    )
    check("evaluation: admin role granted over HTTP", grant.status_code == 200, str(grant.status_code))
    token = user["tokens"]["access_token"]
    me = requests.get(f"{API}/auth/me", headers=auth(token), timeout=30).json()
    check(
        "evaluation: no-doc user can reach the endpoint (has view_evaluation_metrics)",
        "view_evaluation_metrics" in me.get("permissions", []),
        ",".join(me.get("permissions", [])),
    )

    res = requests.post(f"{API}/evaluation/run", headers=auth(token), json={}, timeout=120)
    detail = ""
    if res.headers.get("content-type", "").startswith("application/json"):
        detail = str(res.json().get("detail", ""))[:100]
    else:
        detail = res.text[:100]
    check("evaluation: no-doc run -> 409", res.status_code == 409, f"{res.status_code} {detail}")
    check(
        "evaluation: 409 explains the empty result",
        "no indexed documents" in detail or "Nothing was evaluated" in detail,
        detail,
    )

    after = requests.get(f"{API}/evaluation/runs", headers=auth(admin), timeout=30).json()
    after_count = len(after) if isinstance(after, list) else 0
    check(
        "evaluation: failed run is not persisted",
        after_count == before_count,
        f"before={before_count} after={after_count}",
    )


# ----------------------------------------------------------------------- documents


def check_documents() -> None:
    admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)["access_token"]
    marker = f"lifecycle-marker-{uuid.uuid4().hex}"
    content = f"Enterprise lifecycle probe. {marker}\nSecond line for byte equality.\n"

    res = requests.post(
        f"{API}/documents/upload",
        headers=auth(admin),
        files={"file": ("lifecycle_probe.txt", content.encode(), "text/plain")},
        timeout=60,
    )
    if res.status_code != 200:
        check("documents: upload accepted", False, f"{res.status_code} {res.text[:150]}")
        return
    doc_id = res.json()["id"]
    check("documents: upload accepted", True, f"doc {doc_id}")

    # Capture the storage key before deletion; it is not exposed by DocumentOut.
    from app.database import SessionLocal
    from app.models import Document as DocumentModel
    from app.models import DocumentPermission

    db = SessionLocal()
    try:
        s3_key = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first().s3_key
    finally:
        db.close()

    status = wait_for_status(admin, doc_id)
    check("documents: ingestion reaches indexed", status == "indexed", status)

    # download
    res = requests.get(f"{API}/documents/{doc_id}/download", headers=auth(admin), timeout=60)
    ok = res.status_code == 200 and res.content.decode(errors="replace") == content
    check("documents: download returns the exact stored bytes", ok, f"{res.status_code} {len(res.content)}B")

    chunks = requests.get(f"{API}/documents/{doc_id}/chunks", headers=auth(admin), timeout=30).json()
    total = chunks.get("total_chunks", 0)
    points = qdrant_points_for(doc_id)
    check("documents: chunks visible after ingestion", total >= 1, f"chunks={total} qdrant={points}")
    check("documents: qdrant point count matches", points == total, f"chunks={total} qdrant={points}")

    # reindex
    res = requests.post(f"{API}/documents/{doc_id}/reindex", headers=auth(admin), timeout=30)
    check("documents: reindex accepted", res.status_code == 200, str(res.status_code))
    status = wait_for_status(admin, doc_id)
    check("documents: reindex reaches indexed again", status == "indexed", status)
    chunks = requests.get(f"{API}/documents/{doc_id}/chunks", headers=auth(admin), timeout=30).json()
    total_after = chunks.get("total_chunks", 0)
    points_after = qdrant_points_for(doc_id)
    check(
        "documents: reindex does not duplicate vectors",
        total_after == total and points_after == total_after,
        f"before={total} after={total_after} qdrant={points_after}",
    )

    # delete
    res = requests.delete(f"{API}/documents/{doc_id}", headers=auth(admin), timeout=60)
    ok_body: Dict[str, Any] = res.json() if res.status_code == 200 else {}
    check("documents: delete accepted", res.status_code == 200 and ok_body.get("ok") is True, str(res.status_code))
    check("documents: delete reports no storage error", not ok_body.get("storage_error"), str(ok_body.get("storage_error")))

    points_after_delete = qdrant_points_for(doc_id)
    check("documents: vectors removed", points_after_delete == 0, f"qdrant={points_after_delete}")

    res = requests.get(f"{API}/documents/{doc_id}", headers=auth(admin), timeout=30)
    check("documents: deleted document is 404", res.status_code == 404, str(res.status_code))
    res = requests.get(f"{API}/documents/{doc_id}/chunks", headers=auth(admin), timeout=30)
    check("documents: deleted chunks are 404", res.status_code == 404, str(res.status_code))

    from botocore.exceptions import ClientError

    from app.config import settings
    from app.routers.documents import s3_client

    object_gone = False
    try:
        s3_client().head_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        object_gone = str(code) in {"404", "NoSuchKey", "NotFound"}
    check("documents: object removed from storage", object_gone, f"key={s3_key}")

    logs = requests.get(
        f"{API}/admin/audit-logs",
        headers=auth(admin),
        params={"action": "delete_document", "limit": 1},
        timeout=30,
    ).json()
    detail = logs[0].get("details", {}) if logs else {}
    check(
        "documents: delete audit records vector removal",
        detail.get("vectors_removed") is True,
        str(detail),
    )

    db = SessionLocal()
    try:
        remaining = db.query(DocumentPermission).filter(DocumentPermission.document_id == doc_id).count()
    finally:
        db.close()
    check("documents: permissions cleaned up", remaining == 0, f"grants={remaining}")


# ----------------------------------------------------------------------- ratelimit


def check_ratelimit() -> None:
    # chat scope: burst with a user that has no documents so every call returns instantly.
    user = new_user("employee", prefix="burst")
    token = user["tokens"]["access_token"]

    allowed = 0
    limited: Optional[requests.Response] = None
    for i in range(25):
        res = requests.post(
            f"{API}/chat",
            headers=auth(token),
            json={"question": "ping"},
            timeout=60,
        )
        if res.status_code == 429:
            limited = res
            break
        if res.status_code == 200:
            allowed += 1
    if limited is None:
        # Window may have rolled over mid-burst; wait for a clean window and retry once.
        time.sleep(61)
        for i in range(25):
            res = requests.post(
                f"{API}/chat", headers=auth(token), json={"question": "ping"}, timeout=60
            )
            if res.status_code == 429:
                limited = res
                break
            if res.status_code == 200:
                allowed += 1

    check("ratelimit: chat burst eventually returns 429", limited is not None, f"allowed={allowed}")
    if limited is not None:
        retry_after = limited.headers.get("Retry-After")
        check("ratelimit: chat 429 carries Retry-After", bool(retry_after), str(retry_after))
        try:
            body = limited.json()
        except Exception:
            body = {}
        check(
            "ratelimit: chat 429 body names the limit",
            "Rate limit exceeded" in str(body.get("detail", "")),
            str(body.get("detail", ""))[:80],
        )
        check("ratelimit: chat allowed count respects the limit", allowed <= 20, f"allowed={allowed}")

    # auth scope: 10/min, wrong credentials still consume the budget.
    limited = None
    for _ in range(15):
        res = requests.post(
            f"{API}/auth/login",
            json={"email": "definitely-not-a-user@example.com", "password": "nope"},
            timeout=30,
        )
        if res.status_code == 429:
            limited = res
            break
    check("ratelimit: auth burst returns 429", limited is not None, "")
    if limited is not None:
        retry_after = limited.headers.get("Retry-After")
        check("ratelimit: auth 429 carries Retry-After", bool(retry_after), str(retry_after))


# ------------------------------------------------------------------------- driver


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="skip the LLM-backed positive control")
    parser.add_argument(
        "--only",
        choices=["auth", "rbac", "evaluation", "documents", "ratelimit"],
        action="append",
        help="run only the named group (repeatable)",
    )
    args = parser.parse_args()
    groups = args.only or ["auth", "rbac", "evaluation", "documents", "ratelimit"]

    try:
        requests.get(f"{BASE}/health", timeout=10).raise_for_status()
    except Exception as exc:
        print(f"Backend is not healthy at {BASE}/health: {exc}")
        return 2

    if "auth" in groups:
        print("\n--- auth ---")
        check_auth()
    if "rbac" in groups:
        print("\n--- rbac ---")
        check_rbac(fast=args.fast)
    if "evaluation" in groups:
        print("\n--- evaluation ---")
        check_evaluation()
    if "documents" in groups:
        print("\n--- documents ---")
        check_documents()
    if "ratelimit" in groups:
        print("\n--- ratelimit ---")
        check_ratelimit()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for name, _, detail in failed:
        print(f"  FAILED: {name} [{detail}]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
