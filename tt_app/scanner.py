"""Seite "Scanner": alle liquiden Aktien, filter- und sortierbar."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tt_app import common as c
from tt_app import style as s
from tt_app.signals_ui import SIGNAL_OPTIONS

COLUMNS = {
    "ticker": st.column_config.TextColumn("Ticker"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "exchange": st.column_config.TextColumn("Börse"),
    "close": st.column_config.NumberColumn("Kurs", format="%.2f"),
    "currency": st.column_config.TextColumn("Whg."),
    "signals": st.column_config.TextColumn("Signale", width="medium"),
    "score": st.column_config.NumberColumn("Score", format="%.1f"),
    "chg_1d": st.column_config.NumberColumn("1 Tag %", format="%+.1f"),
    "perf_1m": st.column_config.NumberColumn("1 Mon. %", format="%+.1f"),
    "perf_3m": st.column_config.NumberColumn("3 Mon. %", format="%+.1f"),
    "perf_1y": st.column_config.NumberColumn("1 Jahr %", format="%+.1f"),
    "rs_rank": st.column_config.ProgressColumn("Rel. Stärke", min_value=0, max_value=100,
                                               format="%.0f"),
    "rsi14": st.column_config.NumberColumn("RSI", format="%.0f"),
    "vol_ratio": st.column_config.NumberColumn("Vol. ×", format="%.1f"),
    "dist_sma50": st.column_config.NumberColumn("zu SMA50 %", format="%+.1f"),
    "dist_sma200": st.column_config.NumberColumn("zu SMA200 %", format="%+.1f"),
    "dist_52w_high": st.column_config.NumberColumn("zum 52W-Hoch %", format="%+.1f"),
    "atr_pct": st.column_config.NumberColumn("ATR %", format="%.1f"),
    "avg_volume_m": st.column_config.NumberColumn("Ø Umsatz (Mio.)", format="%.1f"),
}


def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filter")
        query = st.text_input("Suche (Ticker oder Name)").strip().lower()
        sig = st.multiselect("Signale", list(SIGNAL_OPTIONS), placeholder="alle")
        countries = st.multiselect("Land", sorted(df["country"].unique()), placeholder="alle")
        exchanges = st.multiselect("Börse", sorted(df["exchange"].unique()), placeholder="alle")
        trend = st.radio("Trend", ["alle", "über SMA200", "über SMA50 und SMA200",
                                   "unter SMA200"])
        min_rs = st.slider("Relative Stärke mindestens", 0, 100, 0, step=5)
        min_price = st.number_input("Mindestkurs", min_value=0.0, value=0.0, step=5.0)
        min_vol = st.number_input("Mindest-Ø-Umsatz (Mio.)", min_value=0.0, value=0.0, step=5.0)

    view = df
    if query:
        view = view[view["ticker"].str.lower().str.contains(query, regex=False)
                    | view["name"].str.lower().str.contains(query, regex=False)]
    if sig:
        pattern = "|".join(SIGNAL_OPTIONS[s] for s in sig)
        view = view[view["signal_keys"].str.contains(pattern)]
    if countries:
        view = view[view["country"].isin(countries)]
    if exchanges:
        view = view[view["exchange"].isin(exchanges)]
    if trend == "über SMA200":
        view = view[view["dist_sma200"] > 0]
    elif trend == "über SMA50 und SMA200":
        view = view[(view["dist_sma50"] > 0) & (view["dist_sma200"] > 0)]
    elif trend == "unter SMA200":
        view = view[view["dist_sma200"] < 0]
    if min_rs and "rs_rank" in view:
        view = view[view["rs_rank"] >= min_rs]
    view = view[(view["close"] >= min_price) & (view["avg_dollar_volume"] >= min_vol * 1e6)]
    return view


def render() -> None:
    s.page_head('<span class="tt-logo">tradetalk</span> Scanner',
                "Alle liquiden Aktien · filtern in der Seitenleiste")
    df = c.scan()
    if df.empty:
        st.error("Noch keine Scan-Ergebnisse vorhanden.")
        return
    view = sidebar_filters(df)
    sort_default = "score" if c.has_signals(df) else "avg_volume_m"
    view = view.sort_values(sort_default, ascending=False)
    view = view[[k for k in COLUMNS if k in view.columns]].reset_index(drop=True)

    left, right = st.columns([3, 1])
    left.caption(f"{len(view)} von {len(df)} Aktien · Spaltenkopf anklicken zum Sortieren · "
                 "Zeile anklicken für die Analyse")
    right.download_button("⬇️ Als CSV", view.to_csv(index=False).encode("utf-8"),
                          "tradetalk_scan.csv", "text/csv", use_container_width=True)
    event = st.dataframe(view, column_config=COLUMNS, hide_index=True, use_container_width=True,
                         height=640, on_select="rerun", selection_mode="single-row",
                         key="scan_table")
    rows = event.selection.rows if event and event.selection else []
    if rows:
        c.open_analysis(view.iloc[rows[0]]["ticker"])
    s.html_block(f'<div class="tt-disclaimer">{s.esc(c.DISCLAIMER)}</div>')
