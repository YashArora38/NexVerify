"use client";
import type { Health, Lang } from "@/lib/api";
import { t } from "@/lib/copy";
import { Html } from "./Icon";
import { Brand } from "./Logo";
import AuthAccess from "./AuthAccess";

export function TopBar({ lang, setLang, health }: { lang: Lang; setLang: (l: Lang) => void; health?: Health | null }) {
  const mode =
    health === undefined ? null : health === null ? (
      <span className="chip off">
        <span className="d" />
        {t("modeOff", lang)}
      </span>
    ) : health.live ? (
      <span className="chip live" title={health.gemini_model}>
        <span className="d" />
        {t("modeLive", lang)}
      </span>
    ) : (
      <span className="chip warn">
        <span className="d" />
        {t("modeDemo", lang)}
      </span>
    );
  return (
    <header className="topbar">
      <div className="wrap">
        <Brand />
        <div className="top-right">
          <span className="chip call">
            <Html html={t("help", lang)} />
          </span>
          {mode}
          <AuthAccess />
          <div className="lang" role="group" aria-label="Language">
            <button aria-pressed={lang === "en"} onClick={() => setLang("en")}>
              EN
            </button>
            <button aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>
              हिंदी
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

export function SearchForm({
  lang,
  value,
  onChange,
  onSubmit,
  short,
  autoFocus,
}: {
  lang: Lang;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  short?: boolean;
  autoFocus?: boolean;
}) {
  return (
    <form
      className="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <input
        id="nv-q"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("placeholder", lang)}
        aria-label={t("placeholder", lang)}
        autoComplete="off"
        autoFocus={autoFocus}
      />
      <button className="btn" type="submit">
        {short ? t("checkShort", lang) : t("check", lang)}
      </button>
    </form>
  );
}

export function Footer({ lang }: { lang: Lang }) {
  return (
    <footer className="foot">
      <div className="wrap">
        <Html as="div" html={`<div class="big">${t("footBig", lang)}</div>`} />
        <p>{t("footSmall", lang)}</p>
      </div>
    </footer>
  );
}
