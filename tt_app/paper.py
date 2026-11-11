"""Übungstrading: Depot mit Spielgeld, Orders, automatischer Ausstieg/Ziel.

Regeln
- Startkapital 50.000 €, Depotwährung Euro. US-Aktien werden zum aktuellen
  EUR/USD-Kurs umgerechnet (Kauf und Verkauf jeweils zum Tageskurs).
- Gebühr 1 € pro ausgeführter Order. Bruchstücke erlaubt (4 Nachkommastellen).
- Market-Orders. Ist die Börse geschlossen, wartet die Order und wird beim
  ersten Aufruf nach Börsenöffnung zum dann aktuellen Kurs ausgeführt.
- Ausstieg (Stop-Loss) und Ziel (Take-Profit) je Position: Werden sie seit dem
  Kauf berührt, verkauft die App automatisch – zur Marke oder, bei einer
  Kurslücke, zum schlechteren Eröffnungskurs.
- Kurse von Yahoo Finance: US meist nahezu live, Xetra oft ~15 Min. verzögert.
  Feiertage werden nicht berücksichtigt.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

from tt_app import storage

START_CASH = 50_000.0
FEE = 1.0
FX_SYMBOL = "EURUSD=X"
NY, BERLIN = ZoneInfo("America/New_York"), ZoneInfo("Europe/Berlin")


# --------------------------------------------------------------------------- #
# Daten
# --------------------------------------------------------------------------- #
def currency_of(ticker: str) -> str:
    return "EUR" if ticker.upper().endswith(".DE") else "USD"


def market_open(ticker: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if ticker.upper().endswith(".DE"):
        local, start, end = now.astimezone(BERLIN), time(9, 0), time(17, 30)
    else:
        local, start, end = now.astimezone(NY), time(9, 30), time(16, 0)
    return local.weekday() < 5 and start <= local.time() < end


def market_label(ticker: str) -> str:
    return "Xetra" if ticker.upper().endswith(".DE") else "US-Börse"


@st.cache_data(ttl=30, show_spinner=False)
def quotes(tickers: tuple[str, ...]) -> dict[str, dict]:
    """Letzter Kurs je Ticker (+ Zeitpunkt) aus Minutendaten, Fallback Tagesdaten."""
    out: dict[str, dict] = {}
    if not tickers:
        return out
    syms = tuple(sorted(set(tickers) | {FX_SYMBOL}))
    try:
        d = yf.download(list(syms), period="1d", interval="1m", group_by="ticker", progress=False,
                        auto_adjust=False, multi_level_index=True, threads=True)
    except Exception:
        d = None
    for t in syms:
        try:
            s = d[t]["Close"].dropna() if d is not None and t in d.columns.get_level_values(0) else None
            if s is not None and len(s):
                out[t] = {"price": float(s.iloc[-1]), "time": s.index[-1].to_pydatetime()}
        except Exception:
            pass
    missing = [t for t in syms if t not in out]
    if missing:
        try:
            d = yf.download(missing, period="5d", interval="1d", group_by="ticker", progress=False,
                            auto_adjust=False, multi_level_index=True)
            for t in missing:
                if t in d.columns.get_level_values(0):
                    s = d[t]["Close"].dropna()
                    if len(s):
                        out[t] = {"price": float(s.iloc[-1]),
                                  "time": pd.Timestamp(s.index[-1]).tz_localize("UTC").to_pydatetime()
                                  if s.index.tz is None else s.index[-1].to_pydatetime()}
        except Exception:
            pass
    return out


def fx_rate(q: dict) -> float:
    """US-Dollar je Euro."""
    return q.get(FX_SYMBOL, {}).get("price") or 1.10


def to_eur(price: float, ticker: str, fx: float) -> float:
    return price if currency_of(ticker) == "EUR" else price / fx


@st.cache_data(ttl=60, show_spinner=False)
def bars_since(ticker: str, since_iso: str) -> pd.DataFrame:
    """Tagesbalken nach dem Kauftag + Minutenbalken von heute (nach dem Kaufzeitpunkt)."""
    since = pd.Timestamp(since_iso)
    frames = []
    try:
        day = yf.download(ticker, start=(since - pd.Timedelta(days=1)).date().isoformat(),
                          interval="1d", progress=False, auto_adjust=False, multi_level_index=False)
        if len(day):
            day.index = pd.to_datetime(day.index).tz_localize("UTC") if day.index.tz is None else day.index
            day = day[(day.index.normalize() > since.normalize())
                      & (day.index.normalize() < pd.Timestamp.now(tz="UTC").normalize())]
            frames.append(day[["Open", "High", "Low", "Close"]])
        intra = yf.download(ticker, period="1d", interval="1m", progress=False, auto_adjust=False,
                            multi_level_index=False)
        if len(intra):
            intra = intra[intra.index > since]
            frames.append(intra[["Open", "High", "Low", "Close"]])
    except Exception:
        return pd.DataFrame()
    return pd.concat(frames).sort_index() if frames else pd.DataFrame()


# --------------------------------------------------------------------------- #
# Depot
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_depot() -> dict:
    return {"start_cash": START_CASH, "cash": START_CASH, "created": now_iso(), "fee": FEE,
            "positions": {}, "orders": [], "history": []}


def get() -> dict:
    data = storage.get()
    if not data.get("paper"):
        data["paper"] = new_depot()
    return data["paper"]


def save() -> bool:
    return storage.save(storage.get())


def reset() -> None:
    storage.get()["paper"] = new_depot()
    save()


def reserved_cash(p: dict) -> float:
    return sum(o["estimate_eur"] for o in p["orders"] if o["status"] == "pending" and o["side"] == "buy")


def pending_sell_shares(p: dict, ticker: str) -> float:
    return sum(o["shares"] for o in p["orders"]
               if o["status"] == "pending" and o["side"] == "sell" and o["ticker"] == ticker)


def place_order(side: str, ticker: str, name: str, shares: float, price_eur_est: float,
                stop: float | None = None, target: float | None = None, idea: str = "",
                reason: str = "von Hand") -> tuple[bool, str]:
    p = get()
    shares = round(float(shares), 4)
    if shares <= 0:
        return False, "Bitte eine Stückzahl größer als 0 angeben."
    if side == "buy":
        cost = shares * price_eur_est + p["fee"]
        if cost > p["cash"] - reserved_cash(p) + 1e-6:
            return False, (f"Nicht genug Geld: benötigt {cost:,.2f} €, verfügbar "
                           f"{p['cash'] - reserved_cash(p):,.2f} €.").replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        have = p["positions"].get(ticker, {}).get("shares", 0) - pending_sell_shares(p, ticker)
        if shares > have + 1e-6:
            return False, f"Du hast nur {have:g} Stück davon."
    order = {"id": uuid.uuid4().hex[:8], "side": side, "ticker": ticker, "name": name,
             "currency": currency_of(ticker), "shares": shares, "created": now_iso(),
             "status": "pending", "estimate_eur": round(shares * price_eur_est + p["fee"], 2),
             "stop": stop, "target": target, "idea": idea, "reason": reason}
    p["orders"].append(order)
    filled = process(only=order["id"])
    save()
    if filled:
        return True, f"{'Gekauft' if side == 'buy' else 'Verkauft'}: {shares:g} × {name}"
    return True, (f"Die {market_label(ticker)} ist gerade geschlossen. Deine Order wartet und wird "
                  "zum ersten Kurs nach Börsenöffnung ausgeführt.")


def cancel_order(order_id: str) -> None:
    for o in get()["orders"]:
        if o["id"] == order_id and o["status"] == "pending":
            o["status"] = "cancelled"
    save()


def _fill(p: dict, o: dict, price: float, fx: float, when: str | None = None) -> None:
    price_eur = to_eur(price, o["ticker"], fx)
    value = o["shares"] * price_eur
    o.update(status="filled", filled=when or now_iso(), price=round(price, 4), fx=round(fx, 5),
             price_eur=round(price_eur, 4), fee=p["fee"])
    pos = p["positions"].get(o["ticker"])
    if o["side"] == "buy":
        p["cash"] -= value + p["fee"]
        if pos:
            total = pos["shares"] + o["shares"]
            pos["avg_price"] = (pos["avg_price"] * pos["shares"] + price * o["shares"]) / total
            pos["cost_eur"] += value + p["fee"]
            pos["shares"] = round(total, 4)
            if o.get("stop"):
                pos["stop"] = o["stop"]
            if o.get("target"):
                pos["target"] = o["target"]
        else:
            p["positions"][o["ticker"]] = {
                "ticker": o["ticker"], "name": o["name"], "currency": o["currency"],
                "shares": o["shares"], "avg_price": price, "cost_eur": value + p["fee"],
                "stop": o.get("stop"), "target": o.get("target"), "idea": o.get("idea", ""),
                "opened": o["filled"]}
    else:
        p["cash"] += value - p["fee"]
        cost_part = pos["cost_eur"] * o["shares"] / pos["shares"]
        o["pnl_eur"] = round(value - p["fee"] - cost_part, 2)
        o["pnl_pct"] = round((value - p["fee"]) / cost_part * 100 - 100, 2) if cost_part else 0
        o["idea"] = pos.get("idea", "")
        o["opened"] = pos.get("opened")
        pos["shares"] = round(pos["shares"] - o["shares"], 4)
        pos["cost_eur"] -= cost_part
        if pos["shares"] <= 1e-6:
            del p["positions"][o["ticker"]]
    p["cash"] = round(p["cash"], 2)


def process(only: str | None = None) -> int:
    """Wartende Orders ausführen und Ausstieg/Ziel prüfen. Gibt Anzahl Ausführungen zurück."""
    p = get()
    tickers = {o["ticker"] for o in p["orders"] if o["status"] == "pending"} | set(p["positions"])
    if not tickers:
        return 0
    q = quotes(tuple(sorted(tickers)))
    fx = fx_rate(q)
    n = 0
    for o in p["orders"]:
        if o["status"] != "pending" or (only and o["id"] != only):
            continue
        if not market_open(o["ticker"]) or o["ticker"] not in q:
            continue
        price = q[o["ticker"]]["price"]
        if o["side"] == "buy" and o["shares"] * to_eur(price, o["ticker"], fx) + p["fee"] > p["cash"] + 1e-6:
            o.update(status="cancelled", reason="nicht genug Geld bei Ausführung")
            continue
        _fill(p, o, price, fx)
        n += 1
    if only:
        return n
    # Ausstieg / Ziel
    for t, pos in list(p["positions"].items()):
        stop, target = pos.get("stop"), pos.get("target")
        if not stop and not target:
            continue
        bars = bars_since(t, pos["opened"])
        for ts, bar in bars.iterrows():
            hit_price, why = None, None
            if stop and bar["Low"] <= stop:
                hit_price, why = min(stop, bar["Open"]), "Ausstieg erreicht"
            elif target and bar["High"] >= target:
                hit_price, why = max(target, bar["Open"]), "Ziel erreicht"
            if hit_price:
                o = {"id": uuid.uuid4().hex[:8], "side": "sell", "ticker": t, "name": pos["name"],
                     "currency": pos["currency"], "shares": pos["shares"], "created": now_iso(),
                     "status": "pending", "estimate_eur": 0, "reason": why}
                p["orders"].append(o)
                _fill(p, o, float(hit_price), fx, when=pd.Timestamp(ts).isoformat())
                n += 1
                break
    return n


def snapshot(value: float) -> None:
    """Depotwert einmal pro Tag merken (letzter Aufruf des Tages gewinnt)."""
    p = get()
    day = datetime.now(BERLIN).date().isoformat()
    hist = [h for h in p.get("history", []) if h["date"] != day]
    hist.append({"date": day, "value": round(value, 2)})
    p["history"] = hist[-400:]


def valuation() -> dict:
    """Aktueller Depotwert, Positionen mit Live-Kursen."""
    p = get()
    q = quotes(tuple(sorted(p["positions"])) or ("EURUSD=X",))
    fx = fx_rate(q)
    rows = []
    for t, pos in p["positions"].items():
        quote = q.get(t)
        price = quote["price"] if quote else pos["avg_price"]
        value = pos["shares"] * to_eur(price, t, fx)
        rows.append({**pos, "price": price, "price_time": quote["time"] if quote else None,
                     "value_eur": value, "pnl_eur": value - pos["cost_eur"],
                     "pnl_pct": (value / pos["cost_eur"] - 1) * 100 if pos["cost_eur"] else 0})
    invested = sum(r["value_eur"] for r in rows)
    total = p["cash"] + invested
    return {"cash": p["cash"], "reserved": reserved_cash(p), "invested": invested, "total": total,
            "pnl_total": total - p["start_cash"],
            "pnl_total_pct": (total / p["start_cash"] - 1) * 100, "positions": rows, "fx": fx}


def closed_trades() -> pd.DataFrame:
    rows = [o for o in get()["orders"] if o["status"] == "filled" and o["side"] == "sell"]
    return pd.DataFrame(rows)


def nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))
