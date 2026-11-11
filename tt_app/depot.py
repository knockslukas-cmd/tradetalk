"""Seite "Mein Bereich": Merkliste, Übungsdepot und Einstellungen."""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from tt_app import common as c
from tt_app import storage
from tt_app import style as s


def nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def live_prices(tickers: list[str]) -> dict[str, float]:
    data = c.closes(tuple(sorted(set(tickers))), "5d") if tickers else {}
    return {t: v[-1] for t, v in data.items() if v}


def storage_banner() -> None:
    if storage.status() != "gist":
        err = st.session_state.get("_store_error")
        st.warning("**Achtung: Deine Merkliste und dein Übungsdepot werden noch nicht dauerhaft "
                   "gespeichert** – sie gehen beim Schließen der App verloren. "
                   "Wie du das einrichtest, steht unter **Einstellungen**."
                   + (f"  \nGrund: {err}" if err else ""), icon="💾")


# --------------------------------------------------------------------------- #
# Merkliste
# --------------------------------------------------------------------------- #
def watchlist_tab(scan: pd.DataFrame) -> None:
    items = storage.get()["watchlist"]
    if not items:
        st.info("Deine Merkliste ist leer. Öffne eine Aktie in der **Aktienanalyse** und klicke auf "
                "**⭐ Merken**, um sie hier zu beobachten.")
        return
    prices = live_prices([w["ticker"] for w in items])
    info = scan.set_index("ticker") if len(scan) else pd.DataFrame()
    rows = []
    for w in items:
        p = prices.get(w["ticker"], float("nan"))
        sc = info.loc[w["ticker"]] if w["ticker"] in info.index else None
        rows.append({
            "ticker": w["ticker"], "name": w["name"],
            "added": pd.Timestamp(w["added"]).tz_convert("Europe/Berlin").date(),
            "price_added": w["price_added"], "price": p,
            "since": (p / w["price_added"] - 1) * 100 if w["price_added"] and not nan(p) else None,
            "signals": sc["signals"] if sc is not None else "",
            "stars": int(sc["stars"]) if sc is not None and "stars" in sc and not nan(sc["stars"]) else 0,
        })
    df = pd.DataFrame(rows)
    st.caption(f"{len(df)} Aktien · Kurse live · Zeile anklicken für die Analyse")
    event = st.dataframe(
        df, hide_index=True, use_container_width=True, on_select="rerun",
        selection_mode="single-row", key="wl_table",
        column_config={
            "ticker": st.column_config.TextColumn("Kürzel"),
            "name": st.column_config.TextColumn("Name", width="medium"),
            "added": st.column_config.DateColumn("Gemerkt am", format="DD.MM.YYYY"),
            "price_added": st.column_config.NumberColumn("Kurs damals", format="%.2f"),
            "price": st.column_config.NumberColumn("Kurs jetzt", format="%.2f"),
            "since": st.column_config.NumberColumn("Seitdem %", format="%+.1f"),
            "signals": st.column_config.TextColumn("Was fällt heute auf?", width="medium"),
            "stars": st.column_config.NumberColumn("Sterne heute", format="%d ★"),
        })
    rows_sel = event.selection.rows if event and event.selection else []
    if rows_sel:
        c.open_analysis(df.iloc[rows_sel[0]]["ticker"])
    with st.expander("Aktie von der Merkliste entfernen"):
        t = st.selectbox("Aktie", [w["ticker"] for w in items], key="wl_remove")
        if st.button("Entfernen", key="wl_remove_btn"):
            storage.remove_watch(t)
            st.rerun()


# --------------------------------------------------------------------------- #
# Übungsdepot
# --------------------------------------------------------------------------- #
def trade_card(t: dict, price: float) -> str:
    cur = s.esc(t["currency"])
    pnl = (price - t["entry"]) * t["shares"] if not nan(price) else float("nan")
    pct = (price / t["entry"] - 1) * 100 if not nan(price) else float("nan")
    span = (t["target"] - t["stop"]) or 1
    pos = max(0, min(100, (price - t["stop"]) / span * 100)) if not nan(price) else 50
    entry_pos = max(0, min(100, (t["entry"] - t["stop"]) / span * 100))
    alert = ""
    if not nan(price) and price <= t["stop"]:
        alert = s.pill("Ausstiegsmarke erreicht – Idee gescheitert", "down")
    elif not nan(price) and price >= t["target"]:
        alert = s.pill("Ziel erreicht 🎉", "up")
    return (
        f'<div class="tt-tile" style="padding:1rem 1.1rem">'
        f'<div class="tt-row"><div><div class="tt-tk" style="font-weight:800;font-size:1.1rem">'
        f'{s.esc(t["ticker"])} <span class="muted-t" style="font-weight:500;font-size:.85rem">'
        f'{s.esc(t["name"])}</span></div>'
        f'<div class="tt-s">{t["shares"]} Stück · gekauft zu {c.fmt_num(t["entry"])} {cur} am '
        f'{pd.Timestamp(t["opened"]).tz_convert("Europe/Berlin"):%d.%m.%Y}</div></div>'
        f'<div style="text-align:right"><div class="tt-v {s.tone(pnl)}-t">{c.fmt_num(pnl, 0)} {cur}</div>'
        f'<div class="tt-s {s.tone(pct)}-t">{c.fmt_pct(pct)}</div></div></div>'
        f'<div style="position:relative;margin:.9rem 0 .3rem">'
        f'<div class="tt-bar" style="height:8px;background:linear-gradient(90deg,{s.DOWN},#222a38 '
        f'{entry_pos:.0f}%,{s.UP})"></div>'
        f'<div style="position:absolute;top:-4px;left:{pos:.0f}%;width:16px;height:16px;border-radius:50%;'
        f'background:#fff;border:3px solid #0b0e14;transform:translateX(-50%)"></div></div>'
        f'<div class="tt-scale-labels"><span class="down-t">Ausstieg {c.fmt_num(t["stop"])}</span>'
        f'<span>jetzt {c.fmt_num(price)}</span><span class="up-t">Ziel {c.fmt_num(t["target"])}</span></div>'
        f'<div style="margin-top:.5rem">{alert}</div></div>'
    )


def depot_tab() -> None:
    trades = storage.get()["trades"]
    open_t = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] == "closed"]
    prices = live_prices([t["ticker"] for t in open_t])

    st.markdown("Im **Übungsdepot** handelst du mit Spielgeld: Du eröffnest Trades aus der "
                "Aktienanalyse heraus und siehst, wie sie sich entwickeln – ganz ohne Risiko.")
    # Bilanz
    realized = sum((t["exit"] - t["entry"]) * t["shares"] for t in closed)
    unrealized = sum((prices.get(t["ticker"], t["entry"]) - t["entry"]) * t["shares"] for t in open_t)
    wins = sum(1 for t in closed if t["exit"] > t["entry"])
    quote = wins / len(closed) * 100 if closed else float("nan")
    s.html_block('<div class="tt-grid c4">' + "".join([
        s.tile("Offene Trades", str(len(open_t))),
        s.tile("Abgeschlossen", str(len(closed)),
               "" if not closed else f"{wins} mit Gewinn ({c.fmt_num(quote, 0)} %)"),
        s.tile("Ergebnis abgeschlossen", f'<span class="{s.tone(realized)}-t">{c.fmt_num(realized, 0)}</span>',
               "in Handelswährung"),
        s.tile("Ergebnis offen", f'<span class="{s.tone(unrealized)}-t">{c.fmt_num(unrealized, 0)}</span>',
               "Buchgewinn/-verlust jetzt"),
    ]) + "</div>")

    s.section("Offene Trades", str(len(open_t)))
    if not open_t:
        st.info("Noch keine offenen Übungstrades. Öffne eine Aktie in der **Aktienanalyse** und "
                "klicke dort auf **🧪 Übungstrade eröffnen**.")
    for t in open_t:
        price = prices.get(t["ticker"], float("nan"))
        col1, col2 = st.columns([4, 1], vertical_alignment="center")
        with col1:
            s.html_block(trade_card(t, price))
        with col2:
            reason = ("Ausstieg erreicht" if not nan(price) and price <= t["stop"]
                      else "Ziel erreicht" if not nan(price) and price >= t["target"] else "von Hand")
            if st.button("Verkaufen", key=f"close_{t['id']}", use_container_width=True,
                         disabled=nan(price), help="Zum aktuellen Kurs schließen"):
                storage.close_trade(t["id"], price, reason)
                st.rerun()
            if st.button("Analyse", key=f"an_{t['id']}", use_container_width=True):
                c.open_analysis(t["ticker"])

    if closed:
        s.section("Abgeschlossene Trades", str(len(closed)))
        df = pd.DataFrame([{
            "ticker": t["ticker"], "name": t["name"],
            "opened": pd.Timestamp(t["opened"]).tz_convert("Europe/Berlin").date(),
            "closed": pd.Timestamp(t["closed"]).tz_convert("Europe/Berlin").date(),
            "entry": t["entry"], "exit": t["exit"], "shares": t["shares"],
            "pnl": (t["exit"] - t["entry"]) * t["shares"],
            "pct": (t["exit"] / t["entry"] - 1) * 100, "reason": t["reason"],
        } for t in closed]).sort_values("closed", ascending=False)
        st.dataframe(df, hide_index=True, use_container_width=True, column_config={
            "ticker": "Kürzel", "name": st.column_config.TextColumn("Name", width="medium"),
            "opened": st.column_config.DateColumn("Gekauft", format="DD.MM.YYYY"),
            "closed": st.column_config.DateColumn("Verkauft", format="DD.MM.YYYY"),
            "entry": st.column_config.NumberColumn("Kauf", format="%.2f"),
            "exit": st.column_config.NumberColumn("Verkauf", format="%.2f"),
            "shares": st.column_config.NumberColumn("Stück"),
            "pnl": st.column_config.NumberColumn("Ergebnis", format="%+.0f"),
            "pct": st.column_config.NumberColumn("%", format="%+.1f"),
            "reason": st.column_config.TextColumn("Grund"),
        })
    with st.expander("Trade löschen (z. B. aus Versehen angelegt)"):
        if trades:
            labels = {t["id"]: f"{t['ticker']} · {t['shares']} Stück · {t['status']}" for t in trades}
            tid = st.selectbox("Trade", list(labels), format_func=labels.get, key="del_trade")
            if st.button("Endgültig löschen", key="del_trade_btn"):
                storage.delete_trade(tid)
                st.rerun()


# --------------------------------------------------------------------------- #
# Einstellungen
# --------------------------------------------------------------------------- #
def settings_tab() -> None:
    cfg = storage.get()["settings"]
    st.markdown("**Dein Börsengeld** – damit der Rechner in der Aktienanalyse passende Vorschläge macht.")
    col1, col2 = st.columns(2)
    depot = col1.number_input("Wie viel Geld hast du insgesamt für Aktien (Euro/Dollar)?",
                              min_value=0.0, value=float(cfg["depot_size"]), step=1000.0)
    risk = col2.slider("Wie viel Prozent davon darf ein einzelner Trade höchstens kosten?",
                       0.25, 3.0, float(cfg["risk_pct"]), step=0.25,
                       help="Profis riskieren meist 0,5–2 % pro Trade. So überlebst du auch "
                            "mehrere Fehlschläge hintereinander.")
    st.caption(f"→ Pro Trade höchstens **{c.fmt_num(depot * risk / 100, 0)}** verlieren. "
               "Diesen Betrag schlägt die Aktienanalyse automatisch vor.")
    if st.button("Speichern", type="primary"):
        storage.update_settings(depot_size=depot, risk_pct=risk)
        st.success("Gespeichert.")

    st.divider()
    st.markdown("**Speicher**")
    if storage.status() == "gist":
        st.success("Merkliste, Übungsdepot und Einstellungen werden dauerhaft in einem privaten "
                   "Gist in deinem GitHub-Konto gespeichert.", icon="💾")
    else:
        st.markdown(
            "Damit sich die App alles dauerhaft merkt, braucht dein GitHub-Schlüssel eine zusätzliche "
            "Berechtigung:\n\n"
            "1. Öffne **https://github.com/settings/personal-access-tokens** und klicke auf "
            "**tradetalk-app**.\n"
            "2. Klicke auf **Edit**.\n"
            "3. Unter **Permissions** → Reiter **Account** → **Add permissions** → **Gists** "
            "auswählen und auf **Read and write** stellen.\n"
            "4. Ganz unten **Update** klicken.\n"
            "5. Diese Seite neu laden. Der Schlüssel selbst bleibt gleich – du musst nichts neu "
            "eintragen.")


def render() -> None:
    s.page_head('<span class="tt-logo">tradetalk</span> Mein Bereich',
                "Merkliste · Übungsdepot · Einstellungen")
    storage_banner()
    tabs = st.tabs(["⭐ Merkliste", "🧪 Übungsdepot", "⚙️ Einstellungen"])
    with tabs[0]:
        watchlist_tab(c.scan())
    with tabs[1]:
        depot_tab()
    with tabs[2]:
        settings_tab()
