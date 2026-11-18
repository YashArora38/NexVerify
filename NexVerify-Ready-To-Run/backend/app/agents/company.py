"""Checker 3: company registry (CIN, incorporation date, status) + domain age (RDAP)."""
from __future__ import annotations

from datetime import date

from ..claims import names_match
from ..web import registrable_domain
from .base import Ctx, as_bool, finish, new_output

KEY = "company"
DETAIL = "MCA records via public mirrors (Google Search via Gemini) + RDAP domain age"


def prompt_for(cin: str | None, name: str) -> str:
    target = f'the CIN "{cin}"' if cin else f'the company "{name}"'
    return f"""You look up Indian company registry (MCA) records. Use Google Search.

Find the official MCA record for {target}. Public MCA mirrors such as ZaubaCorp, Tofler,
The Company Check or Falcon Ebiz are fine. {"Report whichever company this CIN actually belongs to, even if the name is different." if cin else ""}

Do not guess. If no record is found, set "found" to false.

Return ONLY a JSON object:
{{"found": true|false, "cin": string|null, "company_name": string|null,
  "incorporated_on": "YYYY-MM-DD"|null, "status": string|null, "evidence_url": string|null, "notes": string}}"""


def _age_days(iso: str | None) -> int | None:
    try:
        return (date.today() - date.fromisoformat(str(iso)[:10])).days
    except Exception:
        return None


async def run(ctx: Ctx) -> dict:
    out = new_output(KEY, "Company registry & WHOIS", "Gemini + Google Search, RDAP")
    out["method_detail"] = DETAIL
    s = ctx.subject
    claims = await ctx.wait_for_claims(20)

    # --- domain age (RDAP, no key) ---------------------------------------
    domain = {"ok": False}
    site = s.get("website_url")
    if site:
        dom = registrable_domain(site)
        await ctx.step(KEY, f"RDAP: when was {dom} registered?")
        rd = await ctx.rdap(dom)
        raw = rd.pop("raw", None)
        domain = rd
        item = ctx.evidence.add(KEY, "rdap", f"RDAP record for {dom}", rd.get("source_url"),
                                {"summary": rd, "rdap_response": raw}, simulated=ctx.demo is not None)
        out["evidence_ids"].append(item["id"])
        if rd.get("ok"):
            await ctx.step(KEY, f"{dom} registered on {rd['registered_on']} ({rd['age_days']} days ago)")

    # --- company registry -------------------------------------------------
    cin = (claims.get("cins") or [None])[0]
    candidates = [n for n in (s.get("legal_name"), *(claims.get("legal_names") or [])) if n]
    # Prefer the legal name that matches the brand (not, say, its NBFC partner).
    name = next((n for n in candidates if names_match(n, s.get("display_name"))),
                candidates[0] if candidates else s.get("display_name"))
    if not ctx.ai_allowed:
        data = {"company": {"found": None, "searched_for": None, "notes": ctx.ai_skip_note[0]}, "domain": domain, "company_age_days": None}
        if domain.get("ok"):
            return finish(out, "done", data=data)
        return finish(out, "skipped", data=data, note=ctx.ai_skip_note[0], note_hi=ctx.ai_skip_note[1])
    await ctx.step(KEY, f"Looking up CIN {cin}" if cin else f"Looking up company records for {name}")
    prompt = prompt_for(cin, name)
    try:
        res = await ctx.ask(KEY, prompt)
        out["evidence_ids"].append(ctx.save_gemini(KEY, "Company registry lookup (Google Search answer + sources)", prompt, res))
        d = res.data or {}
        company = {"found": as_bool(d.get("found")), "cin": d.get("cin"), "company_name": d.get("company_name"),
                   "incorporated_on": d.get("incorporated_on"), "status": d.get("status"),
                   "evidence_url": d.get("evidence_url"), "notes": d.get("notes"), "sources": res.sources[:6],
                   "searched_for": cin or name}
    except Exception as exc:
        company = {"found": None, "cin": None, "company_name": None, "notes": f"Registry check unavailable: {exc}", "searched_for": cin or name}
        res = None
    MCA_HOSTS = {"zaubacorp.com", "tofler.in", "thecompanycheck.com", "mca.gov.in", "instafinancials.com", "falconebiz.com"}
    has_mca_source = bool(res and any(any(h in f"{src.get('url', '')} {src.get('title', '')}".lower() for h in MCA_HOSTS) for src in res.sources))
    if company["found"] and not has_mca_source:
        company["found"] = None  # Ungrounded model guess -> cannot verify without registry source
    if company["found"] is False and not (res and res.sources):
        company["found"] = None  # "not found" only counts when Google actually returned pages
    company_age = None
    if company["found"]:
        # Searched by name? Only trust the record if it is clearly the same company.
        same = bool(cin) or any(names_match(company["company_name"], n)
                                for n in (s.get("display_name"), s.get("legal_name"), *(claims.get("legal_names") or [])) if n)
        if same:
            company_age = _age_days(company["incorporated_on"])
            await ctx.step(KEY, f"{company['company_name']}: incorporated {company['incorporated_on']}, {company['status']}")
        else:
            company["found"] = None
            company["notes"] = (company.get("notes") or "") + " (different company name; ignored)"
    elif company["found"] is False:
        await ctx.step(KEY, "No company record found")

    data = {"company": company, "domain": domain, "company_age_days": company_age}
    if not domain.get("ok") and company["found"] is None:
        return finish(out, "unverified", data=data, note="No registry or domain data; not scored")
    return finish(out, "done", data=data)
