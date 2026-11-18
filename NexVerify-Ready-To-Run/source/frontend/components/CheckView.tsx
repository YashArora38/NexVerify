"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Footer, SearchForm, TopBar } from "@/components/Chrome";
import Investigation from "@/components/Investigation";
import EvidenceIntegrity from "@/components/EvidenceIntegrity";
import { Html, Icon } from "@/components/Icon";
import { API, type Card, flagCheck, getHealth, type Health, type Result, slugify, startCheck, type Subject, submitHumanAssist } from "@/lib/api";
import { CHECKS, ICONS, L, MARK, PAID, t, TODO, VERDICT } from "@/lib/copy";
import { useLang } from "@/lib/useLang";

const ORDER = ["rbi", "sebi", "company", "listing", "news"] as const;
const FINISHED = new Set(["done", "skipped", "unverified", "error"]);

interface AgentState {
  state: string;
  note?: string;
  steps: { at: string; msg: string }[];
}

const timeOf = (iso: string) => {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
};

function Ring({ score, color, label }: { score: number; color: string; label: string }) {
  const r = 70;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(100, score)) / 100);
  return (
    <div className="ring">
      <svg viewBox="0 0 170 170" aria-hidden="true">
        <circle cx="85" cy="85" r={r} fill="none" stroke="rgba(150,172,214,0.14)" strokeWidth="14" />
        <circle cx="85" cy="85" r={r} fill="none" stroke={color} strokeWidth="14" strokeLinecap="round" strokeDasharray={c.toFixed(1)} strokeDashoffset={off.toFixed(1)} />
      </svg>
      <div className="val">
        <div>
          <b>{label}</b>
          <small>/100</small>
        </div>
      </div>
    </div>
  );
}

export default function CheckView({ query }: { query: string }) {
  const [lang, setLang] = useLang();
  const i = L(lang);
  const router = useRouter();
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  const [input, setInput] = useState(query);
  const [nonce, setNonce] = useState(0);
  const [fresh, setFresh] = useState(false);
  const [checkId, setCheckId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [subject, setSubject] = useState<Subject | null>(null);
  const [demo, setDemo] = useState(false);
  const [cached, setCached] = useState(false);
  const [agents, setAgents] = useState<Record<string, AgentState>>({});
  const [cards, setCards] = useState<Card[]>([]);
  const [liveScore, setLiveScore] = useState(100);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const started = useRef<string | null>(null);

  // Dispute / Flagging state
  const [showFlagForm, setShowFlagForm] = useState(false);
  const [flagReason, setFlagReason] = useState("disputeReason1");
  const [flagComment, setFlagComment] = useState("");
  const [flagSubmitted, setFlagSubmitted] = useState(false);
  const [flagLoading, setFlagLoading] = useState(false);
  const [flagCount, setFlagCount] = useState(0);

  // Human Assist state
  const [haUrl, setHaUrl] = useState("");
  const [haText, setHaText] = useState("");
  const [haQ1, setHaQ1] = useState("WhatsApp");
  const [haQ2, setHaQ2] = useState("No");
  const [haQ3, setHaQ3] = useState("");
  const [haLoading, setHaLoading] = useState(false);
  const [haConsent, setHaConsent] = useState(false);

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);
  useEffect(() => setInput(query), [query]);

  // 1) create the check once per (query, nonce)
  useEffect(() => {
    const key = `${query}#${nonce}`;
    if (started.current === key) return;
    started.current = key;
    setCheckId(null);
    setResult(null);
    setError(null);
    startCheck(query, fresh)
      .then(setCheckId)
      .catch((reason) => setError(reason instanceof Error ? reason.message : t("offline", lang)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, nonce]);

  // 2) follow its live stream (the server replays history, so state is rebuilt from scratch)
  useEffect(() => {
    if (!checkId) return;
    setAgents({});
    setCards([]);
    setLiveScore(100);
    setResult(null);
    setError(null);
    setCached(false);
    setStatus("");
    const es = new EventSource(`${API}/api/check/${checkId}/stream`, { withCredentials: true });
    const on = (name: string, fn: (d: any) => void) =>
      es.addEventListener(name, (e) => {
        const m = e as MessageEvent;
        if (m.data === undefined) return;
        try {
          fn(JSON.parse(m.data));
        } catch {}
      });
    on("status", (d) => {
      setStatus(d.message || "");
      if (d.cached) setCached(true);
    });
    on("subject", (d) => {
      setSubject(d.subject);
      setDemo(!!d.demo);
    });
    on("agent", (d) => {
      setAgents((prev) => {
        const cur: AgentState = prev[d.key] || { state: "queued", steps: [] };
        const steps = [...cur.steps];
        if (d.step && d.step !== "Starting" && steps[steps.length - 1]?.msg !== d.step) steps.push({ at: d.at || new Date().toISOString(), msg: d.step });
        return { ...prev, [d.key]: { state: d.state || cur.state, note: d.note ?? cur.note, steps } };
      });
    });
    on("cards", (d) => {
      setCards(d.cards || []);
      if (typeof d.score === "number") setLiveScore(d.score);
    });
    on("result", (d: Result) => {
      setResult(d);
      setCards(d.cards);
      setSubject(d.subject);
      setDemo(d.demo);
      if (d.flag_count !== undefined) setFlagCount(d.flag_count);
      if (d.cached) setCached(true);
    });
    es.addEventListener("error", (e) => {
      const m = e as MessageEvent;
      if (m.data) {
        try {
          setError(JSON.parse(m.data).message);
        } catch {}
        es.close();
      } else if (es.readyState === EventSource.CLOSED) {
        setError((prev) => prev || t("offline", lang));
      }
    });
    on("end", () => es.close());
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkId]);

  const cardFor = (key: string) => cards.find((x) => x.key === key);
  const doneCount = ORDER.filter((k) => FINISHED.has(agents[k]?.state)).length;
  const fileOf = useMemo(() => {
    const m: Record<string, string> = {};
    result?.evidence.forEach((e) => (m[e.id] = e.file));
    return m;
  }, [result]);
  const evLink = (id: string) => (fileOf[id] && checkId ? `${API}/api/evidence/${checkId}/${fileOf[id]}` : undefined);
  const pdfLink = result ? `${API}/api/check/${result.check_id}/report.pdf` : "#";

  const submit = (q: string, isFresh: boolean) => {
    const s = q.trim();
    if (s.length < 2) return;
    setFresh(isFresh);
    if (s === query) setNonce((n) => n + 1);
    else router.push(`/check/${slugify(s)}?q=${encodeURIComponent(s)}`);
  };

  const handleFlagSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!result) return;
    setFlagLoading(true);
    try {
      const res = await flagCheck(result.check_id, flagReason, flagComment);
      if (res.ok) {
        setFlagCount(res.flag_count);
        setFlagSubmitted(true);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setFlagLoading(false);
    }
  };

  const handleHumanAssistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!result) return;
    setHaLoading(true);
    try {
      const updated = await submitHumanAssist(result.check_id, {
        actual_url: haUrl || undefined,
        pasted_text: haText || undefined,
        consent: haConsent,
        answers: {
          received_via: haQ1,
          asking_money_or_otp: haQ2,
          promises: haQ3,
        },
      });
      setResult(updated);
      setCards(updated.cards);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not retain submitted evidence");
    } finally {
      setHaLoading(false);
    }
  };

  const copy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.complaint_text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = result.complaint_text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const hits = result ? [...result.hits].sort((a, b) => b.penalty - a.penalty) : [];
  const v = result ? VERDICT[result.verdict.code] || VERDICT.UNKNOWN : null;
  const meta = subject
    ? [subject.category.charAt(0).toUpperCase() + subject.category.slice(1), subject.website_url ? subject.website_url.replace(/^https?:\/\//, "") : "", subject.play_url ? "Google Play" : "", subject.telegram_url ? "Telegram" : ""]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <>
      <TopBar lang={lang} setLang={setLang} health={health} />
      <div className="bar">
        <div className="wrap">
          <SearchForm lang={lang} value={input} onChange={setInput} onSubmit={() => submit(input, false)} short />
        </div>
      </div>

      <main className="wrap">
        <div className="subject">
          <h1>{subject ? subject.display_name : query}</h1>
          <span className="meta">{meta}</span>
          {demo && (
            <span className="chip warn">
              <span className="d" />
              {t("sample", lang)}
            </span>
          )}
          {cached && (
            <span className="chip live">
              <span className="d" />
              {t("cached", lang)}
            </span>
          )}
        </div>

        {/* ---------------- the answer ---------------- */}
        {error ? (
          <section className="verdict gray">
            <Ring score={0} color="var(--gray)" label="!" />
            <div>
              <div className="vword">{lang === "hi" ? "जाँच नहीं हो पाई" : "Couldn't check"}</div>
              <p className="vsum">{error}</p>
            </div>
            <div />
          </section>
        ) : result && v ? (
          <>
            <section className={`verdict ${v[0]}`} aria-live="polite">
              <Ring score={result.score} color={`var(--${v[0]})`} label={result.verdict.code === "UNKNOWN" ? "?" : String(result.score)} />
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
                  <span className="vword" style={{ margin: 0 }}>{v[1 + i]}</span>
                  {result.confidence && (
                    <span className={`badge-conf ${result.confidence}`}>
                      {result.confidence === "HIGH" ? t("confHigh", lang) : result.confidence === "MEDIUM" ? t("confMed", lang) : t("confLow", lang)}
                    </span>
                  )}
                  {result.human_assisted && (
                    <span className="human-assist-badge">
                      {t("humanAssistBadge", lang)}
                    </span>
                  )}
                </div>
                <div className="vsub">{v[3 + i]}</div>
                <p className="vsum">{lang === "hi" ? result.summary.hi : result.summary.en}</p>
                {result.trust_strip && (
                  <div className="trust-strip">
                    <span className="trust-text">
                      {lang === "hi" ? result.trust_strip.label_hi : result.trust_strip.label_en}
                    </span>
                  </div>
                )}
                {result.partial && <p className="dim" style={{ fontSize: 14, margin: "8px 0 0" }}>{t("partial", lang)}</p>}
              </div>
              <div className="vactions">
                {result.verdict.code !== "LOW_RISK" && (
                  <a className="call-box" href="tel:1930">
                    {t("callBox", lang)} <b>1930</b>
                  </a>
                )}
                <a className="btn small" href={pdfLink}>
                  {t("proofDl", lang)}
                </a>
                <button className="btn ghost small" onClick={() => submit(query, true)}>
                  {t("again", lang)}
                </button>
              </div>
            </section>

            {/* Dispute / Flag Bar */}
            <div className="dispute-panel">
              <div className="dispute-meta">
                {flagCount > 0 && <span>⚠️ {t("reportedBy", lang).replace("{count}", String(flagCount))}</span>}
                <span>Checked at {timeOf(result.started_at)}</span>
              </div>
              <button
                type="button"
                className="btn-flag"
                onClick={() => setShowFlagForm((prev) => !prev)}
              >
                {t("disputeBtn", lang)}
              </button>
            </div>

            {showFlagForm && (
              <form className="flag-form" onSubmit={handleFlagSubmit}>
                {flagSubmitted ? (
                  <p style={{ color: "var(--green)", margin: 0, fontWeight: 600 }}>
                    ✓ {t("disputeThanks", lang)}
                  </p>
                ) : (
                  <>
                    <h4 style={{ margin: "0 0 8px", fontSize: 15 }}>{t("disputeTitle", lang)}</h4>
                    <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--muted)" }}>{t("disputeSub", lang)}</p>
                    <div className="ha-field">
                      <label>{t("disputeReason", lang)}</label>
                      <select
                        className="ha-select"
                        value={flagReason}
                        onChange={(e) => setFlagReason(e.target.value)}
                      >
                        <option value="official_bank_or_gov">{t("disputeReason1", lang)}</option>
                        <option value="legitimate_business">{t("disputeReason2", lang)}</option>
                        <option value="uncaught_scam">{t("disputeReason3", lang)}</option>
                        <option value="other">{t("disputeReason4", lang)}</option>
                      </select>
                    </div>
                    <div className="ha-field">
                      <label>{t("disputeComment", lang)}</label>
                      <textarea
                        className="ha-textarea"
                        placeholder="Provide details or proof..."
                        value={flagComment}
                        onChange={(e) => setFlagComment(e.target.value)}
                      />
                    </div>
                    <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        className="btn ghost small"
                        onClick={() => setShowFlagForm(false)}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="btn small"
                        disabled={flagLoading}
                      >
                        {flagLoading ? "Submitting..." : t("disputeSubmit", lang)}
                      </button>
                    </div>
                  </>
                )}
              </form>
            )}

            {/* Human Assist Mode Panel */}
            {result.human_assist_needed && (
              <div className="human-assist-box">
                <div className="human-assist-head">
                  <h3>{t("humanAssistTitle", lang)}</h3>
                  <span className="human-assist-badge">Tier 3</span>
                </div>
                <p className="ha-desc">{t("humanAssistSub", lang)}</p>
                <form onSubmit={handleHumanAssistSubmit}>
                  <div className="ha-field">
                    <label>{t("humanAssistUrl", lang)}</label>
                    <input
                      type="url"
                      className="ha-input"
                      placeholder="https://..."
                      value={haUrl}
                      onChange={(e) => setHaUrl(e.target.value)}
                    />
                  </div>
                  <div className="ha-field">
                    <label>{t("humanAssistText", lang)}</label>
                    <textarea
                      className="ha-textarea"
                      placeholder="Paste page content or message received..."
                      value={haText}
                      onChange={(e) => setHaText(e.target.value)}
                    />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
                    <div className="ha-field">
                      <label>{t("humanAssistQ1", lang)}</label>
                      <select className="ha-select" value={haQ1} onChange={(e) => setHaQ1(e.target.value)}>
                        <option value="WhatsApp">WhatsApp</option>
                        <option value="Telegram">Telegram</option>
                        <option value="SMS">SMS</option>
                        <option value="Google Search">Google Search</option>
                        <option value="Email">Email</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                    <div className="ha-field">
                      <label>{t("humanAssistQ2", lang)}</label>
                      <select className="ha-select" value={haQ2} onChange={(e) => setHaQ2(e.target.value)}>
                        <option value="No">No / Unsure</option>
                        <option value="Yes - Upfront Registration Fee">Yes - Registration / Security Fee</option>
                        <option value="Yes - Asking for OTP / PIN">Yes - Asking for OTP / PIN</option>
                        <option value="Yes - Personal UPI Payment">Yes - Personal UPI Payment</option>
                      </select>
                    </div>
                  </div>
                  <div className="ha-field">
                    <label>{t("humanAssistQ3", lang)}</label>
                    <input
                      type="text"
                      className="ha-input"
                      placeholder="e.g. Guaranteed 200% returns, free laptop, high paying daily job"
                      value={haQ3}
                      onChange={(e) => setHaQ3(e.target.value)}
                    />
                  </div>
                  <div style={{ marginTop: 16 }}>
                    <label className="integrity-consent"><input type="checkbox" checked={haConsent} onChange={event => setHaConsent(event.target.checked)} />
                      I consent to retaining minimized text in the private revision history. Do not submit OTPs, passwords or sensitive documents. Automatic redaction is best-effort, not guaranteed.
                    </label>
                    <button type="submit" className="btn small" disabled={haLoading || !haConsent}>
                      {haLoading ? "Verifying with your evidence..." : t("humanAssistSubmit", lang)}
                    </button>
                  </div>
                </form>
              </div>
            )}
          </>
        ) : (
          <section className="verdict pending" aria-live="polite">
            <Ring score={liveScore} color="var(--blue-2)" label={String(liveScore)} />
            <div>
              <div className="vword" style={{ color: "var(--ink)" }}>
                {t("checking", lang)}…
              </div>
              <div className="vsub">
                {doneCount} {t("doneOf", lang)}
              </div>
              <div className="progress">
                <i style={{ width: `${(doneCount / 5) * 100}%` }} />
              </div>
              {status && (
                <p className="vsum muted" style={{ fontSize: 15 }}>
                  {status}
                </p>
              )}
            </div>
            <div />
          </section>
        )}

        {/* ---------------- why ---------------- */}
        {result && (
          <section className="block">
            <h2>{t("whyTitle", lang)}</h2>
            {hits.length ? (
              <div className="reasons">
                {hits.map((h) => {
                  const cls = h.color === "amber" ? "amber" : "red";
                  const main = lang === "hi" ? (h as any).short_hi || h.found : h.found;
                  return (
                    <div className={`reason ${cls}`} key={h.rule_id}>
                      <div className="mk">
                        <Icon svg={cls === "amber" ? MARK["!"] : MARK.x} />
                      </div>
                      <div>
                        <b>{main}</b>
                        <span>{cardFor(h.agent)?.title}</span>
                      </div>
                      <div className="cut">−{h.penalty}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="good">{t("allGood", lang)}</div>
            )}
          </section>
        )}

        {/* ---------------- 7-Signal Score Breakdown ---------------- */}
        {result && result.score_breakdown && result.score_breakdown.length > 0 && (
          <section className="block">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
              <div>
                <h2>{t("scoreBreakdown", lang)}</h2>
                <p className="dim" style={{ margin: "4px 0 0", fontSize: 14 }}>{t("scoreBreakdownSub", lang)}</p>
              </div>
            </div>
            <div className="table-scroll" style={{ marginTop: 14 }}>
              <table className="breakdown-table">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th style={{ textAlign: "right" }}>Points</th>
                    <th>Evidence / Finding</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {result.score_breakdown.map((item) => (
                    <tr key={item.id}>
                      <td><b>{lang === "hi" ? item.title_hi : item.title_en}</b></td>
                      <td><span className="cat-tag">{item.category}</span></td>
                      <td>
                        <span className={`badge-status ${item.status}`}>
                          {item.status === "pass" ? t("statusPass", lang) : item.status === "warn" ? t("statusWarn", lang) : item.status === "fail" ? t("statusFail", lang) : t("statusUnknown", lang)}
                        </span>
                      </td>
                      <td className={`pts-delta ${item.status === 'fail' ? 'fail' : item.status === 'warn' ? 'warn' : item.points === '+0' || item.points === '0' ? 'zero' : 'pass'}`}>
                        {item.points}
                      </td>
                      <td>{lang === "hi" ? item.evidence_hi : item.evidence_en}</td>
                      <td>
                        {item.source.startsWith("http") ? (
                          <a href={item.source} target="_blank" rel="noreferrer" className="src-link">
                            {item.source.replace(/^https?:\/\//, "").slice(0, 32)}…
                          </a>
                        ) : (
                          <span className="cat-tag">{item.source}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {result && <EvidenceIntegrity result={result} lang={lang} />}

        {/* ---------------- the five checks ---------------- */}
        <section className="block">
          <h2>{t("checksDone", lang)}</h2>
          <div className="tiles">
            {ORDER.map((key) => {
              const a = agents[key];
              const c = cardFor(key);
              const state = a?.state || "queued";
              const finished = FINISHED.has(state) && c?.label;
              let badge: { cls: string; word: string };
              if (!finished) badge = { cls: "run", word: state === "queued" ? "…" : t("checking", lang) };
              else if (state === "skipped") badge = { cls: "gray", word: lang === "hi" ? "ज़रूरी नहीं" : "Not needed" };
              else if (state === "unverified" || state === "error") badge = { cls: "gray", word: lang === "hi" ? "जाँच नहीं हुई" : "Couldn't check" };
              else {
                const col = c!.color || "gray";
                const word = col === "green"
                  ? (lang === "hi" ? "ठीक" : "OK")
                  : col === "amber"
                  ? (lang === "hi" ? "चेतावनी" : "Warning")
                  : col === "red"
                  ? (lang === "hi" ? "समस्या" : "Problem")
                  : (lang === "hi" ? "जाँच हुई" : "Checked");
                badge = { cls: col, word };
              }
              return (
                <button key={key} className={`tile ${state === "running" ? "running" : ""}`} onClick={() => setOpen((o) => (o === key ? null : key))} aria-expanded={open === key}>
                  <div className="top">
                    <span className="icon-box">
                      <Icon svg={ICONS[key]} />
                    </span>
                    <span className={`st ${badge.cls}`}>{badge.word}</span>
                  </div>
                  <b>{CHECKS[key][i][0]}</b>
                  {finished ? (
                    <div className="line">{lang === "hi" ? c!.detail_hi : c!.detail_en}</div>
                  ) : (
                    <div className="line mono">{a?.steps[a.steps.length - 1]?.msg || ""}</div>
                  )}
                </button>
              );
            })}
            {open && agents[open] && (
              <div className="steplog">
                <b>{CHECKS[open][i][0]}</b>
                {agents[open].steps.map((s, n) => (
                  <div key={n}>
                    {timeOf(s.at)} · {s.msg}
                  </div>
                ))}
                {agents[open].note && <div>{agents[open].note}</div>}
              </div>
            )}
          </div>
          <p className="dim" style={{ fontSize: 13.5, margin: "10px 2px 0" }}>
            {t("tapTile", lang)}
          </p>
        </section>

        {/* ---------------- what to do ---------------- */}
        {result && (
          <section className="block">
            <h2>{t("todoTitle", lang)}</h2>
            <div className="todo">
              <div>
                <h3>{t("notPaid", lang)}</h3>
                <ol>
                  {(TODO[result.verdict.code] || TODO.UNKNOWN)[i].map((x: string, n: number) => (
                    <Html as="li" key={n} html={x} />
                  ))}
                </ol>
              </div>
              <div>
                <h3>{t("paid", lang)}</h3>
                <ol>
                  {PAID[i].map((x: string, n: number) => (
                    <Html as="li" key={n} html={x} />
                  ))}
                </ol>
                <div className="btns">
                  <button className="btn small" onClick={copy}>
                    {copied ? t("copied", lang) : t("copy", lang)}
                  </button>
                  <a className="btn ghost small" href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
                    {t("portal", lang)}
                  </a>
                </div>
              </div>
            </div>
          </section>
        )}

        {result && <Investigation key={result.check_id} result={result} hindi={lang === "hi"} />}

        {/* ---------------- technical details, folded away ---------------- */}
        {result && (
          <details className="tech">
            <summary>
              {t("tech", lang)} <span>{t("techSub", lang)} ↓</span>
            </summary>
            <div className="tech-body">
              <div>
                <h3>{t("tClaims", lang)}</h3>
                {hits.length > 0 && (
                  <div className="table-scroll">
                    <table className="pg">
                      <thead>
                        <tr>
                          <th>{t("claim", lang)}</th>
                          <th>{t("how", lang)}</th>
                          <th>{t("found", lang)}</th>
                          <th>{t("proofCol", lang)}</th>
                          <th style={{ textAlign: "right" }}>{t("cut", lang)}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hits.map((h) => (
                          <tr key={h.rule_id}>
                            <td>
                              <b>{h.claim}</b>
                            </td>
                            <td>{h.how_checked}</td>
                            <td>{h.found}</td>
                            <td>
                              {h.evidence_ids.map((id) => (
                                <a key={id} className="ev-link" href={evLink(id)} target="_blank" rel="noreferrer">
                                  {id}
                                </a>
                              ))}
                            </td>
                            <td className="pen">−{h.penalty}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="formula">
                  {result.verdict.code === "UNKNOWN" ? "Identity unverified; neutral internal score: " : "score = max(0, 100 − total) = "}
                  <b>
                    100{hits.map((h) => ` − ${h.penalty}`).join("")} = {result.score}
                  </b>
                </p>
              </div>
              <div>
                <h3>{t("tEvidence", lang)}</h3>
                <div className="evs">
                  {result.evidence.map((e) => (
                    <div className="ev" key={e.id}>
                      <span>
                        {e.id} · {e.label}
                        <small>sha256 {e.sha256.slice(0, 24)}…</small>
                      </span>
                      <a className="ev-link" href={evLink(e.id)} target="_blank" rel="noreferrer">
                        {t("open", lang)}
                      </a>
                    </div>
                  ))}
                </div>
                <p className="formula" style={{ fontSize: 12, marginTop: 10 }}>
                  manifest {result.manifest_sha256}
                </p>
              </div>
              <div className="complaint">
                <h3>{t("tComplaint", lang)}</h3>
                <pre>{result.complaint_text}</pre>
              </div>
              <div>
                <h3>{t("tRules", lang)}</h3>
                <table className="rules">
                  <tbody>
                    {Object.entries(result.rules).map(([id, r]) => (
                      <tr key={id}>
                        <td>−{r.penalty}</td>
                        <td>{r.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </details>
        )}
      </main>
      <Footer lang={lang} />
    </>
  );
}
