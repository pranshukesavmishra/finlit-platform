from finlit.store import prepare_dsn


def test_neon_style_url_is_cleaned_for_asyncpg():
    dsn, extra = prepare_dsn("postgresql://u:p%40ss@ep-cool-123.ap-southeast-1.aws.neon.tech/finlit?sslmode=require&channel_binding=require")
    assert dsn == "postgresql://u:p%40ss@ep-cool-123.ap-southeast-1.aws.neon.tech/finlit?sslmode=require" and extra == {}


def test_pooled_endpoint_turns_the_statement_cache_off():
    _, extra = prepare_dsn("postgresql://u:p@ep-cool-123-pooler.ap-southeast-1.aws.neon.tech/finlit?sslmode=require")
    assert extra == {"statement_cache_size": 0}


def test_plain_local_url_is_untouched():
    assert prepare_dsn("postgresql://finlit:finlit@localhost:5432/finlit_dev") == ("postgresql://finlit:finlit@localhost:5432/finlit_dev", {})
