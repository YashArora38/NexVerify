"""Link intelligence: what can be proven about a link or name without opening it.

Pure, deterministic and offline. Same input -> same answer. No network, no AI.
The preview page runs a line-for-line JavaScript port of this file
(preview/linkintel.js) against the same data file (data/linkintel.json);
tests/test_linkintel_parity.py checks that both give identical results.

How it decides
--------------
1. Work out who really owns the address: the registrable domain under the
   Public Suffix List, plus India's restricted zones (.bank.in, .gov.in ...)
   that the public list does not know yet.
2. Proof of identity (positives): restricted zone, a brand's own domain or
   brand TLD, a known official site.
3. Warning signs (negatives), each with fixed points:
      weak 5-20 . medium 35-45 . strong 70+
   A brand name on someone else's address, a lookalike spelling, a fake
   government address, an "@" trick or an .apk download are strong. Free
   hosting, bait words, cheap endings and odd structure are weak on their
   own and only add up when they appear together.
4. Verdict for a link checked on its own:
      >= 70 points        HIGH_RISK   ("Don't pay")   score <= 30
      55-69               SUSPICIOUS                  score 31-45
      31-54               CAUTION     ("Be careful")  score 46-69
   score = 100 - risk points, exactly (the page shows this sum).
      otherwise           VERIFIED_OFFICIAL / LOW_RISK when identity is proven,
                          UNKNOWN ("Couldn't verify") when it is not.
   "No red flags" therefore always needs proof of who runs the site; finding
   nothing wrong is never enough.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

DATA_DIR = Path(__file__).parent / "data"

HIGH, SUSP, CAUT = 70, 55, 31  # risk points; score = 100 - risk


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _psl() -> tuple[set, set, set]:
    rules, wild, exc = set(), set(), set()
    for line in (DATA_DIR / "public_suffixes.txt").read_text(encoding="utf-8").splitlines():
        s = line.strip().lower()
        if not s or s.startswith("//"):
            continue
        if s.startswith("!"):
            exc.add(s[1:])
        elif s.startswith("*."):
            wild.add(s[2:])
        else:
            rules.add(s)
    return rules, wild, exc


@lru_cache(maxsize=1)
def data() -> dict:
    d = json.loads((DATA_DIR / "linkintel.json").read_text(encoding="utf-8"))
    official: dict[str, dict] = {}
    for b in d["brands"]:
        for dom in b["official"]:
            official.setdefault(dom, b)
    d["_official"] = official
    d["_free"] = set(d["free_hosts"])
    d["_short"] = set(d["shorteners"])
    d["_risky"] = set(d["risky_tlds"])
    d["_very_risky"] = set(d["very_risky_tlds"])
    d["_mid_risky"] = set(d.get("mid_risky_tlds") or [])
    w = d["words"]
    d["_cred"], d["_service"], d["_lure"], d["_money"], d["_context"] = (set(w[k]) for k in ("credential", "service", "lure", "money", "context"))
    vocab = set().union(*(set(v) for v in w.values()))
    brand_words = set()
    for b in d["brands"]:
        brand_words.update(b["tokens"])
        brand_words.update(b["fused"])
    d["_vocab"] = vocab
    d["_vocab_and_brands"] = vocab | brand_words
    d["_ugc"] = d["ugc_hosts"]
    d["_generic_paths"] = set(d["generic_paths"])
    d["_betting"] = d["betting"]
    d["_gov_words"] = set(d["gov_words"])
    look = []
    for b in d["brands"]:
        bases = set(b["look"])
        names = set(b["tokens"]) | set(b["fused"])
        for dom in b["official"]:
            lab = split_host(dom)[2]
            if lab and "." not in lab and lab in names:
                bases.add(lab)
        for base in bases:
            base = base.replace("-", "")
            if len(base) >= 5 and base not in vocab:
                look.append((base, b))
    d["_look"] = look
    labels_known = set()
    for dom in list(d["known"]) + list(official):
        lab = split_host(dom)[2]
        if lab:
            labels_known.add(lab.replace("-", ""))
    d["_known_labels"] = labels_known
    d["_look_exc"] = set(d.get("lookalike_exceptions") or [])
    return d


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def split_host(host: str) -> tuple[str, str, str]:
    """Return (registrable, public_suffix, label) for a hostname.

    The label is the registrable domain without its suffix ("sbi-kyc" for
    sbi-kyc.co.in). Follows Public Suffix List rules, including wildcards and
    exceptions, with India's restricted zones added."""
    rules, wild, exc = _psl()
    host = host.lower().strip(".")
    parts = host.split(".")
    if len(parts) == 1:
        return host, "", host
    suffix_len = 1
    for i in range(len(parts)):
        cand = ".".join(parts[i:])
        if cand in exc:
            suffix_len = len(parts) - i - 1
            break
        if cand in rules:
            suffix_len = len(parts) - i
            break
        if i + 1 < len(parts) and ".".join(parts[i + 1:]) in wild:
            suffix_len = len(parts) - i
            break
    if suffix_len >= len(parts):
        return host, host, ""
    suffix = ".".join(parts[len(parts) - suffix_len:])
    reg = ".".join(parts[len(parts) - suffix_len - 1:])
    return reg, suffix, parts[len(parts) - suffix_len - 1]


_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.I)
_BARE = re.compile(r"^(?:[^\s/?#@]+@)?(?:[^\s/?#.:@]+\.)+[^\s/?#.:@]{2,}(?::\d{1,5})?(?:[/?#][^\s]*)?$", re.I)
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _idna_decode(label: str) -> str:
    if label.startswith("xn--"):
        try:
            return label[4:].encode("ascii").decode("punycode")
        except Exception:
            return label
    return label


def _to_ascii_host(host: str) -> str:
    out = []
    for lab in host.split("."):
        if lab and not lab.isascii():
            try:
                lab = "xn--" + lab.encode("punycode").decode("ascii")
            except Exception:
                pass
        out.append(lab)
    return ".".join(out)


@dataclass
class Parsed:
    text: str
    is_link: bool
    url: str = ""
    scheme: str = ""          # "" when the user typed no scheme
    host: str = ""
    port: str = ""
    path: str = "/"
    query: str = ""
    userinfo: str = ""
    registrable: str = ""
    suffix: str = ""
    label: str = ""
    subdomain: str = ""
    is_ip: bool = False
    unicode_host: str = ""


def parse(text: str) -> Parsed:
    s = (text or "").strip()
    has_scheme = bool(_SCHEME.match(s))
    if not s or (not has_scheme and (" " in s or not _BARE.match(s))):
        return Parsed(text=s, is_link=False)
    if has_scheme and not re.match(r"^https?://", s, re.I):
        scheme = s.split(":", 1)[0].lower()
        if scheme in ("javascript", "data", "vbscript", "file"):
            return Parsed(text=s, is_link=True, url=s, scheme=scheme)
        return Parsed(text=s, is_link=False)
    try:
        u = urlsplit(s if has_scheme else "http://" + s)
        host = (u.hostname or "").strip(".")
        port = str(u.port or "") if u.port else ""
    except ValueError:
        return Parsed(text=s, is_link=False)
    if not host or "." not in host and not host.startswith("["):
        return Parsed(text=s, is_link=False)
    userinfo = ""
    netloc = u.netloc
    if "@" in netloc:
        userinfo = unquote(netloc.rsplit("@", 1)[0])
    host_ascii = _to_ascii_host(host.lower())
    is_ip = bool(_IPV4.match(host_ascii)) or host_ascii.startswith("[") or ":" in host_ascii
    if is_ip:
        reg, suffix, label = host_ascii, "", host_ascii
    else:
        reg, suffix, label = split_host(host_ascii)
    sub = host_ascii[: -len(reg) - 1] if host_ascii.endswith("." + reg) else ""
    return Parsed(text=s, is_link=True, url=s if has_scheme else "http://" + s,
                  scheme=(u.scheme.lower() if has_scheme else ""), host=host_ascii, port=port,
                  path=u.path or "/", query=u.query or "", userinfo=userinfo, registrable=reg,
                  suffix=suffix, label=label, subdomain=sub, is_ip=is_ip,
                  unicode_host=".".join(_idna_decode(x) for x in host_ascii.split(".")))


# ---------------------------------------------------------------------------
# Signals and report
# ---------------------------------------------------------------------------
@dataclass
class Signal:
    id: str
    points: int            # > 0 risk, < 0 assurance
    level: str             # verified | positive | strong | medium | weak | info
    group: str             # identity | brand | link | words | platform | content
    en: str
    hi: str
    detail: dict = field(default_factory=dict)


@dataclass
class Report:
    input: str
    is_link: bool
    parsed: dict
    identity: dict | None      # who is proven to run the site
    platform: str | None       # free / shared hosting platform the site sits on
    ugc: list | None           # [kind_en, kind_hi] when the page was made by a user of a platform
    signals: list[Signal]
    risk: int
    verdict: str
    score: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signals"] = [asdict(s) for s in self.signals]
        return d

    def negatives(self) -> list[Signal]:
        return [s for s in self.signals if s.points > 0]


def _pieces(s: str) -> list[str]:
    return [p for p in re.split(r"[.\-_]+", s.lower()) if p]


def _segment(rest: str, vocab: set[str]) -> list[str] | None:
    """Split `rest` into vocabulary words (or digit runs). None if impossible."""
    n = len(rest)
    if n == 0:
        return []
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        if best[i] is None:
            continue
        for j in range(i + 1, min(n, i + 20) + 1):
            w = rest[i:j]
            if (w in vocab and len(w) >= 2) or w.isdigit():
                cand = best[i] + [w]
                if best[j] is None or len(cand) < len(best[j]):
                    best[j] = cand
    return best[n]


def _kind_words(words: list[str]) -> dict:
    d = data()
    out = {"credential": [], "service": [], "lure": [], "money": []}
    for w in words:
        for k, bucket in (("credential", "_cred"), ("lure", "_lure"), ("service", "_service"), ("money", "_money")):
            if w in d[bucket]:
                if w not in out[k]:
                    out[k].append(w)
                break
    return out


def _damerau1(a: str, b: str) -> str | None:
    """If a and b differ by exactly one edit, name it; else None."""
    if a == b:
        return None
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return None
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return "sub"
        if len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]:
            return "swap"
        return None
    # one insertion / deletion
    if la > lb:
        long_, short_, op = a, b, "ins"
    else:
        long_, short_, op = b, a, "del"
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short_:
            dup = (i > 0 and long_[i] == long_[i - 1]) or (i + 1 < len(long_) and long_[i] == long_[i + 1])
            return op + ("_dup" if dup else "")
    return None


_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_ADJ: dict[str, set] = {}
for _r, _row in enumerate(_ROWS):
    for _i, _c in enumerate(_row):
        n = set()
        for _j in (_i - 1, _i + 1):
            if 0 <= _j < len(_row):
                n.add(_row[_j])
        if _r > 0:
            for _j in (_i, _i + 1):
                if _j < len(_ROWS[_r - 1]):
                    n.add(_ROWS[_r - 1][_j])
        if _r < 2:
            for _j in (_i - 1, _i):
                if 0 <= _j < len(_ROWS[_r + 1]):
                    n.add(_ROWS[_r + 1][_j])
        _ADJ[_c] = n
for _c in _ROWS[0] + _ROWS[1] + _ROWS[2]:
    for _o in list(_ADJ[_c]):
        _ADJ.setdefault(_o, set()).add(_c)
_PHONETIC = {frozenset(x) for x in ("ck", "kq", "sz", "iy", "vw", "uv", "gj", "mn", "il", "o0", "l1", "i1", "e3", "a4", "s5", "b8", "g9")}


def _sub_char(a: str, b: str) -> tuple[str, str] | None:
    if len(a) != len(b):
        return None
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return (a[diff[0]], b[diff[0]]) if len(diff) == 1 else None


def _typo_sub(x: str, y: str) -> bool:
    return frozenset((x, y)) in _PHONETIC or y in _ADJ.get(x, ()) or data()["homoglyphs"].get(x) == y or data()["homoglyphs"].get(y) == x


def _dl(a: str, b: str, limit: int = 3) -> int:
    """Damerau-Levenshtein distance (optimal string alignment), stops early past `limit`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        lo = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
            lo = min(lo, v)
        if lo > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[lb]


def _homo(s: str) -> str:
    d = data()
    for k, v in d["multi_homoglyphs"].items():
        s = s.replace(k, v)
    s = "".join(d["homoglyphs"].get(c, c) for c in s)
    return s.replace("l", "i").replace("1", "i")


def _randomish(label: str) -> bool:
    """Machine-made labels like 'qwvlxcwevjpic8psemq' or 'doiw0zuhcw9rosjhic'."""
    d = data()
    for piece in re.split(r"[\-_.]+", label.lower()):
        s = re.sub(r"[^a-z0-9]", "", piece)
        if len(s) < 8 or _segment(s, d["_vocab_and_brands"]) is not None:
            continue
        letters = re.sub(r"[^a-z]", "", s)
        digits = len(s) - len(letters)
        vowels = sum(c in "aeiou" for c in letters)
        if letters and vowels / len(letters) < 0.2:
            return True
        if len(re.findall(r"[a-z]\d+[a-z]", s)) >= 2:
            return True
        if digits >= 3 and len(letters) >= 4 and 0.2 <= digits / len(s) <= 0.8:
            return True
        if max((len(x) for x in re.findall(r"[^aeiouy\d]+", letters)), default=0) >= 6:
            return True
    return False


def _is_foreign_gov(suffix: str) -> bool:
    labs = suffix.split(".")
    return any(x in ("gov", "gob", "gouv", "govt", "go", "mil", "gv") for x in labs) or suffix in ("gov", "mil", "int")


def identity_of(p: Parsed) -> dict | None:
    """Proof of who owns the address, or None."""
    d = data()
    if not p.is_link or p.is_ip or not p.host:
        return None
    on_platform = platform_of(p) is not None
    # restricted Indian zone
    for zone, meta in d["zones"].items():
        if p.suffix == zone or p.host.endswith("." + zone):
            b = d["_official"].get(p.registrable)
            k = d["known"].get(p.registrable)
            name = (b or {}).get("name") or (k[0] if k else None)
            en = (f"This is {name}'s official address. " if name else "") + meta["en"]
            hi = (f"यह {name} का आधिकारिक पता है। " if name else "") + meta["hi"]
            return {"source": "zone", "zone": zone, "name": name, "kind": (b or {}).get("kind") or meta["kind"], "verified": meta["verified"],
                    "brand": (b or {}).get("id"), "en": en, "hi": hi}
    if on_platform:
        return None
    tld = p.host.rsplit(".", 1)[-1]
    if tld in d["brand_tlds"]:
        b = next((x for x in d["brands"] if x["id"] == d["brand_tlds"][tld]), None)
        if b:
            return {"source": "brand_tld", "name": b["name"], "kind": b["kind"], "verified": True, "brand": b["id"],
                    "en": f"Address on .{tld}, a top-level domain only {b['name']} can use.",
                    "hi": f".{tld} पर पता, जिसे सिर्फ़ {b['name']} इस्तेमाल कर सकता है।"}
    for cand in (p.host, p.registrable):
        b = d["_official"].get(cand)
        k = d["known"].get(cand)
        if b and not (k and b["official"][0] != cand):
            return {"source": "brand", "name": b["name"], "kind": b["kind"], "verified": True, "brand": b["id"],
                    "en": f"This is an official {b['name']} address ({p.registrable}).",
                    "hi": f"यह {b['name']} का आधिकारिक पता है ({p.registrable})।"}
        if k:
            return {"source": "known", "name": k[0], "kind": k[1], "verified": bool(b),
                    "en": f"This is the real {k[0]} website ({p.registrable}).",
                    "hi": f"यह {k[0]} की असली वेबसाइट है ({p.registrable})।"}
    return None


def platform_of(p: Parsed) -> str | None:
    d = data()
    if not p.is_link or not p.suffix or not p.label:
        return None
    for fh in d["_free"]:
        if p.suffix == fh or p.suffix.endswith("." + fh):
            return fh
    return None


def ugc_of(p: Parsed, ident: dict | None) -> list | None:
    d = data()
    if not p.is_link:
        return None
    host = p.host.removeprefix("www.").removeprefix("m.")
    kind = d["_ugc"].get(host) or d["_ugc"].get(p.registrable)
    if not kind:
        return None
    path = p.path.rstrip("/") or "/"
    if host == "play.google.com":
        return kind if "id=" in p.query else None
    if path in d["_generic_paths"] and not p.query:
        return None
    if p.registrable == "linkedin.com":
        if path.startswith("/in/"):
            return ["profile", "प्रोफ़ाइल"]
        if path.startswith("/company/"):
            return ["company page", "कंपनी पेज"]
        if path.startswith("/jobs/"):
            return ["job post", "नौकरी की पोस्ट"]
    return kind


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def _brand_label_hits(p: Parsed, risky_tld: bool, on_free: bool) -> list[Signal]:
    d = data()
    out: list[Signal] = []
    label = p.label
    label_pieces = [x for x in re.split(r"[\-_]+", label) if x]
    sub_pieces = [x for x in _pieces(p.subdomain) if x not in ("www", "m", "en", "in")]
    seen = set()

    for b in d["brands"]:
        if b["id"] in seen:
            continue
        name, real = b["name"], b["official"][0]
        tokens = [t for t in b["tokens"] if t]
        fused = [f for f in b["fused"] if len(f) >= 4]
        off_labels = set()
        for x in b["official"]:
            reg, sfx, lab = split_host(x)
            if "." in x and reg == x and sfx not in d["zones"] and lab and len(lab) >= 3:
                off_labels.add(lab)
        hit = None

        # 1. the brand (or one of its addresses) in front of someone else's address
        host_wo_reg = p.subdomain
        if host_wo_reg:
            emb = next((od for od in b["official"] if "." in od and (host_wo_reg == od or host_wo_reg.endswith("." + od) or ("." + od + ".") in ("." + host_wo_reg + ".") or host_wo_reg.startswith(od + "."))), None)
            if emb or any(sp in tokens or sp in off_labels or any(f in sp for f in fused if len(f) >= 5) for sp in sub_pieces):
                hit = Signal("BRAND_IN_SUBDOMAIN", 70, "strong", "brand",
                             f"Puts the name {name} in front of a different website ({p.registrable}). {name}'s real site is {real}.",
                             f"{name} का नाम किसी दूसरी वेबसाइट ({p.registrable}) के आगे लगाया गया है। {name} की असली साइट {real} है।",
                             {"brand": b["id"], "real": real, "where": "subdomain"})

        # 2. the brand inside the address itself
        if not hit:
            for i, pc in enumerate(label_pieces):
                others = label_pieces[:i] + label_pieces[i + 1:]
                kind = None
                rest_words: list[str] = []
                if pc in tokens or pc in fused:
                    kind = "piece"
                    rest_words = others
                else:
                    f = next((f for f in sorted(fused, key=len, reverse=True) if f in pc), None)
                    if not f:
                        f = next((t for t in sorted(tokens, key=len, reverse=True) if len(t) >= 3 and (pc.startswith(t) or pc.endswith(t)) and len(pc) > len(t)), None)
                        if f:
                            rest = pc.replace(f, "", 1)
                            seg = _segment(rest, d["_vocab_and_brands"])
                            if seg is None or (len(f) <= 4 and not any(len(w) >= 3 and not w.isdigit() for w in seg)):
                                f = None
                    if f:
                        rest = pc.replace(f, "", 1)
                        seg = _segment(rest, d["_vocab_and_brands"])
                        kind = "fused" if seg is not None else "fused_unclear"
                        rest_words = (seg or []) + others
                if not kind and pc in (b.get("weak") or []) and others:
                    kind, rest_words = "weak_piece", others
                if not kind:
                    continue
                words = _kind_words(rest_words + [w for o in others for w in (_segment(o, d["_vocab"]) or [])])
                bad_words = words["credential"] + words["service"] + words["lure"] + [w for w in words["money"] if w not in ("card", "pay")]
                if kind == "weak_piece":
                    bad_only = words["credential"] + words["lure"] + [w for w in words["service"] if w not in ("service", "services", "support", "care", "customer")]
                    if not bad_only:
                        continue
                    hit = Signal("BRAND_IMPERSONATION", 75, "strong", "brand",
                                 f"Uses the name {name} next to words like “{'”, “'.join(bad_only[:2])}”, but {name}'s real site is {real}.",
                                 f"{name} का नाम “{'”, “'.join(bad_only[:2])}” जैसे शब्दों के साथ इस्तेमाल करता है, पर {name} की असली साइट {real} है।",
                                 {"brand": b["id"], "real": real, "words": bad_only[:2]})
                elif kind == "fused_unclear":
                    if not bad_words:  # "loginpaytmm": the rest does not split into words, but holds a bait word
                        left = pc.replace(f, "", 1)
                        bad_words = [w for w in sorted(d["_cred"] | d["_lure"], key=len, reverse=True) if len(w) >= 5 and w in left][:2]
                    if risky_tld or on_free or bad_words:
                        hit = Signal("BRAND_LOOKALIKE_NAME", 70, "strong", "brand",
                                     f"Uses the name {name} in an address {name} does not own. {name}'s real site is {real}.",
                                     f"ऐसे पते में {name} का नाम है जो {name} का नहीं है। {name} की असली साइट {real} है।",
                                     {"brand": b["id"], "real": real, "where": "label"})
                    else:
                        hit = Signal("BRAND_NAME_INSIDE", 15, "weak", "brand",
                                     f"The address contains the letters of {name}, but it is not {name}'s site ({real}).",
                                     f"पते में {name} के अक्षर हैं, पर यह {name} की साइट ({real}) नहीं है।",
                                     {"brand": b["id"], "real": real})
                elif bad_words or risky_tld or on_free or (b["intl"] is False and kind == "piece" and others and False):
                    why = (bad_words[:2] if bad_words else [])
                    extra_en = f" next to words like “{'”, “'.join(why)}”" if why else ""
                    extra_hi = f" और “{'”, “'.join(why)}” जैसे शब्दों के साथ" if why else ""
                    hit = Signal("BRAND_IMPERSONATION", 75, "strong", "brand",
                                 f"Uses the name {name}{extra_en}, but {name}'s real site is {real}.",
                                 f"{name} का नाम{extra_hi} इस्तेमाल करता है, पर {name} की असली साइट {real} है।",
                                 {"brand": b["id"], "real": real, "words": why})
                else:
                    pts = 15 if b.get("intl") else 35
                    hit = Signal("BRAND_NAME_UNOFFICIAL", pts, "weak" if pts < 31 else "medium", "brand",
                                 f"Uses the name {name}, but {name}'s real site is {real}.",
                                 f"{name} का नाम इस्तेमाल करता है, पर {name} की असली साइट {real} है।",
                                 {"brand": b["id"], "real": real})
                break

        # 3. the brand's own name with another ending (sbi.mx, paytm.co)
        if not hit and "-" not in label and label in off_labels:
            very = p.suffix.rsplit(".", 1)[-1] in d["_very_risky"]
            pts = 70 if very else (15 if b.get("intl") else 35)
            hit = Signal("BRAND_OTHER_ENDING", pts, "strong" if pts >= 70 else ("medium" if pts >= 31 else "weak"), "brand",
                         f"Has {name}'s name but a different ending (.{p.suffix}). {name}'s real site is {real}.",
                         f"इसमें {name} का नाम है पर अंत अलग है (.{p.suffix})। {name} की असली साइट {real} है।",
                         {"brand": b["id"], "real": real})
        if hit:
            seen.add(b["id"])
            out.append(hit)
            if hit.level == "strong":
                break
    # keep only the strongest brand claim
    out.sort(key=lambda s: -s.points)
    return out[:1]


def _lookalike_hits(p: Parsed) -> list[Signal]:
    d = data()
    cands = set()
    lab = p.label
    cands.add(lab.replace("-", ""))
    cands.update(x for x in re.split(r"[\-_]+", lab) if x)
    for sp in _pieces(p.subdomain):
        cands.add(sp)
    extra = set()
    for c in list(cands):
        for w in d["_vocab"]:
            if len(w) >= 3 and len(c) - len(w) >= 5:
                if c.endswith(w):
                    extra.add(c[: -len(w)])
                if c.startswith(w):
                    extra.add(c[len(w):])
    extra -= cands  # a cut-off word: its first letters are uncertain ("for|besindia" from forbesindia)
    cands |= extra
    cands = {c for c in cands if len(c) >= 5 and c not in d["_vocab"] and c not in d["_known_labels"] and c not in d["_look_exc"]}
    for c in sorted(cands, key=len, reverse=True):
        hc = _homo(c)
        for base, b in d["_look"]:
            if c == base or base in c:
                continue  # the brand spelled correctly inside a longer name is checked elsewhere
            why = None
            if hc == _homo(base):
                why = "letters swapped for lookalikes"
            else:
                op = _damerau1(c, base)
                if op and len(base) < 9 and c[0] != base[0] and d["homoglyphs"].get(c[0]) != base[0] and op != "swap":
                    op = None  # a different first letter is a different word, not a typo
                if op == "sub" and len(base) < 9:
                    pair = _sub_char(c, base)
                    if not pair or not _typo_sub(*pair) or (c[0] != base[0] and d["homoglyphs"].get(c[0]) != base[0]):
                        op = None
                if op and (len(base) >= 7 or op in ("swap", "ins_dup", "del_dup") or (op == "sub" and len(base) >= 6)):
                    why = {"sub": "one letter changed", "swap": "two letters swapped", "ins": "one extra letter", "del": "one letter missing",
                           "ins_dup": "a letter doubled", "del_dup": "a doubled letter dropped"}[op]
                elif op is None and len(base) >= 10 and abs(len(c) - len(base)) <= 3 and c[:2] == base[:2]:
                    lim = 3 if len(base) >= 14 else 2
                    if _dl(_homo(c), _homo(base), lim) <= lim:
                        why = "a few letters changed"
            if why and c in extra and why != "letters swapped for lookalikes" and c[:2] != base[:2]:
                why = None
            if why:
                real = b["official"][0]
                return [Signal("LOOKALIKE", 70, "strong", "brand",
                               f"Spelled to look like {b['name']} ({why}: “{c}” vs “{base}”), but it is a different website. The real site is {real}.",
                               f"{b['name']} जैसा दिखने के लिए लिखा गया है (“{c}” बनाम “{base}”), पर यह अलग वेबसाइट है। असली साइट {real} है।",
                               {"brand": b["id"], "real": real, "candidate": c, "base": base, "why": why})]
    return []


def _hyphen_copy_hits(p: Parsed) -> list[Signal]:
    """An official address rebuilt with hyphens instead of dots: "sbi-bank.in" for
    sbi.bank.in, "hdfcbank-com.xyz" for hdfcbank.com. The hyphen must sit inside
    the copied address; "images-amazon.com" is only a brand name with a prefix."""
    d = data()
    if "-" not in p.host:
        return []
    host = p.host
    conv = host.replace("-", ".")
    for i in range(len(conv)):
        if i and conv[i - 1] != ".":
            continue
        for od, b in ((x, y) for x, y in d["_official"].items() if "." in x and conv.startswith(x, i)):
            j = i + len(od)
            if j < len(conv) and conv[j] != ".":
                continue
            original = host[i:j]
            if "-" in original and original != od and not host.endswith("." + od) and host != od:
                return [Signal("HYPHEN_COPY", 75, "strong", "brand",
                               f"Copies the address {od} by swapping dots for hyphens. It is not {b['name']}'s site.",
                               f"बिंदुओं की जगह हाइफ़न लगाकर {od} पते की नकल करता है। यह {b['name']} की साइट नहीं है।",
                               {"brand": b["id"], "real": od})]
        for zone, meta in d["zones"].items():
            if not meta["verified"]:
                continue
            m = re.match(r"[a-z0-9]+\." + re.escape(zone) + r"(?=\.|$)", conv[i:])
            if m and "-" in host[i:i + m.end()] and not host.endswith("." + zone):
                tail = m.group(0)
                b = d["_official"].get(tail)
                name = b["name"] if b else "an official Indian bank / government body"
                return [Signal("HYPHEN_COPY", 75, "strong", "brand",
                               f"Copies the address {tail} by swapping dots for hyphens. It is not {name}'s site.",
                               f"बिंदुओं की जगह हाइफ़न लगाकर {tail} पते की नकल करता है। यह {name} की साइट नहीं है।",
                               {"brand": (b or {}).get("id"), "real": tail})]
    return []


def _gov_hits(p: Parsed) -> list[Signal]:
    d = data()
    if _is_foreign_gov(p.suffix) or p.suffix in ("gov.in", "nic.in") or p.label in ("gov", "gob", "gouv", "govt", "go", "gv", "mil"):
        return []
    labels = (p.subdomain + "." + p.label).strip(".").split(".")
    pieces = [x for lab in labels for x in re.split(r"[\-_]+", lab) if x]
    strong_words = {"gov", "govt", "goi", "govin", "nicin", "mygov", "pmyojana", "pradhanmantri", "modiyojana", "pmmodi", "bharatsarkar"}
    joined = "-".join(pieces)
    if any(x in strong_words for x in pieces) or re.search(r"(^|[.\-])gov[\-.]?in([.\-]|$)", "." + ".".join(labels) + ".") or "gov-in" in joined:
        return [Signal("FAKE_GOV", 70, "strong", "brand",
                       "Looks like a government site, but real Indian government sites end in .gov.in or .nic.in.",
                       "सरकारी साइट जैसी दिखती है, पर असली भारतीय सरकारी साइटें .gov.in या .nic.in पर ख़त्म होती हैं।", {})]
    if any(x in ("sarkari", "sarkar", "yojana") for x in pieces):
        return [Signal("GOV_WORDS", 35, "medium", "brand",
                       "Uses government words (sarkari / yojana) but is a private address, not .gov.in.",
                       "सरकारी शब्द (सरकारी / योजना) इस्तेमाल करता है, पर यह निजी पता है, .gov.in नहीं।", {})]
    # nested zone: sbi.bank.in.something.com
    if re.search(r"(^|\.)(bank|fin)\.in\.", p.host + ".") and not (p.suffix in ("bank.in", "fin.in")):
        return [Signal("FAKE_BANK_ZONE", 70, "strong", "brand",
                       "Copies a bank address (.bank.in) inside a different website's address.",
                       "किसी दूसरी वेबसाइट के पते के अंदर बैंक का पता (.bank.in) कॉपी किया गया है।", {})]
    return []


def _words_hits(p: Parsed, brand_found: bool) -> list[Signal]:
    d = data()
    words: list[str] = []
    obfuscated: list[str] = []
    for lab in (p.subdomain + "." + p.label).strip(".").split("."):
        for pc in re.split(r"[\-_]+", lab):
            if not pc:
                continue
            seg = _segment(pc, d["_vocab"])
            if seg:
                words.extend(seg)
                continue
            collapsed = re.sub(r"(.)\1+", r"\1", pc)
            seg2 = _segment(collapsed, d["_vocab"]) if collapsed != pc else None
            if seg2 and any(w in d["_cred"] or w in d["_lure"] for w in seg2):
                obfuscated.append(pc)
                words.extend(seg2)
                continue
            words.append(pc)
            found = sorted((w for w in d["_cred"] | d["_lure"] if len(w) >= 6 and w in pc), key=len, reverse=True)
            kept: list[str] = []
            for w in found:
                if not any(w in k or k in w for k in kept):
                    kept.append(w)
            words.extend(kept)
    k = _kind_words(words)
    cred, svc, lure = sorted(set(k["credential"])), sorted(set(k["service"])), sorted(set(k["lure"]))
    out = []
    if obfuscated:
        out.append(Signal("MISSPELLED_LOGIN", 45, "medium", "words",
                          f"Misspells login words on purpose (“{obfuscated[0]}”) to slip past filters. Real companies don't do this.",
                          f"फ़िल्टर से बचने के लिए लॉग-इन वाले शब्दों की जान-बूझकर गलत स्पेलिंग (“{obfuscated[0]}”)। असली कंपनियाँ ऐसा नहीं करतीं।", {}))
    if brand_found:
        return out
    if len(cred) >= 2 or (cred and (svc or lure)):
        w = (cred + svc + lure)[:3]
        out.append(Signal("LOGIN_BAIT_WORDS", 35, "medium", "words",
                          f"The address is built from login and warning words (“{'”, “'.join(w)}”), as phishing pages are.",
                          f"पता लॉग-इन और चेतावनी वाले शब्दों (“{'”, “'.join(w)}”) से बना है, जैसे फ़िशिंग पेज बनते हैं।", {"words": w}))
    elif len(lure) >= 2 or (lure and (k["money"] or svc)) or (len(set(k["money"])) >= 2 and set(svc) & {"claim", "claims", "apk", "download"}):
        w = (lure + svc + k["money"])[:3]
        out.append(Signal("PRIZE_BAIT_WORDS", 35, "medium", "words",
                          f"The address is built from prize and money words (“{'”, “'.join(w)}”), as scam pages are.",
                          f"पता इनाम और पैसे वाले शब्दों (“{'”, “'.join(w)}”) से बना है, जैसे स्कैम पेज बनते हैं।", {"words": w}))
    elif set(svc) & {"fee", "fees", "deposit"} and (set(words) & {"career", "careers", "job", "jobs", "hiring", "recruit", "recruitment", "intern", "internship", "loan", "loans", "work"}):
        w = sorted(set(words) & {"career", "careers", "job", "jobs", "hiring", "recruit", "recruitment", "intern", "internship", "loan", "loans", "work"})[:1] + sorted(set(svc) & {"fee", "fees", "deposit"})[:1]
        out.append(Signal("JOB_FEE_WORDS", 45, "medium", "words",
                          f"The address itself joins job or loan words with a fee (“{'”, “'.join(w)}”). Real employers and lenders never charge to apply.",
                          f"पता ही नौकरी या लोन वाले शब्दों को फ़ीस से जोड़ता है (“{'”, “'.join(w)}”)। असली कंपनियाँ आवेदन के पैसे नहीं लेतीं।", {"words": w}))
    elif cred or lure:
        w = (cred + lure)[:2]
        out.append(Signal("BAIT_WORD", 10, "weak", "words",
                          f"Uses the word “{w[0]}” in its address.", f"पते में “{w[0]}” शब्द है।", {"words": w}))
    return out


def _path_hits(p: Parsed, trusted_host: bool, on_free: bool) -> list[Signal]:
    d = data()
    if trusted_host:
        return []
    path = unquote(p.path + ("?" + p.query if p.query else "")).lower()
    segs = [x for x in re.split(r"[/?#=&._\-+]+", path) if x]
    out = []
    brand = None
    for b in d["brands"]:
        names = set(b["tokens"]) | {f for f in b["fused"] if len(f) >= 5} | {split_host(x)[2] for x in b["official"] if "." in x and len(split_host(x)[2]) >= 5}
        names = {n for n in names if len(n) >= 4 or n in b["tokens"] and len(n) >= 3}
        long_names = {n for n in names if len(n) >= 6}
        if any(s in names for s in segs) or any(n in s for s in segs for n in long_names) or any(("/" + od + "/") in path or ("/" + od) == path.rstrip("/") for od in b["official"] if "." in od):
            brand = b
            break
    cred_words = [s for s in segs if s in d["_cred"]]
    kit = bool(re.search(r"(login|signin|logon|verify|account|update|secure|auth|billing|webscr|confirm|access|session|validate)\w*\.(php|html?|aspx?)|cmd=login|login_submit|region\.php|particulier|/servlet/|webscr|[?&](email|user|login)=[^&]*@|/\.well-known/[^/]*/(?!acme|security\.txt)", path))
    kit = kit or (bool(cred_words) and bool(re.search(r"\.(php|aspx?)(\?|$)", p.path.lower())))
    embedded = re.search(r"/(?:www\.)?[a-z0-9\-]{3,}\.(?:com|net|org|in|co\.in|co\.uk|io)(?:/|$)", p.path.lower())
    hacked = re.search(r"/wp-(?:content|includes|admin)/(?!uploads/\d{4}/\d{2}/[^/]+\.(?:jpe?g|png|gif|webp|pdf)$).+|/(?:cgi-bin|alfacgiapi|vendor|plugins|modules|components|admin|includes|libraries|cache|tmp|temp|\.well-known)/(?:[^/]+/){0,8}[^/]*(?:\.php|\.html?|/)?(?:\?|$)|/[a-f0-9]{24,}(?:/|$)|/[a-z0-9_\-]*(?:login|signin|verify|secure|account|update|auth)[a-z0-9_\-]*\.(?:php|html?)", p.path.lower())
    if brand:
        lvl_strong = bool(cred_words) or kit or on_free
        out.append(Signal("BRAND_IN_PATH", 70 if lvl_strong else 35, "strong" if lvl_strong else "medium", "brand",
                          f"Shows the name {brand['name']} inside the link{' with a login page' if lvl_strong else ''}, on a site {brand['name']} does not own. {brand['name']}'s real site is {brand['official'][0]}.",
                          f"लिंक के अंदर {brand['name']} का नाम है{' और लॉग-इन पेज है' if lvl_strong else ''}, पर साइट {brand['name']} की नहीं है। असली साइट {brand['official'][0]} है।",
                          {"brand": brand["id"], "real": brand["official"][0]}))
    elif kit:
        out.append(Signal("PHISHING_KIT_PATH", 35, "medium", "link",
                          "The link points to a login or verify page on an unknown site, which is how phishing kits look.",
                          "लिंक किसी अनजान साइट के लॉग-इन या वेरिफ़ाई पेज पर ले जाता है, फ़िशिंग किट ऐसे ही दिखते हैं।", {}))
    elif hacked:
        out.append(Signal("HIDDEN_PAGE", 35, "medium", "link",
                          "The page is hidden deep inside the site's program folders, where hacked websites host scam pages.",
                          "पेज साइट के प्रोग्राम फ़ोल्डरों में गहराई में छिपा है, जहाँ हैक की गई वेबसाइटें स्कैम पेज रखती हैं।", {}))
    elif embedded:
        out.append(Signal("SITE_INSIDE_LINK", 35, "medium", "link",
                          f"Hides another website's name (“{embedded.group(0).strip('/')}”) inside the link to look like it.",
                          f"लिंक के अंदर दूसरी वेबसाइट का नाम (“{embedded.group(0).strip('/')}”) छिपाया गया है ताकि वैसी दिखे।", {}))
    elif len(set(cred_words)) >= 2:
        out.append(Signal("LOGIN_PATH", 15, "weak", "link",
                          "The link goes to a login or account page on a site we can't confirm.",
                          "लिंक ऐसी साइट के लॉग-इन या अकाउंट पेज पर जाता है जिसकी पुष्टि नहीं हो सकी।", {}))
    if on_free and re.fullmatch(r"/(?:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{24,})/?", p.path.lower()):
        out.append(Signal("FREE_HOST_TOKEN", 35, "medium", "platform",
                          "A free-platform page reached through a random code, the way throwaway phishing links are built.",
                          "बेतरतीब कोड से खुलने वाला मुफ़्त प्लेटफ़ॉर्म का पेज, जैसे थोड़े समय के फ़िशिंग लिंक बनते हैं।", {}))
    if re.search(r"\.apk(\?|$|#)", p.path.lower() + ("?" if p.query else "")) or re.search(r"\.apk$", p.path.lower()):
        out.append(Signal("APK_DOWNLOAD", 70, "strong", "content",
                          "It downloads an app file (.apk) from outside the Play Store. Fake bank and KYC apps spread this way.",
                          "यह Play Store के बाहर से ऐप फ़ाइल (.apk) डाउनलोड कराता है। नकली बैंक और KYC ऐप ऐसे ही फैलते हैं।", {}))
    return out


def _structure_hits(p: Parsed, on_free: bool, ident: dict | None) -> list[Signal]:
    d = data()
    out = []
    if p.userinfo:
        out.append(Signal("AT_TRICK", 70, "strong", "link",
                          f"Uses an “@” trick: the part before @ (“{p.userinfo[:40]}”) is only decoration; the link really opens {p.host}.",
                          f"“@” की चाल: @ से पहले वाला हिस्सा (“{p.userinfo[:40]}”) सिर्फ़ दिखावा है; लिंक असल में {p.host} खोलता है।", {}))
    if ident:
        return out
    if p.is_ip:
        out.append(Signal("IP_ADDRESS", 40, "medium", "link",
                          "The link is a bare number (IP address) instead of a website name. Real businesses don't send these.",
                          "लिंक में वेबसाइट का नाम नहीं, सिर्फ़ नंबर (IP पता) है। असली कंपनियाँ ऐसे लिंक नहीं भेजतीं।", {}))
        return out
    labels_puny = [x for x in (p.subdomain + "." + p.label).split(".") if x.startswith("xn--")]
    if labels_puny:
        dec = [_idna_decode(x) for x in labels_puny]
        latin = any(re.search(r"[a-z]", x) for x in dec)
        lookalike = any(any(ch in d["homoglyphs"] for ch in x) for x in dec)
        if lookalike or latin:
            norm = _homo("".join(_idna_decode(x) for x in labels_puny))
            brand = next((b for base, b in d["_look"] if base in norm or norm in base), None)
            pts = 70 if brand or lookalike else 40
            out.append(Signal("PUNYCODE", pts, "strong" if pts >= 70 else "medium", "link",
                              f"The address uses letters from other alphabets that look like English ones ({'.'.join(dec)})"
                              + (f", copying {brand['name']}." if brand else "."),
                              f"पते में दूसरी लिपियों के ऐसे अक्षर हैं जो अंग्रेज़ी जैसे दिखते हैं ({'.'.join(dec)})" + (f", {brand['name']} की नकल।" if brand else "।"),
                              {"decoded": dec}))
    tld = p.host.rsplit(".", 1)[-1]
    if (p.registrable in d["_short"] or p.host in d["_short"]) and (p.path.strip("/") or p.query):
        out.append(Signal("SHORT_LINK", 35, "medium", "link",
                          "A short link hides where it really goes. Open it only if you trust the sender, and check the real address first.",
                          "छोटा लिंक छिपाता है कि यह असल में कहाँ ले जाता है। भरोसेमंद भेजने वाले का हो तभी खोलें, पहले असली पता देखें।", {}))
    if tld in d["_very_risky"]:
        pts = 20 if tld in d["_mid_risky"] else 31
        out.append(Signal("RISKY_ENDING", pts, "medium" if pts >= 31 else "weak", "link",
                          f"Ends in .{tld}, a cheap ending that scam sites use far more than real businesses.",
                          f".{tld} पर ख़त्म होता है, यह सस्ता अंत है जिसे असली कंपनियों से कहीं ज़्यादा स्कैम साइटें इस्तेमाल करती हैं।", {"tld": tld}))
    elif tld in d["_risky"]:
        out.append(Signal("RISKY_ENDING_MILD", 5, "weak", "link",
                          f"Ends in .{tld}, an ending often used by short-lived sites.",
                          f".{tld} पर ख़त्म होता है, यह अंत अक्सर थोड़े समय की साइटों में दिखता है।", {"tld": tld}))
    if on_free:
        out.append(Signal("FREE_HOSTING", 15, "weak", "platform",
                          f"Made on a free website platform ({on_free}) where anyone can publish a page in minutes.",
                          f"मुफ़्त वेबसाइट प्लेटफ़ॉर्म ({on_free}) पर बना है, जहाँ कोई भी मिनटों में पेज बना सकता है।", {"platform": on_free}))
    if _randomish(p.label):
        out.append(Signal("RANDOM_NAME", 35 if on_free else 10, "medium" if on_free else "weak", "link",
                          "The name looks machine-made (random letters and numbers), as throwaway scam sites often are.",
                          "नाम मशीन से बना लगता है (बेतरतीब अक्षर और अंक), जैसे अक्सर थोड़े समय की स्कैम साइटें होती हैं।", {}))
    if on_free and re.fullmatch(r"[a-z]+-[a-z]+-(?:[0-9a-f]{5,7}|\d{4,7})|[a-z]+-\d{6,}|[a-z]+\d{6,}", p.label):
        out.append(Signal("AUTO_NAMED_PAGE", 35, "medium", "platform",
                          "An auto-named test page on a free platform (the name was never changed), typical of throwaway phishing pages.",
                          "मुफ़्त प्लेटफ़ॉर्म पर अपने-आप बने नाम वाला टेस्ट पेज (नाम कभी बदला नहीं गया), थोड़े समय के फ़िशिंग पेज ऐसे ही होते हैं।", {}))
    if re.fullmatch(r"\d{6,}", p.label):
        out.append(Signal("NUMBER_NAME", 15, "weak", "link",
                          "The site name is just a long number, which real businesses don't use.",
                          "साइट का नाम सिर्फ़ एक लंबा नंबर है, असली कंपनियाँ ऐसा नहीं रखतीं।", {}))
    if p.label.count("-") >= 3:
        out.append(Signal("MANY_HYPHENS", 10, "weak", "link",
                          "The address is stuffed with hyphens, a common trick to look official.",
                          "पते में बहुत सारे हाइफ़न हैं, आधिकारिक दिखने की एक आम चाल।", {}))
    if len([x for x in p.subdomain.split(".") if x and x != "www"]) >= 3 or len(p.host) > 55:
        out.append(Signal("LONG_ADDRESS", 10, "weak", "link",
                          "Unusually long address with many parts, often used to hide the real site name.",
                          "असामान्य रूप से लंबा पता, कई हिस्सों वाला, अक्सर असली साइट का नाम छिपाने के लिए।", {}))
    if p.scheme == "http":
        out.append(Signal("NO_HTTPS", 5, "weak", "link", "Not a secure (https) link.", "सुरक्षित (https) लिंक नहीं है।", {}))
    if p.port and p.port not in ("80", "443"):
        out.append(Signal("ODD_PORT", 10, "weak", "link", f"Uses an unusual port (:{p.port}).", f"असामान्य पोर्ट (:{p.port}) इस्तेमाल करता है।", {}))
    return out


def betting_hit(text: str) -> Signal | None:
    d = data()
    t = " " + re.sub(r"[^a-z0-9]+", " ", text.lower()) + " "
    compact = re.sub(r"[^a-z0-9]", "", text.lower())
    for w in d["_betting"]:
        ww = w.replace(" ", "")
        if f" {w} " in t or (len(ww) >= 5 and ww in compact) or (ww in ("1win", "1xbet", "4rabet") and ww in compact):
            return Signal("BETTING", 70, "strong", "content",
                          "Online betting, casino or satta platform. These are illegal or unregulated in most of India, and players often can't withdraw their money.",
                          "ऑनलाइन सट्टा, कैसीनो या बेटिंग प्लेटफ़ॉर्म। भारत के ज़्यादातर हिस्सों में ये ग़ैरक़ानूनी या अनियंत्रित हैं, और अक्सर पैसे वापस नहीं निकलते।",
                          {"word": w})
    return None


# Scam language in names, messages and page text
TEXT_RULES = [
    ("UPFRONT_FEE", 70, re.compile(
        r"\b(?:registration|security|training|kit|onboarding|joining|entry|processing|verification|refundable|insurance|gst|file|documentation|stamp\s*duty)\s*(?:fee|fees|deposit|charges?|amount)\b"
        r"|\bpay\s*(?:rs\.?|₹|inr)?\s*\d{2,6}\s*(?:to|for|as)\b|\b(?:fee|deposit)\s*(?:of\s*)?(?:rs\.?|₹|inr)\s*\d{2,6}"
        r"|पहले\s*फ़?फ?ीस|रजिस्ट्रेशन\s*फ़?फ?ीस", re.I),
     "Asks for a fee or deposit before giving a job, loan or prize. Real employers and lenders don't do this.",
     "नौकरी, लोन या इनाम देने से पहले फ़ीस या डिपॉज़िट माँगता है। असली कंपनियाँ ऐसा नहीं करतीं।"),
    ("GUARANTEED_RETURNS", 70, re.compile(
        r"(?<!not\s)(?<!no\s)(?<!never\s)\b(?:guaranteed|assured|fixed|sure[\s\-]?shot)\s+(?:\d{1,3}\s*%\s*)?(?:daily\s+|monthly\s+|weekly\s+)?(?:returns?|profits?|income)\b"
        r"|\b\d{1,4}\s*%\s*(?:guaranteed|assured|daily|weekly|monthly)\s*(?:returns?|profits?)?\b|\b(?:double|triple)\s+your\s+(?:money|capital|investment)\b|पक्का\s*मुनाफ", re.I),
     "Promises guaranteed or very high returns. SEBI does not allow anyone to promise fixed returns on market investments.",
     "पक्के या बहुत ज़्यादा मुनाफ़े का वादा। SEBI किसी को भी बाज़ार निवेश पर तय मुनाफ़े का वादा करने नहीं देता।"),
    ("TASK_SCAM", 70, re.compile(
        r"\b(?:like|rate|review|subscribe|follow)\w*\s+(?:youtube\s+)?(?:videos?|hotels?|products?|channels?|posts?|pages?)\b.{0,40}\b(?:earn|paid|money|income|rs|₹)"
        r"|\b(?:earn|income)\s*(?:rs\.?|₹|inr)?\s*\d{3,6}\s*(?:daily|per\s*day|a\s*day|/\s*day)|\bprepaid\s+tasks?\b|\btelegram\s+tasks?\b", re.I),
     "Pays you for simple online tasks (likes, reviews, ratings). This is the most common job scam in India: you are later asked to 'invest' to unlock earnings.",
     "आसान ऑनलाइन कामों (लाइक, रिव्यू, रेटिंग) के पैसे का वादा। यह भारत का सबसे आम नौकरी स्कैम है: बाद में कमाई 'अनलॉक' करने के लिए पैसे माँगे जाते हैं।"),
    ("LOTTERY_PRIZE", 70, re.compile(
        r"\b(?:lucky\s*draw|lottery|jackpot|you\s+(?:have\s+)?won|winner\s+of|cash\s*prize|kbc\s*(?:lottery|lucky|winner|prize)|claim\s+(?:your\s+)?(?:prize|reward|gift)|reward\s*points?\s*(?:expir|redeem|claim))", re.I),
     "Says you won a prize, lottery or reward points that you must claim. Nobody gives prizes this way.",
     "कहता है कि आपने इनाम, लॉटरी या रिवॉर्ड पॉइंट जीते हैं जिन्हें क्लेम करना है। कोई भी ऐसे इनाम नहीं देता।"),
    ("VIP_TIPS", 45, re.compile(
        r"\b(?:vip|premium|paid)\s*(?:stock\s*|trading\s*|share\s*|crypto\s*|option\s*)?(?:group|channel|tips|calls?|signals?)\b|\b(?:sure\s*shot|jackpot|100\s*%\s*accurate|intraday|btst|option)\s*(?:tips|calls?|signals?)\b|\bstock\s*tips?\s*(?:group|channel)\b", re.I),
     "Sells stock or trading tips in a group. Only SEBI-registered advisers may give paid tips, and most such groups are scams.",
     "ग्रुप में शेयर या ट्रेडिंग टिप्स बेचता है। सिर्फ़ SEBI-रजिस्टर्ड सलाहकार पैसे लेकर टिप्स दे सकते हैं, और ऐसे ज़्यादातर ग्रुप स्कैम होते हैं।"),
    ("KYC_THREAT", 70, re.compile(
        r"\b(?:kyc|pan|aadhaa?r)\s*(?:update|verify|verification|expired?|pending|blocked|suspend)\w*|\baccount\s+(?:will\s+be\s+)?(?:blocked|suspended|deactivated|closed)\b|\b(?:electricity|power)\s+(?:will\s+be\s+)?(?:cut|disconnected)\b", re.I),
     "Threatens that your account, KYC or electricity will be blocked unless you act now. Banks and boards never ask this by link.",
     "धमकी देता है कि अभी कुछ नहीं किया तो अकाउंट, KYC या बिजली बंद हो जाएगी। बैंक और बोर्ड कभी लिंक से ऐसा नहीं कहते।"),
    ("APK_TEXT", 70, re.compile(r"\b(?:download|install)\s*(?:the\s+)?(?:app\s+)?(?:apk|\.apk)\b|\bapk\s*(?:download|file|install)\b", re.I),
     "Asks you to install an app file (APK) from outside the Play Store. Fake bank and KYC apps steal money this way.",
     "Play Store के बाहर से ऐप फ़ाइल (APK) इंस्टॉल करने को कहता है। नकली बैंक और KYC ऐप ऐसे ही पैसे चुराते हैं।"),
    ("INSTANT_LOAN_PROMISE", 35, re.compile(r"\b(?:instant|quick|urgent|fast)\b.{0,20}\bloans?\b.{0,40}\b(?:minutes?|mins?|no\s*cibil|without\s*(?:documents|cibil))\b|\bloans?\b.{0,30}\b(?:in|within)?\s*\d+\s*(?:minutes?|mins?)\b|\bno\s*cibil\b|\bwithout\s+cibil\b", re.I),
     "Promises a loan in minutes with no CIBIL check, the usual pitch of illegal loan apps.",
     "कुछ मिनटों में बिना CIBIL के लोन का वादा, ग़ैरक़ानूनी लोन ऐप यही कहते हैं।"),
]


def text_hits(text: str) -> list[Signal]:
    out = []
    for rid, pts, rx, en, hi in TEXT_RULES:
        m = rx.search(text or "")
        if m and rid == "VIP_TIPS" and re.search(r"whats\s*app|telegram|t\.me/|wa\.me/", text or "", re.I):
            pts = 70
        if m:
            out.append(Signal(rid, pts, "strong" if pts >= 70 else "medium", "content", en, hi, {"quote": m.group(0)[:80]}))
    b = betting_hit(text or "")
    if b:
        out.append(b)
    return out


def brand_mentioned(text: str) -> dict | None:
    """A brand named in plain text ('Amazon work from home')."""
    d = data()
    t = " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()) + " "
    for b in d["brands"]:
        if b["id"] in ("meta", "telegram", "x", "discord", "linkedin", "google", "openai"):
            continue
        names = set(b["tokens"]) | set(b["fused"]) | {b["name"].lower().split(" (")[0]}
        if any(len(n) >= 3 and f" {n} " in t for n in names):
            return b
    return None


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------
_REDIRECT_KEYS = ("url", "q", "u", "adurl", "redirect", "redirect_uri", "redirect_url", "redir", "next", "continue", "dest", "destination", "target", "link", "goto", "to", "out", "r", "returnurl", "return_url", "return", "jump", "site")


def redirect_target(p: Parsed) -> str | None:
    """Address that a link forwards to through a query parameter (google.com/url?q=...)."""
    if not p.query:
        return None
    from urllib.parse import parse_qsl
    for k, v in parse_qsl(p.query, keep_blank_values=False):
        if k.lower() in _REDIRECT_KEYS:
            v = unquote(v).strip()
            if re.match(r"^(https?:)?//", v, re.I) or (k.lower() in ("url", "adurl", "dest", "destination", "goto") and _BARE.match(v)):
                dp = parse(v if not v.startswith("//") else "https:" + v)
                if dp.is_link and dp.registrable and dp.registrable != p.registrable:
                    return dp.url
    return None


def analyze(text: str, page_text: str = "", _depth: int = 0) -> Report:
    """Everything provable about `text` (a link or a name) without opening it.
    `page_text`, when given, is extra text to scan for scam language."""
    p = parse(text)
    d = data()
    signals: list[Signal] = []
    ident = identity_of(p) if p.is_link else None
    platform = platform_of(p) if p.is_link else None
    ugc = ugc_of(p, ident) if p.is_link else None

    if p.is_link and p.scheme in ("javascript", "data", "vbscript", "file"):
        signals.append(Signal("SCRIPT_LINK", 90, "strong", "link", "This is not a web address but a script or file link. Never open it.",
                              "यह वेब पता नहीं, स्क्रिप्ट या फ़ाइल लिंक है। इसे कभी न खोलें।", {}))
    elif p.is_link:
        if ident:
            signals.append(Signal("IDENTITY", -40 if ident["verified"] else -30, "verified" if ident["verified"] else "positive", "identity",
                                  ident["en"], ident["hi"], {"source": ident["source"]}))
        tld = p.host.rsplit(".", 1)[-1]
        risky_tld = tld in d["_very_risky"]
        brand_sigs: list[Signal] = []
        if not ident and not p.is_ip:
            found = _hyphen_copy_hits(p) + _gov_hits(p) + _brand_label_hits(p, risky_tld, bool(platform)) + _lookalike_hits(p)
            found.sort(key=lambda s: -s.points)
            brand_sigs = found[:1]
            if len(found) > 1 and found[0].id != found[1].id and found[1].points >= 25 and found[0].points < 60:
                brand_sigs = found[:2]
            signals += brand_sigs
            signals += _words_hits(p, brand_found=bool(brand_sigs))
        signals += _structure_hits(p, platform, ident)
        big_company = bool(ident) and ident.get("source") in ("brand", "brand_tld") and not ugc
        signals += _path_hits(p, trusted_host=big_company, on_free=bool(platform))
        # combinations that are stronger than their parts
        neg_ids = {s.id for s in signals if s.points > 0}
        if platform and neg_ids - {"FREE_HOSTING"} and not neg_ids & {"LOGIN_BAIT_WORDS", "PRIZE_BAIT_WORDS", "PHISHING_KIT_PATH", "BAIT_WORD"}:
            signals.append(Signal("FREE_HOST_PLUS", 16, "weak", "platform",
                                  "A free-platform page that also shows other warning signs.",
                                  "मुफ़्त प्लेटफ़ॉर्म का पेज जिसमें और भी ख़तरे के संकेत हैं।", {}))
        if platform and neg_ids & {"LOGIN_BAIT_WORDS", "PRIZE_BAIT_WORDS", "PHISHING_KIT_PATH", "BAIT_WORD"}:
            signals.append(Signal("FREE_HOST_BAIT", 35, "medium", "platform",
                                  "A free-platform page that uses login or prize words is how most phishing pages are made.",
                                  "मुफ़्त प्लेटफ़ॉर्म का पेज जिसमें लॉग-इन या इनाम वाले शब्द हों, ज़्यादातर फ़िशिंग पेज ऐसे ही बनते हैं।", {}))
        if not ident:
            b = betting_hit(p.host + " " + p.path)
            if b:
                signals.append(b)
    # scam language in what the user typed (names, messages) and in page text
    txt = (p.text if not p.is_link else unquote(p.path + " " + p.query).replace("-", " ").replace("_", " ")) + " " + (page_text or "")
    for s in text_hits(txt):
        if not any(x.id == s.id for x in signals):
            if ident and ident.get("verified") and not ugc and s.id in ("APK_TEXT", "INSTANT_LOAN_PROMISE", "VIP_TIPS"):
                continue
            signals.append(s)
    if not p.is_link:
        b = brand_mentioned(p.text)
        if b and any(s.points >= 45 for s in signals):
            signals.append(Signal("BRAND_NAME_USED", 15, "weak", "brand",
                                  f"Uses the name {b['name']} to look trustworthy. {b['name']} never asks for money this way; its real site is {b['official'][0]}.",
                                  f"भरोसेमंद दिखने के लिए {b['name']} का नाम इस्तेमाल करता है। {b['name']} कभी ऐसे पैसे नहीं माँगता; असली साइट {b['official'][0]} है।",
                                  {"brand": b["id"], "real": b["official"][0]}))
    if ugc and ident:
        signals.append(Signal("USER_CONTENT", 0, "info", "platform",
                              f"The website is the real {ident['name'] or 'platform'}, but this {ugc[0]} was made by someone using it. A link check can't tell who.",
                              f"वेबसाइट असली {ident['name'] or 'प्लेटफ़ॉर्म'} है, पर यह {ugc[1]} किसी यूज़र ने बनाया है। लिंक जाँच से पता नहीं चलता कि किसने।",
                              {"kind": ugc[0]}))

    dest = redirect_target(p) if p.is_link else None
    if dest and _depth < 2:
        inner = analyze(dest, _depth=_depth + 1)
        if inner.verdict in ("VERIFIED_OFFICIAL", "LOW_RISK"):
            signals = [s for s in signals if s.id != "IDENTITY"] + [x for x in inner.signals if x.id == "IDENTITY"]
            ident, ugc = inner.identity, inner.ugc
            signals.append(Signal("REDIRECTS_TO_REAL", 0, "info", "link",
                                  f"The link passes through {p.registrable} and then opens {inner.parsed.get('host')}.",
                                  f"लिंक {p.registrable} से होकर {inner.parsed.get('host')} खोलता है।", {"destination": dest[:300]}))
        else:
            signals = [s for s in signals if s.id != "IDENTITY"]
            ident, ugc = None, None
            signals.append(Signal("REDIRECTS_ELSEWHERE", 35, "medium", "link",
                                  f"The link starts on {p.registrable} but forwards you to a different site: {inner.parsed.get('host') or dest[:60]}.",
                                  f"लिंक {p.registrable} से शुरू होता है पर आपको दूसरी साइट पर भेजता है: {inner.parsed.get('host') or dest[:60]}।",
                                  {"destination": dest[:300]}))
            for s2 in inner.signals:
                if s2.points > 0 and not any(x.id == s2.id for x in signals):
                    signals.append(s2)
    risk = sum(s.points for s in signals if s.points > 0)
    verdict, score = decide(risk, ident, ugc, signals, p)
    return Report(input=text, is_link=p.is_link, parsed=asdict(p), identity=ident, platform=platform, ugc=ugc,
                  signals=signals, risk=risk, verdict=verdict, score=score)


def _simple_path(p: Parsed) -> bool:
    segs = [x for x in p.path.split("/") if x]
    return len(segs) <= 2 and not re.search(r"\.(php|aspx?|cgi|html?)$", p.path.lower()) and len(p.query) <= 40


def decide(risk: int, ident: dict | None, ugc, signals: list[Signal], p: Parsed | None = None) -> tuple[str, int]:
    """Verdict from risk points. The score is always 100 - risk."""
    score = max(0, 100 - risk)
    if risk >= HIGH:
        return "HIGH_RISK", score
    if risk >= SUSP:
        return "SUSPICIOUS", score
    if risk >= CAUT:
        return "CAUTION", score
    if ident and not ugc:
        if ident.get("verified"):
            return "VERIFIED_OFFICIAL", score
        if ident.get("source") == "zone" and p is not None and not _simple_path(p):
            return "UNKNOWN", score
        return "LOW_RISK", score
    return "UNKNOWN", min(score, 50)


def assess(text: str) -> dict:
    return analyze(text).to_dict()
