from backend.tests.conftest import asgi_request


VALID = {
    "name": "Priya Sharma", "email": "priya@example.com", "phone": "+91 90000 12345",
    "services": ["Global Investing", "Portfolio Review & Stock Selection"],
    "message": "I would like to review my portfolio and discuss global exposure.",
}


def test_public_service_enquiry_submission_still_works_without_admin_token(isolated_app):
    app, database = isolated_app
    status, body = asgi_request(app, "POST", "/api/service-enquiry", VALID)
    assert status == 200
    assert body["name"] == VALID["name"]
    assert body["services"] == VALID["services"]
    assert body["source"] == "Services Page"
    assert database.service_enquiries.insert_calls == 1


def test_service_enquiry_preserves_unicode_punctuation_and_multiline_text(isolated_app):
    app, database = isolated_app
    payload = {
        **VALID,
        "name": "प्रिया Sharma",
        "message": "पहली पंक्ति & details\nSecond line — ₹50,000",
    }

    status, body = asgi_request(app, "POST", "/api/service-enquiry", payload)

    assert status == 200
    assert body["name"] == payload["name"]
    assert body["message"] == payload["message"]
    assert database.service_enquiries.documents[0]["message"] == payload["message"]


def test_service_enquiry_validation_remains(isolated_app):
    app, _database = isolated_app
    status, body = asgi_request(app, "POST", "/api/service-enquiry", {**VALID, "services": []})
    assert status == 400
    assert "service" in body["detail"].lower()
    status, _body = asgi_request(app, "POST", "/api/service-enquiry", {**VALID, "email": "bad"})
    assert status == 422


def test_service_enquiry_rejects_unknown_or_oversized_fields_before_storage(isolated_app):
    app, database = isolated_app
    invalid_payloads = [
        {**VALID, "services": ["Not a FinLit service"]},
        {**VALID, "services": ["Global Investing"] * 6},
        {**VALID, "name": "N" * 121},
        {**VALID, "phone": "1" * 31},
        {**VALID, "message": "M" * 5001},
    ]

    for payload in invalid_payloads:
        status, _body = asgi_request(app, "POST", "/api/service-enquiry", payload)
        assert status == 422
    assert database.service_enquiries.insert_calls == 0
