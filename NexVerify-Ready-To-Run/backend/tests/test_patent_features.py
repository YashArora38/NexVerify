"""Reproducible technical tests; these do not establish novelty or patentability."""
import base64
import copy
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import config, provenance, security
from app.main import app
from app.orchestrator import start_check, wait_result
from app.privacy import minimize_answers, minimize_text


@pytest.mark.asyncio
async def test_revision_bundle_and_consent_api(monkeypatch):
    run = await start_check("QuickRupee", fresh=True)
    original = await wait_result(run, 30)
    assert original and original["integrity"]["revision"] == 1
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:3000") as client:
        base = f"/api/check/{run.id}"
        assert (await client.get(base + "/verify")).json()["ok"]
        no_consent = await client.post(base + "/human-assist", json={"pasted_text": "Guaranteed 200% returns"})
        assert no_consent.status_code == 400
        assisted = await client.post(base + "/human-assist", json={
            "consent": True, "pasted_text": "Guaranteed 200% returns. Contact person@example.com or 9876543210.",
            "answers": {"received_via": "WhatsApp", "asking_money_or_otp": "Yes - Registration Fee"},
        })
        assert assisted.status_code == 200
        result = assisted.json()
        assert result["integrity"]["revision"] == 2
        record = provenance.load_revision(run.id)
        submission = record["evidence"][-1]
        assert "person@example.com" not in submission["excerpt"]
        assert "9876543210" not in submission["excerpt"]
        assert record["graph"]["ownership_verified"] is False
        assert len((await client.get(base + "/ledger")).json()["history"]) == 2
        assert (await client.get(base + "/verify")).json()["verified_revision_count"] == 2
        assert (await client.get(base + "/bundle.zip")).content[:2] == b"PK"
        assert original["integrity"]["revision"] == 1  # Earlier result object was not overwritten.
        monkeypatch.setattr(config, "ANCHOR_PREPARATION_ENABLED", True)
        monkeypatch.setattr(config, "ANCHOR_CONTRACT", "0x" + "ab" * 20)
        prepared = (await client.post(base + "/anchor/prepare", json={"consent": True})).json()
        assert prepared["status"] == "simulated" and prepared["broadcast_enabled"] is False
        assert set(prepared["transaction"]) == {"chainId", "to", "data", "value"}
        assert "person@example.com" not in json.dumps(prepared)
        assert "commitment_salt" not in prepared
        assert (await client.post(base + "/anchor/prepare", json={"consent": False})).status_code == 400
        # Corruption of a predecessor must block BOTH export and anchor preparation.
        artifact = provenance.load_revision(run.id, 1)["artifacts"][0]["path"]
        path = config.DATA_DIR / "ledger" / run.id / "revision-000001" / artifact
        path.write_bytes(b"corrupted predecessor")
        assert not (await client.get(base + "/verify")).json()["ok"]
        assert (await client.get(base + "/bundle.zip")).status_code == 409
        assert (await client.post(base + "/anchor/prepare", json={"consent": True})).status_code == 409


def test_minimization_is_bounded_and_not_anonymity_claim():
    assert "1234 5678 9012" not in minimize_text("Aadhaar 1234 5678 9012")
    assert "INH000000000" in minimize_text("SEBI INH000000000")
    with pytest.raises(ValueError):
        minimize_answers({"arbitrary_key": "value"})
    with pytest.raises(ValueError):
        minimize_answers({"promises": "x" * 1001})


def production_settings(monkeypatch):
    monkeypatch.setenv("NEXVERIFY_ENV", "production")
    monkeypatch.setenv("MANUS_JWT_SECRET", "s" * 40)
    monkeypatch.setenv("MANUS_PROJECT_ID", "wdp_test")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://verify.example")
    monkeypatch.setenv("MANUS_OAUTH_PORTAL_URL", "https://oauth.example")
    monkeypatch.setenv("MANUS_OAUTH_API_URL", "https://identity.example")


def test_owner_isolation_including_nested_batch_paths(monkeypatch):
    production_settings(monkeypatch)
    a = FastAPI()
    security.install_security(a)
    @a.post("/api/create-fixture")
    def create(request: Request):
        security.claim_resource(request, "nv111111111111")
        security.claim_resource(request, "batch_test_owned")
        return {"ok": True}
    @a.get("/api/check/{check_id}")
    def get(check_id: str):
        return {"ok": True}
    @a.get("/api/check/batch/{batch_id}/export.csv")
    def export(batch_id: str):
        return {"ok": True}
    client = TestClient(a, base_url="https://verify.example")
    def headers(user):
        token = security.encode_session({"appId": "wdp_test", "openId": user, "exp": int(time.time()) + 60}, "s" * 40)
        return {"Cookie": f"webdev_app_session={token}", "Origin": "https://verify.example"}
    assert client.post("/api/create-fixture", headers=headers("owner-1")).status_code == 200
    for path in ("/api/check/nv111111111111", "/api/check/batch/batch_test_owned/export.csv"):
        assert client.get(path, headers=headers("owner-1")).status_code == 200
        assert client.get(path, headers=headers("other-user")).status_code == 403
        assert client.get(path).status_code == 401


def test_manus_oauth_wire_contract_and_single_use_state(monkeypatch):
    production_settings(monkeypatch)
    a = FastAPI()
    security.install_security(a)
    client = TestClient(a, base_url="https://verify.example")
    login = client.get("/api/auth/login", follow_redirects=False)
    assert login.status_code == 307
    location = urlsplit(login.headers["location"])
    query = parse_qs(location.query)
    assert location.path == "/app-auth"
    assert query["appId"] == ["wdp_test"]
    assert query["responseType"] == ["code"]
    state = query["state"][0]
    decoded = json.loads(base64.b64decode(state))
    assert decoded["redirectUri"] == "https://verify.example/api/auth/callback"
    calls = []
    def provider(request):
        calls.append(request)
        body = json.loads(request.content)
        if request.url.path.endswith("/ExchangeToken"):
            assert body == {"clientId": "wdp_test", "grantType": "authorization_code", "code": "test-code", "redirectUri": decoded["redirectUri"]}
            return httpx.Response(200, json={"accessToken": "test-access-token"})
        assert request.method == "POST" and body == {"accessToken": "test-access-token"}
        return httpx.Response(200, json={"openId": "real-provider-test-identity", "name": "Test person"})
    original = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(provider), **kwargs))
    callback = client.get("/api/auth/callback", params={"code": "test-code", "state": state}, follow_redirects=False)
    assert callback.status_code == 303
    assert len(calls) == 2
    assert client.get("/api/auth/status").json()["authenticated"] is True
    assert client.get("/api/auth/callback", params={"code": "test-code", "state": state}).status_code == 400


def test_jwt_nan_and_production_http_fail_closed(monkeypatch):
    production_settings(monkeypatch)
    settings = security.SecuritySettings.from_env()
    token = security.encode_session({"appId": "wdp_test", "openId": "x", "exp": float("nan")}, "s" * 40)
    assert security.decode_session(token, settings) is None
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://verify.example")
    with pytest.raises(security.SecurityConfigurationError):
        security.SecuritySettings.from_env()
