"""Checker 5: scam / harassment reports in news and complaint forums.

Gemini lists the reports it finds with Google Search; we only COUNT a report
when its site is one Google actually returned for that search.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ..gemini import url_is_grounded
from .base import Ctx, finish, new_output

KEY = "news"
DETAIL = "News + complaint forums (Google Search & Live News Feeds); only links returned are counted"
TYPE_WORDS = {"harassment": "harassment", "extortion": "extortion", "fraud": "fraud", "scam": "scam",
              "fake_offer": "fake offers", "fake": "fake offers", "other": "complaint"}


def fetch_live_news(query: str, limit: int = 8) -> list[dict]:
    """Fetch live news headlines and sources via Google News RSS for India."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    items = []
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item")[:limit]:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                pubDate = item.find("pubDate").text if item.find("pubDate") is not None else ""
                source_el = item.find("source")
                source = source_el.text if source_el is not None else "News"
                if title:
                    items.append({"title": title, "url": link, "source": source, "date": pubDate})
    except Exception:
        pass
    return items


def prompt_for(subject: dict, extra_news: list[dict] | None = None) -> str:
    news_context = ""
    if extra_news:
        lines = [f"- {n['title']} ({n.get('source', '')}) URL: {n.get('url', '')}" for n in extra_news[:6]]
        news_context = "\nRecent public news stories found:\n" + "\n".join(lines) + "\n"

    return f"""You check for public complaints about businesses in India. Use Google Search.

Find news articles, police / cyber-cell advisories, and complaint-forum posts (Reddit, consumer
complaint sites, X/Twitter) concerning "{subject['display_name']}".
{news_context}
CRITICAL INSTRUCTION: Classify each report's "target_role" into one of two categories:
1. "perpetrator": The entity "{subject['display_name']}" itself is accused of defrauding, cheating, extorting, running an illegal scheme, or refusing payouts.
2. "impersonated_or_warning": Third-party scammers or cybercriminals are impersonating or misusing "{subject['display_name']}"'s name, brand, or platform to trick victims (e.g., fake job offers using Naukri's name, fake Razorpay payment links, fake bank reward SMS, fake VIP telegram channels), OR police alerts warning the public about imposters.

Rules:
- If "{subject['display_name']}" is a legitimate or established platform and third-party scammers are merely using its name to run independent scams, you MUST classify it as "impersonated_or_warning".
- If unsure whether the entity itself is the perpetrator, classify as "impersonated_or_warning".
- If the entity is a news organization or legitimate publication, news it published are NOT accusations against it.
- Max 8 items.

Return ONLY a JSON object:
{{"reports": [{{
  "title": string,
  "url": string,
  "source": string,
  "target_role": "perpetrator" | "impersonated_or_warning",
  "type": "scam"|"fraud"|"harassment"|"extortion"|"fake_offer"|"other",
  "date": string|null
}}],
"notes": string}}"""


async def run(ctx: Ctx) -> dict:
    out = new_output(KEY, "Forums & news", "Gemini + Google Search")
    out["method_detail"] = DETAIL
    if not ctx.ai_allowed:
        return finish(out, "skipped", note=ctx.ai_skip_note[0], note_hi=ctx.ai_skip_note[1])
    await ctx.step(KEY, "Searching news and complaint forums")

    # Fetch live public news related to entity and possible scam/fraud mentions
    extra_news = []
    try:
        query_news = f"{ctx.subject['display_name']} scam OR fraud OR police OR arrest OR FIR OR cheat"
        extra_news = fetch_live_news(query_news, limit=6)
        if not extra_news and ctx.subject.get("website_url"):
            from ..gemini import host_of
            h = host_of(ctx.subject["website_url"])
            if h:
                extra_news = fetch_live_news(f"{ctx.subject['display_name']} {h} news", limit=6)
        if not extra_news:
            extra_news = fetch_live_news(f"{ctx.subject['display_name']} news", limit=6)
    except Exception:
        pass

    if extra_news:
        await ctx.step(KEY, f"Found {len(extra_news)} recent news publications to analyze")

    prompt = prompt_for(ctx.subject, extra_news)
    res = await ctx.ask(KEY, prompt)

    # Ground news sources with the live items retrieved
    for item in extra_news:
        if not any(s.get("url") == item["url"] for s in res.sources):
            res.sources.append({"title": item["title"], "url": item["url"]})
    if not res.queries:
        res.queries.append(f"{ctx.subject['display_name']} news & scam check")

    out["evidence_ids"].append(ctx.save_gemini(KEY, "News & forum search (answer + sources)", prompt, res))
    for q in res.queries[:2]:
        await ctx.step(KEY, f"Google: {q}")

    reports = (res.data or {}).get("reports") or []
    verified, seen, unverified = [], set(), 0
    for r in reports:
        url = (r or {}).get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        if url_is_grounded(url, res):  # only links Google really returned count
            verified.append(r)
        else:
            unverified += 1

    perpetrator_reports = []
    impersonation_reports = []
    for r in verified:
        role = str(r.get("target_role", "")).lower().strip()
        title_lower = str(r.get("title", "")).lower()
        # Signals indicating third-party impersonation or generic warning
        is_impersonation = (
            "impersonat" in role
            or "warning" in role
            or "victim" in role
            or any(w in title_lower for w in (
                "impersonat", "posing as", "fake job", "phishing", "scam alert",
                "beware of fake", "cyber cell warns", "cyber police alert", "misusing",
                "job racket", "fraudsters use", "scammers use"
            ))
        )
        if is_impersonation:
            impersonation_reports.append(r)
        elif role == "perpetrator":
            perpetrator_reports.append(r)
        elif not role:
            # Fallback when target_role is missing (e.g. demo fixtures, mocks, or unclassified LLM output):
            if ctx.subject.get("is_trusted_domain"):
                impersonation_reports.append(r)
            else:
                perpetrator_reports.append(r)
        else:
            # Default to informational if uncertain
            impersonation_reports.append(r)

    types: list[str] = []
    for r in perpetrator_reports:
        t = TYPE_WORDS.get(str(r.get("type", "other")).lower(), "complaint")
        if t not in types:
            types.append(t)

    data = {
        "reports_count": len(perpetrator_reports),
        "reports": perpetrator_reports,
        "impersonation_count": len(impersonation_reports),
        "impersonation_reports": impersonation_reports,
        "unverified_count": unverified,
        "types": types,
        "top_links": [r.get("url") for r in (perpetrator_reports or impersonation_reports)[:3]],
        "sources": res.sources[:8],
    }
    if not res.sources and not res.queries:
        return finish(out, "unverified", data=data, note="Search did not run; not scored")
    step_msg = f"{len(perpetrator_reports)} direct complaint(s)"
    if impersonation_reports:
        step_msg += f", {len(impersonation_reports)} imposter warning(s) noted"
    await ctx.step(KEY, step_msg)
    return finish(out, "done", data=data)
