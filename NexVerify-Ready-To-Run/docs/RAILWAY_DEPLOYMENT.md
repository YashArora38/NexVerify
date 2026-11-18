# NexVerify — Railway Linux Hosting & Production Deployment Guide

This guide details the exact steps to deploy NexVerify to [Railway](https://railway.app/) (or any Linux container environment) using independent, scalable microservices.

---

## 1. Architecture Overview

NexVerify runs in production as two cooperating container services connected via Railway's private internal network:

```
┌─────────────────────────────────────────────────────────────┐
│                       End User Browser                      │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS (Public Web)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Service 1: Next.js Frontend                 │
│                 (Container: Dockerfile.frontend)             │
│  - Serves React 19 UI, Cybercrime Handoff & Web3 Controls   │
│  - Reverse-proxies /api/* to Backend via Next.js rewrites   │
│  - Forwards live SSE streams without client-side CORS issues│
└──────────────────────────────┬──────────────────────────────┘
                               │ Internal HTTP (Private Network)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Service 2: FastAPI Backend                 │
│                  (Container: Dockerfile.backend)            │
│  - Runs ProofGrid engine, EvidenceSealer, & Web Crawlers    │
│  - Serves REST endpoints, SSE streams, PDFs, and ZIP bundles│
│  - Persistent Volume mounted at /app/data                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
   ┌─────────────────────────┐   ┌─────────────────────────┐
   │    Persistent Storage   │   │   Ethereum Sepolia      │
   │       (/app/data)       │   │     (Chain 11155111)    │
   │  - SQLite (WAL mode)    │   │  - CommitmentAnchor.sol │
   │  - Evidence Sealer Store│   │  - Salted SHA-256 Hash  │
   │  - Generated PDF Reports│   │  - Web3 User Signatures │
   └─────────────────────────┘   └─────────────────────────┘
```

---

## 2. Service 1: Backend Setup (FastAPI)

### A. Railway Configuration
1. In Railway, click **New Service** > **Deploy from GitHub repo**.
2. Set the build config:
   - **Builder:** Dockerfile
   - **Dockerfile Path:** `NexVerify-Ready-To-Run/Dockerfile.backend`
3. Add a **Persistent Volume**:
   - **Mount Path:** `/app/data`
   - **Size:** 1 GB to 5 GB (stores `nexverify.db`, raw scraped evidence, and signed PDF reports).

### B. Environment Variables (Backend)
Set the following environment variables in the Railway service settings:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `NEXVERIFY_ENV` | `production` | Disables `/docs` & `/redoc`, hardens security |
| `NEXVERIFY_DATA_DIR` | `/app/data` | Directory mounted to the persistent volume |
| `DATABASE_URL` | `sqlite:////app/data/nexverify.db` | Persistent SQLite database (or Postgres connection string) |
| `PORT` | `8000` | Railway automatically assigns `$PORT` |
| `CORS_ORIGINS` | `https://<frontend-subdomain>.up.railway.app` | Restricts CORS to the production frontend domain |
| `NEXVERIFY_ALLOW_ACTIVE_BROWSER` | `false` | Keeps browser sandbox off in production for host isolation |
| `GEMINI_API_KEY` | *(Your Gemini API key)* | Optional: enables live search grounding and translation |
| `NEXVERIFY_ANCHOR_RPC_URL` | `https://rpc.sepolia.org` | Sepolia JSON-RPC provider (Infura/Alchemy/Public) |
| `NEXVERIFY_ANCHOR_CONTRACT` | `0x...` | Deployed `CommitmentAnchor` contract address on Sepolia |
| `NEXVERIFY_ANCHOR_CHAIN_ID` | `11155111` | Ethereum Sepolia testnet chain ID |

### C. Healthcheck
- **Path:** `/api/health`
- **Expected Status:** `200 OK`
- Returns: `{"ok": true, "environment": "production", "evidence_count": ...}`

---

## 3. Service 2: Frontend Setup (Next.js Standalone)

### A. Railway Configuration
1. In Railway, click **New Service** > **Deploy from GitHub repo**.
2. Set the build config:
   - **Builder:** Dockerfile
   - **Dockerfile Path:** `NexVerify-Ready-To-Run/Dockerfile.frontend`
3. Generate a **Public Domain** (e.g. `https://nexverify-production.up.railway.app`).

### B. Environment Variables (Frontend)

| Variable | Value | Description |
| :--- | :--- | :--- |
| `NEXVERIFY_INTERNAL_API_URL` | `http://<backend-service-name>.railway.internal:8000` | Private internal Railway DNS URL to Backend |
| `NODE_ENV` | `production` | Next.js production mode |
| `PORT` | `3000` | Railway automatically assigns `$PORT` |

### C. Internal API Proxy & Live Streaming
Next.js handles all API traffic transparently through `source/frontend/next.config.mjs`:
- Client requests to `/api/*` are rewritten server-side to `${NEXVERIFY_INTERNAL_API_URL}/api/*`.
- **Server-Sent Events (SSE):** The live stream endpoint `/api/check/{id}/stream` streams step-by-step checker telemetry directly to the browser UI without buffering or CORS blocks.

---

## 4. Production Security Hardening Checklist

NexVerify incorporates multi-layered defense-in-depth safeguards:

1. **SSRF Protection (`app.web.is_safe_ip`):**
   - Outbound HTTP requests strictly inspect resolved IP addresses.
   - Connections to loopback (`127.0.0.0/8`), private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), cloud metadata (`169.254.169.254`), and link-local addresses are rejected before socket connection.
2. **Rate Limiting (`app.security.RateLimiter`):**
   - In-memory token bucket tracks request frequency per client IP with a hard cap of 4,096 active tracked keys to prevent memory exhaustion attacks.
3. **Fail-Closed Production Mode:**
   - Swagger/OpenAPI docs (`/docs`, `/redoc`) are disabled in production.
   - Resource access controls enforce ownership validation.
4. **Hardened HTTP Response Headers:**
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: camera=(), microphone=(), geolocation=()`

---

## 5. Blockchain Anchoring: Sepolia Live Deployment

> [!IMPORTANT]
> **Cryptographic Clarification:**
> NexVerify uses a **salted SHA-256 cryptographic commitment scheme** to record verifiable proof of investigation records on an immutable ledger. This binds evidence hashes to block timestamps without revealing sensitive investigation payloads.
> **It is a commitment scheme, NOT a zero-knowledge proof (ZKP).** Do not describe it as a ZKP.

### Step-by-Step Sepolia Contract Activation:
1. Ensure your deployment wallet has testnet Sepolia ETH (obtainable from Sepolia faucets).
2. Compile and deploy `blockchain/contracts/CommitmentAnchor.sol`:
   - Using Remix IDE or Hardhat:
     ```bash
     cd NexVerify-Ready-To-Run/blockchain
     npx hardhat run scripts/deploy.mjs --network sepolia
     ```
3. Record the deployed contract address.
4. Update Railway Backend variables:
   - `NEXVERIFY_ANCHOR_CONTRACT=<deployed_sepolia_address>`
   - `NEXVERIFY_ANCHOR_RPC_URL=https://sepolia.infura.io/v3/<your_key>` (or `https://rpc.sepolia.org`)
   - `NEXVERIFY_ANCHOR_CHAIN_ID=11155111`
5. Restart the Backend service. The frontend Web3 button will prompt MetaMask / browser wallet users to anchor directly to the verified Sepolia contract.

---

## 6. Local Testing with Docker Compose

To verify the production container setup locally before deploying to Railway:

```bash
cd NexVerify-Ready-To-Run
docker compose up --build
```

- Frontend available at: `http://localhost:3000`
- Backend API available at: `http://localhost:8000`
- SQLite volume persisted at: `nexverify-data` volume
