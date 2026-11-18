"""ProofGrid: turn everything the checks found into one score and one plain answer.

Rules (fixed; the same evidence always gives the same answer)
----------------------------------------------------------------
* Every warning sign has fixed points. score = 100 - total points, exactly,
  so the page can show the sum ("100 - 70 - 20 = 10").
* Bands:     70+ points -> HIGH_RISK  ("Don't pay")
             55-69      -> SUSPICIOUS
             31-54      -> CAUTION    ("Be careful")
* With 30 points or less the answer depends on PROOF, never on the absence of
  problems:
      address proves the owner (bank.in / gov.in / a brand's own domain)  -> VERIFIED_OFFICIAL
      known real site, RBI/SEBI listing, company record + old domain ...  -> LOW_RISK ("Looks safe")
      nothing proves who runs it                                          -> UNKNOWN ("Couldn't verify")
* A threat-feed or Google Safe Browsing hit on the exact page is final (score <= 10).
* "Not found" from a search is weak: Google's index can miss a register entry,
  so it only counts against entities with no other proof and a young or
  unknown domain. A search that did not run, or ran without sources, counts
  for nothing.
* AI is never the judge: Gemini only fetches records with Google Search; its
  answers count only with sources. All scoring is the code below.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import linkintel
from .claims import names_match

AGENT_TITLES = {
    "listing": "Website & app listing",
    "rbi": "RBI NBFC & DLA list",
    "sebi": "SEBI portal",
    "company": "Company registry & WHOIS",
    "news": "Forums & news",
}
AGENT_ORDER = ["rbi", "sebi", "company", "listing", "news"]
HIGH, SUSP, CAUT = linkintel.HIGH, linkintel.SUSP, linkintel.CAUT
REGULATED = {"loan app", "lending", "investment/stock tips", "investment", "crypto"}

# id -> (points, short label, description). Link-check rules come first; the
# pipeline rules follow. Shown on the page as "All scoring rules".
RULES: dict[str, tuple[int, str, str]] = {
    "THREAT_FEED": (100, "PHISHING LIST", "The exact page is on an active phishing / malware list (OpenPhish, URLhaus, Phishing.Database)"),
    "SAFE_BROWSING": (100, "GOOGLE WARNING", "Google Safe Browsing lists the page as deceptive or malware"),
    "SCRIPT_LINK": (90, "NOT A WEBSITE", "javascript:, data: or file: link"),
    "BRAND_IMPERSONATION": (75, "FAKE BRAND", "A brand's name plus login, prize or service words on an address the brand does not own"),
    "BRAND_IN_SUBDOMAIN": (70, "FAKE BRAND", "A brand's name or address placed in front of someone else's domain"),
    "BRAND_LOOKALIKE_NAME": (70, "FAKE BRAND", "A brand's name glued into an unrelated address with a risky ending or free hosting"),
    "LOOKALIKE": (70, "LOOKALIKE", "Spelled like a brand's address with swapped, extra or lookalike letters"),
    "FAKE_GOV": (70, "FAKE GOVT", "Looks like a government site but is not on .gov.in / .nic.in"),
    "FAKE_BANK_ZONE": (70, "FAKE BANK", "Copies a .bank.in address inside another domain"),
    "AT_TRICK": (70, "HIDDEN ADDRESS", "An @ in the link hides the real destination"),
    "PUNYCODE": (70, "LOOKALIKE LETTERS", "Letters from other alphabets that imitate a brand (40 when no brand is copied)"),
    "APK_DOWNLOAD": (70, "APK", "Downloads an app file outside the Play Store"),
    "BRAND_IN_PATH": (70, "FAKE BRAND", "A brand's name inside the link on a site it does not own, with a login page (35 without)"),
    "BRAND_OTHER_ENDING": (35, "OTHER ENDING", "A brand's exact name with a different ending (15 for brands that run country sites, 70 on the worst endings)"),
    "BRAND_NAME_UNOFFICIAL": (35, "NOT OFFICIAL", "Uses a brand's name on an address it does not own (15 for global brands)"),
    "BRAND_NAME_INSIDE": (15, "BRAND LETTERS", "Contains a brand's letters inside a longer name"),
    "BETTING": (70, "BETTING", "Online betting / casino / satta; real-money online games are banned in India (Online Gaming Act, 2025)"),
    "UPFRONT_FEE": (70, "FEE FIRST", "Asks for a fee or deposit before a job, loan or prize"),
    "GUARANTEED_RETURNS": (70, "GUARANTEED", "Promises guaranteed or very high returns"),
    "TASK_SCAM": (70, "TASK SCAM", "Pays for likes, reviews or other simple tasks"),
    "LOTTERY_PRIZE": (70, "FAKE PRIZE", "Says you won a prize, lottery or reward points"),
    "KYC_THREAT": (70, "THREAT", "Threatens to block your account, KYC or electricity"),
    "APK_TEXT": (70, "APK", "Asks you to install an app file (APK)"),
    "VIP_TIPS": (45, "TIPS GROUP", "Sells stock tips in a paid group"),
    "INSTANT_LOAN_PROMISE": (35, "LOAN PITCH", "Loan in minutes / no CIBIL check"),
    "MISSPELLED_LOGIN": (45, "MISSPELLED", "Misspells login words on purpose to dodge filters"),
    "IP_ADDRESS": (40, "IP ADDRESS", "A bare IP address instead of a name"),
    "LOGIN_BAIT_WORDS": (35, "LOGIN WORDS", "Address built from login / verify / warning words"),
    "PRIZE_BAIT_WORDS": (35, "PRIZE WORDS", "Address built from prize / money words"),
    "GOV_WORDS": (35, "GOVT WORDS", "Government words (sarkari / yojana) on a private address"),
    "SHORT_LINK": (35, "SHORT LINK", "A short link hides the destination"),
    "REDIRECTS_ELSEWHERE": (35, "REDIRECT", "Starts on one site and forwards you to another"),
    "PHISHING_KIT_PATH": (35, "LOGIN PAGE", "Login / verify script page on an unknown site"),
    "HIDDEN_PAGE": (35, "HIDDEN PAGE", "Page buried in program folders, as on hacked sites"),
    "SITE_INSIDE_LINK": (35, "FAKE ADDRESS", "Another site's name hidden inside the link"),
    "FREE_HOST_BAIT": (35, "FREE SITE", "Free-platform page with login or prize words"),
    "FREE_HOST_TOKEN": (35, "FREE SITE", "Free-platform page reached through a random code"),
    "AUTO_NAMED_PAGE": (35, "TEST PAGE", "Auto-named test page on a free platform"),
    "RISKY_ENDING": (31, "CHEAP ENDING", "Ending used far more by scams (.top, .tk, ...); 20 for .xyz-type endings"),
    "RANDOM_NAME": (10, "RANDOM NAME", "Machine-made name (35 on a free platform)"),
    "FREE_HOSTING": (15, "FREE SITE", "Made on a free website platform"),
    "FREE_HOST_PLUS": (16, "FREE SITE", "Free-platform page with other warning signs"),
    "NUMBER_NAME": (15, "NUMBER NAME", "The name is just a long number"),
    "LOGIN_PATH": (15, "LOGIN PAGE", "Login / account page on a site we can't confirm"),
    "BAIT_WORD": (10, "BAIT WORD", "One login or prize word in the address"),
    "MANY_HYPHENS": (10, "HYPHENS", "Address stuffed with hyphens"),
    "LONG_ADDRESS": (10, "LONG ADDRESS", "Very long address with many parts"),
    "ODD_PORT": (10, "ODD PORT", "Unusual port number"),
    "RISKY_ENDING_MILD": (5, "ENDING", "Ending often used by short-lived sites"),
    "NO_HTTPS": (5, "NO HTTPS", "Not a secure https link"),
    "BRAND_NAME_USED": (15, "BRAND NAME", "Uses a well-known brand's name to look trustworthy"),
    # pipeline rules
    "AGE_CONTRADICTION": (70, "CONTRADICTION", "Claims years of history but the domain is under 30 days old"),
    "VERY_NEW_DOMAIN": (45, "NEW DOMAIN", "Domain registered less than 30 days ago"),
    "NEW_DOMAIN": (20, "NEW DOMAIN", "Domain registered 1-6 months ago"),
    "YOUNG_DOMAIN": (10, "YOUNG DOMAIN", "Domain registered 6-12 months ago"),
    "NEW_COMPANY": (20, "NEW COMPANY", "Company incorporated less than a year ago"),
    "CIN_MISMATCH": (70, "WRONG CIN", "The CIN it shows belongs to another company or is struck off"),
    "CIN_NOT_FOUND": (45, "CIN NOT FOUND", "The CIN it shows is not in company records"),
    "RBI_NOT_LISTED": (45, "NOT FOUND", "Loan app with no RBI-regulated lender listing it (only for unproven, young entities)"),
    "SEBI_FAKE_CLAIM": (70, "FAKE CLAIM", "Shows a SEBI number that SEBI's records give to someone else or don't have"),
    "SEBI_CLAIM_UNCONFIRMED": (45, "UNCONFIRMED", "Says 'SEBI registered' but no SEBI record was found"),
    "SEBI_UNREGISTERED": (35, "NOT REGISTERED", "Gives tips but SEBI has no record of it"),
    "SCAM_REPORTS": (70, "REPORTS", "3+ news or complaint reports of it cheating people (only for unproven entities)"),
    "SCAM_REPORTS_FEW": (35, "REPORTS", "1-2 news or complaint reports of it cheating people"),
    "PLAY_PUBLISHER": (20, "PUBLISHER", "Play Store publisher is a different company"),
    "PLAY_PERMISSIONS": (10, "PERMISSIONS", "Loan app wants contacts, photos, SMS or call logs"),
    "VIRUSTOTAL": (70, "ANTIVIRUS", "3+ antivirus engines flag the site"),
    "VIRUSTOTAL_FEW": (15, "ANTIVIRUS", "1-2 antivirus engines flag the site"),
    "URLSCAN_MALICIOUS": (35, "SCANNER", "urlscan.io scans marked it malicious"),
    "FEED_LISTED_OFFICIAL": (35, "LISTED", "A phishing list names this official domain; a page may be hacked"),
    "USER_SAYS_MONEY": (15, "ASKS MONEY", "You said the page asks for money, OTP, PIN or Aadhaar"),
    "INSECURE_SENSITIVE_FORM": (60, "UNENCRYPTED DATA", "Sensitive form submits over HTTP"),
    "SENSITIVE_EXTERNAL_FORM": (35, "CHECK DATA RECIPIENT", "Sensitive form sends data to another domain with unverified affiliation"),
    "SENSITIVE_QUERY_STRING": (35, "DATA IN URL", "Sensitive form uses GET and may expose data in URLs"),
    "P2P_UPI_REQUEST": (50, "PERSONAL UPI", "Asks to pay directly to a personal UPI ID instead of a verified merchant checkout"),
    "PERSONAL_PHONE_VPA": (35, "PHONE NUMBER VPA", "Found mobile-number based personal payment handle"),
    "WHATSAPP_PAY_REDIRECT": (45, "WHATSAPP FUNNEL", "Redirects payment verification to WhatsApp chat"),
    "EXTERNAL_FORM_SUBMISSION": (45, "THIRD-PARTY FORM", "Forms send user data or payment to external unverified services"),
    "SHORTENED_LINKS": (30, "HIDDEN REDIRECT", "Contains shortened redirect links hiding final URLs"),
}

LABEL = {k: v[1] for k, v in RULES.items()}


@dataclass
class Hit:
    rule_id: str
    agent: str
    penalty: int
    color: str
    claim: str
    how_checked: str
    found: str
    card_en: str = ""
    card_hi: str = ""
    short_en: str = ""
    short_hi: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    level: str = "medium"
    group: str = ""

    def __post_init__(self):
        if not self.group:  # hits made outside collect() get the group of the check that found them
            self.group = {"news": "reputation", "rbi": "regulatory", "sebi": "regulatory", "company": "domain",
                          "passive": "security", "payment": "payment"}.get(self.agent, "link")

    def to_dict(self) -> dict:
        return asdict(self)


def _lc(s: str) -> str:
    if len(s) > 1 and s[:2].isupper():
        return s
    return s[:1].lower() + s[1:]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


_ABBR = re.compile(r"(?:\b(?:Rs|No|Pvt|Ltd|Co|Inc|St|Dr|Mr|Mrs|Ms|vs|etc|e\.g|i\.e)|\d)\.$", re.I)


def _first_sentence(s: str) -> str:
    """First sentence, without cutting at 'Rs.' or a decimal point or inside quotes."""
    s = s.strip()
    depth = 0
    for i, ch in enumerate(s):
        if ch in "“\"":
            depth += 1 if ch == "“" or (ch == '"' and depth % 2 == 0) else -1
        elif ch == "”":
            depth = max(0, depth - 1)
        elif ch in ".।" and depth == 0 and (i + 1 == len(s) or s[i + 1] == " ") and not _ABBR.search(s[: i + 1]):
            return s[:i]
    return s.rstrip(".।")


def _level(points: int) -> str:
    return "hard" if points >= 100 else "strong" if points >= HIGH else "medium" if points >= CAUT else "weak"


def _color(points: int) -> str:
    return "red" if points >= 45 else "amber"


def _mk(rule_id: str, agent: str, points: int, found_en: str, found_hi: str, *, claim: str = "", how: str = "",
        evidence: list[str] | None = None, group: str = "content", card_en: str = "", card_hi: str = "") -> Hit:
    return Hit(rule_id=rule_id, agent=agent, penalty=points, color=_color(points), claim=claim or "A trustworthy business",
               how_checked=how, found=found_en, card_en=card_en or _cap(_first_sentence(found_en)),
               card_hi=card_hi or _first_sentence(found_hi), short_en=_lc(_first_sentence(found_en)),
               short_hi=_first_sentence(found_hi), evidence_ids=list(evidence or []), level=_level(points), group=group)


def _out(outputs: dict, key: str) -> dict:
    return outputs.get(key) or {}


def _done(outputs: dict, key: str) -> dict | None:
    o = outputs.get(key)
    return o if o and o.get("status") == "done" else None


# ---------------------------------------------------------------------------
# The link report (same engine as the preview page)
# ---------------------------------------------------------------------------
def link_report(subject: dict, outputs: dict | None = None) -> linkintel.Report:
    """Analyse what the user typed: the link itself, or for a name, the website
    the name resolved to plus the scam language in the name."""
    q = subject.get("query") or ""
    p = linkintel.parse(q)
    if p.is_link:
        rep = linkintel.analyze(q)
    elif subject.get("website_url"):
        rep = linkintel.analyze(subject["website_url"])
        extra = linkintel.text_hits(q)
        b = linkintel.brand_mentioned(q)
        for s in extra:
            if not any(x.id == s.id for x in rep.signals):
                rep.signals.append(s)
        if b and extra:
            rep.signals.append(linkintel.Signal("BRAND_NAME_USED", 15, "weak", "brand",
                                                f"Uses the name {b['name']} to look trustworthy. Its real site is {b['official'][0]}.",
                                                f"भरोसेमंद दिखने के लिए {b['name']} का नाम इस्तेमाल करता है। असली साइट {b['official'][0]} है।", {}))
        rep.risk = sum(s.points for s in rep.signals if s.points > 0)
    else:
        rep = linkintel.analyze(q)
    # where the page really ended up after redirects
    listing = (outputs or {}).get("listing") or {}
    for pg in (listing.get("data") or {}).get("pages") or []:
        final = pg.get("final_url")
        if final and rep.is_link:
            fp = linkintel.parse(final)
            if fp.is_link and fp.registrable and fp.registrable != rep.parsed.get("registrable"):
                inner = linkintel.analyze(final)
                if inner.verdict not in ("VERIFIED_OFFICIAL", "LOW_RISK"):
                    rep.signals.append(linkintel.Signal("REDIRECTS_ELSEWHERE", 35, "medium", "link",
                                                        f"Opening the link took us to a different site: {fp.host}.",
                                                        f"लिंक खोलने पर हम दूसरी साइट पर पहुँचे: {fp.host}।", {"destination": final[:300]}))
                    for s in inner.signals:
                        if s.points > 0 and not any(x.id == s.id for x in rep.signals):
                            rep.signals.append(s)
                    rep.identity, rep.ugc = None, None
                    rep.risk = sum(s.points for s in rep.signals if s.points > 0)
                break
    return rep


def identity(subject: dict, rep: linkintel.Report | None = None) -> dict | None:
    rep = rep or link_report(subject)
    if rep.ugc:
        return None
    return rep.identity


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------
def _established(outputs: dict, days: int = 730) -> bool:
    dom = (_out(outputs, "company").get("data") or {}).get("domain") or {}
    return bool(dom.get("ok") and (dom.get("age_days") or 0) >= days)


def _popular(outputs: dict) -> int | None:
    t = ((_out(outputs, "passive").get("data") or {}).get("tranco") or {}).get("data") or {}
    r = t.get("rank")
    return r if isinstance(r, int) and r <= 100_000 else None


def evaluate(subject: dict, outputs: dict) -> list[Hit]:
    """Every warning sign found, with fixed points."""
    hits, _ = collect(subject, outputs)
    return hits


def collect(subject: dict, outputs: dict) -> tuple[list[Hit], list[dict]]:
    rep = link_report(subject, outputs)
    ident = None if rep.ugc else rep.identity
    proven = bool(ident and ident.get("verified"))
    hits: list[Hit] = []
    pos: list[dict] = []
    seen: set[str] = set()
    category = subject.get("category") or ""
    listing = _out(outputs, "listing")
    claims = ((listing.get("data") or {}).get("claims") or {}) if listing else {}
    ev_list = list(listing.get("evidence_ids") or [])

    def add(h: Hit) -> None:
        if h.rule_id in seen:
            return
        seen.add(h.rule_id)
        hits.append(h)

    # 1. the link itself ----------------------------------------------------
    for s in rep.signals:
        if s.points <= 0:
            continue
        agent = "listing"
        add(_mk(s.id, agent, s.points, s.en, s.hi, claim=_link_claim(s, subject), how="Link check (fixed rules, no AI)",
                group=s.group if s.group in ("brand", "link", "words", "platform", "content") else "link",
                card_en=_card(s), card_hi=_first_sentence(s.hi)))
    if ident:
        pos.append({"id": "IDENTITY", "group": "identity", "verified": bool(ident.get("verified")),
                    "en": ident["en"], "hi": ident["hi"], "source": {"zone": "Restricted Indian domain zone",
                                                                     "brand_tld": "Brand-owned top-level domain",
                                                                     "brand": "NexVerify brand registry", "known": "NexVerify known-sites list"}.get(ident["source"], "")})

    # 2. what their page says ------------------------------------------------
    page_rules = [
        ("UPFRONT_FEE", claims.get("upfront_fee_text")),
        ("GUARANTEED_RETURNS", claims.get("guaranteed_returns_text")),
        ("LOTTERY_PRIZE", claims.get("lottery_claim_text")),
        ("APK_TEXT", claims.get("apk_download_text")),
        ("VIP_TIPS", claims.get("vip_group_text")),
    ]
    if not (ident and ident.get("verified")):
        for rid, snip in page_rules:
            if not snip or rid in seen:
                continue
            if rid == "UPFRONT_FEE" and proven and category not in ("job offer", "loan app", "lending", "lottery/reward/prize"):
                continue
            if rid == "GUARANTEED_RETURNS" and proven and category not in REGULATED:
                continue
            pts = RULES[rid][0]
            if rid == "VIP_TIPS" and (subject.get("telegram_url") or re.search(r"whats\s*app|telegram", snip, re.I)):
                pts = 70
            # Words on an established site's page (a template shop listing a "lottery" design,
            # a news article quoting a scam) are a note, not proof. Fees for jobs and loans
            # and guaranteed returns on investment sites still count in full.
            if _established(outputs) and not (rid == "UPFRONT_FEE" and category in ("job offer", "loan app", "lending")) \
                    and not (rid == "GUARANTEED_RETURNS" and category in REGULATED):
                pts = 10
            txt = next((t for r2, p2, rx, t, h in linkintel.TEXT_RULES if r2 == rid), RULES[rid][2])
            txt_hi = next((h for r2, p2, rx, t, h in linkintel.TEXT_RULES if r2 == rid), "")
            h = _mk(rid, "listing", pts, f"Their page says “{snip[:120]}”. {txt}", f"उनके पेज पर लिखा है “{snip[:120]}”। {txt_hi}",
                    claim=f"“{snip[:120]}”", how="Text on their page (fixed patterns)", evidence=ev_list, group="content",
                    card_en=RULES[rid][2], card_hi=_first_sentence(txt_hi))
            h.short_en, h.short_hi = "it " + _lc(_first_sentence(txt)), "यह " + _first_sentence(txt_hi)
            add(h)

    ld = listing.get("data") or {}
    dev = ld.get("developer")
    if dev and ld.get("play_url") and not (ident and ident.get("verified")):
        comp_name = ((_out(outputs, "company").get("data") or {}).get("company") or {}).get("company_name")
        rbi_entity = (_out(outputs, "rbi").get("data") or {}).get("entity")
        expected = [x for x in (subject.get("display_name"), subject.get("legal_name"), comp_name, rbi_entity,
                                claims.get("nbfc_partner"), *(claims.get("legal_names") or [])) if x]
        if expected and not any(names_match(dev, e) for e in expected):
            add(_mk("PLAY_PUBLISHER", "listing", RULES["PLAY_PUBLISHER"][0],
                    f"On Google Play the app is published by “{dev}”, a different name.",
                    f"Google Play पर ऐप “{dev}” के नाम से है, जो अलग नाम है।",
                    claim=f"App presented as “{subject.get('display_name')}”", how="Google Play listing page", evidence=ev_list,
                    group="payment", card_en="Publisher mismatch", card_hi="पब्लिशर का नाम अलग"))
    sens = [x for x in ld.get("sensitive_data", []) if x in {"contacts", "photos", "call_logs", "sms"}]
    if sens and category in ("lending", "loan app"):
        nice = {"contacts": "contacts", "photos": "photos", "call_logs": "call logs", "sms": "SMS"}
        nice_hi = {"contacts": "कॉन्टैक्ट्स", "photos": "फ़ोटो", "call_logs": "कॉल लॉग", "sms": "SMS"}
        add(_mk("PLAY_PERMISSIONS", "listing", RULES["PLAY_PERMISSIONS"][0],
                f"The loan app collects your {', '.join(nice[x] for x in sens)}, which illegal lenders use to harass borrowers.",
                f"लोन ऐप आपके {', '.join(nice_hi[x] for x in sens)} लेता है, जिनसे ग़ैरक़ानूनी लेंडर परेशान करते हैं।",
                claim="Loan app from Play Store", how="Play 'Data safety' section", evidence=ev_list, group="payment",
                card_en=f"Asks for {nice[sens[0]]}", card_hi=f"{nice_hi[sens[0]]} माँगता है"))
    if listing.get("status") == "done" and not ld.get("is_blocked"):
        pos.append({"id": "PAGE_OPENED", "group": "claims", "en": "We opened their page and read what it promises.",
                    "hi": "हमने उनका पेज खोलकर उसके दावे पढ़े।", "source": "Direct page fetch"})
    if ld.get("play_verified"):
        pos.append({"id": "PLAY_LISTED", "group": "claims", "strong": False,
                    "en": f"Listing retrieved from Google Play Store" + (f" by {dev}" if dev else "") + ".",
                    "hi": f"Google Play Store पर आधिकारिक ऐप लिस्टेड है" + (f" ({dev})" if dev else "") + "।",
                    "source": "Google Play Store listing"})
    if ld.get("apple_verified"):
        apple_dev = (ld.get("apple_info") or {}).get("developer")
        pos.append({"id": "APP_STORE_LISTED", "group": "claims", "strong": False,
                    "en": f"Listing retrieved from Apple App Store" + (f" by {apple_dev}" if apple_dev else "") + ".",
                    "hi": f"Apple App Store पर आधिकारिक ऐप लिस्टेड है" + (f" ({apple_dev})" if apple_dev else "") + "।",
                    "source": "Apple App Store listing"})

    # Payment & link intelligence
    pi = ld.get("payment_intel") or {}
    if pi:
        if pi.get("risk_flags"):
            for rf in pi.get("risk_flags", []):
                rid = rf["rule"]
                if rid not in seen and rid in RULES:
                    pts = RULES[rid][0]
                    h = _mk(rid, "listing", pts, rf["en"], rf["hi"],
                            claim="Payment & link mechanism", how="Payment & link scanner",
                            evidence=[rf["evidence_id"]] if rf.get("evidence_id") else ev_list, group="payment",
                            card_en=rf["label"], card_hi=rf["label"])
                    h.short_en = rf["en"]
                    h.short_hi = rf["hi"]
                    add(h)
        if pi.get("has_merchant_gateway"):
            gws = ", ".join(pi["detected_gateways"])
            pos.append({
                "id": "MERCHANT_GATEWAY_VERIFIED",
                "group": "payment",
                "strong": False,
                "en": f"Gateway endpoint referenced ({gws}); merchant identity not verified.",
                "hi": f"गेटवे लिंक मिला ({gws}); मर्चेंट की पहचान सत्यापित नहीं है।",
                "source": "Payment gateway scanner"
            })

    # 3. domain and company age --------------------------------------------
    comp = _out(outputs, "company")
    cd = comp.get("data") or {}
    dom = cd.get("domain") or {}
    comp_ev = list(comp.get("evidence_ids") or [])
    age = dom.get("age_days") if dom.get("ok") else None
    years = claims.get("claimed_years")
    if age is not None and not ident:
        if years and years >= 1 and age < 30:
            add(_mk("AGE_CONTRADICTION", "company", 70,
                    f"Claims {years} years of history, but the website was registered only {age} days ago.",
                    f"{years} साल पुराना होने का दावा, पर वेबसाइट सिर्फ़ {age} दिन पहले रजिस्टर हुई।",
                    claim=f"“{years} years” of history", how="Domain registration date (RDAP)", evidence=comp_ev, group="domain",
                    card_en=f"Domain {age} days old, claims {years} years", card_hi=f"डोमेन {age} दिन पुराना, दावा {years} साल"))
        elif age < 30:
            add(_mk("VERY_NEW_DOMAIN", "company", 45, f"The website was registered only {age} days ago. Most scam sites are this new.",
                    f"वेबसाइट सिर्फ़ {age} दिन पहले रजिस्टर हुई। ज़्यादातर स्कैम साइटें इतनी ही नई होती हैं।",
                    claim="An established business", how="Domain registration date (RDAP)", evidence=comp_ev, group="domain",
                    card_en=f"Website only {age} days old", card_hi=f"वेबसाइट सिर्फ़ {age} दिन पुरानी"))
        elif age < 180:
            m = max(1, age // 30)
            add(_mk("NEW_DOMAIN", "company", 20, f"The website was registered only about {m} months ago.",
                    f"वेबसाइट सिर्फ़ लगभग {m} महीने पहले रजिस्टर हुई।", how="Domain registration date (RDAP)", evidence=comp_ev,
                    group="domain", card_en=f"Website {m} month{'s' if m != 1 else ''} old", card_hi=f"वेबसाइट {m} महीने पुरानी"))
        elif age < 365:
            m = max(1, age // 30)
            add(_mk("YOUNG_DOMAIN", "company", 10, f"The website is less than a year old ({m} months).",
                    f"वेबसाइट एक साल से कम पुरानी है ({m} महीने)।", how="Domain registration date (RDAP)", evidence=comp_ev,
                    group="domain", card_en=f"Website {m} month{'s' if m != 1 else ''} old", card_hi=f"वेबसाइट {m} महीने पुरानी"))
    if age is not None and age >= 365:
        pos.append({"id": "DOMAIN_AGE", "group": "domain", "years": age // 365,
                    "en": f"The website has been registered for {age // 365} year{'s' if age >= 730 else ''} ({dom.get('registered_on', '')}).",
                    "hi": f"वेबसाइट {age // 365} साल से रजिस्टर है ({dom.get('registered_on', '')})।", "source": "RDAP (official WHOIS)"})

    company = cd.get("company") or {}
    claimed_cin = (claims.get("cins") or [None])[0]
    if comp.get("status") == "done" and claimed_cin and not ident and company.get("sources"):
        expected = [subject.get("display_name"), subject.get("legal_name"), *(claims.get("legal_names") or [])]
        status = str(company.get("status") or "").lower()
        if company.get("found") is False:
            add(_mk("CIN_NOT_FOUND", "company", 45, f"The company number (CIN {claimed_cin}) on their page is not in company records.",
                    f"उनके पेज पर दिया कंपनी नंबर (CIN {claimed_cin}) कंपनी रिकॉर्ड में नहीं है।", claim=f"CIN {claimed_cin} shown as proof",
                    how=comp.get("method_detail", "Company registry"), evidence=comp_ev, group="regulatory", card_en="CIN not found", card_hi="CIN रिकॉर्ड में नहीं"))
        elif company.get("company_name") and not any(names_match(company["company_name"], e) for e in expected if e):
            add(_mk("CIN_MISMATCH", "company", 70, f"The company number (CIN {claimed_cin}) on their page belongs to another company: {company['company_name']}.",
                    f"उनके पेज पर दिया कंपनी नंबर (CIN {claimed_cin}) किसी दूसरी कंपनी ({company['company_name']}) का है।",
                    claim=f"CIN {claimed_cin} shown as proof", how=comp.get("method_detail", "Company registry"), evidence=comp_ev,
                    group="regulatory", card_en="CIN belongs to another company", card_hi="CIN किसी दूसरी कंपनी का"))
        elif any(x in status for x in ("strike", "struck", "dissolved", "liquidat")):
            add(_mk("CIN_MISMATCH", "company", 70, f"The company it names is closed (status: {company.get('status')}).",
                    f"बताई गई कंपनी बंद हो चुकी है (स्थिति: {company.get('status')})।", claim=f"CIN {claimed_cin} shown as proof",
                    how=comp.get("method_detail", "Company registry"), evidence=comp_ev, group="regulatory", card_en="Company struck off", card_hi="कंपनी बंद"))
    comp_age = cd.get("company_age_days")
    if company.get("found") is True and company.get("sources"):
        pos.append({"id": "COMPANY_REGISTERED", "group": "regulatory",
                    "en": f"Registered company: {company.get('company_name')}" + (f", incorporated {company.get('incorporated_on')}" if company.get("incorporated_on") else "") + (f", status {company.get('status')}" if company.get("status") else "") + ".",
                    "hi": f"रजिस्टर्ड कंपनी: {company.get('company_name')}।", "source": "MCA records (via Google Search, with sources)"})
        if comp_age is not None and comp_age < 365 and not ident:
            add(_mk("NEW_COMPANY", "company", 20, f"The company was incorporated only {max(1, comp_age // 30)} months ago.",
                    f"कंपनी सिर्फ़ {max(1, comp_age // 30)} महीने पहले बनी।", how="Incorporation date (MCA)", evidence=comp_ev,
                    group="regulatory", card_en="Company under 1 year old", card_hi="कंपनी 1 साल से कम पुरानी"))

    # 4. regulators ---------------------------------------------------------
    young = not _established(outputs)
    rbi = _out(outputs, "rbi")
    rd = rbi.get("data") or {}
    if rbi.get("status") == "done":
        if rd.get("found") is True:
            pos.append({"id": "RBI_LISTED", "group": "regulatory", "strong": True,
                        "en": f"Listed by an RBI-regulated lender: {rd.get('entity') or 'regulated entity'}.",
                        "hi": f"RBI के नियम वाले लेंडर की सूची में: {rd.get('entity') or ''}।", "source": "RBI Digital Lending Apps list (via Google Search, with sources)"})
        elif rd.get("found") is False and rd.get("sources") and not proven and category in ("lending", "loan app"):
            add(_mk("RBI_NOT_LISTED", "rbi", 45 if young else 20, "No RBI-regulated bank or NBFC lists this loan app. Legal loan apps must be run by one.",
                    "कोई RBI-रजिस्टर्ड बैंक या NBFC इस लोन ऐप को लिस्ट नहीं करता। क़ानूनी लोन ऐप किसी रजिस्टर्ड लेंडर के होने चाहिए।",
                    claim="Lending app" + (f" claiming “{claims['rbi_claim_text']}”" if claims.get("rbi_claim_text") else ""),
                    how=rbi.get("method_detail", "RBI DLA list via Google Search"), evidence=rbi.get("evidence_ids"), group="regulatory",
                    card_en="No lender lists this app", card_hi="किसी लेंडर ने यह ऐप लिस्ट नहीं किया"))
    sebi = _out(outputs, "sebi")
    sd = sebi.get("data") or {}
    nums = claims.get("sebi_numbers") or []
    if sebi.get("status") == "done":
        if sd.get("found") is True:
            pos.append({"id": "SEBI_REGISTERED", "group": "regulatory", "strong": True,
                        "en": f"SEBI registered: {sd.get('category') or 'intermediary'} {sd.get('reg_no') or ''}".strip() + ".",
                        "hi": f"SEBI रजिस्टर्ड: {sd.get('reg_no') or ''}।", "source": "SEBI records (via Google Search, with sources)"})
        elif sd.get("found") is False and sd.get("sources") and not proven:
            tips = bool(subject.get("telegram_url")) or "VIP_TIPS" in seen
            if nums:
                add(_mk("SEBI_FAKE_CLAIM", "sebi", 70, f"It shows SEBI number {nums[0]}, but SEBI's records have no match for it.",
                        f"यह SEBI नंबर {nums[0]} दिखाता है, पर SEBI के रिकॉर्ड में यह नहीं है।", claim=f"“SEBI registered” (no. {nums[0]})",
                        how=sebi.get("method_detail", "SEBI lists via Google Search"), evidence=sebi.get("evidence_ids"), group="regulatory",
                        card_en="Fake SEBI number", card_hi="नकली SEBI नंबर"))
            elif claims.get("sebi_claim") and young:
                add(_mk("SEBI_CLAIM_UNCONFIRMED", "sebi", 45, "It says it is SEBI registered, but no SEBI record was found for it.",
                        "यह SEBI रजिस्टर्ड होने का दावा करता है, पर इसका कोई SEBI रिकॉर्ड नहीं मिला।", claim="“SEBI registered”",
                        how=sebi.get("method_detail", "SEBI lists via Google Search"), evidence=sebi.get("evidence_ids"), group="regulatory",
                        card_en="SEBI claim not found", card_hi="SEBI दावा नहीं मिला"))
            elif tips:
                add(_mk("SEBI_UNREGISTERED", "sebi", 35, "It gives stock tips, but SEBI has no record of it. Only registered advisers may sell tips.",
                        "यह शेयर टिप्स देता है, पर SEBI में इसका कोई रिकॉर्ड नहीं। सिर्फ़ रजिस्टर्ड सलाहकार टिप्स बेच सकते हैं।",
                        claim="Stock tips channel", how=sebi.get("method_detail", "SEBI lists via Google Search"), evidence=sebi.get("evidence_ids"),
                        group="regulatory", card_en="Gives tips, not SEBI registered", card_hi="टिप्स देता है, SEBI में नहीं"))

    # 5. complaints ----------------------------------------------------------
    news = _out(outputs, "news")
    nd = news.get("data") or {}
    if news.get("status") == "done":
        n = int(nd.get("reports_count") or 0)
        if n and not proven:
            types = nd.get("types") or []
            kinds = " and ".join(types[:2]) if types else "scam"
            rid = "SCAM_REPORTS" if n >= 3 else "SCAM_REPORTS_FEW"
            add(_mk(rid, "news", RULES[rid][0], f"{n} news or complaint report{'s' if n != 1 else ''} say it cheated people ({kinds}).",
                    f"{n} ख़बरों या शिकायतों में लिखा है कि इसने लोगों को ठगा ({kinds})।", how=news.get("method_detail", "News and forums via Google Search"),
                    evidence=news.get("evidence_ids"), group="reputation", card_en=f"{_cap(kinds)} reports", card_hi=f"{n} शिकायतें"))
        elif not n:
            pos.append({"id": "NO_REPORTS", "group": "reputation", "en": "No news or complaint reports of it cheating people.",
                        "hi": "इसके ठगने की कोई ख़बर या शिकायत नहीं मिली।", "source": "News and forums via Google Search"})

    # 6. security feeds --------------------------------------------------------
    pdata = _out(outputs, "passive").get("data") or {}
    tf = pdata.get("threat_feeds") or {}
    if tf.get("status") == "fail":
        exact = (tf.get("data") or {}).get("match") == "url"
        if ident and ident.get("verified") and not exact:
            add(_mk("FEED_LISTED_OFFICIAL", "news", 35, "A phishing list names this official domain. The site is real, but a page on it may have been hacked.",
                    "एक फ़िशिंग सूची में यह आधिकारिक डोमेन है। साइट असली है, पर इसका कोई पेज हैक हो सकता है।", how=tf.get("source", "Threat feeds"), group="security"))
        else:
            add(_mk("THREAT_FEED", "news", 100, "This address is on an active phishing / malware list.",
                    "यह पता एक सक्रिय फ़िशिंग / मैलवेयर सूची में है।", how=tf.get("source", "Threat feeds"), group="security",
                    card_en="On a phishing list", card_hi="फ़िशिंग सूची में"))
    elif tf.get("status") == "pass":
        pos.append({"id": "FEEDS_CLEAN", "group": "security", "en": "Not on the phishing and malware lists we check.",
                    "hi": "हमारी जाँची फ़िशिंग और मैलवेयर सूचियों में नहीं है।", "source": tf.get("source", "Threat feeds")})
    sb = pdata.get("safe_browsing") or {}
    if sb.get("status") == "fail":
        add(_mk("SAFE_BROWSING", "listing", 100, sb.get("reason") or "Google Safe Browsing lists this page as dangerous.",
                "Google Safe Browsing ने इस पेज को ख़तरनाक बताया है।", how="Google Safe Browsing v4", group="security",
                card_en="Google Safe Browsing warning", card_hi="Google सेफ़ ब्राउज़िंग चेतावनी"))
    elif sb.get("status") == "pass":
        pos.append({"id": "SAFE_BROWSING_CLEAN", "group": "security", "en": "Google Safe Browsing has no warning for it.",
                    "hi": "Google Safe Browsing में इसके लिए कोई चेतावनी नहीं।", "source": "Google Safe Browsing v4"})
    vt = pdata.get("virustotal") or {}
    if vt.get("status") == "fail" and not (ident and ident.get("verified")):
        add(_mk("VIRUSTOTAL", "listing", 70, vt.get("reason") or "Several antivirus engines flag this site.", "कई एंटीवायरस इंजन इस साइट को ख़तरनाक बताते हैं।",
                how="VirusTotal", group="security", card_en="Antivirus warning", card_hi="एंटीवायरस चेतावनी"))
    elif vt.get("status") == "warn" and not ident:
        add(_mk("VIRUSTOTAL_FEW", "listing", 15, vt.get("reason") or "One or two antivirus engines flag this site.", "एक-दो एंटीवायरस इंजन इसे संदिग्ध बताते हैं।",
                how="VirusTotal", group="security"))
    us = pdata.get("urlscan") or {}
    if us.get("status") == "fail" and not ident:
        add(_mk("URLSCAN_MALICIOUS", "listing", 35, us.get("reason") or "Earlier urlscan.io scans marked it malicious.", "पिछले urlscan.io स्कैन ने इसे ख़तरनाक बताया।",
                how="urlscan.io", group="security"))
    rank = _popular(outputs)
    if rank and not rep.platform and not rep.ugc:
        pos.append({"id": "POPULAR", "group": "identity", "strong": True,
                    "en": f"One of the world's most visited sites (Tranco rank #{rank:,}).", "hi": f"दुनिया की सबसे ज़्यादा देखी जाने वाली साइटों में (Tranco रैंक #{rank:,})।",
                    "source": "Tranco top sites"})
    ssl = ld.get("ssl_info") or {}
    if ssl.get("is_valid"):
        pos.append({"id": "HTTPS", "group": "security", "en": f"Valid HTTPS certificate ({ssl.get('issuer') or 'trusted issuer'}).",
                    "hi": "मान्य HTTPS सर्टिफ़िकेट।", "source": "TLS handshake"})

    # 7. category, and what the user told us ----------------------------------
    if category in ("online betting/gambling", "betting", "casino", "satta") and "BETTING" not in seen and not (ident and ident.get("verified")):
        bet = linkintel.betting_hit("casino")
        add(_mk("BETTING", "listing", 70, bet.en, bet.hi, how="Category check", group="content",
                card_en="Betting / gambling platform", card_hi="सट्टा / बेटिंग प्लेटफ़ॉर्म"))
    answers = subject.get("human_answers") or {}
    if subject.get("human_assisted") and answers.get("asks_money_or_otp") and any(h.penalty >= 35 for h in hits):
        add(_mk("USER_SAYS_MONEY", "listing", 15, "You told us the page asks for money, an OTP, your PIN or Aadhaar.",
                "आपने बताया कि पेज पैसे, OTP, PIN या आधार माँगता है।", how="What you saw on the page", group="payment",
                card_en="Asks for money / OTP", card_hi="पैसे / OTP माँगता है"))
    return hits, pos


def _card(s: linkintel.Signal) -> str:
    d = s.detail or {}
    brand = d.get("brand")
    if s.id in ("BRAND_IMPERSONATION", "BRAND_IN_SUBDOMAIN", "BRAND_LOOKALIKE_NAME", "BRAND_IN_PATH") and brand:
        b = next((x for x in linkintel.data()["brands"] if x["id"] == brand), None)
        return f"Fake {b['name'].split(' (')[0]} address" if b else "Fake brand address"
    if s.id == "LOOKALIKE" and brand:
        b = next((x for x in linkintel.data()["brands"] if x["id"] == brand), None)
        return f"Looks like {d.get('real')}" if b else "Lookalike address"
    return _cap(_first_sentence(s.en))[:80]


def _link_claim(s: linkintel.Signal, subject: dict) -> str:
    real = (s.detail or {}).get("real")
    if real:
        return f"Official site ({real})"
    return "A normal, safe link"


# ---------------------------------------------------------------------------
# Score and verdict
# ---------------------------------------------------------------------------
V = {
    "HIGH_RISK": ("red", "HIGH RISK: DO NOT PAY", "बहुत ज़्यादा जोखिम: पैसे न भेजें"),
    "SUSPICIOUS": ("amber", "SUSPICIOUS: WARNING SIGNS", "संदिग्ध: ख़तरे के संकेत"),
    "CAUTION": ("amber", "BE CAREFUL", "सावधान रहें"),
    "UNKNOWN": ("gray", "COULD NOT VERIFY: DON'T PAY YET", "पुष्टि नहीं हो पाई: अभी पैसे न भेजें"),
    "LOW_RISK": ("green", "LOOKS SAFE", "सुरक्षित लगता है"),
    "VERIFIED_OFFICIAL": ("green", "VERIFIED OFFICIAL", "प्रमाणित आधिकारिक"),
}


def _verdict(code: str, reason_en: str = "", reason_hi: str = "") -> dict:
    c, en, hi = V[code]
    return {"code": code, "color": c, "label_en": en, "label_hi": hi, "reason_en": reason_en, "reason_hi": reason_hi}


def proof_of(subject: dict, outputs: dict, hits: list[Hit] | None = None) -> tuple[str | None, str, str]:
    """('verified' | 'strong' | None, reason_en, reason_hi): what proves who runs it."""
    rep = link_report(subject, outputs)
    ident = None if rep.ugc else rep.identity
    category = subject.get("category") or ""
    if ident and ident.get("verified"):
        return "verified", ident["en"], ident["hi"]
    if ident:
        if ident.get("source") == "zone" and rep.is_link and not linkintel._simple_path(linkintel.parse(subject.get("query") or "")):
            pass
        else:
            return "strong", ident["en"], ident["hi"]
    _, pos = collect(subject, outputs)
    ids = {p["id"] for p in pos}
    # Popularity is reputation, not proof of domain control or legal affiliation.
    if ids & {"RBI_LISTED", "SEBI_REGISTERED"}:
        p = next(x for x in pos if x["id"] in ("RBI_LISTED", "SEBI_REGISTERED"))
        return "strong", p["en"], p["hi"]
    if category in REGULATED:
        return None, "", ""
    old = next((x for x in pos if x["id"] == "DOMAIN_AGE"), None)
    if "COMPANY_REGISTERED" in ids and old and old.get("years", 0) >= 2 and "PAGE_OPENED" in ids:
        return "strong", "Registered company with a website that is several years old.", "रजिस्टर्ड कंपनी, जिसकी वेबसाइट कई साल पुरानी है।"
    if old and old.get("years", 0) >= 3 and "PAGE_OPENED" in ids and not rep.ugc and not rep.platform:
        return "strong", old["en"], old["hi"]
    return None, "", ""


def score_and_verdict(hits: list[Hit], subject: dict | None = None, outputs: dict | None = None,
                      checked: int = 5, is_demo: bool = False) -> tuple[int, dict]:
    subject = subject or {}
    outputs = outputs or {}
    risk = sum(h.penalty for h in hits)
    score = max(0, 100 - risk)
    if any(h.penalty >= 100 for h in hits):
        return min(score, 10), _verdict("HIGH_RISK")
    if risk >= HIGH:
        return score, _verdict("HIGH_RISK")
    if risk >= SUSP:
        return score, _verdict("SUSPICIOUS")
    if risk >= CAUT:
        return score, _verdict("CAUTION")
    if not subject:
        return score, _verdict("LOW_RISK" if score >= 70 else "UNKNOWN")
    level, why_en, why_hi = proof_of(subject, outputs, hits)
    if level == "verified":
        return score, _verdict("VERIFIED_OFFICIAL", why_en, why_hi)
    if level == "strong":
        return score, _verdict("LOW_RISK", why_en, why_hi)
    # "Couldn't verify" is shown as "?"; the stored number is a neutral 50 so lists and
    # batch counts never treat it as safe.
    return min(score, 50), _verdict("UNKNOWN", "Nothing proves who runs it.", "कुछ भी साबित नहीं करता कि इसे कौन चलाता है।")


def score_of(hits: list[Hit], subject: dict | None = None, outputs: dict | None = None) -> int:
    return max(0, 100 - sum(h.penalty for h in hits))


def verdict_of(score: int, checked: int = 5, hits: list[Hit] | None = None, is_demo: bool = False,
               subject: dict | None = None) -> dict:
    if hits is None and subject is None:
        risk = 100 - score
        return _verdict("HIGH_RISK" if risk >= HIGH else "SUSPICIOUS" if risk >= SUSP else "CAUTION" if risk >= CAUT else "LOW_RISK")
    return score_and_verdict(hits or [], subject, None, checked=checked, is_demo=is_demo)[1]


# ---------------------------------------------------------------------------
# Page pieces: per-check cards, the 7-part breakdown, the summary
# ---------------------------------------------------------------------------
def cards_of(subject: dict, outputs: dict, hits: list[Hit]) -> list[dict]:
    rep = link_report(subject, outputs)
    ident = None if rep.ugc else rep.identity
    _, pos = collect(subject, outputs)
    pids = {p["id"]: p for p in pos}
    cards = []
    for key in AGENT_ORDER:
        out = outputs.get(key)
        title = (out or {}).get("title") or AGENT_TITLES[key]
        card = {"key": key, "title": title, "state": (out or {}).get("status", "queued"), "label": "", "color": "gray",
                "detail_en": "", "detail_hi": "", "penalty": 0, "method": (out or {}).get("method", "")}
        if not out:
            cards.append(card)
            continue
        mine = sorted([h for h in hits if h.agent == key], key=lambda h: -h.penalty)
        if mine:
            card.update(label=LABEL.get(mine[0].rule_id, "WARNING"), color="red" if any(h.color == "red" for h in mine) else "amber",
                        detail_en=_cap(", ".join([mine[0].card_en] + [_lc(h.card_en) for h in mine[1:3]])),
                        detail_hi=", ".join(h.card_hi for h in mine[:3]), penalty=-sum(h.penalty for h in mine))
        elif out.get("status") == "skipped":
            card.update(label="SKIPPED", detail_en=out.get("note") or "Not needed", detail_hi=out.get("note_hi") or "ज़रूरी नहीं")
        elif out.get("status") in ("unverified", "error"):
            card.update(label="UNVERIFIED", detail_en=out.get("note") or "Could not check; not scored",
                        detail_hi="जाँच नहीं हो सकी; स्कोर में नहीं गिना")
        else:
            d = out.get("data") or {}
            if key == "rbi":
                if "RBI_LISTED" in pids:
                    card.update(label="LISTED", color="green", detail_en=pids["RBI_LISTED"]["en"], detail_hi=pids["RBI_LISTED"]["hi"])
                else:
                    card.update(label="CHECKED", detail_en="No RBI listing found by search (not scored)", detail_hi="खोज में RBI सूची नहीं मिली (स्कोर में नहीं)")
            elif key == "sebi":
                if "SEBI_REGISTERED" in pids:
                    card.update(label="REGISTERED", color="green", detail_en=pids["SEBI_REGISTERED"]["en"], detail_hi=pids["SEBI_REGISTERED"]["hi"])
                else:
                    card.update(label="CHECKED", detail_en="No SEBI record found by search (not scored)", detail_hi="खोज में SEBI रिकॉर्ड नहीं मिला (स्कोर में नहीं)")
            elif key == "company":
                if "COMPANY_REGISTERED" in pids:
                    c = d.get("company") or {}
                    yr = (c.get("incorporated_on") or "")[:4]
                    card.update(label="REGISTERED", color="green", detail_en=f"Incorporated {yr or '?'}, status {c.get('status') or 'active'}",
                                detail_hi=f"{yr} में बनी, स्थिति: {c.get('status') or 'सक्रिय'}")
                elif "DOMAIN_AGE" in pids:
                    card.update(label="OLD DOMAIN", color="green", detail_en=pids["DOMAIN_AGE"]["en"], detail_hi=pids["DOMAIN_AGE"]["hi"])
                elif ident:
                    card.update(label="OFFICIAL", color="green", detail_en=ident["en"], detail_hi=ident["hi"])
                else:
                    card.update(label="NO RECORD", detail_en="No company record or domain age found (not scored)", detail_hi="कंपनी रिकॉर्ड या डोमेन की उम्र नहीं मिली (स्कोर में नहीं)")
            elif key == "listing":
                if ident:
                    card.update(label="OFFICIAL" if ident.get("verified") else "KNOWN SITE", color="green", detail_en=ident["en"], detail_hi=ident["hi"])
                elif rep.ugc:
                    card.update(label="USER PAGE", detail_en=f"A {rep.ugc[0]} made by someone on a real platform; can't tell who",
                                detail_hi=f"असली प्लेटफ़ॉर्म पर किसी का बनाया {rep.ugc[1]}; किसने, पता नहीं")
                elif "APP_STORE_LISTED" in pids and "PLAY_LISTED" in pids:
                    card.update(label="STORE LISTINGS", color="green", detail_en="Listed on both Google Play & Apple App Store",
                                detail_hi="Google Play और Apple App Store दोनों पर मौजूद")
                elif "APP_STORE_LISTED" in pids:
                    card.update(label="APP STORE", color="green", detail_en=pids["APP_STORE_LISTED"]["en"],
                                detail_hi=pids["APP_STORE_LISTED"]["hi"])
                elif "PLAY_LISTED" in pids:
                    card.update(label="PLAY STORE", color="green", detail_en=pids["PLAY_LISTED"]["en"],
                                detail_hi=pids["PLAY_LISTED"]["hi"])
                elif "MERCHANT_GATEWAY_VERIFIED" in pids:
                    card.update(label="GATEWAY", color="green", detail_en=pids["MERCHANT_GATEWAY_VERIFIED"]["en"],
                                detail_hi=pids["MERCHANT_GATEWAY_VERIFIED"]["hi"])
                else:
                    card.update(label="NO RED FLAGS", color="green", detail_en="Link and page checked, nothing wrong found",
                                detail_hi="लिंक और पेज जाँचे, कुछ गलत नहीं मिला")
            elif key == "news":
                card.update(label="NO REPORTS", color="green", detail_en="No reports of it cheating people", detail_hi="ठगी की कोई शिकायत नहीं")
        cards.append(card)
    return cards


_GROUPS = [
    ("identity", "Who runs the site", "साइट कौन चलाता है", ("brand", "link", "words", "platform")),
    ("domain", "Website age", "वेबसाइट की उम्र", ("domain",)),
    ("security", "Phishing lists & security", "फ़िशिंग सूची और सुरक्षा", ("security",)),
    ("regulatory", "RBI / SEBI / company records", "RBI / SEBI / कंपनी रिकॉर्ड", ("regulatory",)),
    ("claims", "What it promises", "यह क्या वादा करता है", ("content",)),
    ("reputation", "Complaints", "शिकायतें", ("reputation",)),
    ("payment", "App & payment", "ऐप और पेमेंट", ("payment",)),
]


def build_score_breakdown(subject: dict, outputs: dict, hits: list[Hit], score: int, verdict: dict) -> tuple[list[dict], str, dict]:
    """Seven rows. Points are exactly the points used in the score; a row with
    nothing to report says so instead of inventing a check."""
    _, pos = collect(subject, outputs)
    rows = []
    for gid, en, hi, groups in _GROUPS:
        mine = [h for h in hits if h.group in groups]
        p = [x for x in pos if x["group"] == gid]
        if mine:
            pts = sum(h.penalty for h in mine)
            rows.append({"id": gid, "title_en": en, "title_hi": hi, "category": gid,
                         "status": "fail" if any(h.penalty >= 45 for h in mine) else "warn", "points": f"-{pts}",
                         "evidence_en": " ".join(_cap(_first_sentence(h.found)) + "." for h in sorted(mine, key=lambda h: -h.penalty)[:3]),
                         "evidence_hi": "। ".join(h.short_hi for h in mine[:3]), "source": ", ".join(sorted({h.how_checked for h in mine if h.how_checked}))[:120]})
        elif p:
            rows.append({"id": gid, "title_en": en, "title_hi": hi, "category": gid, "status": "pass", "points": "0",
                         "evidence_en": " ".join(x["en"] for x in p[:2]), "evidence_hi": " ".join(x["hi"] for x in p[:2]),
                         "source": ", ".join(sorted({x.get("source", "") for x in p if x.get("source")}))[:120]})
        else:
            rows.append({"id": gid, "title_en": en, "title_hi": hi, "category": gid, "status": "unknown", "points": "0",
                         "evidence_en": _unknown_reason(gid, subject, outputs), "evidence_hi": "जाँच नहीं हुई या ज़रूरी नहीं थी।", "source": ""})
    verified = sum(1 for r in rows if r["status"] != "unknown")
    code = verdict.get("code")
    strong_neg = any(h.penalty >= HIGH for h in hits)
    if code == "VERIFIED_OFFICIAL" or strong_neg:
        conf = "HIGH"
    elif code == "LOW_RISK" and verified >= 4 and not (
            (subject.get("category") or "") in REGULATED and any(r["id"] == "regulatory" and r["status"] == "unknown" for r in rows)):
        conf = "HIGH"  # a money business is never "high confidence" while its licence is unchecked
    elif verified >= 3:
        conf = "MEDIUM"
    else:
        conf = "LOW"
    strip = {"total": len(rows), "verified": verified, "unverified": len(rows) - verified, "confidence": conf,
             "label_en": f"{len(rows)} areas: {verified} with evidence, {len(rows) - verified} without",
             "label_hi": f"{len(rows)} क्षेत्र: {verified} में सबूत, {len(rows) - verified} में नहीं"}
    return rows, conf, strip


def _unknown_reason(gid: str, subject: dict, outputs: dict) -> str:
    st = lambda k: (outputs.get(k) or {}).get("status")  # noqa: E731
    if gid == "domain":
        return "Domain age not available (no website, or the registry did not answer)."
    if gid == "regulatory":
        return "No RBI / SEBI licence needed for this kind of business, or the lookup did not run." if st("rbi") == "skipped" and st("sebi") == "skipped" else "Lookups did not return a usable answer."
    if gid == "reputation":
        return "Complaint search did not run." if st("news") != "done" else "No reports."
    if gid == "security":
        return "Phishing lists were not reachable."
    if gid == "claims":
        return "We could not open their page."
    if gid == "payment":
        return "No app listing or payment page to check."
    return "Nothing proves who runs it."


def summary_template(score: int, verdict: dict, hits: list[Hit], subject: dict | None = None, outputs: dict | None = None) -> dict:
    code = verdict.get("code", "")
    top = sorted(hits, key=lambda h: -h.penalty)[:2]
    if code in ("HIGH_RISK", "SUSPICIOUS", "CAUTION") and top:
        en = _cap(top[0].short_en)
        hi = top[0].short_hi
        if len(top) > 1:
            en += ", and " + top[1].short_en
            hi += ", और " + top[1].short_hi
        tail_en = " Don't pay. Already paid? Call 1930." if code == "HIGH_RISK" else " Don't pay until this is explained." if code == "SUSPICIOUS" else " Check carefully before you pay anything."
        tail_hi = " पैसे न भेजें। भेज चुके हैं? 1930 पर कॉल करें।" if code == "HIGH_RISK" else " यह साफ़ होने तक पैसे न भेजें।" if code == "SUSPICIOUS" else " कुछ भी भेजने से पहले ध्यान से जाँचें।"
        return {"en": en + "." + tail_en, "hi": hi + "।" + tail_hi}
    if code == "VERIFIED_OFFICIAL":
        why = verdict.get("reason_en") or "The address proves this is the official site."
        why_hi = verdict.get("reason_hi") or "पता साबित करता है कि यह आधिकारिक साइट है।"
        is_unverified = bool(outputs and (outputs.get("listing") or {}).get("status") in ("unverified", "error"))
        scope_en = " Note: Verification is established by official registry proof (live website content was not crawled)." if is_unverified else ""
        scope_hi = " ध्यान दें: यह पुष्टि आधिकारिक रजिस्ट्री रिकॉर्ड पर आधारित है (वेबसाइट सामग्री क्रॉल नहीं हुई)।" if is_unverified else ""
        return {"en": f"{why}{scope_en} Still, never share your OTP or PIN, and check the address bar matches exactly.",
                "hi": f"{why_hi}{scope_hi} फिर भी OTP या PIN कभी न बताएँ, और देखें कि पता बिल्कुल यही हो।"}
    if code == "LOW_RISK":
        why = verdict.get("reason_en") or "Records look consistent."
        return {"en": f"No warning signs. {why} This is not a guarantee, so never pay strangers upfront.",
                "hi": f"कोई ख़तरे का संकेत नहीं। {verdict.get('reason_hi') or ''} यह गारंटी नहीं है, अनजान लोगों को पहले पैसे न दें।".replace("  ", " ")}
    rep = link_report(subject) if subject else None
    if rep and rep.ugc and rep.identity:
        return {"en": f"The website is the real {rep.identity.get('name') or 'platform'}, but this {rep.ugc[0]} was made by one of its users. We can't confirm who, so don't pay or share details yet.",
                "hi": f"वेबसाइट असली {rep.identity.get('name') or 'प्लेटफ़ॉर्म'} है, पर यह {rep.ugc[1]} किसी यूज़र ने बनाया है। किसने, पता नहीं, इसलिए अभी पैसे या जानकारी न दें।"}
    if top:
        return {"en": f"We couldn't confirm who runs this, and {top[0].short_en}. Don't pay until you have checked it through the official website or app.",
                "hi": f"इसे कौन चलाता है, पुष्टि नहीं हो पाई, और {top[0].short_hi}। ऑफ़िशियल वेबसाइट या ऐप से जाँचे बिना पैसे न भेजें।"}
    return {"en": "Nothing we checked looks wrong, but nothing proves who runs it either. Don't pay until you confirm it through official channels.",
            "hi": "जाँच में कुछ गलत नहीं दिखा, पर यह भी साबित नहीं हुआ कि इसे कौन चलाता है। ऑफ़िशियल माध्यम से पक्का किए बिना पैसे न भेजें।"}
