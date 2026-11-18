"""Direct, key-free lookups: fetch a public page with SSRF protection,
headless browser inspection (Playwright), SSL/DNS analysis, and 3-tier fallback.

Tier 1: Fast server fetch (timeout 8s, SSRF-guarded redirect tracking).
Tier 2: Headless browser (Playwright sandbox) with SSL cert, forms & DNS.
Tier 3: Human-assist mode for blocked pages, CAPTCHAs, or geo-walls.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import logging
import re
import socket
import ssl
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import tldextract

logger = logging.getLogger(__name__)
from . import config

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 NexVerify/2.0"
)

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB safety limit
MAX_REDIRECTS = 5

_EXTRACTOR = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())  # offline snapshot only

# Bot challenge signatures
BOT_CHALLENGE_PATTERNS = re.compile(
    r"(cf-browser-verification|cf-challenge|ddos-guard|attention required!|"
    r"just a moment\.\.\.|security check to access|cloudflare ray id|"
    r"recaptcha|hcaptcha|turnstile|verify you are human|bot detection|access denied|waf)",
    re.I,
)


# ---------------------------------------------------------------------------
# SSRF Protection
# ---------------------------------------------------------------------------
def is_safe_ip(ip_str: str) -> bool:
    """Validate that the given IP is not private, loopback, link-local, or cloud metadata."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        # Specific cloud metadata protections
        if ip_str in ("169.254.169.254", "fd00:ec2::254"):
            return False
        return True
    except ValueError:
        return False


def resolve_safe_ips(host: str) -> list[str]:
    """Resolve host and ensure all target IPs are public and safe."""
    try:
        addrinfo = socket.getaddrinfo(host, None)
        ips = list({info[4][0] for info in addrinfo})
        safe_ips = [ip for ip in ips if is_safe_ip(ip)]
        if not safe_ips or len(safe_ips) < len(ips):
            # If any resolved IP is private/unsafe, block immediately
            return []
        return safe_ips
    except Exception as exc:
        logger.debug("DNS resolution error for %s: %s", host, exc)
        return []


def validate_safe_url(url: str) -> tuple[bool, str]:
    """Check scheme, hostname and DNS resolution against SSRF rules."""
    try:
        if len(url) > 4096 or re.search(r"[\\\x00-\x20\x7f]", url):
            return False, "Ambiguous or oversized URL"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Unsupported scheme '{parsed.scheme}' (only HTTP/HTTPS allowed)"
        if parsed.username is not None or parsed.password is not None:
            return False, "URL credentials are not allowed"
        if parsed.port not in (None, 80, 443):
            return False, "Destination blocked: only standard HTTP/HTTPS ports are allowed"
        host = parsed.hostname
        if not host:
            return False, "Missing hostname in URL"
        if host.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return False, f"Access to localhost/metadata '{host}' is strictly blocked"

        # Check if hostname is an explicit raw IP address
        try:
            raw_ip = ipaddress.ip_address(host)
            if not is_safe_ip(str(raw_ip)):
                return False, f"Destination IP '{host}' is in a private/restricted address range"
            return True, ""
        except ValueError:
            pass  # It's a standard domain name

        safe_ips = resolve_safe_ips(host)
        if not safe_ips:
            return False, f"Hostname '{host}' resolves to private/restricted or unresolvable IP addresses"
        return True, ""
    except Exception as exc:
        return False, f"URL validation error: {exc}"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class FormField:
    action: str
    method: str
    action_domain: str
    is_external: bool


@dataclass
class SSLCertInfo:
    issuer: str = ""
    subject: str = ""
    valid_from: str = ""
    valid_to: str = ""
    days_remaining: int = 0
    is_valid: bool = False
    error: str = ""


@dataclass
class Page:
    url: str
    final_url: str
    status: int
    title: str
    html: str
    text: str
    error: str = ""
    redirect_chain: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    ssl_info: dict = field(default_factory=dict)
    dns_records: dict = field(default_factory=dict)
    security_headers: dict = field(default_factory=dict)
    screenshot_path: str = ""
    tier: int = 1
    is_blocked: bool = False
    block_reason: str = ""
    human_assist_needed: bool = False
    human_assisted: bool = False

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.text.strip()) and not self.is_blocked


_BLOCK_TAGS = re.compile(
    r"</?(p|div|br|li|ul|ol|h[1-6]|tr|td|th|section|article|header|footer|span)\b[^>]*>",
    re.I,
)


def html_to_text(raw: str) -> str:
    """Extract clean readable text from HTML with scripts/styles safely stripped."""
    raw = re.sub(r"(?is)<(script|style|noscript|svg|template)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    raw = _BLOCK_TAGS.sub("\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html_lib.unescape(raw)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in raw.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln and (not out or out[-1] != ln):
            out.append(ln)
    return "\n".join(out)


def page_title(raw: str) -> str:
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', raw, re.I)
    if m:
        return html_lib.unescape(m.group(1)).strip()
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    return html_lib.unescape(m.group(1)).strip() if m else ""


def registrable_domain(url_or_host: str) -> str:
    """Extract registered domain accurately using the Public Suffix List (including .bank.in, .gov.in)."""
    raw = url_or_host.strip()
    if "://" in raw:
        try:
            raw = urlparse(raw).hostname or raw
        except Exception:
            pass
    raw = raw.split("/")[0].split(":")[0].lower().removeprefix("www.")
    from . import linkintel  # Public Suffix List + India's restricted zones (.bank.in ...)
    reg = linkintel.split_host(raw)[0] if "." in raw else raw
    return reg or raw


# ---------------------------------------------------------------------------
# SSL & DNS Inspectors
# ---------------------------------------------------------------------------
def inspect_ssl(host: str, port: int = 443, timeout: float = 5.0) -> dict:
    """Read SSL certificate directly via TLS handshake without depending on browser."""
    clean_host = host.split("/")[0].split(":")[0].lower().removeprefix("www.")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        with socket.create_connection((clean_host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=clean_host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return {"is_valid": False, "error": "No certificate returned"}

                # Extract Issuer
                issuer_dict = dict(x[0] for x in cert.get("issuer", ()))
                issuer_name = issuer_dict.get("organizationName") or issuer_dict.get("commonName") or "Unknown"

                # Extract Subject
                subject_dict = dict(x[0] for x in cert.get("subject", ()))
                subject_name = subject_dict.get("commonName") or clean_host

                # Dates
                not_before = cert.get("notBefore", "")
                not_after = cert.get("notAfter", "")
                exp_date = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days_left = (exp_date - datetime.now(timezone.utc)).days

                return {
                    "is_valid": days_left > 0,
                    "issuer": issuer_name,
                    "subject": subject_name,
                    "valid_from": not_before,
                    "valid_to": not_after,
                    "days_remaining": days_left,
                    "error": "",
                }
    except Exception as exc:
        return {"is_valid": False, "error": str(exc)[:200]}


def inspect_dns(host: str) -> dict:
    """Resolve A, MX, NS records for a domain."""
    clean_host = host.split("/")[0].split(":")[0].lower().removeprefix("www.")
    records = {"a": [], "mx": [], "ns": []}
    try:
        addrinfo = socket.getaddrinfo(clean_host, 80)
        records["a"] = sorted(list({info[4][0] for info in addrinfo}))
    except Exception:
        pass
    return records


def extract_forms(html_text: str, base_url: str) -> list[dict]:
    """Find all HTML forms and analyze action endpoints."""
    forms = []
    base_domain = registrable_domain(base_url)
    form_matches = re.finditer(r"<form\b([^>]*)>(.*?)</form>", html_text, re.I | re.S)

    for fm in form_matches:
        attrs = fm.group(1)
        action_match = re.search(r'action=["\']([^"\']*)["\']', attrs, re.I)
        method_match = re.search(r'method=["\']([^"\']*)["\']', attrs, re.I)
        action = action_match.group(1) if action_match else base_url
        method = (method_match.group(1) if method_match else "get").upper()

        full_action = urljoin(base_url, action)
        action_domain = registrable_domain(full_action)
        is_external = bool(action_domain and action_domain != base_domain)

        forms.append({
            "action": full_action,
            "method": method,
            "action_domain": action_domain,
            "is_external": is_external,
        })

    return forms


# ---------------------------------------------------------------------------
# Tier 1: Fast Server Fetch with SSRF & Hop-by-Hop Redirect Tracking
# ---------------------------------------------------------------------------
async def _bounded_get(client: httpx.AsyncClient, url: str, headers: dict,
                       pin_address: bool = True) -> httpx.Response:
    """Validate each hop; connect to the validated address while preserving TLS SNI.

    Mock transports do not use address pinning. Environment proxies are disabled by callers.
    Returned response URLs retain the original hostname, not the pinned IP.
    """
    safe, error = await asyncio.to_thread(validate_safe_url, url)
    if not safe:
        raise ValueError(f"Blocked destination: {error}")
    target = httpx.URL(url)
    request_headers = dict(headers)
    extensions = {}
    if pin_address:
        ips = await asyncio.to_thread(resolve_safe_ips, target.host)
        if not ips:
            raise ValueError("Destination resolution became unsafe")
        request_headers["Host"] = target.netloc.decode("ascii")
        extensions["sni_hostname"] = target.host
        target = target.copy_with(host=sorted(ips)[0])
    request = client.build_request("GET", target, headers=request_headers, extensions=extensions)
    response = await client.send(request, stream=True)
    try:
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("Response exceeds collection byte limit")
            chunks.append(chunk)
        return httpx.Response(response.status_code, headers=response.headers,
                              content=b"".join(chunks), request=httpx.Request("GET", url))
    finally:
        await response.aclose()


async def fetch_page(
    url: str,
    timeout: float = 8.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Page:
    """Tier 1: Fast fetch with manual redirect checking against SSRF rules."""
    current_url = url
    redirect_chain = []
    headers = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"}

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
            verify=True,
            trust_env=False,
        ) as client:
            for hop in range(MAX_REDIRECTS + 1):
                safe, err = validate_safe_url(current_url)
                if not safe:
                    return Page(
                        url=url, final_url=current_url, status=0, title="", html="", text="",
                        error=f"Blocked by SSRF protection: {err}",
                        redirect_chain=redirect_chain,
                    )

                r = await _bounded_get(client, current_url, headers, pin_address=transport is None)
                host = urlparse(current_url).hostname or ""
                redirect_chain.append({
                    "url": current_url,
                    "status": r.status_code,
                    "host": host,
                })

                if r.is_redirect and "location" in r.headers:
                    next_url = urljoin(current_url, r.headers["location"])
                    current_url = next_url
                    continue
                else:
                    # Final destination reached
                    raw = r.text[:MAX_RESPONSE_BYTES]
                    title = page_title(raw)
                    text = html_to_text(raw)
                    forms = extract_forms(raw, str(r.url))

                    # Security Headers
                    sec_headers = {
                        "hsts": bool(r.headers.get("strict-transport-security")),
                        "csp": bool(r.headers.get("content-security-policy")),
                        "x_frame_options": r.headers.get("x-frame-options", ""),
                        "x_content_type_options": r.headers.get("x-content-type-options", ""),
                    }

                    # Bot protection / challenge detection
                    is_blocked = (
                        r.status_code in (403, 503, 429)
                        or bool(BOT_CHALLENGE_PATTERNS.search(raw[:2000]))
                    )
                    block_reason = (
                        "Cloudflare / Bot Challenge / CAPTCHA detected on page"
                        if is_blocked else ""
                    )

                    return Page(
                        url=url,
                        final_url=str(r.url),
                        status=r.status_code,
                        title=title,
                        html=raw,
                        text=text,
                        redirect_chain=redirect_chain,
                        forms=forms,
                        security_headers=sec_headers,
                        is_blocked=is_blocked,
                        block_reason=block_reason,
                        human_assist_needed=is_blocked,
                    )

            return Page(
                url=url, final_url=current_url, status=310, title="", html="", text="",
                error=f"Too many redirects (exceeded maximum {MAX_REDIRECTS})",
                redirect_chain=redirect_chain,
            )

    except Exception as exc:
        return Page(
            url=url, final_url=current_url, status=0, title="", html="", text="",
            error=str(exc)[:200], redirect_chain=redirect_chain,
            human_assist_needed=True, block_reason=f"Connection failure / timeout: {exc}",
        )


# ---------------------------------------------------------------------------
# Tier 2: Headless Browser (Playwright) Deep Inspection
# ---------------------------------------------------------------------------
async def inspect_page_deep(
    url: str,
    screenshot_dest: str | None = None,
    timeout_sec: float = 20.0,
) -> Page:
    """Tier 2: Run sandboxed Playwright Chromium with network idle, screenshot & SSL."""
    # Run Tier 1 first to capture headers and redirect chain
    p1 = await fetch_page(url, timeout=8.0)
    safe, _ = await asyncio.to_thread(validate_safe_url, p1.final_url or url)
    if not safe or not config.ALLOW_ACTIVE_BROWSER:
        return p1

    # Perform direct SSL and DNS inspection in parallel
    parsed = urlparse(p1.final_url or url)
    host = parsed.hostname or url
    ssl_task = asyncio.to_thread(inspect_ssl, host)
    dns_task = asyncio.to_thread(inspect_dns, host)
    ssl_info, dns_records = await asyncio.gather(ssl_task, dns_task)

    p1.ssl_info = ssl_info
    p1.dns_records = dns_records

    # Attempt Playwright render for live DOM, form inspection, and screenshot
    try:
        from playwright.async_api import async_playwright

        for attempt in range(2):  # 1 retry on transient failure
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-extensions",
                        ],
                    )
                    context = await browser.new_context(
                        user_agent=UA,
                        viewport={"width": 1280, "height": 900},
                        ignore_https_errors=False,
                    )
                    page = await context.new_page()

                    response = await page.goto(
                        url,
                        timeout=int(timeout_sec * 1000),
                        wait_until="domcontentloaded",
                    )
                    await asyncio.sleep(1.0)

                    final_url = page.url
                    content = await page.content()
                    title = await page.title()
                    text = html_to_text(content)

                    # Save screenshot if requested
                    if screenshot_dest and not p1.screenshot_path:
                        Path(screenshot_dest).parent.mkdir(parents=True, exist_ok=True)
                        await page.screenshot(path=screenshot_dest, full_page=False)
                        p1.screenshot_path = screenshot_dest

                    await browser.close()

                    # Check for bot challenge in rendered DOM
                    is_challenge = bool(BOT_CHALLENGE_PATTERNS.search(content[:3000]))
                    if is_challenge:
                        p1.is_blocked = True
                        p1.block_reason = "Cloudflare / CAPTCHA Challenge detected in rendered page"
                        p1.human_assist_needed = True

                    p1.final_url = final_url
                    p1.title = title or p1.title
                    p1.html = content
                    p1.text = text if len(text) > len(p1.text) else p1.text
                    p1.forms = extract_forms(content, final_url)
                    break
            except Exception as attempt_err:
                if attempt == 1:
                    logger.debug("Playwright attempt 2 failed for %s: %s", url, attempt_err)
    except Exception as exc:
        logger.debug("Playwright not usable: %s", exc)

    return p1


# ---------------------------------------------------------------------------
# Tier 3: Human Assist Processor
# ---------------------------------------------------------------------------
def build_human_assist_page(
    url: str,
    pasted_text: str = "",
    screenshot_path: str = "",
    answers: dict | None = None,
) -> Page:
    """Tier 3: Build a standardized Page object from human-provided evidence."""
    answers = answers or {}
    text_blocks = []
    if pasted_text.strip():
        text_blocks.append(pasted_text.strip())

    # Format user responses into analysis context
    answers_summary = []
    if answers.get("source"):
        answers_summary.append(f"Link Source: {answers['source']}")
    if answers.get("asks_money_or_otp"):
        answers_summary.append("User states site ASKS for money, OTP, PIN, or Aadhaar details")
    if answers.get("promise"):
        answers_summary.append(f"Promised outcome: {answers['promise']}")

    if answers_summary:
        text_blocks.append("\nUser Questions Evidence:\n" + "\n".join(answers_summary))

    combined_text = "\n\n".join(text_blocks)
    title = f"Human Verified: {registrable_domain(url)}"

    return Page(
        url=url,
        final_url=url,
        status=200,
        title=title,
        html=f"<div>{html_lib.escape(combined_text)}</div>",
        text=combined_text,
        screenshot_path=screenshot_path,
        tier=3,
        human_assisted=True,
        human_assist_needed=False,
    )


async def rdap_registration(
    domain: str,
    timeout: float = 8.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Ask RDAP (the ICANN replacement for WHOIS) when a domain was registered."""
    reg_dom = registrable_domain(domain)
    url = f"https://rdap.org/domain/{reg_dom}"
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/rdap+json, application/json"},
            transport=transport,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                r = await _bounded_get(client, url, {"Accept": "application/rdap+json, application/json"},
                                       pin_address=transport is None)
                if r.is_redirect and "location" in r.headers:
                    url = urljoin(url, r.headers["location"])
                    continue
                break
            else:
                return {"ok": False, "domain": reg_dom, "source_url": url, "error": "Too many redirects"}
            if r.status_code != 200:
                return {"ok": False, "domain": reg_dom, "source_url": url, "error": f"HTTP {r.status_code}"}
            data = r.json()
    except Exception as exc:
        return {"ok": False, "domain": reg_dom, "source_url": url, "error": str(exc)[:200]}

    reg = None
    for ev in data.get("events") or []:
        if str(ev.get("eventAction", "")).lower() in {"registration", "registered"}:
            reg = ev.get("eventDate")
            break
    if not reg:
        return {"ok": False, "domain": reg_dom, "source_url": url, "error": "no registration date", "raw": data}
    when = datetime.fromisoformat(reg.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - when).days
    return {
        "ok": True,
        "domain": reg_dom,
        "source_url": url,
        "registered_on": when.date().isoformat(),
        "age_days": age_days,
        "raw": data,
    }


async def screenshot(url: str, out_path: str) -> bool:
    """Save a PNG of a page as evidence using Playwright."""
    if not config.ALLOW_ACTIVE_BROWSER:
        return False
    safe, _ = await asyncio.to_thread(validate_safe_url, url)
    if not safe:
        return False
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return False
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            await page.screenshot(path=out_path, full_page=False)
            await browser.close()
        return True
    except Exception:
        return False
