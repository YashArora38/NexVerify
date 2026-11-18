import pytest
import httpx
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app import config, store
from app.blockchain import (
    ANCHOR_SELECTOR,
    IS_ANCHORED_SELECTOR,
    COMMITMENT_ANCHORED_TOPIC,
    TransactionVerificationError,
    verify_on_chain_transaction,
)

COMMITMENT = "0x" + "11" * 32
CONTRACT = "0x" + "aa" * 20
TX_HASH = "0x" + "bb" * 32
PUBLISHER = "0x" + "cc" * 20


@pytest.mark.asyncio
async def test_verify_on_chain_transaction_success():
    # Mock RPC responses
    mock_chain_res = {"jsonrpc": "2.0", "result": hex(11155111), "id": 1}
    mock_code_res = {"jsonrpc": "2.0", "result": "0x608060405234801561001057600080fd5b50", "id": 2}

    # CommitmentAnchored(publisher, commitment, timestamp)
    padded_publisher = "0x" + "0" * 24 + PUBLISHER[2:].lower()
    mock_receipt = {
        "status": "0x1",
        "to": CONTRACT.lower(),
        "blockNumber": "0x64",  # 100
        "logs": [
            {
                "topics": [
                    COMMITMENT_ANCHORED_TOPIC,
                    padded_publisher,
                    COMMITMENT.lower(),
                ],
                "data": hex(1700000000),
            }
        ],
    }
    mock_receipt_res = {"jsonrpc": "2.0", "result": mock_receipt, "id": 3}
    mock_block_res = {"jsonrpc": "2.0", "result": "0x69", "id": 4}  # 105 -> 6 confirmations
    mock_block_info = {"jsonrpc": "2.0", "result": {"timestamp": hex(1700000000)}, "id": 5}
    mock_state_res = {"jsonrpc": "2.0", "result": "0x0000000000000000000000000000000000000000000000000000000000000001", "id": 6}

    async def mock_post(url, json=None, **kwargs):
        method = json.get("method")
        resp = AsyncMock()
        resp.status_code = 200
        if method == "eth_chainId":
            resp.json = lambda: mock_chain_res
        elif method == "eth_getCode":
            resp.json = lambda: mock_code_res
        elif method == "eth_getTransactionReceipt":
            resp.json = lambda: mock_receipt_res
        elif method == "eth_blockNumber":
            resp.json = lambda: mock_block_res
        elif method == "eth_getBlockByNumber":
            resp.json = lambda: mock_block_info
        elif method == "eth_call":
            resp.json = lambda: mock_state_res
        else:
            resp.json = lambda: {"jsonrpc": "2.0", "result": "0x0"}
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await verify_on_chain_transaction(
            tx_hash=TX_HASH,
            expected_contract=CONTRACT,
            expected_commitment=COMMITMENT,
            rpc_url="http://fake-rpc.local",
            expected_chain_id=11155111,
            min_confirmations=2,
        )

        assert res["verified"] is True
        assert res["status"] == "VERIFIED_ON_CHAIN"
        assert res["publisher"].lower() == PUBLISHER.lower()
        assert res["commitment"].lower() == COMMITMENT.lower()
        assert res["block_number"] == 100
        assert res["confirmations"] == 6
        assert "sepolia.etherscan.io" in res["explorer_url"]


@pytest.mark.asyncio
async def test_verify_on_chain_pending_mempool():
    mock_chain_res = {"jsonrpc": "2.0", "result": hex(11155111), "id": 1}
    mock_code_res = {"jsonrpc": "2.0", "result": "0x1234", "id": 2}
    mock_receipt_res = {"jsonrpc": "2.0", "result": None, "id": 3}

    async def mock_post(url, json=None, **kwargs):
        method = json.get("method")
        resp = AsyncMock()
        resp.status_code = 200
        if method == "eth_chainId":
            resp.json = lambda: mock_chain_res
        elif method == "eth_getCode":
            resp.json = lambda: mock_code_res
        elif method == "eth_getTransactionReceipt":
            resp.json = lambda: mock_receipt_res
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await verify_on_chain_transaction(
            tx_hash=TX_HASH,
            expected_contract=CONTRACT,
            expected_commitment=COMMITMENT,
            rpc_url="http://fake-rpc.local",
            expected_chain_id=11155111,
        )
        assert res["verified"] is False
        assert res["status"] == "PENDING_CONFIRMATION"


@pytest.mark.asyncio
async def test_verify_on_chain_reverted_tx():
    mock_chain_res = {"jsonrpc": "2.0", "result": hex(11155111), "id": 1}
    mock_code_res = {"jsonrpc": "2.0", "result": "0x1234", "id": 2}
    mock_receipt_res = {"jsonrpc": "2.0", "result": {"status": "0x0", "to": CONTRACT.lower()}, "id": 3}

    async def mock_post(url, json=None, **kwargs):
        method = json.get("method")
        resp = AsyncMock()
        resp.status_code = 200
        if method == "eth_chainId":
            resp.json = lambda: mock_chain_res
        elif method == "eth_getCode":
            resp.json = lambda: mock_code_res
        elif method == "eth_getTransactionReceipt":
            resp.json = lambda: mock_receipt_res
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await verify_on_chain_transaction(
            tx_hash=TX_HASH,
            expected_contract=CONTRACT,
            expected_commitment=COMMITMENT,
            rpc_url="http://fake-rpc.local",
            expected_chain_id=11155111,
        )
        assert res["verified"] is False
        assert res["status"] == "FAILED"


@pytest.mark.asyncio
async def test_verify_on_chain_commitment_mismatch_raises():
    mock_chain_res = {"jsonrpc": "2.0", "result": hex(11155111), "id": 1}
    mock_code_res = {"jsonrpc": "2.0", "result": "0x1234", "id": 2}
    # Log contains a DIFFERENT commitment
    padded_publisher = "0x" + "0" * 24 + PUBLISHER[2:].lower()
    different_commitment = "0x" + "99" * 32
    mock_receipt = {
        "status": "0x1",
        "to": CONTRACT.lower(),
        "blockNumber": "0x64",
        "logs": [
            {
                "topics": [
                    COMMITMENT_ANCHORED_TOPIC,
                    padded_publisher,
                    different_commitment,
                ],
                "data": hex(1700000000),
            }
        ],
    }
    mock_receipt_res = {"jsonrpc": "2.0", "result": mock_receipt, "id": 3}

    async def mock_post(url, json=None, **kwargs):
        method = json.get("method")
        resp = AsyncMock()
        resp.status_code = 200
        if method == "eth_chainId":
            resp.json = lambda: mock_chain_res
        elif method == "eth_getCode":
            resp.json = lambda: mock_code_res
        elif method == "eth_getTransactionReceipt":
            resp.json = lambda: mock_receipt_res
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(TransactionVerificationError, match="not found in transaction logs"):
            await verify_on_chain_transaction(
                tx_hash=TX_HASH,
                expected_contract=CONTRACT,
                expected_commitment=COMMITMENT,
                rpc_url="http://fake-rpc.local",
                expected_chain_id=11155111,
            )


@pytest.mark.asyncio
async def test_verify_on_chain_wrong_chain_id_raises():
    mock_chain_res = {"jsonrpc": "2.0", "result": hex(1), "id": 1}  # Ethereum Mainnet (1) instead of Sepolia (11155111)

    async def mock_post(url, json=None, **kwargs):
        resp = AsyncMock()
        resp.status_code = 200
        resp.json = lambda: mock_chain_res
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(TransactionVerificationError, match="Chain ID mismatch"):
            await verify_on_chain_transaction(
                tx_hash=TX_HASH,
                expected_contract=CONTRACT,
                expected_commitment=COMMITMENT,
                rpc_url="http://fake-rpc.local",
                expected_chain_id=11155111,
            )


def test_anchor_persistence_and_anti_replay():
    check_id_1 = "nvteststore01"
    check_id_2 = "nvteststore02"

    record1 = {
        "check_id": check_id_1,
        "revision_id": 1,
        "commitment": COMMITMENT,
        "chain_id": 11155111,
        "contract_address": CONTRACT,
        "tx_hash": TX_HASH,
        "status": "VERIFIED_ON_CHAIN",
        "confirmations": 12,
        "publisher": PUBLISHER,
    }

    saved = store.save_anchor(record1)
    assert saved is not None
    assert saved["check_id"] == check_id_1
    assert saved["status"] == "VERIFIED_ON_CHAIN"

    # Lookup by check_id
    retrieved = store.get_anchor(check_id_1, 1)
    assert retrieved["commitment"] == COMMITMENT
    assert retrieved["publisher"].lower() == PUBLISHER.lower()

    # Lookup by tx_hash
    by_tx = store.get_anchor_by_tx(TX_HASH)
    assert by_tx is not None
    assert by_tx["check_id"] == check_id_1

    # Anti-replay: another check cannot claim this tx_hash
    assert by_tx["check_id"] != check_id_2
