import asyncio
import json
import os
from types import SimpleNamespace

import pytest


# Keep the application import deterministic and never use project credentials in tests.
os.environ["MONGO_URL"] = "mongodb://test-mongo.invalid:27017"
os.environ["DB_NAME"] = "finlit_test"
os.environ["CMS_JWT_SECRET"] = "test-only-jwt-secret-with-more-than-32-bytes"
os.environ["CMS_ADMIN_EMAIL"] = "admin@example.test"
os.environ["CMS_ADMIN_PASSWORD_HASH"] = "not-used-by-these-tests"
os.environ["RESEND_API_KEY"] = "test-resend-key"
os.environ["CONTACT_RECIPIENT_EMAIL"] = "owner@example.com"

from backend import server


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit):
        return [dict(document) for document in self.documents]


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.find_calls = 0
        self.insert_calls = 0

    async def insert_one(self, document):
        self.insert_calls += 1
        self.documents.append(dict(document))
        return SimpleNamespace(inserted_id=document.get("id"))

    def find(self, *_args, **_kwargs):
        self.find_calls += 1
        return FakeCursor(self.documents)


class FakeDatabase:
    def __init__(self):
        self.contact_messages = FakeCollection()
        self.service_enquiries = FakeCollection()


@pytest.fixture
def isolated_app(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(server, "db", database)

    async def fake_contact_email(_lead, auto_reply=True):
        return "test-contact-email-id"

    async def fake_service_email(_enquiry):
        return "test-service-email-id"

    monkeypatch.setattr(server, "send_lead_emails", fake_contact_email)
    monkeypatch.setattr(server, "send_service_enquiry_email", fake_service_email)
    return server.app, database


def asgi_request(app, method, path, payload=None, headers=None):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    request_header_values = {key.lower(): value for key, value in (headers or {}).items()}
    request_header_values["host"] = "localhost"
    request_header_values.setdefault("content-type", "application/json")
    request_headers = [(key.encode(), value.encode()) for key, value in request_header_values.items()]
    messages = []
    sent_body = False
    response_finished = asyncio.Event()

    async def receive():
        nonlocal sent_body
        if sent_body:
            await response_finished.wait()
            return {"type": "http.disconnect"}
        sent_body = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body":
            response_finished.set()

    scope = {
        "type": "http", "http_version": "1.1", "method": method,
        "path": path, "raw_path": path.encode(), "query_string": b"",
        "headers": request_headers, "scheme": "http",
        "server": ("localhost", 80), "client": ("127.0.0.1", 123),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))
    response = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    response_text = response_body.decode("utf-8", errors="replace")
    if not response_text:
        response_data = None
    else:
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            response_data = {"_non_json": True, "text": response_text}
    return response["status"], response_data
