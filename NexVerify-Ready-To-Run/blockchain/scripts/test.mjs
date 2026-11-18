import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { compileContract } from "./compile.mjs";

const artifact = compileContract();
const anchor = artifact.abi.find((item) => item.type === "function" && item.name === "anchor");
assert.deepEqual(anchor.inputs, [{ internalType: "bytes32", name: "commitment", type: "bytes32" }]);
assert.equal(anchor.stateMutability, "nonpayable");
assert.ok(artifact.evm.bytecode.object.length > 0, "contract must compile to bytecode");

const commitment = `0x${"11".repeat(32)}`;
const address = `0x${"ab".repeat(20)}`;
const expected = {
  chainId: "0x1",
  to: address,
  data: `0x54be8d59${"11".repeat(32)}`,
  value: "0x0",
};

const backend = path.resolve(import.meta.dirname, "../../backend");
const pythonCode = [
  "import json",
  `import sys; sys.path.insert(0, ${JSON.stringify(backend)})`,
  "from app.blockchain import prepare_anchor",
  `print(json.dumps(prepare_anchor(${JSON.stringify(commitment)}, 1, ${JSON.stringify(address)}, consent=True)['transaction']))`,
].join("; ");
let pythonResult;
for (const command of [process.env.PYTHON, "python", "python3", "py"].filter(Boolean)) {
  const args = command === "py" ? ["-3", "-c", pythonCode] : ["-c", pythonCode];
  const attempt = spawnSync(command, args, { cwd: backend, encoding: "utf8" });
  if (!attempt.error && attempt.status === 0) {
    pythonResult = JSON.parse(attempt.stdout.trim());
    break;
  }
}
if (!pythonResult) {
  throw new Error("Python runtime unavailable: install/use the project venv to run the Python golden-vector comparison");
}
assert.deepEqual(pythonResult, expected);
console.log("Solidity ABI and Python unsigned anchor golden vector match; no broadcast path exercised.");
