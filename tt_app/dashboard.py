"""Seite "Dashboard": Marktlage, Top-Setups und Auffälligkeiten auf einen Blick."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tt_app import common as c


def regime_section() -> None:
    stored = c.stored_regime()
    with st.spinner("Lade aktuelle Indexstände …"):
        live = c.live_regime()
    regime = live or stored
    if not regime:
        st.warning("Keine Marktdaten vorhanden.")
        return

    icon, color = c.VERDICT_STYLE.get(regime["verdict"], ("⚪", "gray"))
    source = "live" if live else f"Stand {c.berlin(stored['generated_at'])}"
    st.markdown(f"### {icon} Marktlage: :{color}[{regime['verdict']}]  "
                f"<span style='font-size:0.9rem;opacity:0.7'>Punkte {regime['points']:+d} · "
                f"{source}</span>", unsafe_allow_html=True)

    long = regime["sma_long"]
    cols = st.columns(len(regime["indices"]) + 1)
    for col, idx in zip(cols, regime["indices"]):
        if not idx.get("available"):
            col.metric(idx["name"], "–")
            continue
        dist = (idx["close"] / idx["sma_long"] - 1) * 100
        col.metric(idx["name"], c.fmt_num(idx["close"], 0), f"{c.fmt_pct(dist)} zur SMA{long}")
        col.caption(idx["label"])
    if regime.get("vix"):
        v = regime["vix"]
        cols[-1].metric("VIX", c.fmt_num(v["value"], 1), v["label"], delta_color="off")

    # Marktbreite aus dem letzten Scan
    b = stored.get("breadth")
    if b:
        bc = st.columns(5)
        bc[0].metric("Aktien über SMA200", c.fmt_num(b["above_sma200_pct"], 0, " %"))
        bc[1].metric("Aktien über SMA50", c.fmt_num(b["above_sma50_pct"], 0, " %"))
        bc[2].metric("Neue 52W-Hochs / -Tiefs", f"{b['new_highs']} / {b['new_lows']}")
        bc[3].metric("Gewinner / Verlierer", f"{b['advancers']} / {b['decliners']}")
        bc[4].metric("Setups / Warnsignale", f"{b['setups']} / {b['warnings']}")

    hist = c.history()
    if len(hist) > 1:
        with st.expander("Verlauf der Marktlage"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hist["date"], y=hist["points"], name="Punkte",
                                     line=dict(color="#4c9be8"), mode="lines+markers"))
            if "above_sma200_pct" in hist:
                fig.add_trace(go.Scatter(x=hist["date"], y=hist["above_sma200_pct"],
                                         name="% über SMA200", yaxis="y2",
                                         line=dict(color="#f0a43a", dash="dot")))
            fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                              yaxis=dict(title="Punkte"),
                              yaxis2=dict(title="%", overlaying="y", side="right", range=[0, 100]),
                              legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)

    if regime["verdict"] == "Gegenwind":
        st.warning("Gegenwind: Neue Long-Setups haben es in diesem Umfeld schwerer. "
                   "Positionen eher kleiner wählen oder abwarten.")


def setup_card(row: pd.Series, key: str) -> None:
    with st.container(border=True):
        top = st.columns([3, 2])
        top[0].markdown(f"**{row['ticker']}**  \n<span style='opacity:0.7;font-size:0.85rem'>"
                        f"{str(row['name'])[:38]}</span>", unsafe_allow_html=True)
        top[1].markdown(f"<div style='text-align:right'><b>{c.fmt_num(row['close'])}</b> "
                        f"{row['currency']}<br><span style='font-size:0.85rem'>"
                        f"{c.fmt_pct(row['chg_1d'])} heute</span></div>",
                        unsafe_allow_html=True)
        st.markdown(c.signal_badges(row["signal_keys"]))
        st.caption(
            f"RSI {c.fmt_num(row['rsi14'], 0)} · Rel. Stärke {c.fmt_num(row['rs_rank'], 0)}/100 · "
            f"Vol. {c.fmt_num(row['vol_ratio'], 1)}× · "
            f"Stopp {c.fmt_num(row['stop'])} ({c.fmt_pct(-row['risk_pct'])})"
        )
        if st.button("Analyse öffnen →", key=f"open_{key}", use_container_width=True):
            c.open_analysis(row["ticker"])


def setups_section(scan: pd.DataFrame) -> None:
    st.subheader("🎯 Top-Setups")
    setups = scan[scan["has_setup"] & (scan["score"] > 0)].sort_values("score", ascending=False)
    if setups.empty:
        st.info("Heute keine Setups gefunden.")
        return
    kinds = {"Alle": None, "Ausbrüche": "breakout_52w", "Pullbacks": "pullback_sma50",
             "Golden Cross": "golden_cross", "Rückeroberung SMA200": "reclaim_sma200",
             "Überverkauft": "oversold_trend"}
    choice = st.segmented_control("Art", list(kinds), default="Alle",
                                  label_visibility="collapsed", key="setup_kind")
    if kinds.get(choice or "Alle"):
        setups = setups[setups["signal_keys"].str.contains(kinds[choice])]
    st.caption(f"{len(setups)} Setups · sortiert nach Score (Signalstärke, relative Stärke, "
               "Volumen)")
    top = setups.head(9)
    for start in range(0, len(top), 3):
        cols = st.columns(3)
        for col, (_, row) in zip(cols, top.iloc[start:start + 3].iterrows()):
            with col:
                setup_card(row, f"setup_{row['ticker']}")


def pick_table(df: pd.DataFrame, columns: dict, key: str) -> None:
    """Kompakte Tabelle; ein Klick auf eine Zeile öffnet die Analyse."""
    if df.empty:
        st.caption("Nichts Auffälliges.")
        return
    view = df[list(columns)].reset_index(drop=True)
    event = st.dataframe(view, column_config=columns, hide_index=True, use_container_width=True,
                         height=min(38 * (len(view) + 1) + 3, 390), on_select="rerun",
                         selection_mode="single-row", key=key)
    rows = event.selection.rows if event and event.selection else []
    if rows:
        c.open_analysis(view.iloc[rows[0]]["ticker"])


def anomalies_section(scan: pd.DataFrame) -> None:
    st.subheader("⚡ Auffälligkeiten")
    st.caption("Zeile anklicken für die Analyse")
    base = {
        "ticker": st.column_config.TextColumn("Ticker"),
        "name": st.column_config.TextColumn("Name", width="medium"),
        "close": st.column_config.NumberColumn("Kurs", format="%.2f"),
        "chg_1d": st.column_config.NumberColumn("Heute %", format="%+.1f"),
    }
    vol = {**base, "vol_ratio": st.column_config.NumberColumn("Volumen ×", format="%.1f")}
    gap = {**base, "gap_pct": st.column_config.NumberColumn("Gap %", format="%+.1f")}
    hi = {**base, "perf_3m": st.column_config.NumberColumn("3 Mon. %", format="%+.1f")}
    warn = {**base, "signals": st.column_config.TextColumn("Signal", width="medium")}

    tabs = st.tabs(["🔊 Volumen", "↕️ Gaps", "🚀 Gewinner", "📉 Verlierer",
                    "🏔️ Neue Hochs", "⚠️ Warnsignale"])
    with tabs[0]:
        df = scan[scan["vol_ratio"] >= 2].sort_values("vol_ratio", ascending=False).head(15)
        pick_table(df, vol, "t_vol")
    with tabs[1]:
        df = scan[scan["gap_pct"].abs() >= 4]
        df = df.reindex(df["gap_pct"].abs().sort_values(ascending=False).index).head(15)
        pick_table(df, gap, "t_gap")
    with tabs[2]:
        pick_table(scan.sort_values("chg_1d", ascending=False).head(15), vol, "t_win")
    with tabs[3]:
        pick_table(scan.sort_values("chg_1d").head(15), vol, "t_lose")
    with tabs[4]:
        df = scan[scan["new_52w_high"]].sort_values("perf_3m", ascending=False).head(15)
        pick_table(df, hi, "t_high")
    with tabs[5]:
        df = scan[scan["has_warning"]].sort_values("avg_dollar_volume", ascending=False).head(15)
        pick_table(df, warn, "t_warn")


def render() -> None:
    st.title("📈 tradetalk")
    df = c.scan()
    stored = c.stored_regime()
    if stored:
        st.caption(f"Scan-Stand: {c.berlin(stored['generated_at'])} · "
                   f"{stored.get('liquid_count', len(df))} liquide Aktien von "
                   f"{stored.get('universe_count', '–')}")
    regime_section()
    st.divider()
    if df.empty:
        st.error("Noch keine Scan-Ergebnisse vorhanden.")
        return
    if not c.has_signals(df):
        st.info("Die Signale erscheinen nach dem nächsten Aktualisierungslauf.")
        return
    setups_section(df)
    st.divider()
    anomalies_section(df)
    st.caption(c.DISCLAIMER)
