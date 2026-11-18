from datetime import date

from app.claims import extract_claims, names_match, play_developer, sensitive_data_types


def test_extracts_core_claims():
    text = ("Bullvanta Signals - 10 years trusted company. SEBI Regd. Research Analyst INH000000000. "
            "CIN U67190MH2014PTC000777. Guaranteed 300% returns in 30 days!")
    c = extract_claims(text)
    assert c.claimed_years == 10
    assert c.cins == ["U67190MH2014PTC000777"]
    assert c.sebi_numbers == ["INH000000000"]
    assert c.sebi_claim is True
    assert "300% returns" in c.guaranteed_returns_text


def test_since_year_and_rbi_claim():
    c = extract_claims("Loans by SafeKosh Capital Limited, an RBI registered NBFC. Serving customers since 2016.",
                       today=date(2026, 10, 21))
    assert c.claimed_years == 10
    assert c.rbi_claim is True
    assert c.legal_names == ["SafeKosh Capital Limited"]


def test_years_need_trust_words():
    # "2 years" of loan tenure is not a trust claim
    assert extract_claims("Loan tenure up to 2 years, EMI from Rs 999").claimed_years is None


def test_upfront_fee_and_nbfc_partner():
    c = extract_claims("Pay a refundable registration fee of Rs. 1,999. Lending partner: Zorvana Finvest Private Limited")
    assert "registration fee" in c.upfront_fee_text
    assert c.nbfc_partner == "Zorvana Finvest Private Limited"


def test_play_developer_html_and_markdown():
    html = '<a href="/store/apps/dev?id=123"><span>Qrovix Tech Solutions</span></a>'
    assert play_developer(html) == "Qrovix Tech Solutions"
    html2 = '<a href="/store/apps/developer?id=SafeKosh+Capital+Limited">x</a>'
    assert play_developer(html2) == "x"
    md = "[Acme Loans Pvt Ltd](https://play.google.com/store/apps/developer?id=Acme)"
    assert play_developer(md) == "Acme Loans Pvt Ltd"


def test_sensitive_data():
    assert sensitive_data_types("Data safety\nPersonal info\nContacts\nPhotos and videos") == ["contacts", "photos"]
    assert sensitive_data_types("Data safety\nLocation\nFinancial info") == []


def test_names_match():
    assert names_match("Quickrupee Fintech Private Limited", "QuickRupee")
    assert names_match("SafeKosh Capital Limited", "SafeKosh Finance")
    assert not names_match("Qrovix Tech Solutions", "QuickRupee")
    assert not names_match("Velqora Agro Traders Private Limited", "Bullvanta Signals")
