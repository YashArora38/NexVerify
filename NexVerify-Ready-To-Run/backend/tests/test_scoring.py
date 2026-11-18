"""The demo cases run the whole pipeline (fixtures in, real rules out)."""
import pytest

from app.orchestrator import start_check, wait_result
from app.proofgrid import Hit, score_of, verdict_of


async def _run(q):
    run = await start_check(q, fresh=True)
    res = await wait_result(run, 30)
    assert res, run.events[-3:]
    return res


async def test_quickrupee_matches_mockup():
    r = await _run("QuickRupee - Instant Loan App")
    assert r["score"] == 0
    assert r["verdict"]["code"] == "HIGH_RISK"
    cards = {c["key"]: c for c in r["cards"]}
    assert (cards["rbi"]["label"], cards["rbi"]["penalty"]) == ("NOT FOUND", -45)
    assert (cards["sebi"]["label"], cards["sebi"]["penalty"]) == ("SKIPPED", 0)
    assert (cards["company"]["label"], cards["company"]["penalty"]) == ("NEW DOMAIN", -40)
    assert (cards["listing"]["label"], cards["listing"]["penalty"]) == ("UNENCRYPTED DATA", -90)
    assert any(h["rule_id"] == "INSECURE_SENSITIVE_FORM" and h["evidence_ids"] for h in r["hits"])
    assert cards["listing"]["detail_en"] == "UNENCRYPTED DATA, publisher mismatch, asks for contacts"
    assert (cards["news"]["label"], cards["news"]["penalty"]) == ("REPORTS", -70)
    assert "Already paid? Call 1930." in r["summary"]["en"]
    # score = 100 - every penalty, exactly
    assert r["score"] == max(0, 100 - sum(h["penalty"] for h in r["hits"]))
    # the made-up blog link was not in Google's sources, so it was not counted
    assert r["agents"]["news"]["data"]["unverified_count"] == 1


async def test_telegram_tips_all_contradictions_fire():
    r = await _run("Bullvanta Signals")
    ids = {h["rule_id"] for h in r["hits"]}
    assert {"AGE_CONTRADICTION", "CIN_MISMATCH", "SEBI_FAKE_CLAIM"} <= ids
    assert r["score"] == 0


async def test_fake_internship_is_caution():
    r = await _run("Hirevexa Internships")
    # asking for a fee before a job is the scam itself
    assert "UPFRONT_FEE" in {h["rule_id"] for h in r["hits"]}
    assert r["verdict"]["code"] == "HIGH_RISK"


async def test_clean_app_scores_100():
    r = await _run("SafeKosh Finance")
    assert r["score"] == 100
    assert r["hits"] == []
    assert r["verdict"]["code"] == "LOW_RISK"  # RBI-listed lender, but not an official-domain proof


async def test_evidence_is_sealed():
    import hashlib
    from app import config

    r = await _run("QuickRupee")
    assert r["evidence"]
    for e in r["evidence"]:
        data = (config.EVIDENCE_DIR / r["check_id"] / e["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e["sha256"]
    # every penalty points at evidence
    assert all(h["evidence_ids"] for h in r["hits"])


async def test_cache_returns_same_check():
    a = await _run("SafeKosh Finance")
    run = await start_check("safekosh finance")
    b = await wait_result(run, 5)
    assert b["check_id"] == a["check_id"]


def _h(rule, p):
    return Hit(rule, "x", p, "red", "", "", "", "", "", "", "")


@pytest.mark.parametrize("pens,score", [([40, 50, 50], 0), ([40, 20, 12, 10], 18), ([], 100), ([30, 5], 65), ([100], 0)])
def test_score_rule(pens, score):
    assert score_of([_h("R", p) for p in pens]) == score


def test_verdict_bands():
    # risk = 100 - score: >=70 Don't pay, 55-69 Suspicious, 31-54 Be careful
    assert verdict_of(30)["code"] == "HIGH_RISK"
    assert verdict_of(31)["code"] == "SUSPICIOUS"
    assert verdict_of(45)["code"] == "SUSPICIOUS"
    assert verdict_of(46)["code"] == "CAUTION"
    assert verdict_of(69)["code"] == "CAUTION"
    assert verdict_of(70)["code"] == "LOW_RISK"


def test_no_proof_means_unknown_not_safe():
    from app.proofgrid import score_and_verdict
    subject = {"query": "Some New Shop", "display_name": "Some New Shop", "category": "company/service"}
    score, v = score_and_verdict([], subject, {})
    assert v["code"] == "UNKNOWN" and score == 50
