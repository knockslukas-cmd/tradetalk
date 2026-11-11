"""Marktumfeld für tradetalk: Rückenwind, neutral oder Gegenwind.

Prüft für S&P 500, Nasdaq und DAX, ob der Index über seiner 50- und
200-Tage-Linie liegt, liest den VIX aus und zählt, wie viele Aktien den
Liquiditätsfilter bestehen.

Bewertung (Punkte):
  je Index   +1  über 50- und 200-Tage-Linie
              0  gemischt
             -1  unter der 200-Tage-Linie
  VIX        +1  unter vix_calm (Standard 20)
              0  dazwischen
             -1  über vix_stress (Standard 30)
  Summe >= tailwind_min (Standard +3) -> Rückenwind,
        <= headwind_max (Standard -2) -> Gegenwind, sonst neutral

Aufruf aus dem Projektordner:  python3 src/market_regime.py
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from filters import apply_filters, load_config  # noqa: E402

log = logging.getLogger("market_regime")


def download_closes(symbols: list[str], days: int) -> dict[str, pd.Series]:
    # genug Kalendertage für die lange Linie plus Puffer für Feiertage
    period = f"{max(2, days // 250 + 1)}y"
    df = yf.download(
        symbols, period=period, group_by="ticker", auto_adjust=False,
        progress=False, threads=True, multi_level_index=True,
    )
    closes = {}
    for s in symbols:
        if df is not None and s in df.columns.get_level_values(0):
            series = df[s]["Close"].dropna()
            if not series.empty:
                closes[s] = series
    return closes


def index_status(close: pd.Series, short: int, long: int) -> dict:
    last = float(close.iloc[-1])
    sma_s = float(close.tail(short).mean())
    sma_l = float(close.tail(long).mean()) if len(close) >= long else float("nan")
    above_s, above_l = bool(last > sma_s), bool(last > sma_l)
    if above_s and above_l:
        points, label = 1, "über beiden Linien"
    elif not above_l:
        points, label = -1, f"unter der {long}-Tage-Linie"
    else:
        points, label = 0, "gemischt"
    return {
        "date": close.index[-1].date().isoformat(), "close": last,
        "sma_short": sma_s, "sma_long": sma_l,
        "above_short": above_s, "above_long": above_l, "points": points, "label": label,
    }


def vix_points(vix: float, calm: float, stress: float) -> tuple[int, str]:
    if vix < calm:
        return 1, "ruhig"
    if vix > stress:
        return -1, "Stress"
    return 0, "erhöht"


def assess(total: int, tailwind_min: int = 3, headwind_max: int = -2) -> str:
    if total >= tailwind_min:
        return "Rückenwind"
    if total <= headwind_max:
        return "Gegenwind"
    return "neutral"


def compute_regime(cfg: dict) -> dict:
    """Berechnet das Marktumfeld und gibt es als JSON-taugliches dict zurück."""
    mr = cfg["market_regime"]
    short, long = mr["sma_short"], mr["sma_long"]
    indices: dict[str, str] = mr["indices"]
    closes = download_closes(list(indices) + [mr["vix"]], long)

    total = 0
    rows = []
    for symbol, name in indices.items():
        if symbol not in closes:
            rows.append({"symbol": symbol, "name": name, "available": False})
            continue
        s = index_status(closes[symbol], short, long)
        total += s["points"]
        rows.append({"symbol": symbol, "name": name, "available": True, **s})

    vix = None
    if mr["vix"] in closes:
        value = float(closes[mr["vix"]].iloc[-1])
        p, label = vix_points(value, mr["vix_calm"], mr["vix_stress"])
        total += p
        vix = {"value": value, "points": p, "label": label,
               "date": closes[mr["vix"]].index[-1].date().isoformat()}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sma_short": short,
        "sma_long": long,
        "indices": rows,
        "vix": vix,
        "points": total,
        "verdict": assess(total, mr.get("tailwind_min", 3), mr.get("headwind_max", -2)),
    }


def mark(flag: bool) -> str:
    return "ja " if flag else "nein"


def print_regime(regime: dict) -> None:
    short, long = regime["sma_short"], regime["sma_long"]
    print("\nMarktumfeld\n")
    print(f"  {'Index':<18} {'Stand':>10} {'SMA' + str(short):>10} {'SMA' + str(long):>10}  "
          f"{'>' + str(short):<5} {'>' + str(long):<5} Bewertung")
    for s in regime["indices"]:
        if not s["available"]:
            print(f"  {s['name']:<18} keine Daten – wird nicht gewertet")
            continue
        print(f"  {s['name']:<18} {s['close']:>10,.0f} {s['sma_short']:>10,.0f} {s['sma_long']:>10,.0f}  "
              f"{mark(s['above_short']):<5} {mark(s['above_long']):<5} {s['label']} ({s['points']:+d})")
    vix = regime["vix"]
    if vix:
        print(f"\n  VIX {vix['value']:.1f} – {vix['label']} ({vix['points']:+d})")
    else:
        print("\n  VIX: keine Daten – wird nicht gewertet")
    print(f"\n  Einschätzung: {regime['verdict']} (Punkte: {regime['points']:+d})")
    if "liquid_count" in regime:
        share = regime["liquid_count"] / regime["universe_count"] * 100 if regime["universe_count"] else 0
        print(f"\n  Liquiditätsfilter: {regime['liquid_count']} von {regime['universe_count']} "
              f"Aktien bestehen ({share:.0f} %)\n")


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    cfg = load_config()
    regime = compute_regime(cfg)
    passed, result = apply_filters(cfg, show_progress=False)
    regime.update(liquid_count=len(passed), universe_count=len(result))
    print_regime(regime)
    return 0


if __name__ == "__main__":
    sys.exit(main())
