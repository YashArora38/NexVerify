"""NexVerify API (FastAPI).

    POST /api/check                 {"query": "QuickRupee"}  -> {"check_id": ...}
    GET  /api/check/{id}/stream     live Server-Sent Events (each step of each checker)
    GET  /api/check/{id}            final result JSON
    GET  /api/check/{id}/report.pdf evidence PDF
    GET  /api/evidence/{id}/{file}  one sealed evidence file
    POST /api/whatsapp              Twilio-style WhatsApp webhook (text in -> verdict out)
"""
from __future__ import annotations

import asyncio
import copy
import csv
import io
import json
import re
import uuid
from xml.sax.saxutils import escape

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import blockchain, config, demo, explain, provenance, store, web
from .evidence import EvidenceStore, evidence_path
from .orchestrator import RUNS, start_check, wait_result
from .proofgrid import RULES
from .report_pdf import build_batch_pdf, build_pdf
from .security import claim_resource, filter_recent, install_security

app = FastAPI(title="NexVerify API", version="0.2.0",
              docs_url=None if config.PRODUCTION else "/docs",
              redoc_url=None if config.PRODUCTION else "/redoc")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Last-Event-ID"],
                   allow_credentials=True)
install_security(app)

ID_RE = re.compile(r"^nv[0-9a-f]{12}$")
_MUTATION_LOCK = asyncio.Lock()


class CheckIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    fresh: bool = False  # true = ignore the 24h cache


class FlagIn(BaseModel):
    reason: str = Field(min_length=2, max_length=100)
    comment: str = Field(default="", max_length=500)


class HumanAssistIn(BaseModel):
    pasted_text: str = Field(default="", max_length=10000)
    actual_url: str = Field(default="", max_length=300)
    answers: dict = Field(default_factory=dict)
    consent: bool = False
    screenshot_base64: str = Field(default="", max_length=1400000)


class BatchIn(BaseModel):
    inputs: str | list[str] = Field(max_length=20000)
    fresh: bool = False


# In-memory store for active batch runs
BATCH_RUNS: dict[str, dict] = {}
BATCH_CONDS: dict[str, asyncio.Condition] = {}


@app.get("/api/health")
def health():
    return {"ok": True, "live": config.live_enabled(), "gemini_model": config.GEMINI_MODEL,
            "db": store.db_kind(), "cache": store.cache.kind, "demo_names": demo.DEMO_NAMES,
            "screenshots": config.ENABLE_SCREENSHOTS}


@app.get("/api/rules")
def rules():
    return [{"id": k, "penalty": v[0], "label": v[1], "description": v[2]} for k, v in RULES.items()]


@app.get("/api/recent")
def recent(request: Request):
    return filter_recent(request, store.recent(100))[:10]


@app.post("/api/check")
async def create_check(body: CheckIn, request: Request):
    # Shared cache results can contain another person's assisted evidence.
    private = config.PRODUCTION or bool(getattr(request.state, "user", None))
    run = await start_check(body.query, fresh=body.fresh or private)
    claim_resource(request, run.id)
    return {"check_id": run.id, "stream_url": f"/api/check/{run.id}/stream"}


def _sse(event: str, data: dict, idx: int | None = None) -> str:
    head = f"id: {idx}\n" if idx is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.get("/api/check/{check_id}/stream")
async def stream(check_id: str, request: Request):
    if not ID_RE.match(check_id):
        raise HTTPException(404, "unknown check")
    run = RUNS.get(check_id)
    if run is None:
        saved = store.load_result(check_id)
        if not saved:
            raise HTTPException(404, "unknown check")

        async def once():
            yield _sse("result", saved)
            yield _sse("end", {})
        return StreamingResponse(once(), media_type="text/event-stream")

    # Browser reconnects send Last-Event-ID: resume after it instead of replaying.
    try:
        start = int(request.headers.get("last-event-id", "-1")) + 1
    except ValueError:
        start = 0

    async def gen():
        i = max(0, start)
        while True:
            async with run.cond:
                while i >= len(run.events) and not run.done:
                    try:
                        await asyncio.wait_for(run.cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                batch = run.events[i:]
                done = run.done
            if not batch and not done:
                yield ": ping\n\n"  # keep the connection open
                continue
            for n, (ev, data) in enumerate(batch):
                yield _sse(ev, data, i + n)
            i += len(batch)
            if done and i >= len(run.events):
                yield _sse("end", {})
                return

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _result_or_404(check_id: str) -> dict:
    if not ID_RE.match(check_id):
        raise HTTPException(404, "unknown check")
    run = RUNS.get(check_id)
    if run and run.result:
        return run.result
    saved = store.load_result(check_id)
    if not saved:
        raise HTTPException(404, "not finished or unknown")
    return saved


@app.get("/api/check/{check_id}")
def get_check(check_id: str):
    return _result_or_404(check_id)


def _revision_or_404(check_id: str, revision: int | None = None) -> dict:
    _result_or_404(check_id)
    try:
        return provenance.load_revision(check_id, revision)
    except FileNotFoundError:
        raise HTTPException(404, "No versioned bundle exists; run a fresh check")
    except ValueError:
        raise HTTPException(400, "Invalid revision")


def _anchor_config(record: dict | None = None, check_id: str | None = None) -> dict:
    saved = store.get_anchor(check_id) if check_id else None
    cfg = {
        "status": (saved.get("status") if saved else ("not_prepared" if config.ANCHOR_PREPARATION_ENABLED else "disabled")),
        "chain_id": config.ANCHOR_CHAIN_ID,
        "contract_address": config.ANCHOR_CONTRACT,
        "rpc_configured": bool(config.ANCHOR_RPC_URL),
        "broadcast_enabled": False,
        "anchored": (saved.get("status") == "VERIFIED_ON_CHAIN") if saved else False,
        "receipt_verification": "supported",
        "saved_anchor": saved,
    }
    if config.ANCHOR_PREPARATION_ENABLED and record and record.get("commitment"):
        try:
            prepared = blockchain.prepare_anchor(
                "0x" + record["commitment"],
                config.ANCHOR_CHAIN_ID,
                config.ANCHOR_CONTRACT,
                consent=True,
                simulated=bool((record.get("result") or {}).get("demo")),
            )
            cfg["prepared"] = prepared
            if not saved or saved.get("status") in ("PREPARED", "not_prepared"):
                cfg["status"] = "prepared"
            cfg["commitment"] = "0x" + record["commitment"]
        except Exception:
            pass
    return cfg


@app.get("/api/check/{check_id}/integrity")
@app.get("/api/check/{check_id}/provenance")
def get_integrity(check_id: str):
    result = _result_or_404(check_id)
    try:
        record = provenance.load_revision(check_id)
    except FileNotFoundError:
        return {"integrity": None, "history": [], "graph": None, "anchor": _anchor_config(check_id=check_id)}
    return {"integrity": result.get("integrity"), "history": provenance.get_history(check_id),
            "graph": record["graph"], "anchor": _anchor_config(record, check_id=check_id)}


@app.get("/api/check/{check_id}/verify")
def verify_integrity(check_id: str, revision: int | None = None):
    _revision_or_404(check_id, revision)
    return provenance.verify_revision(check_id, revision)


@app.get("/api/check/{check_id}/ledger")
def get_ledger(check_id: str):
    _result_or_404(check_id)
    return {"history": provenance.get_history(check_id)}


@app.get("/api/check/{check_id}/bundle.zip")
@app.get("/api/check/{check_id}/evidence.zip")
def offline_bundle(check_id: str, revision: int | None = None):
    record = _revision_or_404(check_id, revision)
    if not provenance.verify_revision(check_id, revision)["ok"]:
        raise HTTPException(409, "Evidence integrity failed; export refused")
    path = provenance.export_bundle(check_id, revision)
    return FileResponse(path, media_type="application/zip",
                        filename=f"NexVerify_{check_id}_r{record['revision']}.zip",
                        headers={"Cache-Control": "private, no-store"})


class AnchorIn(BaseModel):
    consent: bool = False
    revision: int | None = Field(default=None, ge=1)


class VerifyTxIn(BaseModel):
    tx_hash: str = Field(min_length=66, max_length=66)
    revision: int | None = Field(default=None, ge=1)


@app.post("/api/check/{check_id}/anchor/prepare")
@app.post("/api/check/{check_id}/anchor")
def prepare_blockchain_anchor(check_id: str, body: AnchorIn):
    if not config.ANCHOR_PREPARATION_ENABLED:
        raise HTTPException(403, "Anchor preparation is disabled by the operator")
    record = _revision_or_404(check_id, body.revision)
    if not provenance.verify_revision(check_id, body.revision)["ok"]:
        raise HTTPException(409, "Evidence integrity failed; anchor preparation refused")
    try:
        prep = blockchain.prepare_anchor("0x" + record["commitment"], config.ANCHOR_CHAIN_ID,
                                         config.ANCHOR_CONTRACT, consent=body.consent,
                                         simulated=bool(record["result"].get("demo")))
        # Persist prepared record in store
        store.save_anchor({
            "check_id": check_id,
            "revision_id": record["revision"],
            "commitment": "0x" + record["commitment"],
            "chain_id": config.ANCHOR_CHAIN_ID,
            "contract_address": config.ANCHOR_CONTRACT,
            "status": "PREPARED",
        })
        return prep
    except blockchain.AnchorPreparationError as error:
        raise HTTPException(400, str(error))


@app.get("/api/check/{check_id}/anchor/status")
@app.get("/api/check/{check_id}/anchor")
def get_blockchain_anchor_status(check_id: str, revision: int | None = None):
    _result_or_404(check_id)
    anchor = store.get_anchor(check_id, revision)
    return {
        "check_id": check_id,
        "revision": revision or 1,
        "chain_id": config.ANCHOR_CHAIN_ID,
        "contract_address": config.ANCHOR_CONTRACT,
        "rpc_configured": bool(config.ANCHOR_RPC_URL),
        "anchor": anchor or {"status": "NOT_ANCHORED"},
    }


@app.get("/api/check/{check_id}/anchor/eligibility")
def get_blockchain_anchor_eligibility(check_id: str, revision: int | None = None):
    _result_or_404(check_id)
    record = _revision_or_404(check_id, revision)
    ver = provenance.verify_revision(check_id, revision)
    if not ver.get("ok"):
        return {
            "eligible": False,
            "reason": "Local evidence integrity verification failed; cannot anchor invalid evidence",
            "errors": ver.get("errors", []),
        }
    commitment = "0x" + record["commitment"]
    saved = store.get_anchor(check_id, revision)
    if saved and saved.get("status") == "VERIFIED_ON_CHAIN":
        return {
            "eligible": False,
            "already_anchored": True,
            "commitment": commitment,
            "chain_id": config.ANCHOR_CHAIN_ID,
            "contract_address": config.ANCHOR_CONTRACT,
            "status": saved["status"],
            "tx_hash": saved.get("tx_hash"),
            "reason": "This evidence revision is already verified on-chain",
        }
    return {
        "eligible": True,
        "commitment": commitment,
        "chain_id": config.ANCHOR_CHAIN_ID,
        "contract_address": config.ANCHOR_CONTRACT,
        "status": saved.get("status") if saved else "PREPARED",
    }


@app.post("/api/check/{check_id}/anchor/verify")
async def verify_blockchain_anchor(check_id: str, body: VerifyTxIn, request: Request):
    _result_or_404(check_id)
    record = _revision_or_404(check_id, body.revision)
    rev_num = record["revision"]

    if not provenance.verify_revision(check_id, rev_num)["ok"]:
        raise HTTPException(409, "Evidence integrity failed; on-chain verification refused")

    expected_commitment = "0x" + record["commitment"]
    rpc_url = config.ANCHOR_RPC_URL
    if not rpc_url:
        raise HTTPException(
            503,
            "No Ethereum RPC endpoint is configured on the server (NEXVERIFY_ANCHOR_RPC_URL is unset). "
            "Configure a Sepolia RPC endpoint to enable on-chain verification."
        )

    # Anti-replay check
    existing_by_tx = store.get_anchor_by_tx(body.tx_hash)
    if existing_by_tx and existing_by_tx.get("check_id") != check_id:
        raise HTTPException(
            409,
            f"Transaction {body.tx_hash} has already been registered to another investigation ({existing_by_tx.get('check_id')})"
        )

    store.save_anchor({
        "check_id": check_id,
        "revision_id": rev_num,
        "commitment": expected_commitment,
        "chain_id": config.ANCHOR_CHAIN_ID,
        "contract_address": config.ANCHOR_CONTRACT,
        "tx_hash": body.tx_hash,
        "status": "SUBMITTED",
    })

    try:
        verification = await blockchain.verify_on_chain_transaction(
            tx_hash=body.tx_hash,
            expected_contract=config.ANCHOR_CONTRACT,
            expected_commitment=expected_commitment,
            rpc_url=rpc_url,
            expected_chain_id=config.ANCHOR_CHAIN_ID,
            min_confirmations=config.ANCHOR_MIN_CONFIRMATIONS,
        )
    except blockchain.TransactionVerificationError as err:
        store.save_anchor({
            "check_id": check_id,
            "revision_id": rev_num,
            "commitment": expected_commitment,
            "chain_id": config.ANCHOR_CHAIN_ID,
            "contract_address": config.ANCHOR_CONTRACT,
            "tx_hash": body.tx_hash,
            "status": "FAILED",
            "error_details": str(err),
        })
        raise HTTPException(400, f"Transaction verification failed: {err}")
    except Exception as err:
        raise HTTPException(502, f"Failed communicating with Ethereum RPC: {err}")

    updated = store.save_anchor({
        "check_id": check_id,
        "revision_id": rev_num,
        "commitment": expected_commitment,
        "chain_id": verification["chain_id"],
        "contract_address": verification["contract_address"],
        "publisher": verification.get("publisher"),
        "tx_hash": verification["tx_hash"],
        "block_number": verification.get("block_number"),
        "block_timestamp": verification.get("block_timestamp"),
        "confirmations": verification.get("confirmations", 0),
        "status": verification["status"],
        "verified_at": verification.get("verified_at"),
    })

    return {
        "success": True,
        "verified": verification["verified"],
        "status": verification["status"],
        "record": updated,
        "verification": verification,
    }


@app.post("/api/check/{check_id}/anchor/reverify")
async def reverify_blockchain_anchor(check_id: str, revision: int | None = None):
    _result_or_404(check_id)
    saved = store.get_anchor(check_id, revision)
    if not saved or not saved.get("tx_hash"):
        raise HTTPException(404, "No blockchain transaction recorded for this investigation")

    record = _revision_or_404(check_id, revision)
    expected_commitment = "0x" + record["commitment"]
    rpc_url = config.ANCHOR_RPC_URL
    if not rpc_url:
        raise HTTPException(503, "No Ethereum RPC endpoint is configured on the server")

    try:
        verification = await blockchain.verify_on_chain_transaction(
            tx_hash=saved["tx_hash"],
            expected_contract=saved["contract_address"],
            expected_commitment=expected_commitment,
            rpc_url=rpc_url,
            expected_chain_id=saved["chain_id"],
            min_confirmations=config.ANCHOR_MIN_CONFIRMATIONS,
        )
        updated = store.save_anchor({
            "check_id": check_id,
            "revision_id": saved["revision_id"],
            "commitment": expected_commitment,
            "chain_id": verification["chain_id"],
            "contract_address": verification["contract_address"],
            "publisher": verification.get("publisher"),
            "tx_hash": verification["tx_hash"],
            "block_number": verification.get("block_number"),
            "block_timestamp": verification.get("block_timestamp"),
            "confirmations": verification.get("confirmations", 0),
            "status": verification["status"],
            "verified_at": verification.get("verified_at"),
        })
        return {"success": True, "record": updated, "verification": verification}
    except Exception as err:
        raise HTTPException(400, f"Re-verification error: {err}")


@app.get("/api/check/{check_id}/report.txt")
def text_report(check_id: str):
    from .report_text import build_text_report
    result = _result_or_404(check_id)
    return PlainTextResponse(build_text_report(result), headers={"Content-Disposition": f'attachment; filename="NexVerify_{check_id}.txt"', "Cache-Control": "private, no-store"})


@app.get("/api/check/{check_id}/report.pdf")
def report(check_id: str):
    result = _result_or_404(check_id)
    path = build_pdf(result)
    slug = result["subject"].get("slug", "check")
    return FileResponse(path, media_type="application/pdf", filename=f"NexVerify_{slug}_{check_id}.pdf")


def _save_revision_result(result: dict, actor: str, reason: str) -> None:
    result["integrity"] = provenance.record_revision(result, actor=actor, reason=reason)
    store.save_result(result)
    if result["check_id"] in RUNS:
        RUNS[result["check_id"]].result = result


@app.post("/api/check/{check_id}/flag")
async def flag_check(check_id: str, body: FlagIn, request: Request):
    async with _MUTATION_LOCK:
        res = copy.deepcopy(_result_or_404(check_id))
        count = store.add_flag(check_id, res.get("query", ""), body.reason, body.comment)
        res["flag_count"] = count
        actor = str((getattr(request.state, "user", None) or {}).get("openId") or "anonymous-user")
        _save_revision_result(res, actor, "user dispute recorded; verdict unchanged")
    return {"ok": True, "check_id": check_id, "flag_count": count}


@app.post("/api/check/{check_id}/human-assist")
async def human_assist(check_id: str, body: HumanAssistIn, request: Request):
    """Retain minimized user assertions; never promote them to official confirmation."""
    from .claims import extract_claims
    from .privacy import minimize_answers, minimize_text
    from .proofgrid import evaluate, score_and_verdict, build_score_breakdown, cards_of
    if not body.consent:
        raise HTTPException(400, "Consent to retain submitted evidence is required")
    if body.screenshot_base64:
        # The old UI has no upload control. Fail explicitly rather than silently ignoring a file.
        raise HTTPException(400, "Screenshot upload is not enabled; submit bounded text evidence")
    try:
        answers = minimize_answers(body.answers)
    except ValueError as error:
        raise HTTPException(400, str(error))
    pasted_text = minimize_text(body.pasted_text)
    async with _MUTATION_LOCK:
        res = copy.deepcopy(_result_or_404(check_id))
        subject, outputs = res["subject"], res["agents"]
        url = body.actual_url or subject.get("website_url") or subject.get("query") or ""
        page = web.build_human_assist_page(url=url, pasted_text=pasted_text, answers=answers)
        locker = EvidenceStore(check_id)
        item = locker.add("listing", "human_assertion", "User-submitted text (minimized; unverified)", url,
                          {"text": pasted_text, "answers": answers, "source_url": url,
                           "user_asserted": True, "personal_data_minimization": "best-effort-v1"},
                          simulated=bool(res.get("demo")))
        claims = extract_claims(page.text).to_dict()
        listing = outputs.setdefault("listing", {"key": "listing", "evidence_ids": []})
        listing["status"] = "done"
        listing.setdefault("data", {}).update({"human_assisted": True, "text": page.text,
                                                "claims": claims, "human_assist_needed": False,
                                                "evidence_state": "user_asserted"})
        listing.setdefault("evidence_ids", []).append(item["id"])
        listing["note"] = "User assertion retained; not an independently verified official source"
        subject["human_assisted"] = True
        subject["human_answers"] = answers
        hits = evaluate(subject, outputs)
        checked = sum(1 for out in outputs.values() if out.get("status") in ("done", "skipped"))
        score, verdict = score_and_verdict(hits, subject, outputs, checked=checked, is_demo=bool(res.get("demo")))
        breakdown, confidence, trust_strip = build_score_breakdown(subject, outputs, hits, score, verdict)
        manifest = locker.manifest()
        res.update(score=score, verdict=verdict, hits=[h.to_dict() for h in hits],
                   cards=cards_of(subject, outputs, hits), score_breakdown=breakdown,
                   confidence=confidence, trust_strip=trust_strip, total_penalty=sum(h.penalty for h in hits),
                   human_assisted=True, human_assist_needed=False, evidence=locker.items,
                   manifest_sha256=manifest["manifest_sha256"])
        res["summary"] = await explain.summarize(subject, score, verdict, hits, use_ai=False)
        res["complaint_text"] = explain.complaint_text(subject, score, verdict, hits,
                                                       manifest["manifest_sha256"], res["started_at"])
        actor = str((getattr(request.state, "user", None) or {}).get("openId") or "anonymous-user")
        _save_revision_result(res, actor, "consented minimized human evidence; decision recomputed")
        # Do not share user submissions through the global query cache.
        store.cache.clear()
    return res


# ---------------------------------------------------------------------------
# Multi-URL Batch Verification Engine
# ---------------------------------------------------------------------------
def _parse_batch_inputs(raw: str | list[str]) -> list[str]:
    lines = []
    if isinstance(raw, list):
        for item in raw:
            lines.extend(str(item).splitlines())
    else:
        # Split on newlines, commas, or semicolons
        lines = re.split(r"[\r\n,;]+", raw)

    cleaned = []
    seen = set()
    for ln in lines:
        c = ln.strip()
        if len(c) >= 2 and c.lower() not in seen:
            seen.add(c.lower())
            cleaned.append(c)
    return cleaned[:100]  # Cap at 100 per batch


async def _process_batch(batch_id: str, inputs: list[str], fresh: bool, request: Request):
    sem = asyncio.Semaphore(5)  # Concurrency limit of 5
    batch = BATCH_RUNS[batch_id]
    cond = BATCH_CONDS[batch_id]

    async def _check_one(inp: str):
        async with sem:
            try:
                run = await start_check(inp, fresh=fresh)
                claim_resource(request, run.id)
                res = await wait_result(run, timeout=50)
                if not res:
                    res = {
                        "check_id": run.id,
                        "query": inp,
                        "score": 50,
                        "verdict": {
                            "code": "COULDNT_VERIFY",
                            "color": "amber",
                            "label_en": "COULD NOT VERIFY: TIMEOUT",
                            "label_hi": "सत्यापित नहीं कर सके: समय सीमा समाप्त",
                        },
                        "confidence": "LOW",
                        "hits": [],
                        "summary": {"en": "Check timed out. Please try again.", "hi": "जाँच का समय समाप्त हो गया। कृपया पुनः प्रयास करें।"},
                    }
            except Exception as e:
                res = {
                    "check_id": f"err_{uuid.uuid4().hex[:8]}",
                    "query": inp,
                    "score": 50,
                    "verdict": {
                        "code": "COULDNT_VERIFY",
                        "color": "amber",
                        "label_en": "COULD NOT VERIFY: ERROR",
                        "label_hi": "त्रुटि: पुष्टि नहीं हो सकी",
                    },
                    "confidence": "LOW",
                    "hits": [],
                    "summary": {"en": "Verification failed; no completed result is available.", "hi": "जाँच के दौरान त्रुटि।"},
                }

            async with cond:
                batch["items"].append(res)
                batch["completed"] += 1
                cond.notify_all()

    tasks = [_check_one(inp) for inp in inputs]
    await asyncio.gather(*tasks, return_exceptions=True)

    async with cond:
        batch["done"] = True
        cond.notify_all()


@app.post("/api/check/batch")
async def create_batch(body: BatchIn, request: Request):
    inputs = _parse_batch_inputs(body.inputs)
    if not inputs:
        raise HTTPException(400, "No valid URLs or names found in batch input")
    if any(len(item) > 200 for item in inputs):
        raise HTTPException(400, "Each batch input must be at most 200 characters")

    batch_id = f"batch_{uuid.uuid4().hex[:10]}"
    cond = asyncio.Condition()
    BATCH_RUNS[batch_id] = {
        "batch_id": batch_id,
        "total": len(inputs),
        "completed": 0,
        "items": [],
        "done": False,
        "inputs": inputs,
        "fresh": body.fresh,
    }
    BATCH_CONDS[batch_id] = cond

    claim_resource(request, batch_id)
    private = config.PRODUCTION or bool(getattr(request.state, "user", None))
    asyncio.create_task(_process_batch(batch_id, inputs, body.fresh or private, request))
    return {
        "batch_id": batch_id,
        "total": len(inputs),
        "stream_url": f"/api/check/batch/{batch_id}/stream",
    }


@app.get("/api/check/batch/{batch_id}")
def get_batch(batch_id: str):
    batch = BATCH_RUNS.get(batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found or expired")
    return batch


@app.get("/api/check/batch/{batch_id}/stream")
async def stream_batch(batch_id: str):
    batch = BATCH_RUNS.get(batch_id)
    cond = BATCH_CONDS.get(batch_id)
    if not batch or not cond:
        raise HTTPException(404, "Batch not found")

    async def gen():
        i = 0
        while True:
            async with cond:
                while i >= len(batch["items"]) and not batch["done"]:
                    try:
                        await asyncio.wait_for(cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                new_items = batch["items"][i:]
                is_done = batch["done"]

            for it in new_items:
                yield _sse("item", it, i)
                i += 1

            if is_done and i >= len(batch["items"]):
                yield _sse("end", {"total": batch["total"], "completed": batch["completed"]})
                return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/check/batch/{batch_id}/export.csv")
def export_batch_csv(batch_id: str):
    batch = BATCH_RUNS.get(batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Check ID", "Target / Input", "Category", "Score", "Verdict", "Confidence", "Summary (EN)", "Top Reason"])

    for it in batch["items"]:
        v = it.get("verdict") or {}
        hits = it.get("hits") or []
        top_reason = hits[0].get("found", "") if hits else ""
        cells = [
            it.get("check_id", ""),
            it.get("query", ""),
            it.get("subject", {}).get("category", "general"),
            it.get("score", ""),
            v.get("label_en", v.get("code", "")),
            it.get("confidence", "MED"),
            it.get("summary", {}).get("en", ""),
            top_reason,
        ]
        writer.writerow(["'" + str(cell) if isinstance(cell, str) and cell.lstrip().startswith(("=", "+", "-", "@")) else cell for cell in cells])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=NexVerify_Batch_{batch_id}.csv"},
    )


@app.get("/api/check/batch/{batch_id}/report.pdf")
def export_batch_pdf(batch_id: str):
    batch = BATCH_RUNS.get(batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")

    pdf_path = build_batch_pdf(batch)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"NexVerify_Batch_{batch_id}.pdf",
    )


@app.post("/api/check/batch/{batch_id}/retry-failed")
async def retry_failed_batch(batch_id: str, request: Request):
    batch = BATCH_RUNS.get(batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if not batch.get("done"):
        raise HTTPException(409, "Batch is already running")

    failed_inputs = [
        it.get("query") for it in batch["items"]
        if it.get("verdict", {}).get("code") in ("UNKNOWN", "COULDNT_VERIFY") or it.get("score") == 50
    ]
    if not failed_inputs:
        return {"message": "No failed items to retry", "count": 0}

    # Filter out failed items and re-process them
    batch["items"] = [
        it for it in batch["items"]
        if it.get("query") not in failed_inputs
    ]
    batch["completed"] = len(batch["items"])
    batch["done"] = False
    asyncio.create_task(_process_batch(batch_id, failed_inputs, fresh=True, request=request))
    return {"message": f"Retrying {len(failed_inputs)} failed items", "count": len(failed_inputs)}


@app.get("/api/evidence/{check_id}/{file_name}")
def evidence_file(check_id: str, file_name: str):
    p = evidence_path(check_id, file_name)
    if not p:
        raise HTTPException(404, "no such evidence file")
    return FileResponse(p)


@app.post("/api/whatsapp")
async def whatsapp(Body: str = Form(""), From: str = Form("")):
    """Point a Twilio WhatsApp sandbox at this URL. Reply is TwiML."""
    text = Body.strip()
    hindi = bool(re.search(r"[ऀ-ॿ]", text))
    if len(text) < 2:
        msg = "Send the name of an app, company or Telegram channel to check it."
    else:
        run = await start_check(text)
        result = await wait_result(run, timeout=60)
        if not result:
            msg = "Still checking. Open the website for the live result." if not hindi else "जाँच जारी है, थोड़ी देर बाद फिर भेजें।"
        else:
            v = result["verdict"]
            lang = "hi" if hindi else "en"
            msg = (f"NexVerify: {result['subject']['display_name']}\n"
                   f"{result['score']}/100 - {v['label_' + lang]}\n{result['summary'][lang]}")
            if result.get("demo"):
                msg += "\n(Demo data)"
    _ = From
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(msg)}</Message></Response>'
    return Response(content=xml, media_type="application/xml")
