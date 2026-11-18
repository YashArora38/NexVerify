import sys
from pathlib import Path
backend = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend))

import httpx
from app.web import is_safe_ip

print("=== 1. SSRF IP Defense Check ===")
test_ips = [
    ("127.0.0.1", False),
    ("10.0.0.1", False),
    ("172.16.0.1", False),
    ("192.168.1.1", False),
    ("169.254.169.254", False),
    ("0.0.0.0", False),
    ("224.0.0.1", False),
    ("8.8.8.8", True),
    ("1.1.1.1", True),
]
all_ssrf_ok = True
for ip, expected in test_ips:
    actual = is_safe_ip(ip)
    match = actual == expected
    if not match:
        all_ssrf_ok = False
    print(f"IP: {ip:<18} Safe: {str(actual):<5} (Expected: {str(expected):<5}) -> {'PASS' if match else 'FAIL'}")
print("SSRF Defense Verification:", "PASS" if all_ssrf_ok else "FAIL")

print("\n=== 2. CORS Behavior Check ===")
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=5)
r_allowed = c.get("/api/health", headers={"Origin": "http://localhost:3000"})
print("Allowed Origin (localhost:3000) ACAO:", r_allowed.headers.get("Access-Control-Allow-Origin", "NONE"))

r_untrusted = c.get("/api/health", headers={"Origin": "http://evil-attacker.com"})
print("Untrusted Origin (evil-attacker.com) ACAO:", r_untrusted.headers.get("Access-Control-Allow-Origin", "NONE"))

print("\n=== 3. Rate Limiting Check ===")
# Burst 120 rapid requests to test rate limit behavior
exceeded = False
status_codes = []
for i in range(120):
    r = c.get("/api/health", headers={"X-Forwarded-For": "203.0.113.199"})
    status_codes.append(r.status_code)
    if r.status_code == 429:
        exceeded = True
        break
print(f"Sent burst requests from IP. 429 encountered: {exceeded} (Final status: {status_codes[-1]})")

print("\n=== 4. Next.js Production Security Headers Check ===")
c_frontend = httpx.Client(base_url="http://127.0.0.1:3000", timeout=5)
r_fe = c_frontend.get("/")
for h in ["X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"]:
    print(f"Frontend Header {h}: {r_fe.headers.get(h, 'MISSING')}")
