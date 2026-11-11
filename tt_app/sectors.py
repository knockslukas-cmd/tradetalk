"""Branchen-Übersicht über US-Branchen-ETFs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tt_app import common as c
from tt_app import style as s

# yfinance-Sektor -> Branchen-ETF
YF_SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Energy": "XLE",
    "Industrials": "XLI", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Basic Materials": "XLB", "Utilities": "XLU", "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


def _pct(series: list[float], n: int) -> float:
    return (series[-1] / series[-n - 1] - 1) * 100 if len(series) > n else float("nan")


@st.cache_data(ttl=1800, show_spinner=False)
def sector_table() -> pd.DataFrame:
    sectors: dict = c.config().get("sectors", {})
    data = c.closes(tuple(sectors) + ("SPY",), "1y")
    spy = data.get("SPY", [])
    rows = []
    for etf, name in sectors.items():
        sr = data.get(etf)
        if not sr or len(sr) < 60:
            continue
        sma50 = sum(sr[-50:]) / 50
        sma200 = sum(sr[-200:]) / min(200, len(sr))
        rows.append({
            "etf": etf, "name": name, "w1": _pct(sr, 5), "m1": _pct(sr, 21), "m3": _pct(sr, 63),
            "vs_market": _pct(sr, 63) - _pct(spy, 63) if spy else float("nan"),
            "up_short": sr[-1] > sma50, "up_long": sr[-1] > sma200, "series": sr[-90:],
        })
    df = pd.DataFrame(rows)
    return df.sort_values("m3", ascending=False) if len(df) else df


def sector_verdict(row) -> tuple[str, str]:
    if row["up_short"] and row["up_long"] and row["vs_market"] > 0:
        return "läuft stark", "up"
    if not row["up_long"] and not row["up_short"]:
        return "läuft schwach", "down"
    return "gemischt", "warn"


def sector_for(yf_sector: str | None) -> dict | None:
    etf = YF_SECTOR_ETF.get(yf_sector or "")
    if not etf:
        return None
    df = sector_table()
    row = df[df["etf"] == etf]
    return row.iloc[0].to_dict() if len(row) else None


def render_section() -> None:
    df = sector_table()
    if df.empty:
        return
    s.section("🏭 Welche Branchen laufen gerade?", "letzte 3 Monate")
    tiles = []
    for _, r in df.iterrows():
        label, tone = sector_verdict(r)
        tiles.append(
            f'<div class="tt-tile"><div class="tt-row"><div style="min-width:0">'
            f'<div class="tt-k" title="{s.esc(r["name"])}">{s.esc(r["name"])}</div>'
            f'<div class="tt-v {s.tone(r["m3"])}-t">{c.fmt_pct(r["m3"])}</div>'
            f'<div class="tt-s">1 Monat {c.fmt_pct(r["m1"])}</div></div>'
            f'<div style="width:40%">{s.sparkline(r["series"], 120, 40)}</div></div>'
            f'<div style="margin-top:.45rem">{s.pill(label, tone)}</div></div>')
    s.html_block(f'<div class="tt-grid c6">{"".join(tiles)}</div>')
    best = df.iloc[0]["name"]
    worst = df.iloc[-1]["name"]
    st.caption(f"Am stärksten: **{best}**, am schwächsten: **{worst}**. Ideen aus starken Branchen "
               "haben oft Rückenwind – aus schwachen Branchen eher Gegenwind. (Maßstab: US-Branchenfonds)")
