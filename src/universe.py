"""Baut das Aktien-Universum für tradetalk.

US-Aktien:   Nasdaq-Trader-Symbollisten (nasdaqlisted.txt, otherlisted.txt),
             ohne ETFs, Testsymbole, Warrants, Units und Vorzugsaktien.
Deutschland: Mitglieder von DAX, MDAX, SDAX und TecDAX (Quelle: onvista),
             Ticker mit Suffix .DE.

Ergebnis: data/universe/tickers.csv (Spalten: ticker, name, exchange, country)

Aufruf aus dem Projektordner:  python3 src/universe.py
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
COLUMNS = ["ticker", "name", "exchange", "country"]

log = logging.getLogger("universe")

# Börsenkürzel in otherlisted.txt
OTHER_EXCHANGES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}

# --------------------------------------------------------------------------- #
# Filtermuster (werden auf den Wertpapiernamen angewendet)
# --------------------------------------------------------------------------- #
RE_WARRANT = re.compile(r"\bwarrants?\b", re.I)
RE_UNIT = re.compile(r"\bunits?\b", re.I)
# MLPs und Royalty-Trusts handeln "Common Units"/"Trust Units" – das sind
# Anteile und keine SPAC-Units, sie bleiben drin.
RE_EQUITY_UNIT = re.compile(
    r"\bcommon units?\b|\bunits? representing\b|\blimited partner(ship)? units?\b"
    r"|\bunits? of beneficial interest\b|\btrust units?\b",
    re.I,
)
RE_PREFERRED = re.compile(
    r"\bpreferred (stock|shares?|securities|units?)\b"
    r"|\s-\s*preferred\b"
    r"|\bpfd\b"
    r"|\bpreference shares?\b"
    r"|\bdepositary shares?\b.*\bpreferred\b"
    r"|\bseries [a-z]{1,2}\b.*\bcumulative\b",
    re.I,
)
RE_RIGHT = re.compile(
    r"\brights?\s*$|\brights?,|\bcontingent value rights?\b|\bsubscription rights?\b", re.I
)
RE_DEBT = re.compile(
    r"\d[\d.]*\s*%.*\b(notes?|debentures?|bonds?)\b"
    r"|\bsenior notes?\b|\bsubordinated notes?\b|\bdebentures?\b"
    r"|\bETNs?\b|\bexchange[- ]traded notes?\b",
    re.I,
)
# Symbolendungen in otherlisted.txt: AAC.U = Unit, AAC.W = Warrant, XYZ.R = Right
RE_OTHER_SUFFIX = re.compile(r"\.(U|W|WS|WT|R|RT)$")

# Zusätze wie "- Common Stock", die im Namen nicht gebraucht werden
RE_NAME_SUFFIX = re.compile(
    r"\s*-?\s*\b(Class [A-Z]\s+)?(Common Stock|Common Shares|Ordinary Shares|"
    r"American Depositary Shares|Capital Stock)\b.*$",
    re.I,
)


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def make_session(cfg: dict) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = cfg["http"]["user_agent"]
    return session


def fetch_text(session: requests.Session, url: str, timeout: int, params: dict | None = None) -> str:
    resp = session.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def clean_name(name: str) -> str:
    name = name.strip()
    cleaned = RE_NAME_SUFFIX.sub("", name).strip(" -,")
    return cleaned or name


def exclusion_reason(name: str, drop_rights: bool = True, drop_debt: bool = True) -> str | None:
    """Warum ein Wertpapier keine Stammaktie ist – oder None, wenn es eine ist."""
    if RE_WARRANT.search(name):
        return "warrant"
    if RE_UNIT.search(name) and not RE_EQUITY_UNIT.search(name):
        return "unit"
    if RE_PREFERRED.search(name):
        return "preferred"
    if drop_rights and RE_RIGHT.search(name):
        return "right"
    if drop_debt and RE_DEBT.search(name):
        return "debt"
    return None


# --------------------------------------------------------------------------- #
# US-Aktien
# --------------------------------------------------------------------------- #
def read_symbol_file(text: str) -> pd.DataFrame:
    """Liest eine Nasdaq-Trader-Datei (Pipe-getrennt, letzte Zeile = Zeitstempel)."""
    df = pd.read_csv(io.StringIO(text), sep="|", dtype=str, keep_default_na=False)
    df = df[~df.iloc[:, 0].str.startswith("File Creation Time")]
    return df.apply(lambda col: col.str.strip())


def load_us(cfg: dict, session: requests.Session) -> pd.DataFrame:
    us = cfg["universe"]["us"]
    timeout = cfg["http"]["timeout"]
    sep = us.get("class_separator", "-")
    removed: dict[str, int] = {}

    def count(reason: str, n: int) -> None:
        if n:
            removed[reason] = removed.get(reason, 0) + n

    # nasdaqlisted.txt
    nas = read_symbol_file(fetch_text(session, us["nasdaq_listed_url"], timeout))
    mask = (nas["Test Issue"] == "Y") | (nas["ETF"] == "Y")
    if "NextShares" in nas:
        mask |= nas["NextShares"] == "Y"
    count("test/etf", int(mask.sum()))
    nas = nas[~mask]
    nas = pd.DataFrame({"ticker": nas["Symbol"], "name": nas["Security Name"], "exchange": "NASDAQ"})

    # otherlisted.txt
    oth = read_symbol_file(fetch_text(session, us["other_listed_url"], timeout))
    mask = (oth["Test Issue"] == "Y") | (oth["ETF"] == "Y")
    count("test/etf", int(mask.sum()))
    oth = oth[~mask]

    sym = oth["ACT Symbol"]
    pref = sym.str.contains("$", regex=False)
    suffix = sym.str.contains(RE_OTHER_SUFFIX)
    count("preferred", int(pref.sum()))
    count("unit/warrant/right", int((suffix & ~pref).sum()))
    oth = oth[~pref & ~suffix]

    unknown = sorted(set(oth["Exchange"]) - set(OTHER_EXCHANGES))
    if unknown:
        log.warning("Unbekannte Börsenkürzel in otherlisted.txt: %s", unknown)
    oth = pd.DataFrame(
        {
            "ticker": oth["ACT Symbol"].str.replace(".", sep, regex=False),
            "name": oth["Security Name"],
            "exchange": oth["Exchange"].map(OTHER_EXCHANGES).fillna("Code " + oth["Exchange"]),
        }
    )

    # gemeinsame Namensfilter
    df = pd.concat([nas, oth], ignore_index=True)
    reasons = df["name"].map(
        lambda n: exclusion_reason(n, us.get("drop_rights", True), us.get("drop_debt", True))
    )
    for reason, n in reasons.value_counts().items():
        count(reason, int(n))
    df = df[reasons.isna() & (df["ticker"] != "")].copy()

    df["name"] = df["name"].map(clean_name)
    df["country"] = "US"
    df = df.drop_duplicates("ticker")

    log.info("US: %d Aktien behalten, entfernt: %s", len(df), removed)
    return df[COLUMNS]


# --------------------------------------------------------------------------- #
# Deutsche Indizes
# --------------------------------------------------------------------------- #
def find_constituents(node) -> dict | None:
    """Sucht im __NEXT_DATA__-JSON von onvista den Block 'constituents'."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            block = cur.get("constituents")
            if isinstance(block, dict) and isinstance(block.get("list"), list):
                return block
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def fetch_index_page(session, url: str, timeout: int, params: dict | None = None):
    html = fetch_text(session, url, timeout, params)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError(f"keine Indexdaten in {url} (Seitenaufbau geändert?)")
    block = find_constituents(json.loads(m.group(1)))
    if block is None:
        raise ValueError(f"keine Indexmitglieder in {url}")
    members = []
    for entry in block["list"]:
        inst = entry.get("instrument") or {}
        # "symbol" ist das Xetra-Kürzel; "homeSymbol" kann das Heimatbörsen-Kürzel
        # sein (z. B. QGEN statt QIA bei Qiagen)
        symbol = inst.get("symbol") or inst.get("homeSymbol")
        if symbol and inst.get("isin"):
            members.append({"isin": inst["isin"], "symbol": symbol, "name": inst.get("name", "")})
    return int(block.get("total") or len(members)), members


def load_index(session, url: str, timeout: int) -> list[dict]:
    """Lädt alle Mitglieder eines Index (onvista zeigt höchstens 50 pro Seite)."""
    total, members = fetch_index_page(session, url, timeout)
    by_isin = {m["isin"]: m for m in members}
    if len(by_isin) < total:
        _, rest = fetch_index_page(session, url, timeout, params={"order": "DESC"})
        for m in rest:
            by_isin.setdefault(m["isin"], m)
    if len(by_isin) != total:
        log.warning("%s: nur %d von %d Mitgliedern gefunden", url, len(by_isin), total)
    return list(by_isin.values())


def load_de(cfg: dict, session: requests.Session) -> pd.DataFrame:
    de = cfg["universe"]["de"]
    timeout = cfg["http"]["timeout"]
    rows: dict[str, dict] = {}
    for index_name, url in de["indices"].items():
        try:
            members = load_index(session, url, timeout)
        except (requests.RequestException, ValueError) as exc:
            log.error("%s konnte nicht geladen werden: %s", index_name, exc)
            continue
        log.info("%s: %d Werte", index_name, len(members))
        overrides = de.get("symbol_overrides") or {}
        for m in members:
            symbol = overrides.get(m["symbol"], m["symbol"])
            # TecDAX-Werte stecken auch in DAX/MDAX/SDAX -> nach ISIN entdoppeln
            rows.setdefault(
                m["isin"],
                {
                    "ticker": f"{symbol}{de['suffix']}",
                    "name": m["name"],
                    "exchange": de["exchange"],
                    "country": de["country"],
                },
            )
    df = pd.DataFrame(list(rows.values()), columns=COLUMNS)
    return df.drop_duplicates("ticker")


# --------------------------------------------------------------------------- #
# Hauptprogramm
# --------------------------------------------------------------------------- #
def build_universe(cfg: dict) -> pd.DataFrame:
    session = make_session(cfg)
    df = pd.concat([load_us(cfg, session), load_de(cfg, session)], ignore_index=True)
    return df.sort_values(["country", "exchange", "ticker"], ascending=[False, True, True])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    out_path = ROOT / cfg["paths"]["tickers_csv"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = build_universe(cfg)
    df.to_csv(out_path, index=False, encoding="utf-8")

    print(f"\n{len(df)} Ticker gespeichert in {out_path.relative_to(ROOT)}\n")
    print("Ticker pro Börse:")
    counts = df["exchange"].value_counts()
    width = max(len(e) for e in counts.index)
    for exchange, n in counts.items():
        print(f"  {exchange:<{width}}  {n:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
