import json

import pytest

from app.blockchain import ANCHOR_SELECTOR, AnchorPreparationError, prepare_anchor


COMMITMENT = "0x" + "11" * 32
ADDRESS = "0x" + "Ab" * 20
EXPECTED_DATA = ANCHOR_SELECTOR + "11" * 32


def test_golden_unsigned_abi_vector_and_keccak_selector():
    result = prepare_anchor(COMMITMENT, 1, ADDRESS, consent=True)

    assert ANCHOR_SELECTOR == "0x54be8d59"
    assert result["status"] == "prepared"
    assert result["transaction"] == {
        "chainId": "0x1",
        "to": ADDRESS.lower(),
        "data": EXPECTED_DATA,
        "value": "0x0",
    }


def test_simulation_is_explicit_and_still_not_broadcast():
    result = prepare_anchor(COMMITMENT, 11155111, ADDRESS, consent=True, simulated=True)

    assert result["status"] == "simulated"
    assert result["broadcast_enabled"] is False
    assert "not anchored" in result["warnings"][0].lower()


def test_privacy_boundary_has_no_raw_identifiers_or_salt():
    result = prepare_anchor(COMMITMENT, 1, ADDRESS, consent=True)
    serialized = json.dumps(result).lower()

    assert "query" not in serialized
    assert "check_id" not in serialized
    assert "salt" not in serialized
    assert "raw evidence" not in serialized
    assert result["commitment"] == COMMITMENT


@pytest.mark.parametrize(
    ("commitment", "chain_id", "address"),
    [
        ("11" * 32, 1, ADDRESS),
        ("0x" + "11" * 31, 1, ADDRESS),
        ("0x" + "gg" * 32, 1, ADDRESS),
        ("0x" + "00" * 32, 1, ADDRESS),
        (COMMITMENT, 0, ADDRESS),
        (COMMITMENT, -1, ADDRESS),
        (COMMITMENT, True, ADDRESS),
        (COMMITMENT, 1, "0x" + "00" * 20),
        (COMMITMENT, 1, "0x1234"),
    ],
)
def test_invalid_inputs_rejected(commitment, chain_id, address):
    with pytest.raises(AnchorPreparationError):
        prepare_anchor(commitment, chain_id, address, consent=True)


def test_missing_consent_rejected_before_preparation():
    with pytest.raises(AnchorPreparationError, match="consent"):
        prepare_anchor(COMMITMENT, 1, ADDRESS)


def test_no_broadcast_or_signing_fields_are_returned():
    result = prepare_anchor(COMMITMENT, 1, ADDRESS, consent=True)

    assert result["broadcast_enabled"] is False
    assert set(result["transaction"]) == {"chainId", "to", "data", "value"}
    assert not any(
        forbidden in json.dumps(result).lower()
        for forbidden in ("private_key", "signature", "nonce", "gas", "rpc", "send")
    )
