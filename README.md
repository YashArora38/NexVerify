# 🛡️ NexVerify

### AI-Assisted Fraud Risk Investigation & Blockchain-Ready Evidence Verification

**NexVerify** is a pre-payment fraud risk investigation platform designed to help users evaluate suspicious websites, applications, and financial services before trusting them with money or personal information.

Instead of providing an unexplained safe/unsafe label, NexVerify combines multiple verification sources, deterministic risk scoring, and evidence preservation to deliver transparent, understandable investigation results.

## 🚀 Key Features

- **Multi-Source Investigation:** Five specialized asynchronous checkers analyze lending, investment, company/domain, website/app, and reputation signals.
- **Explainable Risk Scoring:** A deterministic ProofGrid engine produces risk classifications with supporting findings.
- **Website & Payment Inspection:** Detects suspicious URLs, impersonation patterns, insecure forms, and questionable payment destinations.
- **AI-Assisted Research:** Uses Gemini-assisted discovery and extraction where configured, while keeping risk scoring rule-based.
- **Live Investigation Progress:** Server-Sent Events (SSE) provide real-time investigation updates.
- **Evidence Integrity:** SHA-256 hashes, Merkle trees, and versioned evidence records support tamper detection.
- **Blockchain Integration:** Ethereum-compatible smart contract and locally tested evidence anchoring, with Sepolia deployment support.
- **Investigation Reports:** Export findings as PDF, TXT, and offline-verifiable ZIP bundles.
- **Complaint Assistance:** Helps users prepare editable incident reports for official submission.

## 🏗️ Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React, Next.js, TypeScript |
| Backend | Python, FastAPI |
| AI Assistance | Google Gemini |
| Database | SQLite, SQLAlchemy |
| Blockchain | Ethereum, Solidity, ethers.js |
| Evidence Integrity | SHA-256, Merkle Trees |
| Streaming | Server-Sent Events (SSE) |
| Reporting | PDF, TXT, ZIP |

## ⚙️ How NexVerify Works

1. **Submit:** Enter a website URL, application, or financial service name.
2. **Investigate:** Specialized checkers collect available public evidence.
3. **Analyze:** ProofGrid applies explainable rules to produce a risk assessment.
4. **Preserve:** Evidence artifacts are hashed and recorded with revision history.
5. **Verify:** Saved evidence can be checked for modification; optional blockchain anchoring provides an independent commitment record.
6. **Export:** Download investigation reports and prepare complaint drafts.

## 🔐 Blockchain & Evidence Integrity

NexVerify uses blockchain to support **evidence integrity, not fraud detection**.

The platform generates cryptographic fingerprints of investigation evidence and creates a salted commitment representing the preserved evidence bundle.

An Ethereum smart contract can store this commitment, allowing future comparisons with the
