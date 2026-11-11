"""Seite "Übungstrading": Depot mit 50.000 € Spielgeld, Kaufen/Verkaufen mit Live-Kursen."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from tt_app import common as c
from tt_app import paper, storage
from tt_app import style as s

VIEWS = ["💼 Depot", "🛒 Handeln", "🧾 Aktivität", "🎯 Ideen-Check"]


def nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def eur(x, d: int = 2) -> str:
    return c.fmt_num(x, d) + " €"


def ago(ts) -> str:
    if ts is None:
        return "–"
    mins = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(ts)).total_seconds() / 60
    if mins < 2:
        return "gerade eben"
    if mins < 60:
        return f"vor {mins:.0f} Min."
    return c.berlin(pd.Timestamp(ts).isoformat())


def go_trade(ticker: str, side: str = "Kaufen") -> None:
    st.session_state["trade_ticker"] = ticker
    st.session_state["trade_side"] = side
    st.session_state["_goto_view"] = VIEWS[1]   # wird vor dem Bereichs-Umschalter angewendet


# --------------------------------------------------------------------------- #
# Depot
# --------------------------------------------------------------------------- #
@st.fragment(run_every=30)
def depot_live() -> None:
    p = paper.get()
    day_before = len(p.get("history", []))
    if paper.process():
        paper.save()
        st.toast("Eine Order wurde ausgeführt.", icon="✅")
    v = paper.valuation()
    paper.snapshot(v["total"])
    if len(p["history"]) != day_before:
        paper.save()

    hist = p.get("history", [])
    prev = hist[-2]["value"] if len(hist) >= 2 else p["start_cash"]
    today = v["total"] - prev
    color = s.UP if v["pnl_total"] >= 0 else s.DOWN
    s.html_block(
        f'<div class="tt-hero" style="--glow:{"rgba(38,208,124,.18)" if v["pnl_total"] >= 0 else "rgba(240,80,110,.18)"}">'
        f'<div class="tt-label">Übungsdepot · Spielgeld</div>'
        f'<div class="tt-verdict" style="font-size:2.8rem">{eur(v["total"])}</div>'
        f'<div style="font-size:1rem;font-weight:700;color:{color}">{c.fmt_pct(v["pnl_total_pct"], 2)} · '
        f'{"+" if v["pnl_total"] >= 0 else ""}{eur(v["pnl_total"])} seit Start</div>'
        f'<div class="tt-s muted-t" style="margin-top:.2rem">Heute: <span class="{s.tone(today)}-t">'
        f'{"+" if today >= 0 else ""}{eur(today)}</span> · Kurse aktualisieren sich alle 30 Sekunden</div></div>')

    if len(hist) >= 2:
        h = pd.DataFrame(hist)
        fig = go.Figure(go.Scatter(x=pd.to_datetime(h["date"]), y=h["value"], mode="lines",
                                   line=dict(color=color, width=2), fill="tozeroy",
                                   fillcolor="rgba(45,212,163,.08)"))
        fig.update_layout(height=180, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(gridcolor="#1a2130", side="right"),
                          xaxis=dict(showgrid=False))
        st.plotly_chart(fig, config={"displayModeBar": False})

    s.html_block('<div class="tt-grid c4" style="margin-top:.8rem">' + "".join([
        s.tile("Verfügbares Geld", eur(v["cash"] - v["reserved"]),
               f"reserviert für wartende Orders: {eur(v['reserved'])}" if v["reserved"] else "zum Kaufen"),
        s.tile("In Aktien", eur(v["invested"]), f"{len(v['positions'])} Positionen"),
        s.tile("Startkapital", eur(p["start_cash"]), f"seit {c.berlin(p['created'])[:10]}"),
        s.tile("Euro/Dollar", c.fmt_num(v["fx"], 4), "für US-Aktien"),
    ]) + "</div>")

    s.section("Deine Positionen", str(len(v["positions"])))
    if not v["positions"]:
        st.info("Noch keine Aktien im Depot. Wechsle zu **🛒 Handeln** oder öffne eine Trade-Idee im "
                "Dashboard und klicke dort auf **Im Übungsdepot handeln**.")
    for r in sorted(v["positions"], key=lambda r: -r["value_eur"]):
        cur = r["currency"]
        span = (r["target"] - r["stop"]) if r.get("stop") and r.get("target") else None
        bar = ""
        if span:
            pos = max(0, min(100, (r["price"] - r["stop"]) / span * 100))
            bar = (f'<div style="position:relative;margin:.6rem 0 .2rem"><div class="tt-bar" style="height:6px;'
                   f'background:linear-gradient(90deg,{s.DOWN},#222a38 50%,{s.UP})"></div>'
                   f'<div style="position:absolute;top:-4px;left:{pos:.0f}%;width:14px;height:14px;border-radius:50%;'
                   f'background:#fff;border:3px solid #0b0e14;transform:translateX(-50%)"></div></div>'
                   f'<div class="tt-scale-labels"><span class="down-t">Ausstieg {c.fmt_num(r["stop"])}</span>'
                   f'<span class="up-t">Ziel {c.fmt_num(r["target"])}</span></div>')
        col1, col2 = st.columns([5, 1], vertical_alignment="center")
        col1.markdown(
            f'<div class="tt-tile" style="padding:.85rem 1rem"><div class="tt-row"><div style="min-width:0">'
            f'<div style="font-weight:800;font-size:1.05rem">{s.esc(r["name"])} '
            f'<span class="muted-t" style="font-weight:500;font-size:.8rem">{s.esc(r["ticker"])}</span></div>'
            f'<div class="tt-s">{c.fmt_num(r["shares"], 4).rstrip("0").rstrip(",")} Stück · Ø Kauf '
            f'{c.fmt_num(r["avg_price"])} {cur} · jetzt {c.fmt_num(r["price"])} {cur} '
            f'<span class="muted-t">({ago(r["price_time"])})</span></div></div>'
            f'<div style="text-align:right"><div class="tt-v">{eur(r["value_eur"])}</div>'
            f'<div class="tt-s {s.tone(r["pnl_eur"])}-t">{c.fmt_pct(r["pnl_pct"])} · '
            f'{"+" if r["pnl_eur"] >= 0 else ""}{eur(r["pnl_eur"])}</div></div></div>{bar}</div>',
            unsafe_allow_html=True)
        with col2:
            if st.button("Handeln", key=f"trade_{r['ticker']}", width="stretch"):
                go_trade(r["ticker"], "Verkaufen")
                st.rerun(scope="app")

    pending = [o for o in p["orders"] if o["status"] == "pending"]
    if pending:
        s.section("Wartende Orders", str(len(pending)))
        for o in pending:
            col1, col2 = st.columns([5, 1], vertical_alignment="center")
            col1.markdown(
                f"**{'Kauf' if o['side'] == 'buy' else 'Verkauf'}** {o['shares']:g} × {o['name']} "
                f"({o['ticker']}) · wartet auf Öffnung der {paper.market_label(o['ticker'])} · "
                f"ca. {eur(o['estimate_eur'])}")
            if col2.button("Stornieren", key=f"cancel_{o['id']}", width="stretch"):
                paper.cancel_order(o["id"])
                st.rerun(scope="app")


def depot_view() -> None:
    depot_live()
    with st.expander("Depot zurücksetzen"):
        st.caption("Löscht alle Positionen und Orders und startet wieder mit 50.000 € Spielgeld.")
        if st.checkbox("Ja, ich möchte neu anfangen", key="reset_ok") and \
                st.button("Depot zurücksetzen", type="primary"):
            paper.reset()
            st.rerun()


# --------------------------------------------------------------------------- #
# Handeln
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=60, show_spinner=False)
def intraday(ticker: str) -> pd.DataFrame:
    try:
        d = yf.download(ticker, period="1d", interval="5m", progress=False, auto_adjust=False,
                        multi_level_index=False)
        return d.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


def mini_chart(ticker: str, span: str) -> None:
    if span == "Heute":
        df = intraday(ticker)
    else:
        df = c.price_history(ticker, "2y")
        months = {"1 Woche": 0.25, "1 Monat": 1, "6 Monate": 6, "1 Jahr": 12}[span]
        if len(df):
            df = df[df.index >= df.index[-1] - pd.Timedelta(days=int(months * 30.5))]
    if df.empty:
        st.caption("Kein Kursverlauf verfügbar (Börse heute noch nicht offen?).")
        return
    up = df["Close"].iloc[-1] >= df["Close"].iloc[0]
    color = s.UP if up else s.DOWN
    fig = go.Figure(go.Scatter(x=df.index, y=df["Close"], mode="lines", line=dict(color=color, width=2),
                               fill="tozeroy", fillcolor="rgba(38,208,124,.07)" if up else "rgba(240,80,110,.07)"))
    lo, hi = float(df["Close"].min()), float(df["Close"].max())
    fig.update_layout(height=240, margin=dict(l=0, r=0, t=6, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                      yaxis=dict(gridcolor="#1a2130", side="right", range=[lo * 0.995, hi * 1.005]),
                      xaxis=dict(showgrid=False))
    st.plotly_chart(fig, config={"displayModeBar": False})


def _pick() -> None:
    st.session_state["trade_ticker"] = st.session_state["trade_pick"]
    st.session_state.pop("trade_plan", None)


def _typed() -> None:
    t = st.session_state.get("trade_free", "").strip().upper()
    if t:
        st.session_state["trade_ticker"] = t
        st.session_state.pop("trade_plan", None)


def trade_view() -> None:
    p = paper.get()
    scan = c.scan()
    labels = {t: f"{t} – {n}" for t, n in zip(scan["ticker"], scan["name"])} if len(scan) else {}
    for t, pos in p["positions"].items():
        labels.setdefault(t, f"{t} – {pos['name']}")
    ticker = st.session_state.get("trade_ticker")
    if ticker and ticker not in labels:
        labels = {ticker: ticker, **labels}
    st.session_state["trade_pick"] = ticker
    a, b = st.columns([3, 1])
    a.selectbox("Aktie", list(labels), key="trade_pick", index=None, on_change=_pick,
                format_func=lambda t: labels.get(t, t), label_visibility="collapsed",
                placeholder="🔍 Aktie suchen – Name oder Kürzel")
    b.text_input("Kürzel", key="trade_free", on_change=_typed, label_visibility="collapsed",
                 placeholder="… oder Kürzel, z. B. TSLA")
    if not ticker:
        st.info("Wähle oben eine Aktie, die du kaufen oder verkaufen möchtest.")
        return

    q = paper.quotes((ticker,))
    if ticker not in q:
        st.error(f"Für {ticker} gibt es gerade keinen Kurs. Stimmt das Kürzel?")
        return
    fx = paper.fx_rate(q)
    price, qtime = q[ticker]["price"], q[ticker]["time"]
    cur = paper.currency_of(ticker)
    price_eur = paper.to_eur(price, ticker, fx)
    info = c.company_info(ticker)
    name = info.get("longName") or labels.get(ticker, ticker).split(" – ")[-1]
    is_open = paper.market_open(ticker)
    hist = c.price_history(ticker, "2y")
    chg = (price / float(hist["Close"].iloc[-2]) - 1) * 100 if len(hist) > 1 else float("nan")

    s.html_block(
        f'<div class="tt-quote" style="margin-top:.6rem"><div><div style="font-weight:800;font-size:1.3rem">'
        f'{s.esc(name)} <span class="muted-t" style="font-size:.9rem;font-weight:500">{s.esc(ticker)}</span></div>'
        f'<div class="tt-price">{c.fmt_num(price)} <span class="muted-t" style="font-size:1rem">{cur}</span></div></div>'
        f'<div class="tt-chg {s.tone(chg)}-t">{c.fmt_pct(chg)} heute</div>'
        f'<div>{s.pill(("🟢 " if is_open else "🔴 ") + paper.market_label(ticker) + (" geöffnet" if is_open else " geschlossen"), "up" if is_open else "down")}'
        f'{s.pill("Kurs " + ago(qtime), "muted")}'
        + (s.pill(f"≈ {eur(price_eur)}", "info") if cur != "EUR" else "") + "</div></div>")
    span = st.segmented_control("Zeitraum", ["Heute", "1 Woche", "1 Monat", "6 Monate", "1 Jahr"],
                                default="1 Monat", label_visibility="collapsed", key="trade_span") or "1 Monat"
    mini_chart(ticker, span)

    pos = p["positions"].get(ticker)
    left, right = st.columns([3, 2], gap="large")
    with left:
        if not st.session_state.get("trade_side"):
            st.session_state["trade_side"] = "Kaufen"
        side = st.segmented_control("Aktion", ["Kaufen", "Verkaufen"], key="trade_side") or "Kaufen"
        if side == "Verkaufen" and not pos:
            st.warning("Diese Aktie hast du nicht im Depot.")
            return
        mode = st.radio("Wie viel?", ["Betrag in €", "Stückzahl"], horizontal=True, key="trade_mode")
        available = p["cash"] - paper.reserved_cash(p)
        if mode == "Betrag in €":
            default_amt = float(min(1000.0, max(0.0, available - p["fee"]))) if side == "Kaufen" \
                else float(round(pos["shares"] * price_eur, 2))
            amount = st.number_input("Betrag (€)", min_value=0.0, value=default_amt, step=100.0, key="trade_amount")
            shares = round(max(0.0, amount - (p["fee"] if side == "Kaufen" else 0)) / price_eur, 4) if price_eur else 0
        else:
            max_sh = float(pos["shares"]) if side == "Verkaufen" else None
            shares = st.number_input("Stück", min_value=0.0, max_value=max_sh,
                                     value=float(pos["shares"]) if side == "Verkaufen" else 1.0,
                                     step=1.0, format="%.4f", key="trade_shares")
        if side == "Verkaufen" and pos:
            shares = min(shares, pos["shares"])

        stop = target = None
        idea = ""
        if side == "Kaufen":
            plan = st.session_state.get("trade_plan") or {}
            if not plan and len(hist) > 30:
                m = c.signals.analyze(hist)
                plan = {"stop": m["stop"], "target": m["target"], "idea": m["signals"]}
            auto = st.checkbox("Automatisch verkaufen bei Ausstieg oder Ziel (empfohlen)", value=True,
                               key="trade_auto",
                               help="Die App verkauft von selbst, wenn der Kurs die Ausstiegsmarke oder das "
                                    "Ziel erreicht – so wie ein Stop-Loss beim echten Broker.")
            if auto:
                c1, c2 = st.columns(2)
                stop = c1.number_input(f"Ausstieg, falls falsch ({cur})", min_value=0.0,
                                       value=float(round(plan.get("stop") or price * 0.92, 2)), step=0.1,
                                       key=f"trade_stop_{ticker}")
                target = c2.number_input(f"Ziel ({cur})", min_value=0.0,
                                         value=float(round(plan.get("target") or price * 1.16, 2)), step=0.1,
                                         key=f"trade_target_{ticker}")
            idea = plan.get("idea") or ""
            if idea:
                st.caption(f"Idee: {idea}")

    with right:
        value = shares * price_eur
        total = value + p["fee"] if side == "Kaufen" else value - p["fee"]
        risk = shares * paper.to_eur(price - stop, ticker, fx) + p["fee"] if stop else None
        chance = shares * paper.to_eur(target - price, ticker, fx) - p["fee"] if target else None
        rows = [("Stück", c.fmt_num(shares, 4).rstrip("0").rstrip(",")),
                ("Kurs", f"{c.fmt_num(price)} {cur}" + (f" ≈ {eur(price_eur)}" if cur != "EUR" else "")),
                ("Gebühr", eur(p["fee"])),
                ("Gesamt", f"<b>{eur(total)}</b>")]
        if side == "Kaufen":
            rows.append(("Verfügbar danach", eur(available - total)))
        if risk is not None and side == "Kaufen":
            rows.append(("Verlust am Ausstieg", f'<span class="down-t">−{eur(risk)}</span>'))
        if chance is not None and side == "Kaufen":
            rows.append(("Gewinn am Ziel", f'<span class="up-t">+{eur(chance)}</span>'))
        if side == "Verkaufen" and pos:
            pnl = value - p["fee"] - pos["cost_eur"] * shares / pos["shares"]
            rows.append(("Gewinn/Verlust", f'<span class="{s.tone(pnl)}-t">{"+" if pnl >= 0 else ""}{eur(pnl)}</span>'))
        s.html_block('<div class="tt-planbox">' + "".join(
            f'<div class="tt-planrow"><div class="tt-d" style="font-size:.88rem">{k}</div>'
            f'<div class="tt-r" style="font-size:1rem">{v}</div></div>' for k, v in rows) + "</div>")
        if not is_open:
            st.caption(f"Die {paper.market_label(ticker)} ist geschlossen – die Order wird zum ersten Kurs "
                       "nach der Öffnung ausgeführt. Der Preis kann dann abweichen.")
        label = "Kauf bestätigen" if side == "Kaufen" else "Verkauf bestätigen"
        if st.button(label, type="primary", width="stretch", disabled=shares <= 0,
                     key="trade_confirm"):
            ok, msg = paper.place_order("buy" if side == "Kaufen" else "sell", ticker, name, shares,
                                        price_eur, stop=stop, target=target, idea=idea)
            (st.success if ok else st.error)(msg)
            if ok:
                st.session_state.pop("trade_plan", None)
                st.toast(msg, icon="✅")
        if storage.status() != "gist":
            st.caption("⚠️ Speicher nicht eingerichtet – das Depot geht beim Schließen verloren.")


# --------------------------------------------------------------------------- #
# Aktivität und Ideen-Check
# --------------------------------------------------------------------------- #
def activity_view() -> None:
    orders = paper.get()["orders"]
    if not orders:
        st.info("Noch keine Orders.")
        return
    df = pd.DataFrame(orders).sort_values("created", ascending=False)
    df["Art"] = df["side"].map({"buy": "Kauf", "sell": "Verkauf"})
    df["Status"] = df["status"].map({"filled": "ausgeführt", "pending": "wartet", "cancelled": "storniert"})
    df["Zeit"] = df.apply(lambda r: c.berlin(r.get("filled") or r["created"]), axis=1)
    df["Betrag €"] = df.apply(lambda r: r["shares"] * r["price_eur"] if r.get("price_eur") == r.get("price_eur")
                              and r.get("price_eur") else None, axis=1)
    for col in ["price", "pnl_eur", "pnl_pct", "reason"]:
        if col not in df:
            df[col] = None
    st.dataframe(df[["Zeit", "Art", "name", "ticker", "shares", "price", "currency", "Betrag €", "pnl_eur",
                     "pnl_pct", "Status", "reason"]],
                 hide_index=True, width="stretch", column_config={
                     "name": st.column_config.TextColumn("Name", width="medium"),
                     "ticker": "Kürzel", "shares": st.column_config.NumberColumn("Stück", format="%.4f"),
                     "price": st.column_config.NumberColumn("Kurs", format="%.2f"), "currency": "Whg.",
                     "Betrag €": st.column_config.NumberColumn(format="%.2f"),
                     "pnl_eur": st.column_config.NumberColumn("Ergebnis €", format="%+.2f"),
                     "pnl_pct": st.column_config.NumberColumn("Ergebnis %", format="%+.1f"),
                     "reason": "Anlass"})


def ideas_view() -> None:
    st.markdown("Hier siehst du, wie deine **abgeschlossenen** Übungstrades gelaufen sind – getrennt nach "
                "der Idee, mit der du gekauft hast. So prüfst du im Alltag, ob die Ideen der App funktionieren.")
    ct = paper.closed_trades()
    if ct.empty:
        st.info("Noch keine abgeschlossenen Trades. Sobald du eine Position verkaufst (oder die App bei "
                "Ausstieg/Ziel automatisch verkauft), erscheint hier die Auswertung.")
        return
    ct["Art der Idee"] = ct["idea"].fillna("").map(lambda v: v.split(",")[0].strip() or "ohne Idee")
    wins = (ct["pnl_eur"] > 0).mean() * 100
    s.html_block('<div class="tt-grid c4">' + "".join([
        s.tile("Abgeschlossene Trades", str(len(ct))),
        s.tile("Mit Gewinn", c.fmt_num(wins, 0, " %")),
        s.tile("Ergebnis gesamt", f'<span class="{s.tone(ct["pnl_eur"].sum())}-t">{eur(ct["pnl_eur"].sum())}</span>'),
        s.tile("Ø pro Trade", c.fmt_pct(ct["pnl_pct"].mean())),
    ]) + "</div>")
    g = ct.groupby("Art der Idee").agg(Trades=("pnl_eur", "size"),
                                       Gewinnquote=("pnl_eur", lambda x: (x > 0).mean() * 100),
                                       Durchschnitt=("pnl_pct", "mean"), Summe=("pnl_eur", "sum")).reset_index()
    st.dataframe(g.sort_values("Summe", ascending=False), hide_index=True, width="stretch",
                 column_config={
                     "Gewinnquote": st.column_config.NumberColumn("mit Gewinn %", format="%.0f"),
                     "Durchschnitt": st.column_config.NumberColumn("Ø Ergebnis %", format="%+.1f"),
                     "Summe": st.column_config.NumberColumn("Summe €", format="%+.2f")})
    st.caption("Zum Vergleich: Im Rückblick der Erfolgskontrolle endeten rund 33 % der Ideen mit Gewinn. "
               "Nach 20–30 Trades kannst du einschätzen, ob du ähnlich oder besser liegst.")


def render() -> None:
    s.page_head('<span class="tt-logo">tradetalk</span> Übungstrading',
                "50.000 € Spielgeld · Live-Kurse · 1 € pro Order")
    if storage.status() != "gist":
        st.warning("Dein Übungsdepot wird noch nicht dauerhaft gespeichert (siehe Lern-Ecke → Einrichtung).",
                   icon="💾")
    if st.session_state.get("_goto_view"):
        st.session_state["trade_view"] = st.session_state.pop("_goto_view")
    if "trade_view" not in st.session_state:
        st.session_state["trade_view"] = VIEWS[1] if st.session_state.get("trade_ticker") else VIEWS[0]
    view = st.segmented_control("Bereich", VIEWS, key="trade_view", label_visibility="collapsed") or VIEWS[0]
    if view == VIEWS[0]:
        depot_view()
    elif view == VIEWS[1]:
        trade_view()
    elif view == VIEWS[2]:
        activity_view()
    else:
        ideas_view()
    s.html_block('<div class="tt-disclaimer">Übungsdepot mit Spielgeld – keine echten Orders. Kurse von Yahoo '
                 'Finance, teils verzögert. Feiertage werden nicht berücksichtigt.</div>')
