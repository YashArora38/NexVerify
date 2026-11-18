# NexVerify: MSIT demo and honest technical review

## Open the product
Double-click START-NEXVERIFY.bat. Open http://127.0.0.1:3000. Keep the launcher running.
Use a fresh check after an upgrade. Existing saved reports describe their original captures.

## The strongest 3-minute demo
1. Start QuickRupee (explicitly say: simulated scam fixture). Show the computed HIGH RISK verdict, publisher mismatch, domain-age contradiction, and new unencrypted account/OTP form. Open Follow the evidence: UPI and APK destination are visible; the fake Razorpay hostname is not recognized as a gateway. UPI itself is not penalized.
2. Run SafeKosh Finance (simulated clean financial service). Explain that an ordinary financial form or store listing alone is neither proof of scam nor proof of safety.
3. If internet works, check https://sbi.bank.in. Distinguish official-domain recognition from the availability of live page captures; a bot block is not a scam finding. Unknown websites may correctly remain UNKNOWN.
4. Download the PDF and text report. Show deductions, source evidence IDs, UTC captures and SHA-256 hashes. Demo reports are labelled simulated.
5. Show the editable complaint draft. Explain that the user reviews facts, enters incident details, and completes official portal login/OTP. No automatic FIR claim. Do not submit demo evidence.

## A credible pitch
“NexVerify is a pre-payment investigation assistant. It separates what a website claims from what public evidence supports. It explains where data and payment links lead, identifies concrete risky patterns, and produces a reviewable evidence package. Missing evidence stays unknown; a bank-details form, UPI ID or app-store listing alone never settles the verdict.”

## What was wrong with the pasted Antigravity review
- HTML string matches were labelled verified payment gateways; spoofed domains and copied text could trigger them.
- A mobile-number UPI handle was treated as proof of personal payment and heavily penalized. Its format does not establish recipient type or fraud.
- Third-party contact forms and shorteners were assigned severe penalties without sensitive-field context.
- Apple listing availability was marked verified even when fetch failed. A store URL was used as strong safety evidence.
- User reporting that a site asks for money/OTP/Aadhaar previously caused a 70-point penalty on its own.
- The launcher explicitly disables blockchain broadcast. An anchor preparation payload is not a Sepolia transaction receipt.
- Hashes detect changes relative to recorded hashes; they do not establish truth, author identity, court admissibility or an independently trusted timestamp.
- The “100% safe”, “bulletproof”, “India's first” and guaranteed-winner claims were unsupported.

## Improvements implemented
- HTTPS gateway endpoint parsing with exact host matching; displayed as references, never merchant verification.
- Sensitive-field form analysis: HTTP transport, GET leakage and unverified cross-domain destinations. Ordinary forms and UPI handles receive no automatic fraud penalty.
- Same-site public informational crawl: root plus at most 3 selected pages, bounded request time, existing SSRF-guarded fetcher. No checkout submissions or installer execution.
- Raw public HTML and HTTP redirect observations captured in hashed evidence; per-page availability and evidence IDs.
- Installer links, script/iframe sources, declared refresh targets, encoded-script heuristics and content-category indicators. Heuristics are not malware verdicts.
- A dedicated investigation UI, PDF section, text report endpoint and editable complaint draft with official portal handoff.
- App-listing false certainty removed. Cache engine version bumped so new checks do not replay old scoring results.
- Next.js patched from 16.4.2 to 16.4.6 after an npm advisory; source install audit reported zero known vulnerabilities.

## Remaining gaps, in priority order
1. Real labelled benchmark: measure precision/recall and false-positive rate on genuine banks, small merchants, hosted checkout and independently documented phishing. Passing unit tests is not detection accuracy.
2. Identity binding: verify publisher-to-domain and merchant-to-beneficiary relationships using authoritative sources or provider integrations; a gateway SDK alone cannot establish these.
3. Malware sandbox: APK signing-certificate verification, manifest permission extraction, static analysis and isolated dynamic analysis require a separate controlled service. This build only inventories download links, not binary reverse engineering.
4. Authenticated/dynamic checkout and server-side code are not inspected. Current bounded HTML coverage is intentionally shown. External scripts are inventoried, not all retrieved or executed.
5. Domain registrant identity may be privacy-protected; creation dates do not prove the app's release date or who runs a scam.
6. Production deployment needs broader security review, dependency maintenance, privacy/retention policy, abuse limits and measured network-failure behavior. This is a local hackathon prototype, not a certification service.
7. Verified blockchain deployment and independently confirmed receipts would be needed before claiming on-chain anchoring. Hash verification already works without such claims.

## Primary references checked
- RBI Digital Lending Directions 2025: directory inclusion is not RBI registration, authorization or endorsement; lender affiliation must be independently understood.
  https://www.rbi.org.in/scripts/FS_Notification.aspx?Id=12848
- RBI cautions against unauthorised lending apps and advises verifying the provider before sharing KYC documents.
  https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=50846
- National Cybercrime Portal Report Suspect supports suspicious URLs/handles; victims are directed to the official portal or 1930.
  https://cybercrime.gov.in/webform/cyber_suspect.aspx

## Re-run verification
From the bundle's parent directory:
NexVerify-Ready-To-Run\runtime\python\python.exe -m pytest NexVerify-Ready-To-Run\backend\tests -q -o asyncio_mode=auto
Frontend: cd source\frontend, then npm ci and npm run build. The launcher serves the packaged frontend directory, so source changes need repackaging.

## Verification completed
- Backend: 163 passed, 1 skipped (full suite with asyncio_mode=auto).
- Production build and TypeScript checks passed on Next.js 16.4.6.
- Same-origin running-app smoke check: new engine, unsafe form finding, spoofed gateway rejection, installer inventory, PDF/text export, evidence integrity and ZIP bundle passed.
- Nine-page demo PDF rendered and visually inspected.
- Live https://sbi.bank.in: VERIFIED_OFFICIAL, 100, partial=true, listing unavailable. Official domain recognition does not mean content was successfully inspected.
- Desktop complaint editing and simulated-data submission guard verified; mobile overflow identified and corrected.
- Prior packaged frontend retained in frontend-before-investigation for recovery.
