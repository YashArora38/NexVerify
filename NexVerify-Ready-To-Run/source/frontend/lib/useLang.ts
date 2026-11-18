"use client";
import { useEffect, useState } from "react";
import type { Lang } from "./api";

export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLang] = useState<Lang>("en");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("nv-lang");
      if (saved === "hi" || saved === "en") setLang(saved);
    } catch {}
  }, []);
  useEffect(() => {
    document.body.classList.toggle("hi", lang === "hi");
    document.documentElement.lang = lang;
  }, [lang]);
  const set = (l: Lang) => {
    setLang(l);
    try {
      localStorage.setItem("nv-lang", l);
    } catch {}
  };
  return [lang, set];
}
