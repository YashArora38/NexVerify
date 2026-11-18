"""Pull claims out of page text with fixed patterns (no AI).

These are the things a scam page says to look trustworthy: "10 years trusted",
a CIN number, a SEBI registration number, "RBI approved", "guaranteed returns",
"refundable registration fee", and so on.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import unquote_plus

CIN_RE = re.compile(r"\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b")
SEBI_NO_RE = re.compile(r"\b(IN[AHZ]\d{9})\b")
SEBI_CLAIM_RE = re.compile(
    r"(sebi[\s\-]*(registered|regd\.?|approved|certified|licensed|registration)|registered\s+with\s+sebi)", re.I)
RBI_CLAIM_RE = re.compile(
    r"((rbi|reserve\s+bank(\s+of\s+india)?)[\s\-]*(registered|approved|regulated|licensed|authori[sz]ed)"
    r"|registered\s+with\s+(the\s+)?(rbi|reserve\s+bank))", re.I)
NBFC_PARTNER_RE = re.compile(
    r"(?:nbfc|lending|lender)\s+partner\s*[:\-]?\s*([A-Z][A-Za-z0-9&.,' ]{2,70}?"
    r"(?:Private Limited|Pvt\.? Ltd\.?|Limited|Ltd\.?))", re.I)
YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years|yrs)\b(?:\s+of)?", re.I)
SINCE_RE = re.compile(r"\b(?:since|established\s+in|founded\s+in|estd\.?|est\.)\s*((?:19|20)\d{2})\b", re.I)
LEGAL_NAME_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9&.']*\s){1,6}(?:Private Limited|Pvt\.? Ltd\.?|Limited|LLP))\b")
RETURNS_RE = re.compile(
    r"(?<!not\s)(?<!no\s)(?<!never\s)\b(?:guaranteed|assured|sure[\s\-]?shot)\s+(?:\d{1,3}\s*%\s*)?(?:returns?|profits?|income)\b"
    r"|\b\d{1,3}\s*%\s*(?:guaranteed|assured)\s*(?:returns?|profits?)\b"
    r"|\b(?:double|triple)\s+your\s+(?:money|capital|investment)\b",
    re.I)
FEE_RE = re.compile(
    r"\b(?:pay|send|deposit)\s*(?:rs\.?|\b)?\s*\d+\s*(?:as\s*)?(?:registration|security|training|kit|onboarding|joining|entry|verification)\s*(?:fee|deposit|charge|amount)"
    r"|\b(?:registration|security|training|kit|onboarding|joining|entry)\s*(?:fee|deposit|charges?)\s*(?:of\s*)?(?:rs\.?|\b)?\s*\d+"
    r"|\b(?:pay\s+\d{3,5}\s*(?:registration|security|training)\s*(?:fee|deposit)?\b)"
    r"|\brefundable\s+(?:security\s+)?(?:deposit|fee)\s+(?:for\s+work|for\s+job|before\s+loan|to\s+start)",
    re.I)
LOTTERY_RE = re.compile(r"(lucky\s*draw\s*(?:winner|prize|contest)|you\s+(?:have\s+)?won|claim\s+your\s+(?:prize|reward|gift)|cash\s*prize\s*of|reward\s*points?\s*(?:claim|redeem|expir)|kbc\s*(?:lottery|lucky|winner|draw)|lottery\s*(?:winner|prize|ticket\s*number|department))", re.I)
VIP_GROUP_RE = re.compile(r"\b(vip\s*group|vip\s*channel|vip\s*(?:stock\s*)?tips|sure\s*shot\s*tips?|premium\s*tips)\b", re.I)
APK_RE = re.compile(r"(\.apk\b|download\s*apk|apk\s*download|install\s*apk)", re.I)
SENSITIVE_DATA = {
    "contacts": re.compile(r"\bcontacts?\b", re.I),
    "photos": re.compile(r"\bphotos?(\s+and\s+videos)?\b|\bgallery\b|\bfiles\s+and\s+docs\b", re.I),
    "sms": re.compile(r"\bsms\b|\btext\s+messages\b", re.I),
    "call_logs": re.compile(r"\bcall\s+(history|logs?)\b", re.I),
}
TRUST_WORDS = re.compile(r"\b(trust\w*|experience\w*|experts?|serving|served|legacy|old|in\s+business|industry|since)\b", re.I)


@dataclass
class Claims:
    claimed_years: int | None = None
    claimed_years_text: str | None = None
    cins: list[str] = field(default_factory=list)
    sebi_numbers: list[str] = field(default_factory=list)
    sebi_claim: bool = False
    sebi_claim_text: str | None = None
    rbi_claim: bool = False
    rbi_claim_text: str | None = None
    nbfc_partner: str | None = None
    legal_names: list[str] = field(default_factory=list)
    guaranteed_returns_text: str | None = None
    upfront_fee_text: str | None = None
    lottery_claim_text: str | None = None
    vip_group_text: str | None = None
    apk_download_text: str | None = None
    developer: str | None = None
    sensitive_data: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def cin(self) -> str | None:
        return self.cins[0] if self.cins else None

    @property
    def sebi_no(self) -> str | None:
        return self.sebi_numbers[0] if self.sebi_numbers else None


def _snippet(text: str, m: re.Match, limit: int = 110) -> str:
    """The sentence around a match, cut at word boundaries."""
    stops = ".!?\n|"
    a = max((text.rfind(ch, 0, m.start()) for ch in stops), default=-1) + 1
    ends = [i for i in (text.find(ch, m.end()) for ch in stops) if i != -1]
    b = min(ends) + 1 if ends else len(text)
    # keep the decimal point of "Rs. 1,999" / "No." style abbreviations inside the sentence
    while b < len(text) and text[b - 1] == "." and re.search(r"\b(Rs|No|Regd|Pvt|Ltd|Reg)\.$", text[a:b]):
        nxt = [i for i in (text.find(ch, b) for ch in stops) if i != -1]
        b = min(nxt) + 1 if nxt else len(text)
    snip = re.sub(r"\s+", " ", text[a:b]).strip()
    if len(snip) > limit:
        core = re.sub(r"\s+", " ", m.group(0))
        i = snip.find(core)
        lo = max(0, i - (limit - len(core)) // 2)
        lo = snip.rfind(" ", 0, lo) + 1 if lo > 0 else 0
        hi = snip.find(" ", lo + limit)
        snip = ("\u2026" if lo > 0 else "") + snip[lo: hi if hi != -1 else len(snip)].strip() + ("\u2026" if hi != -1 else "")
    return snip


def _uniq(items):
    seen, out = set(), []
    for x in items:
        k = x.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out


def extract_claims(text: str, today: date | None = None) -> Claims:
    today = today or date.today()
    c = Claims()
    if not text:
        return c

    c.cins = _uniq(CIN_RE.findall(text))
    c.sebi_numbers = _uniq(SEBI_NO_RE.findall(text))

    m = SEBI_CLAIM_RE.search(text)
    if m or c.sebi_numbers:
        c.sebi_claim = True
        c.sebi_claim_text = _snippet(text, m) if m else f"SEBI no. {c.sebi_numbers[0]}"
    m = RBI_CLAIM_RE.search(text)
    if m:
        c.rbi_claim = True
        c.rbi_claim_text = _snippet(text, m)
    m = NBFC_PARTNER_RE.search(text)
    if m:
        c.nbfc_partner = m.group(1).strip(" ,.")

    # "10 years trusted", "15+ years of experience" (only near trust words)
    best = None
    for m in YEARS_RE.finditer(text):
        n = int(m.group(1))
        window = text[max(0, m.start() - 40): m.end() + 40]
        if 1 <= n <= 60 and TRUST_WORDS.search(window):
            if best is None or n > best[0]:
                best = (n, _snippet(text, m))
    for m in SINCE_RE.finditer(text):
        n = today.year - int(m.group(1))
        if 1 <= n <= 100 and (best is None or n > best[0]):
            best = (n, _snippet(text, m))
    if best:
        c.claimed_years, c.claimed_years_text = best

    c.legal_names = _uniq(n.strip() for n in LEGAL_NAME_RE.findall(text) if not n.startswith(("Lending ", "The ")))[:5]

    m = RETURNS_RE.search(text)
    if m:
        c.guaranteed_returns_text = _snippet(text, m)
    m = FEE_RE.search(text)
    if m:
        c.upfront_fee_text = _snippet(text, m)
    m = LOTTERY_RE.search(text)
    if m:
        c.lottery_claim_text = _snippet(text, m)
    m = VIP_GROUP_RE.search(text)
    if m:
        c.vip_group_text = _snippet(text, m)
    m = APK_RE.search(text)
    if m:
        c.apk_download_text = _snippet(text, m)
    return c


# ---------------------------------------------------------------------------
# Google Play pages
# ---------------------------------------------------------------------------
_DEV_LINK = re.compile(r'href="(?:https://play\.google\.com)?/store/apps/dev(?:eloper)?\?id=([^"&]+)[^"]*"[^>]*>(.*?)</a>', re.S | re.I)
_DEV_MD = re.compile(r"\[([^\]]{2,80})\]\((?:https://play\.google\.com)?/store/apps/dev(?:eloper)?\?id=[^)]+\)", re.I)


def play_developer(html_or_md: str) -> str | None:
    m = _DEV_LINK.search(html_or_md or "")
    if m:
        name = re.sub(r"<[^>]+>", " ", m.group(2))
        name = re.sub(r"\s+", " ", name).strip()
        if not name or name.isdigit():
            name = unquote_plus(m.group(1))
        return name if name and not name.isdigit() else None
    m = _DEV_MD.search(html_or_md or "")
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:Offered by|Developer)\s*[:\n]\s*([^\n]{2,80})", html_or_md or "", re.I)
    return m.group(1).strip() if m else None


def sensitive_data_types(data_safety_text: str) -> list[str]:
    """Which sensitive data types a Play 'Data safety' page says the app collects or shares."""
    text = data_safety_text or ""
    idx = text.lower().find("data safety")
    if idx != -1:
        text = text[idx:]
    found = [k for k, rx in SENSITIVE_DATA.items() if rx.search(text)]
    return found


def play_id(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"[?&]id=([A-Za-z0-9_.]+)", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Name matching (publisher vs company, CIN owner vs claimed name)
# ---------------------------------------------------------------------------
_STOP = {
    "private", "limited", "pvt", "ltd", "llp", "the", "and", "of", "india", "indian",
    "technologies", "technology", "tech", "solutions", "services", "company", "co", "inc",
    "app", "apps", "official", "loan", "loans", "instant", "group", "global", "ventures",
}


def name_tokens(name: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    toks = {w for w in words if w not in _STOP and len(w) > 1}
    # also split joined words like "QuickRupee" -> "quick", "rupee"
    for w in re.findall(r"[A-Z][a-z]+", name or ""):
        if w.lower() not in _STOP and len(w) > 2:
            toks.add(w.lower())
    return toks


def names_match(a: str | None, b: str | None) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta & tb:
        return True
    # joined forms: "Quick Rupee" vs "QuickRupee" (only for longer names)
    ja, jb = "".join(sorted(ta)), "".join(sorted(tb))
    return (len(ja) >= 5 and ja in "".join(tb)) or (len(jb) >= 5 and jb in "".join(ta))
