"""Logo pipeline: image checks, icon discovery, the fetch rules (https only, public addresses, robots.txt, no going around a block)."""
import struct
import zlib

import httpx
import pytest

from finlit import logos
from finlit.logos import Fetcher, Rejected, amc_logo_keys, fetch_logo, icon_candidates, site_domain, sniff


def png(w: int, h: int, pad: int = 0) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))   # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", b"\x00" * (10 + pad)) + chunk(b"IEND", b"")


def ico(entries) -> bytes:
    """entries: [(w, h, payload)]"""
    head = struct.pack("<HHH", 0, 1, len(entries))
    off = 6 + 16 * len(entries)
    dirs, body = b"", b""
    for w, h, data in entries:
        dirs += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(data), off + len(body))
        body += data
    return head + dirs + body


def test_sniff_accepts_real_square_bitmaps():
    out, mime, w, h = sniff(png(180, 180))
    assert (mime, w, h) == ("image/png", 180, 180) and out.startswith(b"\x89PNG")
    # an .ico whose largest entry is a PNG keeps just that PNG
    out, mime, w, h = sniff(ico([(16, 16, b"\x00" * 40), (64, 64, png(64, 64))]))
    assert (mime, w, h) == ("image/png", 64, 64)
    # an .ico of bitmaps is kept whole
    _, mime, w, h = sniff(ico([(16, 16, b"\x00" * 40), (48, 48, b"\x00" * 80)]))
    assert (mime, w, h) == ("image/x-icon", 48, 48)
    jpeg = b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 120, 128) + b"\x00" * 12
    assert sniff(jpeg)[1:] == ("image/jpeg", 128, 120)
    gif = b"GIF89a" + struct.pack("<HH", 32, 32) + b"\x00" * 20
    assert sniff(gif)[1:] == ("image/gif", 32, 32)
    vp8x = b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 8 + (99).to_bytes(3, "little") + (99).to_bytes(3, "little")
    assert sniff(vp8x)[1:] == ("image/webp", 100, 100)


@pytest.mark.parametrize("data, why", [
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "SVG"),
    (b"<!doctype html><html>not found</html>", "web page"),
    (b"BM6\x00\x00\x00 a bitmap file", "unknown"),
    (png(8, 8), "outside"),
    (png(2048, 2048), "outside"),
    (png(200, 60), "square"),
    (png(128, 128, pad=70_000), "too large"),
])
def test_sniff_rejects(data, why):
    with pytest.raises(Rejected, match=why):
        sniff(data)


def test_site_domain():
    assert site_domain("www.ril.com") == "www.ril.com"
    assert site_domain("https://www.TCS.com/en-in/") == "www.tcs.com"
    assert site_domain("http://infosys.com:8080/x") == "infosys.com"
    for bad in (None, "", "N/A", "localhost", "10.0.0.1", "http://192.168.1.1", "not a site", "javascript:alert(1)"):
        assert site_domain(bad) is None, bad


def test_icon_candidates_order():
    html = """<html><head><base href="/static/">
      <link rel="icon" href="tiny.png" sizes="16x16"><link rel="icon" type="image/svg+xml" href="logo.svg">
      <link rel="shortcut icon" href="big.png" sizes="96x96"><link rel="apple-touch-icon" href="/touch-152.png" sizes="152x152">
      <link rel="apple-touch-icon" href="/touch-180.png" sizes="180x180"><link rel="icon" href="http://insecure.example/x.png" sizes="64x64">
      <link rel="icon" href="data:image/png;base64,AAAA"></head></html>"""
    got = icon_candidates(html, "https://www.example.com/")
    assert got == ["https://www.example.com/touch-180.png", "https://www.example.com/touch-152.png", "https://www.example.com/static/big.png",
                   "http://insecure.example/x.png", "https://www.example.com/static/tiny.png",
                   "https://www.example.com/apple-touch-icon.png", "https://www.example.com/favicon.ico"]          # declared first, largest first; never SVG or data:
    assert icon_candidates("<<garbage", "https://x.example/")[-1] == "https://x.example/favicon.ico"


async def public(host):
    return ["93.184.216.34"]


def site(routes, log=None):
    """A fake web: path -> (status, body, headers)."""
    def handler(req: httpx.Request):
        if log is not None:
            log.append((str(req.url), req.headers.get("user-agent")))
        st, body, hd = routes.get(req.url.path, (404, b"", {}))
        return httpx.Response(st, content=body, headers=hd)
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(logos, "PAUSE", 0)


async def test_fetch_logo_finds_apple_touch_icon_and_identifies_itself():
    calls = []
    t = site({"/": (200, b'<link rel="apple-touch-icon" href="/t.png">', {}), "/t.png": (200, png(180, 180), {"content-type": "image/png"}),
              "/robots.txt": (200, b"User-agent: *\nAllow: /\n", {})}, calls)
    f = Fetcher(t, public)
    res = await fetch_logo(f, "www.example.com")
    await f.aclose()
    assert res["status"] == "ok" and res["width"] == 180 and res["source_url"] == "https://www.example.com/t.png"
    assert all(ua == logos.USER_AGENT for _, ua in calls)


async def test_fetch_logo_falls_back_and_explains():
    t = site({"/": (200, b"<html>no icons</html>", {}), "/favicon.ico": (200, ico([(8, 8, b"\x00" * 40)]), {})})
    f = Fetcher(t, public)
    res = await fetch_logo(f, "www.example.com")
    await f.aclose()
    assert res["status"] == "none" and "favicon.ico" in res["note"] and "outside" in res["note"]


async def test_robots_disallow_is_obeyed():
    calls = []
    t = site({"/robots.txt": (200, b"User-agent: *\nDisallow: /\n", {}), "/": (200, b"x", {})}, calls)
    f = Fetcher(t, public)
    res = await fetch_logo(f, "www.example.com")
    await f.aclose()
    assert res["status"] == "rejected" and "robots" in res["note"]
    assert [u for u, _ in calls] == ["https://www.example.com/robots.txt"]       # the home page itself was never asked for


@pytest.mark.parametrize("status, body", [(403, b"Forbidden"), (429, b""), (503, b""),
                                           (200, b"<html><script src='/cdn-cgi/challenge-platform/h/b/orchestrate'></script></html>")])
async def test_block_or_bot_check_stops_us(status, body):
    calls = []
    t = site({"/": (status, body, {}), "/favicon.ico": (200, png(64, 64), {})}, calls)
    f = Fetcher(t, public)
    res = await fetch_logo(f, "www.example.com")
    await f.aclose()
    assert res["status"] == "blocked"
    assert not any(u.endswith("favicon.ico") for u, _ in calls)                  # nothing else is tried once a site says no


async def test_contact_form_recaptcha_is_not_a_block():
    t = site({"/": (200, b'<html><script src="https://www.google.com/recaptcha/api.js"></script><link rel="icon" href="/i.png" sizes="64x64"></html>', {}),
              "/i.png": (200, png(64, 64), {})})
    f = Fetcher(t, public)
    assert (await fetch_logo(f, "www.example.com"))["status"] == "ok"
    await f.aclose()


async def test_private_addresses_and_redirects_are_refused():
    async def private(host):
        return ["10.1.2.3"] if host == "internal.example" else ["93.184.216.34"]
    t = site({"/": (302, b"", {"location": "https://internal.example/"})})
    f = Fetcher(t, private)
    res = await fetch_logo(f, "www.example.com")
    assert res["status"] == "rejected" and "private" in res["note"]
    t2 = site({"/": (302, b"", {"location": "https://www.example.com:8443/admin"})})
    f2 = Fetcher(t2, public)
    assert "standard ports" in (await fetch_logo(f2, "www.example.com"))["note"]
    loop = site({"/": (302, b"", {"location": "/"})})
    f3 = Fetcher(loop, public)
    assert "redirects" in (await fetch_logo(f3, "www.example.com"))["note"]
    for x in (f, f2, f3):
        await x.aclose()


async def test_long_home_page_is_read_only_up_to_its_head_and_big_files_are_refused():
    head = b'<html><head><link rel="icon" href="/huge.png" sizes="64x64"><link rel="icon" href="/ok.png" sizes="32x32"></head>'
    t = site({"/": (200, head + b"x" * (logos.MAX_HTML * 3), {}), "/huge.png": (200, b"\x89PNG" + b"x" * (logos.MAX_BYTES * 5), {}), "/ok.png": (200, png(32, 32), {})})
    f = Fetcher(t, public)
    res = await fetch_logo(f, "www.example.com")
    await f.aclose()
    assert res["status"] == "ok" and res["width"] == 32 and res["source_url"].endswith("/ok.png")


async def test_the_sharpest_icon_wins():
    t = site({"/": (200, b'<link rel="icon" href="/a.png" sizes="16x16">', {}), "/a.png": (200, png(16, 16), {}),
              "/apple-touch-icon.png": (200, png(48, 48), {}), "/favicon.ico": (200, ico([(32, 32, png(32, 32))]), {})})
    f = Fetcher(t, public)
    res = await fetch_logo(f, "www.example.com")
    await f.aclose()
    assert res["status"] == "ok" and res["width"] == 48


def test_amc_names_map_to_sites():
    got = amc_logo_keys(["Nippon India Mutual Fund", "SBI Mutual Fund", "ICICI Prudential Mutual Fund", "Tata Mutual Fund", "Unknown House", ""])
    assert got == {"Nippon India Mutual Fund": "nipponindia", "SBI Mutual Fund": "sbi", "ICICI Prudential Mutual Fund": "iciciprudential", "Tata Mutual Fund": "tata"}
    assert all(d == site_domain(d) for d in logos.AMC_SITES.values())
