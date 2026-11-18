"""Runs one check end to end and streams every step to the browser."""
from __future__ import annotations

import asyncio
import secrets
import time

from . import config, demo, explain, proofgrid, provenance, resolver, store
from .agents import AGENTS
from .agents.base import Ctx, finish, new_output
from .evidence import EvidenceStore, utc_now
from .gemini import GeminiQuotaError
from .proofgrid import (
    AGENT_ORDER,
    AGENT_TITLES,
    RULES,
    build_score_breakdown,
    cards_of,
    evaluate,
    score_and_verdict,
    score_of,
)


class CheckRun:
    def __init__(self, check_id: str, query: str):
        self.id = check_id
        self.query = query
        self.events: list[tuple[str, dict]] = []
        self.cond = asyncio.Condition()
        self.done = False
        self.result: dict | None = None
        self.created = time.time()

    async def emit(self, event: str, data: dict) -> None:
        async with self.cond:
            self.events.append((event, data))
            self.cond.notify_all()

    async def close(self) -> None:
        async with self.cond:
            self.done = True
            self.cond.notify_all()


RUNS: dict[str, CheckRun] = {}
_TASKS: set[asyncio.Task] = set()  # keep references so running checks are not garbage-collected


def _new_id() -> str:
    return "nv" + secrets.token_hex(6)


def _gc() -> None:
    cutoff = time.time() - 3600
    for k in [k for k, r in RUNS.items() if r.done and r.created < cutoff]:
        RUNS.pop(k, None)


async def start_check(query: str, fresh: bool = False) -> CheckRun:
    _gc()
    query = query.strip()[:200]
    norm = resolver.normalize(query)
    if not fresh:
        cached_id = store.cache.get(norm)
        cached = store.load_result(cached_id) if cached_id else None
        if cached and cached.get("engine") == "proofgrid-3":
            run = CheckRun(cached["check_id"], query)
            RUNS[run.id] = run
            await _replay(run, cached)
            return run
    run = CheckRun(_new_id(), query)
    RUNS[run.id] = run
    task = asyncio.create_task(_execute(run, norm))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return run


async def _replay(run: CheckRun, result: dict) -> None:
    run.result = result
    await run.emit("status", {"message": "Saved result from the last 24 hours (instant)", "cached": True})
    await run.emit("subject", {"subject": result["subject"], "demo": result["demo"]})
    for key in AGENT_ORDER:
        out = result["agents"].get(key) or {}
        await run.emit("agent", {"key": key, "state": out.get("status", "skipped"), "step": "From cache",
                                 "title": out.get("title") or AGENT_TITLES[key], "method": out.get("method", "")})
    await run.emit("cards", {"cards": result["cards"], "score": result["score"]})
    await run.emit("result", {**result, "cached": True})
    await run.close()


def _public(out: dict) -> dict:
    return {k: v for k, v in out.items() if not k.startswith("_")}


def _ai_gate(subject: dict) -> tuple[bool, tuple[str, str]]:
    """Decide whether the Gemini lookups are worth the quota for this link."""
    rep = proofgrid.link_report(subject)
    ident = None if rep.ugc else rep.identity
    if ident and rep.risk < proofgrid.CAUT:
        name = ident.get("name") or "the official"
        return False, (f"Not needed: the address itself proves this is {name if ident.get('name') else 'an official'} site",
                       f"ज़रूरत नहीं: पता खुद साबित करता है कि यह {name if ident.get('name') else 'आधिकारिक'} साइट है")
    if rep.risk >= proofgrid.HIGH and rep.is_link:
        return False, ("Not needed: the link already shows strong signs of a scam", "ज़रूरत नहीं: लिंक में पहले से स्कैम के पक्के संकेत हैं")
    return True, ("", "")


async def _execute(run: CheckRun, norm: str) -> None:
    t0 = time.monotonic()
    started = utc_now()
    try:
        scenario = demo.build(run.query)
        evidence = EvidenceStore(run.id)
        await run.emit("status", {"message": "Reading the link and finding the real name, app and website"})
        ai_ok, ai_note = True, ("", "")
        if scenario is not None:
            await asyncio.sleep(0.6 / max(config.DEMO_SPEED, 0.05))
            subject = dict(scenario.subject)
            subject["demo"] = True
        else:
            pre_ok, _ = _ai_gate({"query": run.query})
            use_ai = config.live_enabled() and pre_ok
            subject, ev = await resolver.resolve(run.query, run.emit, use_ai=use_ai)
            subject["demo"] = False
            if ev:
                evidence.add("resolver", "search", "Name lookup (Google Search answer + sources)", None, ev)
            ai_ok, ai_note = _ai_gate(subject)
            ai_ok = ai_ok and config.live_enabled()
            if not config.live_enabled() and ai_note == ("", ""):
                ai_note = ("Needs a Gemini key (GEMINI_API_KEY); not checked", "Gemini key चाहिए; जाँच नहीं हुई")
        await run.emit("subject", {"subject": subject, "demo": scenario is not None})
        await run.emit("status", {"message": "Running 5 checks at the same time"})

        ctx = Ctx(check_id=run.id, subject=subject, evidence=evidence, emit=run.emit, demo=scenario,
                  ai_allowed=ai_ok, ai_skip_note=ai_note)
        for key in AGENT_ORDER:
            await run.emit("agent", {"key": key, "state": "queued", "title": AGENT_TITLES[key]})

        async def run_one(key: str):
            fn = AGENTS[key]
            await run.emit("agent", {"key": key, "state": "running", "step": "Starting"})
            try:
                out = await asyncio.wait_for(fn(ctx), timeout=config.CHECK_TIMEOUT_SECONDS + 30)
            except asyncio.TimeoutError:
                out = finish(new_output(key, AGENT_TITLES[key], ""), "unverified",
                             note="Took too long; not scored (partial score from the others)")
            except GeminiQuotaError:
                out = finish(new_output(key, AGENT_TITLES[key], ""), "unverified",
                             note="Gemini's free quota is used up for now; not scored",
                             note_hi="Gemini का मुफ़्त कोटा अभी ख़त्म है; स्कोर में नहीं गिना")
            except Exception as exc:  # one broken source must not break the check
                out = finish(new_output(key, AGENT_TITLES[key], ""), "error",
                             note=f"Could not check ({type(exc).__name__}); not scored")
                out["data"] = {"error": str(exc)[:300]}
            finally:
                if key == "listing":
                    ctx.claims_ready.set()
            await _store(key, out)

        async def _store(key: str, out: dict) -> None:
            out = _public(out)
            ctx.outputs[key] = out
            hits = evaluate(subject, ctx.outputs)
            await run.emit("agent", {"key": key, "state": out["status"], "title": out.get("title"),
                                     "method": out.get("method", ""), "note": out.get("note", ""),
                                     "duration_ms": out.get("duration_ms")})
            await run.emit("cards", {"cards": cards_of(subject, ctx.outputs, hits), "score": score_of(hits, subject, ctx.outputs)})

        from urllib.parse import urlparse
        from .passive import run_passive_checks

        passive_task = None
        if scenario is None:
            raw_url = subject.get("website_url") or (run.query if run.query.startswith("http") else "")
            target_host = urlparse(raw_url).hostname or (proofgrid.link_report(subject).parsed.get("host") or "")
            if target_host:
                passive_task = asyncio.create_task(run_passive_checks(raw_url or f"https://{target_host}/", target_host))

        tasks = {k: asyncio.create_task(run_one(k)) for k in AGENT_ORDER}
        deadline = config.CHECK_DEADLINE_SECONDS if scenario is None else 120
        done, pending = await asyncio.wait(tasks.values(), timeout=deadline)
        for key, task in tasks.items():
            if task in pending:
                task.cancel()
                if key == "listing":
                    ctx.claims_ready.set()
                await _store(key, finish(new_output(key, AGENT_TITLES[key], ""), "unverified",
                                         note="Took too long; not scored (partial score from the others)",
                                         note_hi="बहुत समय लगा; स्कोर में नहीं गिना"))

        if passive_task is not None:
            try:
                passive_results = await asyncio.wait_for(passive_task, timeout=10.0)
            except Exception:
                passive_results = {}
            ctx.outputs["passive"] = {"status": "done", "data": passive_results}

        hits = evaluate(subject, ctx.outputs)
        checked = sum(1 for k in AGENT_ORDER if ctx.outputs.get(k, {}).get("status") in ("done", "skipped"))
        score, verdict = score_and_verdict(hits, subject, ctx.outputs, checked=checked, is_demo=scenario is not None)
        breakdown, confidence, trust_strip = build_score_breakdown(subject, ctx.outputs, hits, score, verdict)
        cards = cards_of(subject, ctx.outputs, hits)
        await run.emit("status", {"message": "Writing the verdict in Hindi and English"})
        summary = await explain.summarize(subject, score, verdict, hits, use_ai=scenario is None and config.AI_SUMMARY and ai_ok, outputs=ctx.outputs)
        manifest = evidence.manifest()
        unverified = [k for k in AGENT_ORDER if ctx.outputs.get(k, {}).get("status") in ("unverified", "error")]
        listing_data = (ctx.outputs.get("listing") or {}).get("data", {})
        human_needed = bool(listing_data.get("human_assist_needed") or (ctx.outputs.get("listing") or {}).get("status") in ("unverified", "error")) \
            and verdict["code"] not in ("VERIFIED_OFFICIAL", "LOW_RISK", "HIGH_RISK")
        result = {
            "check_id": run.id,
            "query": run.query,
            "norm_query": norm,
            "demo": scenario is not None,
            "subject": subject,
            "started_at": started,
            "finished_at": utc_now(),
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "agents": ctx.outputs,
            "link": proofgrid.link_report(subject, ctx.outputs).to_dict(),
            "hits": [h.to_dict() for h in hits],
            "cards": cards,
            "score": score,
            "total_penalty": sum(h.penalty for h in hits),
            "verdict": verdict,
            "summary": summary,
            "score_breakdown": breakdown,
            "confidence": confidence,
            "trust_strip": trust_strip,
            "flag_count": store.get_flag_count(run.id, norm),
            "human_assist_needed": human_needed,
            "human_assisted": bool(subject.get("human_assisted")),
            "partial": bool(unverified),
            "unverified": unverified,
            "complaint_text": explain.complaint_text(subject, score, verdict, hits,
                                                     manifest["manifest_sha256"], started),
            "evidence": evidence.items,
            "manifest_sha256": manifest["manifest_sha256"],
            "rules": {k: {"penalty": v[0], "label": v[1], "description": v[2]} for k, v in RULES.items()},
            "investigation": listing_data.get("payment_intel") or {},
            "engine": "proofgrid-3",
        }
        result["integrity"] = await asyncio.to_thread(provenance.record_revision, result)
        store.save_result(result)
        store.cache.set(norm, run.id)
        run.result = result
        await run.emit("result", result)
    except Exception as exc:
        await run.emit("error", {"message": f"Something went wrong: {type(exc).__name__}: {str(exc)[:200]}"})
    finally:
        await run.close()


async def wait_result(run: CheckRun, timeout: float = 90) -> dict | None:
    deadline = time.monotonic() + timeout
    async with run.cond:
        while not run.done:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                await asyncio.wait_for(run.cond.wait(), timeout=left)
            except asyncio.TimeoutError:
                break
    return run.result
