"""Offline provenance ledger for NexVerify.

Canonical JSON here means the project's explicit Python convention: UTF-8,
sorted string keys, compact separators and ``allow_nan=False``.  It is not a
claim of RFC 8785/JCS compatibility.  This module never contacts a chain and
never contains a private-key or broadcast path.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config
from .evidence import SAFE_ID, sha256_bytes, verify_manifest

CANONICAL_VERSION = "python-json-v1"
PROVENANCE_VERSION = "provenance-v1"
MERKLE_VERSION = "ordered-merkle-v1"
_COMMIT_DOMAIN = b"NEXVERIFY/COMMITMENT/v1\x00"
_ARTIFACT_DOMAIN = b"NEXVERIFY/ARTIFACT/v1\x00"
_LEAF_DOMAIN = b"NEXVERIFY/MERKLE/LEAF/v1\x00"
_NODE_DOMAIN = b"NEXVERIFY/MERKLE/NODE/v1\x00"
_EMPTY_DOMAIN = b"NEXVERIFY/MERKLE/EMPTY/v1\x00"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_ENTRY_BYTES = 32 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(value: Any) -> bytes:
    """Return deterministic project JSON and reject non-string keys/NaN."""
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for key, child in v.items():
                if not isinstance(key, str):
                    raise TypeError("canonical JSON object keys must be strings")
                walk(child)
        elif isinstance(v, (list, tuple)):
            for child in v:
                walk(child)
        elif isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            raise ValueError("NaN and infinity are not valid canonical JSON")

    walk(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def _digest_domain(domain: bytes, value: bytes) -> str:
    return hashlib.sha256(domain + value).hexdigest()


def merkle_leaf(value: Any) -> str:
    return _digest_domain(_LEAF_DOMAIN, canonical_json(value))


def merkle_root(leaves: list[str] | tuple[str, ...]) -> str:
    """Hash leaves in caller-provided order; odd levels duplicate the last."""
    if not leaves:
        return _digest_domain(_EMPTY_DOMAIN, b"")
    level = [bytes.fromhex(x) if isinstance(x, str) else bytes(x) for x in leaves]
    if any(len(x) != 32 for x in level):
        raise ValueError("Merkle leaves must be SHA-256 digests")
    while len(level) > 1:
        nxt: list[bytes] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            nxt.append(hashlib.sha256(_NODE_DOMAIN + left + right).digest())
        level = nxt
    return level[0].hex()


def merkle_proof(leaves: list[str] | tuple[str, ...], index: int) -> list[dict[str, str]]:
    """Return a compact ordered proof; useful to callers, not required by the ledger."""
    if not 0 <= index < len(leaves):
        raise IndexError(index)
    level = [bytes.fromhex(x) for x in leaves]
    proof: list[dict[str, str]] = []
    pos = index
    while len(level) > 1:
        sibling = pos - 1 if pos % 2 else pos + 1
        if sibling >= len(level):
            sibling = pos
        proof.append({"side": "left" if pos % 2 else "right", "hash": level[sibling].hex()})
        nxt = []
        for i in range(0, len(level), 2):
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(hashlib.sha256(_NODE_DOMAIN + level[i] + right).digest())
        level, pos = nxt, pos // 2
    return proof


def verify_merkle_proof(leaf: str, proof: list[dict[str, str]], root: str) -> bool:
    current = bytes.fromhex(leaf)
    for step in proof:
        sibling = bytes.fromhex(step["hash"])
        current = hashlib.sha256(_NODE_DOMAIN + (sibling + current if step["side"] == "left" else current + sibling)).digest()
    return current.hex() == root


@contextmanager
def _exclusive_lock(path: Path, timeout: float = 15.0) -> Iterator[None]:
    """Cross-process one-byte lock using only the Python standard library."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\x00")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("provenance lock timeout")
                    time.sleep(0.03)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _check_id(check_id: str) -> str:
    if not isinstance(check_id, str) or not SAFE_ID.fullmatch(check_id):
        raise ValueError("unsafe check_id")
    return check_id


def _ledger_dir(check_id: str) -> Path:
    return config.DATA_DIR / "ledger" / _check_id(check_id)


def _revision_dir(check_id: str, revision: int) -> Path:
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("revision must be a positive integer")
    return _ledger_dir(check_id) / f"revision-{revision:06d}"


def _revision_numbers(check_id: str) -> list[int]:
    directory = _ledger_dir(check_id)
    if not directory.is_dir():
        return []
    out = []
    for child in directory.iterdir():
        match = re.fullmatch(r"revision-(\d{6})", child.name)
        if match and child.is_dir() and (child / "revision.json").is_file():
            out.append(int(match.group(1)))
    return sorted(out)


def _read_revision(check_id: str, revision: int | None = None) -> dict:
    nums = _revision_numbers(check_id)
    if not nums:
        raise FileNotFoundError(f"no provenance revisions for {check_id}")
    selected = nums[-1] if revision is None else revision
    path = _revision_dir(check_id, selected) / "revision.json"
    if not path.is_file():
        raise FileNotFoundError(str(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid revision record")
    return value


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def _safe_file_name(name: Any) -> bool:
    return isinstance(name, str) and bool(_SAFE_NAME.fullmatch(name)) and Path(name).name == name and name not in {".", ".."}


def _artifact_digest(metadata: dict, content: bytes) -> str:
    return hashlib.sha256(_ARTIFACT_DOMAIN + canonical_json(metadata) + b"\x00" + content).hexdigest()


def _source_manifest(check_id: str, evidence: list[dict]) -> dict:
    path = config.EVIDENCE_DIR / check_id / "manifest.json"
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("items"), list):
                return loaded
        except (OSError, ValueError, TypeError):
            pass
    created_at = utc_now()
    payload = {"canonical_version": CANONICAL_VERSION, "check_id": check_id,
               "created_at": created_at, "items": copy.deepcopy(evidence)}
    return {
        "canonical_version": CANONICAL_VERSION,
        "check_id": check_id,
        "created_at": created_at,
        "items": copy.deepcopy(evidence),
        "manifest_sha256": canonical_hash(payload),
    }


def _result_snapshot(result: dict) -> dict:
    snapshot = copy.deepcopy(result)
    snapshot.pop("integrity", None)
    return snapshot


def _graph(snapshot: dict, evidence_by_id: dict[str, dict]) -> dict:
    subject = snapshot.get("subject") if isinstance(snapshot.get("subject"), dict) else {}
    nodes = [{"id": "subject", "type": "identity", "state": "unverified", "value": {
        k: subject.get(k) for k in ("query", "website_url", "name", "category") if k in subject
    }}]
    edges: list[dict] = []
    hits = snapshot.get("hits") if isinstance(snapshot.get("hits"), list) else []
    for index, hit in enumerate(hits):
        if not isinstance(hit, dict):
            continue
        hit_id = str(hit.get("id") or hit.get("rule_id") or f"hit-{index + 1:04d}")
        deps = [str(x) for x in (hit.get("evidence_ids") or []) if str(x)]
        # An observation without evidence is retained as a heuristic trace, not authority.
        state = "heuristic" if not deps else "unverified"
        nodes.append({"id": f"claim:{hit_id}", "type": "claim", "state": state,
                      "authoritative": False, "rule_id": hit.get("rule_id"), "evidence_ids": deps,
                      "claim": hit.get("claim", ""), "found": hit.get("found", "")})
        edges.append({"from": f"claim:{hit_id}", "to": "subject", "type": "about"})
        for evidence_id in deps:
            if evidence_id in evidence_by_id:
                edges.append({"from": f"claim:{hit_id}", "to": f"evidence:{evidence_id}", "type": "depends_on"})
    for evidence_id, item in sorted(evidence_by_id.items()):
        nodes.append({"id": f"evidence:{evidence_id}", "type": "evidence",
                      "state": "simulated" if item.get("simulated") else "captured",
                      "simulated": bool(item.get("simulated")), "sha256": item.get("sha256")})
    return {"version": "typed-graph-v1", "nodes": nodes, "edges": edges,
            "ownership_verified": False}


def _dependency_map(snapshot: dict) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, hit in enumerate(snapshot.get("hits") or []):
        if isinstance(hit, dict):
            hit_id = str(hit.get("id") or hit.get("rule_id") or f"hit-{index + 1:04d}")
            result[hit_id] = {"rule_id": hit.get("rule_id"),
                              "evidence_ids": sorted(str(x) for x in (hit.get("evidence_ids") or []))}
    return result


def _dependency_diff(previous: dict | None, current: dict, current_evidence: list[dict]) -> dict:
    old_snapshot = (previous or {}).get("result") if previous else {}
    old_evidence = {(i.get("id")): canonical_hash(i) for i in ((previous or {}).get("evidence") or []) if isinstance(i, dict)}
    new_evidence = {(i.get("id")): canonical_hash(i) for i in current_evidence if isinstance(i, dict)}
    changed_evidence = sorted(k for k in set(old_evidence) & set(new_evidence) if old_evidence[k] != new_evidence[k])
    added_evidence = sorted(set(new_evidence) - set(old_evidence))
    removed_evidence = sorted(set(old_evidence) - set(new_evidence))
    old_rules = (old_snapshot or {}).get("rules") if isinstance(old_snapshot, dict) else {}
    new_rules = current.get("rules") if isinstance(current.get("rules"), dict) else {}
    changed_rules = sorted(k for k in set(old_rules or {}) | set(new_rules) if canonical_hash((old_rules or {}).get(k)) != canonical_hash(new_rules.get(k)))
    old_map = _dependency_map(old_snapshot or {})
    new_map = _dependency_map(current)
    affected = []
    for hit_id in sorted(set(old_map) | set(new_map)):
        old = old_map.get(hit_id)
        new = new_map.get(hit_id)
        if old != new or (set((new or {}).get("evidence_ids", [])) & set(changed_evidence + added_evidence + removed_evidence)) or ((new or {}).get("rule_id") in changed_rules):
            affected.append(hit_id)
    return {"changed_evidence": changed_evidence, "added_evidence": added_evidence,
            "removed_evidence": removed_evidence, "changed_rules": changed_rules,
            "affected_hit_ids": affected}


def _artifact_descriptors(check_id: str, evidence: list[dict]) -> tuple[list[dict], dict[str, bytes], dict[str, dict]]:
    descriptors: list[dict] = []
    data: dict[str, bytes] = {}
    by_id: dict[str, dict] = {}
    for index, raw in enumerate(evidence):
        item = copy.deepcopy(raw) if isinstance(raw, dict) else {"id": f"E{index + 1:02d}"}
        item_id = str(item.get("id") or f"E{index + 1:02d}")
        by_id[item_id] = item
        name = item.get("file")
        simulated = bool(item.get("simulated"))
        descriptor = {"id": item_id, "file": name if _safe_file_name(name) else "",
                      "path": f"artifacts/{name}" if _safe_file_name(name) else "",
                      "metadata_sha256": canonical_hash(item), "content_sha256": None,
                      "artifact_sha256": None, "bytes": None,
                      "status": "simulated" if simulated else "missing_legacy"}
        if _safe_file_name(name):
            source = config.EVIDENCE_DIR / check_id / name
            if source.is_file():
                blob = source.read_bytes()
                descriptor.update(content_sha256=sha256_bytes(blob), artifact_sha256=_artifact_digest(item, blob),
                                  bytes=len(blob), status="simulated" if simulated else "present")
                data[name] = blob
        descriptors.append(descriptor)
    return descriptors, data, by_id


def _bundle_payload(record: dict) -> dict:
    return {"provenance_version": record["provenance_version"], "check_id": record["check_id"],
            "revision": record["revision"], "result_sha256": record["result_sha256"],
            "evidence_manifest_sha256": record["evidence_manifest_sha256"],
            "artifacts": record["artifacts"], "merkle_root": record["merkle_root"],
            "graph": record["graph"], "dependency_diff": record["dependency_diff"]}


def _artifact_root(descriptors: list[dict]) -> str:
    leaves = [merkle_leaf({"path": d.get("path"), "id": d.get("id"),
                           "metadata_sha256": d.get("metadata_sha256"),
                           "content_sha256": d.get("content_sha256"), "artifact_sha256": d.get("artifact_sha256"),
                           "status": d.get("status"),
                           "bytes": d.get("bytes")}) for d in descriptors]
    return merkle_root(leaves)


def _summary(record: dict) -> dict:
    return {"check_id": record["check_id"], "revision": record["revision"],
            "bundle_sha256": record["bundle_sha256"], "merkle_root": record["merkle_root"],
            "commitment": record["commitment"], "previous_revision_hash": record["previous_revision_hash"],
            "revision_hash": record["revision_hash"], "evidence_count": len(record["evidence"]),
            "created_at": record["created_at"], "actor": record.get("actor"), "reason": record.get("reason"),
            "dependency_diff": copy.deepcopy(record["dependency_diff"]),
            "ownership_verified": False, "external_authenticity": "not_verified",
            "capture_time": "self_reported"}


def record_revision(result: dict, actor: str = "system", reason: str = "initial") -> dict:
    """Append an immutable revision and return its integrity summary.

    ``result`` is deep-copied and never mutated; callers may assign the returned
    summary to ``result['integrity']`` after this function returns.
    """
    if not isinstance(result, dict):
        raise TypeError("result must be a dict")
    check_id = _check_id(result.get("check_id"))
    snapshot = _result_snapshot(result)
    evidence = [copy.deepcopy(i) for i in (snapshot.get("evidence") or []) if isinstance(i, dict)]
    ledger = _ledger_dir(check_id)
    ledger.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(ledger / ".lock"):
        previous = _read_revision(check_id) if _revision_numbers(check_id) else None
        revision = (_revision_numbers(check_id)[-1] + 1) if _revision_numbers(check_id) else 1
        descriptors, blobs, evidence_by_id = _artifact_descriptors(check_id, evidence)
        frozen_manifest = _source_manifest(check_id, evidence)
        record = {"provenance_version": PROVENANCE_VERSION, "canonical_version": CANONICAL_VERSION,
                  "merkle_version": MERKLE_VERSION, "check_id": check_id, "revision": revision,
                  "created_at": utc_now(), "actor": str(actor)[:200], "reason": str(reason)[:500],
                  "result": snapshot, "result_sha256": canonical_hash(snapshot),
                  "evidence": evidence, "evidence_manifest": frozen_manifest,
                  "evidence_manifest_sha256": canonical_hash(frozen_manifest), "artifacts": descriptors,
                  "graph": _graph(snapshot, evidence_by_id),
                  "dependency_diff": _dependency_diff(previous, snapshot, evidence),
                  "previous_revision_hash": previous.get("revision_hash") if previous else None,
                  "commitment_salt": secrets.token_hex(32)}
        record["merkle_root"] = _artifact_root(descriptors)
        record["bundle_sha256"] = canonical_hash(_bundle_payload(record))
        salt = bytes.fromhex(record["commitment_salt"])
        record["commitment"] = hashlib.sha256(_COMMIT_DOMAIN + salt + record["bundle_sha256"].encode("ascii")).hexdigest()
        record["revision_hash"] = canonical_hash({k: v for k, v in record.items() if k != "revision_hash"})
        directory = _revision_dir(check_id, revision)
        directory.mkdir()
        for name, blob in blobs.items():
            _write_exclusive(directory / "artifacts" / name, blob)
        _write_exclusive(directory / "revision.json", canonical_json(record))
    return _summary(record)


def get_history(check_id: str) -> list[dict]:
    _check_id(check_id)
    return [_summary(_read_revision(check_id, number)) for number in _revision_numbers(check_id)]


def load_revision(check_id: str, revision: int | None = None) -> dict:
    _check_id(check_id)
    return _read_revision(check_id, revision)


def _verify_record(record: dict, artifacts: dict[str, bytes], check_previous: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if record.get("provenance_version") != PROVENANCE_VERSION:
        errors.append("unsupported provenance version")
    snapshot = record.get("result")
    if not isinstance(snapshot, dict) or record.get("result_sha256") != canonical_hash(snapshot):
        errors.append("result snapshot hash mismatch")
    manifest = record.get("evidence_manifest")
    if not isinstance(manifest, dict) or record.get("evidence_manifest_sha256") != canonical_hash(manifest):
        errors.append("evidence manifest hash mismatch")
    if isinstance(manifest, dict):
        legacy = verify_manifest(manifest)
        if not legacy["ok"]:
            errors.extend(legacy["errors"])
        if manifest.get("canonical_version") != CANONICAL_VERSION:
            warnings.append("legacy evidence manifest semantics used")
    descriptors = record.get("artifacts") if isinstance(record.get("artifacts"), list) else []
    frozen_items = {str(item.get("id")): item for item in (record.get("evidence") or []) if isinstance(item, dict)}
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            errors.append("invalid artifact descriptor")
            continue
        name = descriptor.get("path")
        item = frozen_items.get(str(descriptor.get("id")))
        if item is None or descriptor.get("metadata_sha256") != canonical_hash(item):
            errors.append(f"artifact metadata hash mismatch: {name}")
        blob = artifacts.get(name)
        expected = descriptor.get("content_sha256")
        if item and expected and item.get("sha256") != expected:
            errors.append(f"captured-content hash differs from evidence metadata: {name}")
        if descriptor.get("status") in ("present", "simulated") and expected:
            if blob is None:
                errors.append(f"missing artifact: {name}")
            elif sha256_bytes(blob) != expected or len(blob) != descriptor.get("bytes"):
                errors.append(f"artifact hash mismatch: {name}")
            elif descriptor.get("artifact_sha256") != _artifact_digest(item, blob):
                errors.append(f"metadata-plus-content hash mismatch: {name}")
        if descriptor.get("metadata_sha256") is None:
            errors.append(f"artifact metadata hash missing: {name}")
    if record.get("merkle_root") != _artifact_root(descriptors):
        errors.append("Merkle root mismatch")
    if record.get("bundle_sha256") != canonical_hash(_bundle_payload(record)):
        errors.append("bundle hash mismatch")
    try:
        expected_commitment = hashlib.sha256(_COMMIT_DOMAIN + bytes.fromhex(record["commitment_salt"]) + str(record["bundle_sha256"]).encode("ascii")).hexdigest()
    except (KeyError, ValueError, TypeError):
        expected_commitment = ""
    if record.get("commitment") != expected_commitment:
        errors.append("salted commitment mismatch")
    if record.get("revision_hash") != canonical_hash({k: v for k, v in record.items() if k != "revision_hash"}):
        errors.append("revision hash mismatch")
    if check_previous and record.get("revision", 1) > 1:
        try:
            previous = _read_revision(record["check_id"], record["revision"] - 1)
            if record.get("previous_revision_hash") != previous.get("revision_hash"):
                errors.append("previous revision link mismatch")
        except (OSError, ValueError, FileNotFoundError):
            errors.append("previous revision missing")
    if not check_previous and record.get("revision", 1) > 1:
        warnings.append("Standalone bundle does not independently verify previous revision history")
    missing = [d.get("id") for d in descriptors if isinstance(d, dict) and d.get("status") == "missing_legacy"]
    if missing:
        warnings.append("Legacy evidence was not retained: " + ", ".join(str(x) for x in missing))
    return {"ok": not errors, "check_id": record.get("check_id"), "revision": record.get("revision"),
            "errors": errors, "warnings": warnings, "summary": _summary(record),
            "ownership_verified": False, "external_authenticity": "not_verified",
            "capture_time": "self_reported"}


def verify_revision(check_id: str, revision: int | None = None) -> dict:
    _check_id(check_id)
    record = _read_revision(check_id, revision)
    result = None
    chain_errors = []
    for number in range(1, int(record["revision"]) + 1):
        try:
            current = _read_revision(check_id, number)
            artifacts: dict[str, bytes] = {}
            directory = _revision_dir(check_id, number) / "artifacts"
            for descriptor in current.get("artifacts", []):
                if isinstance(descriptor, dict) and descriptor.get("path", "").startswith("artifacts/"):
                    name = descriptor["path"][len("artifacts/"):]
                    if _safe_file_name(name) and (directory / name).is_file():
                        artifacts[descriptor["path"]] = (directory / name).read_bytes()
            checked = _verify_record(current, artifacts, check_previous=True)
            chain_errors.extend(f"revision {number}: {error}" for error in checked["errors"])
            result = checked
        except (OSError, ValueError, KeyError, TypeError):
            chain_errors.append(f"revision {number}: missing or invalid record")
    if result is None:
        return {"ok": False, "errors": chain_errors, "warnings": []}
    result["errors"] = chain_errors
    result["ok"] = not chain_errors
    result["verified_revision_count"] = int(record["revision"])
    return result


def export_bundle(check_id: str, revision: int | None = None) -> Path:
    _check_id(check_id)
    record = _read_revision(check_id, revision)
    directory = _revision_dir(check_id, int(record["revision"]))
    output = directory / "bundle.zip"
    if output.is_file():
        return output
    memory = bytearray()
    import io
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("revision.json", canonical_json(record))
        for descriptor in record.get("artifacts", []):
            if not isinstance(descriptor, dict) or descriptor.get("status") not in ("present", "simulated"):
                continue
            name = descriptor.get("path", "")
            if not name.startswith("artifacts/") or not _safe_file_name(name[10:]):
                raise ValueError("unsafe artifact path")
            source = directory / "artifacts" / name[10:]
            if source.is_file():
                archive.writestr(name, source.read_bytes())
        archive.writestr("README.txt", "NexVerify offline provenance bundle. Hashes prove file consistency only; external authenticity and trusted capture time are not established.\n")
    memory.extend(stream.getvalue())
    if len(memory) > MAX_BUNDLE_BYTES:
        raise ValueError("bundle exceeds size bound")
    try:
        _write_exclusive(output, bytes(memory))
    except FileExistsError:
        pass
    return output


def verify_bundle(path: str | os.PathLike[str]) -> dict:
    """Verify a ZIP in memory with fixed safe paths and bounded sizes."""
    bundle = Path(path)
    if not bundle.is_file():
        return {"ok": False, "errors": ["bundle not found"], "warnings": []}
    try:
        if bundle.stat().st_size > MAX_BUNDLE_BYTES:
            return {"ok": False, "errors": ["bundle exceeds size bound"], "warnings": []}
        import io
        raw = bundle.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                return {"ok": False, "errors": ["duplicate ZIP path"], "warnings": []}
            allowed = {"revision.json", "README.txt"}
            total_uncompressed = 0
            for info in infos:
                name = info.filename
                if name not in allowed and not (name.startswith("artifacts/") and _safe_file_name(name[10:])):
                    return {"ok": False, "errors": [f"unsafe ZIP path: {name}"], "warnings": []}
                if info.is_dir() or info.file_size > MAX_ENTRY_BYTES:
                    return {"ok": False, "errors": ["ZIP entry exceeds size bound"], "warnings": []}
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_BUNDLE_BYTES:
                    return {"ok": False, "errors": ["ZIP contents exceed size bound"], "warnings": []}
            if "revision.json" not in names:
                return {"ok": False, "errors": ["revision.json missing"], "warnings": []}
            record = json.loads(archive.read("revision.json").decode("utf-8"))
            artifacts = {name: archive.read(name) for name in names if name.startswith("artifacts/")}
        if not isinstance(record, dict):
            return {"ok": False, "errors": ["invalid revision.json"], "warnings": []}
        return _verify_record(record, artifacts, check_previous=False)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        return {"ok": False, "errors": [f"invalid bundle: {type(exc).__name__}"], "warnings": []}
