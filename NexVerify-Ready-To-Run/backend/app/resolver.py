"""Step 2: turn what the user typed into a structured subject with signals.

General, signal-based classification across all categories and input types:
- Categorization (loan app, investment/stock tips, job offer, shopping/e-commerce,
  government scheme, bank/UPI/payment, crypto, KYC/APK download, lottery/reward/prize,
  charity/donation, company/service, other, or unclear).
- Input type (domain, url, app name, telegram/whatsapp link, plain company name).
- Brand impersonation detection and domain authenticity check.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .gemini import get_client, host_of
from .signals import (
    CATEGORIES,
    classify_category,
    detect_brand_impersonation,
    detect_input_type,
    extract_domain,
    is_trusted_official_domain,
)

SOCIAL = {
    "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "linkedin.com",
    "wikipedia.org", "reddit.com", "quora.com", "medium.com", "apkpure.com", "apkcombo.com"
}


def slugify(s: str) -> str:
    s = re.sub(r"https?://", "", s.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "check"


def normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def _clean_url(u: str | None, must_host: str | None = None) -> str | None:
    if not u or not isinstance(u, str) or not u.startswith(("http://", "https://")):
        return None
    h = host_of(u)
    if not h:
        return None
    if must_host and not (h == must_host or h.endswith("." + must_host)):
        return None
    if must_host is None and any(h == sx or h.endswith("." + sx) for sx in SOCIAL | {"play.google.com", "t.me", "telegram.me"}):
        return None
    return u


def parse_direct(query: str) -> dict:
    """Handle URLs / @handles / domains typed straight in."""
    q = query.strip()
    sub: dict = {}
    if re.match(r"^@[A-Za-z0-9_]{3,}$", q):
        sub["telegram_url"] = f"https://t.me/{q[1:]}"
        sub["display_name"] = q[1:]
    elif re.match(r"^(https?://)?(t\.me|telegram\.me)/", q, re.I):
        url = q if q.startswith("http") else "https://" + q
        sub["telegram_url"] = url
        sub["display_name"] = url.rstrip("/").split("/")[-1]
    elif re.match(r"^(https?://)?(chat\.whatsapp\.com|wa\.me)/", q, re.I):
        url = q if q.startswith("http") else "https://" + q
        sub["telegram_url"] = url
        sub["display_name"] = "WhatsApp group / link"
    elif re.match(r"^(https?://)?play\.google\.com/store/apps/details", q, re.I):
        url = q if q.startswith("http") else "https://" + q
        sub["play_url"] = url
        m = re.search(r"id=([A-Za-z0-9_.]+)", url)
        sub["display_name"] = m.group(1).split(".")[-1] if m else "app"
    elif re.match(r"^(https?://)?apps\.apple\.com/[a-z]{2}/app/", q, re.I):
        url = q if q.startswith("http") else "https://" + q
        sub["app_store_url"] = url
        m = re.search(r"/app/([^/]+)/id(\d+)", url)
        sub["display_name"] = m.group(1).replace("-", " ") if m else "app"
    elif re.match(r"^(https?://)?[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+(/.*)?$", q) and " " not in q:
        url = q if q.startswith("http") else "https://" + q
        sub["website_url"] = url
        sub["display_name"] = (urlparse(url).hostname or q).removeprefix("www.")
    return sub


RESOLVE_PROMPT = """You help Indian users check whether an app, website, job, investment, or link is a scam.
Work out which app, company or channel they mean (India). Search explicitly for scam reports, cybercrime mentions, and brand impersonation.

The user typed: "{query}"

Analyze this entity thoroughly for India:
1. Category: choose exactly one from:
   - "loan app" (instant loan, credit, NBFC lending)
   - "investment/stock tips" (stock tips, trading, crypto advisory, forex, VIP signals)
   - "job offer" (internship, recruitment, work from home)
   - "shopping/e-commerce" (online store, shopping deals)
   - "government scheme" (welfare scheme, subsidy, government portal)
   - "bank/UPI/payment" (banking, UPI payments, wallet)
   - "crypto" (cryptocurrency token, exchange)
   - "KYC/APK download" (APK download link, KYC update)
   - "lottery/reward/prize" (lottery, lucky draw, reward points redemption, cash prize)
   - "charity/donation" (fundraiser, NGO donation)
   - "company/service" (general business, IT services, consulting)
   - "other" (if it fits none of the above)
   If you cannot determine the category, return "Could not determine category".

2. Input type: "domain", "url", "app name", "telegram/whatsapp link", or "plain company name".
3. Official details:
   - Official website URL, if any
   - Official Google Play Store URL, if an app
   - Official Apple App Store URL, if an iOS app
   - Legal registered company name (e.g. "... Private Limited"), if published
107. Signals:
   - Is it impersonating a bank, government body (e.g. SBI, RBI, PM-Kisan, EPFO) or major brand?
     NOTE: Domains on .bank.in (e.g. sbi.bank.in, hdfc.bank.in) are official RBI-mandated bank domains; do NOT mark them as impersonating.
   - Any public scam warnings, police advisories, consumer complaints?
   - Any required regulatory license (RBI for loans, SEBI for stock advice)?

Do not guess or invent URLs or registrations. If not found or unverified, use null.

Return ONLY a JSON object:
{{
  "display_name": string,
  "category": string,
  "input_type": string,
  "play_url": string|null,
  "app_store_url": string|null,
  "website_url": string|null,
  "telegram_url": string|null,
  "legal_name": string|null,
  "impersonating": string|null,
  "scam_warning": string|null,
  "notes": string
}}"""


async def resolve(query: str, emit=None, use_ai: bool = True) -> tuple[dict, dict | None]:
    """Returns (subject, gemini_evidence) — evidence is saved by the caller.
    use_ai=False skips the Gemini lookup (the link already settles the answer)."""
    direct = parse_direct(query)
    host = extract_domain(direct.get("website_url") or query)
    input_type = detect_input_type(query)

    cat, cat_reason = classify_category(query, host)
    impersonation = detect_brand_impersonation(query, host)
    is_trusted, trust_reason = is_trusted_official_domain(host)

    subject = {
        "query": query,
        "slug": slugify(query),
        "display_name": direct.get("display_name") or query.strip(),
        "category": cat,
        "category_reason": cat_reason,
        "input_type": input_type,
        "website_url": direct.get("website_url"),
        "play_url": direct.get("play_url"),
        "app_store_url": direct.get("app_store_url"),
        "telegram_url": direct.get("telegram_url"),
        "legal_name": None,
        "impersonation": impersonation,
        "is_trusted_domain": is_trusted,
        "trust_reason": trust_reason,
        "is_app": False,
    }

    from . import appstore
    app_meta = None
    try:
        app_meta = await appstore.resolve_app_details(query)
    except Exception:
        pass
    if app_meta:
        subject["is_app"] = True
        if not direct.get("display_name") or subject["display_name"] == query.strip():
            subject["display_name"] = app_meta["display_name"]
        if not subject.get("play_url") and app_meta.get("play_url"):
            subject["play_url"] = app_meta["play_url"]
        if not subject.get("app_store_url") and app_meta.get("app_store_url"):
            subject["app_store_url"] = app_meta["app_store_url"]
        if not subject.get("website_url") and app_meta.get("website_url"):
            subject["website_url"] = app_meta["website_url"]
        if app_meta.get("developer") and not subject.get("legal_name"):
            subject["legal_name"] = app_meta["developer"]
        if subject["category"] in ("Could not determine category", "other") and app_meta.get("category"):
            subject["category"] = app_meta["category"]
        subject["input_type"] = "app name"
        subject["app_meta"] = app_meta

    from . import linkintel
    ident = linkintel.identity_of(linkintel.parse(direct.get("website_url") or query))
    kind_cat = {"bank": "bank/UPI/payment", "payment": "bank/UPI/payment", "broker": "investment/stock tips", "exchange": "investment/stock tips",
                "nbfc": "loan app", "government": "government scheme", "regulator": "government scheme", "ecommerce": "shopping/e-commerce",
                "jobs": "job offer", "job": "job offer", "crypto": "crypto", "insurance": "company/service", "education": "company/service"}
    if ident and subject["category"] in ("Could not determine category", "company/service"):
        subject["category"] = kind_cat.get(ident.get("kind"), subject["category"])
        if ident.get("name") and not direct.get("display_name"):
            subject["display_name"] = ident["name"]

    evidence = None
    client = get_client()
    if client.enabled and use_ai:
        if emit:
            await emit("status", {"message": "Analyzing category, brand impersonation and official records"})
        prompt = RESOLVE_PROMPT.format(query=query.replace('"', "'"))
        try:
            res = await client.generate(prompt, search=True, timeout=40)
            d = res.data or {}
            evidence = {
                "prompt": prompt,
                "google_search_queries": res.queries,
                "sources_returned_by_google": res.sources,
                "answer": res.text,
            }
            if not direct.get("display_name") and d.get("display_name"):
                subject["display_name"] = str(d["display_name"]).strip()[:80]
            subject["play_url"] = subject["play_url"] or _clean_url(d.get("play_url"), "play.google.com")
            if d.get("app_store_url"):
                subject["app_store_url"] = subject.get("app_store_url") or _clean_url(d.get("app_store_url"), "apps.apple.com")
            if d.get("is_app"):
                subject["is_app"] = True
            subject["website_url"] = subject["website_url"] or _clean_url(d.get("website_url"))
            tg = d.get("telegram_url")
            if not subject["telegram_url"] and isinstance(tg, str) and re.search(r"t\.me/|telegram\.me/|wa\.me/|chat\.whatsapp\.com/", tg, re.I):
                subject["telegram_url"] = tg
            if d.get("legal_name"):
                subject["legal_name"] = str(d["legal_name"]).strip()[:120]

            # Validate model category if our pattern did not find a strong one
            model_cat = d.get("category")
            if model_cat:
                if model_cat in ("lending", "loan app"):
                    subject["category"] = "loan app"
                elif model_cat in ("investment", "investment/stock tips"):
                    subject["category"] = "investment/stock tips"
                elif model_cat in ("job", "job offer"):
                    subject["category"] = "job offer"
                elif model_cat in CATEGORIES and subject["category"] in ("Could not determine category", "other", "company/service"):
                    subject["category"] = model_cat

            if d.get("input_type") and subject["input_type"] == "plain company name":
                subject["input_type"] = d["input_type"]

            # What the model thinks is kept as a note only. It never changes the score:
            # impersonation is decided by the fixed link rules.
            if d.get("impersonating") and not subject.get("is_trusted_domain"):
                subject["ai_note_impersonating"] = str(d["impersonating"])[:80]
            if d.get("scam_warning") and not subject.get("is_trusted_domain"):
                subject["scam_warning"] = str(d["scam_warning"])[:300]
        except Exception as exc:
            evidence = {"prompt": prompt, "error": str(exc)}

    # Ensure strong pattern classification overrides weak general assignments
    cat_override, _ = classify_category(f"{query} {subject['display_name']}", host)
    if cat_override not in ("Could not determine category", "company/service"):
        subject["category"] = cat_override
    elif subject.get("telegram_url") and subject["category"] in ("Could not determine category", "company/service"):
        subject["category"] = "investment/stock tips"
    elif (subject.get("play_url") or subject.get("app_store_url")) and subject["category"] in ("Could not determine category", "other"):
        subject["category"] = "company/service"

    # If the refined display name differs, re-verify with appstore for official URLs
    if subject.get("display_name") and subject["display_name"].lower() != query.strip().lower():
        try:
            refined_meta = await appstore.resolve_app_details(subject["display_name"])
            if refined_meta:
                subject["is_app"] = True
                if refined_meta.get("play_url"):
                    subject["play_url"] = refined_meta["play_url"]
                if refined_meta.get("app_store_url"):
                    subject["app_store_url"] = refined_meta["app_store_url"]
                if refined_meta.get("website_url"):
                    subject["website_url"] = refined_meta["website_url"]
                if refined_meta.get("category") and subject["category"] in ("Could not determine category", "other"):
                    subject["category"] = refined_meta["category"]
                subject["app_meta"] = refined_meta
        except Exception:
            pass

    # The website found by search may differ from what was typed; re-check it.
    site_host = extract_domain(subject.get("website_url") or "")
    if site_host and site_host != host:
        t, why = is_trusted_official_domain(site_host)
        subject["website_is_official"] = t
    if subject.get("is_trusted_domain"):
        subject["impersonation"] = None
    return subject, evidence
