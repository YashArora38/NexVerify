"use client";

import { useEffect, useState, useCallback } from "react";
import { BrowserProvider, Contract } from "ethers";
import { API, type Result } from "@/lib/api";

interface Revision {
  revision: number;
  revision_hash?: string;
  bundle_sha256?: string;
  merkle_root?: string;
  commitment?: string;
  created_at?: string;
  evidence_count?: number;
  reason?: string;
  actor?: string;
}

interface IntegrityResponse {
  integrity?: Revision;
  history?: Revision[];
  verification?: { ok?: boolean; valid?: boolean; errors?: string[]; [key: string]: unknown };
  anchor?: { status: string; chain_id?: number; contract_address?: string; broadcast_enabled?: boolean };
  graph?: { nodes?: unknown[]; edges?: unknown[]; [key: string]: unknown };
}

interface AnchorRecord {
  id?: number;
  check_id: string;
  revision_id: number;
  commitment: string;
  chain_id: number;
  contract_address: string;
  publisher: string;
  tx_hash: string;
  block_number: number;
  block_timestamp: string;
  confirmations: number;
  status: string;
  error_details?: string;
  created_at: string;
  verified_at?: string;
}

interface AnchorStatusResponse {
  anchored: boolean;
  status: string;
  commitment: string;
  chain_id: number;
  contract_address: string;
  tx_hash: string;
  block_number: number;
  confirmations: number;
  verified_at: string;
  explorer_url: string;
  record: AnchorRecord | null;
  config: {
    enabled: boolean;
    chain_id: number;
    contract_address: string;
    rpc_configured: boolean;
    explorer_base: string;
  };
}

const COMMITMENT_ANCHOR_ABI = [
  "function anchor(bytes32 commitment) external",
  "function isAnchored(address publisher, bytes32 commitment) external view returns (bool)",
  "function anchoredAt(bytes32 commitment) external view returns (uint256)",
  "function writers(address writer) external view returns (bool)",
  "function owner() external view returns (address)",
  "event CommitmentAnchored(address indexed publisher, bytes32 indexed commitment, uint256 timestamp)"
];

const SEPOLIA_CHAIN_ID = 11155111;

async function requestJson(path: string, body?: object): Promise<any> {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    cache: "no-store",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  return data;
}

export default function EvidenceIntegrity({ result, lang }: { result: Result; lang: "en" | "hi" }) {
  const hi = lang === "hi";
  const [data, setData] = useState<IntegrityResponse | null>(null);
  const [anchorStatus, setAnchorStatus] = useState<AnchorStatusResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [payload, setPayload] = useState<any>(null);
  const [showGraph, setShowGraph] = useState(false);

  // Web3 Wallet state
  const [hasProvider, setHasProvider] = useState(false);
  const [walletAccount, setWalletAccount] = useState<string | null>(null);
  const [walletChainId, setWalletChainId] = useState<number | null>(null);
  const [isAuthorizedWriter, setIsAuthorizedWriter] = useState<boolean | null>(null);
  const [txState, setTxState] = useState<{ status: string; hash?: string; message?: string }>({ status: "idle" });
  const [manualTxHash, setManualTxHash] = useState("");

  const base = `/api/check/${result.check_id}`;

  const loadAnchorStatus = useCallback(async () => {
    try {
      const status: AnchorStatusResponse = await requestJson(`${base}/anchor/status`);
      setAnchorStatus(status);
    } catch {
      // Backend may not have anchor endpoint configured or DB empty
    }
  }, [base]);

  useEffect(() => {
    let active = true;
    setPayload(null);
    setConsent(false);
    setError("");
    setTxState({ status: "idle" });

    if (typeof window !== "undefined" && (window as any).ethereum) {
      setHasProvider(true);
    }

    requestJson(`${base}/integrity`)
      .then(value => { if (active) setData(value); })
      .catch(reason => { if (active) setError(reason.message); });

    loadAnchorStatus();

    return () => { active = false; };
  }, [base, result, loadAnchorStatus]);

  // Check authorization when wallet account or target contract changes
  useEffect(() => {
    async function checkWriter() {
      if (!walletAccount || !anchorStatus?.config?.contract_address || typeof window === "undefined" || !(window as any).ethereum) {
        setIsAuthorizedWriter(null);
        return;
      }
      try {
        const provider = new BrowserProvider((window as any).ethereum);
        const contract = new Contract(anchorStatus.config.contract_address, COMMITMENT_ANCHOR_ABI, provider);
        const [writerAuthorized, ownerAddr] = await Promise.all([
          contract.writers(walletAccount).catch(() => false),
          contract.owner().catch(() => "")
        ]);
        const authorized = writerAuthorized || (ownerAddr && ownerAddr.toLowerCase() === walletAccount.toLowerCase());
        setIsAuthorizedWriter(!!authorized);
      } catch {
        setIsAuthorizedWriter(null);
      }
    }
    checkWriter();
  }, [walletAccount, anchorStatus?.config?.contract_address]);

  async function connectWallet() {
    if (typeof window === "undefined" || !(window as any).ethereum) {
      setError(hi ? "ब्राउज़र में Web3 वॉलेट (जैसे MetaMask) नहीं मिला।" : "No Web3 wallet (e.g. MetaMask) detected in browser.");
      return;
    }
    try {
      setBusy(true);
      setError("");
      const provider = new BrowserProvider((window as any).ethereum);
      const accounts = await provider.send("eth_requestAccounts", []);
      const network = await provider.getNetwork();
      setWalletAccount(accounts[0] || null);
      setWalletChainId(Number(network.chainId));
    } catch (e: any) {
      setError(e.message || "Failed to connect wallet");
    } finally {
      setBusy(false);
    }
  }

  async function switchNetwork(targetChainId: number) {
    if (typeof window === "undefined" || !(window as any).ethereum) return;
    try {
      setBusy(true);
      const hexChainId = "0x" + targetChainId.toString(16);
      await (window as any).ethereum.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: hexChainId }],
      });
      const provider = new BrowserProvider((window as any).ethereum);
      const network = await provider.getNetwork();
      setWalletChainId(Number(network.chainId));
    } catch (e: any) {
      setError(e.message || "Failed to switch network");
    } finally {
      setBusy(false);
    }
  }

  async function anchorWithWallet() {
    const revision = data?.integrity || (result as Result & { integrity?: Revision }).integrity;
    const commitment = revision?.commitment;
    const contractAddr = anchorStatus?.config?.contract_address;
    const targetChain = anchorStatus?.config?.chain_id || SEPOLIA_CHAIN_ID;

    if (!commitment || !contractAddr) {
      setError("Commitment or contract address missing.");
      return;
    }
    if (!consent) {
      setError(hi ? "कृपया पहले ऑन-चेन प्रसारण सहमति स्वीकार करें।" : "Please accept on-chain broadcast consent before proceeding.");
      return;
    }

    try {
      setBusy(true);
      setError("");
      setTxState({ status: "requesting", message: "Awaiting wallet signature in MetaMask..." });

      const provider = new BrowserProvider((window as any).ethereum);
      const signer = await provider.getSigner();
      const contract = new Contract(contractAddr, COMMITMENT_ANCHOR_ABI, signer);

      setTxState({ status: "signing", message: "Broadcasting anchor(bytes32) to network..." });
      const tx = await contract.anchor(commitment);

      setTxState({
        status: "pending",
        hash: tx.hash,
        message: `Transaction broadcast! Waiting for block confirmation (${tx.hash.slice(0, 10)}...)...`
      });

      const receipt = await tx.wait(1);
      if (!receipt || receipt.status !== 1) {
        throw new Error("Transaction reverted or failed on-chain.");
      }

      setTxState({
        status: "verifying",
        hash: tx.hash,
        message: `Confirmed in block #${receipt.blockNumber}! Verifying independently with backend RPC...`
      });

      // Submit to backend for cryptographic event verification & database recording
      const verifyRes = await requestJson(`${base}/anchor/verify`, {
        tx_hash: tx.hash,
        account: await signer.getAddress(),
        commitment
      });

      if (verifyRes.status === "confirmed") {
        setTxState({ status: "confirmed", hash: tx.hash, message: "Successfully verified and recorded on-chain!" });
        await loadAnchorStatus();
      } else {
        setTxState({ status: "pending", hash: tx.hash, message: verifyRes.message || "Recorded. Awaiting deeper block confirmations." });
      }
    } catch (e: any) {
      const msg = e.reason || e.message || "Failed to anchor transaction";
      setError(msg);
      setTxState({ status: "error", message: msg });
    } finally {
      setBusy(false);
    }
  }

  async function verifyManualTx() {
    if (!manualTxHash || !manualTxHash.startsWith("0x")) {
      setError("Enter a valid 66-character transaction hash starting with 0x");
      return;
    }
    try {
      setBusy(true);
      setError("");
      const res = await requestJson(`${base}/anchor/verify`, { tx_hash: manualTxHash.trim() });
      if (res.status === "confirmed") {
        await loadAnchorStatus();
        setManualTxHash("");
      } else {
        setError(res.message || "Verification did not confirm anchor.");
      }
    } catch (e: any) {
      setError(e.message || "Manual verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function reverifyOnChain() {
    try {
      setBusy(true);
      setError("");
      await requestJson(`${base}/anchor/reverify`);
      await loadAnchorStatus();
    } catch (e: any) {
      setError(e.message || "Re-verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true); setError("");
    try {
      const verification = await requestJson(`${base}/verify`);
      setData(previous => ({ ...previous, verification }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Verification failed"); }
    finally { setBusy(false); }
  }

  async function prepare() {
    setBusy(true); setError("");
    try { setPayload(await requestJson(`${base}/anchor/prepare`, { consent })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Preparation failed"); }
    finally { setBusy(false); }
  }

  function downloadPayload() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = "nexverify-unsigned-anchor.json";
    link.click(); URL.revokeObjectURL(url);
  }

  const revision = data?.integrity || (result as Result & { integrity?: Revision }).integrity;
  const valid = data?.verification?.ok ?? data?.verification?.valid;
  const isAnchored = anchorStatus?.anchored || anchorStatus?.status === "anchored" || anchorStatus?.status === "confirmed";
  const targetChainId = anchorStatus?.config?.chain_id || SEPOLIA_CHAIN_ID;
  const chainMismatch = walletChainId !== null && walletChainId !== targetChainId;

  return (
    <section className="block integrity-panel">
      <div className="integrity-heading">
        <div>
          <span className="integrity-kicker">PROVENANCE / EVIDENCE INTEGRITY</span>
          <h2>{hi ? "प्रमाण इतिहास और ब्लॉकचेन एंकरिंग" : "Evidence History & Blockchain Anchoring"}</h2>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span className={`integrity-state ${valid === true ? "verified" : ""}`}>
            {valid === true ? "Local bytes verified" : valid === false ? "Integrity failed" : "Bytes unverified"}
          </span>
          {isAnchored && (
            <span className="integrity-state verified" style={{ background: "rgba(34,197,94,0.18)", borderColor: "#22c55e", color: "#86efac" }}>
              ✓ Sepolia Anchored
            </span>
          )}
        </div>
      </div>

      <p className="dim">
        {hi
          ? "SHA-256 हैश और मर्कल ट्री लोकल फाइलों में बदलाव पहचानते हैं। Ethereum Sepolia पर 32-बाइट साल्टेड कमिटमेंट सार्वजनिक और अपरिवर्तनीय टाइमस्टैम्प एंकर प्रदान करता है।"
          : "SHA-256 hashes and Merkle roots detect local file tampering. Ethereum Sepolia anchoring commits a salted 32-byte hash to provide an immutable, independent timestamp proof."}
      </p>

      {result.demo && <p className="integrity-notice">Simulated demo evidence — not a live-source verification.</p>}

      {revision ? (
        <>
          <div className="integrity-facts">
            <div><small>Revision</small><b>#{revision.revision}</b></div>
            <div><small>Evidence artifacts</small><b>{revision.evidence_count ?? "—"}</b></div>
            <div>
              <small>Blockchain Status</small>
              <b style={{ color: isAnchored ? "#86efac" : anchorStatus?.status === "pending" ? "#fde047" : "#94a3b8" }}>
                {isAnchored ? "Anchored" : anchorStatus?.status === "pending" ? "Pending" : "Not Anchored"}
              </b>
            </div>
            <div><small>Network</small><b>{targetChainId === 11155111 ? "Sepolia" : `Chain ${targetChainId}`}</b></div>
          </div>

          <label className="integrity-hash">Bundle SHA-256<code>{revision.bundle_sha256}</code></label>
          <label className="integrity-hash">Merkle Root<code>{revision.merkle_root}</code></label>
          <label className="integrity-hash">Salted On-Chain Commitment (bytes32)<code>{revision.commitment}</code></label>

          <div className="integrity-actions">
            <button className="btn ghost" disabled={busy} onClick={verify}>
              {busy ? "Working…" : "Verify Local Evidence Files"}
            </button>
            <a className="btn ghost" href={`${API}${base}/bundle.zip`}>Download Private Offline Bundle (.zip)</a>
            <button className="btn ghost" onClick={() => setShowGraph(!showGraph)}>
              {showGraph ? "Hide" : "View"} Dependency Trace
            </button>
          </div>

          {data?.verification && <pre className="integrity-json">{JSON.stringify(data.verification, null, 2)}</pre>}
          {showGraph && <pre className="integrity-json">{JSON.stringify(data?.graph || { note: "No dependency graph recorded for this legacy result." }, null, 2)}</pre>}

          <details className="integrity-history">
            <summary>Append-only revision history ({data?.history?.length ?? 0})</summary>
            {data?.history?.map(item => (
              <div key={item.revision} className="integrity-history-item">
                <b>Revision {item.revision}</b><span>{item.created_at}</span><code>{item.revision_hash}</code>
              </div>
            ))}
          </details>

          {/* ON-CHAIN ANCHORING SECTION */}
          <div className="integrity-anchor" style={{ marginTop: "24px", paddingTop: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
              <h3 style={{ margin: 0 }}>
                {hi ? "Ethereum Sepolia पर सार्वजनिक एंकरिंग" : "Ethereum Sepolia Public Anchoring"}
              </h3>
              {isAnchored && (
                <button className="btn ghost" style={{ fontSize: "12px", padding: "6px 12px" }} disabled={busy} onClick={reverifyOnChain}>
                  {busy ? "Checking..." : "Re-verify On-Chain"}
                </button>
              )}
            </div>

            {isAnchored ? (
              <div style={{ background: "rgba(16, 50, 36, 0.45)", border: "1px solid #10b981", borderRadius: "12px", padding: "18px", margin: "14px 0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
                  <span style={{ fontSize: "18px" }}>✅</span>
                  <div>
                    <b style={{ color: "#86efac", fontSize: "15px" }}>Independently Verified on Ethereum Sepolia</b>
                    <div style={{ fontSize: "12px", color: "#9ca3af" }}>
                      This investigation commitment is permanently recorded in the smart contract ledger.
                    </div>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px", fontSize: "12px" }}>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Transaction Hash:</span>
                    <div style={{ marginTop: "4px" }}>
                      <a
                        href={anchorStatus?.explorer_url || `https://sepolia.etherscan.io/tx/${anchorStatus?.tx_hash}`}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: "#60a5fa", wordBreak: "break-all", textDecoration: "underline" }}
                      >
                        {anchorStatus?.tx_hash} ↗
                      </a>
                    </div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Block & Confirmations:</span>
                    <div style={{ marginTop: "4px", color: "#e2e8f0" }}>
                      Block #{anchorStatus?.block_number} ({anchorStatus?.confirmations ?? 1}+ confirmations)
                    </div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Publisher Account:</span>
                    <div style={{ marginTop: "4px", color: "#e2e8f0", wordBreak: "break-all" }}>
                      {anchorStatus?.record?.publisher || "Recorded on contract"}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Contract Address:</span>
                    <div style={{ marginTop: "4px", color: "#e2e8f0", wordBreak: "break-all" }}>
                      {anchorStatus?.contract_address}
                    </div>
                  </div>
                  {anchorStatus?.verified_at && (
                    <div>
                      <span style={{ color: "#94a3b8" }}>Backend Verification Timestamp:</span>
                      <div style={{ marginTop: "4px", color: "#e2e8f0" }}>
                        {new Date(anchorStatus.verified_at).toLocaleString()}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <>
                <p className="dim" style={{ marginBottom: "16px" }}>
                  {hi
                    ? "केवल 32-बाइट साल्टेड क्रिप्टोग्राफिक कमिटमेंट कॉन्ट्रैक्ट में प्रकाशित होता है। कोई यूआरएल, नाम, व्यक्तिगत डेटा, या सबूत फ़ाइलें ब्लॉकचेन पर नहीं भेजी जाती हैं।"
                    : "Only the salted 32-byte cryptographic commitment is stored in the contract. No URLs, personal names, phone numbers, evidence files, or salts are published on-chain."}
                </p>

                <p className="mono" style={{ background: "rgba(0,0,0,0.2)", padding: "10px", borderRadius: "8px" }}>
                  Target Network: {targetChainId === 11155111 ? "Ethereum Sepolia (Chain ID 11155111)" : `Chain ID ${targetChainId}`} · Contract: {anchorStatus?.config?.contract_address || "Not configured"}
                </p>

                {/* Browser Wallet Interaction Section */}
                <div style={{ border: "1px solid rgba(147, 197, 253, 0.2)", borderRadius: "12px", padding: "16px", marginTop: "16px", background: "rgba(15, 23, 42, 0.5)" }}>
                  <h4 style={{ margin: "0 0 10px 0", fontSize: "14px", color: "#bfdbfe" }}>
                    {hi ? "विकल्प 1: Web3 ब्राउज़र वॉलेट से साइन और ब्रॉडकास्ट करें" : "Option 1: Sign & Broadcast with Web3 Wallet (MetaMask / EIP-1193)"}
                  </h4>

                  {!hasProvider ? (
                    <p style={{ color: "#94a3b8", fontSize: "13px" }}>
                      No Web3 browser wallet extension detected (e.g. MetaMask). You can install MetaMask or use manual/offline signing below.
                    </p>
                  ) : !walletAccount ? (
                    <div>
                      <p style={{ fontSize: "13px", color: "#cbd5e1" }}>
                        Connect your Web3 wallet to sign and broadcast the commitment directly from your browser.
                      </p>
                      <button className="btn ghost" disabled={busy} onClick={connectWallet} style={{ borderColor: "#3b82f6", color: "#93c5fd" }}>
                        {busy ? "Connecting..." : "Connect Web3 Wallet"}
                      </button>
                    </div>
                  ) : (
                    <div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "16px", alignItems: "center", marginBottom: "12px", fontSize: "13px" }}>
                        <div>
                          <span style={{ color: "#94a3b8" }}>Connected: </span>
                          <code style={{ color: "#60a5fa" }}>{walletAccount.slice(0, 8)}...{walletAccount.slice(-6)}</code>
                        </div>
                        <div>
                          <span style={{ color: "#94a3b8" }}>Chain ID: </span>
                          <b style={{ color: chainMismatch ? "#f87171" : "#4ade80" }}>{walletChainId ?? "Unknown"}</b>
                          {chainMismatch && <span style={{ color: "#f87171" }}> (Expected {targetChainId})</span>}
                        </div>
                        {isAuthorizedWriter !== null && (
                          <div>
                            <span style={{ color: "#94a3b8" }}>Role: </span>
                            <b style={{ color: isAuthorizedWriter ? "#4ade80" : "#f87171" }}>
                              {isAuthorizedWriter ? "Authorized Writer ✓" : "Unauthorized Writer ✗"}
                            </b>
                          </div>
                        )}
                      </div>

                      {chainMismatch && (
                        <div style={{ marginBottom: "14px" }}>
                          <button className="btn ghost" disabled={busy} onClick={() => switchNetwork(targetChainId)} style={{ borderColor: "#f59e0b", color: "#fcd34d" }}>
                            Switch Network to Sepolia ({targetChainId})
                          </button>
                        </div>
                      )}

                      {isAuthorizedWriter === false && (
                        <div style={{ background: "rgba(220, 38, 38, 0.15)", border: "1px solid #ef4444", borderRadius: "8px", padding: "10px 14px", margin: "10px 0", fontSize: "12px", color: "#fca5a5" }}>
                          Wallet <code>{walletAccount}</code> is not listed as an approved writer on contract <code>{anchorStatus?.config?.contract_address}</code>. Only authorized writers or the contract owner can anchor commitments.
                        </div>
                      )}

                      <label className="integrity-consent" style={{ margin: "14px 0" }}>
                        <input
                          type="checkbox"
                          checked={consent}
                          onChange={e => setConsent(e.target.checked)}
                        />
                        <span>
                          {hi
                            ? "मैं पुष्टि करता हूँ कि यह 32-बाइट साल्टेड हैश Ethereum Sepolia पर स्थायी रूप से प्रकाशित हो सकता है। कोई निजी डेटा या साक्ष्य फ़ाइलें ब्लॉकचेन पर नहीं भेजी जाएंगी।"
                            : "I confirm and consent to publishing this 32-byte salted hash on Ethereum Sepolia. No private personal data, URLs, or evidence files will be published."}
                        </span>
                      </label>

                      <button
                        className="btn ghost"
                        disabled={!consent || busy || chainMismatch || isAuthorizedWriter === false || !anchorStatus?.config?.contract_address}
                        onClick={anchorWithWallet}
                        style={{
                          background: consent && !chainMismatch && isAuthorizedWriter !== false ? "rgba(37, 99, 235, 0.25)" : undefined,
                          borderColor: "#3b82f6",
                          color: "#93c5fd",
                          fontWeight: 600
                        }}
                      >
                        {busy ? "Broadcasting..." : "Sign & Anchor on Sepolia"}
                      </button>

                      {txState.message && (
                        <p style={{ marginTop: "12px", fontSize: "12px", color: txState.status === "error" ? "#fca5a5" : "#93c5fd" }}>
                          {txState.message}
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* Option 2: Verify existing external transaction */}
                <div style={{ border: "1px solid rgba(147, 197, 253, 0.15)", borderRadius: "12px", padding: "16px", marginTop: "16px", background: "rgba(15, 23, 42, 0.3)" }}>
                  <h4 style={{ margin: "0 0 10px 0", fontSize: "14px", color: "#cbd5e1" }}>
                    {hi ? "विकल्प 2: पहले से प्रस्तुत ट्रांज़ैक्शन को सत्यापित करें" : "Option 2: Verify Existing On-Chain Transaction Hash"}
                  </h4>
                  <p style={{ fontSize: "12px", color: "#94a3b8" }}>
                    If you anchored this commitment using the CLI deployer script, Foundry, or an airgapped key, paste the transaction hash here to verify and record it in the ledger.
                  </p>
                  <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "10px" }}>
                    <input
                      type="text"
                      placeholder="0x... (66-character transaction hash)"
                      value={manualTxHash}
                      onChange={e => setManualTxHash(e.target.value)}
                      style={{
                        flex: "1 1 280px",
                        background: "rgba(0,0,0,0.3)",
                        border: "1px solid #475569",
                        borderRadius: "8px",
                        padding: "8px 12px",
                        color: "#fff",
                        fontSize: "12px",
                        fontFamily: "monospace"
                      }}
                    />
                    <button className="btn ghost" disabled={busy || !manualTxHash.trim()} onClick={verifyManualTx}>
                      {busy ? "Verifying..." : "Verify On-Chain Tx"}
                    </button>
                  </div>
                </div>

                {/* Option 3: Offline preparation */}
                <div style={{ border: "1px solid rgba(147, 197, 253, 0.1)", borderRadius: "12px", padding: "16px", marginTop: "16px", background: "rgba(15, 23, 42, 0.2)" }}>
                  <h4 style={{ margin: "0 0 10px 0", fontSize: "14px", color: "#94a3b8" }}>
                    {hi ? "विकल्प 3: ऑफ़लाइन अहस्ताक्षरित पेलोड तैयार करें" : "Option 3: Air-Gapped / Offline Payload Preparation"}
                  </h4>
                  <p className="dim" style={{ fontSize: "12px" }}>
                    Prepares the exact ABI-encoded calldata for anchor(bytes32) without broadcasting. You can inspect or sign this payload using an offline hardware signer.
                  </p>
                  <label className="integrity-consent">
                    <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />
                    <span>I consent to generating an unsigned commitment payload for inspection. Nothing will be broadcast.</span>
                  </label>
                  <button className="btn ghost" disabled={!consent || busy} onClick={prepare}>
                    Prepare Unsigned Payload
                  </button>
                  {payload && (
                    <div style={{ marginTop: "12px" }}>
                      <pre className="integrity-json">{JSON.stringify(payload, null, 2)}</pre>
                      <button className="btn ghost" style={{ marginTop: "8px" }} onClick={downloadPayload}>
                        Download Unsigned JSON Payload
                      </button>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </>
      ) : (
        <p className="dim">No versioned bundle is available for this older result. Run a fresh check to create one.</p>
      )}

      {error && <p role="alert" className="integrity-error" style={{ marginTop: "16px" }}>{error}</p>}
    </section>
  );
}
