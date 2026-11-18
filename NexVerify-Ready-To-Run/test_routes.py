import httpx

base = "http://127.0.0.1:3000"
c = httpx.Client(base_url=base, timeout=30, headers={"Origin": base})

cid = "nva2997ac9f4f1"  # QuickRupee generated earlier

endpoints = [
    ("GET", "/api/health", None),
    ("GET", f"/api/check/{cid}", None),
    ("GET", f"/api/check/{cid}/stream", None),
    ("GET", f"/api/check/{cid}/report.pdf", None),
    ("GET", f"/api/check/{cid}/report.txt", None),
    ("GET", f"/api/check/{cid}/verify", None),
    ("GET", f"/api/check/{cid}/bundle.zip", None),
    ("GET", f"/api/check/{cid}/integrity", None),
    ("GET", f"/api/check/{cid}/anchor/status", None),
    ("GET", f"/api/check/{cid}/anchor/eligibility", None),
    ("POST", f"/api/check/{cid}/anchor/prepare", {"consent": True}),
    ("POST", f"/api/check/{cid}/flag", {"reason": "test audit", "comment": "automated route audit"}),
    ("POST", "/api/check/batch", {"inputs": "https://sbi.bank.in\nhttps://phonepe.com", "fresh": False}),
]

print(f"{'Method':<6} {'Route':<42} {'Status':<8} {'Content-Type / Info'}")
print("-" * 75)
for method, route, body in endpoints:
    try:
        if method == "GET":
            r = c.get(route)
        else:
            r = c.post(route, json=body)
        info = r.headers.get("Content-Type", "")
        if "pdf" in route:
            info += f" ({len(r.content)} bytes, PDF Magic: {r.content[:4]})"
        elif "zip" in route:
            info += f" ({len(r.content)} bytes, PK Magic: {r.content[:2]})"
        else:
            info += f" ({len(r.content)} bytes)"
        print(f"{method:<6} {route:<42} {r.status_code:<8} {info}")
    except Exception as e:
        print(f"{method:<6} {route:<42} ERROR    {e}")
