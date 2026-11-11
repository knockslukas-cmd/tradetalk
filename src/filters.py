"""Liquiditätsfilter für das tradetalk-Universum.

Behält nur Aktien mit
- letztem Schlusskurs >= filters.min_price
- Ø Tagesumsatz (Close x Volume) über filters.avg_volume_days Tage
  >= filters.min_avg_dollar_volume
- aktuellen Kursdaten (letzter Kurs höchstens filters.max_stale_days alt)

Die Grenzen gelten in Handelswährung (USD für US-, EUR für DE-Aktien).

Ergebnis: data/universe/liquid.csv

Aufruf aus dem Projektordner:  python3 src/filters.py
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

log = logging.getLogger("filters")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def price_path(prices_dir: Path, ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("^", "_")
    return prices_dir / f"{safe}.parquet"


def liquidity_stats(path: Path, days: int) -> dict | None:
    """Letzter Kurs und Ø Tagesumsatz der letzten `days` Handelstage."""
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["Close", "Volume"]).dropna(subset=["Close"])
    if len(df) < days:
        return None
    recent = df.tail(days)
    return {
        "last_date": recent.index[-1].date(),
        "close": float(recent["Close"].iloc[-1]),
        "avg_dollar_volume": float((recent["Close"] * recent["Volume"]).mean()),
    }


def apply_filters(cfg: dict, show_progress: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gibt (bestandene Aktien, alle Aktien mit Kennzahlen und Grund) zurück."""
    f = cfg["filters"]
    prices_dir = ROOT / cfg["paths"]["prices_dir"]
    universe = pd.read_csv(ROOT / cfg["paths"]["tickers_csv"], dtype=str, keep_default_na=False)
    cutoff = date.today() - timedelta(days=f["max_stale_days"])

    rows = []
    tickers = universe.to_dict("records")
    for row in tqdm(tickers, unit="Ticker", desc="Filter", disable=not show_progress):
        stats = liquidity_stats(price_path(prices_dir, row["ticker"]), f["avg_volume_days"])
        if stats is None:
            reason = "keine/zu wenig Kursdaten"
        elif stats["last_date"] < cutoff:
            reason = "Kursdaten veraltet"
        elif stats["close"] < f["min_price"]:
            reason = "Kurs zu niedrig"
        elif stats["avg_dollar_volume"] < f["min_avg_dollar_volume"]:
            reason = "Umsatz zu niedrig"
        else:
            reason = ""
        rows.append({**row, **(stats or {}), "reason": reason})

    result = pd.DataFrame(rows)
    passed = result[result["reason"] == ""].drop(columns="reason")
    passed = passed.sort_values("avg_dollar_volume", ascending=False)
    return passed, result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    passed, result = apply_filters(cfg)

    out_path = ROOT / cfg["paths"]["liquid_csv"]
    passed.to_csv(out_path, index=False, float_format="%.2f")

    f = cfg["filters"]
    print(
        f"\nLiquiditätsfilter (Kurs >= {f['min_price']}, "
        f"Ø Umsatz {f['avg_volume_days']} Tage >= {f['min_avg_dollar_volume']:,.0f}):"
    )
    print(f"  {len(passed)} von {len(result)} Aktien bestehen -> {out_path.relative_to(ROOT)}\n")
    print("Aussortiert:")
    for reason, n in result.loc[result["reason"] != "", "reason"].value_counts().items():
        print(f"  {reason:<26} {n:>5}")
    print("\nBestanden pro Börse:")
    for exchange, n in passed["exchange"].value_counts().items():
        print(f"  {exchange:<26} {n:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
