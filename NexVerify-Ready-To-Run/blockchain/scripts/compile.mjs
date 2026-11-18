import fs from "node:fs";
import path from "node:path";
import solc from "solc";

export function compileContract() {
  const sourcePath = path.resolve(import.meta.dirname, "../contracts/CommitmentAnchor.sol");
  const source = fs.readFileSync(sourcePath, "utf8");
  const input = {
    language: "Solidity",
    sources: { "CommitmentAnchor.sol": { content: source } },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors ?? []).filter((entry) => entry.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((entry) => entry.formattedMessage).join("\n"));
  }
  const artifact = output.contracts?.["CommitmentAnchor.sol"]?.CommitmentAnchor;
  if (!artifact) throw new Error("CommitmentAnchor was not produced by solc");
  return artifact;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  const artifact = compileContract();
  const anchor = artifact.abi.find((item) => item.type === "function" && item.name === "anchor");
  if (!anchor || anchor.inputs.length !== 1 || anchor.inputs[0].type !== "bytes32") {
    throw new Error("anchor(bytes32) ABI entry is missing or malformed");
  }
  if (!artifact.evm.bytecode.object) throw new Error("compiled bytecode is empty");
  console.log(`compiled CommitmentAnchor: ${artifact.evm.bytecode.object.length / 2} bytes`);
}
