import copy
import json
import zipfile
from pathlib import Path

import pytest

from app import config
from app.evidence import EvidenceStore
from app.provenance import (
    canonical_json,
    export_bundle,
    record_revision,
    verify_bundle,
    verify_revision,
)


def _result(check_id="check_prov"):
    return {
        "check_id": check_id,
        "subject": {"query": "Example Finance", "website_url": "https://example.test", "category": "loan app"},
        "evidence": [],
        "hits": [{"id": "H1", "rule_id": "RISKY_ENDING", "claim": "A risk signal", "found": "observed", "evidence_ids": []}],
        "rules": {"RISKY_ENDING": {"penalty": 31, "description": "test rule"}},
        "score": 69,
    }


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path / "reports")
    config.DATA_DIR.mkdir(exist_ok=True)
    config.EVIDENCE_DIR.mkdir()
    return tmp_path


def test_canonical_json_rejects_nonstring_keys_and_nan():
    with pytest.raises(TypeError):
        canonical_json({1: "not a JSON object key"})
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


def test_evidence_is_immutable_and_resumes(isolated_data):
    store = EvidenceStore("check_prov")
    first = store.add("agent", "lookup", "A source", "https://example.test", "same bytes")
    assert first["id"] == "E01"
    store.manifest()
    resumed = EvidenceStore("check_prov")
    second = resumed.add("agent", "lookup", "A source", "https://example.test", "different bytes")
    assert second["id"] == "E02"
    assert (store.dir / first["file"]).read_text() == "same bytes"
    assert (store.dir / second["file"]).read_text() == "different bytes"
    manifest = resumed.manifest()
    assert manifest["canonical_version"] == "python-json-v1"
    assert manifest["manifest_sha256"]
    assert manifest["items"][0]["label"] == "A source"


def test_revision_chain_export_and_offline_verify(isolated_data):
    store = EvidenceStore("check_prov")
    item = store.add("agent", "lookup", "A source", "https://example.test", "captured")
    store.manifest()
    result = _result()
    result["evidence"] = [item]
    before = copy.deepcopy(result)
    first = record_revision(result, actor="test", reason="initial")
    assert result == before
    assert first["revision"] == 1 and first["evidence_count"] == 1
    assert verify_revision("check_prov")["ok"]

    result2 = copy.deepcopy(result)
    result2["score"] = 68
    second = record_revision(result2, reason="correction")
    assert second["revision"] == 2
    assert second["previous_revision_hash"] == first["revision_hash"]
    assert verify_revision("check_prov", 2)["ok"]

    bundle = export_bundle("check_prov", 2)
    assert bundle.name == "bundle.zip"
    assert verify_bundle(bundle)["ok"]
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {"revision.json", "artifacts/E01_agent_lookup.txt", "README.txt"}


def test_tampering_and_states_are_visible(isolated_data):
    store = EvidenceStore("check_prov")
    simulated = store.add("agent", "lookup", "simulated", "", "fixture", simulated=True)
    missing = dict(simulated)
    missing["id"] = "E02"
    missing["file"] = "E02_agent_lookup.txt"
    missing["sha256"] = "0" * 64
    missing["simulated"] = False
    result = _result()
    result["evidence"] = [simulated, missing]
    result["hits"][0]["evidence_ids"] = []
    summary = record_revision(result)
    assert summary["revision"] == 1
    revision = verify_revision("check_prov")
    assert revision["ok"]
    record_path = config.DATA_DIR / "ledger" / "check_prov" / "revision-000001" / "revision.json"
    record = json.loads(record_path.read_text())
    assert {item["status"] for item in record["artifacts"]} == {"simulated", "missing_legacy"}
    assert any(node["state"] == "heuristic" for node in record["graph"]["nodes"] if node["type"] == "claim")

    artifact = config.DATA_DIR / "ledger" / "check_prov" / "revision-000001" / "artifacts" / "E01_agent_lookup.txt"
    artifact.write_text("tampered", encoding="utf-8")
    assert not verify_revision("check_prov")["ok"]


def test_zip_path_traversal_is_rejected(isolated_data, tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("revision.json", "{}")
        archive.writestr("artifacts/../escape.txt", "no")
    result = verify_bundle(bad)
    assert not result["ok"] and any("unsafe ZIP path" in error for error in result["errors"])
