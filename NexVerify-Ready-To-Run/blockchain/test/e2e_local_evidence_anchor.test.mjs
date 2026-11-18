import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import ganache from "ganache";
import { ethers } from "ethers";
import { compileContract } from "../scripts/compile.mjs";

console.log("=== Running End-to-End Local EVM Evidence Anchoring & Verification Test ===");

// 1. Compile contract
const compiled = compileContract();
const abi = compiled.abi;
const bytecode = compiled.evm.bytecode.object;

// 2. Start local EVM provider
const ganacheProvider = ganache.provider({
  wallet: { totalAccounts: 5, defaultBalance: 100 },
  logging: { quiet: true },
});
const provider = new ethers.BrowserProvider(ganacheProvider);
const [ownerSigner, publisherSigner] = await provider.listAccounts();
const ownerAddr = await ownerSigner.getAddress();
const publisherAddr = await publisherSigner.getAddress();

console.log(`Local EVM ready. Deployer: ${ownerAddr}, Publisher: ${publisherAddr}`);

// 3. Step 1: Deploy CommitmentAnchor locally
const factory = new ethers.ContractFactory(abi, bytecode, ownerSigner);
const contract = await factory.deploy();
await contract.waitForDeployment();
const contractAddress = await contract.getAddress();
console.log(`[Step 1] CommitmentAnchor deployed locally at: ${contractAddress}`);

// Authorize publisher
await (await contract.connect(ownerSigner).setWriter(publisherAddr, true)).wait();
assert.equal(await contract.writers(publisherAddr), true, "Publisher must be authorized");

// 4. Step 2 & 3: Generate a genuine NexVerify evidence revision and calculate salted commitment
const backendDir = path.resolve(import.meta.dirname, "../../backend");
const pythonBin = process.env.PYTHON || path.resolve(backendDir, "../runtime/python/python.exe");
const pythonScript = `
import json, sys, secrets
from pathlib import Path
sys.path.insert(0, ${JSON.stringify(backendDir)})

from app.evidence import EvidenceStore
from app.provenance import record_revision, load_revision, canonical_hash

# Create a genuine unique check result with evidence artifacts
check_id = "nv" + secrets.token_hex(6)
store = EvidenceStore(check_id)
ev1 = store.add("listing", "surface", "Test HTML surface", "https://example.com", {"html": "<html><body>Genuine Test Evidence</body></html>", "url": "https://example.com"})

fake_result = {
    "check_id": check_id,
    "query": "https://example.com",
    "norm_query": "example.com",
    "demo": False,
    "subject": {"display_name": "Example Test"},
    "hits": [],
    "score": 100,
    "verdict": {"code": "LOW_RISK", "label_en": "Looks safe"},
    "evidence": store.items,
}

integrity = record_revision(fake_result, actor="e2e-test", reason="e2e-verification")
rev = load_revision(check_id, 1)

output = {
    "check_id": check_id,
    "commitment": "0x" + integrity["commitment"],
    "bundle_sha256": integrity["bundle_sha256"],
    "merkle_root": integrity["merkle_root"],
    "evidence_file": ev1["file"],
    "evidence_id": ev1["id"]
}
print(json.dumps(output))
`;

const pyProc = spawnSync(pythonBin, ["-c", pythonScript], { cwd: backendDir, encoding: "utf8" });
if (pyProc.status !== 0 || !pyProc.stdout) {
  throw new Error(`Python revision generation failed: ${pyProc.stderr}`);
}
const evidenceData = JSON.parse(pyProc.stdout.trim());
console.log(`[Step 2] Generated genuine NexVerify revision for check ${evidenceData.check_id}`);
console.log(`[Step 3] Calculated Salted Commitment: ${evidenceData.commitment}`);

// 5. Step 4 & 5: Submit the commitment to the deployed contract and wait for receipt
const tx = await contract.connect(publisherSigner).anchor(evidenceData.commitment);
const receipt = await tx.wait();
assert.equal(receipt.status, 1, "Transaction must succeed");
console.log(`[Step 4 & 5] Submitted commitment to contract. Tx Hash: ${receipt.hash}, Block: ${receipt.blockNumber}`);

// 6. Step 6: Read commitment from contract
const isAnchored = await contract.isAnchored(publisherAddr, evidenceData.commitment);
assert.equal(isAnchored, true, "Contract must confirm commitment is anchored");
const anchoredTimestamp = await contract.anchoredAt(publisherAddr, evidenceData.commitment);
assert.ok(anchoredTimestamp > 0n, "Timestamp must be recorded");
console.log(`[Step 6] Read commitment on-chain: isAnchored=true, anchoredAt=${anchoredTimestamp}`);

// 7. Step 7: Verify emitted event
const parsedLogs = receipt.logs.map(log => {
  try { return contract.interface.parseLog(log); } catch { return null; }
}).filter(Boolean);
const anchorEvent = parsedLogs.find(l => l.name === "CommitmentAnchored");
assert.ok(anchorEvent, "CommitmentAnchored event must exist");
assert.equal(anchorEvent.args.publisher.toLowerCase(), publisherAddr.toLowerCase());
assert.equal(anchorEvent.args.commitment, evidenceData.commitment);
assert.equal(anchorEvent.args.timestamp, anchoredTimestamp);
console.log(`[Step 7] Emitted CommitmentAnchored event validated with exact publisher, commitment, and timestamp`);

// 8. Step 8 & 9: Recalculate commitment from preserved evidence and confirm match
const verifyScript = `
import json, sys
sys.path.insert(0, ${JSON.stringify(backendDir)})
from app.provenance import load_revision, verify_revision

check_id = ${JSON.stringify(evidenceData.check_id)}
rev = load_revision(check_id, 1)
v = verify_revision(check_id, 1)

print(json.dumps({
    "ok": v["ok"],
    "errors": v.get("errors", []),
    "recalculated_commitment": "0x" + rev["commitment"]
}))
`;
const verifyProc = spawnSync(pythonBin, ["-c", verifyScript], { cwd: backendDir, encoding: "utf8" });
if (verifyProc.status !== 0) {
  throw new Error(`Python verification failed: ${verifyProc.stderr}`);
}
const verificationResult = JSON.parse(verifyProc.stdout.trim());
assert.equal(verificationResult.ok, true, "Local provenance verification must be ok: " + JSON.stringify(verificationResult.errors));
assert.equal(verificationResult.recalculated_commitment, evidenceData.commitment, "Recalculated commitment must match original");
console.log(`[Step 8 & 9] Locally recalculated commitment matches on-chain anchored commitment: ${verificationResult.recalculated_commitment}`);

// 9. Step 10: Modify a copied evidence artifact and demonstrate verification failure (Tamper Test)
const tamperScript = `
import json, sys
from pathlib import Path
sys.path.insert(0, ${JSON.stringify(backendDir)})
from app import config
from app.provenance import verify_revision

check_id = ${JSON.stringify(evidenceData.check_id)}
# Tamper with the artifact file inside the ledger
artifact_file = config.DATA_DIR / "ledger" / check_id / "revision-000001" / "artifacts" / ${JSON.stringify(evidenceData.evidence_file)}
if artifact_file.is_file():
    artifact_file.write_bytes(b"TAMPERED EVIDENCE CONTENT - MALICIOUS INJECTION")

v = verify_revision(check_id, 1)
print(json.dumps({"ok": v["ok"], "errors": v.get("errors", [])}))
`;
const tamperProc = spawnSync(pythonBin, ["-c", tamperScript], { cwd: backendDir, encoding: "utf8" });
const tamperResult = JSON.parse(tamperProc.stdout.trim());
assert.equal(tamperResult.ok, false, "Tampered evidence MUST fail verification");
assert.ok(tamperResult.errors.length > 0, "Tamper errors must be reported");
console.log(`[Step 10] TAMPER TEST PASSED: Tampered artifact was instantly detected! Errors: ${tamperResult.errors.join(", ")}`);

console.log("\nALL 10 END-TO-END BLOCKCHAIN INTEGRATION STEPS VERIFIED SUCCESSFULLY!");
