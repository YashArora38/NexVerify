# NexVerify: technical invention-candidate disclosure

**Status:** implemented technical mechanisms for review, not an assertion of novelty, patentability, inventorship, or a patent grant. Adding a blockchain, Merkle tree, hashes, AI, risk scores, or a web UI by itself does not establish an inventive step. The earlier patent-readiness review identifies substantial existing work in phishing classification, automated fact checking and cryptographic timestamping. Do not publish the invention before discussing filing strategy with a qualified patent professional.

## Proposed technical problem

A multi-source scam-verification system can revise its verdict after delayed official lookups, new user evidence, changed rules or disputes. Mutable result rows, missing source artifacts, untyped AI assertions and uncontrolled disclosure can make it difficult to reproduce what evidence supported which decision, distinguish a user claim from an authoritative source, and prepare a public integrity commitment without leaking personal data. A chain record alone would not solve those problems.

## Implemented interaction worth examining

| Stage | Concrete implementation | Observable property |
| --- | --- | --- |
| Capture | Exclusive evidence writes; artifact metadata records hash, source, capture time and simulation flag | New captures do not overwrite old file bytes |
| Revision | Locked append-only revision directories, frozen result/manifests/artifacts, previous-revision hash | Earlier decisions remain available after correction/dispute |
| Dependency trace | Typed subject/claim/evidence graph with dependency edges and changed-evidence/rules/affected-hit diff | Unsupported claims remain heuristic/unverified; source changes are visible |
| Commitment | Versioned canonical result/manifest hashes, domain-separated ordered artifact Merkle tree, aggregate bundle digest | Metadata and evidence byte integrity are bound together |
| Privacy boundary | Random 256-bit off-chain salt and domain-separated commitment to the bundle digest | Unsigned public payload does not expose raw query, evidence, personal data or salt |
| Gate | Re-verify current revision **and its predecessors** before allowing bundle export or unsigned anchoring | A corrupted predecessor blocks release/preparation rather than certifying a newer projection |
| Preparation | Consent-gated validated chain/address, fixed ABI `anchor(bytes32)` unsigned call, permanently disabled broadcasting | No key/signing/transaction submission exists in the app |
| Correction | Consented minimized human assertion is retained, claim extraction and verdict are recomputed, a new revision is written | A correction is auditable and never silently rewrites the older decision |

### Candidate A — lineage-gated release of decision commitments

A candidate combination is a verification decision's dependency-aware, frozen artifact/result commitment coupled to a release gate that validates all prior revisions before exporting an offline bundle or preparing a public cryptographic commitment. The system refuses release when a predecessor's retained artifact is corrupted even if the newest decision row appears intact. Its technical effect to measure is detection of evidence/metadata/history substitution and prevention of releasing an apparently valid new commitment after lineage corruption.

Implemented files: `backend/app/provenance.py`, `evidence.py`, `main.py`, and `tests/test_patent_features.py`. The test `test_revision_bundle_and_consent_api` corrupts a predecessor artifact and demonstrates failed verification plus HTTP 409 refusal for bundle export and anchor preparation. This is a concrete reproducible behavior, **not proof that the combination is new**. Append-only ledgers and provenance gating are established concepts; a professional must search claim-by-claim for the exact interaction.

### Candidate B — typed uncertainty preserved across evidence corrections

The typed graph retains a subject identity as unverified, claim nodes as unverified when evidence exists and heuristic when dependencies are absent, and evidence nodes as captured/simulated. It explicitly reports `ownership_verified=false`; it does not convert “captured” into “true.” Changes in rule metadata, evidence metadata/dependencies and affected rule-hit IDs are attached to revisions. User-provided statements stay user assertions after scoring and do not become an official registry confirmation merely because they were uploaded or hashed.

Current limitation: the graph and dependency diff are audit traces. They do not yet implement transitive selective re-execution, cryptographic domain-control attestation, official record linkage, signed source attestations, confidence calibration, or a policy that universally prevents every unsupported signal from affecting scoring. Full scoring currently recomputes. These would be **future developments**, not implemented claims. The existing curated official-domain registry still has its own assumptions and is not a fresh ownership challenge.

### Candidate C — privacy-separated, no-broadcast anchoring preparation

The bundle digest binds exact off-chain evidence and decision metadata; a random per-revision salt is retained only inside the private bundle/ledger. Public calldata contains just a 32-byte salted commitment and chain/contract routing fields. Preparation requires explicit consent and successful integrity verification; simulated demo evidence is labeled simulated. The Solidity registry records write-once per-publisher commitments and an event, with an immutable owner and a writer allowlist; it has no upgrade/delete/rewrite path.

This improves the separation between private audit material and possible future public commitment publication. It is still based on well-known cryptographic commitments and EVM ABI encoding. It does not provide zero knowledge, guaranteed anonymization, encrypted storage, a trusted timestamp, or proof of the truth of the evidence. No contract has been deployed and no receipt/finality verifier is implemented. `anchored` cannot currently be established by this application.

## Format and threat assumptions

Canonicalization is explicitly **`python-json-v1`**, using UTF-8, sorted string keys, compact separators and rejection of NaN/infinity. It is not advertised as RFC 8785/JCS. Result hashes exclude the returned `integrity` field to avoid a circular digest. Artifact hashing includes metadata plus content under a domain separator; Merkle leaves and internal nodes use different SHA-256 domains. Ordered pairing is intentional and is **not** the default sorted Keccak tree expected by OpenZeppelin `MerkleProof`.

The salted commitment uses `SHA256("NEXVERIFY/COMMITMENT/v1\\0" || salt_bytes || bundle_sha256_ascii)`. The exact bytes, versions and implementation are retained for reproducibility. The EVM selector is the first four bytes of Ethereum Keccak-256 of `anchor(bytes32)`: `0x54be8d59`, independently confirmed by the Solidity compiler/ABI comparison.

The ledger is application-level append-only on ordinary filesystem storage, not physical WORM storage. A privileged attacker can rewrite the whole ledger and recompute all self-authenticating hashes if no trustworthy external root/checkpoint exists. Self-reported local time is not independently trusted. Hashes can show consistency only relative to a trusted previously held digest/commitment. Salts prevent straightforward guessing only while undisclosed and sufficiently random; hashes must not be treated as erased/anonymized personal data. Authorized bundle recipients receive retained private data and the salt. A standalone exported later revision does not independently reconstruct its complete earlier history; local verification checks all predecessors and the bundle reports that offline limitation.

## Reproducible workflows

Run normal backend tests from `backend`: `python -m pytest tests -q`. On this specific desktop, the original venv could not start; an isolated `.work/tools/python312` test runtime was used instead. The full local suite passed **145 tests**, with one framework deprecation warning. Use a currently patched supported Python for future internet deployment, not that test-only runtime.

To inspect the evidence workflow, run a fresh demo such as QuickRupee, open Evidence history & integrity, verify retained evidence, download the private offline ZIP, and use `python backend/tools/verify_bundle.py path/to/bundle.zip`. Submit consented human text to create the next revision. Historical revisions remain available through `/api/check/{id}/ledger`. In a configured **local test**, unsigned preparation uses `/api/check/{id}/anchor/prepare`; the shipped operator configuration leaves it disabled.

Solidity validation: from `blockchain`, use `npm ci` then `npm test`, with `PYTHON` set to a usable interpreter if necessary. The compiler is pinned. This compiles and compares ABI/Python vectors only; it does not deploy or send anything.

## Evidence a patent professional will still need

Prepare a dated invention disclosure identifying actual human inventors and contributions; a claim-element comparison against patents and technical publications; architecture/state-transition diagrams; exact algorithms/formats and alternatives; failure cases and working examples; and measurements against appropriate baselines. Relevant measurements include corruption detection under metadata/body/history attacks, latency/overhead of freezing and chain verification, storage growth and restore integrity, link/claim decision accuracy with source coverage/abstention, and privacy tests for payload leakage. Use independent/time-separated test data, not just the current hand-written demonstrations.

For an Indian filing, discuss computer-related invention exclusions/technical effect, novelty/inventive step, sufficiency and provisional-versus-complete disclosure with counsel. A provisional filing does not make later-added subject matter automatically eligible for its earlier date. The jurisdiction, inventors, ownership and disclosure history have not been confirmed in this task. Prior-art and filing details are in the separate patent-readiness report. No application, legal submission, public disclosure, publication or deployment has been performed.
