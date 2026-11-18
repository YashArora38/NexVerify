"""App Store & Play Store Detection and Verification for NexVerify.

Performs live, authoritative lookups on:
  1. Apple App Store (via official Apple iTunes Search API, country=IN)
  2. Google Play Store (via direct package lookup & web search)

Verifies developer identity, store listings, ratings, and official websites.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import urllib.parse
from typing import Any

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


async def search_apple_app_store(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Query Apple's official iTunes Search API for iOS apps in India."""
    q = query.strip()
    if not q:
        return []
    encoded = urllib.parse.quote(q)
    url = f"https://itunes.apple.com/search?term={encoded}&country=in&entity=software&limit={limit}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            for item in data.get("results", []):
                results.append({
                    "store": "apple_app_store",
                    "app_name": item.get("trackName") or item.get("trackCensoredName") or "",
                    "developer": item.get("sellerName") or item.get("artistName") or "",
                    "bundle_id": item.get("bundleId") or "",
                    "app_store_url": item.get("trackViewUrl") or "",
                    "website_url": item.get("sellerUrl") or "",
                    "genres": item.get("genres") or [],
                    "primary_genre": item.get("primaryGenreName") or "",
                    "rating": float(item.get("averageUserRating") or 0.0),
                    "rating_count": int(item.get("userRatingCount") or 0),
                    "price": float(item.get("price") or 0.0),
                    "version": item.get("version") or "",
                    "description": item.get("description") or "",
                })
            return results
    except Exception:
        return []


async def check_play_store_package(package_id: str) -> dict[str, Any] | None:
    """Check a specific Google Play package ID directly."""
    if not package_id or not re.match(r"^[a-zA-Z0-9._]+$", package_id):
        return None
    url = f"https://play.google.com/store/apps/details?id={package_id}&hl=en_IN&gl=IN"
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            body = resp.text
            title_m = re.search(r"<title[^>]*>(.*?)</title>", body)
            title = html.unescape(title_m.group(1)).replace(" – Apps on Google Play", "").strip() if title_m else package_id

            # Developer name extraction
            dev_m = re.search(r'/store/apps/developer\?id=([^"&>]+)', body) or re.search(r'/store/apps/dev\?id=([0-9]+)', body)
            developer = urllib.parse.unquote(dev_m.group(1)) if dev_m else ""

            # Rating extraction
            rating_m = re.search(r'aria-label="Rated ([0-9.]+) stars out of', body) or re.search(r'"([0-9.]+)\s+stars"', body)
            rating = float(rating_m.group(1)) if rating_m else 0.0

            return {
                "store": "google_play",
                "app_name": title,
                "developer": developer,
                "package_id": package_id,
                "play_url": url,
                "rating": rating,
                "verified": True,
            }
    except Exception:
        return None


async def search_google_play_store(query: str) -> dict[str, Any] | None:
    """Search Google Play Store for an app query."""
    q = query.strip()
    if not q:
        return None
    encoded = urllib.parse.quote(q)
    url = f"https://play.google.com/store/search?q={encoded}&c=apps&hl=en_IN&gl=IN"
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            pkg_ids = list(dict.fromkeys(re.findall(r'/store/apps/details\?id=([a-zA-Z0-9._]+)', resp.text)))
            # Exclude common system/google packages unless specifically queried
            filtered = [p for p in pkg_ids if not p.startswith("com.google.android.") or "google" in q.lower()]
            if not filtered and pkg_ids:
                filtered = pkg_ids
            if filtered:
                top_pkg = filtered[0]
                return await check_play_store_package(top_pkg)
    except Exception:
        pass
    return None


STOP_WORDS = {"app", "the", "some", "any", "unknown", "thing", "new", "test", "free", "best", "top"}


async def resolve_app_details(query: str) -> dict[str, Any] | None:
    """Resolve an entity query across Apple App Store and Google Play Store."""
    q = query.strip()
    # Normalize query for app search: remove trailing .com, .in, https://, etc.
    clean = re.sub(r"^https?://(www\.)?", "", q).split("/")[0]
    clean = re.sub(r"\.(com|in|co\.in|org|net|app)$", "", clean, flags=re.I)
    clean = clean.replace("-", " ").strip()

    words = [w for w in re.findall(r"[a-z0-9]+", clean.lower()) if len(w) > 2]
    if not words or all(w in STOP_WORDS for w in words):
        return None

    apple_task = search_apple_app_store(clean)
    play_search_task = search_google_play_store(clean)

    apple_results, play_result = await asyncio.gather(apple_task, play_search_task, return_exceptions=True)
    apple_results = apple_results if isinstance(apple_results, list) else []
    play_result = play_result if isinstance(play_result, dict) else None

    # Check top Apple match - require actual query name overlap
    top_apple = None
    if apple_results:
        clean_lower = clean.lower()
        clean_words = [w for w in re.findall(r"[a-z0-9]+", clean_lower) if len(w) > 2]
        for cand in apple_results:
            cand_name = cand["app_name"].lower()
            cand_words = [w for w in re.findall(r"[a-z0-9]+", cand_name) if len(w) > 2]
            if clean_lower in cand_name or cand_name in clean_lower:
                top_apple = cand
                break
            if clean_words and any(w in cand_words or any(w in cw for cw in cand_words) for w in clean_words):
                top_apple = cand
                break

    # If Apple provided a bundle_id, check if Google Play has that exact package first
    if top_apple and top_apple.get("bundle_id"):
        play_direct = await check_play_store_package(top_apple["bundle_id"])
        if play_direct:
            play_result = play_direct

    # If play_result exists from generic search, verify it actually matches the query
    if play_result and not top_apple:
        p_name = play_result["app_name"].lower()
        clean_lower = clean.lower()
        if clean_lower not in p_name and not any(w in p_name for w in re.findall(r"[a-z0-9]+", clean_lower) if len(w) > 2):
            play_result = None

    if not top_apple and not play_result:
        return None

    display_name = (top_apple.get("app_name") if top_apple else play_result.get("app_name")) or clean
    # Clean up name if it has long subtitles like "Inshorts - News in 60 words"
    display_name_short = re.split(r"[:\-|–]", display_name)[0].strip()

    website_url = top_apple.get("website_url") if top_apple else None

    category = "company/service"
    if top_apple:
        genres = [g.lower() for g in top_apple.get("genres", [])]
        primary = top_apple.get("primary_genre", "").lower()
        if "news" in primary or "news" in genres:
            category = "news / media"
        elif "finance" in primary or "finance" in genres:
            category = "bank/UPI/payment"
        elif "shopping" in primary or "shopping" in genres:
            category = "shopping/e-commerce"

    return {
        "is_app": True,
        "display_name": display_name_short,
        "full_name": display_name,
        "category": category,
        "apple_app": top_apple,
        "play_app": play_result,
        "app_store_url": top_apple.get("app_store_url") if top_apple else None,
        "play_url": play_result.get("play_url") if play_result else None,
        "website_url": website_url,
        "developer": (top_apple.get("developer") if top_apple else play_result.get("developer")) or "",
        "bundle_id": (top_apple.get("bundle_id") if top_apple else play_result.get("package_id")) or "",
        "rating": top_apple.get("rating") if top_apple else play_result.get("rating"),
    }
