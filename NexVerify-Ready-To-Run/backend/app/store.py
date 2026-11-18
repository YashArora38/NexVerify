"""Saved results (SQLite by default, PostgreSQL via DATABASE_URL) + 24h cache.

Cache uses Redis when REDIS_URL is set, otherwise an in-memory dict, so the
app runs with zero setup and scales up without code changes.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, select

from . import config

metadata = MetaData()
checks = Table(
    "checks", metadata,
    Column("id", String(32), primary_key=True),
    Column("query", String(300), nullable=False),
    Column("norm_query", String(300), index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("score", Integer),
    Column("verdict", String(32)),
    Column("demo", Boolean, default=False),
    Column("result_json", Text, nullable=False),
)

flags = Table(
    "flags", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("check_id", String(32), index=True),
    Column("query", String(300), index=True),
    Column("reason", String(100), nullable=False),
    Column("comment", String(500), default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

anchors = Table(
    "anchors", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("check_id", String(32), index=True, nullable=False),
    Column("revision_id", Integer, default=1),
    Column("commitment", String(66), nullable=False),
    Column("chain_id", Integer, default=11155111),
    Column("contract_address", String(42), nullable=False),
    Column("publisher", String(42)),
    Column("tx_hash", String(66), index=True),
    Column("block_number", Integer),
    Column("block_timestamp", DateTime(timezone=True)),
    Column("confirmations", Integer, default=0),
    Column("status", String(32), default="PREPARED"),  # NOT_ANCHORED, PREPARED, AWAITING_WALLET, SUBMITTED, PENDING_CONFIRMATION, VERIFIED_ON_CHAIN, FAILED, REORG_DETECTED
    Column("error_details", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("verified_at", DateTime(timezone=True)),
)

_engine = None


def engine():
    global _engine
    if _engine is None:
        if config.DATABASE_URL.startswith("sqlite"):
            kw = {"connect_args": {"check_same_thread": False, "timeout": 30.0}}
        else:
            kw = {}
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, **kw)
        if config.DATABASE_URL.startswith("sqlite"):
            try:
                with _engine.connect() as _c:
                    _c.exec_driver_sql("PRAGMA journal_mode=WAL")
                    _c.exec_driver_sql("PRAGMA synchronous=NORMAL")
                    _c.exec_driver_sql("PRAGMA busy_timeout=30000")
            except Exception:
                pass
        metadata.create_all(_engine)
    return _engine


def db_kind() -> str:
    return "postgres" if config.DATABASE_URL.startswith("postgres") else "sqlite"


def save_result(result: dict) -> None:
    with engine().begin() as conn:
        conn.execute(checks.delete().where(checks.c.id == result["check_id"]))
        conn.execute(checks.insert().values(
            id=result["check_id"], query=result["query"][:300], norm_query=result["norm_query"][:300],
            created_at=datetime.now(timezone.utc), score=result["score"], verdict=result["verdict"]["code"],
            demo=result["demo"], result_json=json.dumps(result, ensure_ascii=False)))


def load_result(check_id: str) -> dict | None:
    with engine().connect() as conn:
        row = conn.execute(select(checks.c.result_json).where(checks.c.id == check_id)).first()
    return json.loads(row[0]) if row else None


def recent(limit: int = 10) -> list[dict]:
    with engine().connect() as conn:
        rows = conn.execute(select(checks.c.id, checks.c.query, checks.c.score, checks.c.verdict,
                                   checks.c.created_at, checks.c.demo)
                            .order_by(checks.c.created_at.desc()).limit(limit)).all()
    return [{"check_id": r[0], "query": r[1], "score": r[2], "verdict": r[3],
             "created_at": r[4].isoformat() if r[4] else None, "demo": r[5]} for r in rows]


def add_flag(check_id: str, query: str, reason: str, comment: str = "") -> int:
    """Store user flag disputing a verdict, return updated count."""
    try:
        with engine().begin() as conn:
            conn.execute(flags.insert().values(
                check_id=check_id,
                query=query[:300],
                reason=reason[:100],
                comment=comment[:500],
                created_at=datetime.now(timezone.utc),
            ))
    except Exception:
        pass
    return get_flag_count(check_id, query)


def get_flag_count(check_id: str, query: str = "") -> int:
    """Get total disputed flag count for a check ID or query."""
    try:
        with engine().connect() as conn:
            count = conn.execute(
                select(flags.c.id).where((flags.c.check_id == check_id) | (flags.c.query == query))
            ).fetchall()
            return len(count)
    except Exception:
        return 0


# --- Blockchain Anchors Persistence ----------------------------------------
def save_anchor(record: dict) -> dict:
    now = datetime.now(timezone.utc)
    with engine().begin() as conn:
        existing = conn.execute(
            select(anchors).where(
                (anchors.c.check_id == record["check_id"]) &
                (anchors.c.revision_id == record.get("revision_id", 1))
            )
        ).first()
        values = {
            "check_id": record["check_id"],
            "revision_id": record.get("revision_id", 1),
            "commitment": record["commitment"],
            "chain_id": record.get("chain_id", config.ANCHOR_CHAIN_ID),
            "contract_address": record.get("contract_address", config.ANCHOR_CONTRACT).lower(),
            "publisher": record.get("publisher", "").lower() if record.get("publisher") else None,
            "tx_hash": record.get("tx_hash", "").lower() if record.get("tx_hash") else None,
            "block_number": record.get("block_number"),
            "block_timestamp": record.get("block_timestamp"),
            "confirmations": record.get("confirmations", 0),
            "status": record.get("status", "PREPARED"),
            "error_details": record.get("error_details"),
            "created_at": record.get("created_at") or now,
            "verified_at": record.get("verified_at"),
        }
        if existing:
            conn.execute(
                anchors.update().where(anchors.c.id == existing.id).values(**values)
            )
        else:
            conn.execute(anchors.insert().values(**values))
    return get_anchor(record["check_id"], record.get("revision_id", 1))


def get_anchor(check_id: str, revision_id: int | None = None) -> dict | None:
    with engine().connect() as conn:
        q = select(anchors).where(anchors.c.check_id == check_id)
        if revision_id is not None:
            q = q.where(anchors.c.revision_id == revision_id)
        else:
            q = q.order_by(anchors.c.revision_id.desc())
        row = conn.execute(q).first()
        if not row:
            return None
        return {
            "id": row.id,
            "check_id": row.check_id,
            "revision_id": row.revision_id,
            "commitment": row.commitment,
            "chain_id": row.chain_id,
            "contract_address": row.contract_address,
            "publisher": row.publisher,
            "tx_hash": row.tx_hash,
            "block_number": row.block_number,
            "block_timestamp": row.block_timestamp.isoformat() if row.block_timestamp else None,
            "confirmations": row.confirmations,
            "status": row.status,
            "error_details": row.error_details,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        }


def get_anchor_by_tx(tx_hash: str) -> dict | None:
    norm_tx = tx_hash.lower()
    with engine().connect() as conn:
        row = conn.execute(select(anchors).where(anchors.c.tx_hash == norm_tx)).first()
        if not row:
            return None
        return get_anchor(row.check_id, row.revision_id)


def update_anchor(check_id: str, revision_id: int, updates: dict) -> dict | None:
    with engine().begin() as conn:
        conn.execute(
            anchors.update().where(
                (anchors.c.check_id == check_id) &
                (anchors.c.revision_id == revision_id)
            ).values(**updates)
        )
    return get_anchor(check_id, revision_id)


def get_pending_anchors() -> list[dict]:
    with engine().connect() as conn:
        rows = conn.execute(
            select(anchors).where(
                anchors.c.status.in_(["SUBMITTED", "PENDING_CONFIRMATION"])
            )
        ).all()
        return [get_anchor(r.check_id, r.revision_id) for r in rows if r]


# ---------------------------------------------------------------------------
class _MemoryCache:
    def __init__(self):
        self._d: dict[str, tuple[float, str]] = {}

    def get(self, k: str):
        v = self._d.get(k)
        if not v:
            return None
        if v[0] < time.time():
            self._d.pop(k, None)
            return None
        return v[1]

    def set(self, k: str, v: str, ttl: int):
        self._d[k] = (time.time() + ttl, v)

    def clear(self):
        self._d.clear()


class Cache:
    def __init__(self):
        self.kind = "memory"
        self._mem = _MemoryCache()
        self._redis = None
        if config.REDIS_URL:
            try:
                import redis

                self._redis = redis.Redis.from_url(config.REDIS_URL, socket_timeout=2)
                self._redis.ping()
                self.kind = "redis"
            except Exception:
                self._redis = None

    def get(self, norm_query: str) -> str | None:
        key = f"nexverify:check:{norm_query}"
        try:
            if self._redis is not None:
                v = self._redis.get(key)
                return v.decode() if v else None
        except Exception:
            pass
        return self._mem.get(key)

    def set(self, norm_query: str, check_id: str) -> None:
        key = f"nexverify:check:{norm_query}"
        try:
            if self._redis is not None:
                self._redis.setex(key, config.CACHE_TTL_SECONDS, check_id)
                return
        except Exception:
            pass
        self._mem.set(key, check_id, config.CACHE_TTL_SECONDS)

    def clear(self) -> None:
        self._mem.clear()


cache = Cache()
