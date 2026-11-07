"""The exchange relay (deploy/amfi-relay/worker.js): NSE and BSE answer the AWS server's address with 403, so the company brief and the earnings-call job read
exchange pages through a free Cloudflare Worker. These tests use a fake transport (no network, no database)."""
import asyncio

import httpx
import pytest

from finlit.earnings import transcripts as T

RELAY = ("https://relay.example.workers.dev", "secret-key")
NSE = "https://www.nseindia.com/api/annual-reports?index=equities&symbol=TCS"


async def nosleep(_):
    return None


def fetcher(handler, relay=RELAY):
    return T.Fetcher(budget=20, transport=httpx.MockTransport(handler), sleep=nosleep, pause=0, relay=relay)


def run(coro):
    return asyncio.run(coro)


def test_relay_settings_prefer_the_exchange_names_then_the_amfi_ones():
    assert T.relay_settings({}) is None
    assert T.relay_settings({"AMFI_RELAY_URL": "https://a.workers.dev/", "AMFI_RELAY_KEY": "k"}) == ("https://a.workers.dev", "k")
    assert T.relay_settings({"AMFI_RELAY_URL": "https://a.workers.dev", "AMFI_RELAY_KEY": "k", "EXCHANGE_RELAY_URL": "https://b.workers.dev", "EXCHANGE_RELAY_KEY": "j"}) == ("https://b.workers.dev", "j")
    assert T.relay_settings({"AMFI_RELAY_URL": "http://insecure.example", "AMFI_RELAY_KEY": "k"}) is None      # only https
    assert T.relay_settings({"AMFI_RELAY_URL": "https://a.workers.dev"}) is None                                 # no key, no relay


def test_an_exchange_page_goes_through_the_relay_with_the_key_and_the_forwarded_headers():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"data": []}, headers={"x-relay": "1"})

    r = run(fetcher(handler)._get_once(NSE, {"User-Agent": "UA-1", "Accept": "application/json", "Referer": "https://www.nseindia.com/x"}))
    assert r.status_code == 200 and len(seen) == 1
    q = seen[0]
    assert str(q.url).startswith("https://relay.example.workers.dev/fetch?") and q.url.params["u"] == NSE
    assert q.headers["x-relay-key"] == "secret-key" and q.headers["x-fwd-user-agent"] == "UA-1"
    assert q.headers["x-fwd-accept"] == "application/json" and q.headers["x-fwd-referer"] == "https://www.nseindia.com/x"


def test_without_a_relay_the_request_goes_straight_to_the_exchange():
    seen = []
    f = fetcher(lambda req: (seen.append(req), httpx.Response(200))[1], relay=None)
    f.relay = None
    run(f._get_once(NSE, {"User-Agent": "UA"}))
    assert str(seen[0].url) == NSE and "x-relay-key" not in seen[0].headers


def test_a_host_that_is_not_an_exchange_never_goes_through_the_relay():
    seen = []
    f = fetcher(lambda req: (seen.append(req), httpx.Response(200))[1])
    run(f._get_once("https://www.acme.example.com/report.pdf", {}))
    assert str(seen[0].url) == "https://www.acme.example.com/report.pdf" and "x-relay-key" not in seen[0].headers


def test_an_answer_the_relay_did_not_write_is_never_read_as_the_exchanges_answer():
    # a wrong key or a Cloudflare error page has no X-Relay header: it must not look like the exchange refusing (403) or answering
    f = fetcher(lambda req: httpx.Response(403, text="forbidden"))
    with pytest.raises(T.FetchFailed, match="relay answered HTTP 403"):
        run(f._get_once(NSE, {}))


def test_the_relays_own_error_is_a_failed_fetch_not_a_block():
    f = fetcher(lambda req: httpx.Response(502, text="x", headers={"x-relay": "1", "x-relay-error": "could not reach the exchange"}))
    with pytest.raises(T.FetchFailed, match="relay: could not reach the exchange"):
        run(f._get_once(NSE, {}))


def test_an_exchange_403_through_the_relay_still_means_blocked():
    f = fetcher(lambda req: httpx.Response(403, text="Access Denied", headers={"x-relay": "1"}))
    with pytest.raises(T.Blocked):
        run(f._get("https://nsearchives.nseindia.com/x.pdf", T.USER_AGENT))   # robots.txt answers 403 too: the host is blocked


def test_redirects_are_followed_through_the_relay():
    calls = []

    def handler(req):
        target = req.url.params["u"]
        calls.append(target)
        if target.endswith("/robots.txt"):
            return httpx.Response(404, headers={"x-relay": "1"})
        if target.endswith("/start"):
            return httpx.Response(302, headers={"x-relay": "1", "location": "https://nsearchives.nseindia.com/final.pdf"})
        return httpx.Response(200, content=b"%PDF-1.4", headers={"x-relay": "1"})

    r = run(fetcher(handler)._get("https://www.nseindia.com/start", T.USER_AGENT))
    assert r.content == b"%PDF-1.4" and calls[-1] == "https://nsearchives.nseindia.com/final.pdf"
