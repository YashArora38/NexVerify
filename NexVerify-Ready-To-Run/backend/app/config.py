"""All settings come from environment variables (or backend/.env).

Nothing secret is ever hard-coded. Copy .env.example to .env and add your Gemini key.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # dotenv is optional
    pass


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("NEXVERIFY_DATA_DIR", BASE_DIR / "data"))
EVIDENCE_DIR = DATA_DIR / "evidence"
REPORT_DIR = DATA_DIR / "reports"

# --- Gemini (Google) ---------------------------------------------------------
# Used two ways:
#   1. The checkers ask Gemini to look things up with Google Search grounding
#      and return plain facts + source links.
#   2. The final verdict (already scored by fixed rules) is turned into simple
#      Hindi / English. Gemini never sets the score.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip()
# Tried in order only when the model above is not available (HTTP 404).
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-flash-latest,gemini-3.8-flash").split(",") if m.strip()]
# Free keys allow only a few requests per minute; calls are spaced to stay under it.
GEMINI_RPM = int(os.getenv("GEMINI_RPM", "12") or 12)
# On HTTP 429 wait at most this long for the per-minute window, else give up for now.
GEMINI_MAX_WAIT_SECONDS = float(os.getenv("GEMINI_MAX_WAIT_SECONDS", "12") or 12)
# Whole check must finish within this many seconds; slow sources are marked "not verified".
CHECK_DEADLINE_SECONDS = float(os.getenv("CHECK_DEADLINE_SECONDS", "55") or 55)
# Let Gemini rewrite the summary (one extra call per check). Off: the fixed template is used.
AI_SUMMARY = os.getenv("AI_SUMMARY", "false").strip().lower() in ("1", "true", "yes")
GEMINI_BASE = os.getenv("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
# "low" keeps each lookup fast. Leave empty to use the model default.
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
CHECK_TIMEOUT_SECONDS = _float("CHECK_TIMEOUT_SECONDS", 60)

# --- Storage -------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'nexverify.db').as_posix()}")
REDIS_URL = os.getenv("REDIS_URL", "").strip()
CACHE_TTL_SECONDS = int(_float("CACHE_TTL_SECONDS", 24 * 3600))

# --- Behaviour -----------------------------------------------------------------
DEMO_SPEED = _float("DEMO_SPEED", 1.0)  # 2.0 = demo animation runs twice as fast
ENABLE_SCREENSHOTS = _bool("ENABLE_SCREENSHOTS", False)  # needs `playwright install chromium`
ENVIRONMENT = os.getenv("NEXVERIFY_ENV", "development").strip().lower()
PRODUCTION = ENVIRONMENT == "production"
# Browser engines lack a fully pinned egress boundary; keep them off for production.
ALLOW_ACTIVE_BROWSER = _bool("NEXVERIFY_ALLOW_ACTIVE_BROWSER", not PRODUCTION)
ANCHOR_PREPARATION_ENABLED = _bool("NEXVERIFY_ANCHOR_PREPARATION", True)
ANCHOR_CHAIN_ID = int(os.getenv("NEXVERIFY_ANCHOR_CHAIN_ID", "11155111"))
ANCHOR_CONTRACT = os.getenv("NEXVERIFY_ANCHOR_CONTRACT", "0x5FbDB2315678afecb367f032d93F642f64180aa3").strip()
ANCHOR_RPC_URL = os.getenv("NEXVERIFY_ANCHOR_RPC_URL", os.getenv("SEPOLIA_RPC_URL", "")).strip()
ANCHOR_MIN_CONFIRMATIONS = int(os.getenv("NEXVERIFY_ANCHOR_MIN_CONFIRMATIONS", "1"))
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]

# --- Threat Intelligence & External Verifiers (Optional) -----------------------
SAFE_BROWSING_KEY = os.getenv("SAFE_BROWSING_KEY", "").strip()
VT_KEY = os.getenv("VT_KEY", "").strip()
URLSCAN_KEY = os.getenv("URLSCAN_KEY", "").strip()
OTX_KEY = os.getenv("OTX_KEY", "").strip()
BROWSER_PROVIDER_URL = os.getenv("BROWSER_PROVIDER_URL", "").strip()

for _d in (DATA_DIR, EVIDENCE_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def live_enabled() -> bool:
    return bool(GEMINI_API_KEY)
