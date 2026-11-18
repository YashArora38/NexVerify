"""Checker 4: read what the website / Play listing / Telegram channel CLAIMS.

Direct page fetch (no key), then fixed regex patterns pull out the claims.
Gemini URL-context is only a fallback when a page blocks plain requests.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..claims import extract_claims, play_developer, play_id, sensitive_data_types
from ..gemini import host_of
from .base import Ctx, finish, new_output

KEY = "listing"


def _title(subject: dict) -> str:
    if subject.get("play_url") and subject.get("app_store_url"):
        return "Google Play & App Store"
    if subject.get("play_url"):
        return "Google Play listing"
    if subject.get("app_store_url"):
        return "Apple App Store listing"
    if subject.get("telegram_url"):
        return "Telegram channel"
    return "Website claims"


def _telegram_preview(url: str) -> str:
    m = re.search(r"t\.me/(?:s/)?([A-Za-z0-9_]{4,})", url)
    return f"https://t.me/s/{m.group(1)}" if m else url


async def run(ctx: Ctx) -> dict:
    s = ctx.subject
    out = new_output(KEY, _title(s), "Browser ladder (curl_cffi -> nodriver -> playwright) + fixed patterns")
    out["title"] = _title(s)
    texts: list[str] = []
    pages: list[dict] = []
    developer = None
    sensitive: list[str] = []
    ladder_data: dict = {}
    website_page = None
    play_verified = False

    try:
        if s.get("website_url"):
            target_url = s["website_url"]
            await ctx.step(KEY, f"Opening {host_of(target_url)}")
            # Tier 1: Fast server fetch
            page = await ctx.fetch(target_url)
            if page.ok:
                website_page = page
                pages.append({"url": target_url, "status": page.status, "final_url": page.final_url, "rung_used": "fast_fetch", "html": page.html})
                out["evidence_ids"].append(ctx.save_page(KEY, "Website text snapshot", page))
                texts.append(page.text)
                if sid := await ctx.maybe_screenshot(KEY, page.final_url):
                    out["evidence_ids"].append(sid)
            elif ctx.demo is None:
                # Tier 2: Active Browser Ladder (curl_cffi -> nodriver -> playwright)
                from ..browser_ladder import execute_browser_ladder
                await ctx.step(KEY, "Fast fetch blocked/failed; escalating to browser ladder")
                ladder_page = await execute_browser_ladder(target_url)
                pages.append({
                    "url": target_url,
                    "status": ladder_page.status,
                    "final_url": ladder_page.final_url,
                    "rung_used": ladder_page.rung_used,
                    "block_type": ladder_page.block_type,
                    "html": ladder_page.html,
                })
                ladder_data = {
                    "ssl_info": ladder_page.ssl_info,
                    "dns_records": ladder_page.dns_records,
                    "forms": ladder_page.forms,
                    "rung_used": ladder_page.rung_used,
                    "is_blocked": ladder_page.is_blocked,
                    "block_type": ladder_page.block_type,
                    "block_reason": ladder_page.block_reason,
                    "human_assist_needed": ladder_page.human_assist_needed,
                }
                if ladder_page.ok:
                    website_page = ladder_page
                    out["evidence_ids"].append(ctx.save_page(KEY, "Website text snapshot", ladder_page))
                    texts.append(ladder_page.text)
                    if ladder_page.screenshot_path:
                        out["evidence_ids"].append(ladder_page.screenshot_path)
                    elif sid := await ctx.maybe_screenshot(KEY, ladder_page.final_url or target_url):
                        out["evidence_ids"].append(sid)
                else:
                    await ctx.step(KEY, f"Page blocked/unreachable: {ladder_page.block_type or 'Fetch error'}")
            else:
                pages.append({"url": target_url, "status": page.status})

        if s.get("play_url"):
            pid = play_id(s["play_url"])
            await ctx.step(KEY, "Opening the Google Play listing")
            page = await ctx.fetch(f"https://play.google.com/store/apps/details?id={pid}&hl=en_IN&gl=IN")
            pages.append({"url": s["play_url"], "status": page.status})
            if page.ok:
                out["evidence_ids"].append(ctx.save_page(KEY, "Play Store listing snapshot", page))
                developer = play_developer(page.html or page.text)
                play_verified = bool(developer)
                texts.append(page.text)
                if developer:
                    await ctx.step(KEY, f"Publisher on Play: {developer}")
            await ctx.step(KEY, "Reading the Play 'Data safety' section")
            ds = await ctx.fetch(f"https://play.google.com/store/apps/datasafety?id={pid}&hl=en_IN&gl=IN")
            pages.append({"url": f"datasafety?id={pid}", "status": ds.status})
            if ds.ok:
                out["evidence_ids"].append(ctx.save_page(KEY, "Play Data safety snapshot", ds))
                sensitive = sensitive_data_types(ds.text)
                if sensitive:
                    await ctx.step(KEY, "Data safety mentions: " + ", ".join(sensitive).replace("_", " "))

        apple_info = None
        if s.get("app_store_url"):
            await ctx.step(KEY, "Opening Apple App Store listing")
            apple_page = await ctx.fetch(s["app_store_url"])
            pages.append({"url": s["app_store_url"], "status": apple_page.status})
            if apple_page.ok:
                out["evidence_ids"].append(ctx.save_page(KEY, "Apple App Store listing snapshot", apple_page))
                texts.append(apple_page.text)
            app_meta = s.get("app_meta", {})
            apple_meta = app_meta.get("apple_app") or {}
            apple_dev = apple_meta.get("developer")
            apple_rating = apple_meta.get("rating")
            if apple_dev:
                developer = developer or apple_dev
                rating_str = f" ({apple_rating}★)" if apple_rating else ""
                await ctx.step(KEY, f"Publisher on Apple App Store: {apple_dev}{rating_str}")
            apple_info = {
                "url": s["app_store_url"],
                "developer": apple_dev,
                "rating": apple_rating,
                "verified": bool(apple_page.ok and urlparse(apple_page.final_url).hostname == "apps.apple.com" and re.search(r"/id\d+", s["app_store_url"])),
            }

        if s.get("telegram_url"):
            url = _telegram_preview(s["telegram_url"])
            await ctx.step(KEY, f"Reading public posts of {url.split('/')[-1]}")
            page = await ctx.fetch(url)
            pages.append({"url": url, "status": page.status})
            if page.ok:
                out["evidence_ids"].append(ctx.save_page(KEY, "Telegram channel snapshot", page))
                texts.append(page.text)

        claims = extract_claims("\n".join(texts))
        claims.developer = developer
        claims.sensitive_data = sensitive
        ctx.claims = claims.to_dict()

        for label, val in (("Claims", claims.claimed_years_text), ("CIN shown", claims.cin),
                           ("SEBI claim", claims.sebi_claim_text), ("Promise", claims.guaranteed_returns_text),
                           ("Fee", claims.upfront_fee_text)):
            if val:
                await ctx.step(KEY, f"{label}: “{val[:80]}”")

        from ..payment_intel import analyze_page_payments_and_links
        combined_html = "\n".join(p.get("html", "") for p in pages if isinstance(p, dict) and p.get("html"))
        combined_text = "\n".join(texts)
        current_target = s.get("website_url") or s.get("query") or ""
        payment_intel = analyze_page_payments_and_links(combined_html, combined_text, current_target)

        if website_page is not None:
            from ..investigation import investigate
            await ctx.step(KEY, "Inspecting public payment, download and identity surfaces (up to 4 pages)")
            payment_intel, surface_ids = await investigate(ctx, website_page)
            out["evidence_ids"].extend(surface_ids)

        if payment_intel.get("upi_ids"):
            upis = ", ".join(payment_intel["upi_ids"][:3])
            await ctx.step(KEY, f"Detected UPI IDs: {upis}")
        if payment_intel.get("detected_gateways"):
            gws = ", ".join(payment_intel["detected_gateways"])
            await ctx.step(KEY, f"Gateway reference (merchant not verified): {gws}")
        elif payment_intel.get("asks_direct_payment"):
            await ctx.step(KEY, "Warning: Asks for direct money/UPI transfer without verified gateway")
        if payment_intel.get("shortened_links"):
            await ctx.step(KEY, f"Found {len(payment_intel['shortened_links'])} shortened / hidden redirect link(s)")

        data = {
            "website_url": s.get("website_url"),
            "play_url": s.get("play_url"),
            "app_store_url": s.get("app_store_url"),
            "apple_info": apple_info,
            "play_verified": play_verified,
            "apple_verified": bool(apple_info and apple_info["verified"]),
            "developer": developer,
            "sensitive_data": sensitive,
            "claims": ctx.claims,
            "payment_intel": payment_intel,
            "pages": [{k: v for k, v in p.items() if k != "html"} for p in pages],
            **ladder_data,
        }
        if not texts:
            block_msg = ladder_data.get("block_type") or "unreachable"
            return finish(out, "unverified", data=data, note=f"Could not open page ({block_msg}); not scored")
        if play_verified or (apple_info and apple_info["verified"]):
            await ctx.step(KEY, "Store listing retrieved; app identity and safety require additional evidence")
        return finish(out, "done", data=data)
    finally:
        ctx.claims_ready.set()
