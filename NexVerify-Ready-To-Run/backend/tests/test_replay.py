"""Replays the real checks saved in data/nexverify.db (if present) through today's rules."""
import importlib.util
from pathlib import Path

import pytest

DB = Path(__file__).resolve().parent.parent / "data" / "nexverify.db"


@pytest.mark.skipif(not DB.exists(), reason="no saved checks to replay")
def test_saved_real_checks_have_no_dangerous_mistakes():
    spec = importlib.util.spec_from_file_location("replay_checks", DB.parent.parent / "tools" / "replay_checks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tally = mod.main(str(DB), quiet=True)["new"]
    if not tally:
        pytest.skip("database has no labelled checks")
    assert sum(v["danger"] for v in tally.values()) == 0
    n = sum(v["n"] for v in tally.values())
    ok = sum(v["ok"] for v in tally.values())
    assert ok / n >= 0.97
