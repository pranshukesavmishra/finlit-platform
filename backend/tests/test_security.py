import pytest

from finlit.api import create_app
from finlit.config import Settings
from finlit.security import _bucket_ip, client_ip


def prod(**kw):
    base = dict(environment="production", finedge_mode="live", finedge_api_key="k",
                database_url="postgresql://finlit:Str0ng-Secret@db:5432/finlit", redis_url="redis://:pw@redis:6379/0",
                allowed_hosts=["api.finlitventures.com"], cors_origins=["https://finlitventures.com"])
    base.update(kw)
    return Settings(**base)


def test_production_settings_ok():
    assert prod().validate() == []


@pytest.mark.parametrize("override, fragment", [
    ({"database_url": "postgresql://finlit:finlit@db:5432/finlit"}, "default password"),
    ({"redis_url": "redis://redis:6379/0"}, "REDIS_URL"),
    ({"allowed_hosts": ["*"]}, "ALLOWED_HOSTS"),
    ({"cors_origins": ["http://finlitventures.com"]}, "CORS"),
    ({"finedge_mode": "fixtures"}, "FINEDGE"),
])
def test_unsafe_production_refuses_to_start(override, fragment):
    with pytest.raises(RuntimeError, match=fragment):
        create_app(prod(**override))


def test_docs_disabled_in_production():
    app = create_app(prod())
    paths = {r.path for r in app.routes}
    assert "/api/docs" not in paths and "/api/openapi.json" not in paths


def test_client_ip_ignores_headers_unless_configured():
    scope = {"client": ("10.0.0.5", 1234), "headers": [(b"cf-connecting-ip", b"1.2.3.4")]}
    assert client_ip(scope) == "10.0.0.5"  # spoofable header ignored by default
    assert client_ip(scope, "cf-connecting-ip") == "1.2.3.4"
    bad = {"client": ("10.0.0.5", 1), "headers": [(b"cf-connecting-ip", b"not-an-ip<script>")]}
    assert client_ip(bad, "cf-connecting-ip") == "10.0.0.5"


def test_ipv6_limited_per_slash_64():
    assert _bucket_ip("2001:db8:1:2:aaaa::1") == _bucket_ip("2001:db8:1:2:bbbb::9")
    assert _bucket_ip("2001:db8:1:3::1") != _bucket_ip("2001:db8:1:2::1")
