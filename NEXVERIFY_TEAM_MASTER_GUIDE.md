# NexVerify: Master Team Technical & Judge Defense Guide
> **Version:** Windows Local Review Edition (17-18 November 2026)  
> **Target:** Hackathon Presentation, Viva Defense, and Internal Team Alignment  
> **Language:** Easy Hinglish + Technical English (Full Comprehensive Coverage)

---

## Quick Navigation / Table of Contents
1. [Executive Summary & Verification of Codex Changes](#1-executive-summary--verification-of-codex-changes)
2. [What is Working vs What NOT to Claim (Judge Trap Protection)](#2-what-is-working-vs-what-not-to-claim-judge-trap-protection)
3. [Technology Stack & System Architecture](#3-technology-stack--system-architecture)
4. [Complete End-to-End Workflow (Step-by-Step Lifecycle)](#4-complete-end-to-end-workflow-step-by-step-lifecycle)
5. [ProofGrid Deterministic Scoring Engine & Mathematical Rules](#5-proofgrid-deterministic-scoring-engine--mathematical-rules)
6. [Payment Intel & Anti-Spoofing Heuristics](#6-payment-intel--anti-spoofing-heuristics)
7. [Blockchain Architecture & Solidity Smart Contract](#7-blockchain-architecture--solidity-smart-contract)
8. [Database, Storage, Caching & Provenance](#8-database-storage-caching--provenance)
9. [Judge Q&A & Viva Counter-Questions (Kuch Bhi Puche Toh Yeh Bolna)](#9-judge-qa--viva-counter-questions-kuch-bhi-puche-toh-yeh-bolna)
10. [The 3-Minute Winning MSIT Demo Script](#10-the-3-minute-winning-msit-demo-script)

---

## 1. Executive Summary & Verification of Codex Changes

Bhai, folder aur codebase ko thoroughly check aur live test karke verify kiya gaya hai. Sabhi features working aur verified hain:

| Feature / Update | Status | Verification Proof |
| :--- | :---: | :--- |
| **Backend Test Suite** | **PASSED** | **163 passed, 1 skipped** (Run via `pytest NexVerify-Ready-To-Run/backend/tests -q -o asyncio_mode=auto`). |
| **False Positives Fixed** | **PASSED** | Normal UPI ID (`phone@okhdfcbank`) aur contact forms par ab automatic 70-point scam penalty nahi lagti. |
| **Deeper Surface Inspection** | **PASSED** | Root page + max 3 candidate pages (Total max 4 pages: about, contact, privacy, refund, download, payment). |
| **Fake Gateway Detection** | **PASSED** | Strict whitelist matching on HTTPS + port 443 (`checkout.razorpay.com`, `mercury.phonepe.com`, etc.). Sirf text ya spoofed domains reject hote hain. |
| **Evidence Panel & PDF/TXT** | **PASSED** | Har deduction ka reason, evidence ID, UTC timestamp, aur SHA-256 hash report me render hota hai. |
| **Editable Complaint Draft** | **PASSED** | Browser me editable draft textarea with review checkbox aur direct official handoff to [cybercrime.gov.in](https://cybercrime.gov.in). |
| **Next.js Security & Mobile** | **PASSED** | Patched to **Next.js 16.4.6** (Zero npm vulnerabilities). Mobile layout overflow table horizontally scrollable. |

---

## 2. What is Working vs What NOT to Claim (Judge Trap Protection)

> [!WARNING]
> Hackathons me sabse zyada marks tab kat-te hain jab teams aisi cheezein claim kar deti hain jo code me nahi hoti (jaise "Humne sab kuch blockchain par daal diya" ya "Humari app direct FIR file kar deti hai"). Judges trap pakad lete hain. 

### What is WORKING (Bindaas Claim Karo):
- **Pre-Payment Investigation:** Payment karne se pehle public digital footprints inspect karna.
- **5 Concurrent Python Checkers:** RBI, SEBI, Company/RDAP, Website/Listing, News/Reputation concurrent run hote hain.
- **Deterministic ProofGrid Scoring:** $Score = \max(0, 100 - \sum Penalties)$. AI score calculate nahi karta; code calculate karta hai.
- **Bounded SSRF-Guarded Fetcher:** Private subnets, 127.0.0.1, aur cloud metadata IPs connect hone se pehle block hote hain.
- **Off-Chain Tamper-Evident Evidence:** Har evidence file ka SHA-256 hash, Merkle tree root aur canonical manifest banta hai.
- **Offline Unsigned EVM Payload Preparation:** Solidity contract `CommitmentAnchor.sol` ke standard function `anchor(bytes32)` ke liye exact calldata `0x54be8d59...` generate hota hai.

### What is NOT Implemented (Demo Me Bhoolkar Bhi Claim Mat Karna):
1. **No Live Blockchain Broadcast:** Current local build me `broadcast_enabled: false` hai. Koi private key server par stored nahi hai, gas fee pay nahi hoti.
2. **No Automatic FIR Filing:** App police ya cyber cell me direct login karke FIR lodge nahi karti. User ko drafted complaint aur direct link (`cybercrime.gov.in` ya 1930) deti hai.
3. **No APK Binary Reverse-Engineering:** APK download links inventory hote hain, par APK decompilation ya static/dynamic malware analysis sandbox me run nahi hota.
4. **No Hidden Backend Code Access:** Hum sirf public HTML aur HTTP redirects dekh sakte hain, scammer ka private database ya server code nahi dekh sakte.
5. **No Merchant Identity Certification:** Payment gateway reference milna merchant ke legitimate hone ka proof nahi hai.

---

## 3. Technology Stack & System Architecture

### Frontend Layer:
- **Framework:** Next.js 16.4.6 (App Router) + React 19.3.1.
- **Language:** TypeScript 5 (Strict mode).
- **Styling:** Responsive Custom CSS (Desktop table view + Mobile-first cards).
- **3D Visualization:** Three.js 0.128.0 (StageScene component me background interactive grid aur nodes render karta hai).
- **Streaming Client:** HTML5 `EventSource` API jo `/api/check/{id}/stream` se live Server-Sent Events (SSE) sunta hai.
- **API Rewrite:** `next.config.mjs` me same-origin rewrite: browser se `/api/*` calls automatic port 8000 (FastAPI) par forward hoti hain (No CORS issues).

### Backend Layer:
- **Framework:** Python 3.12 + FastAPI 0.162.5 + Uvicorn 0.54.0.
- **Validation:** Pydantic 2.14.3 (Request payload sanitization, length boundaries, strict typing).
- **Concurrency:** Native `asyncio` event loop (5 async checker tasks parallel run hote hain).
- **HTTP Engine:** `httpx` 0.28.1 with custom SSRF security validator and DNS address pinning.
- **AI Integration:** Google Gemini API (`gemini-2.5-flash`) via `google-genai` SDK. **Strict grounding:** AI sirf Google Search use karke public records fetch karta hai, scoring me zero intervention hai.
- **PDF Generation:** ReportLab 5.1.0 (Dynamic layout drawing, CP1252 ASCII glyph normalization).

### Database & Storage:
- **ORM / DB Access:** SQLAlchemy 2.1.8 Core.
- **Database:** SQLite (default: `data/nexverify.db`). Agar production me PostgreSQL chahiye toh sirf `DATABASE_URL` set karni hoti hai.
- **Tables:** `checks` (id, query, norm_query, created_at, score, verdict, demo, result_json) aur `flags` (community dispute tracking).
- **Cache:** 24-hour memory cache (optional Redis via `REDIS_URL`).
- **Filesystem Evidence:** `data/evidence/<check_id>/` (Raw HTML captures, search responses, manifest) aur `data/ledger/<check_id>/` (Revision versioning).

---

## 4. Complete End-to-End Workflow (Step-by-Step Lifecycle)

Jab user search bar me URL ya app name daalta hai:

```
[1. User Input] -> (POST /api/check)
        |
        v
[2. Resolver & LinkIntel]
    - Query normalise hoti hai (slugify, URL parsing).
    - Checks official TLDs (.gov.in / .bank.in) -> Fast pass.
    - Checks lookalike spelling, @ tricks, punycode.
    - Fast AI Gate: Agar domain pehle se official hai ya extreme obvious scam hai,
      toh AI quota waste nahi hota.
        |
        v
[3. Orchestrator Concurrent Dispatch (asyncio.gather)]
    |--> rbi.py:       RBI NBFC list & Digital Lending Apps register match.
    |--> sebi.py:      SEBI registered intermediaries & warning lists.
    |--> company.py:   RDAP WHOIS domain age & MCA company register match.
    |--> listing.py:   Play Store/App Store metadata + Surface Crawl (investigate()).
    |--> news.py:      Consumer forums, cyber fraud reports via Google Search.
    |--> passive.py:   Phishing feeds (URLhaus, OpenPhish), SSL certs, DNS cues.
        |
        v
[4. Live Progress Streaming (SSE)]
    - Har agent ke steps live browser me stream hote hain:
      event: "agent" -> { key: "rbi", state: "running", step: "Checking NBFC register" }
      event: "cards" -> Intermediate findings render hoti hain.
        |
        v
[5. ProofGrid Scoring Engine]
    - Saare findings ke penalty points subtract hote hain (Score = 100 - Total Penalties).
    - Final Verdict assign hota hai (HIGH_RISK, SUSPICIOUS, CAUTION, etc.).
        |
        v
[6. Cryptographic Sealing & Revision]
    - Har evidence artifact ka SHA-256 hash generate hota hai.
    - Canonical Manifest banta hai.
    - Result SQLite database me save hota hai aur revision file ledger me likhi jaati hai.
        |
        v
[7. Presentation & Export]
    - Browser me final results, visual score meter aur evidence table render hoti hai.
    - User 1-click me PDF report, plain TXT report ya ZIP bundle download kar sakta hai.
    - Editable complaint draft me UTR/amount daal kar cybercrime.gov.in par handoff.
```

---

## 5. ProofGrid Deterministic Scoring Engine & Mathematical Rules

### The Scoring Equation:
$$\text{Score} = \max\left(0, 100 - \sum \text{Applied Penalties}\right)$$

Har rule ki fixed point deduction hoti hai. Koi random "AI vibe score" nahi hai.

### Verdict Bands:
- **$\ge 70$ Points Penalty $\rightarrow$ HIGH_RISK:** (Score 0-30, Red Badge, "Don't pay"). Fraud ke clear signals hain.
- **$55 - 69$ Points Penalty $\rightarrow$ SUSPICIOUS:** (Orange Badge). Multiple high-risk warning signs hain.
- **$31 - 54$ Points Penalty $\rightarrow$ CAUTION:** (Yellow Badge, "Be careful"). Context verify karne ki zaroorat hai.
- **$\le 30$ Points Penalty:**
  - Agar official government ya bank domain hai (`.gov.in`, `.bank.in`) $\rightarrow$ **VERIFIED_OFFICIAL** (Score 100).
  - Agar verified company + old domain + RBI/SEBI record hai $\rightarrow$ **LOW_RISK** (Score 70-100).
  - Agar koi identity proof nahi mila $\rightarrow$ **UNKNOWN** (Score capped at 50, UI displays `?`).

### Top Critical Scoring Rules:
| Rule ID | Penalty | Label | Condition |
| :--- | :---: | :--- | :--- |
| `THREAT_FEED` | **100** | PHISHING LIST | Exact URL active phishing list me listed hai. |
| `SAFE_BROWSING` | **100** | GOOGLE WARNING | Google Safe Browsing flagged as deceptive. |
| `BRAND_IMPERSONATION` | **75** | FAKE BRAND | Brand ka naam + login words on unofficial domain. |
| `LOOKALIKE` | **70** | LOOKALIKE | Domain spelling me swapped ya extra lookalike letters. |
| `FAKE_BANK_ZONE` | **70** | FAKE BANK | `.bank.in` ko kisi doosre domain ke andar copy kiya. |
| `INSECURE_SENSITIVE_FORM` | **60** | UNENCRYPTED DATA | Sensitive fields (OTP/Account/PIN) unencrypted HTTP par submit ho rahe hain. |
| `AGE_CONTRADICTION` | **70** | CONTRADICTION | Website 5 saal ka history claim karti hai, par domain < 30 din purana hai. |
| `VERY_NEW_DOMAIN` | **45** | NEW DOMAIN | Domain registration 30 din se kam purana hai. |
| `SENSITIVE_EXTERNAL_FORM` | **35** | DATA RECIPIENT | Sensitive data unverified 3rd party domain par bheja ja raha hai. |
| `SENSITIVE_QUERY_STRING` | **35** | DATA IN URL | Sensitive data GET method se URL parameters me bhej rahe hain. |

---

## 6. Payment Intel & Anti-Spoofing Heuristics

### A. Deep Surface Crawling (`investigation.py`):
- Root page se informational links filter karta hai (`about`, `contact`, `privacy`, `refund`, `download`, `payments`).
- Maximum 4 pages crawl hote hain (1 root + up to 3 candidate pages).
- Har fetch ka 7-second timeout hota hai SSRF protection ke saath.
- Form submissions, login, checkout, ya unsafe actions (`logout`, `delete`, `pay`, `buy`) **kabhi execute nahi hote**.

### B. Payment Gateway Detection (`gateway_for()`):
- Whitelist Domains:
  - Razorpay: `checkout.razorpay.com`, `api.razorpay.com`, `rzp.io`
  - Cashfree: `sdk.cashfree.com`, `payments.cashfree.com`
  - PayU: `secure.payu.in`, `test.payu.in`
  - PhonePe: `mercury.phonepe.com`, `merchants.phonepe.com`
  - Paytm Merchant: `securegw.paytm.in`
  - Stripe: `js.stripe.com`, `checkout.stripe.com`
- **Spoofing Guard:** URL parse karke strictly scheme=`https`, port=`443`, username/password=`None`, aur hostname exact whitelist me check hota hai.
- Fake hostnames jaise `razorpay-quickrupee.com` ya HTML me likha "Powered by Razorpay" reject ho jaate hain.

### C. Sensitive Form Analysis:
- HTML inputs me `password`, `otp`, `pin`, `cvv`, `card_number`, `account_number`, `aadhaar` scan karta hai.
- Agar form action `http://` hai $\rightarrow$ Penalty 60.
- Agar form method `GET` hai $\rightarrow$ Penalty 35.
- Normal contact forms (name, feedback, email) par zero penalty.

---

## 7. Blockchain Architecture & Solidity Smart Contract

### The Reality (Honest Explanation):
Humara blockchain system **Tamper-Evident Evidence Anchoring** ke liye banaya gaya hai.

```
[Raw Evidence Files] -> SHA-256 Hashes -> [Merkle Root]
                                                |
                                    + 32-byte Random Salt
                                                v
                                    [Salted Commitment (32 bytes)]
                                                |
            +-----------------------------------+-----------------------------------+
            |                                                                       |
    (Current Working State)                                                 (Future Extended State)
            v                                                                       v
[backend/app/blockchain.py]                                              [User Signs via Web3 Wallet]
- Explicit user consent required                                        - MetaMask / Hardware wallet
- Validates 32-byte commitment                                          - Submits to Sepolia Testnet
- Computes EVM Calldata:                                                - Contract emits CommitmentAnchored event
  Selector: 0x54be8d59                                                  - On-chain permanent timestamp
  Data: 0x54be8d59<commitment_hex>
- broadcast_enabled: false (Secure & offline)
```

### Smart Contract (`CommitmentAnchor.sol`):
- **Language:** Solidity `^0.8.20`.
- **Purpose:** Store immutable 32-byte commitments; source evidence off-chain rehta hai.
- **Key Functions:**
  - `constructor()`: Sets `owner = msg.sender` aur deployer ko default writer banata hai.
  - `setWriter(address writer, bool allowed)`: Owner naye authorized publishers add ya remove kar sakta hai.
  - `anchor(bytes32 commitment)`: Writer 32-byte hash anchor karta hai. Zero commitment ya duplicate anchor revert karta hai.
  - `CommitmentAnchored(publisher, commitment, timestamp)` event emit hota hai.
- **ABI Function Selector:**
  - Ethereum Keccak-256 hash of `anchor(bytes32)` = `54be8d59...`
  - First 4 bytes = `0x54be8d59`. (NIST SHA3-256 use nahi hota, Ethereum Keccak-256 hi use hota hai).

### Why Evidence is Off-Chain:
1. **Privacy:** User ka query data, PII, aur URLs public blockchain ledger par store nahi hona chahiye (GDPR / DPDP Act compliance).
2. **Cost & Scalability:** Raw HTML ya PDFs ko on-chain store karna astronomically expensive hota. 32-byte hash store karne se gas cost minimal rehti hai.

---

## 8. Database, Storage, Caching & Provenance

### 1. Database Schema (SQLAlchemy Core):
- **`checks` Table:**
  - `id`: String(32) primary key (e.g. `nv8a4f10c3b2`).
  - `query`: Original search query.
  - `norm_query`: Normalized query (indexed for fast lookups).
  - `created_at`: UTC timestamp.
  - `score`: Computed integer score (0 to 100).
  - `verdict`: Verdict code (e.g. `HIGH_RISK`, `VERIFIED_OFFICIAL`).
  - `demo`: Boolean (true for simulated test cases).
  - `result_json`: Complete JSON output object.
- **`flags` Table:** Community disputes aur report flags store karta hai.

### 2. Caching Strategy:
- 24-hour default TTL in-memory dictionary.
- Agar user `fresh: true` bhejta hai ya private authenticated check karta hai, toh cache bypass karke fresh scan chalta hai.
- Cache engine version `proofgrid-3` check karta hai taaki purane algorithms ke cached results re-play na hon.

### 3. Provenance & Revisions (`provenance.py`):
- Har check ke baad evidence files lock hoti hain aur `manifest.json` banta hai.
- Agar user **Human-Assist** ke zariye screenshot ya additional text deta hai, toh purana record overwrite nahi hota; ek nayi **Revision Directory** banti hai (`revision-001`, `revision-002`) with parent revision SHA-256 link.

---

## 9. Judge Q&A & Viva Counter-Questions (Kuch Bhi Puche Toh Yeh Bolna)

#### Q1: "Tumhara system aur VirusTotal ya Google Safe Browsing me kya farq hai?"
* **Answer:** *"Sir, VirusTotal aur Safe Browsing reactive threat feeds hain—woh tab detect karte hain jab hazaron log victim ban chuke hon ya domain blacklist ho chuka ho. NexVerify ek **Pre-Payment Investigation Assistant** hai. Hum domain create hone ke pehle ghante me bhi detect kar lete hain kyunki hum context dekhte hain: domain age contradiction, sensitive form destination, APK delivery, aur payment recipient ki identity."*

#### Q2: "AI agar hallucinate kare toh score galat nahi ho jayega?"
* **Answer:** *"Nahi Sir. Ye NexVerify ki core design strength hai: **AI is NOT the judge.** Gemini AI sirf search results se text facts extract karta hai (jaise company name ya registration claim). Scoring 100% deterministic Python rules (`proofgrid.py`) se hoti hai. Same evidence har baar mathematically same score calculate karega."*

#### Q3: "Agar website poori client-side React / JavaScript se load hoti ho toh HTML crawler kaise chalega?"
* **Answer:** *"Sir, NexVerify me **Browser Ladder** architecture hai (`browser_ladder.py`). Static HTML inspection fast layer hai. Agar page dynamic ho toh backend me curl_cffi aur Playwright headless browser fallback modules implemented hain jo JS evaluate kar sakte hain. Current Windows demo launcher me resource bounds ke liye bounded static crawl active hai."*

#### Q4: "Tumne blockchain par broadcast kyun disable rakha hai?"
* **Answer:** *"Sir, security aur integrity ke rules ke mutabiq server par hardcoded private keys ya unsecured hot wallets nahi hone chahiye. Humne Solidity smart contract `CommitmentAnchor.sol` complete likha hai aur backend user ke consent par canonical unsigned EVM calldata (`0x54be8d59...`) generate karta hai. Is payload ko user apne MetaMask wallet se Sepolia testnet par sign aur broadcast kar sakta hai."*

#### Q5: "Scammer agar fake certificate ya official-looking domain banaye toh?"
* **Answer:** *"Sir, hum sirf domain string match nahi karte. Public Suffix list aur Registrable Domain extraction se subdomains expose hote hain. Agar koi `sbi.bank.in.fake-portal.com` banaye, toh system instantly pehchan leta hai ki registrable domain `fake-portal.com` hai aur **BRAND_IN_SUBDOMAIN** (70 points penalty) trigger karke HIGH RISK declare kar deta hai."*

#### Q6: "Agar koi unknown harmless personal blog ho toh kya use scam declare kar doge?"
* **Answer:** *"Bilkul nahi Sir. Humara rule engine **absence of evidence ko proof of safety nahi maanta**. Agar kisi site par koi scam report nahi hai par koi official business identity bhi nahi hai, toh score 100 nahi hota; balki use **UNKNOWN** verdict diya jaata hai (Internal score capped at 50, UI par `?`). Hum false safety declare nahi karte."*

---

## 10. The 3-Minute Winning MSIT Demo Script

Is flow ko exactly practice karo. 3 minute me judges clear ho jayenge:

### Step 1: Hook & Pitch (0:00 - 0:30)
- *"Good morning Judges. India me digital fraud har mahine hazaron crore cross kar raha hai. Log fake loan apps aur fake task websites par paise transfer karne ke baad cyber cell jaate hain. NexVerify payment karne se **pehle** kaam karta hai—ye batata hai ki website jo claim kar rahi hai, public evidence use support karta hai ya nahi."*

### Step 2: High-Risk Scam Demo - QuickRupee (0:30 - 1:20)
- Search bar me `QuickRupee` type karo (Clear bolna: *"This is our simulated scam fixture"*).
- Screen par live timeline aayegi (SSE streaming).
- Dikhao: **HIGH RISK (Score 18/100)**.
- Deep Investigation Panel kholo:
  - *"Judges, dekhiye: Website claim karti hai 5 saal ka experience, par domain sirf 4 mahine purana hai (`AGE_CONTRADICTION`)."*
  - *"Page par unencrypted HTTP form hai jo user se account number aur OTP maang raha hai (`INSECURE_SENSITIVE_FORM`)."*
  - *"Fake Razorpay URL detect hua jise system ne gateway verify karne se reject kar diya."*
  - *"Aur notice kijiye: Humne UPI ID ko scam nahi bola—humne expose kiya ki ye recipient kahan lead karta hai."*

### Step 3: Clean Entity Comparison - SafeKosh / SBI (1:20 - 1:50)
- SafeKosh ya live official domain `sbi.bank.in` run karo.
- Dikhao: **VERIFIED_OFFICIAL (Score 100/100)**.
- *"Yahan dekhiye: Domain authorized `.bank.in` hai, RBI registered NBFC binding authentic hai, aur form submission encrypted HTTPS par hai."*

### Step 4: Evidence Report & Hash Integrity (1:50 - 2:30)
- Download PDF report button par click karo.
- PDF kholo aur dikhao:
  - Transparent Score Breakdown table.
  - Evidence Manifest aur individual SHA-256 content hashes.
  - Offline revision verification status.

### Step 5: Incident Complaint Draft & Cybercrime Portal Handoff (2:30 - 3:00)
- Investigation panel me neeche jao:
  - *"Agar kisi ke saath fraud ho chuka hai, toh NexVerify ek editable, pre-filled complaint draft generate karta hai jisme date, amount aur UTR daal sakte hain."*
  - Review checkbox tick karke direct official [cybercrime.gov.in](https://cybercrime.gov.in) button dikhao.
  - Concluding punchline: *"NexVerify claims nahi karta, evidence deta hai. We show what was found, why marks were deducted, and what remains unknown!"*

---
*Created for the NexVerify Team — Ready for Review & Presentation.*
