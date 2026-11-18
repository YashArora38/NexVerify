export function ShieldIcon({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <path d="M32 4 8 12v18c0 15 10.4 26.6 24 30 13.6-3.4 24-15 24-30V12L32 4Z" fill="#2f6bff" />
      <path d="m21 32 8 8 15-16" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand() {
  return (
    <a href="/" className="brand" aria-label="NexVerify home" style={{ textDecoration: "none" }}>
      <span className="brand-mark">
        <ShieldIcon />
      </span>
      <span className="brand-name">NexVerify</span>
    </a>
  );
}
