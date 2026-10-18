import time

import jwt

from backend.tests.conftest import asgi_request


def admin_token(expiration=None):
    payload = {"sub": "admin@example.test", "role": "admin", "iat": int(time.time())}
    if expiration is not None:
        payload["exp"] = expiration
    return jwt.encode(payload, "test-only-jwt-secret-with-more-than-32-bytes", algorithm="HS256")


def contact_payload():
    return {
        "name": "Asha Investor", "email": "asha@example.com", "phone": "+91 98765 43210",
        "investment_size": "₹1 Cr – ₹5 Cr", "subject": "Research discussion",
        "message": "Please contact me about the portfolio.",
    }


def test_missing_invalid_and_expired_admin_tokens_cannot_read_contacts(isolated_app):
    app, database = isolated_app
    for headers in ({}, {"Authorization": "Bearer definitely-invalid"},
                    {"Authorization": f"Bearer {admin_token(int(time.time()) - 1)}"}):
        status, _body = asgi_request(app, "GET", "/api/contact", headers=headers)
        assert status == 401
    assert database.contact_messages.find_calls == 0


def test_valid_admin_token_can_read_contacts_and_only_then_queries(isolated_app):
    app, database = isolated_app
    database.contact_messages.documents.append({"id": "contact-1", "name": "Asha", "email": "asha@example.com"})
    status, body = asgi_request(
        app, "GET", "/api/contact",
        headers={"Authorization": f"Bearer {admin_token(int(time.time()) + 3600)}"},
    )
    assert status == 200
    assert body[0]["id"] == "contact-1"
    assert database.contact_messages.find_calls == 1


def test_public_contact_submission_still_works_without_admin_token(isolated_app):
    app, database = isolated_app
    status, body = asgi_request(app, "POST", "/api/contact", contact_payload())
    assert status == 200
    assert body["name"] == contact_payload()["name"]
    assert database.contact_messages.insert_calls == 1


def test_contact_validation_regressions_remain(isolated_app):
    app, _database = isolated_app
    status, _body = asgi_request(app, "POST", "/api/contact", {"email": "not-an-email"})
    assert status == 422
    status, _body = asgi_request(app, "POST", "/api/contact", {"name": "   ", "email": "x@example.com"})
    assert status == 400


def test_contact_preserves_unicode_punctuation_and_multiline_text(isolated_app):
    app, database = isolated_app
    payload = {
        "name": "आशा O'Neil",
        "email": "asha+research@example.com",
        "subject": "Markets & goals — discussion",
        "message": "पहली पंक्ति & details\nSecond line — ₹50,000",
    }

    status, body = asgi_request(app, "POST", "/api/contact", payload)

    assert status == 200
    assert body["name"] == payload["name"]
    assert body["subject"] == payload["subject"]
    assert body["message"] == payload["message"]
    assert database.contact_messages.documents[0]["message"] == payload["message"]


def test_contact_rejects_oversized_request_fields_before_storage(isolated_app):
    app, database = isolated_app
    base = contact_payload()
    for field, value in (
        ("name", "A" * 121),
        ("subject", "S" * 201),
        ("message", "M" * 5001),
        ("phone", "1" * 31),
    ):
        status, _body = asgi_request(app, "POST", "/api/contact", {**base, field: value})
        assert status == 422
    assert database.contact_messages.insert_calls == 0


def test_asgi_request_preserves_plaintext_response_diagnostics():
    async def plaintext_app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 418, "headers": []})
        await send({"type": "http.response.body", "body": b"Invalid host header"})

    status, body = asgi_request(plaintext_app, "GET", "/api/contact")

    assert status == 418
    assert body == {"_non_json": True, "text": "Invalid host header"}
