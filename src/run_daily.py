"""Täglicher Lauf von tradetalk.

Führt nacheinander aus:
  1. universe       – Tickerliste aktualisieren (data/universe/tickers.csv)
  2. fetch          – fehlende Kurstage nachladen (data/prices/)
  3. filters        – Liquiditätsfilter
  4. market_regime  – Marktumfeld

und speichert die Ergebnisse für die App:
  results/scan_latest.parquet   liquide Aktien mit Kennzahlen und Signalen
  results/market_regime.json    Marktumfeld inkl. Marktbreite
  results/regime_history.csv    Verlauf der Marktlage (ein Eintrag pro Tag)

Aufruf aus dem Projektordner:  python3 src/run_daily.py
"""

from __future__ import annotations

import argparse
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
import signals  # noqa: E402
import tracking  # noqa: E402
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


def build_scan(cfg: dict, passed: pd.DataFrame) -> pd.DataFrame:
    """Kennzahlen und Signale für alle liquiden Aktien."""
    prices_dir = ROOT / cfg["paths"]["prices_dir"]
    metrics = []
    for t in passed["ticker"]:
        try:
            df = pd.read_parquet(filters.price_path(prices_dir, t))
            metrics.append(signals.analyze(df))
        except Exception as exc:  # einzelne kaputte Datei soll den Lauf nicht stoppen
            log.warning("%s: Kennzahlen fehlgeschlagen (%s)", t, exc)
            metrics.append({})
    scan = pd.concat([passed.reset_index(drop=True), pd.DataFrame(metrics)], axis=1)
    scan["last_date"] = pd.to_datetime(scan["last_date"])
    scan["currency"] = scan["country"].map({"DE": "EUR"}).fillna("USD")
    for col in ["has_setup", "has_anomaly", "has_warning", "uptrend", "new_52w_high", "new_52w_low"]:
        scan[col] = scan[col].fillna(False).astype(bool)
    scan["signal_keys"] = scan["signal_keys"].fillna("")
    scan["signals"] = scan["signals"].fillna("")
    return signals.add_scores(scan)


def market_breadth(scan: pd.DataFrame) -> dict:
    """Wie breit läuft der Markt mit? Anteile über den Durchschnittslinien usw."""
    n = len(scan)
    if not n:
        return {}
    return {
        "above_sma50_pct": float((scan["dist_sma50"] > 0).mean() * 100),
        "above_sma200_pct": float((scan["dist_sma200"] > 0).mean() * 100),
        "new_highs": int(scan["new_52w_high"].sum()),
        "new_lows": int(scan["new_52w_low"].sum()),
        "advancers": int((scan["chg_1d"] > 0).sum()),
        "decliners": int((scan["chg_1d"] < 0).sum()),
        "setups": int(scan["has_setup"].sum()),
        "warnings": int(scan["has_warning"].sum()),
    }


def append_history(path: Path, regime: dict) -> None:
    """Hält einen Eintrag pro Tag fest (der letzte Lauf eines Tages gewinnt)."""
    b = regime.get("breadth", {})
    row = {
        "date": regime["generated_at"][:10],
        "points": regime["points"],
        "verdict": regime["verdict"],
        "vix": (regime.get("vix") or {}).get("value"),
        "above_sma200_pct": b.get("above_sma200_pct"),
        "new_highs": b.get("new_highs"),
        "new_lows": b.get("new_lows"),
    }
    for idx in regime["indices"]:
        if idx.get("available"):
            row[idx["symbol"].lstrip("^")] = idx["close"]
    hist = pd.read_csv(path) if path.exists() else pd.DataFrame()
    hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    hist = hist.drop_duplicates("date", keep="last").sort_values("date").tail(400)
    hist.to_csv(path, index=False, float_format="%.2f")


def main() -> int:
    parser = argparse.ArgumentParser(description="Täglicher Lauf von tradetalk")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Universum und Kurse nicht neu laden (nur auswerten)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    cfg = universe.load_config()
    results_dir = ROOT / cfg["paths"]["results_dir"]
    results_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    if args.skip_fetch:
        log.info("Universum und Kurse übersprungen (--skip-fetch)")
        failed = pd.DataFrame(columns=["ticker"])
    else:
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

    # Erfolgskontrolle: heutige Ideen festhalten und alle bisherigen auswerten
    try:
        day = scan["last_date"].max().strftime("%Y-%m-%d")
        ideas_log = tracking.log_ideas(results_dir / "ideas_log.csv",
                                       tracking.ideas_from_scan(scan, day))
        prices_dir = ROOT / cfg["paths"]["prices_dir"]
        ev = tracking.evaluate(ideas_log, lambda tk: filters.price_path(prices_dir, tk))
        if len(ev):
            ev.drop(columns=["signals"], errors="ignore").to_parquet(
                results_dir / "ideas_eval.parquet", index=False)
        log.info("Erfolgskontrolle: %d Ideen im Protokoll", len(ideas_log))
    except Exception as exc:
        log.error("Erfolgskontrolle fehlgeschlagen: %s", exc)

    t = step("4/4 Marktumfeld")
    regime = market_regime.compute_regime(cfg)
    regime.update(
        liquid_count=int(len(passed)),
        universe_count=int(len(result)),
        failed_count=int(len(failed)),
        filters=cfg["filters"],
        breadth=market_breadth(scan),
    )
    with open(results_dir / "market_regime.json", "w", encoding="utf-8") as fh:
        json.dump(regime, fh, ensure_ascii=False, indent=2)
    append_history(results_dir / "regime_history.csv", regime)
    market_regime.print_regime(regime)
    log.info("%d Setups, %d Auffälligkeiten, %d Warnsignale",
             int(scan["has_setup"].sum()), int(scan["has_anomaly"].sum()), int(scan["has_warning"].sum()))

    log.info("Gesamtlaufzeit %.0fs – Ergebnisse in %s/", time.time() - start,
             results_dir.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
