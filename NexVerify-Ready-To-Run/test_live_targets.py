import httpx
import json
import time

targets = ["https://sbi.bank.in", "https://www.phonepe.com", "https://zerodha.com"]
client = httpx.Client(base_url="http://127.0.0.1:3000", timeout=60, headers={"Origin": "http://127.0.0.1:3000"})

for t in targets:
    t0 = time.time()
    res = client.post("/api/check", json={"query": t, "fresh": True})
    assert res.status_code == 200, res.text
    cid = res.json()["check_id"]
    stream = client.get(f"/api/check/{cid}/stream")
    data = client.get(f"/api/check/{cid}").json()
    duration = time.time() - t0
    print(f"=== Target: {t} ===")
    print(f"Check ID: {cid}")
    print(f"Score: {data.get('score')}")
    print(f"Verdict: {json.dumps(data.get('verdict'))}")
    hits = [h["rule_id"] for h in data.get("hits", [])]
    print(f"Hits ({len(hits)}): {hits}")
    print(f"Evidence Count: {len(data.get('evidence', []))}")
    print(f"Partial: {data.get('partial')}")
    print(f"Unverified: {data.get('unverified')}")
    print(f"Duration: {duration:.2f}s")
    print("-" * 50)
