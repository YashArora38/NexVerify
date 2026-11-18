import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir, fast demo, no real key, before the app is imported.
_tmp = tempfile.mkdtemp(prefix="nexverify-test-")
os.environ["NEXVERIFY_DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DEMO_SPEED"] = "100"
os.environ["GEMINI_API_KEY"] = ""
os.environ["REDIS_URL"] = ""
os.environ["GEMINI_RPM"] = "10000"  # mocked Gemini: no need to pace calls

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
