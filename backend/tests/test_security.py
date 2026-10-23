import pytest

from finlit.api import create_app
from finlit.config import Settings
from finlit.security import _bucket_ip, client_ip


def prod(**kw):
    base = dict(environment="production", finedge_mode="live", finedge_api_key="k",
                database_url="postgresql://finlit:Str0ng-Secret@db:5432/finlit", redis_url="redis://:pw@redis:6379/0",
                allowed_hosts=["api.finlitventures.com"], cors_origins=["https://finlitventures.com"],
                secret_key="x" * 48, mail_mode="resend", resend_api_key="re_test", public_site_url="https://finlitventures.com")
    base.update(kw)
    return Settings(**base)


def test_production_settings_ok():
    assert prod().validate() == []


@pytest.mark.parametrize("override, fragment", [
    ({"database_url": "postgresql://finlit:finlit@db:5432/finlit"}, "default password"),
    ({"redis_url": "redis://localhost:6379/0"}, "REDIS_URL"),  # a private-network host without a password is allowed (managed Redis); localhost is not
    ({"allowed_hosts": ["*"]}, "ALLOWED_HOSTS"),
    ({"cors_origins": ["http://finlitventures.com"]}, "CORS"),
    ({"finedge_mode": "fixtures"}, "FINEDGE"),
    ({"secret_key": "dev-only-secret-key-do-not-use-in-production"}, "SECRET_KEY"),
    ({"mail_mode": "console"}, "MAIL_MODE"),
    ({"public_site_url": "http://finlitventures.com"}, "PUBLIC_SITE_URL"),
])
def test_unsafe_production_refuses_to_start(override, fragment):
    with pytest.raises(RuntimeError, match=fragment):
        create_app(prod(**override))


def test_docs_disabled_in_production():
    app = create_app(prod())
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/docs" not in paths and "/api/openapi.json" not in paths


def test_docs_disabled_on_a_deployed_staging_site():
    paths = {getattr(r, "path", "") for r in create_app(Settings(environment="staging")).routes}
    assert "/api/docs" not in paths and "/api/openapi.json" not in paths
    paths = {getattr(r, "path", "") for r in create_app(Settings(environment="development")).routes}
    assert "/api/docs" in paths


def test_client_ip_ignores_headers_unless_configured():
    scope = {"client": ("10.0.0.5", 1234), "headers": [(b"cf-connecting-ip", b"1.2.3.4")]}
    assert client_ip(scope) == "10.0.0.5"  # spoofable header ignored by default
    assert client_ip(scope, "cf-connecting-ip") == "1.2.3.4"
    bad = {"client": ("10.0.0.5", 1), "headers": [(b"cf-connecting-ip", b"not-an-ip<script>")]}
    assert client_ip(bad, "cf-connecting-ip") == "10.0.0.5"


def test_ipv6_limited_per_slash_64():
    assert _bucket_ip("2001:db8:1:2:aaaa::1") == _bucket_ip("2001:db8:1:2:bbbb::9")
    assert _bucket_ip("2001:db8:1:3::1") != _bucket_ip("2001:db8:1:2::1")


def test_xff_uses_rightmost_hop_not_client_supplied():
    from finlit.security import client_ip
    scope = {"headers": [(b"x-forwarded-for", b"10.9.9.9, 203.0.113.7")], "client": ("127.0.0.1", 1)}
    assert client_ip(scope, "x-forwarded-for") == "203.0.113.7"


def xff(value: str, peer: str = "10.1.2.3") -> str:
    from finlit.security import client_ip
    return client_ip({"headers": [(b"x-forwarded-for", value.encode())], "client": (peer, 1)}, "x-forwarded-for")


def test_xff_skips_cloudflare_and_load_balancer_hops_whatever_their_number():
    assert xff("49.36.1.2") == "49.36.1.2"                                   # the host appends the visitor only
    assert xff("49.36.1.2, 172.70.10.1") == "49.36.1.2"                      # visitor, then a Cloudflare edge address
    assert xff("49.36.1.2, 172.70.10.1, 10.0.4.7") == "49.36.1.2"            # visitor, Cloudflare, internal load balancer
    assert xff("2401:4900:1c3a::5, 2606:4700:10::1") == "2401:4900:1c3a::5"  # IPv6 through Cloudflare's IPv6 edge


def test_xff_values_written_by_the_visitor_are_never_used():
    # A visitor sends their own X-Forwarded-For to look like someone else (or like a proxy); the host appends the real address after it.
    assert xff("1.1.1.1, 49.36.1.2, 172.70.10.1") == "49.36.1.2"
    assert xff("10.0.0.1, 162.158.0.1, 49.36.1.2, 172.70.10.1") == "49.36.1.2"
    assert xff("<script>, 49.36.1.2") == "49.36.1.2"
    many = ", ".join(f"8.8.{i}.{i}" for i in range(200)) + ", 49.36.1.2"
    assert xff(many) == "49.36.1.2"


def test_xff_without_a_usable_address_falls_back_to_the_peer():
    assert xff("") == "10.1.2.3"
    assert xff("not-an-ip") == "10.1.2.3"
    assert xff("192.168.1.20, 10.0.0.9") == "192.168.1.20"                  # all private (local network): the furthest hop


def test_xff_ipv4_mapped_ipv6_is_read_as_ipv4():
    assert xff("::ffff:49.36.1.2, ::ffff:172.70.10.1") == "49.36.1.2"


def test_extra_trusted_proxies(monkeypatch):
    from finlit.security import _proxy_networks
    monkeypatch.setenv("TRUSTED_PROXIES", "35.190.0.0/17, nonsense")
    assert xff("49.36.1.2, 35.190.5.5") == "49.36.1.2"
    monkeypatch.delenv("TRUSTED_PROXIES")
    assert xff("49.36.1.2, 35.190.5.5") == "35.190.5.5"
    assert _proxy_networks.cache_info().currsize >= 2


def test_common_passwords_rejected():
    from finlit.auth.crypto import password_problem
    for pw in ("qwertyuiop12", "letmein123456", "Passw0rd12345", "Finlit2026!"):
        assert password_problem(pw, "a@b.co"), pw
    assert password_problem("blue-harbour-lamp-47", "a@b.co") is None
