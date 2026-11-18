"""Replay checks stored in data/nexverify.db through the current scoring engine.

Uses the saved results of real checks (what each source returned at the time),
re-applies today's rules, and compares the answer with what the item really is.

    python tools/replay_checks.py [path/to/nexverify.db]

Older saved results came from earlier agent versions. To compare fairly, the
replay applies the current agents' evidence rules to the stored data:
news reports count only when Google returned their site, and "not found"
from RBI / SEBI / company searches counts only when the search returned sources.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import proofgrid  # noqa: E402
from app.gemini import host_of  # noqa: E402

# What each tested input really is. legit = real business, scam = fraud or banned,
# unverifiable = made-up / unknown names that no source can confirm.
TRUTH = {
    "cybercrime.gov.in": "legit", "chitkara.edu.in": "legit", "hdfcbank.com": "legit", "flipkart.com": "legit",
    "smallcase.com": "legit", "moneyview.in": "legit", "zerodha.com": "legit", "irctc.co.in": "legit", "myjar.app": "legit",
    "naukri.com": "legit", "razorpay.com": "legit", "uidai.gov.in": "legit", "groww.in": "legit", "https://groww.in/": "legit",
    "https://sbi.bank.in": "legit", "https://sbi.bank.in/": "legit", "https://onlinesbi.sbi.bank.in/": "legit",
    "https://www.bitpay.com/buy-crypto": "legit", "https://www.slideegg.com/powerpoint": "legit-unknown", "https://xhamster.com/": "legit-unknown",
    "sbi-rewards-claim.in": "scam", "pmkisan-yojana-apk.in": "scam", "kbc-lucky-draw-winner.in": "scam", "tatamotors-bonus-share.in": "scam",
    "incometax-refund-claim.in": "scam", "Amazon work from home, pay 999 registration fee": "scam",
    "Aarav Capital VIP stock tips WhatsApp group": "scam", "Urgent Rupee loan app 50000 1 minute": "scam", "https://bankingsbi.co.in/": "scam",
    "https://amazon-career-offer.example": "scam", "https://1win-uz.eu.com/": "scam", "https://1-win.tr/": "scam",
    "FastCash Pro instant loan app": "unverifiable", "xk7-qpl-trade.in": "unverifiable", "Velocitrix Global Solutions": "unverifiable",
    "QuickEarn Plus": "unverifiable", "bluestone-decor-studios.in": "unverifiable", "kavya-decor-studios.in": "unverifiable",
    "Sunrise Retail Ventures Pvt Ltd": "unverifiable", "nextstep-finserve.com": "unverifiable", "https://smboclub.pro/": "unverifiable",
    "https://omegal.app/": "unverifiable", "https://rupeeq.com/personal-loan": "unverifiable",
}
GREEN = {"VERIFIED_OFFICIAL", "LOW_RISK"}
WARN = {"HIGH_RISK", "SUSPICIOUS", "CAUTION"}


def _grounded(url: str, sources: list[dict]) -> bool:
    h = host_of(url or "")
    if not h:
        return False
    for s in sources or []:
        if h in (s.get("title") or "").lower() or h == host_of(s.get("url") or ""):
            return True
    return False


def adapt(outputs: dict) -> dict:
    """Apply today's evidence rules to outputs saved by older agent versions."""
    out = json.loads(json.dumps(outputs))
    news = out.get("news") or {}
    nd = news.get("data") or {}
    if news.get("status") == "done":
        if not nd.get("sources"):
            news["status"] = "unverified"
        else:
            reps = [r for r in nd.get("reports") or [] if _grounded(r.get("url"), nd.get("sources"))
                    and str(r.get("target_role", "perpetrator")).lower().startswith("perp")]
            nd["reports"], nd["reports_count"] = reps, len(reps)
    for k in ("rbi", "sebi"):
        o = out.get(k) or {}
        d = o.get("data") or {}
        if o.get("status") == "done" and d.get("found") is False and not d.get("sources"):
            o["status"] = "unverified"
    comp = out.get("company") or {}
    c = (comp.get("data") or {}).get("company") or {}
    if c.get("found") is False and not c.get("sources"):
        c["found"] = None
    return out


def main(db: str, quiet: bool = False) -> dict:
    con = sqlite3.connect(db)
    rows = con.execute("select query, created_at, verdict, score, result_json from checks where demo=0 order by created_at").fetchall()
    tally = {"old": {}, "new": {}}
    lines = []
    for q, at, old_v, old_s, rj in rows:
        truth = TRUTH.get(q.strip())
        if not truth:
            continue
        r = json.loads(rj)
        subject = dict(r["subject"])
        subject.setdefault("query", q)
        outputs = adapt(r.get("agents") or {})
        hits = proofgrid.evaluate(subject, outputs)
        score, verdict = proofgrid.score_and_verdict(hits, subject, outputs)
        new_v = verdict["code"]
        for tag, v in (("old", old_v), ("new", new_v)):
            if truth == "legit":
                ok, danger = v in GREEN, v == "HIGH_RISK"
            elif truth == "legit-unknown":
                ok, danger = v in GREEN | {"UNKNOWN", "COULDNT_VERIFY"}, v == "HIGH_RISK"
            elif truth == "scam":
                ok, danger = v in WARN, v in GREEN
            else:  # unverifiable: anything but a green answer is right
                ok, danger = v not in GREEN, v in GREEN
            t = tally[tag].setdefault(truth, {"n": 0, "ok": 0, "danger": 0})
            t["n"] += 1
            t["ok"] += ok
            t["danger"] += danger
        lines.append(f"{at[5:16]}  {q[:44]:44} {truth:13} old {old_v[:10]:10} {old_s:3} -> new {new_v[:10]:10} {score:3}  {', '.join(h.rule_id for h in hits)[:70]}")
    if quiet:
        return tally
    print("\n".join(lines))
    for tag in ("old", "new"):
        tot = sum(v["n"] for v in tally[tag].values())
        ok = sum(v["ok"] for v in tally[tag].values())
        dg = sum(v["danger"] for v in tally[tag].values())
        print(f"\n{tag.upper()} engine: {ok}/{tot} correct ({100 * ok / max(1, tot):.1f}%), dangerous mistakes {dg}")
        for k, v in sorted(tally[tag].items()):
            print(f"   {k:14} {v['ok']}/{v['n']} correct, {v['danger']} dangerous")
    return tally


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data" / "nexverify.db"))
