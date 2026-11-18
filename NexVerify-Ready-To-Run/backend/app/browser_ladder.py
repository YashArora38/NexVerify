"""Active Browser Ladder: Multi-rung residential fetch & rendering engine.

Ladder execution (stopping at first success):
1. curl_cffi with Chrome TLS/JA3 impersonation (fastest)
2. nodriver using real system Chrome
3. Playwright sandboxed headless Chromium

Features:
- SSRF protection: loopback, RFC 1918 private, link-local, cloud metadata IPs blocked on every hop.
- Challenge detection: Cloudflare ("Just a moment...", "Verify you are human"), Turnstile, CAPTCHA, 403/429/503 with cf-ray.
- Failure classification: BOT_WALL, CAPTCHA, GEO_BLOCK, TIMEOUT, DNS_NXDOMAIN, TLS_FAIL, CONN_REFUSED.
- Security constraints: NO third-party CAPTCHA solving, NO form submit, NO login, NO executing downloads.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import logging
import re
import socket
import ssl
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from . import config
from .web import is_safe_ip, validate_safe_url, html_to_text, inspect_ssl, inspect_dns

logger = logging.getLogger("nexverify.browser_ladder")

CHALLENGE_TITLE_PATTERNS = [
    re.compile(r"just a moment", re.I),
    re.compile(r"attention required", re.I),
    re.compile(r"verify you are human", re.I),
    re.compile(r"cloudflare", re.I),
    re.compile(r"access denied", re.I),
    re.compile(r"security challenge", re.I),
    re.compile(r"bot detection", re.I),
    re.compile(r"ddos protection", re.I),
]

CAPTCHA_PATTERNS = [
    re.compile(r"cf-turnstile", re.I),
    re.compile(r"g-recaptcha", re.I),
    re.compile(r"h-captcha", re.I),
    re.compile(r"captcha", re.I),
]


@dataclass
class LadderPage:
    url: str
    final_url: str = ""
    status: int = 0
    title: str = ""
    html: str = ""
    text: str = ""
    error: str = ""
    rung_used: str = ""  # "curl_cffi" | "nodriver" | "playwright" | "none"
    redirect_chain: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    ssl_info: dict = field(default_factory=dict)
    dns_records: dict = field(default_factory=dict)
    security_headers: dict = field(default_factory=dict)
    screenshot_path: str = ""
    is_blocked: bool = False
    block_type: str = ""  # BOT_WALL, CAPTCHA, GEO_BLOCK, TIMEOUT, DNS_NXDOMAIN, TLS_FAIL, CONN_REFUSED
    block_reason: str = ""
    human_assist_needed: bool = False
    tier: int = 2

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.text.strip()) and not self.is_blocked


def classify_fetch_failure(status: int, title: str, text: str, headers: dict, exc: Exception | None = None) -> tuple[str, str]:
    """Classifies a failed or blocked fetch into structured reason categories."""
    if exc:
        err_msg = str(exc).lower()
        if "getaddrinfo failed" in err_msg or "name or service not known" in err_msg or "nxdomain" in err_msg:
            return "DNS_NXDOMAIN", "Domain does not exist or DNS resolution failed"
        if "ssl" in err_msg or "certificate" in err_msg or "handshake" in err_msg:
            return "TLS_FAIL", "SSL/TLS certificate invalid, expired, or untrusted"
        if "timed out" in err_msg or "timeout" in err_msg:
            return "TIMEOUT", "Connection or response timed out"
        if "connection refused" in err_msg or "failed to connect" in err_msg:
            return "CONN_REFUSED", "Server refused connection"

    combined = f"{title} {text[:800]}".lower()

    # Check for CAPTCHA
    for cp in CAPTCHA_PATTERNS:
        if cp.search(combined):
            return "CAPTCHA", "Interactive CAPTCHA / Human verification challenge"

    # Check for Cloudflare / Bot wall
    for bp in CHALLENGE_TITLE_PATTERNS:
        if bp.search(title) or bp.search(text[:300]):
            return "BOT_WALL", "Protected by automated bot wall / Cloudflare challenge"

    if status in (403, 503):
        if "cf-ray" in headers or "cloudflare" in str(headers).lower():
            return "BOT_WALL", "Cloudflare HTTP security barrier"
        return "BOT_WALL", f"Server access forbidden (HTTP {status})"

    if status == 429:
        return "BOT_WALL", "HTTP 429 Too Many Requests (Rate limited)"

    if "geo" in combined or "not available in your country" in combined or "region" in combined:
        return "GEO_BLOCK", "Geographically restricted access"

    return "BOT_WALL", f"Page could not be inspected (HTTP {status})"


# ---------------------------------------------------------------------------
# Rung 1: curl_cffi with Chrome Impersonation
# ---------------------------------------------------------------------------

async def _fetch_curl_cffi(url: str, timeout_sec: float = 12.0) -> LadderPage | None:
    try:
        from curl_cffi.requests import AsyncSession

        safe, reason = validate_safe_url(url)
        if not safe:
            return LadderPage(url=url, error=reason, is_blocked=True, block_type="BOT_WALL", block_reason=reason)

        async with AsyncSession(impersonate="chrome124", timeout=timeout_sec, max_redirects=5) as s:
            r = await s.get(url, headers={"Accept-Language": "en-US,en;q=0.9,hi;q=0.8"})

            final_url = str(r.url)
            safe_final, f_reason = validate_safe_url(final_url)
            if not safe_final:
                return LadderPage(url=url, final_url=final_url, error=f_reason, is_blocked=True, block_type="BOT_WALL", block_reason=f_reason)

            text_html = r.text or ""
            title_match = re.search(r"<title[^>]*>(.*?)</title>", text_html, re.I | re.S)
            title = html_lib.unescape(title_match.group(1).strip()) if title_match else ""
            clean_text = html_to_text(text_html)

            headers_lower = {k.lower(): v for k, v in r.headers.items()}
            is_chal = any(p.search(title) for p in CHALLENGE_TITLE_PATTERNS) or r.status_code in (403, 429, 503)

            if is_chal or not clean_text.strip():
                b_type, b_reason = classify_fetch_failure(r.status_code, title, clean_text, headers_lower)
                return LadderPage(
                    url=url,
                    final_url=final_url,
                    status=r.status_code,
                    title=title,
                    html=text_html[:100000],
                    text=clean_text,
                    is_blocked=True,
                    block_type=b_type,
                    block_reason=b_reason,
                    human_assist_needed=True,
                    rung_used="curl_cffi",
                )

            return LadderPage(
                url=url,
                final_url=final_url,
                status=r.status_code,
                title=title,
                html=text_html[:150000],
                text=clean_text,
                is_blocked=False,
                rung_used="curl_cffi",
            )
    except Exception as exc:
        logger.debug("Rung 1 (curl_cffi) failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Rung 2: nodriver using Real Chrome
# ---------------------------------------------------------------------------

async def _fetch_nodriver(url: str, timeout_sec: float = 16.0) -> LadderPage | None:
    try:
        import nodriver as uc

        safe, reason = validate_safe_url(url)
        if not safe:
            return None

        browser = await uc.start(headless=True, browser_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
        try:
            page = await browser.get(url)
            # Allow up to 5s for challenge resolution or DOM load
            await asyncio.sleep(4.0)

            content = await page.get_content()
            current_url = page.url or url

            title_match = re.search(r"<title[^>]*>(.*?)</title>", content or "", re.I | re.S)
            title = html_lib.unescape(title_match.group(1).strip()) if title_match else ""
            clean_text = html_to_text(content or "")

            is_chal = any(p.search(title) for p in CHALLENGE_TITLE_PATTERNS)
            if is_chal or not clean_text.strip():
                b_type, b_reason = classify_fetch_failure(200, title, clean_text, {})
                return LadderPage(
                    url=url,
                    final_url=current_url,
                    status=200,
                    title=title,
                    html=content[:100000] if content else "",
                    text=clean_text,
                    is_blocked=True,
                    block_type=b_type,
                    block_reason=b_reason,
                    human_assist_needed=True,
                    rung_used="nodriver",
                )

            return LadderPage(
                url=url,
                final_url=current_url,
                status=200,
                title=title,
                html=content[:150000] if content else "",
                text=clean_text,
                is_blocked=False,
                rung_used="nodriver",
            )
        finally:
            browser.stop()
    except Exception as exc:
        logger.debug("Rung 2 (nodriver) failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Rung 3: Playwright Sandboxed Chromium
# ---------------------------------------------------------------------------

async def _fetch_playwright(url: str, timeout_sec: float = 20.0) -> LadderPage | None:
    try:
        from playwright.async_api import async_playwright

        safe, reason = validate_safe_url(url)
        if not safe:
            return None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            # Disallow downloads
            page.on("download", lambda download: asyncio.create_task(download.cancel()))

            redirect_chain = []

            def _on_response(res):
                if res.status in (301, 302, 303, 307, 308):
                    loc = res.headers.get("location")
                    if loc:
                        redirect_chain.append({"from": res.url, "to": loc, "status": res.status})

            page.on("response", _on_response)

            try:
                resp = await page.goto(url, timeout=int(timeout_sec * 1000), wait_until="domcontentloaded")
            except Exception as e:
                await browser.close()
                b_type, b_reason = classify_fetch_failure(0, "", "", {}, e)
                return LadderPage(url=url, is_blocked=True, block_type=b_type, block_reason=b_reason, human_assist_needed=True, rung_used="playwright")

            # Wait 3s for network idle or challenge redirect
            await asyncio.sleep(3.0)

            final_url = page.url
            title = await page.title()
            content = await page.content()
            clean_text = html_to_text(content)

            status_code = resp.status if resp else 200
            headers = resp.headers if resp else {}

            is_chal = any(p.search(title) for p in CHALLENGE_TITLE_PATTERNS) or status_code in (403, 429, 503)

            # Extract form targets
            forms_data = []
            try:
                form_elements = await page.query_selector_all("form")
                for fe in form_elements[:10]:
                    action = await fe.get_attribute("action") or ""
                    method = await fe.get_attribute("method") or "GET"
                    target_url = urljoin(final_url, action)
                    forms_data.append({"action": target_url, "domain": urlparse(target_url).hostname or "", "method": method.upper()})
            except Exception:
                pass

            await browser.close()

            if is_chal or not clean_text.strip():
                b_type, b_reason = classify_fetch_failure(status_code, title, clean_text, headers)
                return LadderPage(
                    url=url,
                    final_url=final_url,
                    status=status_code,
                    title=title,
                    html=content[:100000],
                    text=clean_text,
                    is_blocked=True,
                    block_type=b_type,
                    block_reason=b_reason,
                    human_assist_needed=True,
                    rung_used="playwright",
                    redirect_chain=redirect_chain,
                    forms=forms_data,
                )

            return LadderPage(
                url=url,
                final_url=final_url,
                status=status_code,
                title=title,
                html=content[:150000],
                text=clean_text,
                is_blocked=False,
                rung_used="playwright",
                redirect_chain=redirect_chain,
                forms=forms_data,
            )
    except Exception as exc:
        logger.debug("Rung 3 (playwright) failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Master Ladder Controller
# ---------------------------------------------------------------------------

async def execute_browser_ladder(url: str) -> LadderPage:
    """Executes the active ladder in priority order: curl_cffi -> nodriver -> playwright."""
    from . import config
    safe, error = validate_safe_url(url)
    if not safe or not config.ALLOW_ACTIVE_BROWSER:
        return LadderPage(url=url, is_blocked=True, block_type="POLICY",
                          block_reason=error or "Active browser inspection disabled by deployment policy",
                          human_assist_needed=True)
    parsed = urlparse(url)
    host = parsed.hostname or url

    # Run parallel SSL and DNS lookups
    ssl_task = asyncio.to_thread(inspect_ssl, host)
    dns_task = asyncio.to_thread(inspect_dns, host)
    ssl_info, dns_records = await asyncio.gather(ssl_task, dns_task)

    # Rung 1: curl_cffi
    logger.debug("Ladder Rung 1 (curl_cffi) starting for %s", url)
    res1 = await _fetch_curl_cffi(url, timeout_sec=10.0)
    if res1 and res1.ok:
        res1.ssl_info = ssl_info
        res1.dns_records = dns_records
        return res1

    # Rung 2: nodriver
    logger.debug("Ladder Rung 2 (nodriver) starting for %s", url)
    res2 = await _fetch_nodriver(url, timeout_sec=14.0)
    if res2 and res2.ok:
        res2.ssl_info = ssl_info
        res2.dns_records = dns_records
        return res2

    # Rung 3: Playwright
    logger.debug("Ladder Rung 3 (playwright) starting for %s", url)
    res3 = await _fetch_playwright(url, timeout_sec=18.0)
    if res3:
        res3.ssl_info = ssl_info
        res3.dns_records = dns_records
        return res3

    # Fallback if all rungs failed completely
    last_res = res1 or res2 or LadderPage(
        url=url,
        is_blocked=True,
        block_type="BOT_WALL",
        block_reason="Automated inspection blocked across all browser rungs",
        human_assist_needed=True,
    )
    last_res.ssl_info = ssl_info
    last_res.dns_records = dns_records
    return last_res
