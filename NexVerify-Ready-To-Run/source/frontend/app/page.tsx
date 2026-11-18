"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Footer, SearchForm, TopBar } from "@/components/Chrome";
import { Icon } from "@/components/Icon";
import StageScene, { Rosette } from "@/components/StageScene";
import { API, getHealth, type Health, slugify, startBatchCheck } from "@/lib/api";
import { ANSWERS, CHECKS, ICONS, L, MARK, SAMPLES, STEPS, t, TRUST, TRY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";

const ORDER = ["rbi", "sebi", "company", "listing", "news"];
const FALLBACK_DEMOS = ["QuickRupee - Instant Loan App", "Bullvanta Signals", "Hirevexa Internships", "SafeKosh Finance"];

interface Recent {
  check_id: string;
  query: string;
  score: number;
  verdict: string;
  demo: boolean;
}

function sampleInfo(name: string, lang: "en" | "hi"): [string, string] {
  const k = Object.keys(SAMPLES).find((key) => name.toLowerCase().replace(/\s+/g, "").includes(key));
  return k ? SAMPLES[k][L(lang)] : ["Sample", ""];
}

export default function Home() {
  const [lang, setLang] = useLang();
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"single" | "batch">("single");
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  const [recent, setRecent] = useState<Recent[]>([]);
  const router = useRouter();
  const i = L(lang);

  // Batch states
  const [batchInput, setBatchInput] = useState(
    "https://sbi.bank.in\nhttps://sbi-rewards-claim.in\nhttps://groww.in\nhttps://uidai.gov.in"
  );
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchItems, setBatchItems] = useState<any[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchDone, setBatchDone] = useState(false);
  const [batchFilter, setBatchFilter] = useState<"all" | "safe" | "caution" | "high_risk">("all");

  useEffect(() => {
    getHealth().then(setHealth);
    fetch(`${API}/api/recent`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setRecent)
      .catch(() => {});
  }, []);

  const go = (query: string) => {
    const s = query.trim();
    if (s.length < 2) return;
    router.push(`/check/${slugify(s)}?q=${encodeURIComponent(s)}`);
  };

  const runBatch = async () => {
    const lines = batchInput.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return;
    setBatchItems([]);
    setBatchDone(false);
    setBatchRunning(true);
    try {
      const res = await startBatchCheck(lines);
      setBatchId(res.batch_id);
      setBatchTotal(res.total);

      const es = new EventSource(`${API}/api/check/batch/${res.batch_id}/stream`);
      es.addEventListener("item", (e: MessageEvent) => {
        try {
          const item = JSON.parse(e.data);
          setBatchItems((prev) => {
            if (prev.some((x) => x.query === item.query)) return prev;
            return [...prev, item];
          });
        } catch {}
      });
      es.addEventListener("end", () => {
        setBatchDone(true);
        setBatchRunning(false);
        es.close();
      });
      es.addEventListener("error", () => {
        setBatchRunning(false);
        es.close();
      });
    } catch (e) {
      console.error(e);
      setBatchRunning(false);
    }
  };

  const retryFailed = async () => {
    if (!batchId) return;
    try {
      setBatchRunning(true);
      setBatchDone(false);
      const r = await fetch(`${API}/api/check/batch/${batchId}/retry-failed`, { method: "POST" });
      if (r.ok) {
        const data = await r.json();
        setBatchItems(data.items || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setBatchRunning(false);
      setBatchDone(true);
    }
  };

  const demos: string[] = health?.demo_names?.length ? health.demo_names : FALLBACK_DEMOS;

  const countSafe = batchItems.filter((it) => it.score >= 70 && it.verdict?.code !== "HIGH_RISK").length;
  const countCaution = batchItems.filter((it) => (it.score >= 40 && it.score < 70) || it.verdict?.code === "CAUTION").length;
  const countRisk = batchItems.filter((it) => it.score < 40 || it.verdict?.code === "HIGH_RISK").length;

  const filteredBatchItems = batchItems.filter((it) => {
    if (batchFilter === "safe") return it.score >= 70 && it.verdict?.code !== "HIGH_RISK";
    if (batchFilter === "caution") return (it.score >= 40 && it.score < 70) || it.verdict?.code === "CAUTION";
    if (batchFilter === "high_risk") return it.score < 40 || it.verdict?.code === "HIGH_RISK";
    return true;
  });

  return (
    <>
      <TopBar lang={lang} setLang={setLang} health={health} />
      <section className="hero">
        <Rosette />
        <div className="wrap">
          <div>
            <div className="eyebrow">
              <span className="thread" />
              {t("eyebrow", lang)}
            </div>
            <h1>
              {t("h1a", lang)}
              <br />
              <span>{t("h1b", lang)}</span>
            </h1>

            {/* Mode Selector Tabs */}
            <div className="mode-tabs">
              <button
                type="button"
                className={`mode-tab ${mode === "single" ? "active" : ""}`}
                onClick={() => setMode("single")}
              >
                {t("batchTabSingle", lang)}
              </button>
              <button
                type="button"
                className={`mode-tab ${mode === "batch" ? "active" : ""}`}
                onClick={() => setMode("batch")}
              >
                {t("batchTabMulti", lang)}
              </button>
            </div>

            {mode === "single" ? (
              <>
                <p className="lead">{t("lead", lang)}</p>
                <SearchForm lang={lang} value={q} onChange={setQ} onSubmit={() => go(q)} autoFocus />
                <div className="try">
                  <span>{t("try", lang)}</span>
                  {(TRY as string[]).map((x) => (
                    <button type="button" key={x} onClick={() => go(x)}>
                      {x}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ marginTop: 8 }}>
                <p className="lead">{t("batchLead", lang)}</p>
                <textarea
                  className="batch-textarea"
                  value={batchInput}
                  onChange={(e) => setBatchInput(e.target.value)}
                  placeholder={t("batchPlaceholder", lang)}
                  rows={4}
                />
                <div style={{ marginTop: 12 }}>
                  <button
                    type="button"
                    className="btn"
                    onClick={runBatch}
                    disabled={batchRunning}
                  >
                    {batchRunning ? t("batchProgress", lang) : t("batchStart", lang)}
                  </button>
                </div>
              </div>
            )}

            {health === null && <div className="error-box">{t("offline", lang)}</div>}
            {health && <p className="note-line">{health.live ? t("noteLive", lang) : t("noteDemo", lang)}</p>}
          </div>
          <StageScene />
        </div>
      </section>

      <main className="wrap">
        {/* Batch Results View */}
        {mode === "batch" && (batchRunning || batchItems.length > 0) && (
          <section className="sec" style={{ marginTop: 20 }}>
            <div className="sec-head">
              <h2>{t("batchTitle", lang)}</h2>
              <p>
                {batchItems.length} of {batchTotal} verified
                {batchRunning && " (analyzing in parallel...)"}
              </p>
            </div>

            {batchTotal > 0 && (
              <div className="progress" style={{ height: 8, margin: "14px 0" }}>
                <i style={{ width: `${(batchItems.length / Math.max(1, batchTotal)) * 100}%` }} />
              </div>
            )}

            {/* Stat Counters */}
            <div className="batch-stats">
              <div className="stat-card">
                <b>{batchItems.length} / {batchTotal}</b>
                <span>Total Checked</span>
              </div>
              <div className="stat-card" style={{ borderLeft: "4px solid var(--green)" }}>
                <b style={{ color: "var(--green)" }}>{countSafe}</b>
                <span>Safe</span>
              </div>
              <div className="stat-card" style={{ borderLeft: "4px solid var(--amber)" }}>
                <b style={{ color: "var(--amber)" }}>{countCaution}</b>
                <span>Suspicious</span>
              </div>
              <div className="stat-card" style={{ borderLeft: "4px solid var(--red)" }}>
                <b style={{ color: "var(--red)" }}>{countRisk}</b>
                <span>High Risk</span>
              </div>
            </div>

            {/* Action Bar (Export CSV, PDF, Retry) */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
              {batchId && (
                <>
                  <a className="btn small" href={`${API}/api/check/batch/${batchId}/export.csv`} download>
                    {t("batchDlCsv", lang)}
                  </a>
                  <a className="btn ghost small" href={`${API}/api/check/batch/${batchId}/report.pdf`} target="_blank" rel="noreferrer">
                    {t("batchDlPdf", lang)}
                  </a>
                  {batchDone && (
                    <button type="button" className="btn ghost small" onClick={retryFailed}>
                      {t("batchRetry", lang)}
                    </button>
                  )}
                </>
              )}
            </div>

            {/* Filter Pills */}
            <div className="filter-tabs">
              <button
                type="button"
                className={`filter-pill ${batchFilter === "all" ? "active" : ""}`}
                onClick={() => setBatchFilter("all")}
              >
                {t("filterAll", lang)} ({batchItems.length})
              </button>
              <button
                type="button"
                className={`filter-pill ${batchFilter === "safe" ? "active" : ""}`}
                onClick={() => setBatchFilter("safe")}
              >
                {t("filterSafe", lang)} ({countSafe})
              </button>
              <button
                type="button"
                className={`filter-pill ${batchFilter === "caution" ? "active" : ""}`}
                onClick={() => setBatchFilter("caution")}
              >
                {t("filterSuspicious", lang)} ({countCaution})
              </button>
              <button
                type="button"
                className={`filter-pill ${batchFilter === "high_risk" ? "active" : ""}`}
                onClick={() => setBatchFilter("high_risk")}
              >
                {t("filterHighRisk", lang)} ({countRisk})
              </button>
            </div>

            {/* Batch Results Table */}
            <div className="table-scroll" style={{ marginTop: 10 }}>
              <table className="breakdown-table">
                <thead>
                  <tr>
                    <th>Subject / Input</th>
                    <th>Verdict</th>
                    <th>Score</th>
                    <th>Confidence</th>
                    <th>Key Finding</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBatchItems.map((it, idx) => {
                    const isRisk = it.score < 40 || it.verdict?.code === "HIGH_RISK";
                    const isWarn = !isRisk && ((it.score >= 40 && it.score < 70) || it.verdict?.code === "CAUTION");
                    const stCls = isRisk ? "fail" : isWarn ? "warn" : "pass";
                    const stWord = isRisk ? "High Risk" : isWarn ? "Suspicious" : "Safe";

                    return (
                      <tr key={idx}>
                        <td>
                          <b>{it.query}</b>
                        </td>
                        <td>
                          <span className={`badge-status ${stCls}`}>{stWord}</span>
                        </td>
                        <td>
                          <b style={{ fontFamily: "var(--mono)" }}>{it.score}/100</b>
                        </td>
                        <td>
                          <span className={`badge-conf ${it.confidence || "LOW"}`}>
                            {it.confidence || "LOW"}
                          </span>
                        </td>
                        <td style={{ fontSize: 13, maxWidth: 320 }}>
                          {lang === "hi" ? it.summary?.hi : it.summary?.en}
                        </td>
                        <td>
                          <a
                            href={`/check/${slugify(it.query)}?q=${encodeURIComponent(it.query)}`}
                            className="src-link"
                          >
                            View Proof →
                          </a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section className="sec">
          <div className="sec-head">
            <h2>{t("howTitle", lang)}</h2>
            <p>{t("howSub", lang)}</p>
          </div>
          <div className="steps">
            {STEPS.map((s: any, n: number) => (
              <div className="step" key={n}>
                <div className="n">0{n + 1}</div>
                <h3>{s[i][0]}</h3>
                <p>{s[i][1]}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="sec">
          <div className="sec-head">
            <h2>{t("answersTitle", lang)}</h2>
            <p>{t("answersSub", lang)}</p>
          </div>
          <div className="answers">
            {ANSWERS.map((a: any) => (
              <div className={`answer ${a[0]}`} key={a[0]}>
                <div className="badge">
                  <Icon svg={MARK[a[1]]} />
                  {a[2 + i][0]}
                </div>
                <div className="range">
                  {t("scoreWord", lang)} {a[2 + i][1]}
                </div>
                <p>{a[2 + i][2]}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="sec">
          <div className="sec-head">
            <h2>{t("checksTitle", lang)}</h2>
            <p>{t("checksSub", lang)}</p>
          </div>
          <div className="checks5">
            {ORDER.map((k) => (
              <div className="c5" key={k}>
                <div className="icon-box">
                  <Icon svg={ICONS[k]} />
                </div>
                <b>{CHECKS[k][i][0]}</b>
                <span>{CHECKS[k][i][1]}</span>
                <small>{CHECKS[k][i][2]}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="sec">
          <div className="sec-head">
            <h2>{t("samplesTitle", lang)}</h2>
            <p>{t("samplesSub", lang)}</p>
          </div>
          <div className="samples">
            {demos.map((d) => {
              const [tag, line] = sampleInfo(d, lang);
              return (
                <button className="sample" key={d} onClick={() => go(d)}>
                  <span className="tag">{tag}</span>
                  <b>{d}</b>
                  {line && <span>{line}</span>}
                  <span className="go">{t("run", lang)}</span>
                </button>
              );
            })}
          </div>
        </section>

        {recent.length > 0 && (
          <section className="sec recent">
            <div className="sec-head">
              <h2>{t("recent", lang)}</h2>
            </div>
            <ul>
              {recent.slice(0, 6).map((r) => (
                <li key={r.check_id}>
                  <a href={`/check/${slugify(r.query)}?q=${encodeURIComponent(r.query)}`}>
                    <span>
                      {r.query} {r.demo && <span className="dim">· sample</span>}
                    </span>
                    <span className={`sc ${r.verdict === "HIGH_RISK" || r.verdict === "SUSPICIOUS" ? "c-red" : r.verdict === "CAUTION" ? "c-amber" : r.verdict === "UNKNOWN" ? "c-gray" : "c-green"}`}>
                      {r.verdict === "UNKNOWN" ? "?" : r.score}/100
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="sec">
          <div className="trust">
            {TRUST.map((x: any, n: number) => (
              <div key={n}>
                <b>{x[i][0]}</b>
                <span>{x[i][1]}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
      <Footer lang={lang} />
    </>
  );
}
