"""Evidence locker: every step's output is saved to a file and sealed with SHA-256.

The existing public API is intentionally small and remains compatible with the
check pipeline.  New writes are exclusive: a path may only be reused when its
bytes and recorded metadata agree.  ``manifest_sha256`` in new manifests is a
hash of canonical Python JSON (not RFC 8785); ``legacy_hash`` retains the line
hash used by older manifests.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_SAFE_PART = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_SAFE_EXT = re.compile(r"^[A-Za-z0-9]{1,16}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    """Project canonical JSON: UTF-8, sorted string keys, no whitespace.

    This is deliberately documented as a Python implementation convention,
    not a claim of RFC 8785/JCS interoperability.
    """
    def check(v: Any) -> None:
        if isinstance(v, dict):
            for key, child in v.items():
                if not isinstance(key, str):
                    raise TypeError("canonical JSON object keys must be strings")
                check(child)
        elif isinstance(v, (list, tuple)):
            for child in v:
                check(child)
        elif isinstance(v, float):
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError("NaN and infinity are not valid canonical JSON")

    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class EvidenceStore:
    def __init__(self, check_id: str):
        if not SAFE_ID.fullmatch(check_id):
            raise ValueError("unsafe check_id")
        self.check_id = check_id
        self.dir = config.EVIDENCE_DIR / check_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.items: list[dict] = []
        manifest_path = self.dir / "manifest.json"
        if manifest_path.is_file():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
                if loaded.get("check_id") == check_id and isinstance(loaded.get("items"), list):
                    self.items = [dict(item) for item in loaded["items"] if isinstance(item, dict) and item.get("id")]
            except (OSError, ValueError, TypeError):
                # A damaged legacy manifest must not make the app overwrite files.
                self.items = []

    def _next_id(self) -> str:
        nums = []
        for item in self.items:
            match = re.fullmatch(r"E(\d+)", str(item.get("id", "")))
            if match:
                nums.append(int(match.group(1)))
        return f"E{(max(nums, default=0) + 1):02d}"

    def add(self, agent: str, kind: str, label: str, source_url: str | None,
            content: str | bytes | dict | list, ext: str = "txt", simulated: bool = False) -> dict:
        if not _SAFE_PART.fullmatch(str(agent)) or not _SAFE_PART.fullmatch(str(kind)):
            raise ValueError("unsafe evidence agent or kind")
        if not _SAFE_EXT.fullmatch(str(ext)):
            raise ValueError("unsafe evidence extension")
        eid = self._next_id()
        if isinstance(content, (dict, list)):
            data = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
            ext = "json"
        elif isinstance(content, str):
            data = content.encode("utf-8")
        elif isinstance(content, bytes):
            data = content
        else:
            raise TypeError("evidence content must be text, bytes, dict, or list")
        fname = f"{eid}_{agent}_{kind}.{ext}"
        path = self.dir / fname
        digest = sha256_bytes(data)

        # A restarted writer can safely resume an already completed item.
        for old in self.items:
            if old.get("file") == fname:
                if old.get("sha256") != digest or (path.is_file() and path.read_bytes() != data):
                    raise FileExistsError(f"immutable evidence conflict: {fname}")
                return dict(old)

        try:
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            if not path.is_file() or path.read_bytes() != data:
                raise FileExistsError(f"immutable evidence conflict: {fname}")
            # Do not invent metadata for an unlisted file; callers can repair
            # the manifest explicitly rather than silently claiming provenance.
            raise FileExistsError(f"unlisted evidence already exists: {fname}")

        excerpt = ""
        if ext in ("txt", "json"):
            excerpt = data.decode("utf-8", "replace")[:1800]
        item = {
            "id": eid,
            "agent": agent,
            "kind": kind,
            "label": label,
            "source_url": source_url or "",
            "captured_at": utc_now(),
            "sha256": digest,
            "file": fname,
            "bytes": len(data),
            "excerpt": excerpt,
            "simulated": bool(simulated),
        }
        self.items.append(item)
        return dict(item)

    def manifest(self) -> dict:
        items = [dict(i) for i in self.items]
        lines = "\n".join(f"{i.get('id', '')}  {i.get('sha256', '')}  {i.get('file', '')}" for i in items)
        legacy_hash = sha256_bytes(lines.encode("utf-8"))
        payload = {
            "canonical_version": "python-json-v1",
            "check_id": self.check_id,
            "created_at": utc_now(),
            "items": items,
        }
        manifest = dict(payload)
        manifest["manifest_sha256"] = sha256_bytes(_canonical(payload))
        manifest["legacy_hash"] = legacy_hash
        (self.dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest


def evidence_path(check_id: str, file_name: str) -> Path | None:
    if not SAFE_ID.fullmatch(check_id) or not re.fullmatch(r"[A-Za-z0-9_\-]+\.(txt|json|png)", file_name):
        return None
    p = config.EVIDENCE_DIR / check_id / file_name
    return p if p.is_file() else None


def verify_manifest(manifest: dict, base_dir: Path | None = None) -> dict:
    """Verify new canonical manifests and old line-hash manifests.

    Missing files are reported, not treated as tampering: old app runs may have
    referenced legacy evidence that was never retained.
    """
    errors: list[str] = []
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if not isinstance(items, list):
        return {"ok": False, "errors": ["manifest items missing"], "missing": []}
    if manifest.get("canonical_version") == "python-json-v1":
        payload = {k: manifest.get(k) for k in ("canonical_version", "check_id", "created_at", "items")}
        if manifest.get("manifest_sha256") != sha256_bytes(_canonical(payload)):
            errors.append("canonical manifest hash mismatch")
    else:
        lines = "\n".join(f"{i.get('id', '')}  {i.get('sha256', '')}  {i.get('file', '')}" for i in items if isinstance(i, dict))
        expected = manifest.get("manifest_sha256") or manifest.get("legacy_hash")
        if expected != sha256_bytes(lines.encode("utf-8")):
            errors.append("legacy manifest hash mismatch")
    missing: list[str] = []
    if base_dir is not None:
        for item in items:
            if not isinstance(item, dict):
                errors.append("invalid manifest item")
                continue
            name = item.get("file")
            if not isinstance(name, str) or evidence_path(manifest.get("check_id", ""), name) is None:
                # base_dir may be a ledger artifacts directory, so validate the
                # safe basename directly here rather than using evidence_path.
                if not isinstance(name, str) or Path(name).name != name or ".." in Path(name).parts:
                    errors.append("unsafe manifest filename")
                    continue
                path = base_dir / name
            else:
                path = base_dir / name
            if not path.is_file():
                missing.append(name)
            elif sha256_bytes(path.read_bytes()) != item.get("sha256"):
                errors.append(f"evidence hash mismatch: {name}")
    return {"ok": not errors, "errors": errors, "missing": missing}
