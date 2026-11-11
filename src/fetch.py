"""Lädt Tageskurse (OHLCV) für alle Ticker aus data/universe/tickers.csv.

- Erster Lauf: die letzten `fetch.years` Jahre (Standard: 3).
- Weitere Läufe: nur ab dem letzten gespeicherten Tag nachladen. Der letzte
  Tag wird erneut geladen, weil er beim letzten Lauf noch unvollständig
  gewesen sein kann.
- Eine Parquet-Datei pro Ticker in data/prices/<TICKER>.parquet
- Fehlgeschlagene Ticker landen in data/failed.csv

Aufruf aus dem Projektordner:
    python3 src/fetch.py                  # alle Ticker
    python3 src/fetch.py --limit 200      # nur die ersten 200 (zum Testen)
    python3 src/fetch.py --tickers AAPL SAP.DE
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]

log = logging.getLogger("fetch")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def price_path(prices_dir: Path, ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("^", "_")
    return prices_dir / f"{safe}.parquet"


def last_stored_date(path: Path) -> date | None:
    if not path.exists():
        return None
    try:
        idx = pd.read_parquet(path, columns=["Close"]).index
    except Exception as exc:  # beschädigte Datei -> komplett neu laden
        log.warning("%s nicht lesbar (%s), wird neu geladen", path.name, exc)
        return None
    return idx.max().date() if len(idx) else None


def plan_downloads(tickers: list[str], prices_dir: Path, years: int) -> dict[date, list[str]]:
    """Gruppiert Ticker nach Startdatum, damit ein Batch ein gemeinsames Startdatum hat."""
    full_start = date.today() - timedelta(days=365 * years + years // 4)
    groups: dict[date, list[str]] = {}
    for t in tickers:
        last = last_stored_date(price_path(prices_dir, t))
        groups.setdefault(last or full_start, []).append(t)
    return groups


def download_batch(tickers: list[str], start: date, cfg: dict) -> pd.DataFrame | None:
    """Ein yfinance-Aufruf mit Wiederholungen. None, wenn alle Versuche scheitern."""
    end = date.today() + timedelta(days=1)
    for attempt in range(1, cfg["max_retries"] + 1):
        try:
            df = yf.download(
                tickers,
                start=start.isoformat(),
                end=end.isoformat(),
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=True,
                progress=False,
                multi_level_index=True,
            )
            if df is not None and not df.empty:
                return df
            reason = "leere Antwort"
        except Exception as exc:
            reason = str(exc)
        if attempt < cfg["max_retries"]:
            wait = cfg["retry_backoff"] * attempt
            log.debug("Batch ab %s, Versuch %d fehlgeschlagen (%s), warte %ss", start, attempt, reason, wait)
            time.sleep(wait)
    return None


def extract(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Holt die Kurse eines Tickers aus dem Ergebnis von yf.download."""
    if ticker not in df.columns.get_level_values(0):
        return pd.DataFrame(columns=PRICE_COLUMNS)
    part = df[ticker].dropna(how="all")
    part = part[[c for c in PRICE_COLUMNS if c in part.columns]]
    part.index = pd.to_datetime(part.index).tz_localize(None).normalize()
    part.index.name = "Date"
    part.columns.name = None
    return part


def save(path: Path, new: pd.DataFrame) -> int:
    """Hängt neue Zeilen an die vorhandene Datei an. Gibt die Zahl neuer Tage zurück."""
    if path.exists():
        old = pd.read_parquet(path)
        known = set(old.index)
        merged = pd.concat([old, new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        added = sum(1 for d in new.index if d not in known)
    else:
        merged, added = new.sort_index(), len(new)
    merged["Volume"] = merged["Volume"].fillna(0).astype("int64")
    merged.to_parquet(path)
    return added


def run(tickers: list[str], cfg: dict) -> pd.DataFrame:
    fetch_cfg = cfg["fetch"]
    prices_dir = ROOT / cfg["paths"]["prices_dir"]
    prices_dir.mkdir(parents=True, exist_ok=True)

    groups = plan_downloads(tickers, prices_dir, fetch_cfg["years"])
    batches = [
        (start, group[i : i + fetch_cfg["batch_size"]])
        for start, group in sorted(groups.items())
        for i in range(0, len(group), fetch_cfg["batch_size"])
    ]

    failed: list[dict] = []
    new_days = updated = 0
    now = datetime.now().isoformat(timespec="seconds")

    with tqdm(total=len(tickers), unit="Ticker", desc="Kurse") as bar:
        for n, (start, batch) in enumerate(batches):
            existing = {t for t in batch if price_path(prices_dir, t).exists()}
            df = download_batch(batch, start, fetch_cfg)
            for t in batch:
                part = extract(df, t) if df is not None else pd.DataFrame()
                if part.empty:
                    # Beim Nachladen ist "nichts Neues" (z. B. Wochenende) kein Fehler.
                    if t not in existing:
                        reason = "Download fehlgeschlagen" if df is None else "keine Daten"
                        failed.append({"ticker": t, "reason": reason, "time": now})
                    continue
                try:
                    new_days += save(price_path(prices_dir, t), part)
                    updated += 1
                except Exception as exc:
                    failed.append({"ticker": t, "reason": f"Speichern: {exc}", "time": now})
            bar.update(len(batch))
            bar.set_postfix(fehler=len(failed))
            if n < len(batches) - 1:
                time.sleep(fetch_cfg["pause_seconds"])

    log.info("%d Ticker aktualisiert, %d neue Kurstage, %d fehlgeschlagen", updated, new_days, len(failed))
    return pd.DataFrame(failed, columns=["ticker", "reason", "time"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Tageskurse per yfinance laden")
    parser.add_argument("--limit", type=int, help="nur die ersten N Ticker laden")
    parser.add_argument("--tickers", nargs="+", help="nur diese Ticker laden")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # yfinance meldet jeden fehlenden Ticker einzeln -> wir sammeln sie in failed.csv
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    cfg = load_config()
    if args.tickers:
        tickers = args.tickers
    else:
        universe = pd.read_csv(ROOT / cfg["paths"]["tickers_csv"], dtype=str, keep_default_na=False)
        tickers = universe["ticker"].tolist()
    if args.limit:
        tickers = tickers[: args.limit]

    failed = run(tickers, cfg)
    failed_path = ROOT / cfg["paths"]["failed_csv"]
    failed.to_csv(failed_path, index=False)
    if len(failed):
        print(f"{len(failed)} fehlgeschlagene Ticker in {failed_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
