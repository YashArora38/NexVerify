"""Shared plumbing for the five checkers.

Each checker talks to the outside world only through Ctx:
    ctx.fetch(url)          -> direct page fetch (no key needed)
    ctx.ask(key, prompt)    -> Gemini with Google Search grounding
    ctx.rdap(domain)        -> RDAP domain registration date

In demo mode Ctx answers from made-up fixtures instead of the network, so the
same parsing and scoring code runs either way.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .. import config, web
from ..evidence import EvidenceStore, utc_now
from ..gemini import GeminiResult, get_client

Emit = Callable[[str, dict], Awaitable[None]]


@dataclass
class Ctx:
    check_id: str
    subject: dict
    evidence: EvidenceStore
    emit: Emit
    demo: Any = None  # demo.Scenario when running a demo
    claims_ready: asyncio.Event = field(default_factory=asyncio.Event)
    claims: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    # False when the address already settles the answer (official site, or a
    # clear fake): the Gemini lookups are skipped to save quota.
    ai_allowed: bool = True
    ai_skip_note: tuple[str, str] = ("Not needed for this link", "इस लिंक के लिए ज़रूरी नहीं")

    # ------------------------------------------------------------------ steps
    async def step(self, key: str, message: str) -> None:
        await self.emit("agent", {"key": key, "state": "running", "step": message, "at": utc_now()})

    async def _demo_pause(self, lo: float = 0.6, hi: float = 1.6) -> None:
        await asyncio.sleep(random.uniform(lo, hi) / max(config.DEMO_SPEED, 0.05))

    # ------------------------------------------------------------------ I/O
    async def fetch(self, url: str) -> web.Page:
        if self.demo is not None:
            await self._demo_pause(0.5, 1.2)
            return self.demo.page(url)
        return await web.fetch_page(url)

    async def ask(self, key: str, prompt: str, *, search: bool = True, url_context: bool = False) -> GeminiResult:
        if self.demo is not None:
            await self._demo_pause(1.0, 2.2)
            return self.demo.gemini(key)
        return await get_client().generate(prompt, search=search, url_context=url_context,
                                           timeout=config.CHECK_TIMEOUT_SECONDS)

    async def rdap(self, domain: str) -> dict:
        if self.demo is not None:
            await self._demo_pause(0.4, 0.9)
            return self.demo.rdap(domain)
        return await web.rdap_registration(domain)

    async def wait_for_claims(self, timeout: float = 20.0) -> dict:
        try:
            await asyncio.wait_for(self.claims_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return self.claims

    # ------------------------------------------------------------------ evidence
    def save_gemini(self, key: str, label: str, prompt: str, res: GeminiResult) -> str:
        item = self.evidence.add(key, "search", label, None, {
            "model": config.GEMINI_MODEL if self.demo is None else "demo-fixture",
            "prompt": prompt,
            "google_search_queries": res.queries,
            "sources_returned_by_google": res.sources,
            "answer": res.text,
        }, simulated=self.demo is not None)
        return item["id"]

    def save_page(self, key: str, label: str, page: web.Page) -> str:
        body = f"URL: {page.final_url or page.url}\nHTTP: {page.status}\nTITLE: {page.title}\n\n{page.text[:20000]}"
        item = self.evidence.add(key, "page", label, page.final_url or page.url, body,
                                 simulated=self.demo is not None)
        return item["id"]

    async def maybe_screenshot(self, key: str, url: str) -> str | None:
        if self.demo is not None or not config.ENABLE_SCREENSHOTS or not url:
            return None
        n = len(self.evidence.items) + 1
        fname = f"E{n:02d}_{key}_screenshot.png"
        out = self.evidence.dir / fname
        if await web.screenshot(url, str(out)):
            item = self.evidence.add(key, "screenshot", f"Screenshot of {url}", url, out.read_bytes(), ext="png")
            out.unlink(missing_ok=True)
            return item["id"]
        return None


def new_output(key: str, title: str, method: str) -> dict:
    return {"key": key, "title": title, "method": method, "method_detail": method,
            "status": "running", "data": {}, "evidence_ids": [], "note": "", "note_hi": "",
            "started_at": utc_now(), "_t0": time.monotonic()}


def finish(out: dict, status: str, **kw) -> dict:
    out.update(kw)
    out["status"] = status
    out["finished_at"] = utc_now()
    out["duration_ms"] = int((time.monotonic() - out.pop("_t0", time.monotonic())) * 1000)
    return out


def as_bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.strip().lower() in {"true", "yes", "found", "listed"}:
            return True
        if v.strip().lower() in {"false", "no", "not found", "none"}:
            return False
    return None
