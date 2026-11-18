"""Checker 1: is this lending app in RBI's Digital Lending Apps directory / NBFC records?"""
from __future__ import annotations

from .base import Ctx, as_bool, finish, new_output

KEY = "rbi"
METHOD = "Gemini + Google Search"
DETAIL = "RBI Digital Lending Apps directory + NBFC records (Google Search via Gemini)"


def prompt_for(subject: dict, claims: dict) -> str:
    alt = [x for x in (subject.get("legal_name"), claims.get("nbfc_partner")) if x]
    return f"""You verify loan apps for Indian users. Use Google Search.

Question: Is the mobile lending app "{subject['display_name']}" listed in the Reserve Bank of India's
public directory of Digital Lending Apps (rbi.org.in -> Citizen's Corner -> "DLAs deployed by Regulated
Entities"), or officially linked to an RBI-registered NBFC or bank?
{('Related names to check: ' + ', '.join(alt)) if alt else ''}

Rules:
- Prefer rbi.org.in and the lender's own official site. Ignore ads and app-review blogs.
- Do not guess. If you cannot find clear evidence that it is listed, set "found" to false.

Return ONLY a JSON object:
{{"found": true|false, "app_name": string|null, "entity": string|null, "reg_no": string|null,
  "status": string|null, "evidence_url": string|null, "notes": string}}"""


async def run(ctx: Ctx) -> dict:
    out = new_output(KEY, "RBI NBFC & DLA list", METHOD)
    out["method_detail"] = DETAIL
    s = ctx.subject
    claims: dict = {}
    if s.get("category") not in ("lending", "loan app"):
        claims = await ctx.wait_for_claims(12)
        if not claims.get("rbi_claim") and not claims.get("nbfc_partner"):
            return finish(out, "skipped", note="Not a lending app, RBI check skipped",
                          note_hi="लोन ऐप नहीं है, RBI जाँच छोड़ी गई")
    if not ctx.ai_allowed:
        return finish(out, "skipped", note=ctx.ai_skip_note[0], note_hi=ctx.ai_skip_note[1])
    await ctx.step(KEY, "Searching RBI's Digital Lending Apps directory")
    prompt = prompt_for(s, claims or ctx.claims)
    res = await ctx.ask(KEY, prompt)
    out["evidence_ids"].append(ctx.save_gemini(KEY, "RBI lookup (Google Search answer + sources)", prompt, res))
    for q in res.queries[:2]:
        await ctx.step(KEY, f"Google: {q}")
    d = res.data or {}
    found = as_bool(d.get("found"))
    data = {"found": found, "app_name": d.get("app_name"), "entity": d.get("entity"),
            "reg_no": d.get("reg_no"), "status": d.get("status"), "evidence_url": d.get("evidence_url"),
            "notes": d.get("notes"), "sources": res.sources[:6]}

    if found is None:
        return finish(out, "unverified", data=data, note="No clear answer; not scored")
    if found and not res.sources:
        return finish(out, "unverified", data=data, note="Listed, but no source could be confirmed; not scored")
    if found is False and not res.sources:
        return finish(out, "unverified", data=data, note="Search returned no sources; not scored")
    await ctx.step(KEY, f"Listed by {data['entity']}" if found else "No regulated lender lists this app")
    return finish(out, "done", data=data)
