"use client";
import { useState } from "react";
import { API, type Result } from "@/lib/api";

export interface InvestigationData {
  coverage?: { pages_read: number; pages_attempted: number; limit: number };
  pages?: { url: string; final_url: string; status: string; http_status: number; evidence_id?: string; redirect_chain: { url: string; status: number }[] }[];
  upi_ids?: string[];
  gateway_references?: { provider: string; url: string }[];
  forms?: { action: string; method: string; sensitive_fields: string[] }[];
  downloads?: { url: string; type: string; host: string }[];
  observations?: string[];
  content_indicators?: string[];
  limitations?: string[];
}
export default function Investigation({ result, hindi }: { result: Result; hindi: boolean }) {
  const d = result.investigation;
  const [draft, setDraft] = useState(result.complaint_text);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  async function copyDraft() {
    try { await navigator.clipboard.writeText(draft); setCopied(true); setError(""); }
    catch { setError("Select and copy the draft below manually."); }
  }
  return <section className="investigation-panel" aria-label="Deep investigation">
    <div className="investigation-heading"><div><span className="investigation-kicker">PUBLIC EVIDENCE • READ ONLY</span><h2>{hindi ? "वेबसाइट की गहरी जाँच" : "Follow the evidence"}</h2><p>{hindi ? "पेमेंट, डेटा और डाउनलोड कहाँ जाते हैं?" : "Where do payments, personal data and downloads lead?"}</p></div><a className="btn small" href={`${API}/api/check/${result.check_id}/report.txt`}>Download text report</a></div>
    <div className="investigation-stats">
      <div><strong>{d?.coverage?.pages_read ?? 0}/{d?.coverage?.pages_attempted ?? 0}</strong><span>Public pages read</span></div>
      <div><strong>{d?.forms?.length ?? 0}</strong><span>Form destinations</span></div>
      <div><strong>{d?.downloads?.length ?? 0}</strong><span>Installer links</span></div>
      <div><strong>{d?.gateway_references?.length ?? 0}</strong><span>Gateway references</span></div>
    </div>
    {!d?.coverage && <p>Public website surfaces were not retrieved for this check. Store listings and other available sources are shown in the evidence cards.</p>}
    {!!d?.pages?.length && <div className="table-scroll"><table className="pg"><thead><tr><th>Observed page / final destination</th><th>Capture</th><th>Proof</th></tr></thead><tbody>{d.pages.map((p, i) => <tr key={i}><td><code>{p.url}</code>{p.url !== p.final_url && <p>→ {p.final_url}</p>}{p.redirect_chain.length > 1 && <details><summary>HTTP redirect trace</summary>{p.redirect_chain.map((h, j) => <p key={j}>{h.status} · {h.url}</p>)}</details>}</td><td>{p.status} · HTTP {p.http_status}</td><td>{p.evidence_id || "Unavailable"}</td></tr>)}</tbody></table></div>}
    <div className="investigation-grid"><div><h3>Payment recipient</h3>{d?.upi_ids?.map(u => <p key={u}><code>{u}</code></p>)}{d?.gateway_references?.map((g, i) => <p key={i}><b>{g.provider}</b><br/><code>{g.url}</code></p>)}<p className="investigation-note">A UPI ID, bank-details form or gateway reference alone does not prove fraud or safety. Confirm recipient name and merchant identity before paying.</p></div><div><h3>Data & installer destinations</h3>{d?.forms?.map((f, i) => <p key={i}><b>{f.method} · {f.sensitive_fields.length ? "Sensitive fields detected" : "Form"}</b><br/><code>{f.action}</code></p>)}{d?.downloads?.map((f, i) => <p key={i}><b>{f.type.toUpperCase()} · binary not analyzed</b><br/><code>{f.url}</code></p>)}{!d?.forms?.length && !d?.downloads?.length && <p>No form or installer link detected in the retrieved HTML. Dynamically loaded content may be missing.</p>}</div></div>
    {!!d?.content_indicators?.length && <p>Content indicators: {d.content_indicators.join(", ")} · context signals, not proof of fraud.</p>}
    {d?.observations?.map((o, i) => <p className="investigation-note" key={i}>{o}</p>)}
    <details><summary>What this investigation can and cannot establish</summary><ul>{(d?.limitations || ["Only available public evidence was checked. No binary reverse engineering, authenticated checkout or server-side inspection was performed."]).map((l, i) => <li key={i}>{l}</li>)}</ul></details>
    <div className="case-draft"><span className="investigation-kicker">REVIEW → COPY → OFFICIAL PORTAL</span><h3>{hindi ? "शिकायत का ड्राफ्ट तैयार करें" : "Prepare your complaint draft"}</h3><p>Fill in what actually happened, the date, amount and UTR. This draft stays in this browser; edits are not saved in the downloaded report. {result.demo && <strong>DEMO DATA: do not submit as a real allegation.</strong>}</p><textarea aria-label="Editable complaint draft" value={draft} onChange={e => {setDraft(e.target.value); setCopied(false); setReviewed(false);}} rows={12}/><label className="review-checkbox"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)}/> I have reviewed the facts and completed the draft.</label><div className="btns"><button className="btn small" onClick={copyDraft}>{copied ? "Draft copied" : "Copy edited draft"}</button>{reviewed && !result.demo && <><a className="btn small" href="https://cybercrime.gov.in/" target="_blank" rel="noreferrer">Open official complaint portal ↗</a><a className="btn ghost small" href="https://cybercrime.gov.in/webform/cyber_suspect.aspx" target="_blank" rel="noreferrer">Report a suspicious link ↗</a></>}</div>{error && <p role="alert">{error}</p>}<p className="investigation-note">Financial loss? Call 1930 promptly and contact your bank. Portal login/OTP and submission are completed by you. NexVerify has not filed a complaint or FIR.</p></div>
  </section>;
}
