"""Checker 2: is this adviser / tips channel really SEBI registered?"""
from __future__ import annotations

from .base import Ctx, as_bool, finish, new_output

KEY = "sebi"
METHOD = "Gemini + Google Search"
DETAIL = "SEBI intermediary lists (Investment Advisers / Research Analysts) via Google Search"
SEBI_IA_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=13"


def prompt_for(subject: dict, claims: dict) -> str:
    nums = ", ".join(claims.get("sebi_numbers") or []) or "none given"
    return f"""You verify SEBI registered market intermediaries in India. Use Google Search.

Question: Is "{subject['display_name']}" (registration number: {nums}) an officially registered
SEBI intermediary in India? (e.g. Stock Broker INZ..., Investment Adviser INA..., Research Analyst INH...,
Depository Participant IN-DP..., Portfolio Manager INP..., or Mutual Fund).

Rules:
- Search sebi.gov.in official directories or recognized stock exchange member directories (NSE, BSE, MCX).
- If the registration number starts with INZ (Stock Broker), INA (Investment Adviser), INH (Research Analyst), or IN-DP (Depository Participant) and belongs to this business or its corporate operating entity, set "found" to true.
- Do not guess. If you cannot find clear evidence, set "found" to false.

Return ONLY a JSON object:
{{"found": true|false, "name": string|null, "reg_no": string|null, "category": string|null,
  "valid_till": string|null, "evidence_url": string|null, "notes": string}}"""


async def run(ctx: Ctx) -> dict:
    out = new_output(KEY, "SEBI portal", METHOD)
    out["method_detail"] = DETAIL
    s = ctx.subject
    claims = await ctx.wait_for_claims(10)
    if s.get("category") not in ("investment", "investment/stock tips") and not claims.get("sebi_claim"):
        why = {"lending": ("Lending app, adviser check skipped", "लोन ऐप है, SEBI जाँच छोड़ी गई"),
               "job": ("Job offer, adviser check skipped", "नौकरी का ऑफ़र है, SEBI जाँच छोड़ी गई")}
        note, note_hi = why.get(s.get("category"), ("No investment claims, check skipped", "निवेश का दावा नहीं, जाँच छोड़ी गई"))
        return finish(out, "skipped", note=note, note_hi=note_hi)

    if not ctx.ai_allowed:
        return finish(out, "skipped", note=ctx.ai_skip_note[0], note_hi=ctx.ai_skip_note[1])
    await ctx.step(KEY, "Searching SEBI's registered advisers and analysts")
    prompt = prompt_for(s, claims)
    res = await ctx.ask(KEY, prompt)
    out["evidence_ids"].append(ctx.save_gemini(KEY, "SEBI lookup (Google Search answer + sources)", prompt, res))
    for q in res.queries[:2]:
        await ctx.step(KEY, f"Google: {q}")
    d = res.data or {}
    found = as_bool(d.get("found"))
    data = {"found": found, "name": d.get("name"), "reg_no": d.get("reg_no"), "category": d.get("category"),
            "valid_till": d.get("valid_till"), "evidence_url": d.get("evidence_url"), "notes": d.get("notes"),
            "claimed_numbers": claims.get("sebi_numbers") or [], "sources": res.sources[:6]}
    if found is None:
        return finish(out, "unverified", data=data, note="No clear answer; not scored")
    if found and not res.sources:
        return finish(out, "unverified", data=data, note="Registered, but no source could be confirmed; not scored")
    if found is False and not res.sources:
        return finish(out, "unverified", data=data, note="Search returned no sources; not scored")
    await ctx.step(KEY, f"Registered: {data['reg_no']}" if found else "0 results for the name or number")
    return finish(out, "done", data=data)
