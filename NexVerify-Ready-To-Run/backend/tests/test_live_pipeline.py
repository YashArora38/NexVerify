"""Live path with Gemini and the web mocked: checks wiring, parsing and guards."""
import json

import httpx
import pytest

from app import config, gemini, web
from app.gemini import Gemini, GeminiError, parse_json_loose, url_is_grounded
from app.orchestrator import start_check, wait_result


def _payload(obj, queries=(), hosts=(), raw_text=None):
    text = raw_text if raw_text is not None else "Here you go:\n```json\n" + json.dumps(obj) + "\n```"
    return {"candidates": [{
        "content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]},
        "groundingMetadata": {
            "webSearchQueries": list(queries),
            "groundingChunks": [{"web": {"uri": f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/{i}",
                                         "title": h}} for i, h in enumerate(hosts)],
        },
    }]}


def handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    prompt = body["contents"][0]["parts"][0]["text"]
    assert request.headers["x-goog-api-key"] == "test-key"
    if "Work out which app" in prompt:
        return httpx.Response(200, json=_payload({
            "display_name": "TestLoan", "category": "lending",
            "play_url": "https://play.google.com/store/apps/details?id=com.testloan",
            "website_url": "https://testloan.in", "telegram_url": None, "legal_name": None}, ["TestLoan app"], ["play.google.com"]))
    if "Digital Lending Apps" in prompt:
        return httpx.Response(200, json=_payload({"found": False, "notes": "not listed"},
                                                 ["TestLoan RBI DLA"], ["rbi.org.in"]))
    if "MCA" in prompt:
        return httpx.Response(200, json=_payload({"found": True, "company_name": "Testloan Credit Private Limited",
                                                  "incorporated_on": "2015-01-01", "status": "Active",
                                                  "cin": "U65999DL2015PTC000001"}, ["Testloan Credit CIN"], ["zaubacorp.com"]))
    if "public complaints" in prompt:
        return httpx.Response(200, json=_payload({"reports": [
            {"title": "a", "url": "https://www.realnews.in/a", "type": "harassment"},
            {"title": "b", "url": "https://hallucinated.example/b", "type": "scam"}]},
            ["TestLoan scam"], ["realnews.in"]))
    if "short, simple warnings" in prompt:
        return httpx.Response(200, json=_payload({"en": "TestLoan is not on RBI lists. Already paid? Call 1930.",
                                                  "hi": "TestLoan RBI सूची में नहीं है। पैसे भेज चुके हैं? तुरंत 1930 पर कॉल करें।"}))
    return httpx.Response(500, text="unexpected prompt")


PAGES = {
    "testloan.in": "<html><title>TestLoan</title><body>Trusted for 12 years. Testloan Credit Private Limited</body></html>",
    "details?id=com.testloan": '<html><body><a href="/store/apps/dev?id=9"><span>Shady Apps Ltd</span></a></body></html>',
    "datasafety?id=com.testloan": "<html><body>Data safety: Contacts, Call logs</body></html>",
}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    gemini.set_client(Gemini(api_key="test-key", transport=httpx.MockTransport(handler)))

    async def fake_fetch(url, timeout=15.0, transport=None):
        for frag, html in PAGES.items():
            if frag in url:
                return web.Page(url, url, 200, web.page_title(html), html, web.html_to_text(html))
        return web.Page(url, url, 404, "", "", "")

    async def fake_rdap(domain, timeout=12.0, transport=None):
        return {"ok": True, "domain": domain, "source_url": "https://rdap.org/domain/" + domain,
                "registered_on": "2015-01-01", "age_days": 4000}

    async def fake_passive(url, host):
        return {
            "threat_feeds": {"status": "pass", "points": 0, "data": {}, "reason": "clean", "source": "threat_feeds"},
            "tranco": {"status": "unknown", "points": 0, "data": {}, "reason": "unranked", "source": "tranco"},
            "lexical": {"status": "pass", "points": 0, "data": {}, "reason": "clean", "source": "lexical"},
        }

    monkeypatch.setattr(web, "fetch_page", fake_fetch)
    monkeypatch.setattr(web, "rdap_registration", fake_rdap)
    monkeypatch.setattr("app.passive.run_passive_checks", fake_passive)
    yield
    gemini.set_client(None)


async def test_live_check_end_to_end(live):
    run = await start_check("TestLoan", fresh=True)
    r = await wait_result(run, 30)
    assert r, run.events[-3:]
    assert r["demo"] is False
    assert r["subject"]["website_url"] == "https://testloan.in"
    ids = {h["rule_id"] for h in r["hits"]}
    # Old company, but a loan app no RBI lender lists, a different Play publisher and
    # one grounded harassment report (the made-up link is ignored).
    assert ids == {"RBI_NOT_LISTED", "PLAY_PUBLISHER", "PLAY_PERMISSIONS", "SCAM_REPORTS_FEW"}
    assert r["score"] == max(0, 100 - 20 - 20 - 10 - 35)
    assert r["verdict"]["code"] == "HIGH_RISK"
    news = r["agents"]["news"]["data"]
    assert news["reports_count"] == 1 and news["unverified_count"] == 1  # hallucinated link ignored
    assert r["agents"]["sebi"]["status"] == "skipped"
    assert r["summary"]["source"] == ("gemini" if config.AI_SUMMARY else "template")
    # step events were streamed
    assert any(e == "agent" and d.get("step", "").startswith("Google:") for e, d in run.events)


async def test_summary_with_invented_numbers_falls_back(monkeypatch, live):
    def bad(request):
        prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        if "short, simple warnings" in prompt:
            return httpx.Response(200, json=_payload({"en": "Lost Rs 5000 already!", "hi": "५००० गए"}))
        return handler(request)

    gemini.set_client(Gemini(api_key="test-key", transport=httpx.MockTransport(bad)))
    run = await start_check("TestLoan", fresh=True)
    r = await wait_result(run, 30)
    assert r["summary"]["source"] == "template"


async def test_thinking_level_fallback_and_retry():
    calls = []

    def h(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(400, text='{"error": "Unknown field thinkingConfig.thinkingLevel"}')
        if len(calls) == 2:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json=_payload({"ok": 1}, ["q"], ["x.com"]))

    g = Gemini(api_key="k", transport=httpx.MockTransport(h))
    g.thinking_level = "low"
    g.retry_delay = 0
    res = await g.generate("hi", search=True)
    assert res.data == {"ok": 1}
    assert "generationConfig" not in calls[1]
    assert calls[0]["tools"] == [{"google_search": {}}]


async def test_error_bubbles_up():
    g = Gemini(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(403, text="bad key")))
    with pytest.raises(GeminiError):
        await g.generate("hi")


def test_parse_json_loose_and_grounding():
    assert parse_json_loose('blah {"a": {"b": "}"}} tail') == {"a": {"b": "}"}}
    assert parse_json_loose("```json\n{\"x\": 1}\n```") == {"x": 1}
    res = Gemini._parse(_payload({}, [], ["timesofindia.indiatimes.com"]))
    assert url_is_grounded("https://timesofindia.indiatimes.com/x", res)
    assert not url_is_grounded("https://fake.example/x", res)
    assert res.text.startswith("Here you go")  # thought parts dropped


async def test_unreachable_sources_never_show_green(monkeypatch, live):
    down = Gemini(api_key="test-key", transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down")))
    down.retry_delay = 0
    gemini.set_client(down)

    async def dead_fetch(url, timeout=15.0, transport=None):
        return web.Page(url, url, 0, "", "", "", error="offline")

    async def dead_rdap(domain, timeout=12.0, transport=None):
        return {"ok": False, "domain": domain, "error": "offline"}

    monkeypatch.setattr(web, "fetch_page", dead_fetch)
    monkeypatch.setattr(web, "rdap_registration", dead_rdap)
    run = await start_check("Some Unknown App", fresh=True)
    r = await wait_result(run, 60)
    assert r["score"] == 50 and r["verdict"]["code"] in ("UNKNOWN", "CAUTION")
    assert r["partial"] is True
