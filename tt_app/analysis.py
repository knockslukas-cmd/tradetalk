"""Seite "Aktienanalyse": automatische Recherche zu einer einzelnen Aktie.

Lädt die Kurse live, berechnet Trend, Momentum, Volumen und Signale neu,
vergleicht mit dem Heimatindex und sammelt Unternehmensdaten, Termine und
Nachrichten. Daraus entsteht eine kurze, regelbasierte Einschätzung.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
import streamlit as st

from tt_app import common as c

BENCHMARK = {"US": ("^GSPC", "S&P 500"), "DE": ("^GDAXI", "DAX")}
RECOMMENDATION = {"strong_buy": "Starker Kauf", "buy": "Kaufen", "hold": "Halten",
                  "underperform": "Untergewichten", "sell": "Verkaufen",
                  "strong_sell": "Starker Verkauf", "none": "–"}


def nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def perf(df: pd.DataFrame, days: int) -> float:
    if len(df) <= days:
        return float("nan")
    return (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-days - 1]) - 1) * 100


def assessment(m: dict, rs_rank, rel_3m: float, bench: str, earnings,
               regime: dict | None) -> tuple[str, str, list[str], list[str]]:
    """Fazit, Farbe, positive und negative Punkte."""
    pros, cons = [], []

    # Trend
    if m["uptrend"]:
        pros.append("**Intakter Aufwärtstrend:** Kurs über SMA200, SMA50 über SMA200.")
    elif not nan(m["dist_sma200"]) and m["dist_sma200"] < 0:
        cons.append(f"**Abwärtstrend:** Kurs {c.fmt_pct(m['dist_sma200'])} unter der SMA200.")
    else:
        cons.append("**Trend uneinheitlich:** SMA50 und SMA200 geben kein klares Bild.")

    # Momentum
    r = m["rsi14"]
    if not nan(r):
        if r >= 75:
            cons.append(f"**RSI {r:.0f}: stark überkauft**, Rücksetzer wahrscheinlicher.")
        elif r >= 60:
            pros.append(f"**RSI {r:.0f}:** kräftiges Momentum.")
        elif r <= 30:
            (pros if m["uptrend"] else cons).append(
                f"**RSI {r:.0f}: überverkauft**"
                + (" – im Aufwärtstrend oft eine Einstiegschance." if m["uptrend"] else "."))
        else:
            pros.append(f"**RSI {r:.0f}:** neutral, nicht überhitzt.")

    # Relative Stärke
    if not nan(rel_3m):
        text = f"{c.fmt_pct(rel_3m)} gegenüber dem {bench} (3 Monate)"
        (pros if rel_3m > 0 else cons).append(
            f"**{'Stärker' if rel_3m > 0 else 'Schwächer'} als der Markt:** {text}.")
    if not nan(rs_rank):
        if rs_rank >= 80:
            pros.append(f"**Relative Stärke {rs_rank:.0f}/100:** gehört zu den stärksten Aktien "
                        "im Universum.")
        elif rs_rank <= 30:
            cons.append(f"**Relative Stärke {rs_rank:.0f}/100:** gehört zu den schwächeren "
                        "Aktien.")

    # Lage zum Hoch, Volumen, Volatilität
    d = m["dist_52w_high"]
    if not nan(d):
        if d >= -3:
            pros.append(f"**Nahe am 52-Wochen-Hoch** ({c.fmt_pct(d)}) – kaum Widerstand darüber.")
        elif d <= -30:
            cons.append(f"**Weit unter dem 52-Wochen-Hoch** ({c.fmt_pct(d)}).")
    v = m["vol_ratio"]
    if not nan(v) and v >= 1.5:
        (pros if m["chg_1d"] > 0 else cons).append(
            f"**Volumen {c.fmt_num(v, 1)}× über dem Schnitt** bei {c.fmt_pct(m['chg_1d'])} – "
            f"{'Käufer' if m['chg_1d'] > 0 else 'Verkäufer'} sind aktiv.")
    if not nan(m["atr_pct"]) and m["atr_pct"] >= 6:
        cons.append(f"**Hohe Schwankung:** typische Tagesbewegung {c.fmt_num(m['atr_pct'], 1)} %.")

    # Signale
    for k in [k for k in m["signal_keys"].split(",") if k]:
        name, kind, _ = c.signals.SIGNALS[k]
        (pros if kind == "setup" else cons if kind == "warning" else pros).append(
            f"**Signal:** {name}.")

    # Termine
    if earnings:
        days = (pd.Timestamp(earnings).date() - date.today()).days
        if 0 <= days <= 14:
            cons.append(f"**Zahlen in {days} Tagen** ({pd.Timestamp(earnings):%d.%m.}) – "
                        "erhöhtes Risiko für Kurssprünge.")

    # Marktumfeld
    if regime:
        if regime["verdict"] == "Gegenwind":
            cons.append("**Marktumfeld: Gegenwind.**")
        elif regime["verdict"] == "Rückenwind":
            pros.append("**Marktumfeld: Rückenwind.**")

    score = len(pros) - len(cons)
    if m["has_setup"] and m["uptrend"] and score >= 2:
        verdict, color = "Interessantes Setup", "green"
    elif m["has_warning"] or score <= -2:
        verdict, color = "Vorsicht", "red"
    else:
        verdict, color = "Beobachten", "orange"
    return verdict, color, pros, cons


def _picked() -> None:
    st.session_state["ticker"] = st.session_state["pick"]
    st.session_state["other"] = ""


def _typed() -> None:
    value = st.session_state["other"].strip().upper()
    if value:
        st.session_state["ticker"] = value


def ticker_picker(df: pd.DataFrame) -> str | None:
    options = df.sort_values("score", ascending=False) if "score" in df else df
    labels = {t: f"{t} – {n}" for t, n in zip(options["ticker"], options["name"])}
    tickers = list(labels)
    current = st.session_state.get("ticker") or (tickers[0] if tickers else None)
    if current and current not in labels:
        # frei eingegebener Ticker, der nicht im Scan ist
        tickers = [current] + tickers
        labels[current] = f"{current} (nicht im Scan)"
    st.session_state["ticker"] = current
    st.session_state["pick"] = current  # Auswahl immer passend zur angezeigten Aktie
    with st.sidebar:
        st.header("Aktie wählen")
        st.selectbox("Aktie aus dem Scan", tickers, key="pick", on_change=_picked,
                     format_func=lambda t: labels.get(t, t),
                     placeholder="Ticker oder Name eingeben")
        st.text_input("… oder beliebiger Yahoo-Ticker", key="other", on_change=_typed,
                      placeholder="z. B. SAP.DE, ^GDAXI")
    return current


def render() -> None:
    df = c.scan()
    if df.empty:
        st.error("Noch keine Scan-Ergebnisse vorhanden.")
        return
    ticker = ticker_picker(df)
    if not ticker:
        return
    row = df[df["ticker"] == ticker]
    row = row.iloc[0] if len(row) else None
    country = row["country"] if row is not None else ("DE" if ticker.endswith(".DE") else "US")

    with st.spinner(f"Recherchiere {ticker} …"):
        prices = c.price_history(ticker, "2y")
        info = c.company_info(ticker)
    if prices.empty or len(prices) < 30:
        st.error(f"Für {ticker} konnten keine (ausreichenden) Kurse geladen werden.")
        return

    m = c.signals.analyze(prices)
    bench_symbol, bench_name = BENCHMARK.get(country, BENCHMARK["US"])
    bench = c.price_history(bench_symbol, "1y")
    rel_3m = m["perf_3m"] - perf(bench, 63) if not bench.empty else float("nan")
    rs_rank = row["rs_rank"] if row is not None and "rs_rank" in row else float("nan")
    earnings = c.next_earnings(ticker)
    regime = c.live_regime() or c.stored_regime()
    currency = info.get("currency") or (row["currency"] if row is not None else "")

    # Kopf
    name = info.get("longName") or (row["name"] if row is not None else ticker)
    st.title(f"{ticker} · {name}")
    meta = " · ".join(x for x in [info.get("sector"), info.get("industry"),
                                  row["exchange"] if row is not None else None] if x)
    if meta:
        st.caption(meta)
    if m["signal_keys"]:
        st.markdown(c.signal_badges(m["signal_keys"]))

    k = st.columns(6)
    last = float(prices["Close"].iloc[-1])
    k[0].metric("Kurs", f"{c.fmt_num(last)} {currency}", c.fmt_pct(m["chg_1d"]))
    k[1].metric("1 Monat", c.fmt_pct(m["perf_1m"]))
    k[2].metric("3 Monate", c.fmt_pct(m["perf_3m"]))
    k[3].metric("1 Jahr", c.fmt_pct(m["perf_1y"]))
    k[4].metric("RSI (14)", c.fmt_num(m["rsi14"], 0))
    k[5].metric("Rel. Stärke", "–" if nan(rs_rank) else f"{rs_rank:.0f}/100")

    left, right = st.columns([2, 1])
    with left:
        months = st.segmented_control("Zeitraum", [3, 6, 12, 24], default=12,
                                      format_func=lambda x: f"{x} Mon.",
                                      label_visibility="collapsed", key="chart_months") or 12
        st.plotly_chart(c.price_chart(prices, months, stop=m["stop"]), use_container_width=True)

    with right:
        verdict, color, pros, cons = assessment(m, rs_rank, rel_3m, bench_name, earnings, regime)
        st.markdown(f"### :{color}[{verdict}]")
        st.caption("Automatische Einschätzung aus Trend, Momentum, Stärke, Volumen und Terminen")
        if pros:
            st.markdown("**Spricht dafür**")
            st.markdown("\n".join(f"- ✅ {p}" for p in pros))
        if cons:
            st.markdown("**Spricht dagegen**")
            st.markdown("\n".join(f"- ⚠️ {p}" for p in cons))
        with st.container(border=True):
            st.markdown("**Risiko-Orientierung**")
            st.markdown(
                f"Stopp (2× ATR): **{c.fmt_num(m['stop'])} {currency}** "
                f"({c.fmt_pct(-m['risk_pct'])})  \n"
                f"10-Tage-Tief: {c.fmt_num(m['low_10d'])} · SMA50: {c.fmt_num(m['sma50'])} · "
                f"SMA200: {c.fmt_num(m['sma200'])}  \n"
                f"52W-Hoch: {c.fmt_num(m['high_52w'])} · 52W-Tief: {c.fmt_num(m['low_52w'])}"
            )
            risk_eur = st.number_input("Wie viel darf der Trade maximal kosten? "
                                       f"({currency})", min_value=0.0, value=100.0, step=50.0)
            per_share = last - m["stop"] if not nan(m["stop"]) else float("nan")
            if not nan(per_share) and per_share > 0:
                shares = int(risk_eur // per_share)
                st.markdown(f"→ **{shares} Stück** (≈ {c.fmt_num(shares * last, 0)} {currency} "
                            "Einsatz) bis zum Stopp")

    st.divider()
    a, b = st.columns(2)
    with a:
        st.subheader("🏢 Unternehmen")
        f = st.columns(3)
        f[0].metric("Marktwert", c.fmt_big(info.get("marketCap")))
        f[1].metric("KGV", c.fmt_num(info.get("trailingPE"), 1))
        f[2].metric("KGV erw.", c.fmt_num(info.get("forwardPE"), 1))
        g = st.columns(3)
        dy = info.get("dividendYield")
        g[0].metric("Dividende", "–" if not dy else c.fmt_num(dy, 2, " %"))
        if earnings and pd.Timestamp(earnings).date() >= date.today():
            g[1].metric("Nächste Zahlen", f"{pd.Timestamp(earnings):%d.%m.%Y}")
        elif earnings:
            g[1].metric("Letzte Zahlen", f"{pd.Timestamp(earnings):%d.%m.%Y}")
        else:
            g[1].metric("Nächste Zahlen", "–")
        g[2].metric("Beta", c.fmt_num(info.get("beta"), 2))
        if info.get("targetMeanPrice"):
            upside = (info["targetMeanPrice"] / last - 1) * 100
            st.markdown(
                f"**Analysten:** {RECOMMENDATION.get(info.get('recommendationKey') or 'none', '–')} "
                f"· Kursziel Ø {c.fmt_num(info['targetMeanPrice'])} {currency} "
                f"({c.fmt_pct(upside)}) · {info.get('numberOfAnalystOpinions') or '–'} Analysten")
        if info.get("longBusinessSummary"):
            with st.expander("Geschäftsmodell"):
                st.write(info["longBusinessSummary"])
    with b:
        st.subheader("📰 Nachrichten")
        items = c.news(ticker)
        if not items:
            st.caption("Gerade keine Nachrichten verfügbar.")
        for it in items:
            when = c.berlin(it["date"]) if it.get("date") else ""
            st.markdown(f"[{it['title']}]({it['url']})  \n"
                        f"<span style='opacity:0.6;font-size:0.8rem'>{it['provider']} · "
                        f"{when}</span>", unsafe_allow_html=True)
    st.caption(c.DISCLAIMER)
