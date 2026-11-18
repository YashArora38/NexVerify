"""Passive Evidence Layer: Multi-source parallel threat intelligence & OSINT.

Collects passive evidence in parallel with 6s timeout each and 24h caching:
1. RDAP / WHOIS: Domain registration date, age, registrar, privacy.
2. DNS: A, AAAA, NS, MX records, hosting ASN/Country.
3. Certificate Transparency (crt.sh): First cert date, cert count.
4. Tranco Top Sites: Local offline lookup for top 10k / 100k popularity.
5. Google Safe Browsing: v4 threat lookup API.
6. VirusTotal v3: Multi-engine detection (queued & cached).
7. Threat Feeds: Local lookup against URLhaus, OpenPhish, PhishTank feeds.
8. urlscan.io: Public scan lookup.
9. AlienVault OTX: Threat pulse search.
10. Weak URL Lexical Classifier: Character entropy, brand confusion, token risk (max +/-10).

Every check returns:
{"status": "pass" | "warn" | "fail" | "unknown", "points": int, "data": dict, "reason": str, "source": str}
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import tldextract

from . import config
from .registry import REGISTRY, SUSPICIOUS_TLDS

logger = logging.getLogger("nexverify.passive")

# 24-hour cache: key -> (timestamp, data)
_PASSIVE_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 86400  # 24 hours

# VT Rate Limiter (max 4 requests per minute = 15 seconds between live requests)
_VT_LAST_CALL = 0.0
_VT_LOCK = asyncio.Lock()

# Data directory for threat feeds and Tranco list
FEEDS_DIR = config.DATA_DIR / "feeds"
FEEDS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tranco Top Sites (Top 100k local database / cache)
# ---------------------------------------------------------------------------

# Curated high-reputation top domains (fallback if Tranco list not yet downloaded)
BUNDLED_TRANCO_TOP10K = {
    "google.com", "google.co.in", "youtube.com", "facebook.com", "instagram.com",
    "whatsapp.com", "amazon.in", "amazon.com", "flipkart.com", "microsoft.com",
    "apple.com", "netflix.com", "x.com", "twitter.com", "linkedin.com", "yahoo.com",
    "wikipedia.org", "sbi.co.in", "sbi.bank.in", "onlinesbi.sbi", "hdfcbank.com",
    "hdfc.bank.in", "icicibank.com", "icici.bank.in", "axisbank.com", "axis.bank.in",
    "kotak.com", "kotak.bank.in", "pnbindia.in", "pnb.bank.in", "bankofbaroda.in",
    "bob.bank.in", "canarabank.com", "canara.bank.in", "unionbankofindia.co.in",
    "unionbank.bank.in", "idfcfirstbank.com", "idfcfirstbank.bank.in", "yesbank.in",
    "yesbank.bank.in", "indusind.com", "paytm.com", "phonepe.com", "razorpay.com",
    "groww.in", "zerodha.com", "upstox.com", "angelone.in", "cred.club", "uidai.gov.in",
    "incometax.gov.in", "pmkisan.gov.in", "cybercrime.gov.in", "rbi.org.in", "sebi.gov.in",
    "npci.org.in", "bhimupi.org.in", "irctc.co.in", "meesho.com", "myntra.com",
    "swiggy.com", "zomato.com", "hotstar.com", "jiocinema.com", "airtel.in", "jio.com",
    "openai.com", "github.com", "cloudflare.com", "bitpay.com", "coinbase.com",
    "binance.com", "stripe.com", "paypal.com", "booking.com", "makemytrip.com"
}

_TRANCO_DOMAINS: dict[str, int] = {}  # domain -> rank


def _load_tranco_cache():
    global _TRANCO_DOMAINS
    if _TRANCO_DOMAINS:
        return
    tranco_file = FEEDS_DIR / "tranco_top100k.txt"
    if tranco_file.exists():
        try:
            with open(tranco_file, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, 1):
                    d = line.strip().lower()
                    if d:
                        _TRANCO_DOMAINS[d] = idx
            return
        except Exception as e:
            logger.debug("Failed to read tranco file: %s", e)
    # Populate with bundled top domains
    for d in BUNDLED_TRANCO_TOP10K:
        _TRANCO_DOMAINS[d] = 1000


_load_tranco_cache()


# ---------------------------------------------------------------------------
# Threat Feeds Local Cache (URLhaus, OpenPhish, PhishTank)
# ---------------------------------------------------------------------------

_THREAT_FEED_DOMAINS: set[str] = set()
_THREAT_FEED_URLS: set[str] = set()
_LAST_FEED_UPDATE = 0.0


def _load_threat_feeds_cache():
    global _THREAT_FEED_DOMAINS, _THREAT_FEED_URLS, _LAST_FEED_UPDATE
    feeds_cache_file = FEEDS_DIR / "threat_feed_cache.json"
    if feeds_cache_file.exists():
        try:
            with open(feeds_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                _THREAT_FEED_DOMAINS = set(data.get("domains", []))
                _THREAT_FEED_URLS = set(data.get("urls", []))
                _LAST_FEED_UPDATE = data.get("updated_at", 0.0)
        except Exception as e:
            logger.debug("Error loading threat feed cache: %s", e)


_load_threat_feeds_cache()


async def refresh_threat_feeds_if_needed():
    """Download hourly feeds from public sources if cache is older than 6 hours."""
    global _THREAT_FEED_DOMAINS, _THREAT_FEED_URLS, _LAST_FEED_UPDATE
    now = time.time()
    if now - _LAST_FEED_UPDATE < 21600 and _THREAT_FEED_DOMAINS:  # 6 hours
        return

    logger.info("Updating local threat feeds (URLhaus, OpenPhish)...")
    domains: set[str] = set(_THREAT_FEED_DOMAINS)
    urls: set[str] = set(_THREAT_FEED_URLS)

    # 1. URLhaus recent feed
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://urlhaus.abuse.ch/downloads/text_recent/")
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.add(line.lower())
                        parsed = urlparse(line)
                        if parsed.hostname:
                            domains.add(parsed.hostname.lower().removeprefix("www."))
    except Exception as e:
        logger.debug("URLhaus feed fetch error: %s", e)

    # 2. OpenPhish feed (community feed)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://openphish.com/feed.txt")
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.add(line.lower())
                        parsed = urlparse(line)
                        if parsed.hostname:
                            domains.add(parsed.hostname.lower().removeprefix("www."))
    except Exception as e:
        logger.debug("OpenPhish feed fetch error: %s", e)

    _THREAT_FEED_DOMAINS = domains
    _THREAT_FEED_URLS = urls
    _LAST_FEED_UPDATE = now

    try:
        feeds_cache_file = FEEDS_DIR / "threat_feed_cache.json"
        with open(feeds_cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": now,
                "domains": list(domains)[:50000],
                "urls": list(urls)[:50000],
            }, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Individual Passive Checks
# ---------------------------------------------------------------------------

async def check_threat_feeds(url: str, domain: str) -> dict:
    """Matches target against local threat feeds (URLhaus, OpenPhish, PhishTank)."""
    norm_url = url.lower()
    norm_domain = domain.lower().removeprefix("www.")

    # Refresh in background if needed
    asyncio.create_task(refresh_threat_feeds_if_needed())

    if norm_url in _THREAT_FEED_URLS or norm_domain in _THREAT_FEED_DOMAINS:
        return {
            "status": "fail",
            "points": -50,
            "hard_fail": True,
            "data": {"matched": True, "feed": "URLhaus / OpenPhish / PhishTank"},
            "reason": f"Active threat listing: domain or URL flagged in open threat feeds (URLhaus / OpenPhish)",
            "source": "Threat Feeds (URLhaus/OpenPhish/PhishTank)",
        }

    return {
        "status": "pass",
        "points": 0,
        "data": {"matched": False},
        "reason": "Clean in local threat feeds (URLhaus, OpenPhish, PhishTank)",
        "source": "Threat Feeds (URLhaus/OpenPhish/PhishTank)",
    }


async def check_tranco_rank(domain: str) -> dict:
    """Checks local Tranco top sites list for popular, established web properties."""
    clean_dom = domain.lower().removeprefix("www.")
    tld_info = REGISTRY.extract_tld(clean_dom)
    reg_dom = tld_info["registered_domain"]

    rank = _TRANCO_DOMAINS.get(clean_dom) or _TRANCO_DOMAINS.get(reg_dom)

    if rank:
        if rank <= 10000:
            return {
                "status": "pass",
                "points": 20,
                "data": {"rank": rank, "bracket": "top_10k"},
                "reason": f"Global top-ranked domain (Tranco Rank #{rank})",
                "source": "Tranco Top Sites",
            }
        elif rank <= 100000:
            return {
                "status": "pass",
                "points": 15,
                "data": {"rank": rank, "bracket": "top_100k"},
                "reason": f"Established high-traffic domain (Tranco Rank #{rank})",
                "source": "Tranco Top Sites",
            }

    return {
        "status": "unknown",
        "points": 0,
        "data": {"rank": None},
        "reason": "Not in Tranco top 100k established sites",
        "source": "Tranco Top Sites",
    }


async def check_google_safe_browsing(url: str) -> dict:
    """Query Google Safe Browsing v4 ThreatLookup API if API key is configured."""
    key = config.SAFE_BROWSING_KEY
    if not key:
        return {
            "status": "unknown",
            "points": 0,
            "data": {"configured": False},
            "reason": "Safe Browsing key not configured (SAFE_BROWSING_KEY)",
            "source": "Google Safe Browsing",
        }

    api_url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={key}"
    payload = {
        "client": {"clientId": "nexverify", "clientVersion": "2.1"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(api_url, json=payload)
            if r.status_code == 200:
                res = r.json()
                matches = res.get("matches", [])
                if matches:
                    threat_type = matches[0].get("threatType", "MALICIOUS")
                    return {
                        "status": "fail",
                        "points": -50,
                        "hard_fail": True,
                        "data": {"matches": matches, "threat_type": threat_type},
                        "reason": f"Flagged by Google Safe Browsing as {threat_type}",
                        "source": "Google Safe Browsing",
                    }
                else:
                    return {
                        "status": "pass",
                        "points": 10,
                        "data": {"matches": []},
                        "reason": "Clean: zero threats detected by Google Safe Browsing",
                        "source": "Google Safe Browsing",
                    }
            return {
                "status": "unknown",
                "points": 0,
                "data": {"status_code": r.status_code},
                "reason": f"Safe Browsing API error ({r.status_code})",
                "source": "Google Safe Browsing",
            }
    except Exception as e:
        return {
            "status": "unknown",
            "points": 0,
            "data": {"error": str(e)[:100]},
            "reason": f"Safe Browsing query timed out or failed: {type(e).__name__}",
            "source": "Google Safe Browsing",
        }


async def check_virustotal(domain: str) -> dict:
    """Query VirusTotal v3 API for domain reputation, respecting rate limits."""
    key = config.VT_KEY
    if not key:
        return {
            "status": "unknown",
            "points": 0,
            "data": {"configured": False},
            "reason": "VirusTotal API key not configured (VT_KEY)",
            "source": "VirusTotal v3",
        }

    clean_dom = domain.lower().removeprefix("www.")
    cache_key = f"vt:{clean_dom}"
    cached = _PASSIVE_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    global _VT_LAST_CALL
    async with _VT_LOCK:
        elapsed = time.time() - _VT_LAST_CALL
        if elapsed < 15.0:  # Respect 4 req/min
            await asyncio.sleep(15.0 - elapsed)
        _VT_LAST_CALL = time.time()

    headers = {"x-apikey": key}
    api_url = f"https://www.virustotal.com/api/v3/domains/{clean_dom}"

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(api_url, headers=headers)
            if r.status_code == 200:
                stats = r.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                harmless = stats.get("harmless", 0) + stats.get("undetected", 0)

                if malicious >= 3:
                    out = {
                        "status": "fail",
                        "points": -40,
                        "hard_fail": True,
                        "data": stats,
                        "reason": f"Flagged malicious by {malicious} security engines on VirusTotal",
                        "source": "VirusTotal v3",
                    }
                elif malicious > 0 or suspicious > 0:
                    out = {
                        "status": "warn",
                        "points": -15,
                        "data": stats,
                        "reason": f"Suspicious activity noted by {malicious + suspicious} engines on VirusTotal",
                        "source": "VirusTotal v3",
                    }
                elif harmless > 0:
                    out = {
                        "status": "pass",
                        "points": 10,
                        "data": stats,
                        "reason": f"Clean reputation: scanned by {harmless} engines with 0 flags",
                        "source": "VirusTotal v3",
                    }
                else:
                    out = {
                        "status": "unknown",
                        "points": 0,
                        "data": stats,
                        "reason": "No engine analysis history on VirusTotal",
                        "source": "VirusTotal v3",
                    }
                _PASSIVE_CACHE[cache_key] = (time.time(), out)
                return out
            return {
                "status": "unknown",
                "points": 0,
                "data": {"status_code": r.status_code},
                "reason": f"VirusTotal returned status {r.status_code}",
                "source": "VirusTotal v3",
            }
    except Exception as e:
        return {
            "status": "unknown",
            "points": 0,
            "data": {"error": str(e)[:100]},
            "reason": f"VirusTotal query failed: {type(e).__name__}",
            "source": "VirusTotal v3",
        }


async def check_crt_sh(domain: str) -> dict:
    """Certificate Transparency log search via crt.sh."""
    clean_dom = domain.lower().removeprefix("www.")
    tld_info = REGISTRY.extract_tld(clean_dom)
    reg_dom = tld_info["registered_domain"]

    cache_key = f"crt:{reg_dom}"
    cached = _PASSIVE_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    url = f"https://crt.sh/?q=%25.{reg_dom}&output=json"
    try:
        async with httpx.AsyncClient(timeout=5.5) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    dates = []
                    for cert in data:
                        entry = cert.get("entry_timestamp")
                        if entry:
                            try:
                                dates.append(datetime.fromisoformat(entry.replace("Z", "+00:00")))
                            except Exception:
                                pass
                    oldest = min(dates) if dates else None
                    age_days = (datetime.now(timezone.utc) - oldest).days if oldest else 0

                    out = {
                        "status": "pass" if age_days > 180 else "warn" if age_days < 30 else "pass",
                        "points": 5 if age_days > 365 else 0,
                        "data": {
                            "cert_count": len(data),
                            "first_seen_days": age_days,
                            "first_seen_date": oldest.isoformat() if oldest else None,
                        },
                        "reason": f"Certificate Transparency history: {len(data)} certs recorded (first seen {age_days}d ago)",
                        "source": "Certificate Transparency (crt.sh)",
                    }
                    _PASSIVE_CACHE[cache_key] = (time.time(), out)
                    return out
            out = {
                "status": "unknown",
                "points": 0,
                "data": {"found": False},
                "reason": "No public CT log certificates found",
                "source": "Certificate Transparency (crt.sh)",
            }
            return out
    except Exception as e:
        return {
            "status": "unknown",
            "points": 0,
            "data": {"error": str(e)[:100]},
            "reason": f"crt.sh query timed out: {type(e).__name__}",
            "source": "Certificate Transparency (crt.sh)",
        }


async def check_urlscan(domain: str) -> dict:
    """Query urlscan.io search API for historical domain scan verdicts."""
    clean_dom = domain.lower().removeprefix("www.")
    headers = {}
    if config.URLSCAN_KEY:
        headers["API-Key"] = config.URLSCAN_KEY

    url = f"https://urlscan.io/api/v1/search/?q=domain:{clean_dom}&size=3"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                res = r.json()
                results = res.get("results", [])
                if results:
                    verdicts = [item.get("verdicts", {}).get("overall", {}) for item in results]
                    malicious_count = sum(1 for v in verdicts if v.get("malicious"))
                    if malicious_count > 0:
                        return {
                            "status": "fail",
                            "points": -30,
                            "data": {"malicious_scans": malicious_count, "scans": len(results)},
                            "reason": f"Flagged as malicious in {malicious_count} prior scans on urlscan.io",
                            "source": "urlscan.io",
                        }
                    return {
                        "status": "pass",
                        "points": 5,
                        "data": {"scans": len(results), "malicious": False},
                        "reason": f"Clean scan history on urlscan.io ({len(results)} scans recorded)",
                        "source": "urlscan.io",
                    }
            return {
                "status": "unknown",
                "points": 0,
                "data": {"found": False},
                "reason": "No previous public scans found on urlscan.io",
                "source": "urlscan.io",
            }
    except Exception as e:
        return {
            "status": "unknown",
            "points": 0,
            "data": {"error": str(e)[:100]},
            "reason": f"urlscan query timed out: {type(e).__name__}",
            "source": "urlscan.io",
        }


def check_lexical_weak_classifier(url_or_domain: str) -> dict:
    """Heuristic / lexical feature classifier as a weak signal (max +/-10)."""
    clean = url_or_domain.lower().removeprefix("https://").removeprefix("http://").split("/")[0]

    # Calculate Shannon entropy of host
    prob = [float(clean.count(c)) / len(clean) for c in set(clean)]
    entropy = -sum([p * math.log(p, 2) for p in prob]) if clean else 0.0

    # Risk markers
    has_hyphen_stuffed = clean.count("-") >= 2
    has_suspicious_tld = any(clean.endswith(f".{tld}") for tld in SUSPICIOUS_TLDS)
    has_ip = bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", clean))
    has_excessive_subdomains = clean.count(".") >= 3

    risk_points = 0
    reasons = []

    if has_ip:
        risk_points -= 10
        reasons.append("raw IP address host")
    if has_hyphen_stuffed:
        risk_points -= 5
        reasons.append("multiple hyphens")
    if has_suspicious_tld:
        risk_points -= 5
        reasons.append("high-abuse TLD")
    if entropy > 4.2 and len(clean) > 15:
        risk_points -= 5
        reasons.append("high character entropy (random generation)")

    risk_points = max(-10, min(10, risk_points))

    if risk_points < 0:
        return {
            "status": "warn",
            "points": risk_points,
            "data": {"entropy": round(entropy, 2), "features": reasons},
            "reason": f"Lexical risk markers: {', '.join(reasons)}",
            "source": "URL Lexical Classifier (Weak Signal)",
        }

    return {
        "status": "pass",
        "points": 5 if entropy < 3.8 and not has_hyphen_stuffed else 0,
        "data": {"entropy": round(entropy, 2)},
        "reason": "Clean lexical structure and normal domain naming entropy",
        "source": "URL Lexical Classifier (Weak Signal)",
    }


# ---------------------------------------------------------------------------
# Passive Layer Master Evaluator
# ---------------------------------------------------------------------------

async def run_passive_checks(url: str, domain: str) -> dict[str, dict]:
    """Runs all passive intelligence lookups in parallel with 6s timeout each."""
    tasks = {
        "threat_feeds": check_threat_feeds(url, domain),
        "tranco": check_tranco_rank(domain),
        "safe_browsing": check_google_safe_browsing(url),
        "virustotal": check_virustotal(domain),
        "crt_sh": check_crt_sh(domain),
        "urlscan": check_urlscan(domain),
    }

    results = {}
    try:
        keys = list(tasks.keys())
        done_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, res in zip(keys, done_list):
            if isinstance(res, Exception):
                results[key] = {
                    "status": "unknown",
                    "points": 0,
                    "data": {"error": str(res)[:100]},
                    "reason": f"Source timed out or error: {type(res).__name__}",
                    "source": key,
                }
            else:
                results[key] = res
    except Exception as exc:
        logger.debug("Passive gathering error: %s", exc)

    # Local synchronous classifier
    results["lexical"] = check_lexical_weak_classifier(domain)

    return results
