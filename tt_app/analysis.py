"""Seite "Aktienanalyse": geführte Prüfung einer einzelnen Aktie.

Aufbau
  Auf einen Blick        Gesamteinschätzung in einem Satz
  4 Prüfschritte         Markt · Trend · Stärke · Zeitpunkt (Ampel + Erklärung)
  Kursverlauf            Chart mit Ausstieg und Ziel, verständliche Legende
  Dein möglicher Plan    Einstieg, Ausstieg, Ziel, Chance/Risiko + Euro-Rechner
  Im Blick behalten      Termine, Hinweise, Nachrichten
  Das Unternehmen        Kennzahlen mit Erklärung
"""

from __future__ import annotations

import json
import math
from datetime import date

import pandas as pd
import streamlit as st

from tt_app import ai
from tt_app import common as c
from tt_app import explain as x
from tt_app import sectors, storage
from tt_app import style as s

BENCHMARK = {"US": ("^GSPC", "S&P 500"), "DE": ("^GDAXI", "DAX")}
RECOMMENDATION = {"strong_buy": "Starker Kauf", "buy": "Kaufen", "hold": "Halten",
                  "underperform": "Untergewichten", "sell": "Verkaufen",
                  "strong_sell": "Starker Verkauf", "none": "–"}
TONE_COLOR = {"up": s.UP, "warn": s.WARN, "down": s.DOWN, "muted": s.MUTED}
TONE_BG = {"up": "rgba(38,208,124,.14)", "warn": "rgba(245,165,36,.12)",
           "down": "rgba(240,80,110,.14)", "muted": "rgba(139,149,167,.1)"}


def nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def perf(df: pd.DataFrame, days: int) -> float:
    if len(df) <= days:
        return float("nan")
    return (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-days - 1]) - 1) * 100


# --------------------------------------------------------------------------- #
# Auswahl der Aktie
# --------------------------------------------------------------------------- #
def _picked() -> None:
    st.session_state["ticker"] = st.session_state["pick"]
    st.session_state["other"] = ""


def _from_url() -> None:
    """Ticker aus dem Link übernehmen (z. B. von einer Ideen-Karte: ?ticker=SAP.DE)."""
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
        tickers = [current] + tickers
        labels[current] = f"{current} (nicht im Scan)"
    st.session_state["ticker"] = current
    st.session_state["pick"] = current
    with st.sidebar:
        st.header("Aktie wählen")
        st.selectbox("Aus den geprüften Aktien", tickers, key="pick", on_change=_picked,
                     format_func=lambda t: labels.get(t, t),
                     placeholder="Name oder Kürzel eintippen")
        st.text_input("… oder beliebiges Kürzel", key="other", on_change=_typed,
                      placeholder="z. B. SAP.DE, AAPL",
                      help="Kürzel wie bei Yahoo Finance. Deutsche Aktien enden auf .DE")
    return current


# --------------------------------------------------------------------------- #
# Bausteine
# --------------------------------------------------------------------------- #
def step_tile(n: int, title: str, check: tuple[str, str, str]) -> str:
    tone, head, text = check
    return (f'<div class="tt-step" style="--c:{TONE_COLOR[tone]}">'
            f'<div class="tt-n">Schritt {n} · {s.esc(title)}</div>'
            f'<div class="tt-h">{s.esc(head)}</div>'
            f'<div class="tt-p">{s.esc(text)}</div></div>')


def market_check(regime: dict | None) -> tuple[str, str, str]:
    if not regime:
        return ("muted", "Keine Daten", "")
    v = regime["verdict"]
    return {
        "Rückenwind": ("up", "Gutes Börsenwetter",
                       "Der Gesamtmarkt läuft gut – das hilft fast allen Aktien."),
        "neutral": ("warn", "Gemischtes Börsenwetter",
                    "Der Gesamtmarkt ist unentschlossen. Nur die besten Ideen haben Rückenwind."),
        "Gegenwind": ("down", "Schwieriges Börsenwetter",
                      "Der Gesamtmarkt fällt. Auch gute Aktien werden dann oft mit nach unten gezogen."),
    }.get(v, ("muted", v, ""))


def plan_box(m: dict, last: float, currency: str) -> str:
    risk_amt = last - m["stop"]
    reward_amt = m["target"] - last
    rr = m["reward_risk"]
    total = (risk_amt + reward_amt) or 1
    risk_w, reward_w = risk_amt / total * 100, reward_amt / total * 100
    cur = s.esc(currency)
    return (
        f'<div class="tt-planbox">'
        f'<div class="tt-planrow"><div><div class="tt-l">1. Kurs jetzt</div>'
        f'<div class="tt-d">Zu diesem Preis könntest du ungefähr einsteigen.</div></div>'
        f'<div class="tt-r">{c.fmt_num(last)} {cur}</div></div>'
        f'<div class="tt-planrow"><div><div class="tt-l down-t">2. Ausstieg, falls die Idee falsch ist</div>'
        f'<div class="tt-d">Fällt der Kurs unter diese Marke, hat sich die Idee nicht bestätigt. '
        f'Dann verkaufen – so bleibt der Verlust klein. Lege die Marke vorher fest und halte dich daran.</div></div>'
        f'<div class="tt-r down-t">{c.fmt_num(m["stop"])} {cur}<br>'
        f'<span style="font-size:.8rem">{c.fmt_pct(-m["risk_pct"])}</span></div></div>'
        f'<div class="tt-planrow"><div><div class="tt-l up-t">3. Mögliches Ziel</div>'
        f'<div class="tt-d">Ein realistisches erstes Ziel – meist das Jahreshoch. Dort kann man '
        f'Gewinne mitnehmen oder die Ausstiegsmarke nachziehen.</div></div>'
        f'<div class="tt-r up-t">{c.fmt_num(m["target"])} {cur}<br>'
        f'<span style="font-size:.8rem">{c.fmt_pct(m["target_pct"])}</span></div></div>'
        f'<div class="tt-planrow" style="display:block"><div class="tt-row" '
        f'style="display:flex;justify-content:space-between"><div class="tt-l">4. Lohnt sich das?</div>'
        f'<div class="tt-r">{c.fmt_num(rr, 1)} : 1</div></div>'
        f'<div class="tt-rr"><span style="width:{risk_w:.0f}%;background:{s.DOWN}"></span>'
        f'<span style="width:{reward_w:.0f}%;background:{s.UP}"></span></div>'
        f'<div class="tt-d">Rot = was du riskierst, grün = was möglich ist. '
        + ("Die Chance ist deutlich größer als das Risiko – so sollte es sein."
           if not nan(rr) and rr >= 2 else
           "Die Chance ist nur etwas größer als das Risiko – eher mittelmäßig."
           if not nan(rr) and rr >= 1.5 else
           "Die Chance ist kaum größer als das Risiko – das lohnt sich eher nicht.")
        + "</div></div></div>"
    )


def company_tiles(info: dict, last: float, earnings) -> str:
    dy = info.get("dividendYield")
    if earnings and pd.Timestamp(earnings).date() >= date.today():
        earn = s.tile("Nächste Quartalszahlen", f"{pd.Timestamp(earnings):%d.%m.%Y}",
                      "an solchen Tagen springt der Kurs oft")
    elif earnings:
        earn = s.tile("Letzte Quartalszahlen", f"{pd.Timestamp(earnings):%d.%m.%Y}")
    else:
        earn = s.tile("Quartalszahlen", "–")
    pe = info.get("trailingPE")
    pe_hint = ("eher günstig" if pe and pe < 15 else "normal" if pe and pe < 30
               else "teuer – Anleger erwarten viel" if pe else "kein Gewinn / keine Daten")
    beta = info.get("beta")
    beta_hint = ("schwankt weniger als der Markt" if beta and beta < 0.9
                 else "schwankt etwa wie der Markt" if beta and beta < 1.3
                 else "schwankt stärker als der Markt" if beta else "")
    tiles = [
        s.tile("Firmenwert an der Börse", c.fmt_big(info.get("marketCap"))),
        s.tile("Bewertung (KGV)", c.fmt_num(pe, 1), pe_hint),
        s.tile("Dividende pro Jahr", "–" if not dy else c.fmt_num(dy, 2, " %"),
               "Ausschüttung im Verhältnis zum Kurs"),
        earn,
        s.tile("Schwankung ggü. Markt", c.fmt_num(beta, 2), beta_hint),
    ]
    if info.get("targetMeanPrice"):
        upside = (info["targetMeanPrice"] / last - 1) * 100
        rec = RECOMMENDATION.get(info.get("recommendationKey") or "none", "–")
        tiles.append(s.tile("Kursziel der Analysten",
                            f'<span class="{s.tone(upside)}-t">{c.fmt_pct(upside)}</span>',
                            f'Ø {c.fmt_num(info["targetMeanPrice"])} · Urteil: {rec} · '
                            f'{info.get("numberOfAnalystOpinions") or "–"} Analysten'))
    return f'<div class="tt-grid c3">{"".join(tiles)}</div>'


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
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

    with st.spinner(f"Prüfe {ticker} …"):
        prices = c.price_history(ticker, "2y")
        info = c.company_info(ticker)
    if prices.empty or len(prices) < 30:
        st.error(f"Für {ticker} konnten keine (ausreichenden) Kurse geladen werden. "
                 "Stimmt das Kürzel? Deutsche Aktien enden auf .DE (z. B. SAP.DE).")
        return

    m = c.signals.analyze(prices)
    bench_symbol, bench_name = BENCHMARK.get(country, BENCHMARK["US"])
    bench = c.price_history(bench_symbol, "1y")
    rel_3m = m["perf_3m"] - perf(bench, 63) if not bench.empty else float("nan")
    rs_rank = float(row["rs_rank"]) if row is not None and "rs_rank" in row else float("nan")
    earnings = c.next_earnings(ticker)
    regime = c.live_regime() or c.stored_regime()
    currency = info.get("currency") or (row["currency"] if row is not None else "")
    last = float(prices["Close"].iloc[-1])

    # ---- Kopf --------------------------------------------------------------
    name = info.get("longName") or (row["name"] if row is not None else ticker)
    meta = [v for v in [info.get("sector"), info.get("industry"),
                        row["exchange"] if row is not None else None] if v]
    s.page_head(f'{s.esc(ticker)} <span class="muted-t" style="font-weight:600">· {s.esc(name)}</span>')
    s.html_block(
        f'<div class="tt-quote"><div class="tt-price">{c.fmt_num(last)} '
        f'<span class="muted-t" style="font-size:1rem;font-weight:600">{s.esc(currency)}</span></div>'
        f'<div class="tt-chg {s.tone(m["chg_1d"])}-t">{c.fmt_pct(m["chg_1d"])} heute</div>'
        f'<div>{"".join(s.pill(v, "muted") for v in meta)}{c.signal_pills(m["signal_keys"])}</div></div>')

    # ---- Merken / Übungstrade ------------------------------------------------
    settings = storage.get()["settings"]
    default_loss = float(settings["depot_size"]) * float(settings["risk_pct"]) / 100
    per_share_risk = last - m["stop"] if not nan(m["stop"]) else float("nan")
    b1, b2, _ = st.columns([1, 1, 3])
    if storage.on_watchlist(ticker):
        if b1.button("✓ Auf der Merkliste", width="stretch", help="Klicken zum Entfernen"):
            storage.remove_watch(ticker)
            st.rerun()
    elif b1.button("⭐ Merken", width="stretch", help="Auf die Merkliste setzen"):
        storage.add_watch(ticker, name, last)
        st.toast(f"{ticker} ist jetzt auf deiner Merkliste.", icon="⭐")
        st.rerun()
    if b2.button("🛒 Im Übungsdepot handeln", width="stretch",
                 help="Mit Spielgeld kaufen – Ausstieg und Ziel aus dieser Analyse werden übernommen."):
        st.session_state["trade_ticker"] = ticker
        st.session_state["trade_side"] = "Kaufen"
        st.session_state["trade_plan"] = {"stop": None if nan(m["stop"]) else m["stop"],
                                          "target": None if nan(m["target"]) else m["target"],
                                          "idea": m["signals"]}
        st.session_state["_goto_view"] = "🛒 Handeln"
        st.switch_page(c.PAGES["trading"])

    # ---- Auf einen Blick + 4 Schritte ---------------------------------------
    checks = [
        market_check(regime),
        x.trend_check(m),
        x.strength_check(rs_rank, rel_3m, bench_name),
        x.timing_check(m),
    ]
    tone, head, text = x.overall(checks[1:], regime["verdict"] if regime else None)
    s.html_block(
        f'<div class="tt-summary" style="--vbg:{TONE_BG[tone]}">'
        f'<div class="tt-label muted-t" style="font-size:.75rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.08em">Auf einen Blick</div>'
        f'<div class="tt-vt" style="color:{TONE_COLOR[tone]}">{s.esc(head)}</div>'
        f'<div class="tt-text">{s.esc(text)}</div></div>')
    if row is not None and str(row.get("signal_keys", "")) and not m["has_setup"] \
            and bool(row.get("has_setup", False)):
        st.info(f"Hinweis: Im letzten Scan ({c.berlin(c.stored_regime().get('generated_at', ''))}) "
                f"fiel die Aktie als Idee auf („{row['signals']}“). Mit den aktuellen Kursen von "
                "heute ist das Muster gerade nicht mehr erfüllt – die Lage hat sich verändert.")
    titles = ["Wie läuft der Gesamtmarkt?", "Wohin geht der Trend?", "Ist die Aktie stark?",
              "Ist jetzt ein guter Moment?"]
    s.html_block('<div class="tt-steps">' + "".join(
        step_tile(i + 1, t, ch) for i, (t, ch) in enumerate(zip(titles, checks))) + "</div>")

    # ---- KI-Zusammenfassung ------------------------------------------------
    with st.expander("🤖 KI-Zusammenfassung: Was ist bei dieser Aktie los?"):
        if not ai.available():
            st.caption("Noch nicht eingerichtet: Dafür wird ein Anthropic-API-Schlüssel in den "
                       "Streamlit-Secrets gebraucht (siehe Lern-Ecke → Einrichtung).")
        else:
            key = f"ai_{ticker}"
            if st.button("Zusammenfassung erstellen (kostet ein paar Cent)", key=f"btn_{key}"):
                with st.spinner("Die KI liest Daten und Nachrichten …"):
                    st.session_state[key] = ai.summarize(
                        ticker, ai.facts(name, info, m, checks, head, currency, last),
                        json.dumps(c.news(ticker), ensure_ascii=False, default=str))
            if st.session_state.get(key):
                st.markdown(st.session_state[key])
                st.caption("Erstellt von Claude (Anthropic) aus den Daten dieser Seite. KI kann sich "
                           "irren – wichtige Punkte bitte selbst prüfen.")

    # ---- Kursverlauf -------------------------------------------------------
    s.section("📈 Kursverlauf")
    months = st.segmented_control("Zeitraum", [3, 6, 12, 24], default=12,
                                  format_func=lambda v: f"{v} Monate",
                                  label_visibility="collapsed", key="chart_months") or 12
    st.plotly_chart(c.price_chart(prices, months, stop=m["stop"], target=m["target"], height=520), config={"displayModeBar": False})
    st.caption("So liest du den Chart: Jede Kerze ist ein Tag – grün = Kurs gestiegen, rot = gefallen. "
               "Blaue Linie = Durchschnitt der letzten 50 Tage, orange = der letzten 200 Tage. Liegt der "
               "Kurs über beiden Linien, ist die Aktie im Aufwärtstrend. Rot gestrichelt = Ausstieg, "
               "grün gestrichelt = mögliches Ziel. Unten: wie viel gehandelt wurde.")

    # ---- Dein möglicher Plan -----------------------------------------------
    s.section("🧭 Dein möglicher Plan")
    risk_tone, risk_head, risk_text = x.risk_check(m)
    left, right = st.columns([3, 2], gap="large")
    with left:
        if nan(m["stop"]) or nan(m["target"]):
            st.info("Für diese Aktie lässt sich kein Plan berechnen (zu wenig Kursdaten).")
        else:
            s.html_block(plan_box(m, last, currency))
    with right:
        s.html_block(step_tile(5, "Wie riskant ist die Aktie?", (risk_tone, risk_head, risk_text)))
        with st.container(border=True):
            st.markdown("**Wie viel kann ich kaufen?**")
            loss = st.number_input(
                f"Wie viel Geld ({currency}) wärst du bereit zu verlieren, falls die Idee nicht aufgeht?",
                min_value=0.0, value=float(round(default_loss)), step=50.0,
                help="Faustregel: pro Idee höchstens 1–2 % deines gesamten Börsengelds riskieren.")
            per_share = last - m["stop"] if not nan(m["stop"]) else float("nan")
            if not nan(per_share) and per_share > 0 and loss > 0:
                shares = int(loss // per_share)
                if shares == 0:
                    st.warning(f"Eine einzige Aktie hätte schon ein Risiko von {c.fmt_num(per_share)} "
                               f"{currency}. Erhöhe den Betrag oder wähle eine andere Idee.")
                else:
                    invest = shares * last
                    worst = shares * per_share
                    best = shares * (m["target"] - last)
                    s.html_block(
                        f'<div class="tt-explain">Du könntest <b>{shares} Aktien</b> kaufen – '
                        f'das kostet etwa <b>{c.fmt_num(invest, 0)} {s.esc(currency)}</b>.<br>'
                        f'<span class="down-t">Schlechter Fall:</span> Der Kurs fällt auf die '
                        f'Ausstiegsmarke, du verkaufst und verlierst etwa '
                        f'<b class="down-t">{c.fmt_num(worst, 0)} {s.esc(currency)}</b>.<br>'
                        f'<span class="up-t">Guter Fall:</span> Der Kurs erreicht das Ziel, du gewinnst '
                        f'etwa <b class="up-t">{c.fmt_num(best, 0)} {s.esc(currency)}</b>.</div>')
            st.caption("Gebühren und Kurslücken über Nacht sind nicht eingerechnet.")

    # ---- Im Blick behalten -------------------------------------------------
    a, b = st.columns([1, 1], gap="large")
    with a:
        s.section("👀 Im Blick behalten")
        notes = []
        if earnings:
            days = (pd.Timestamp(earnings).date() - date.today()).days
            if 0 <= days <= 21:
                notes.append(("down", f"In {days} Tagen ({pd.Timestamp(earnings):%d.%m.}) legt das "
                                      "Unternehmen Quartalszahlen vor. Dann springt der Kurs oft stark – "
                                      "in beide Richtungen."))
        sec = sectors.sector_for(info.get("sector"))
        if sec:
            label, tone_ = sectors.sector_verdict(sec)
            notes.append(({"up": "up", "down": "down"}.get(tone_, "warn"),
                          f"Die Branche ({sec['name']}) {label}: {c.fmt_pct(sec['m3'])} in 3 Monaten, "
                          f"{'besser' if sec['vs_market'] > 0 else 'schlechter'} als der Gesamtmarkt."))
        story = x.idea_story({**m, "rs_rank": rs_rank, "currency": currency, "chg_1d": m["chg_1d"]})
        notes += [("warn", w) for w in story["watch"]]
        notes += [("down", w) for w in story["caution"]]
        if not notes:
            notes.append(("warn", "Gerade gibt es keinen besonderen Anlass. Beobachten, ob sich ein "
                                  "Rücksetzer oder ein Ausbruch ergibt."))
        icons = {"up": "✓", "warn": "👀", "down": "!"}
        cls = {"up": "pro", "warn": "mid", "down": "con"}
        s.html_block('<ul class="tt-list">' + "".join(
            f'<li class="{cls[t]}"><span class="tt-ic">{icons[t]}</span><span>{s.esc(n)}</span></li>'
            for t, n in notes) + "</ul>")
        s.section("📰 Aktuelle Nachrichten")
        items = c.news(ticker)
        if not items:
            st.caption("Gerade keine Nachrichten verfügbar.")
        else:
            s.html_block('<div class="tt-news">' + "".join(
                f'<div class="tt-item"><a href="{s.esc(it["url"])}" target="_blank" rel="noopener">'
                f'{s.esc(it["title"])}</a><div class="tt-meta">{s.esc(it["provider"])} · '
                f'{s.esc(c.berlin(it["date"]) if it.get("date") else "")}</div></div>'
                for it in items) + "</div>")
    with b:
        s.section("🏢 Das Unternehmen")
        s.html_block(company_tiles(info, last, earnings))
        if info.get("longBusinessSummary"):
            with st.expander("Was macht das Unternehmen?"):
                st.write(info["longBusinessSummary"])

    s.html_block(f'<div class="tt-disclaimer">{s.esc(c.DISCLAIMER)}</div>')
