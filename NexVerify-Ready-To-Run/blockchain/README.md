# NexVerify commitment anchoring (offline preparation only)

This directory contains a non-upgradeable Solidity commitment registry and
local validation tooling. It is not deployed by this project. No RPC client,
wallet, signer, nonce/gas estimator, transaction sender, private key, or
broadcast path is included.

## Python API

`backend.app.blockchain.prepare_anchor(commitment, chain_id,
contract_address, consent=False, simulated=False)` returns a canonical unsigned
EVM call only after explicit `consent=True`:

```json
{
  "status": "prepared",
  "broadcast_enabled": false,
  "chain_id": 1,
  "contract_address": "0x...",
  "commitment": "0x<64 lowercase hex digits>",
  "transaction": {
    "chainId": "0x1",
    "to": "0x<40 lowercase hex digits>",
    "data": "0x54be8d59<64 hex digits>",
    "value": "0x0"
  },
  "warnings": [
    "Not anchored: this is an unsigned local payload and no network action occurred.",
    "A commitment is not proof of truth; independently verify the off-chain evidence."
  ]
}
```

The selector is the first four bytes of Ethereum Keccak-256 for
`anchor(bytes32)`: `0x54be8d59`. NIST SHA3-256 must not be substituted. Inputs
must be a nonzero 32-byte commitment, a positive integer chain ID, and a
nonzero 20-byte contract address. Missing consent is rejected. `simulated=True`
changes only the status to `simulated`; it does not perform a network action.

The returned object intentionally contains no raw evidence, personal data,
query/check identifier, salt, private key, signature, nonce, gas fields, or
receipt claim. A future independently verified chain receipt may be represented
as a separate `anchored` or `failed` state, but this helper cannot produce
those states.

## Contract policy

`CommitmentAnchor` stores only `bytes32` commitments. The deployer is an
immutable `owner` and is initially the only writer. The owner may allow or
remove additional writer addresses. Each writer is the `publisher` namespace
(`msg.sender`) for `anchor(bytes32)`. A publisher/commitment pair can be stored
only once; repeating it reverts. `CommitmentAnchored` is an auditable event.

The contract has no proxy or upgrade mechanism and no function that rewrites
or deletes an anchored commitment. Writer policy is mutable by design, but
historical commitment records are not. On-chain presence proves only that a
writer submitted a particular commitment; it does not prove the truth or
availability of the off-chain evidence.

## Checks

From `blockchain/`, install the pinned project-local compiler dependency and
run `npm test`. The test compiles the contract in memory, verifies the
`anchor(bytes32)` ABI, and invokes the Python helper to compare the golden
unsigned calldata vector. No generated deployment artifacts are produced.
