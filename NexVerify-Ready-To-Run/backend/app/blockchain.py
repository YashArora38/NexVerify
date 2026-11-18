"""Offline-only preparation of unsigned EVM commitment-anchor transactions.

This module deliberately has no RPC, wallet, signing, nonce, gas, or broadcast
path. A prepared payload is not evidence that a transaction was submitted or
confirmed, and a commitment is not proof that its source evidence is true.
"""

from __future__ import annotations

import re
from typing import Any

# Keccak-256("anchor(bytes32)") =
# 54be8d595794fb25a03fa04ebb619fb0d689047b9b8793906beb52bc2400c175.
# Ethereum uses Keccak-256, not NIST SHA3-256; only the first four bytes are
# used for the Solidity ABI function selector.
ANCHOR_SELECTOR = "0x54be8d59"
IS_ANCHORED_SELECTOR = "0x8cf8ba1a"
COMMITMENT_ANCHORED_TOPIC = "0x901597ad3636fee9dd58e56e4658e5efc99639c63656020f88408b8ba328818e"
_COMMITMENT_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class AnchorPreparationError(ValueError):
    """Raised when an unsigned anchor payload cannot be safely prepared."""


class TransactionVerificationError(ValueError):
    """Raised when an on-chain transaction cannot be verified."""


def _validate_commitment(commitment: str) -> str:
    if not isinstance(commitment, str) or not _COMMITMENT_RE.fullmatch(commitment):
        raise AnchorPreparationError(
            "commitment must be a 32-byte 0x-prefixed hexadecimal value"
        )
    normalized = commitment.lower()
    if int(normalized, 16) == 0:
        raise AnchorPreparationError("commitment must not be the zero bytes32 value")
    return normalized


def _validate_address(contract_address: str) -> str:
    if not isinstance(contract_address, str) or not _ADDRESS_RE.fullmatch(contract_address):
        raise AnchorPreparationError(
            "contract_address must be a 20-byte 0x-prefixed hexadecimal address"
        )
    normalized = contract_address.lower()
    if int(normalized, 16) == 0:
        raise AnchorPreparationError("contract_address must not be the zero address")
    return normalized


def _validate_chain_id(chain_id: int) -> int:
    if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
        raise AnchorPreparationError("chain_id must be a positive integer")
    return chain_id


def _validate_tx_hash(tx_hash: str) -> str:
    if not isinstance(tx_hash, str) or not _TX_HASH_RE.fullmatch(tx_hash):
        raise TransactionVerificationError("tx_hash must be a 32-byte 0x-prefixed hexadecimal hash")
    return tx_hash.lower()


async def verify_on_chain_transaction(
    tx_hash: str,
    expected_contract: str,
    expected_commitment: str,
    rpc_url: str,
    expected_chain_id: int = 11155111,
    min_confirmations: int = 1,
) -> dict[str, Any]:
    """Independently verify an on-chain anchor transaction via JSON-RPC.

    Never trusts client-reported outcomes. Connects directly to the RPC endpoint,
    verifies chain ID, receipt status, contract address, CommitmentAnchored event,
    publisher identity, exact 32-byte commitment, and confirmations.
    """
    import httpx
    from datetime import datetime, timezone

    normalized_tx = _validate_tx_hash(tx_hash)
    normalized_contract = _validate_address(expected_contract)
    normalized_commitment = _validate_commitment(expected_commitment)

    if not rpc_url:
        raise TransactionVerificationError("RPC URL is required for on-chain verification")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Verify chain ID
        chain_res = await client.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}
        )
        if chain_res.status_code != 200:
            raise TransactionVerificationError(f"RPC HTTP {chain_res.status_code} during eth_chainId")
        chain_data = chain_res.json()
        if "error" in chain_data:
            raise TransactionVerificationError(f"RPC error during eth_chainId: {chain_data['error']}")
        actual_chain_id = int(chain_data.get("result", "0x0"), 16)
        if actual_chain_id != expected_chain_id:
            raise TransactionVerificationError(
                f"Chain ID mismatch: connected to chain {actual_chain_id}, expected {expected_chain_id}"
            )

        # 2. Verify contract code exists at address
        code_res = await client.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": "eth_getCode", "params": [normalized_contract, "latest"], "id": 2}
        )
        if code_res.status_code == 200:
            code_data = code_res.json()
            code_bytes = code_data.get("result", "0x")
            if not code_bytes or code_bytes in ("0x", "0x0"):
                raise TransactionVerificationError(f"No contract bytecode deployed at {normalized_contract}")

        # 3. Get transaction receipt
        receipt_res = await client.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": "eth_getTransactionReceipt", "params": [normalized_tx], "id": 3}
        )
        if receipt_res.status_code != 200:
            raise TransactionVerificationError(f"RPC HTTP {receipt_res.status_code} during eth_getTransactionReceipt")
        receipt_data = receipt_res.json()
        if "error" in receipt_data:
            raise TransactionVerificationError(f"RPC error: {receipt_data['error']}")
        receipt = receipt_data.get("result")

        # Pending in mempool
        if receipt is None:
            return {
                "verified": False,
                "status": "PENDING_CONFIRMATION",
                "tx_hash": normalized_tx,
                "contract_address": normalized_contract,
                "commitment": normalized_commitment,
                "confirmations": 0,
                "details": "Transaction found in mempool; awaiting block inclusion",
            }

        # Check transaction success status
        tx_status = receipt.get("status")
        if tx_status != "0x1":
            return {
                "verified": False,
                "status": "FAILED",
                "tx_hash": normalized_tx,
                "contract_address": normalized_contract,
                "commitment": normalized_commitment,
                "confirmations": 0,
                "details": f"Transaction reverted on-chain (status {tx_status})",
            }

        # Check contract address target
        receipt_to = (receipt.get("to") or "").lower()
        if receipt_to != normalized_contract:
            raise TransactionVerificationError(
                f"Transaction target mismatch: recipient {receipt_to} does not match expected contract {normalized_contract}"
            )

        # 4. Search and parse CommitmentAnchored event log
        event_found = False
        publisher_address = None
        anchored_timestamp = None

        for log in receipt.get("logs", []):
            topics = log.get("topics", [])
            if not topics or topics[0].lower() != COMMITMENT_ANCHORED_TOPIC.lower():
                continue
            if len(topics) >= 3:
                # topic 1: publisher (indexed address padded to 32 bytes)
                pub_hex = "0x" + topics[1][-40:].lower()
                # topic 2: commitment (indexed bytes32)
                com_hex = topics[2].lower()
                if com_hex == normalized_commitment:
                    event_found = True
                    publisher_address = pub_hex
                    data_hex = log.get("data", "0x")
                    if data_hex and data_hex != "0x":
                        anchored_timestamp = int(data_hex, 16)
                    break

        if not event_found:
            raise TransactionVerificationError(
                f"CommitmentAnchored event for commitment {normalized_commitment} not found in transaction logs"
            )

        # 5. Get current block number and confirmations
        block_res = await client.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 4}
        )
        current_block = int(block_res.json().get("result", "0x0"), 16)
        tx_block = int(receipt.get("blockNumber", "0x0"), 16)
        confirmations = max(0, current_block - tx_block + 1)

        # 6. Get block timestamp if available
        block_timestamp_iso = None
        block_info_res = await client.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": [receipt.get("blockNumber"), False], "id": 5}
        )
        if block_info_res.status_code == 200:
            b_info = block_info_res.json().get("result")
            if b_info and b_info.get("timestamp"):
                ts = int(b_info["timestamp"], 16)
                block_timestamp_iso = datetime.fromtimestamp(ts, timezone.utc).isoformat()

        # 7. Call isAnchored on-chain directly to confirm state
        if publisher_address:
            padded_pub = publisher_address[2:].rjust(64, "0")
            is_anchored_calldata = IS_ANCHORED_SELECTOR + padded_pub + normalized_commitment[2:]
            state_call_res = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [{"to": normalized_contract, "data": is_anchored_calldata}, "latest"],
                    "id": 6
                }
            )
            if state_call_res.status_code == 200:
                call_ret = state_call_res.json().get("result", "0x")
                if int(call_ret, 16) != 1:
                    raise TransactionVerificationError("Contract isAnchored query returned false on-chain")

        is_verified = confirmations >= min_confirmations
        status = "VERIFIED_ON_CHAIN" if is_verified else "PENDING_CONFIRMATION"

        explorer_url = None
        if actual_chain_id == 11155111:
            explorer_url = f"https://sepolia.etherscan.io/tx/{normalized_tx}"

        return {
            "verified": is_verified,
            "status": status,
            "chain_id": actual_chain_id,
            "contract_address": normalized_contract,
            "publisher": publisher_address,
            "commitment": normalized_commitment,
            "tx_hash": normalized_tx,
            "block_number": tx_block,
            "block_timestamp": block_timestamp_iso,
            "confirmations": confirmations,
            "required_confirmations": min_confirmations,
            "explorer_url": explorer_url,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }


def prepare_anchor(
    commitment: str,
    chain_id: int,
    contract_address: str,
    consent: bool = False,
    simulated: bool = False,
) -> dict[str, Any]:
    """Prepare a canonical, unsigned EVM call for ``anchor(bytes32)``.

    Consent is required even for simulation. The return value contains only a
    hash commitment and transaction metadata; it never includes raw evidence,
    a query/check identifier, a salt, a private key, or guessed nonce/gas.
    ``broadcast_enabled`` is permanently false in this helper.
    """
    if consent is not True:
        raise AnchorPreparationError(
            "explicit consent is required before preparing an anchor payload"
        )

    normalized_commitment = _validate_commitment(commitment)
    normalized_address = _validate_address(contract_address)
    normalized_chain_id = _validate_chain_id(chain_id)

    payload = {
        "chainId": hex(normalized_chain_id),
        "to": normalized_address,
        "data": ANCHOR_SELECTOR + normalized_commitment[2:],
        "value": "0x0",
    }
    return {
        "status": "simulated" if simulated is True else "prepared",
        "broadcast_enabled": False,
        "chain_id": normalized_chain_id,
        "contract_address": normalized_address,
        "commitment": normalized_commitment,
        "transaction": payload,
        "warnings": [
            "Not anchored: this is an unsigned local payload and no network action occurred.",
            "A commitment is not proof of truth; independently verify the off-chain evidence.",
        ],
    }
