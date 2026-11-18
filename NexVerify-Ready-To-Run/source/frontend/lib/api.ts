import type { InvestigationData } from "@/components/Investigation";
// Empty means same-origin /api through the Next.js or production reverse proxy.
export const API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

export type Lang = "en" | "hi";
export type Color = "red" | "amber" | "green" | "gray";

export interface Subject {
  query: string;
  slug: string;
  display_name: string;
  category: "lending" | "investment" | "job" | "general";
  website_url?: string | null;
  play_url?: string | null;
  telegram_url?: string | null;
  legal_name?: string | null;
}

export interface Card {
  key: string;
  title: string;
  state: string;
  label: string;
  color: Color;
  detail_en: string;
  detail_hi: string;
  penalty: number;
  method: string;
}

export interface Hit {
  rule_id: string;
  agent: string;
  penalty: number;
  color: Color;
  claim: string;
  how_checked: string;
  found: string;
  evidence_ids: string[];
}

export interface Evidence {
  id: string;
  agent: string;
  kind: string;
  label: string;
  source_url: string;
  captured_at: string;
  sha256: string;
  file: string;
  simulated: boolean;
}

export interface ScoreBreakdownItem {
  id: string;
  title_en: string;
  title_hi: string;
  category: string;
  status: "pass" | "warn" | "fail" | "unknown";
  points: string;
  evidence_en: string;
  evidence_hi: string;
  source: string;
}

export interface TrustStrip {
  total: number;
  verified: number;
  unverified: number;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  label_en: string;
  label_hi: string;
}

export interface Result {
  investigation?: InvestigationData;
  check_id: string;
  query: string;
  demo: boolean;
  subject: Subject;
  started_at: string;
  duration_ms: number;
  score: number;
  total_penalty: number;
  verdict: { code: string; color: Color; label_en: string; label_hi: string };
  summary: { en: string; hi: string; source: string };
  cards: Card[];
  hits: Hit[];
  score_breakdown?: ScoreBreakdownItem[];
  confidence?: "HIGH" | "MEDIUM" | "LOW";
  trust_strip?: TrustStrip;
  flag_count?: number;
  human_assist_needed?: boolean;
  human_assisted?: boolean;
  partial: boolean;
  unverified: string[];
  complaint_text: string;
  evidence: Evidence[];
  manifest_sha256: string;
  rules: Record<string, { penalty: number; label: string; description: string }>;
  cached?: boolean;
}

export interface Health {
  ok: boolean;
  live: boolean;
  gemini_model: string;
  db: string;
  cache: string;
  demo_names: string[];
}

export function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/https?:\/\//, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "check"
  );
}

export async function getHealth(): Promise<Health | null> {
  try {
    const r = await fetch(`${API}/api/health`, { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export async function startCheck(query: string, fresh = false): Promise<string> {
  const r = await fetch(`${API}/api/check`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, fresh }),
  });
  if (r.status === 401) throw new Error("Sign in with Manus to create a private verification check.");
  if (!r.ok) throw new Error(`Server said ${r.status}`);
  return (await r.json()).check_id;
}

export async function flagCheck(checkId: string, reason: string, comment = ""): Promise<{ ok: boolean; flag_count: number }> {
  const r = await fetch(`${API}/api/check/${checkId}/flag`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason, comment }),
  });
  if (!r.ok) throw new Error(`Flag failed: ${r.status}`);
  return await r.json();
}

export async function submitHumanAssist(
  checkId: string,
  data: { pasted_text?: string; actual_url?: string; consent: boolean; answers?: Record<string, any> }
): Promise<Result> {
  const r = await fetch(`${API}/api/check/${checkId}/human-assist`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(`Human assist failed: ${r.status}`);
  return await r.json();
}

export async function startBatchCheck(
  inputs: string | string[],
  fresh = false
): Promise<{ batch_id: string; total: number; stream_url: string }> {
  const r = await fetch(`${API}/api/check/batch`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs, fresh }),
  });
  if (!r.ok) throw new Error(`Batch failed: ${r.status}`);
  return await r.json();
}

export async function getBatchCheck(batchId: string): Promise<any> {
  const r = await fetch(`${API}/api/check/batch/${batchId}`);
  if (!r.ok) throw new Error(`Get batch failed: ${r.status}`);
  return await r.json();
}
