"use client";
import { useEffect, useRef, useState } from "react";
import { createStage } from "@/lib/stage3d";

// The 3D phone in the hero. Falls back to the flat shield logo if WebGL is unavailable.
export default function StageScene() {
  const ref = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let api: { layout(): void; wake(): void; dispose(): void } | null = null;
    try {
      api = createStage(cv, reduced);
      api!.wake();
      api!.layout();
    } catch {
      setFailed(true);
      return;
    }
    const onResize = () => api?.layout();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      api?.dispose();
    };
  }, []);

  return (
    <div className="stage">
      {failed ? (
        <div className="fallback">
          <svg width="180" height="180" viewBox="0 0 64 64" aria-hidden="true">
            <path d="M32 4 8 12v18c0 15 10.4 26.6 24 30 13.6-3.4 24-15 24-30V12L32 4Z" fill="#2f6bff" />
            <path d="m21 32 8 8 15-16" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      ) : (
        <canvas ref={ref} aria-hidden="true" />
      )}
    </div>
  );
}

export function Rosette() {
  const ellipses = Array.from({ length: 36 }, (_, i) => (i / 36) * 180);
  const rings = Array.from({ length: 6 }, (_, j) => 120 + j * 52);
  return (
    <svg className="rosette" viewBox="0 0 900 900" aria-hidden="true">
      <defs>
        <linearGradient id="thr" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#33d9a6" />
          <stop offset="1" stopColor="#4f8dff" />
        </linearGradient>
      </defs>
      <g fill="none" stroke="url(#thr)" strokeWidth="0.8" opacity="0.13">
        {ellipses.map((a) => (
          <ellipse key={a} cx="450" cy="450" rx="400" ry="150" transform={`rotate(${a.toFixed(1)} 450 450)`} />
        ))}
        {rings.map((r) => (
          <circle key={r} cx="450" cy="450" r={r} />
        ))}
      </g>
    </svg>
  );
}
