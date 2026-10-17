import httpx
import pytest
from fastapi import FastAPI

from finlit.web import mount_frontend


@pytest.fixture
def site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "robots.txt").write_text("User-agent: *")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    app = FastAPI()

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    assert mount_frontend(app, tmp_path)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_files_shell_and_api(site):
    assert (await site.get("/")).text == "<html>shell</html>"
    deep = await site.get("/stocks/TCS")  # client-side route: app shell
    assert deep.status_code == 200 and deep.text == "<html>shell</html>" and deep.headers["cache-control"] == "no-cache"
    asset = await site.get("/assets/app-abc123.js")
    assert asset.text == "console.log(1)" and "immutable" in asset.headers["cache-control"]
    assert "default-src 'self'" in deep.headers["content-security-policy"] and deep.headers["x-frame-options"] == "DENY"
    assert (await site.get("/api/ping")).json() == {"ok": True}


async def test_unknown_api_paths_are_json_404_never_the_website(site):
    r = await site.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json() == {"status": "not_found"}


async def test_cannot_read_files_outside_the_site_folder(site):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        r = await site.get(path)
        assert "do not serve" not in r.text


def test_no_build_means_no_website(tmp_path):
    assert mount_frontend(FastAPI(), tmp_path) is False
