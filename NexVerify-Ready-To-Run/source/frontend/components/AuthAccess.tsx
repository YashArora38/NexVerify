"use client";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

interface AuthState { authenticated?: boolean; required?: boolean; auth_required?: boolean; configured?: boolean; user?: { name?: string }; }
export default function AuthAccess() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  useEffect(() => {
    fetch(`${API}/api/auth/status`, { credentials: "include", cache: "no-store" })
      .then(response => response.ok ? response.json() : null).then(setAuth).catch(() => setAuth(null));
  }, []);
  if (!auth) return null;
  if (!auth.configured && !auth.authenticated) return <span className="auth-access">Sign-in not configured</span>;
  if (auth.authenticated) return <div className="auth-access"><span>{auth.user?.name || "Signed in"}</span><button className="btn ghost" onClick={async () => {
    const response = await fetch(`${API}/api/auth/logout`, { method: "POST", credentials: "include" });
    if (response.ok) window.location.assign("/");
  }}>Sign out</button></div>;
  return <div className="auth-access"><a className="btn ghost" href={`${API}/api/auth/login`}>Sign in with Manus</a>{(auth.required || auth.auth_required) && <span>Private checks require login</span>}</div>;
}
