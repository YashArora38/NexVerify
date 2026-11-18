from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security import (
    SecurityConfigurationError,
    SecuritySettings,
    decode_session,
    encode_session,
    install_security,
)


SECRET = "s" * 40


def _settings(**changes):
    values = {
        "NEXVERIFY_ENV": "test",
        "MANUS_JWT_SECRET": SECRET,
        "MANUS_PROJECT_ID": "wdp_test",
        "FRONTEND_ORIGIN": "http://localhost:3000",
    }
    values.update(changes)
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        return SecuritySettings.from_env()
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_production_fails_closed_without_secret_project_and_origin(monkeypatch):
    monkeypatch.setenv("NEXVERIFY_ENV", "production")
    monkeypatch.delenv("MANUS_JWT_SECRET", raising=False)
    monkeypatch.delenv("MANUS_PROJECT_ID", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    with pytest.raises(SecurityConfigurationError):
        SecuritySettings.from_env()


def test_production_rejects_wildcard_origin(monkeypatch):
    monkeypatch.setenv("NEXVERIFY_ENV", "production")
    monkeypatch.setenv("MANUS_JWT_SECRET", SECRET)
    monkeypatch.setenv("MANUS_PROJECT_ID", "wdp_test")
    monkeypatch.setenv("FRONTEND_ORIGIN", "*")
    with pytest.raises(SecurityConfigurationError):
        SecuritySettings.from_env()


def test_hs256_session_requires_project_openid_and_future_expiry():
    settings = _settings()
    payload = {"appId": "wdp_test", "openId": "user-1", "exp": int(time.time()) + 60}
    token = encode_session(payload, SECRET)
    assert decode_session(token, settings)["openId"] == "user-1"

    parts = token.split(".")
    tampered_payload = base64.urlsafe_b64encode(
        json.dumps({**payload, "openId": "attacker"}, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    tampered = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    assert decode_session(tampered, settings) is None
    assert decode_session(encode_session({**payload, "exp": int(time.time()) - 1}, SECRET), settings) is None
    assert decode_session(encode_session({**payload, "appId": "other"}, SECRET), settings) is None


def test_install_security_allows_public_health_but_protects_api_in_production(monkeypatch):
    monkeypatch.setenv("NEXVERIFY_ENV", "production")
    monkeypatch.setenv("MANUS_JWT_SECRET", SECRET)
    monkeypatch.setenv("MANUS_PROJECT_ID", "wdp_test")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://verify.example")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/check/{check_id}")
    def check(check_id: str):
        return {"check_id": check_id}

    install_security(app)
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/check/nv123456789abc").status_code == 401


def test_unsafe_browser_request_requires_exact_origin(monkeypatch):
    monkeypatch.setenv("NEXVERIFY_ENV", "production")
    monkeypatch.setenv("MANUS_JWT_SECRET", SECRET)
    monkeypatch.setenv("MANUS_PROJECT_ID", "wdp_test")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://verify.example")
    app = FastAPI()

    @app.post("/api/rules/reload")
    def mutate():
        return {"ok": True}

    install_security(app)
    client = TestClient(app)
    token = encode_session({"appId": "wdp_test", "openId": "user-1", "exp": int(time.time()) + 60}, SECRET)
    headers = {"Cookie": f"webdev_app_session={token}"}
    assert client.post("/api/rules/reload", headers={**headers, "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/rules/reload", headers={**headers, "Origin": "https://verify.example"}).status_code == 200
