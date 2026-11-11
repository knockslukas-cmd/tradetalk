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
from tt_app import style as s

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


def _from_url() -> None:
    """Ticker aus dem Link übernehmen (z. B. von einer Setup-Karte: ?ticker=SAP.DE)."""
    qp = st.query_params.get("ticker")
    if qp and qp != st.session_state.get("_qp_seen"):
        st.session_state["ticker"] = qp.upper()
        st.session_state["_qp_seen"] = qp


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




def verdict_box(verdict: str, color: str, pros: list[str], cons: list[str]) -> str:
    css = {"green": (s.UP, "rgba(38,208,124,.14)"), "orange": (s.WARN, "rgba(245,165,36,.12)"),
           "red": (s.DOWN, "rgba(240,80,110,.14)")}
    fg, bg = css.get(color, (s.MUTED, "rgba(139,149,167,.1)"))

    def md(text: str) -> str:
        # **fett** -> <b>fett</b>
        parts = s.esc(text).split("**")
        return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))

    items = "".join(f'<li class="pro"><span class="tt-ic">✓</span><span>{md(p)}</span></li>'
                    for p in pros)
    items += "".join(f'<li class="con"><span class="tt-ic">!</span><span>{md(p)}</span></li>'
                     for p in cons)
    return (f'<div class="tt-verdict-box" style="--vbg:{bg}">'
            f'<div class="tt-k muted-t" style="font-size:.75rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:.08em">Automatische Einschätzung</div>'
            f'<div class="tt-vt" style="color:{fg}">{s.esc(verdict)}</div>'
            f'<ul class="tt-list">{items}</ul></div>')


def render() -> None:
    df = c.scan()
    if df.empty:
        st.error("Noch keine Scan-Ergebnisse vorhanden.")
        return
    _from_url()
    ticker = ticker_picker(df)
    if not ticker:
        return
    if st.query_params.get("ticker") != ticker:
        st.query_params["ticker"] = ticker
        st.session_state["_qp_seen"] = ticker
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
    last = float(prices["Close"].iloc[-1])

    # Kopf
    name = info.get("longName") or (row["name"] if row is not None else ticker)
    meta = [x for x in [info.get("sector"), info.get("industry"),
                        row["exchange"] if row is not None else None] if x]
    s.page_head(f'{s.esc(ticker)} <span class="muted-t" style="font-weight:600">· '
                f'{s.esc(name)}</span>')
    s.html_block(
        f'<div class="tt-quote"><div class="tt-price">{c.fmt_num(last)} '
        f'<span class="muted-t" style="font-size:1rem;font-weight:600">{s.esc(currency)}</span></div>'
        f'<div class="tt-chg {s.tone(m["chg_1d"])}-t">{c.fmt_pct(m["chg_1d"])} heute</div>'
        f'<div>{"".join(s.pill(x, "muted") for x in meta)}{c.signal_pills(m["signal_keys"])}</div></div>'
    )

    def kpi(label: str, value, fmt="pct") -> str:
        txt = c.fmt_pct(value) if fmt == "pct" else value
        cls = s.tone(value) if fmt == "pct" else ""
        return s.tile(label, f'<span class="{cls}-t">{txt}</span>' if cls else txt)

    rsi_v = m["rsi14"]
    rsi_cls = "down" if not nan(rsi_v) and rsi_v >= 75 else "up" if not nan(rsi_v) and rsi_v <= 30 else ""
    s.html_block('<div class="tt-grid c6">' + "".join([
        kpi("1 Woche", m["perf_1w"]), kpi("1 Monat", m["perf_1m"]), kpi("3 Monate", m["perf_3m"]),
        kpi("1 Jahr", m["perf_1y"]),
        s.tile("RSI (14)", f'<span class="{rsi_cls}-t">{c.fmt_num(rsi_v, 0)}</span>'),
        s.tile("Rel. Stärke", "–" if nan(rs_rank) else f"{rs_rank:.0f}<span class='muted-t' "
               f"style='font-size:.9rem'>/100</span>",
               extra="" if nan(rs_rank) else s.bar([(rs_rank, s.ACCENT)])),
    ]) + "</div>")

    left, right = st.columns([2, 1], gap="large")
    with left:
        months = st.segmented_control("Zeitraum", [3, 6, 12, 24], default=12,
                                      format_func=lambda x: f"{x} Monate",
                                      label_visibility="collapsed", key="chart_months") or 12
        st.plotly_chart(c.price_chart(prices, months, stop=m["stop"]), use_container_width=True,
                        config={"displayModeBar": False})

    with right:
        verdict, color, pros, cons = assessment(m, rs_rank, rel_3m, bench_name, earnings, regime)
        s.html_block(verdict_box(verdict, color, pros, cons))

    # Risiko & Positionsgröße
    s.section("🛡️ Risiko & Positionsgröße")
    r1, r2 = st.columns([2, 1], gap="large")
    with r1:
        s.html_block('<div class="tt-grid c4">' + "".join([
            s.tile("Stopp (2× ATR)", f'<span class="down-t">{c.fmt_num(m["stop"])}</span>',
                   f'{c.fmt_pct(-m["risk_pct"])} vom Kurs'),
            s.tile("10-Tage-Tief", c.fmt_num(m["low_10d"]), "nächste Unterstützung"),
            s.tile("SMA50 / SMA200", f'{c.fmt_num(m["sma50"], 1)}',
                   f'SMA200 {c.fmt_num(m["sma200"], 1)}'),
            s.tile("52W-Hoch / -Tief", c.fmt_num(m["high_52w"], 1),
                   f'Tief {c.fmt_num(m["low_52w"], 1)} · {c.fmt_pct(m["dist_52w_high"])} vom Hoch'),
        ]) + "</div>")
    with r2:
        with st.container(border=True):
            risk_eur = st.number_input(f"Maximaler Verlust je Trade ({currency})", min_value=0.0,
                                       value=100.0, step=50.0)
            per_share = last - m["stop"] if not nan(m["stop"]) else float("nan")
            if not nan(per_share) and per_share > 0:
                shares = int(risk_eur // per_share)
                st.markdown(f"**{shares} Stück** · Einsatz ≈ {c.fmt_num(shares * last, 0)} {currency}")
                st.caption("Bis zum Stopp verlierst du höchstens den eingegebenen Betrag.")

    # Unternehmen & Nachrichten
    a, b = st.columns([1, 1], gap="large")
    with a:
        s.section("🏢 Unternehmen")
        dy = info.get("dividendYield")
        if earnings and pd.Timestamp(earnings).date() >= date.today():
            earn_label, earn_val = "Nächste Zahlen", f"{pd.Timestamp(earnings):%d.%m.%Y}"
        elif earnings:
            earn_label, earn_val = "Letzte Zahlen", f"{pd.Timestamp(earnings):%d.%m.%Y}"
        else:
            earn_label, earn_val = "Nächste Zahlen", "–"
        tiles = [
            s.tile("Marktwert", c.fmt_big(info.get("marketCap"))),
            s.tile("KGV / erw.", f'{c.fmt_num(info.get("trailingPE"), 1)} / '
                                f'{c.fmt_num(info.get("forwardPE"), 1)}'),
            s.tile("Dividende", "–" if not dy else c.fmt_num(dy, 2, " %")),
            s.tile(earn_label, earn_val),
            s.tile("Beta", c.fmt_num(info.get("beta"), 2), "Schwankung ggü. Markt"),
        ]
        if info.get("targetMeanPrice"):
            upside = (info["targetMeanPrice"] / last - 1) * 100
            rec = RECOMMENDATION.get(info.get("recommendationKey") or "none", "–")
            tiles.append(s.tile("Analysten", f'<span class="{s.tone(upside)}-t">{c.fmt_pct(upside)}</span>',
                                f'{rec} · Ziel {c.fmt_num(info["targetMeanPrice"])} · '
                                f'{info.get("numberOfAnalystOpinions") or "–"} Analysten'))
        s.html_block(f'<div class="tt-grid c3">{"".join(tiles)}</div>')
        if info.get("longBusinessSummary"):
            with st.expander("Geschäftsmodell"):
                st.write(info["longBusinessSummary"])
    with b:
        s.section("📰 Nachrichten")
        items = c.news(ticker)
        if not items:
            st.caption("Gerade keine Nachrichten verfügbar.")
        else:
            s.html_block('<div class="tt-news">' + "".join(
                f'<div class="tt-item"><a href="{s.esc(it["url"])}" target="_blank" '
                f'rel="noopener">{s.esc(it["title"])}</a><div class="tt-meta">'
                f'{s.esc(it["provider"])} · {s.esc(c.berlin(it["date"]) if it.get("date") else "")}'
                f'</div></div>' for it in items) + "</div>")
    s.html_block(f'<div class="tt-disclaimer">{s.esc(c.DISCLAIMER)}</div>')
