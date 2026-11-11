"""Seite "Termine": Quartalszahlen und Dividenden der Aktien, die dich interessieren."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
import yfinance as yf

from tt_app import common as c
from tt_app import storage
from tt_app import style as s


@st.cache_data(ttl=43200, show_spinner=False)
def ticker_events(ticker: str) -> list[dict]:
    try:
        cal = yf.Ticker(ticker).calendar or {}
    except Exception:
        return []
    out = []
    for d in cal.get("Earnings Date") or []:
        out.append({"date": pd.Timestamp(d).date(), "kind": "Quartalszahlen",
                    "hint": "Der Kurs springt an diesem Tag oft stark – in beide Richtungen."})
    if cal.get("Ex-Dividend Date"):
        out.append({"date": pd.Timestamp(cal["Ex-Dividend Date"]).date(), "kind": "Dividende (Ex-Tag)",
                    "hint": "Ab diesem Tag wird die Aktie ohne Dividende gehandelt – der Kurs sinkt "
                            "meist um den Dividendenbetrag."})
    return out


def render() -> None:
    s.page_head('<span class="tt-logo">tradetalk</span> Termine',
                "Was steht bei deinen Aktien an?")
    data = storage.get()
    scan = c.scan()
    groups = {
        "Übungsdepot": [(t["ticker"], t["name"]) for t in data["trades"] if t["status"] == "open"],
        "Merkliste": [(w["ticker"], w["name"]) for w in data["watchlist"]],
    }
    if len(scan) and "score" in scan:
        top = scan[scan["has_setup"] & (scan["score"] > 0)].sort_values("score", ascending=False).head(8)
        groups["Top-Ideen heute"] = list(zip(top["ticker"], top["name"]))

    seen, rows = set(), []
    with st.spinner("Lade Termine …"):
        for group, items in groups.items():
            for ticker, name in items:
                if ticker in seen:
                    continue
                seen.add(ticker)
                for e in ticker_events(ticker):
                    rows.append({**e, "ticker": ticker, "name": name, "group": group})
    for e in c.config().get("events") or []:
        try:
            rows.append({"date": pd.Timestamp(e["date"]).date(), "kind": "Markttermin", "ticker": "",
                         "name": e["title"], "group": "Allgemein",
                         "hint": e.get("hint", "Kann den ganzen Markt bewegen.")})
        except Exception:
            continue

    today = date.today()
    rows = [r for r in rows if today - timedelta(days=1) <= r["date"] <= today + timedelta(days=60)]
    if not rows:
        st.info("In den nächsten 60 Tagen stehen keine Termine an – oder es sind noch keine Aktien auf "
                "deiner Merkliste. Merke dir Aktien in der Aktienanalyse mit **⭐ Merken**.")
        return
    rows.sort(key=lambda r: r["date"])
    html = []
    for r in rows:
        days = (r["date"] - today).days
        when = "heute" if days == 0 else "morgen" if days == 1 else f"in {days} Tagen" if days > 0 else "gestern"
        tone = "down" if days <= 7 else "warn" if days <= 21 else "muted"
        html.append(
            f'<div class="tt-planrow"><div><div class="tt-l">{r["date"]:%d.%m.%Y} · '
            f'{s.esc(r["kind"])}</div><div class="tt-d">{s.esc(r["hint"])}</div></div>'
            f'<div style="text-align:right"><div class="tt-l">{s.esc(r["ticker"])} '
            f'<span class="muted-t" style="font-weight:500">{s.esc(r["name"])}</span></div>'
            f'{s.pill(when, tone)}{s.pill(r["group"], "muted")}</div></div>')
    s.html_block(f'<div class="tt-planbox">{"".join(html)}</div>')
    st.caption("Termine laut Yahoo Finance, ohne Gewähr. Allgemeine Markttermine (z. B. Zinsentscheide) "
               "kannst du in der Datei config.yaml unter „events“ eintragen.")
