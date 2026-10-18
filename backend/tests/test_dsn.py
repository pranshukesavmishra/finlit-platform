from finlit.store import prepare_dsn


def test_neon_style_url_is_cleaned_for_asyncpg():
    dsn, extra = prepare_dsn("postgresql://u:p%40ss@ep-cool-123.ap-southeast-1.aws.neon.tech/finlit?sslmode=require&channel_binding=require")
    assert dsn == "postgresql://u:p%40ss@ep-cool-123.ap-southeast-1.aws.neon.tech/finlit?sslmode=require" and extra == {}


def test_pooled_endpoint_turns_the_statement_cache_off():
    _, extra = prepare_dsn("postgresql://u:p@ep-cool-123-pooler.ap-southeast-1.aws.neon.tech/finlit?sslmode=require")
    assert extra == {"statement_cache_size": 0}


def test_plain_local_url_is_untouched():
    assert prepare_dsn("postgresql://finlit:finlit@localhost:5432/finlit_dev") == ("postgresql://finlit:finlit@localhost:5432/finlit_dev", {})


def test_session_cookie_is_secure_on_any_https_site_but_not_on_local_http():
    from finlit.config import Settings
    assert Settings(environment="staging", public_site_url="https://finlit.onrender.com").cookie_secure is True
    assert Settings(environment="production", public_site_url="https://finlitventures.com").cookie_secure is True
    assert Settings(environment="development", public_site_url="http://localhost:4173").cookie_secure is False
