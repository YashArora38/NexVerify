"""Small async client for the Gemini API (generateContent).

Only two things are used:
  * Google Search grounding  -> tools=[{"google_search": {}}]
  * URL context              -> tools=[{"url_context": {}}]

Every grounded answer comes back with the search queries Gemini ran and the
source pages it used. Those are saved as evidence and used to cross-check
what Gemini says (a link it "cites" but never actually retrieved is ignored).
"""
from __future__ import annotations

import asyncio
import time
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config


class GeminiError(RuntimeError):
    pass


@dataclass
class GeminiResult:
    text: str
    data: Any = None  # parsed JSON object, if the answer contained one
    queries: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)  # [{"title", "url"}]
    raw: dict = field(default_factory=dict)

    def source_hosts(self) -> set[str]:
        hosts: set[str] = set()
        for s in self.sources:
            for value in (s.get("title") or "", s.get("url") or ""):
                h = host_of(value) if "://" in value else value.strip().lower()
                if h and "vertexaisearch" not in h and "grounding-api" not in h:
                    hosts.add(h.removeprefix("www."))
        return hosts


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def url_is_grounded(url: str | None, result: GeminiResult) -> bool:
    """True when the URL's site is one Google Search actually returned."""
    if not url:
        return False
    h = host_of(url)
    if not h:
        return False
    for src in result.source_hosts():
        if h == src or h.endswith("." + src) or src.endswith("." + h):
            return True
    return False


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json_loose(text: str) -> Any:
    """Pull the first JSON object out of a model answer (handles ``` fences)."""
    if not text:
        return None
    candidates = [m.group(1) for m in _JSON_FENCE.finditer(text)] + [text]
    for chunk in candidates:
        chunk = chunk.strip()
        try:
            return json.loads(chunk)
        except Exception:
            pass
        start = chunk.find("{")
        while start != -1:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(chunk)):
                c = chunk[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(chunk[start : i + 1])
                        except Exception:
                            break
            start = chunk.find("{", start + 1)
    return None


class GeminiQuotaError(GeminiError):
    """The free quota is used up (HTTP 429)."""


def _retry_delay(text: str, default: float) -> float:
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text) or re.search(r"retry in (\d+(?:\.\d+)?)\s*s", text, re.I)
    return float(m.group(1)) if m else default


def _daily_quota(text: str) -> bool:
    return bool(re.search(r"PerDay|per day|daily", text, re.I))


class _Quota:
    """Remembers that the quota ran out, so later calls fail at once instead of waiting."""

    def __init__(self) -> None:
        self.until = 0.0

    def block(self, seconds: float) -> None:
        self.until = max(self.until, time.monotonic() + seconds)

    def blocked(self) -> bool:
        return time.monotonic() < self.until

    def wait_text(self) -> str:
        left = int(self.until - time.monotonic())
        return f"{left // 60} min" if left >= 60 else f"{max(1, left)} s"


class _Limiter:
    """Allows at most GEMINI_RPM calls in any 60-second window. Calls inside the
    limit go straight through (one check makes 3-5), extra calls wait their turn."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.times: list[float] = []

    async def wait(self) -> None:
        limit = max(1, config.GEMINI_RPM)
        async with self.lock:
            while True:
                now = time.monotonic()
                self.times = [t for t in self.times if now - t < 60.0]
                if len(self.times) < limit:
                    self.times.append(now)
                    return
                await asyncio.sleep(60.0 - (now - self.times[0]) + 0.01)


_quota = _Quota()
_limiter = _Limiter()


class Gemini:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.model = model or config.GEMINI_MODEL
        self.base = config.GEMINI_BASE
        self.thinking_level = config.GEMINI_THINKING_LEVEL
        self._transport = transport
        self.retry_delay = 1.5

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def generate(
        self,
        prompt: str,
        *,
        search: bool = False,
        url_context: bool = False,
        json_mode: bool = False,
        timeout: float = 45.0,
    ) -> GeminiResult:
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not set")

        tools: list[dict] = []
        if search:
            tools.append({"google_search": {}})
        if url_context:
            tools.append({"url_context": {}})

        gen_cfg: dict[str, Any] = {}
        # JSON mime type is only requested when no tools are attached; with
        # tools we ask for JSON in the prompt and parse it loosely.
        if json_mode and not tools:
            gen_cfg["responseMimeType"] = "application/json"
        if self.thinking_level:
            gen_cfg["thinkingConfig"] = {"thinkingLevel": self.thinking_level}

        body: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if tools:
            body["tools"] = tools
        if gen_cfg:
            body["generationConfig"] = gen_cfg

        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        # Grounding is never dropped silently: an answer from memory would be
        # stored as if Google had found it. If search fails, the call fails and
        # the check is marked "not verified" instead.
        models = [self.model] + [m for m in config.GEMINI_FALLBACK_MODELS if m and m != self.model]
        if _quota.blocked():
            raise GeminiQuotaError(f"Gemini quota used up; retry after {_quota.wait_text()}")

        last_err = ""
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            for current_model in models:
                url = f"{self.base}/models/{current_model}:generateContent"
                retries = 0
                while True:
                    await _limiter.wait()
                    try:
                        resp = await client.post(url, headers=headers, json=body)
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        last_err = f"Network/Timeout: {type(exc).__name__}"
                        break
                    if resp.status_code == 200:
                        self.model = current_model
                        return self._parse(resp.json())
                    last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    if resp.status_code == 400 and "thinking" in resp.text.lower() and "thinkingConfig" in (body.get("generationConfig") or {}):
                        body["generationConfig"].pop("thinkingConfig", None)
                        if not body["generationConfig"]:
                            body.pop("generationConfig")
                        self.thinking_level = ""
                        continue  # not a retry: the request was simply rejected for that one setting
                    if resp.status_code in (401, 403):
                        raise GeminiError(last_err)  # bad key or API not enabled: other models won't help
                    if resp.status_code == 404:
                        break  # model name not available: try the next one
                    if resp.status_code == 429:
                        delay = _retry_delay(resp.text, self.retry_delay * (retries + 1))
                        # If tools were attached and search quota failed, gracefully drop tools first
                        if "tools" in body:
                            body.pop("tools", None)
                            continue
                        if _daily_quota(resp.text) or delay > config.GEMINI_MAX_WAIT_SECONDS:
                            _quota.block(max(delay, 60.0))
                            raise GeminiQuotaError(last_err)
                        if retries < 2:
                            retries += 1
                            await asyncio.sleep(delay)
                            continue
                        _quota.block(max(delay, 20.0))
                        raise GeminiQuotaError(last_err)
                    if resp.status_code in (500, 502, 503, 504) and retries < 1:
                        retries += 1
                        await asyncio.sleep(self.retry_delay)
                        continue
                    break

        raise GeminiError(last_err)

    @staticmethod
    def _parse(payload: dict) -> GeminiResult:
        cands = payload.get("candidates") or []
        if not cands:
            fb = payload.get("promptFeedback") or {}
            raise GeminiError(f"No answer from Gemini (blocked: {fb.get('blockReason', 'unknown')})")
        cand = cands[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        gm = cand.get("groundingMetadata") or {}
        queries = list(gm.get("webSearchQueries") or [])
        sources = []
        for ch in gm.get("groundingChunks") or []:
            web = ch.get("web") or {}
            if web.get("uri") or web.get("title"):
                sources.append({"title": web.get("title", ""), "url": web.get("uri", "")})
        # URL-context results list the pages that were actually read.
        ucm = cand.get("urlContextMetadata") or cand.get("url_context_metadata") or {}
        for meta in ucm.get("urlMetadata") or ucm.get("url_metadata") or []:
            u = meta.get("retrievedUrl") or meta.get("retrieved_url")
            status = str(meta.get("urlRetrievalStatus") or meta.get("url_retrieval_status") or "")
            if u and "SUCCESS" in status.upper():
                sources.append({"title": host_of(u), "url": u})

        data = parse_json_loose(text)
        return GeminiResult(text=text, data=data, queries=queries,
                            sources=sources, raw=payload)


_client: Gemini | None = None


def get_client() -> Gemini:
    global _client
    if _client is None:
        _client = Gemini()
    return _client


def set_client(client: Gemini | None) -> None:
    """Tests swap in a client with a mock transport."""
    global _client
    _client = client
    _quota.until = 0.0
    _limiter.last = 0.0
