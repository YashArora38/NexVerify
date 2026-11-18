import assert from "node:assert/strict";
import ganache from "ganache";
import { ethers } from "ethers";
import { compileContract } from "../scripts/compile.mjs";

console.log("=== Running EVM-Level Tests on CommitmentAnchor.sol ===");

const compiled = compileContract();
const abi = compiled.abi;
const bytecode = compiled.evm.bytecode.object;

assert.ok(bytecode && bytecode.length > 0, "Bytecode must be present");

// Start in-memory EVM provider
const provider = new ethers.BrowserProvider(
  ganache.provider({
    wallet: { totalAccounts: 5, defaultBalance: 100 },
    logging: { quiet: true },
  })
);

const accounts = await provider.listAccounts();
assert.ok(accounts.length >= 3, "At least 3 accounts required for testing");

const [ownerSigner, writerSigner, unauthorizedSigner] = accounts;
const ownerAddr = await ownerSigner.getAddress();
const writerAddr = await writerSigner.getAddress();
const unauthorizedAddr = await unauthorizedSigner.getAddress();

console.log(`Owner:        ${ownerAddr}`);
console.log(`Writer:       ${writerAddr}`);
console.log(`Unauthorized: ${unauthorizedAddr}`);

// 1. Deploy contract
const factory = new ethers.ContractFactory(abi, bytecode, ownerSigner);
const contract = await factory.deploy();
await contract.waitForDeployment();
const contractAddress = await contract.getAddress();
console.log(`Contract deployed at: ${contractAddress}`);

// Verify owner is set and is an approved writer
assert.equal(await contract.owner(), ownerAddr);
assert.equal(await contract.writers(ownerAddr), true);
assert.equal(await contract.writers(writerAddr), false);

// 2. Test 1: Authorized writer (deployer/owner) can anchor
const testCommitment1 = ethers.keccak256(ethers.toUtf8Bytes("nexverify-evidence-bundle-001"));
const tx1 = await contract.connect(ownerSigner).anchor(testCommitment1);
const receipt1 = await tx1.wait();
assert.equal(receipt1.status, 1, "Transaction 1 must succeed");
assert.equal(await contract.isAnchored(ownerAddr, testCommitment1), true);
console.log("PASS: Owner can anchor commitment");

// Verify event emission
const parsedLogs = receipt1.logs.map(log => {
  try { return contract.interface.parseLog(log); } catch { return null; }
}).filter(Boolean);
const anchorEvent = parsedLogs.find(l => l.name === "CommitmentAnchored");
assert.ok(anchorEvent, "CommitmentAnchored event must be emitted");
assert.equal(anchorEvent.args.publisher.toLowerCase(), ownerAddr.toLowerCase());
assert.equal(anchorEvent.args.commitment, testCommitment1);
assert.ok(anchorEvent.args.timestamp > 0n, "Timestamp must be recorded");
console.log("PASS: CommitmentAnchored event contains valid publisher, commitment & timestamp");

// 3. Test 2: Unauthorized writer cannot anchor
const testCommitment2 = ethers.keccak256(ethers.toUtf8Bytes("nexverify-evidence-bundle-002"));
let unauthorizedFailed = false;
try {
  const tx = await contract.connect(unauthorizedSigner).anchor(testCommitment2);
  await tx.wait();
} catch (err) {
  unauthorizedFailed = true;
  assert.ok(err.message.includes("OnlyWriter") || err.message.includes("revert") || err.code === "CALL_EXCEPTION", "Should revert with OnlyWriter");
}
assert.ok(unauthorizedFailed, "Unauthorized anchor must revert");
assert.equal(await contract.isAnchored(unauthorizedAddr, testCommitment2), false);
console.log("PASS: Unauthorized account cannot anchor");

// 4. Test 3: Duplicate anchoring rejected
let duplicateFailed = false;
try {
  const tx = await contract.connect(ownerSigner).anchor(testCommitment1);
  await tx.wait();
} catch (err) {
  duplicateFailed = true;
  assert.ok(err.message.includes("AlreadyAnchored") || err.message.includes("revert") || err.code === "CALL_EXCEPTION", "Should revert with AlreadyAnchored");
}
assert.ok(duplicateFailed, "Duplicate anchor must revert");
console.log("PASS: Duplicate commitment from same publisher is rejected");

// 5. Test 4: Zero commitment is rejected
let zeroFailed = false;
try {
  const tx = await contract.connect(ownerSigner).anchor(ethers.ZeroHash);
  await tx.wait();
} catch (err) {
  zeroFailed = true;
  assert.ok(err.message.includes("ZeroCommitment") || err.message.includes("revert") || err.code === "CALL_EXCEPTION", "Should revert with ZeroCommitment");
}
assert.ok(zeroFailed, "Zero commitment must revert");
console.log("PASS: Zero commitment is rejected");

// 6. Test 5: Owner can grant writer permission
const setWriterTx = await contract.connect(ownerSigner).setWriter(writerAddr, true);
await setWriterTx.wait();
assert.equal(await contract.writers(writerAddr), true);
console.log("PASS: Owner can grant writer permissions");

// Newly approved writer can anchor
const txWriter = await contract.connect(writerSigner).anchor(testCommitment2);
const receiptWriter = await txWriter.wait();
assert.equal(receiptWriter.status, 1);
assert.equal(await contract.isAnchored(writerAddr, testCommitment2), true);
console.log("PASS: Newly approved writer successfully anchors");

// 7. Test 6: Non-owner cannot change writer permissions
let nonOwnerSetFailed = false;
try {
  const tx = await contract.connect(unauthorizedSigner).setWriter(unauthorizedAddr, true);
  await tx.wait();
} catch (err) {
  nonOwnerSetFailed = true;
  assert.ok(err.message.includes("OnlyOwner") || err.message.includes("revert") || err.code === "CALL_EXCEPTION", "Should revert with OnlyOwner");
}
assert.ok(nonOwnerSetFailed, "Non-owner setting writer must revert");
console.log("PASS: Non-owner cannot grant writer permissions");

// 8. Test 7: Owner can revoke writer permission
const revokeTx = await contract.connect(ownerSigner).setWriter(writerAddr, false);
await revokeTx.wait();
assert.equal(await contract.writers(writerAddr), false);

let revokedAnchorFailed = false;
const testCommitment3 = ethers.keccak256(ethers.toUtf8Bytes("nexverify-evidence-bundle-003"));
try {
  const tx = await contract.connect(writerSigner).anchor(testCommitment3);
  await tx.wait();
} catch (err) {
  revokedAnchorFailed = true;
}
assert.ok(revokedAnchorFailed, "Revoked writer cannot anchor new commitment");
console.log("PASS: Revoked writer cannot anchor new commitments");

// 9. Test 8: Previously anchored commitments remain intact and readable after writer is revoked
assert.equal(await contract.isAnchored(writerAddr, testCommitment2), true);
const anchoredTime = await contract.anchoredAt(writerAddr, testCommitment2);
assert.ok(anchoredTime > 0n, "Anchored timestamp must remain preserved");
console.log("PASS: Previously anchored commitments remain permanently readable after writer revocation");

console.log("\nALL 10 EVM-LEVEL CONTRACT TESTS PASSED SUCCESSFULLY!");
