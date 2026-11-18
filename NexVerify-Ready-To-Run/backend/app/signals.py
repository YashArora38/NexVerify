"""Signal-based classification, impersonation detection, and trust evaluation for NexVerify.

General, signal-based rules for ANY input (domain, URL, app name, social link, company name).
No hard-coded domains or test inputs.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Standard categories required by specification
CATEGORIES = [
    "online betting/gambling",
    "loan app",
    "investment/stock tips",
    "job offer",
    "shopping/e-commerce",
    "government scheme",
    "bank/UPI/payment",
    "crypto",
    "KYC/APK download",
    "lottery/reward/prize",
    "charity/donation",
    "company/service",
    "other",
]

# High-profile entity patterns for impersonation detection
# Matches name/domain roots against major categories in India
ENTITY_PATTERNS = {
    "bank": re.compile(
        r"\b(sbi|state\s*bank|hdfc|icici|axis|pnb|punjab\s*national|bob|bank\s*of\s*baroda|canara|kotak|indusind|yes\s*bank|rbi|reserve\s*bank|nabard)\b",
        re.I,
    ),
    "gov": re.compile(
        r"\b(pmkisan|pm\s*kisan|pmay|ayushman|epfo|epf|uidai|aadhaar|incometax|gst|parivahan|digilocker|passport|irctc|cybercrime|modi\s*yojana|sarkari)\b",
        re.I,
    ),
    "payment": re.compile(
        r"\b(upi|npci|bhim|paytm|phonepe|gpay|google\s*pay)\b",
        re.I,
    ),
    "ecommerce": re.compile(
        r"\b(amazon|flipkart|meesho|myntra|tatacliq|ajio|jio\s*mart|jiomart)\b",
        re.I,
    ),
    "telecom": re.compile(
        r"\b(jio|airtel|vi|vodafone|bsnl)\b",
        re.I,
    ),
    "lottery_media": re.compile(
        r"\b(kbc|kaun\s*banega\s*crorepati|ipl|dream11)\b",
        re.I,
    ),
}

# Authentic / canonical base domains for key organizations
# If a domain contains the brand keyword BUT is NOT in the authentic root, it is impersonation
CANONICAL_DOMAINS = {
    "sbi": {"sbi.bank.in", "sbi.co.in", "statebankofindia.com", "onlinesbi.sbi", "onlinesbi.com", "sbicard.com"},
    "hdfc": {"hdfc.bank.in", "hdfcbank.bank.in", "hdfcbank.com", "hdfc.com", "hdfcsec.com", "hdfclife.com", "hdfcergo.com"},
    "icici": {"icici.bank.in", "icicibank.bank.in", "icicibank.com", "icicidirect.com", "iciciprulife.com", "icicilombard.com"},
    "axis": {"axis.bank.in", "axisbank.bank.in", "axisbank.com"},
    "pnb": {"pnb.bank.in", "pnbindia.in"},
    "bob": {"bob.bank.in", "bankofbaroda.bank.in", "bankofbaroda.in", "bankofbaroda.com"},
    "kotak": {"kotak.bank.in", "kotakbank.bank.in", "kotak.com", "kotakcherry.com", "kotaksecurities.com"},
    "yesbank": {"yes.bank.in", "yesbank.bank.in", "yesbank.in"},
    "idfc": {"idfcfirst.bank.in", "idfcfirstbank.bank.in", "idfcfirstbank.com"},
    "canara": {"canara.bank.in", "canarabank.bank.in", "canarabank.com"},
    "unionbank": {"unionbank.bank.in", "unionbankofindia.bank.in", "unionbankofindia.co.in"},
    "rbi": {"rbi.org.in", "rbi.bank.in"},
    "sebi": {"sebi.gov.in"},
    "pmkisan": {"pmkisan.gov.in"},
    "uidai": {"uidai.gov.in"},
    "aadhaar": {"uidai.gov.in"},
    "irctc": {"irctc.co.in", "irctctourism.com"},
    "cybercrime": {"cybercrime.gov.in"},
    "amazon": {"amazon.in", "amazon.com", "amazon.jobs", "aws.amazon.com"},
    "flipkart": {"flipkart.com", "flipkartcareers.com"},
    "meesho": {"meesho.com"},
    "paytm": {"paytm.com", "paytmbank.com"},
    "phonepe": {"phonepe.com"},
    "razorpay": {"razorpay.com", "razorpay.me"},
    "zerodha": {"zerodha.com"},
    "groww": {"groww.in"},
    "bajaj": {"bajaj.fin.in", "bajajfinserv.in", "bajajfinance.in"},
    "jio": {"jio.com", "reliancedigital.in"},
    "airtel": {"airtel.in", "airtel.com"},
    "tata": {"tata.com", "tatamotors.com", "tcs.com"},
    "kbc": {"sonyliv.com"},
}

# Scam modifiers often combined with brand names or domains
SCAM_MODIFIERS = re.compile(
    r"\b(rewards?|claim|offers?|yojana|kyc|verify|verification|login|signin|apk|bonus|draw|winner|lucky|cash|free|gift|support|update|refund|loan|subsidy|portal|service|work\s*from\s*home|wfh|job|jobs|hiring|part\s*time|earn\s*money|task|registration|fee|pay)\b",
    re.I,
)

# Common scam behavior indicators
SCAM_LANGUAGE = {
    "upfront_fee": re.compile(
        r"\b(?:pay|send|deposit)\s*(?:rs\.?|\b)?\s*\d+\s*(?:as\s*)?(?:registration|security|training|kit|onboarding|joining|entry|verification)\s*(?:fee|deposit|charge|amount)"
        r"|\b(?:registration|security|training|kit|onboarding|joining|entry)\s*(?:fee|deposit|charges?)\s*(?:of\s*)?(?:rs\.?|\b)?\s*\d+"
        r"|\b(?:pay\s+\d{3,5}\s*(?:registration|security|training)\s*(?:fee|deposit)?\b)"
        r"|\brefundable\s+(?:security\s+)?(?:deposit|fee)\s+(?:for\s+work|for\s+job|before\s+loan|to\s+start)",
        re.I,
    ),
    "guaranteed_returns": re.compile(
        r"(?<!not\s)(?<!no\s)(?<!never\s)\b(?:guaranteed|assured|sure[\s\-]?shot)\s+(?:\d{1,3}\s*%\s*)?(?:returns?|profits?|income)\b"
        r"|\b\d{1,3}\s*%\s*(?:guaranteed|assured)\s*(?:returns?|profits?)\b"
        r"|\b(?:double|triple)\s+your\s+(?:money|capital|investment)\b",
        re.I,
    ),
    "vip_group": re.compile(
        r"\b(vip\s*(?:stock\s*|trading\s*|share\s*)?(?:group|channel|tips|calls?)|premium\s*tips|stock\s*tips|trading\s*calls?|crypto\s*signals?|sure\s*shot\s*calls?|jackpot\s*call|100%\s*accurate)\b",
        re.I,
    ),
    "lottery_prize": re.compile(
        r"\b(lucky\s*draw|lottery|winner|won\s*(?:rs\.?|\b)|cash\s*prize|reward\s*points?\s*(?:claim|redeem)|rewards?\s*claim|kbc\s*(?:lottery|lucky))\b",
        re.I,
    ),
    "apk_outside_store": re.compile(
        r"(\.apk\b|download\s*apk|apk\s*download|install\s*apk|direct\s*apk|click\s*to\s*download\s*app)",
        re.I,
    ),
}


def detect_input_type(query: str) -> str:
    """Classify the input format into one of 5 types."""
    q = query.strip()
    if re.match(r"^@[A-Za-z0-9_]{3,}$", q) or re.search(r"\b(t\.me|telegram\.me|chat\.whatsapp\.com|wa\.me|whatsapp|telegram)\b", q, re.I):
        return "telegram/whatsapp link"
    if re.search(r"(play\.google\.com/store/apps/details|apps\.apple\.com)", q, re.I):
        return "app name"
    if re.match(r"^https?://", q, re.I):
        parsed = urlparse(q)
        if parsed.path and parsed.path not in ("/", ""):
            return "url"
        return "domain"
    if re.match(r"^[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+(/.*)?$", q) and " " not in q:
        return "domain"
    if re.search(r"\b(app|apk|instant\s*loan|fast\s*cash|quick\s*loan)\b", q, re.I):
        return "app name"
    if re.search(r"\b(pvt\.?\s*ltd\.?|private\s*limited|limited|llp|technologies|solutions|enterprises|industries)\b", q, re.I):
        return "plain company name"
    return "app name" if ("." not in q and "/" not in q and len(q) <= 30) else ("plain company name" if " " in q else "domain")


def classify_category(text: str, host: str = "") -> tuple[str, str | None]:
    """Classify the input into a standard category. Returns (category, reason).
    Uses whole words only; generic words like "share", "credit", "won" or "claim"
    alone are not enough."""
    t = f"{text} {host}".lower()
    hc = re.sub(r"[^a-z0-9]", "", host.lower())

    from . import linkintel
    if linkintel.betting_hit(f"{text} {host}"):
        return "online betting/gambling", "Online betting, gambling or casino platform"
    if re.search(r"\b(betting|casino|satta|matka|rummy|teen\s*patti|poker|sportsbook)\b", t):
        return "online betting/gambling", "Online betting, gambling or casino platform"
    if re.search(r"\b(lucky\s*draw|lottery|jackpot|kbc|kaun\s*banega|reward\s*points?|cash\s*prize|prize\s*money|you\s+(?:have\s+)?won|claim\s+(?:your\s+)?(?:prize|reward|gift))\b", t) \
            or re.search(r"(lottery|luckydraw|kbc|rewardpoint|cashprize)", hc):
        return "lottery/reward/prize", "Lottery, prize or reward redemption keywords"
    if re.search(r"\b(loans?|lending|lender|borrow|emi|nbfc|instant\s*cash|fast\s*cash|personal\s*loan|payday)\b", t) or re.search(r"(loan|lending|instantcash|fastcash)", hc):
        return "loan app", "Lending / loan keywords"
    if re.search(r"\b(stocks?|trading|trader|signals?|nifty|bank\s*nifty|sebi|intraday|forex|demat|f&o|options\s+trading|stock\s*tips|mutual\s*funds?|portfolio\s*management|research\s*analyst|investment\s*adviser)\b", t) \
            or re.search(r"(stock|trading|signals|nifty|forex|demat)", hc):
        return "investment/stock tips", "Stock trading / investment advisory keywords"
    if re.search(r"\b(intern\w*|jobs?|hiring|careers?|placement|recruit\w*|vacancy|vacancies|work\s*from\s*home|wfh|part\s*time)\b", t) or re.search(r"(career|jobs|hiring|recruit|internship)", hc):
        return "job offer", "Job or internship recruitment keywords"
    if re.search(r"\b(crypto|bitcoin|usdt|binance|ethereum|airdrop|web3|nft)\b", t):
        return "crypto", "Cryptocurrency keywords"
    if re.search(r"\b(bank|banking|upi|npci|bhim|atm|neft|rtgs|imps|netbanking|debit\s*card|credit\s*card|wallet)\b", t):
        return "bank/UPI/payment", "Banking or payment keywords"
    if re.search(r"\b(pmkisan|pm\s*kisan|yojana|sarkari|ration|aadhaa?r|uidai|ayushman|subsidy|pension|government|govt)\b", t) or ".gov.in" in host or ".nic.in" in host:
        return "government scheme", "Government portal or welfare scheme keywords"
    if re.search(r"\b(apk|download\s*apk|kyc\s*update|kyc\s*verify|re-?kyc)\b", t):
        return "KYC/APK download", "APK installation or KYC update keywords"
    if re.search(r"\b(shop|shopping|ecommerce|e-commerce|cart|store|fashion|deals|buy\s*online|sale)\b", t):
        return "shopping/e-commerce", "E-commerce / shopping keywords"
    if re.search(r"\b(charity|donation|ngo|relief\s*fund|donate)\b", t):
        return "charity/donation", "Charity or donation keywords"
    if re.search(r"\b(news|media|journalism|bulletin|headline|press|inshorts?|dainik|patrika|tv\s*news)\b", t):
        return "company/service", "News or media publication platform"
    if re.search(r"\b(pvt|ltd|limited|llp|services|technologies|solutions|holdings|enterprises|consultants?|ventures)\b", t):
        return "company/service", "Company or business service keywords"
    return "Could not determine category", None


def extract_domain(query: str) -> str:
    """Get clean hostname from query if present."""
    q = query.strip()
    if "://" not in q and ("." in q or "/" in q) and " " not in q:
        q = "http://" + q
    try:
        parsed = urlparse(q)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        return host
    except Exception:
        return ""


def detect_brand_impersonation(query: str, host: str = "") -> dict | None:
    """Brand / government impersonation, from the deterministic link engine.
    Returns None for official addresses and when no strong sign is found."""
    from . import linkintel

    target = host or query
    rep = linkintel.analyze(target)
    if rep.identity and not rep.ugc:
        return None
    strong = [x for x in rep.signals if x.group == "brand" and x.points >= linkintel.HIGH]
    if not strong:
        return None
    sig = strong[0]
    brand_id = (sig.detail or {}).get("brand")
    b = next((x for x in linkintel.data()["brands"] if x["id"] == brand_id), None)
    return {
        "brand": b["name"] if b else ("Government of India" if sig.id in ("FAKE_GOV", "GOV_WORDS") else "a known brand"),
        "official_domain": (sig.detail or {}).get("real") or ("gov.in" if sig.id == "FAKE_GOV" else ""),
        "target_host": rep.parsed.get("host") or query,
        "reason": sig.en,
        "rule": sig.id,
    }


def is_trusted_official_domain(host: str) -> tuple[bool, str]:
    """True when the address itself proves who runs the site (restricted zone,
    brand-owned domain or known official site)."""
    from . import linkintel

    p = linkintel.parse(host or "")
    if not p.is_link:
        return False, ""
    ident = linkintel.identity_of(p)
    if ident and not linkintel.ugc_of(p, ident):
        if ident.get("source") == "zone" and not ident.get("verified") and not linkintel._simple_path(p):
            return False, ""
        return True, ident["en"]
    return False, ""
