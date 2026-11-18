"""Turn the fixed verdict into plain Hindi / English, and draft the 1930 complaint.

Gemini only rewrites. If its text contains any number that is not in the
facts we gave it, we throw it away and use the template instead.
"""
from __future__ import annotations

import json
import re

from .gemini import get_client
from .proofgrid import Hit, summary_template

PROMPT = """You write short, simple warnings for ordinary people in India.

Here are the FACTS from an automated check. The score and verdict are final; do not change them.
{facts}

Write two versions of a 1-2 sentence summary for the user:
- "en": very simple English (class 8 level)
- "hi": very simple Hindi in Devanagari
Mention the 1-2 most serious problems in plain words. If the verdict is HIGH_RISK, end with
"Already paid? Call 1930." / "पैसे भेज चुके हैं? तुरंत 1930 पर कॉल करें।".
Do not add any fact, number or name that is not in FACTS. Do not mention the score.

Return ONLY JSON: {{"en": string, "hi": string}}"""


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+", s or ""))


async def summarize(subject: dict, score: int, verdict: dict, hits: list[Hit], use_ai: bool, outputs: dict | None = None) -> dict:
    tpl = summary_template(score, verdict, hits, subject, outputs)
    client = get_client()
    if not use_ai or not client.enabled or verdict["code"] in ("UNKNOWN", "VERIFIED_OFFICIAL", "LOW_RISK"):
        return {**tpl, "source": "template"}
    facts = {"name": subject.get("display_name"), "verdict": verdict["code"],
             "problems": [{"what_they_claim": h.claim, "what_records_show": h.found} for h in
                          sorted(hits, key=lambda h: -h.penalty)[:4]]}
    facts_json = json.dumps(facts, ensure_ascii=False)
    try:
        res = await client.generate(PROMPT.format(facts=facts_json), json_mode=True, timeout=25)
        d = res.data or {}
        en, hi = str(d.get("en") or "").strip(), str(d.get("hi") or "").strip()
        allowed = _numbers(facts_json) | {"1930"}
        if not en or not hi or len(en) > 400 or len(hi) > 500:
            raise ValueError("bad length")
        if (_numbers(en) | _numbers(hi)) - allowed:
            raise ValueError("new numbers")

        # Consistency guard: Never allow AI summary to claim "safe" or "no red flags" if verdict is not LOW_RISK
        if verdict["code"] != "LOW_RISK":
            en_l = en.lower()
            if any(w in en_l for w in ("no red flag", "looks safe", "is safe", "legitimate", "trustworthy", "no danger")) \
               or any(w in hi for w in ("कोई ख़तरे", "कोई ख़तरा", "सुरक्षित")):
                return {**tpl, "source": "template"}
        return {"en": en, "hi": hi, "source": "gemini"}
    except Exception:
        return {**tpl, "source": "template"}


def complaint_text(subject: dict, score: int, verdict: dict, hits: list[Hit], manifest_sha: str,
                   checked_at: str) -> str:
    links = [subject.get(k) for k in ("website_url", "play_url", "app_store_url", "telegram_url") if subject.get(k)]
    lines = [
        "DRAFT ONLY - review facts, complete blanks and submit yourself. No complaint or FIR has been filed.",
        "SIMULATED DEMO - do not submit as a real allegation." if subject.get("demo") else "Automated observations are leads for review, not proof of a crime.",
        "Category: Suspected online incident (select the appropriate category on the portal)",
        f"Suspect name / app / channel: {subject.get('display_name')}",
    ]
    if links:
        lines.append("Links: " + ", ".join(links))
    lines += [
        "",
        "Description:",
        f"I want to report “{subject.get('display_name')}” for review of the concerns listed below. "
        f"An automated public-records check (NexVerify, {checked_at} UTC) rated it {score}/100 "
        f"({verdict['label_en']}) for these reasons:",
    ]
    for i, h in enumerate(sorted(hits, key=lambda h: -h.penalty), 1):
        found = h.found.rstrip(".")
        if h.claim and h.claim not in ("A trustworthy business", "A normal, safe link") and not h.claim.startswith("Official site ("):
            lines.append(f"  {i}. They claim: {h.claim}. Records show: {found}.")
        else:
            lines.append(f"  {i}. {found}.")
    lines += [
        "",
        "Evidence: Attach the NexVerify evidence PDF if you choose (files hashed with SHA-256;",
        f"manifest hash {manifest_sha}).",
        "",
        "What happened to me (facts and timeline): ______________________",
        "Contact details (enter only on the official portal): ______________________",
        "Money lost (if any): Rs. ________   Date: __________",
        "Paid to (UPI ID / account / wallet): ______________________",
        "Transaction ID / UTR: ______________________",
        "",
        "Financial loss: call 1930 promptly and contact your bank. Portal: https://cybercrime.gov.in",
        "Suspicious link without victim loss: https://cybercrime.gov.in/webform/cyber_suspect.aspx",
        "Submission requires your review and portal authentication. Save the acknowledgement; complaint is not an automatic FIR.",
    ]
    return "\n".join(lines)
