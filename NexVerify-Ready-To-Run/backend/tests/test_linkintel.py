"""The offline link engine: real sites must never be called dangerous, copies of
real sites must be caught, and nothing unproven may be called safe."""
import pytest

from app import linkintel

BAD = {"HIGH_RISK", "SUSPICIOUS", "CAUTION"}
SAFE = {"VERIFIED_OFFICIAL", "LOW_RISK"}

OFFICIAL = [
    "sbi.bank.in", "https://onlinesbi.sbi.bank.in/", "hdfcbank.com", "https://netbanking.hdfcbank.com/netbanking/",
    "incometax.gov.in", "uidai.gov.in", "cybercrime.gov.in", "groww.in", "zerodha.com", "paytm.com", "phonepe.com",
    "flipkart.com", "amazon.in", "irctc.co.in", "rbi.org.in", "sebi.gov.in", "npci.org.in", "accounts.google.com",
    "youtube.com", "microsoft.com", "apple.com",
]

NOT_DANGEROUS = [  # real, unrelated sites with names close to a brand
    "grow.com", "canada.ca", "forbesindia.com", "outlookindia.com", "images-amazon.com", "s-msn.com",
    "online-instagram.com", "ah-me.com", "telegraf.com", "healthunlocked.com", "paytmmall.com", "gov.on.ca",
    "bit.ly", "github.io", "translate.google.com",
]

SCAMS = [
    "sbi-bank.in", "incometax-gov.in", "hdfcbank-com.xyz", "onlinesbi-sbi-login.com", "sbi.bank.in-verify.com",
    "securehdfcbnak.com", "flipkrat.com", "bseindai.com", "loginpaytmm.in", "paytm-login.in", "amazonn-offer.in",
    "zer0dha.com", "sbi-rewards-claim.in", "pmkisan-yojana-apk.in", "kbc-lucky-draw-winner.in", "https://bankingsbi.co.in/",
    "https://1win-uz.eu.com/", "https://1-win.tr/", "https://www.google.com/url?q=https://sbi-kyc-update.top/login",
    "http://192.168.10.5/hdfc/login.php", "https://xn--pytm-qna.com/", "https://sites.google.com/view/sbi-kyc-update",
    "https://my-bank-kyc.weebly.com/", "https://bit.ly/3xYzAbc",
]


@pytest.mark.parametrize("u", OFFICIAL)
def test_official_sites_are_safe(u):
    r = linkintel.analyze(u)
    assert r.verdict in SAFE, (u, r.verdict, [s.id for s in r.signals])


@pytest.mark.parametrize("u", NOT_DANGEROUS)
def test_lookalike_names_of_real_sites_are_not_dont_pay(u):
    r = linkintel.analyze(u)
    assert r.verdict != "HIGH_RISK", (u, [(s.id, s.points) for s in r.signals])


@pytest.mark.parametrize("u", SCAMS)
def test_scam_links_are_flagged(u):
    r = linkintel.analyze(u)
    assert r.verdict in BAD, (u, r.verdict, [(s.id, s.points) for s in r.signals])
    assert r.verdict not in SAFE


@pytest.mark.parametrize("u", ["some-new-shop.in", "https://kavya-decor-studios.in/", "xk7-qpl-trade.in"])
def test_unknown_sites_are_never_called_safe(u):
    assert linkintel.analyze(u).verdict not in SAFE


@pytest.mark.parametrize("u", ["https://docs.google.com/document/d/abc/edit", "https://forms.gle/abc123",
                               "https://sites.google.com/view/myshop"])
def test_pages_made_by_anyone_on_big_platforms_are_unknown(u):
    """A Google Doc or Form is on Google's address, but anyone can make one."""
    r = linkintel.analyze(u)
    assert r.verdict == "UNKNOWN" and r.ugc


def test_hacked_college_page_is_not_called_official():
    r = linkintel.analyze("https://dept.someuniv.ac.in/wp-content/uploads/.well/sbi/login.php")
    assert r.verdict not in SAFE


def test_score_is_100_minus_risk():
    r = linkintel.analyze("hdfcbank-com.xyz")
    assert r.risk == sum(s.points for s in r.signals)
    assert r.score == max(0, 100 - r.risk) or r.verdict == "UNKNOWN"


def test_restricted_zone_split():
    assert linkintel.split_host("onlinesbi.sbi.bank.in")[0] == "sbi.bank.in"
    assert linkintel.split_host("incometax.gov.in")[0] == "incometax.gov.in"
    assert linkintel.split_host("abc.github.io")[0] == "abc.github.io"


def test_page_text_rules():
    r = linkintel.analyze("some-jobs-portal.in", page_text="Pay Rs 999 registration fee to confirm your work from home job")
    assert "UPFRONT_FEE" in {s.id for s in r.signals}
    assert r.verdict in BAD
