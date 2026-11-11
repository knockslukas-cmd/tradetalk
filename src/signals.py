"""Technische Kennzahlen und Signale für tradetalk.

Für jede liquide Aktie werden aus den Tageskursen Kennzahlen berechnet
(Trend, Momentum, Volumen, Volatilität) und daraus regelbasierte Signale
abgeleitet:

Setups (mögliche Trades)
  breakout_52w   Ausbruch auf ein neues 52-Wochen-Hoch mit erhöhtem Volumen
  pullback_sma50 Rücksetzer an die 50-Tage-Linie im intakten Aufwärtstrend
  golden_cross   SMA50 hat die SMA200 in den letzten Tagen nach oben gekreuzt
  oversold_trend RSI überverkauft, aber über der 200-Tage-Linie
  reclaim_sma200 Kurs hat die 200-Tage-Linie zurückerobert

Auffälligkeiten
  volume_spike   Volumen weit über dem Durchschnitt mit deutlicher Bewegung
  gap_up/gap_down Kurslücke zum Vortag

Warnsignale
  break_sma200   Kurs ist unter die 200-Tage-Linie gefallen
  death_cross    SMA50 hat die SMA200 nach unten gekreuzt

Die Regeln sind ein Werkzeug zur Vorauswahl, keine Anlageberatung.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Name, Art und Grundgewicht je Signal
SIGNALS = {
    "breakout_52w": ("Neues Jahreshoch", "setup", 3.0),
    "pullback_sma50": ("Rücksetzer im Aufwärtstrend", "setup", 2.5),
    "golden_cross": ("Trend dreht nach oben", "setup", 2.0),
    "reclaim_sma200": ("Zurück im langfristigen Aufwärtstrend", "setup", 1.5),
    "oversold_trend": ("Stark gefallen, Trend intakt", "setup", 1.5),
    "volume_spike": ("Ungewöhnlich viel Handel", "anomaly", 1.0),
    "gap_up": ("Kurssprung nach oben", "anomaly", 0.5),
    "gap_down": ("Kurssprung nach unten", "anomaly", 0.0),
    "break_sma200": ("Langfristiger Trend gebrochen", "warning", 0.0),
    "death_cross": ("Trend dreht nach unten", "warning", 0.0),
}

SETUP_KEYS = [k for k, (_, kind, _) in SIGNALS.items() if kind == "setup"]
ANOMALY_KEYS = [k for k, (_, kind, _) in SIGNALS.items() if kind == "anomaly"]
WARNING_KEYS = [k for k, (_, kind, _) in SIGNALS.items() if kind == "warning"]


def label(key: str) -> str:
    return SIGNALS[key][0]


def _pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b and not math.isnan(b) else float("nan")


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df["Close"].shift()
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _crossed(fast: pd.Series, slow: pd.Series, days: int, up: bool) -> bool:
    """Hat `fast` die Linie `slow` in den letzten `days` Tagen gekreuzt?"""
    diff = (fast - slow).dropna().tail(days + 1)
    if len(diff) < 2:
        return False
    was, now = diff.iloc[0], diff.iloc[-1]
    return (was <= 0 < now) if up else (was >= 0 > now)


def analyze(df: pd.DataFrame) -> dict:
    """Kennzahlen und Signale für einen Kursverlauf (OHLCV, aufsteigend sortiert)."""
    df = df.dropna(subset=["Close"])
    c, v = df["Close"], df["Volume"].astype(float)
    last = float(c.iloc[-1])

    def back(n: int) -> float:
        return float(c.iloc[-n - 1]) if len(c) > n else float("nan")

    sma50_s = c.rolling(50).mean()
    sma200_s = c.rolling(200).mean()
    sma50 = float(sma50_s.iloc[-1]) if len(c) >= 50 else float("nan")
    sma200 = float(sma200_s.iloc[-1]) if len(c) >= 200 else float("nan")
    high_52w = float(df["High"].tail(252).max())
    low_52w = float(df["Low"].tail(252).min())
    prev_high_52w = float(df["High"].iloc[:-1].tail(251).max()) if len(df) > 1 else high_52w
    rsi14 = float(rsi(c).iloc[-1]) if len(c) > 15 else float("nan")
    atr14 = float(atr(df).iloc[-1]) if len(c) > 15 else float("nan")
    avg_vol20 = float(v.iloc[-21:-1].mean()) if len(v) > 21 else float("nan")
    vol_ratio = float(v.iloc[-1] / avg_vol20) if avg_vol20 else float("nan")
    chg_1d = _pct(last, back(1))
    gap = _pct(float(df["Open"].iloc[-1]), back(1)) if "Open" in df else float("nan")
    low_10 = float(df["Low"].tail(10).min())

    m = {
        "chg_1d": chg_1d,
        "perf_1w": _pct(last, back(5)),
        "perf_1m": _pct(last, back(21)),
        "perf_3m": _pct(last, back(63)),
        "perf_6m": _pct(last, back(126)),
        "perf_1y": _pct(last, back(252)),
        "sma50": sma50,
        "sma200": sma200,
        "dist_sma50": _pct(last, sma50),
        "dist_sma200": _pct(last, sma200),
        "high_52w": high_52w,
        "low_52w": low_52w,
        "dist_52w_high": _pct(last, high_52w),
        "rsi14": rsi14,
        "atr_pct": atr14 / last * 100 if last else float("nan"),
        "vol_ratio": vol_ratio,
        "gap_pct": gap,
    }

    uptrend = last > sma200 and sma50 > sma200
    hits: list[str] = []
    if last >= prev_high_52w and vol_ratio >= 1.3:
        hits.append("breakout_52w")
    if uptrend and -2 <= m["dist_sma50"] <= 3 and float(df["Low"].tail(3).min()) <= sma50 * 1.01 and rsi14 < 60:
        hits.append("pullback_sma50")
    if _crossed(sma50_s, sma200_s, 5, up=True):
        hits.append("golden_cross")
    if _crossed(c, sma200_s, 3, up=True) and vol_ratio >= 1.2:
        hits.append("reclaim_sma200")
    if last > sma200 and rsi14 < 32:
        hits.append("oversold_trend")
    if vol_ratio >= 2.5 and abs(chg_1d) >= 3:
        hits.append("volume_spike")
    if gap >= 4:
        hits.append("gap_up")
    if gap <= -4:
        hits.append("gap_down")
    if _crossed(c, sma200_s, 3, up=False):
        hits.append("break_sma200")
    if _crossed(sma50_s, sma200_s, 5, up=False):
        hits.append("death_cross")

    # Möglicher Plan: Ausstiegsmarke 2 x typische Tagesschwankung unter dem Kurs,
    # Ziel am Jahreshoch (falls weit genug entfernt), sonst das Doppelte des Risikos.
    m["low_10d"] = low_10
    if not math.isnan(atr14):
        stop = last - 2 * atr14
        risk = last - stop
        target = high_52w if high_52w - last >= 2 * risk else last + 2 * risk
        m["stop"] = stop
        m["risk_pct"] = risk / last * 100
        m["target"] = target
        m["target_pct"] = (target / last - 1) * 100
        m["reward_risk"] = (target - last) / risk if risk > 0 else float("nan")
    else:
        m["stop"] = m["risk_pct"] = m["target"] = m["target_pct"] = float("nan")
        m["reward_risk"] = float("nan")

    m["signal_keys"] = ",".join(hits)
    m["signals"] = ", ".join(label(k) for k in hits)
    m["has_setup"] = any(k in SETUP_KEYS for k in hits)
    m["has_anomaly"] = any(k in ANOMALY_KEYS for k in hits)
    m["has_warning"] = any(k in WARNING_KEYS for k in hits)
    m["uptrend"] = bool(uptrend)
    m["new_52w_high"] = bool(last >= prev_high_52w)
    m["new_52w_low"] = bool(last <= float(df["Low"].iloc[:-1].tail(251).min())) if len(df) > 1 else False
    return m


def add_scores(scan: pd.DataFrame) -> pd.DataFrame:
    """Relative Stärke und Setup-Score (höher = interessanter)."""
    scan = scan.copy()
    # Relative Stärke: Rang der gewichteten Performance (0–100)
    perf = (0.4 * scan["perf_3m"].fillna(0) + 0.3 * scan["perf_6m"].fillna(0)
            + 0.3 * scan["perf_1m"].fillna(0))
    scan["rs_rank"] = perf.rank(pct=True) * 100

    def num(x, default=float("nan")) -> float:
        try:
            x = float(x)
        except (TypeError, ValueError):
            return default
        return default if math.isnan(x) else x

    def score(row) -> float:
        keys = [k for k in str(row["signal_keys"]).split(",") if k]
        base = sum(SIGNALS[k][2] for k in keys)
        if base == 0 or not row["has_setup"]:
            return 0.0
        vol_bonus = min(num(row["vol_ratio"], 0), 4)
        penalty = 0.0
        if row["has_warning"]:
            penalty += 2
        rsi_v, atr_v, rr = num(row["rsi14"], 50), num(row["atr_pct"], 3), num(row["reward_risk"], 2)
        if rsi_v >= 80:
            penalty += 3.0          # stark überhitzt: Einstieg jetzt ungünstig
        elif rsi_v >= 75:
            penalty += 1.5
        if atr_v >= 8:
            penalty += 1.5          # sehr wilde Schwankungen
        if atr_v < 1:
            penalty += 3.0          # kaum Bewegung (oft laufende Übernahme)
        if row["rs_rank"] < 50:
            penalty += 1.0          # läuft schlechter als die Hälfte aller Aktien
        if rr < 1.5:
            penalty += 1.0          # Chance im Verhältnis zum Risiko zu klein
        return round(base + row["rs_rank"] / 25 + vol_bonus / 2 - penalty, 2)

    scan["score"] = scan.apply(score, axis=1)
    # 1–5 Sterne für die Anzeige (nur für Ideen mit Score > 0)
    stars = pd.cut(scan["score"], bins=[-1e9, 0, 4, 5.5, 7, 8.5, 1e9], labels=[0, 1, 2, 3, 4, 5])
    scan["stars"] = stars.astype(int)
    return scan
