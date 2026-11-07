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


def test_an_exchange_page_is_fetched_directly_and_the_relay_is_not_used_when_the_host_answers():
    seen = []
    r = run(fetcher(lambda req: (seen.append(req), httpx.Response(200, content=b"%PDF"))[1])._get_once("https://nsearchives.nseindia.com/a.pdf", {"User-Agent": "UA"}))
    assert r.status_code == 200 and len(seen) == 1 and str(seen[0].url) == "https://nsearchives.nseindia.com/a.pdf" and "x-relay-key" not in seen[0].headers


def test_a_403_from_an_exchange_host_is_asked_again_through_the_relay_with_the_key_and_the_forwarded_headers():
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.host == "relay.example.workers.dev":
            return httpx.Response(200, json={"data": []}, headers={"x-relay": "1"})
        return httpx.Response(403, text="Access Denied")

    r = run(fetcher(handler)._get_once(NSE, {"User-Agent": "UA-1", "Accept": "application/json", "Referer": "https://www.nseindia.com/x"}))
    assert r.status_code == 200 and len(seen) == 2
    q = seen[1]
    assert q.url.path == "/fetch" and q.url.params["u"] == NSE and q.headers["x-relay-key"] == "secret-key"
    assert q.headers["x-fwd-user-agent"] == "UA-1" and q.headers["x-fwd-accept"] == "application/json" and q.headers["x-fwd-referer"] == "https://www.nseindia.com/x"


def test_without_a_relay_a_403_stays_a_403():
    seen = []
    f = fetcher(lambda req: (seen.append(req), httpx.Response(403))[1], relay=None)
    f.relay = None
    assert run(f._get_once(NSE, {})).status_code == 403 and len(seen) == 1


def test_a_host_that_is_not_an_exchange_never_goes_through_the_relay():
    seen = []
    f = fetcher(lambda req: (seen.append(req), httpx.Response(403))[1])
    assert run(f._get_once("https://www.acme.example.com/report.pdf", {})).status_code == 403 and len(seen) == 1 and "x-relay-key" not in seen[0].headers


def test_when_the_relay_cannot_help_the_exchanges_own_403_stands():
    # a wrong key or a Cloudflare error page (no X-Relay header), or the relay's own error: never read as the exchange's answer, and never hides the 403
    for relay_answer in (httpx.Response(403, text="forbidden"),
                         httpx.Response(502, text="x", headers={"x-relay": "1", "x-relay-error": "could not reach the exchange"})):
        f = fetcher(lambda req, a=relay_answer: a if req.url.host == "relay.example.workers.dev" else httpx.Response(403, text="Access Denied"))
        assert run(f._get_once(NSE, {})).text == "Access Denied"


def test_an_exchange_403_even_through_the_relay_still_means_blocked():
    f = fetcher(lambda req: httpx.Response(403, text="Access Denied", headers={"x-relay": "1"} if req.url.host == "relay.example.workers.dev" else {}))
    with pytest.raises(T.Blocked):
        run(f._get("https://nsearchives.nseindia.com/x.pdf", T.USER_AGENT))


def test_redirects_are_followed_and_the_relay_is_asked_only_after_a_403():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.path.endswith("/start"):
            return httpx.Response(302, headers={"location": "https://nsearchives.nseindia.com/final.pdf"})
        return httpx.Response(200, content=b"%PDF-1.4")

    r = run(fetcher(handler)._get("https://www.nseindia.com/start", T.USER_AGENT))
    assert r.content == b"%PDF-1.4" and calls[-1] == "https://nsearchives.nseindia.com/final.pdf" and not any("relay.example" in c for c in calls)
