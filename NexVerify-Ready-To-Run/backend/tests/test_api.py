import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    # context manager keeps one event loop alive, like a real server
    with TestClient(app) as c:
        yield c


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev:
            out.append((ev, data))
    return out


def test_health(client):
    r = client.get("/api/health").json()
    assert r["ok"] and r["live"] is False and r["db"] == "sqlite"
    assert "QuickRupee - Instant Loan App" in r["demo_names"]


def test_check_stream_result_pdf(client):
    cid = client.post("/api/check", json={"query": "QuickRupee", "fresh": True}).json()["check_id"]
    with client.stream("GET", f"/api/check/{cid}/stream") as s:
        body = "".join(s.iter_text())
    evs = _events(body)
    kinds = [e for e, _ in evs]
    assert kinds[-1] == "end" and "result" in kinds and "cards" in kinds and "subject" in kinds
    result = client.get(f"/api/check/{cid}").json()
    assert result["score"] == 0 and result["verdict"]["code"] == "HIGH_RISK"
    pdf = client.get(f"/api/check/{cid}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    txt = client.get(f"/api/check/{cid}/report.txt")
    assert txt.status_code == 200 and "PUBLIC SURFACE INVESTIGATION" in txt.text
    assert "Binary not analyzed" in txt.text and "DRAFT ONLY" in txt.text
    assert "Merchant NOT verified" not in txt.text  # spoofed Razorpay host is rejected
    f = result["evidence"][0]["file"]
    assert client.get(f"/api/evidence/{cid}/{f}").status_code == 200
    assert client.get(f"/api/evidence/{cid}/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_unknown_name_without_key_is_not_called_safe(client):
    """With no Gemini key the check still runs on the offline engine. A name that
    nothing can confirm must come back as "Could not verify", never as safe."""
    cid = client.post("/api/check", json={"query": "Totally Unknown Thing", "fresh": True}).json()["check_id"]
    with client.stream("GET", f"/api/check/{cid}/stream") as s:
        evs = _events("".join(s.iter_text()))
    assert not [d for e, d in evs if e == "error"]
    result = client.get(f"/api/check/{cid}").json()
    assert result["verdict"]["code"] == "UNKNOWN" and result["score"] <= 50


def test_whatsapp_webhook(client):
    r = client.post("/api/whatsapp", data={"Body": "SafeKosh Finance", "From": "whatsapp:+910000000000"})
    assert r.status_code == 200 and "100/100" in r.text and "<Response>" in r.text


def test_bad_ids(client):
    assert client.get("/api/check/../../x").status_code == 404
    assert client.get("/api/check/nvzzzz").status_code == 404
