"""Erfolgskontrolle: Was ist aus den Trade-Ideen geworden?

- log_ideas():  hält die Ideen eines Tages fest (results/ideas_log.csv)
- evaluate():   prüft für jede Idee anhand der späteren Kurse, ob zuerst das
                Ziel oder die Ausstiegsmarke erreicht wurde (max. 60 Handelstage)
- summarize():  Trefferquoten und Ø Ergebnis je Art und Sterne

Regeln der Auswertung
- Einstieg zum Schlusskurs am Tag der Idee.
- Ab dem nächsten Handelstag: Tief <= Ausstieg -> "Ausstieg erreicht",
  Hoch >= Ziel -> "Ziel erreicht". Passiert beides am selben Tag, zählt
  vorsichtshalber der Ausstieg.
- Nach 60 Handelstagen ohne Treffer: Ergebnis = Kursänderung bis dahin.
- Gebühren und Kurslücken über Nacht sind nicht berücksichtigt.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

MAX_DAYS = 60
LOG_COLUMNS = ["date", "ticker", "name", "kind", "signals", "stars", "score", "entry", "stop",
               "target", "currency", "country", "source"]


def main_setup(keys: str) -> str:
    order = ["breakout_52w", "pullback_sma50", "golden_cross", "reclaim_sma200", "oversold_trend"]
    ks = [k for k in str(keys).split(",") if k]
    return next((k for k in order if k in ks), "")


def ideas_from_scan(scan: pd.DataFrame, day: str, source: str = "live") -> pd.DataFrame:
    ideas = scan[scan["has_setup"] & (scan["score"] > 0)].copy()
    if ideas.empty:
        return pd.DataFrame(columns=LOG_COLUMNS)
    ideas["date"] = day
    ideas["kind"] = ideas["signal_keys"].map(main_setup)
    ideas["entry"] = ideas["close"]
    ideas["source"] = source
    for col in LOG_COLUMNS:
        if col not in ideas:
            ideas[col] = None
    return ideas[LOG_COLUMNS]


def log_ideas(path: Path, new: pd.DataFrame) -> pd.DataFrame:
    old = pd.read_csv(path, dtype={"date": str}) if path.exists() else pd.DataFrame(columns=LOG_COLUMNS)
    log = pd.concat([old, new], ignore_index=True)
    log = log.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "score"],
                                                                         ascending=[True, False])
    log.to_csv(path, index=False, float_format="%.4f")
    return log


def evaluate_one(idea: pd.Series, prices: pd.DataFrame) -> dict:
    entry, stop, target = float(idea["entry"]), float(idea["stop"]), float(idea["target"])
    after = prices[prices.index > pd.Timestamp(idea["date"])].head(MAX_DAYS)
    out = {"outcome": "offen", "days": len(after), "result_pct": float("nan"),
           "ret_5": float("nan"), "ret_20": float("nan"), "ret_60": float("nan"),
           "max_up_pct": float("nan"), "max_down_pct": float("nan")}
    if after.empty or math.isnan(stop) or math.isnan(target):
        return out
    closes = after["Close"].tolist()
    for n in (5, 20, 60):
        if len(closes) >= n:
            out[f"ret_{n}"] = (closes[n - 1] / entry - 1) * 100
    out["max_up_pct"] = (float(after["High"].max()) / entry - 1) * 100
    out["max_down_pct"] = (float(after["Low"].min()) / entry - 1) * 100
    for i, (_, bar) in enumerate(after.iterrows(), start=1):
        if bar["Low"] <= stop:
            out.update(outcome="Ausstieg erreicht", days=i, result_pct=(stop / entry - 1) * 100)
            return out
        if bar["High"] >= target:
            out.update(outcome="Ziel erreicht", days=i, result_pct=(target / entry - 1) * 100)
            return out
    if len(after) >= MAX_DAYS:
        out.update(outcome="nach 60 Tagen beendet", result_pct=(closes[-1] / entry - 1) * 100)
    else:
        out["result_pct"] = (closes[-1] / entry - 1) * 100   # noch offen: aktueller Stand
    return out


def evaluate(log: pd.DataFrame, price_path) -> pd.DataFrame:
    """price_path: Funktion ticker -> Pfad zur Parquet-Datei."""
    rows = []
    for ticker, group in log.groupby("ticker"):
        path = price_path(ticker)
        if not Path(path).exists():
            continue
        prices = pd.read_parquet(path, columns=["High", "Low", "Close"]).dropna()
        for _, idea in group.iterrows():
            rows.append({**idea.to_dict(), **evaluate_one(idea, prices)})
    return pd.DataFrame(rows)


def summarize(ev: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Kennzahlen für abgeschlossene Ideen (Ziel, Ausstieg oder 60 Tage)."""
    done = ev[ev["outcome"] != "offen"]
    if done.empty:
        return pd.DataFrame()

    def stats(g: pd.DataFrame) -> pd.Series:
        wins = (g["result_pct"] > 0).mean() * 100
        return pd.Series({
            "anzahl": len(g),
            "trefferquote": wins,
            "ziel_quote": (g["outcome"] == "Ziel erreicht").mean() * 100,
            "ausstieg_quote": (g["outcome"] == "Ausstieg erreicht").mean() * 100,
            "avg_result": g["result_pct"].mean(),
            "avg_win": g.loc[g["result_pct"] > 0, "result_pct"].mean(),
            "avg_loss": g.loc[g["result_pct"] <= 0, "result_pct"].mean(),
            "avg_days": g["days"].mean(),
        })

    if by:
        return done.groupby(by).apply(stats).reset_index()
    return stats(done).to_frame().T
