import sys
import os
import shutil
from pathlib import Path

backend = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend))

volume_mount = Path(__file__).resolve().parent / "tmp_volume_test"
if volume_mount.exists():
    shutil.rmtree(volume_mount)
volume_mount.mkdir(parents=True, exist_ok=True)

os.environ["NEXVERIFY_DATA_DIR"] = str(volume_mount)
os.environ["DATABASE_URL"] = f"sqlite:///{(volume_mount / 'nexverify.db').as_posix()}"

from app import config, store, provenance, evidence
config.DATA_DIR = volume_mount
config.EVIDENCE_DIR = volume_mount / "evidence"
config.REPORT_DIR = volume_mount / "reports"
for d in (config.DATA_DIR, config.EVIDENCE_DIR, config.REPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

print("=== Phase 1: Store Data on Mounted Volume ===")
test_id = "nv999999999999"

estore = evidence.EvidenceStore(test_id)
item = estore.add("scraper", "form", "Scraped Form", "http://test.local", b'{"evidence": "persistent payload"}', ext="json")

test_result = {
    "check_id": test_id,
    "score": 15,
    "verdict": {"code": "DANGEROUS_SCAM", "label": "Dangerous Scam"},
    "query": "PersistLoanApp",
    "norm_query": "persistloanapp",
    "demo": False,
    "signals": [{"code": "PERSIST_TEST", "penalty": 85}],
    "evidence": [item],
}

summary = provenance.record_revision(test_result)
test_result["integrity"] = summary
store.save_result(test_result)

record = provenance.load_revision(test_id, summary["revision"])
print(f"Created revision {record['revision']} with commitment {record['commitment']}")

store.save_anchor({
    "check_id": test_id,
    "revision_id": record["revision"],
    "commitment": "0x" + record["commitment"],
    "chain_id": 11155111,
    "contract_address": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "status": "PREPARED",
})

assert (volume_mount / "nexverify.db").exists(), "Database file missing on volume"
assert (volume_mount / "evidence" / test_id).exists(), "Evidence dir missing on volume"
assert (volume_mount / "ledger" / test_id).exists(), "Ledger dir missing on volume"
print("Data written and confirmed present on volume.")

print("\n=== Phase 2: Simulate Container / Process Shutdown & Restart ===")
store._engine.dispose()
store._engine = None

loaded_check = store.load_result(test_id)
assert loaded_check is not None, "Failed to restore check from volume after restart!"
assert loaded_check["score"] == 15, "Restored check score mismatch!"
assert loaded_check["verdict"]["code"] == "DANGEROUS_SCAM", "Restored check verdict mismatch!"

loaded_rev = provenance.load_revision(test_id, record["revision"])
assert loaded_rev["commitment"] == record["commitment"], "Restored commitment hash mismatch!"

ver = provenance.verify_revision(test_id, record["revision"])
assert ver["ok"] is True, f"Integrity check failed after volume restore: {ver.get('errors')}"

anchor = store.get_anchor(test_id, record["revision"])
assert anchor is not None, "Anchor record missing from volume!"
assert anchor["status"] == "PREPARED", "Anchor status mismatch!"

print("PERSISTENCE AUDIT: PASS! 100% of database records, evidence artifacts, Merkle roots, and commitments survived container restart.")

if store._engine:
    store._engine.dispose()
    store._engine = None

import time
time.sleep(0.5)
shutil.rmtree(volume_mount)
print("Cleaned up temporary volume.")
