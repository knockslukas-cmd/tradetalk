"""Rückblick: Wie hätten die Trade-Ideen in der Vergangenheit funktioniert?

Spielt für jede Woche der Vergangenheit durch, welche Ideen die App damals
gefunden hätte (gleiche Regeln wie heute), und schreibt sie mit der Quelle
"Rückblick" in results/ideas_log.csv. Die Auswertung übernimmt danach
run_daily.py bzw. tracking.evaluate().

Einschränkungen (ehrlich benannt):
- Es werden die heute liquiden Aktien verwendet. Firmen, die inzwischen
  pleite oder übernommen sind, fehlen -> Ergebnisse eher etwas zu gut.
- Kein Marktumfeld-Filter, keine Gebühren.

Aufruf aus dem Projektordner:  python3 src/backtest.py [--weeks 100]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters  # noqa: E402
import signals  # noqa: E402
import tracking  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("backtest")


def snapshot_rows(args) -> list[dict]:
    """Kennzahlen einer Aktie an allen Stichtagen (läuft in eigenem Prozess)."""
    path, ticker, name, currency, country, dates, min_price, min_dv = args
    try:
        df = pd.read_parquet(path).dropna(subset=["Close"])
    except Exception:
        return []
    rows = []
    for d in dates:
        hist = df[df.index <= d]
        if len(hist) < 220 or hist.index[-1] != d:
            continue
        recent = hist.tail(20)
        if recent["Close"].iloc[-1] < min_price or (recent["Close"] * recent["Volume"]).mean() < min_dv:
            continue
        m = signals.analyze(hist)
        rows.append({"date": d.strftime("%Y-%m-%d"), "ticker": ticker, "name": name,
                     "currency": currency, "country": country, "close": float(hist["Close"].iloc[-1]),
                     **m})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Rückblick auf vergangene Trade-Ideen")
    parser.add_argument("--weeks", type=int, default=100, help="wie viele Wochen zurück")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")

    cfg = filters.load_config()
    prices_dir = ROOT / cfg["paths"]["prices_dir"]
    liquid = pd.read_csv(ROOT / cfg["paths"]["liquid_csv"], dtype=str, keep_default_na=False)
    liquid["currency"] = liquid["country"].map({"DE": "EUR"}).fillna("USD")

    # Stichtage: jeder 5. Handelstag, bis 5 Tage vor heute (damit etwas Zukunft da ist)
    ref = pd.read_parquet(filters.price_path(prices_dir, "AAPL"), columns=["Close"]).index
    dates = list(ref[::-1][5::5][: args.weeks])[::-1]
    log.info("%d Stichtage von %s bis %s, %d Aktien", len(dates), dates[0].date(),
             dates[-1].date(), len(liquid))

    f = cfg["filters"]
    jobs = [(filters.price_path(prices_dir, r.ticker), r.ticker, r.name, r.currency, r.country,
             dates, f["min_price"], f["min_avg_dollar_volume"]) for r in liquid.itertuples()]
    rows: list[dict] = []
    start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(snapshot_rows, j) for j in jobs]
        for i, fut in enumerate(as_completed(futures), start=1):
            rows.extend(fut.result())
            if i % 250 == 0:
                log.info("%d/%d Aktien (%.0fs)", i, len(jobs), time.time() - start)

    all_rows = pd.DataFrame(rows)
    ideas = []
    for day, group in all_rows.groupby("date"):
        scored = signals.add_scores(group.reset_index(drop=True))
        ideas.append(tracking.ideas_from_scan(scored, day, source="Rückblick"))
    ideas = pd.concat(ideas, ignore_index=True)

    # Eigene Datei, damit die tägliche Datei klein bleibt (sonst wächst das Repo stark)
    results = ROOT / cfg["paths"]["results_dir"]
    ev = tracking.evaluate(ideas, lambda t: filters.price_path(prices_dir, t))
    keep = [c for c in ev.columns if c not in ("signals",)]
    ev[keep].to_parquet(results / "ideas_backtest.parquet", index=False)
    done = ev[ev["outcome"] != "offen"]
    log.info("%d Rückblick-Ideen ausgewertet (%d abgeschlossen) in %.0fs", len(ev), len(done),
             time.time() - start)
    if len(done):
        s = tracking.summarize(ev).iloc[0]
        log.info("Trefferquote %.0f %%, Ø Ergebnis %+.2f %% je Idee", s["trefferquote"], s["avg_result"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
