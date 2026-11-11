"""Gemeinsame Daten, Formatierung und Charts für alle Seiten."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml
import yfinance as yf
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import market_regime  # noqa: E402
import signals  # noqa: E402

RESULTS = ROOT / "results"
SCAN_PATH = RESULTS / "scan_latest.parquet"
REGIME_PATH = RESULTS / "market_regime.json"
HISTORY_PATH = RESULTS / "regime_history.csv"

# wird in app.py mit den Seiten befüllt (für st.switch_page)
PAGES: dict[str, st.Page] = {}

VERDICT_STYLE = {
    "Rückenwind": ("🟢", "green"),
    "neutral": ("🟡", "orange"),
    "Gegenwind": ("🔴", "red"),
}

DISCLAIMER = ("Regelbasierte Vorauswahl auf Basis von Kursdaten – keine Anlageberatung. "
              "Kurse von Yahoo Finance, teils verzögert.")


# --------------------------------------------------------------------------- #
# Daten
# --------------------------------------------------------------------------- #
def mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data(show_spinner=False)
def _load_config(_m: float) -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def config() -> dict:
    return _load_config(mtime(ROOT / "config.yaml"))


@st.cache_data(show_spinner=False)
def _load_scan(_m: float) -> pd.DataFrame:
    df = pd.read_parquet(SCAN_PATH)
    # ältere Ergebnisdateien haben noch keine Signale
    for col, default in [("signals", ""), ("signal_keys", ""), ("score", 0.0),
                         ("has_setup", False), ("has_anomaly", False), ("has_warning", False),
                         ("currency", None)]:
        if col not in df:
            df[col] = default
    if df["currency"].isna().all():
        df["currency"] = df["country"].map({"DE": "EUR"}).fillna("USD")
    df["avg_volume_m"] = df["avg_dollar_volume"] / 1e6
    return df


def scan() -> pd.DataFrame:
    if not SCAN_PATH.exists():
        return pd.DataFrame()
    return _load_scan(mtime(SCAN_PATH))


@st.cache_data(show_spinner=False)
def _load_regime(_m: float) -> dict:
    with open(REGIME_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def stored_regime() -> dict:
    return _load_regime(mtime(REGIME_PATH)) if REGIME_PATH.exists() else {}


@st.cache_data(show_spinner=False)
def _load_history(_m: float) -> pd.DataFrame:
    return pd.read_csv(HISTORY_PATH, parse_dates=["date"])


def history() -> pd.DataFrame:
    return _load_history(mtime(HISTORY_PATH)) if HISTORY_PATH.exists() else pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def live_regime() -> dict | None:
    """Marktlage mit aktuellen Indexständen (alle 10 Minuten neu)."""
    try:
        return market_regime.compute_regime(config())
    except Exception:
        return None


def has_signals(df: pd.DataFrame) -> bool:
    return bool(len(df)) and "rsi14" in df.columns


# --------------------------------------------------------------------------- #
# Live-Kurse und Recherche
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=900, show_spinner=False)
def price_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, auto_adjust=False, progress=False,
                     multi_level_index=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def company_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    keys = ["longName", "sector", "industry", "country", "website", "marketCap", "trailingPE",
            "forwardPE", "dividendYield", "targetMeanPrice", "recommendationKey",
            "numberOfAnalystOpinions", "longBusinessSummary", "currency", "beta",
            "fullTimeEmployees"]
    return {k: info.get(k) for k in keys}


@st.cache_data(ttl=86400, show_spinner=False)
def next_earnings(ticker: str):
    try:
        cal = yf.Ticker(ticker).calendar or {}
        dates = cal.get("Earnings Date") or []
        return dates[0] if dates else None
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def news(ticker: str, count: int = 6) -> list[dict]:
    try:
        items = yf.Ticker(ticker).get_news(count=count) or []
    except Exception:
        return []
    out = []
    for it in items:
        c = it.get("content", it)
        url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
        provider = (c.get("provider") or {}).get("displayName") or c.get("publisher", "")
        when = c.get("pubDate") or c.get("providerPublishTime")
        if isinstance(when, (int, float)):
            when = pd.Timestamp(when, unit="s").isoformat()
        if c.get("title") and url:
            out.append({"title": c["title"], "url": url, "provider": provider, "date": when})
    return out


# --------------------------------------------------------------------------- #
# Formatierung
# --------------------------------------------------------------------------- #
def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _de(s: str) -> str:
    """1,234.5 -> 1.234,5"""
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(x, digits: int = 2, suffix: str = "") -> str:
    return "–" if _missing(x) else _de(f"{x:,.{digits}f}") + suffix


def fmt_pct(x, digits: int = 1) -> str:
    return "–" if _missing(x) else _de(f"{x:+,.{digits}f}") + " %"


def fmt_big(x) -> str:
    if not x:
        return "–"
    for div, unit in [(1e12, "Bio."), (1e9, "Mrd."), (1e6, "Mio.")]:
        if abs(x) >= div:
            return f"{fmt_num(x / div, 1)} {unit}"
    return fmt_num(x, 0)


def signal_badges(keys: str) -> str:
    """Markdown-Badges für eine kommagetrennte Liste von Signal-Schlüsseln."""
    colors = {"setup": "green", "anomaly": "blue", "warning": "red"}
    parts = []
    for k in [k for k in str(keys).split(",") if k]:
        name, kind, _ = signals.SIGNALS.get(k, (k, "anomaly", 0))
        parts.append(f":{colors[kind]}-background[{name}]")
    return " ".join(parts)


def berlin(ts: str) -> str:
    try:
        return pd.Timestamp(ts).tz_convert("Europe/Berlin").strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)


def open_analysis(ticker: str) -> None:
    st.session_state["ticker"] = ticker
    st.switch_page(PAGES["analysis"])


# --------------------------------------------------------------------------- #
# Chart
# --------------------------------------------------------------------------- #
def price_chart(df: pd.DataFrame, months: int, stop: float | None = None,
                height: int = 560) -> go.Figure:
    df = df.copy()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    start = df.index[-1] - pd.DateOffset(months=months)
    high_52w = float(df["High"].tail(252).max())
    df = df[df.index >= start]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22],
                        vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"],
                                 close=df["Close"], name="Kurs"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], name="SMA50",
                             line=dict(width=1.5, color="#4c9be8")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], name="SMA200",
                             line=dict(width=1.5, color="#f0a43a")), row=1, col=1)
    fig.add_hline(y=high_52w, line=dict(color="rgba(150,150,150,0.6)", dash="dot", width=1),
                  annotation_text="52W-Hoch", annotation_position="top left", row=1, col=1)
    if stop and not math.isnan(stop):
        fig.add_hline(y=stop, line=dict(color="rgba(230,80,80,0.8)", dash="dash", width=1),
                      annotation_text="Stopp (2×ATR)", annotation_position="bottom left",
                      row=1, col=1)
    colors = ["rgba(38,166,91,0.5)" if c >= o else "rgba(230,80,80,0.5)"
              for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volumen", marker_color=colors,
                         showlegend=False), row=2, col=1)
    fig.update_layout(height=height, xaxis_rangeslider_visible=False, hovermode="x unified",
                      margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.02, x=0))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig
