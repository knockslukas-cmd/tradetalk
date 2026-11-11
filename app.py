"""tradetalk – Streamlit-App.

Zeigt oben das Marktumfeld und darunter die liquiden Aktien aus dem letzten
Tageslauf (results/). Ein Klick auf eine Zeile lädt den Kurs-Chart live per
yfinance.

Lokal starten:  streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SCAN_PATH = RESULTS / "scan_latest.parquet"
REGIME_PATH = RESULTS / "market_regime.json"

st.set_page_config(page_title="tradetalk", page_icon="📈", layout="wide")


# --------------------------------------------------------------------------- #
# Daten
# --------------------------------------------------------------------------- #
def mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data(show_spinner=False)
def load_scan(_mtime: float) -> pd.DataFrame:
    return pd.read_parquet(SCAN_PATH)


@st.cache_data(show_spinner=False)
def load_regime(_mtime: float) -> dict:
    with open(REGIME_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(ttl=900, show_spinner=False)
def load_chart_data(ticker: str, period: str) -> pd.DataFrame:
    # immer 1 Jahr mehr laden, damit die 200-Tage-Linie ab Chartbeginn existiert
    extra = {"6mo": "2y", "1y": "2y", "3y": "5y", "5y": "max"}[period]
    df = yf.download(ticker, period=extra, auto_adjust=False, progress=False,
                     multi_level_index=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Close"])
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    start = df.index[-1] - pd.DateOffset(months={"6mo": 6, "1y": 12, "3y": 36, "5y": 60}[period])
    return df[df.index >= start]


# --------------------------------------------------------------------------- #
# Marktumfeld
# --------------------------------------------------------------------------- #
VERDICT_STYLE = {
    "Rückenwind": ("🟢", st.success),
    "neutral": ("🟡", st.warning),
    "Gegenwind": ("🔴", st.error),
}


def show_regime(regime: dict) -> None:
    icon, box = VERDICT_STYLE.get(regime["verdict"], ("⚪", st.info))
    generated = pd.Timestamp(regime["generated_at"]).tz_convert("Europe/Berlin")
    box(
        f"{icon} **Marktlage: {regime['verdict']}** (Punkte: {regime['points']:+d}) · "
        f"{regime.get('liquid_count', '–')} von {regime.get('universe_count', '–')} Aktien "
        f"bestehen den Liquiditätsfilter · Stand {generated:%d.%m.%Y %H:%M}"
    )
    short, long = regime["sma_short"], regime["sma_long"]
    cols = st.columns(len(regime["indices"]) + 1)
    for col, idx in zip(cols, regime["indices"]):
        if not idx.get("available"):
            col.metric(idx["name"], "keine Daten")
            continue
        dist = (idx["close"] / idx["sma_long"] - 1) * 100
        col.metric(idx["name"], f"{idx['close']:,.0f}", f"{dist:+.1f} % zur SMA{long}")
        col.caption(
            f"SMA{short}: {'✅' if idx['above_short'] else '❌'} · "
            f"SMA{long}: {'✅' if idx['above_long'] else '❌'} · {idx['label']}"
        )
    vix = regime.get("vix")
    if vix:
        cols[-1].metric("VIX", f"{vix['value']:.1f}", vix["label"], delta_color="off")


# --------------------------------------------------------------------------- #
# Tabelle
# --------------------------------------------------------------------------- #
def sidebar_filters(scan: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filter")
    query = st.sidebar.text_input("Suche (Ticker oder Name)").strip().lower()
    countries = st.sidebar.multiselect("Land", sorted(scan["country"].unique()))
    exchanges = st.sidebar.multiselect("Börse", sorted(scan["exchange"].unique()))
    min_price = st.sidebar.number_input("Mindestkurs", min_value=0.0, value=0.0, step=5.0)
    min_vol = st.sidebar.number_input("Mindest-Ø-Umsatz (Mio.)", min_value=0.0, value=0.0, step=5.0)
    trend = st.sidebar.radio(
        "Trend", ["alle", "über SMA200", "über SMA50 und SMA200", "unter SMA200"], index=0
    )
    perf = st.sidebar.slider("Performance 3 Monate (%)", -100, 300, (-100, 300), step=5)

    view = scan
    if query:
        view = view[view["ticker"].str.lower().str.contains(query, regex=False)
                    | view["name"].str.lower().str.contains(query, regex=False)]
    if countries:
        view = view[view["country"].isin(countries)]
    if exchanges:
        view = view[view["exchange"].isin(exchanges)]
    view = view[(view["close"] >= min_price) & (view["avg_dollar_volume"] >= min_vol * 1e6)]
    if trend == "über SMA200":
        view = view[view["dist_sma200"] > 0]
    elif trend == "über SMA50 und SMA200":
        view = view[(view["dist_sma50"] > 0) & (view["dist_sma200"] > 0)]
    elif trend == "unter SMA200":
        view = view[view["dist_sma200"] < 0]
    lo, hi = perf
    if (lo, hi) != (-100, 300):
        view = view[view["perf_3m"].between(lo, hi)]
    return view


COLUMN_CONFIG = {
    "ticker": st.column_config.TextColumn("Ticker"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "exchange": st.column_config.TextColumn("Börse"),
    "country": st.column_config.TextColumn("Land"),
    "close": st.column_config.NumberColumn("Kurs", format="%.2f"),
    "avg_volume_m": st.column_config.NumberColumn("Ø Umsatz (Mio.)", format="%.1f"),
    "chg_1d": st.column_config.NumberColumn("1 Tag %", format="%+.1f"),
    "perf_1m": st.column_config.NumberColumn("1 Mon. %", format="%+.1f"),
    "perf_3m": st.column_config.NumberColumn("3 Mon. %", format="%+.1f"),
    "perf_1y": st.column_config.NumberColumn("1 Jahr %", format="%+.1f"),
    "dist_sma50": st.column_config.NumberColumn("zu SMA50 %", format="%+.1f"),
    "dist_sma200": st.column_config.NumberColumn("zu SMA200 %", format="%+.1f"),
    "dist_52w_high": st.column_config.NumberColumn("zum 52W-Hoch %", format="%+.1f"),
    "last_date": st.column_config.DateColumn("Stand", format="DD.MM.YYYY"),
}


# --------------------------------------------------------------------------- #
# Chart
# --------------------------------------------------------------------------- #
def show_chart(row: pd.Series) -> None:
    ticker = row["ticker"]
    st.subheader(f"{ticker} · {row['name']}")
    period = st.radio("Zeitraum", ["6mo", "1y", "3y", "5y"], index=1, horizontal=True,
                      format_func={"6mo": "6 Monate", "1y": "1 Jahr", "3y": "3 Jahre",
                                   "5y": "5 Jahre"}.get)
    with st.spinner(f"Lade Kurse für {ticker} …"):
        df = load_chart_data(ticker, period)
    if df.empty:
        st.warning(f"Für {ticker} konnten keine Kurse geladen werden.")
        return

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
                        vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"],
                                 close=df["Close"], name="Kurs"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], name="SMA50",
                             line=dict(width=1.5, color="#1f77b4")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], name="SMA200",
                             line=dict(width=1.5, color="#ff7f0e")), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volumen",
                         marker_color="rgba(128,128,128,0.5)"), row=2, col=1)
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, hovermode="x unified",
                      margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.02, x=0))
    # Wochenenden ausblenden, damit keine Lücken entstehen
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("📈 tradetalk")

    if not SCAN_PATH.exists() or not REGIME_PATH.exists():
        st.error("Noch keine Ergebnisse vorhanden. Bitte zuerst `python src/run_daily.py` ausführen.")
        st.stop()

    show_regime(load_regime(mtime(REGIME_PATH)))
    st.divider()

    scan = load_scan(mtime(SCAN_PATH)).copy()
    scan["avg_volume_m"] = scan["avg_dollar_volume"] / 1e6
    view = sidebar_filters(scan)
    view = view[[c for c in COLUMN_CONFIG if c in view.columns]].reset_index(drop=True)

    st.caption(f"{len(view)} von {len(scan)} Aktien · Spaltenkopf anklicken zum Sortieren · "
               "Zeile anklicken für den Chart")
    event = st.dataframe(
        view,
        column_config=COLUMN_CONFIG,
        hide_index=True,
        use_container_width=True,
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        key="scan_table",
    )

    rows = event.selection.rows if event and event.selection else []
    if rows and rows[0] < len(view):
        st.divider()
        show_chart(view.iloc[rows[0]])
    else:
        st.info("Klicke auf eine Zeile in der Tabelle, um den Kurs-Chart zu sehen.")


main()
