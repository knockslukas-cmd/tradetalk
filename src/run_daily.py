"""Täglicher Lauf von tradetalk.

Führt nacheinander aus:
  1. universe       – Tickerliste aktualisieren (data/universe/tickers.csv)
  2. fetch          – fehlende Kurstage nachladen (data/prices/)
  3. filters        – Liquiditätsfilter
  4. market_regime  – Marktumfeld

und speichert die Ergebnisse für die App:
  results/scan_latest.parquet   liquide Aktien mit Kennzahlen
  results/market_regime.json    Marktumfeld

Aufruf aus dem Projektordner:  python3 src/run_daily.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch  # noqa: E402
import filters  # noqa: E402
import market_regime  # noqa: E402
import universe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("run_daily")


def step(title: str):
    log.info("=== %s ===", title)
    return time.time()


def update_universe(cfg: dict) -> list[str]:
    path = ROOT / cfg["paths"]["tickers_csv"]
    try:
        df = universe.build_universe(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8")
        log.info("%d Ticker im Universum", len(df))
    except Exception as exc:
        # Wenn eine Quelle ausfällt, mit der letzten Liste weitermachen
        if not path.exists():
            raise
        log.error("Universum konnte nicht aktualisiert werden (%s), nutze vorhandene Liste", exc)
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df["ticker"].tolist()


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else float("nan")


def stock_metrics(path: Path) -> dict:
    """Kennzahlen für die Tabelle in der App."""
    df = pd.read_parquet(path, columns=["Close", "High"]).dropna(subset=["Close"])
    c = df["Close"]
    last = float(c.iloc[-1])

    def back(n: int) -> float:
        return float(c.iloc[-n - 1]) if len(c) > n else float("nan")

    sma50 = float(c.tail(50).mean()) if len(c) >= 50 else float("nan")
    sma200 = float(c.tail(200).mean()) if len(c) >= 200 else float("nan")
    high_52w = float(df["High"].tail(252).max())
    return {
        "chg_1d": pct(last, back(1)),
        "perf_1m": pct(last, back(21)),
        "perf_3m": pct(last, back(63)),
        "perf_1y": pct(last, back(252)),
        "dist_sma50": pct(last, sma50),
        "dist_sma200": pct(last, sma200),
        "dist_52w_high": pct(last, high_52w),
    }


def build_scan(cfg: dict, passed: pd.DataFrame) -> pd.DataFrame:
    prices_dir = ROOT / cfg["paths"]["prices_dir"]
    metrics = [stock_metrics(filters.price_path(prices_dir, t)) for t in passed["ticker"]]
    scan = pd.concat([passed.reset_index(drop=True), pd.DataFrame(metrics)], axis=1)
    scan["last_date"] = pd.to_datetime(scan["last_date"])
    return scan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    cfg = universe.load_config()
    results_dir = ROOT / cfg["paths"]["results_dir"]
    results_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    t = step("1/4 Universum")
    tickers = update_universe(cfg)
    log.info("fertig in %.0fs", time.time() - t)

    t = step("2/4 Kurse")
    failed = fetch.run(tickers, cfg)
    failed.to_csv(ROOT / cfg["paths"]["failed_csv"], index=False)
    log.info("fertig in %.0fs", time.time() - t)

    t = step("3/4 Liquiditätsfilter")
    passed, result = filters.apply_filters(cfg, show_progress=False)
    passed.to_csv(ROOT / cfg["paths"]["liquid_csv"], index=False, float_format="%.2f")
    scan = build_scan(cfg, passed)
    scan.to_parquet(results_dir / "scan_latest.parquet", index=False)
    log.info("%d von %d Aktien bestehen, fertig in %.0fs", len(passed), len(result), time.time() - t)

    t = step("4/4 Marktumfeld")
    regime = market_regime.compute_regime(cfg)
    regime.update(
        liquid_count=int(len(passed)),
        universe_count=int(len(result)),
        failed_count=int(len(failed)),
        filters=cfg["filters"],
    )
    with open(results_dir / "market_regime.json", "w", encoding="utf-8") as fh:
        json.dump(regime, fh, ensure_ascii=False, indent=2)
    market_regime.print_regime(regime)

    log.info("Gesamtlaufzeit %.0fs – Ergebnisse in %s/", time.time() - start,
             results_dir.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
