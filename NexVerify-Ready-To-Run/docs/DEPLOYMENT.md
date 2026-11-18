# NexVerify: future deployment and security handoff

Nothing has been deployed, publicly published, paid for, or broadcast to a blockchain. The application remains in the existing local folder. Manus project registration succeeded and auto-publication is off, but the private managed-Git checkpoint is blocked by a preparation/file-access error; do not describe a version as synchronized until that operation succeeds.

## What is already integrated

`backend/app/main.py` installs the security boundary and claims new checks, batches, and batch child checks for the authenticated Manus user. Production reads of results, streams, reports, evidence, bundles, and nested batch exports enforce resource ownership. Recent results are owner-filtered. Authenticated or production checks bypass the shared query cache so one person's submitted evidence cannot be reused by another. Human-assisted evidence is consent-gated, best-effort minimized, classified as a user assertion, retained in a new revision, and re-evaluated without an AI call. Screenshot upload is explicitly rejected rather than silently ignored.

Development/test mode intentionally preserves the existing anonymous local workflow. That is not a logged-in identity. **Never expose development mode publicly:** production requires real authenticated sessions and fails closed without the required security configuration.

## Production configuration

Set `NEXVERIFY_ENV=production`. Startup rejects an unknown environment name, a missing/short `MANUS_JWT_SECRET` (minimum 32 UTF-8 bytes), a missing `MANUS_PROJECT_ID`, or a non-HTTPS/non-exact `FRONTEND_ORIGIN`. Obtain the project's actual OAuth/security values through the appropriate protected setup; do not invent or commit them. `backend/.env.production.example` contains placeholders only.

| Value | Purpose |
| --- | --- |
| `MANUS_PROJECT_ID` | Expected Manus application ID |
| `MANUS_JWT_SECRET` | Private project session validation/signing secret, never browser code |
| `MANUS_OAUTH_PORTAL_URL` | Authorization portal base URL |
| `MANUS_OAUTH_API_URL` | Server-side token/identity API base URL |
| `FRONTEND_ORIGIN` | Actual public HTTPS origin, not an internal request Host |
| `CORS_ORIGINS` / `NEXVERIFY_ALLOWED_ORIGINS` | Explicit browser-origin allowlists; no wildcards |
| `DATABASE_URL` | Least-privilege durable database connection |
| `REDIS_URL` | Optional isolated Redis cache |
| `NEXVERIFY_ALLOW_ACTIVE_BROWSER` | Must remain `false` until a separate browser-egress/sandbox review |
| `NEXVERIFY_ANCHOR_PREPARATION` | `false` by default; enables unsigned preparation only |
| `NEXVERIFY_ANCHOR_CHAIN_ID`, `NEXVERIFY_ANCHOR_CONTRACT` | Explicit target for future unsigned call preparation |

### Manus OAuth wire contract

Login uses `<MANUS_OAUTH_PORTAL_URL>/app-auth` with `appId`, `redirectUri`, `responseType=code`, and base64 JSON `state={redirectUri,nonce}`. Two short-lived HttpOnly cookies bind the initiating browser to the one-use server-side state/nonce record. The callback validates that binding before POSTing JSON `{clientId,grantType:"authorization_code",code,redirectUri}` to `<MANUS_OAUTH_API_URL>/webdev.v1.WebDevAuthPublicService/ExchangeToken`. The returned `accessToken` is passed as JSON in a POST to `.../GetUserInfo`. Only a real successful identity response creates an application session; no preview or development user is fabricated.

The application cookie is `webdev_app_session`. It validates HS256 signature, expected `appId`, a nonempty `openId`, and finite future expiry. Secure HTTPS session cookies use `SameSite=None` for possible embedded Preview; third-party-cookie restrictions can still prevent delivery. OAuth binding cookies use `SameSite=Lax` for the top-level redirect flow. Callback redirect is fixed to the configured frontend origin and in-application return path. Live OAuth integration has **not** been exercised against a real configured provider; its exact wire format and one-use state behavior passed mocked tests.

## Request, evidence, and collection safeguards

The middleware applies exact-origin CSRF checks to unsafe cookie-authenticated browser requests, allows credential-free CORS preflight, bounds request bodies including streamed chunks, and applies a bounded per-process rate limiter (default 120 requests/minute, at most 4,096 limiter keys). Responses carry safe headers and private no-store cache controls; production HTTPS adds HSTS. No restrictive frame-ancestor header is added that would break embedded Preview. CSV exports escape spreadsheet-formula prefixes. User-visible failure responses do not expose exception contents. Production uvicorn access logs are disabled in the root API image to avoid callback-code/query logging.

Direct page/RDAP collection validates every redirect, rejects credentials, ambiguous URL characters, nonstandard ports and private/reserved destinations, bounds decoded response bytes, disables environment proxies, and connects to a validated IP while preserving the original HTTP Host and TLS SNI. This is defense in depth, **not** a replacement for an operator-controlled egress firewall. Passive sources, dependency integrations and optional browser engines still need deployment-level network controls. Browser ladders, screenshots and deep browser inspection honor the production-off policy before unsafe escalation/probing.

Private bundles contain retained evidence, metadata, the result snapshot and the commitment salt. They are not public-redacted reports. Only the salted 32-byte commitment and transaction routing metadata are in unsigned blockchain payloads. Automatic text redaction covers limited email/phone/12-digit patterns; it is best-effort, can miss sensitive data or redact useful text, and is not a guarantee of anonymity. Originals scraped from public sources remain off-chain and must be treated as potentially personal/private evidence.

## Future container topology

`deployment/docker-compose.production.yml` is a **non-executed template** for a standalone HTTPS deployment: Caddy routes `/api/*` to FastAPI and all other requests to the standalone Next.js container; PostgreSQL, Redis and API ports are not published. Durable volumes cover database/cache, application evidence/ledger, and certificates. An API egress network is necessary for OAuth/Gemini/public sources and requires an operator-controlled firewall or proxy. The example intentionally starts one API worker because current active checks/batches and rate limits are process-local.

The root `Dockerfile` is an **API-only image**, not a combined Manus full-site publication image. Manus-managed versioning does not make this multi-container stack automatically publishable. If later selecting Manus hosting, first agree its supported runtime topology and adapt the frontend/API packaging; do not press publish against this image and claim the whole site is deployed. The user has not authorized any deployment.

Backend dependency versions are pinned in `backend/requirements.lock.txt` from the validated Windows test environment. The production Linux image must be built, scanned and tested separately, including platform-specific dependencies. Frontend and Solidity compiler dependencies have npm lockfiles. The isolated `.work/tools/python312` runtime was provisioned solely to overcome the unusable existing Windows venv during testing; it is CPython 3.12.10 and **must not be used for public production**. Use a currently security-patched supported runtime for deployment.

## Before any future activation

| Gate | Remaining work |
| --- | --- |
| Patent/disclosure | Patent professional's claim-level prior-art review and filing decision before public disclosure |
| Hosting | Choose provider and supported frontend/API runtime shape; obtain explicit deployment authorization |
| Identity | Configure protected OAuth values and test real login, callback, logout, owner separation and cookies on the actual HTTPS origin |
| Operations | Build Linux images, scan dependencies/images, set resources and edge limits, validate egress firewall and backups/restore |
| Privacy | Define access, encryption at rest, lawful retention/deletion and handling of append-only private evidence |
| Scaling | Move active jobs/batches and limiter/ownership handling to a durable, tested multi-worker design before replicas |
| Blockchain | Audit contract, configure chain/contract, establish receipt/finality verification, obtain separate deployment/transaction authorization |

## Validation achieved locally

145 backend tests passed, including original regressions and new ledger/tamper/privacy/ownership/OAuth-wire tests. One framework deprecation warning remains. The Next.js production build and TypeScript checks passed. Solidity compilation and the Python/ABI unsigned-call golden-vector comparison passed. Compose YAML/topology checks passed without starting containers. Browser-based visual interaction, real OAuth, Linux Docker execution, TLS issuance, real chain receipts and deployment remain untested/unperformed.
