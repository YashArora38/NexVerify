"""Official-domain registry (compatibility layer).

Older code asks REGISTRY.match(url) for "is this an official domain / a lookalike?".
The answer now comes from app/linkintel.py, which reads data/linkintel.json
(134 brands, 260+ known sites, India's restricted zones) and the Public Suffix
List. Restricted zones are handled explicitly, so sbi.bank.in is always the
bank's own address, whatever the installed suffix list knows.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import linkintel

# Kept for code that imports these names.
SUSPICIOUS_TLDS = set(linkintel.data()["very_risky_tlds"])
KNOWN_SHORTENERS = set(linkintel.data()["shorteners"])
RESTRICTED_TLD_SPACES = {z: {"agency": "", "category": m["kind"], "description": m["en"], "is_bank": z == "bank.in"}
                         for z, m in linkintel.data()["zones"].items()}


@dataclass
class RegistryMatch:
    is_official: bool = False
    is_restricted_tld: bool = False
    is_bank_tld: bool = False
    brand: str = ""
    brand_id: str = ""
    registered_domain: str = ""
    primary_domain: str = ""
    category: str = "general"
    source_url: str = ""
    evidence_text: str = ""
    lookalike_hit: dict | None = None
    known_scam_hit: dict | None = None
    raw_entity: dict | None = None


class RegistryEngine:
    def extract_tld(self, url_or_host: str) -> dict:
        p = linkintel.parse(url_or_host if "." in url_or_host else url_or_host + ".")
        host = p.host or url_or_host.lower()
        reg, suffix, label = linkintel.split_host(host) if host else ("", "", "")
        sub = host[: -len(reg) - 1] if host.endswith("." + reg) else ""
        return {"subdomain": sub, "domain": label, "suffix": suffix, "registered_domain": reg or host, "host": host}

    def is_url_shortener(self, host: str) -> bool:
        return self.extract_tld(host)["registered_domain"] in KNOWN_SHORTENERS

    def match(self, url_or_query: str) -> RegistryMatch:
        m = RegistryMatch()
        rep = linkintel.analyze(url_or_query)
        p = rep.parsed
        m.registered_domain = p.get("registrable") or ""
        zone = next((z for z in linkintel.data()["zones"] if p.get("suffix") == z), None)
        if zone:
            m.is_restricted_tld = True
            m.is_bank_tld = zone == "bank.in"
            m.category = linkintel.data()["zones"][zone]["kind"]
        ident = rep.identity
        if ident and not rep.ugc:
            m.is_official = True
            m.brand = ident.get("name") or (p.get("label", "").upper() + {"bank.in": " Bank", "gov.in": " (Government of India)", "nic.in": " (Government of India)"}.get(zone or "", ""))
            m.brand_id = ident.get("brand") or p.get("label") or ""
            m.primary_domain = m.registered_domain
            m.category = ident.get("kind") or m.category
            m.evidence_text = ident["en"]
            return m
        strong = [s for s in rep.signals if s.group == "brand" and s.points >= linkintel.HIGH]
        if strong:
            s = strong[0]
            b = next((x for x in linkintel.data()["brands"] if x["id"] == (s.detail or {}).get("brand")), None)
            m.lookalike_hit = {"type": s.id.lower(), "brand": b["name"] if b else "", "official_domain": (s.detail or {}).get("real", ""),
                               "impersonating_host": p.get("host"), "reason": s.en}
            m.evidence_text = s.en
        return m

    def detect_lookalike(self, url_or_query: str) -> dict | None:
        return self.match(url_or_query).lookalike_hit


REGISTRY = RegistryEngine()
