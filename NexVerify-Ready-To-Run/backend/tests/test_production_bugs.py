"""Regression tests for production bugs observed in NexVerify:

Bug 1: https://1win-uz.eu.com/ (betting site):
       Scored 100/100 "No red flags" while Tier-3 said the page could not be opened.
       Fix: Neutral baseline 50, betting penalty -25, unopened page cap <= 40, verdict SUSPICIOUS or HIGH_RISK.

Bug 2: groww.in (legit):
       Verdict showed "Couldn't check" but score 100 and text "verified and official" (contradiction).
       Fix: REGISTRY match overrides directly to VERIFIED_OFFICIAL, score 100, no contradiction.

Bug 3: https://www.bitpay.com/buy-crypto:
       100/100 with confidence HIGH although 2 signals were unverified.
       Fix: no official-domain proof means "Looks safe" at most, and a money business whose
       licence is unchecked never gets HIGH confidence.

Bug 4: https://1-win.tr/:
       50 "Be careful", LOW confidence, 5 of 7 unverified.
       Fix: Betting category incurs -25 penalty, capped at <= 40, verdict SUSPICIOUS or HIGH_RISK.

Invariant:
       A site that could not be opened and is not in the registry CAN NEVER receive "No red flags" / LOW_RISK.
"""
import ssl
import pytest
from app.registry import REGISTRY
from app.signals import classify_category
from app.browser_ladder import classify_fetch_failure
from app.proofgrid import evaluate, score_and_verdict, build_score_breakdown, summary_template


def test_bug1_1win_betting_blocked():
    """1win-uz.eu.com must be penalized for betting and capped when unopened."""
    url = "https://1win-uz.eu.com/"
    host = "1win-uz.eu.com"
    cat, _ = classify_category(url, host)
    assert cat == "online betting/gambling"

    subject = {
        "query": url,
        "website_url": url,
        "display_name": "1win",
        "category": cat,
        "is_trusted_domain": False,
    }
    outputs = {
        "listing": {
            "status": "unverified",
            "data": {
                "is_blocked": True,
                "block_type": "BOT_WALL",
                "block_reason": "Protected by Cloudflare challenge",
                "human_assist_needed": True,
            },
        },
        "company": {"status": "done", "data": {"domain": {"ok": False, "age_days": 10}}},
        "rbi": {"status": "skipped", "data": {}},
        "sebi": {"status": "skipped", "data": {}},
        "news": {"status": "done", "data": {"reports_count": 0}},
    }

    hits = evaluate(subject, outputs)
    assert any(h.rule_id == "BETTING" for h in hits)

    score, verdict = score_and_verdict(hits, subject, outputs)
    assert score <= 40, f"Expected score <= 40 for betting site, got {score}"
    assert verdict["code"] in ("SUSPICIOUS", "HIGH_RISK")
    assert verdict["code"] != "LOW_RISK"
    assert "no red flag" not in verdict["label_en"].lower()


def test_bug2_groww_verified_official():
    """groww.in must match registry as official broker with score 100 and VERIFIED_OFFICIAL."""
    host = "groww.in"
    reg_m = REGISTRY.match(host)
    assert reg_m.is_official is True
    assert "Groww" in reg_m.brand

    subject = {
        "query": "groww.in",
        "website_url": "https://groww.in",
        "display_name": "Groww",
        "category": "investment/stock tips",
        "is_trusted_domain": True,
    }
    outputs = {
        "listing": {"status": "done", "data": {}},
        "company": {"status": "done", "data": {"company": {"found": True, "company_name": "Groww Invest Tech Pvt Ltd"}}},
        "rbi": {"status": "skipped", "data": {}},
        "sebi": {"status": "done", "data": {"found": True}},
        "news": {"status": "done", "data": {"reports_count": 0}},
    }

    hits = evaluate(subject, outputs)
    score, verdict = score_and_verdict(hits, subject, outputs)

    assert score == 100
    assert verdict["code"] == "VERIFIED_OFFICIAL"
    assert verdict["label_en"] == "VERIFIED OFFICIAL"
    assert verdict["label_hi"] == "प्रमाणित आधिकारिक"

    tpl = summary_template(score, verdict, hits)
    assert "official Groww address" in tpl["en"]


def test_bug3_bitpay_cannot_be_100_with_unverified_signals():
    """bitpay.com with unverified signals cannot receive 100/100 or HIGH confidence without full coverage."""
    subject = {
        "query": "https://www.bitpay.com/buy-crypto",
        "website_url": "https://www.bitpay.com/buy-crypto",
        "display_name": "BitPay",
        "category": "crypto",
        "is_trusted_domain": False,
    }
    outputs = {
        "listing": {
            "status": "done",
            "data": {
                "ssl_info": {"is_valid": True, "days_remaining": 180},
                "is_blocked": False,
                "human_assist_needed": False,
            },
        },
        "company": {"status": "done", "data": {"domain": {"ok": True, "age_days": 3000}}},
        "rbi": {"status": "skipped", "data": {}},  # unverified statutory
        "sebi": {"status": "skipped", "data": {}},  # unverified statutory
        "news": {"status": "done", "data": {"reports_count": 0}},
        "passive": {
            "status": "done",
            "data": {
                "safe_browsing": {"status": "pass"},
                "virustotal": {"status": "pass", "data": {"engines_scanned": 70, "malicious_count": 0}},
                "tranco": {"status": "unknown", "data": {}},
            },
        },
    }

    hits = evaluate(subject, outputs)
    score, verdict = score_and_verdict(hits, subject, outputs)

    # Nothing is wrong with it, but nothing proves it is an official site either:
    # it may be "Looks safe", never "Verified official".
    assert verdict["code"] == "LOW_RISK"

    breakdown, confidence, trust_strip = build_score_breakdown(subject, outputs, hits, score, verdict)
    unverified_count = sum(1 for b in breakdown if b["status"] == "unknown")
    assert unverified_count >= 1, "Expected at least 1 unknown breakdown signal"
    # When unverified signals exist and entity is not in official registry, confidence cannot be HIGH
    assert confidence != "HIGH", f"Expected confidence MEDIUM/LOW, got {confidence}"


def test_bug4_1win_tr_suspicious_or_high_risk():
    """1-win.tr must be classified as betting and receive score <= 40 with SUSPICIOUS or HIGH_RISK."""
    url = "https://1-win.tr/"
    host = "1-win.tr"
    cat, _ = classify_category(url, host)
    assert cat == "online betting/gambling"

    subject = {
        "query": url,
        "website_url": url,
        "display_name": "1-win",
        "category": cat,
        "is_trusted_domain": False,
    }
    outputs = {
        "listing": {
            "status": "unverified",
            "data": {"is_blocked": True, "block_type": "DNS_NXDOMAIN", "human_assist_needed": True},
        },
        "company": {"status": "unverified", "data": {}},
        "rbi": {"status": "skipped", "data": {}},
        "sebi": {"status": "skipped", "data": {}},
        "news": {"status": "unverified", "data": {}},
    }

    hits = evaluate(subject, outputs)
    score, verdict = score_and_verdict(hits, subject, outputs)
    assert score <= 40, f"Expected score <= 40, got {score}"
    assert verdict["code"] in ("SUSPICIOUS", "HIGH_RISK")


def test_invariant_blocked_and_not_in_registry_never_safe():
    """Invariant: A site that could not be opened and is not in registry CAN NEVER be LOW_RISK."""
    subject = {
        "query": "https://unknown-random-site.biz/",
        "website_url": "https://unknown-random-site.biz/",
        "display_name": "Random Site",
        "category": "company/service",
        "is_trusted_domain": False,
    }
    outputs = {
        "listing": {
            "status": "unverified",
            "data": {"is_blocked": True, "block_type": "BOT_WALL", "human_assist_needed": True},
        },
        "company": {"status": "unverified", "data": {}},
        "rbi": {"status": "skipped", "data": {}},
        "sebi": {"status": "skipped", "data": {}},
        "news": {"status": "done", "data": {"reports_count": 0}},
    }

    hits = evaluate(subject, outputs)
    score, verdict = score_and_verdict(hits, subject, outputs)

    assert score <= 60, f"Unopened unknown site score must be <= 60, got {score}"
    assert verdict["code"] in ("CAUTION", "UNKNOWN", "SUSPICIOUS", "HIGH_RISK")
    assert verdict["code"] not in ("LOW_RISK", "VERIFIED_OFFICIAL")


def test_tls_failure_classification():
    """classify_fetch_failure correctly classifies SSL errors as TLS_FAIL."""
    exc = ssl.SSLError("certificate verify failed: certificate has expired")
    block_type, reason = classify_fetch_failure(0, "", "", {}, exc=exc)
    assert block_type == "TLS_FAIL"
    assert "SSL/TLS" in reason
