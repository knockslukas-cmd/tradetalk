"""Seite "Dashboard": Marktlage, Top-Setups und Auffälligkeiten auf einen Blick."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tt_app import common as c
from tt_app import style as s

SETUP_KINDS = {"Alle": None, "Ausbrüche": "breakout_52w", "Pullbacks": "pullback_sma50",
               "Golden Cross": "golden_cross", "Über SMA200 zurück": "reclaim_sma200",
               "Überverkauft": "oversold_trend"}


# --------------------------------------------------------------------------- #
# Marktlage
# --------------------------------------------------------------------------- #
def regime_text(regime: dict) -> str:
    idx = [i for i in regime["indices"] if i.get("available")]
    above = sum(1 for i in idx if i["above_long"])
    both = sum(1 for i in idx if i["above_short"] and i["above_long"])
    parts = [f"{above} von {len(idx)} Indizes über der 200-Tage-Linie, {both} auch über der 50-Tage-Linie."]
    if regime.get("vix"):
        parts.append(f"VIX {c.fmt_num(regime['vix']['value'], 1)} – {regime['vix']['label']}.")
    hint = {"Rückenwind": "Gutes Umfeld für Long-Setups.",
            "neutral": "Gemischtes Umfeld – Setups selektiv angehen.",
            "Gegenwind": "Schwieriges Umfeld – eher abwarten oder kleiner positionieren."}
    parts.append(hint.get(regime["verdict"], ""))
    return " ".join(parts)


def index_tile(name: str, value: float, series: list[float], extra_pills: str,
               digits: int = 0, spark_color: str | None = None) -> str:
    chg = (series[-1] / series[-2] - 1) * 100 if len(series) > 1 else float("nan")
    chg_html = f'<span class="{s.tone(chg)}-t">{c.fmt_pct(chg)}</span>'
    return (
        f'<div class="tt-tile"><div class="tt-row"><div style="min-width:0">'
        f'<div class="tt-k">{s.esc(name)}</div>'
        f'<div class="tt-v">{c.fmt_num(value, digits)}</div>'
        f'<div class="tt-s">{chg_html} heute</div></div>'
        f'<div style="width:46%">{s.sparkline(series[-90:], 140, 44, color=spark_color)}</div></div>'
        f'<div style="margin-top:.55rem">{extra_pills}</div></div>'
    )


def regime_section() -> None:
    stored = c.stored_regime()
    with st.spinner("Lade aktuelle Indexstände …"):
        live = c.live_regime()
    regime = live or stored
    if not regime:
        st.warning("Keine Marktdaten vorhanden.")
        return

    verdict = regime["verdict"]
    color = s.VERDICT_COLOR.get(verdict, s.MUTED)
    pos = (max(-4, min(4, regime["points"])) + 4) / 8 * 100
    source = "Live" if live else f"Stand {c.berlin(stored['generated_at'])}"
    glow = {"Rückenwind": "rgba(38,208,124,.22)", "neutral": "rgba(245,165,36,.18)",
            "Gegenwind": "rgba(240,80,110,.22)"}.get(verdict, "rgba(139,149,167,.15)")

    symbols = tuple(i["symbol"] for i in regime["indices"]) + (c.config()["market_regime"]["vix"],)
    series = c.closes(symbols, "6mo")
    tiles = []
    long, short = regime["sma_long"], regime["sma_short"]
    for i in regime["indices"]:
        if not i.get("available"):
            tiles.append(s.tile(i["name"], "–"))
            continue
        pills = (s.pill(f"SMA{short} {'✓' if i['above_short'] else '✗'}",
                        "up" if i["above_short"] else "down")
                 + s.pill(f"SMA{long} {'✓' if i['above_long'] else '✗'}",
                          "up" if i["above_long"] else "down"))
        short_name = {"Nasdaq Composite": "Nasdaq"}.get(i["name"], i["name"])
        tiles.append(index_tile(short_name, i["close"], series.get(i["symbol"], [i["close"]]), pills))
    if regime.get("vix"):
        v = regime["vix"]
        kind = {"ruhig": "up", "erhöht": "warn", "Stress": "down"}.get(v["label"], "muted")
        tiles.append(index_tile("VIX", v["value"],
                                series.get(symbols[-1], [v["value"]]), s.pill(v["label"], kind),
                                digits=1, spark_color=s.WARN))

    s.html_block(
        f'<div class="tt-hero" style="--glow:{glow}"><div class="tt-hero-grid">'
        f'<div><div class="tt-label">Marktlage · {s.esc(source)}</div>'
        f'<div class="tt-verdict" style="color:{color}">{s.esc(verdict)}</div>'
        f'<div class="tt-text">{s.esc(regime_text(regime))}</div>'
        f'<div class="tt-scale"><div class="tt-marker" style="left:{pos:.0f}%"></div></div>'
        f'<div class="tt-scale-labels"><span>Gegenwind</span><span>Punkte {regime["points"]:+d}</span>'
        f'<span>Rückenwind</span></div></div>'
        f'<div class="tt-grid c4">{"".join(tiles)}</div></div></div>'
    )


def breadth_section(stored: dict) -> None:
    b = stored.get("breadth")
    if not b:
        return
    total_ad = (b["advancers"] + b["decliners"]) or 1
    total_hl = (b["new_highs"] + b["new_lows"]) or 1
    adv = b["advancers"] / total_ad * 100
    hi = b["new_highs"] / total_hl * 100
    tiles = [
        s.tile("Aktien über SMA200", c.fmt_num(b["above_sma200_pct"], 0, " %"), "langfristiger Trend",
               s.bar([(b["above_sma200_pct"], s.ACCENT)])),
        s.tile("Aktien über SMA50", c.fmt_num(b["above_sma50_pct"], 0, " %"), "mittelfristiger Trend",
               s.bar([(b["above_sma50_pct"], s.INFO)])),
        s.tile("Gewinner / Verlierer",
               f'<span class="up-t">{b["advancers"]}</span> / <span class="down-t">{b["decliners"]}</span>',
               "heute", s.bar([(adv, s.UP), (100 - adv, s.DOWN)])),
        s.tile("Neue 52W-Hochs / -Tiefs",
               f'<span class="up-t">{b["new_highs"]}</span> / <span class="down-t">{b["new_lows"]}</span>',
               "Marktbreite", s.bar([(hi, s.UP), (100 - hi, s.DOWN)])),
        s.tile("Setups / Warnsignale",
               f'<span class="up-t">{b["setups"]}</span> / <span class="down-t">{b["warnings"]}</span>',
               "im liquiden Universum"),
    ]
    s.html_block(f'<div class="tt-grid c5" style="margin-top:.8rem">{"".join(tiles)}</div>')

    hist = c.history()
    if len(hist) > 1:
        with st.expander("📈 Verlauf der Marktlage"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hist["date"], y=hist["points"], name="Punkte",
                                     line=dict(color=s.ACCENT, width=2), mode="lines+markers"))
            if "above_sma200_pct" in hist:
                fig.add_trace(go.Scatter(x=hist["date"], y=hist["above_sma200_pct"],
                                         name="% über SMA200", yaxis="y2",
                                         line=dict(color=s.WARN, dash="dot")))
            fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              yaxis=dict(title="Punkte", gridcolor="#1a2130"),
                              yaxis2=dict(title="%", overlaying="y", side="right", range=[0, 100]),
                              legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Setups
# --------------------------------------------------------------------------- #
def setup_card(row: pd.Series, spark: list[float]) -> str:
    risk = row.get("risk_pct")
    risk_txt = "–" if risk is None or (isinstance(risk, float) and math.isnan(risk)) else c.fmt_num(risk, 1, " %")
    return (
        f'<a class="tt-card" href="analyse?ticker={s.esc(row["ticker"])}" target="_self">'
        f'<div class="tt-top"><div style="min-width:0">'
        f'<div class="tt-tk">{s.esc(row["ticker"])}<span class="tt-score">{c.fmt_num(row["score"], 1)}</span></div>'
        f'<div class="tt-nm">{s.esc(row["name"])}</div></div>'
        f'<div class="tt-px">{c.fmt_num(row["close"])} <small>{s.esc(row["currency"])}</small><br>'
        f'<span class="{s.tone(row["chg_1d"])}-t" style="font-size:.85rem">{c.fmt_pct(row["chg_1d"])}</span></div></div>'
        f'<div class="tt-spark">{s.sparkline(spark, 300, 52)}</div>'
        f'<div>{c.signal_pills(row["signal_keys"])}</div>'
        f'<div class="tt-stats">'
        f'<div>RSI<b>{c.fmt_num(row["rsi14"], 0)}</b></div>'
        f'<div>Rel. Stärke<b>{c.fmt_num(row["rs_rank"], 0)}</b></div>'
        f'<div>Volumen<b>{c.fmt_num(row["vol_ratio"], 1)}×</b></div>'
        f'<div>Risiko<b>{risk_txt}</b></div></div></a>'
    )


def setups_section(scan: pd.DataFrame) -> None:
    setups = scan[scan["has_setup"] & (scan["score"] > 0)].sort_values("score", ascending=False)
    s.section("🎯 Top-Setups", f"{len(setups)} gefunden")
    if setups.empty:
        st.info("Heute keine Setups gefunden.")
        return
    choice = st.segmented_control("Art", list(SETUP_KINDS), default="Alle",
                                  label_visibility="collapsed", key="setup_kind") or "Alle"
    if SETUP_KINDS[choice]:
        setups = setups[setups["signal_keys"].str.contains(SETUP_KINDS[choice])]
    top = setups.head(9)
    if top.empty:
        st.caption("Keine Setups dieser Art.")
        return
    sparks = c.closes(tuple(top["ticker"]), "3mo")
    cards = "".join(setup_card(r, sparks.get(r["ticker"], [])) for _, r in top.iterrows())
    s.html_block(f'<div class="tt-grid c3">{cards}</div>')
    st.caption("Score = Signalstärke + relative Stärke + Volumen · Karte anklicken für die Analyse")


# --------------------------------------------------------------------------- #
# Auffälligkeiten
# --------------------------------------------------------------------------- #
def pick_table(df: pd.DataFrame, columns: dict, key: str) -> None:
    if df.empty:
        st.caption("Nichts Auffälliges.")
        return
    view = df[list(columns)].reset_index(drop=True)
    event = st.dataframe(view, column_config=columns, hide_index=True, use_container_width=True,
                         height=min(36 * (len(view) + 1) + 3, 400), on_select="rerun",
                         selection_mode="single-row", key=key)
    rows = event.selection.rows if event and event.selection else []
    if rows:
        c.open_analysis(view.iloc[rows[0]]["ticker"])


def anomalies_section(scan: pd.DataFrame) -> None:
    s.section("⚡ Auffälligkeiten", "Zeile anklicken für die Analyse")
    base = {
        "ticker": st.column_config.TextColumn("Ticker"),
        "name": st.column_config.TextColumn("Name", width="medium"),
        "close": st.column_config.NumberColumn("Kurs", format="%.2f"),
        "chg_1d": st.column_config.NumberColumn("Heute %", format="%+.1f"),
    }
    vol = {**base, "vol_ratio": st.column_config.NumberColumn("Volumen ×", format="%.1f"),
           "perf_1m": st.column_config.NumberColumn("1 Mon. %", format="%+.1f")}
    gap = {**base, "gap_pct": st.column_config.NumberColumn("Gap %", format="%+.1f"),
           "vol_ratio": st.column_config.NumberColumn("Volumen ×", format="%.1f")}
    hi = {**base, "perf_3m": st.column_config.NumberColumn("3 Mon. %", format="%+.1f"),
          "rs_rank": st.column_config.ProgressColumn("Rel. Stärke", min_value=0, max_value=100,
                                                     format="%.0f")}
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
    df = c.scan()
    stored = c.stored_regime()
    sub = ""
    if stored:
        sub = (f"Scan {c.berlin(stored['generated_at'])} · {stored.get('liquid_count', len(df))} "
               f"liquide Aktien von {stored.get('universe_count', '–')}")
    s.page_head('<span class="tt-logo">tradetalk</span> Dashboard', sub)
    regime_section()
    breadth_section(stored)
    if df.empty:
        st.error("Noch keine Scan-Ergebnisse vorhanden.")
        return
    if not c.has_signals(df):
        st.info("Die Signale erscheinen nach dem nächsten Aktualisierungslauf.")
        return
    setups_section(df)
    anomalies_section(df)
    s.html_block(f'<div class="tt-disclaimer">{s.esc(c.DISCLAIMER)}</div>')
