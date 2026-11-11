"""Dauerhafter Speicher für Merkliste, Übungsdepot und Einstellungen.

Die Daten liegen als JSON in einem privaten ("secret") GitHub-Gist deines
Kontos. Dafür braucht der Token in den Streamlit-Secrets zusätzlich die
Berechtigung "Gists: Read and write" (Account permissions).

Ohne diese Berechtigung merkt sich die App alles nur bis zum Schließen.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import requests
import streamlit as st

API = "https://api.github.com"
DESCRIPTION = "tradetalk-userdata"
FILENAME = "tradetalk.json"

DEFAULT = {
    "watchlist": [],
    "trades": [],
    "settings": {"depot_size": 10000.0, "risk_pct": 1.0},
}


def _token() -> str | None:
    try:
        return st.secrets["github"]["token"]
    except Exception:
        return None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _find_gist(token: str) -> str | None:
    page = 1
    while page <= 5:
        r = requests.get(f"{API}/gists", headers=_headers(token),
                         params={"per_page": 100, "page": page}, timeout=10)
        r.raise_for_status()
        items = r.json()
        for g in items:
            if g.get("description") == DESCRIPTION and FILENAME in g.get("files", {}):
                return g["id"]
        if len(items) < 100:
            return None
        page += 1
    return None


def _create_gist(token: str, data: dict) -> str:
    r = requests.post(f"{API}/gists", headers=_headers(token), timeout=10, json={
        "description": DESCRIPTION, "public": False,
        "files": {FILENAME: {"content": json.dumps(data, ensure_ascii=False, indent=2)}}})
    r.raise_for_status()
    return r.json()["id"]


def _merge_defaults(data: dict) -> dict:
    out = json.loads(json.dumps(DEFAULT))
    out.update({k: v for k, v in data.items() if k in out})
    out["settings"] = {**DEFAULT["settings"], **data.get("settings", {})}
    return out


def status() -> str:
    """'gist' (dauerhaft), 'session' (nur bis zum Schließen) oder 'error'."""
    _load()
    return st.session_state.get("_store_mode", "session")


def _load() -> dict:
    if "_store" in st.session_state:
        return st.session_state["_store"]
    data, mode = json.loads(json.dumps(DEFAULT)), "session"
    token = _token()
    if token:
        try:
            gid = _find_gist(token)
            if gid:
                r = requests.get(f"{API}/gists/{gid}", headers=_headers(token), timeout=10)
                r.raise_for_status()
                data = _merge_defaults(json.loads(r.json()["files"][FILENAME]["content"]))
            st.session_state["_gist_id"] = gid
            mode = "gist"
        except requests.HTTPError as exc:
            mode = "session"
            st.session_state["_store_error"] = (
                "Der Token darf keine Gists lesen/schreiben." if exc.response is not None
                and exc.response.status_code in (401, 403, 404) else str(exc))
        except Exception as exc:
            mode, st.session_state["_store_error"] = "session", str(exc)
    st.session_state["_store"] = data
    st.session_state["_store_mode"] = mode
    return data


def get() -> dict:
    return _load()


def save(data: dict) -> bool:
    st.session_state["_store"] = data
    if st.session_state.get("_store_mode") != "gist":
        return False
    token = _token()
    try:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        gid = st.session_state.get("_gist_id")
        if not gid:
            st.session_state["_gist_id"] = _create_gist(token, data)
            return True
        r = requests.patch(f"{API}/gists/{gid}", headers=_headers(token), timeout=10,
                           json={"files": {FILENAME: {"content": content}}})
        r.raise_for_status()
        return True
    except Exception as exc:
        st.session_state["_store_error"] = str(exc)
        st.toast("Speichern fehlgeschlagen – Änderung gilt nur bis zum Schließen.", icon="⚠️")
        return False


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Merkliste
# --------------------------------------------------------------------------- #
def on_watchlist(ticker: str) -> bool:
    return any(w["ticker"] == ticker for w in get()["watchlist"])


def add_watch(ticker: str, name: str, price: float, note: str = "") -> None:
    data = get()
    if not on_watchlist(ticker):
        data["watchlist"].append({"ticker": ticker, "name": name, "added": now(),
                                  "price_added": round(float(price), 4), "note": note})
        save(data)


def remove_watch(ticker: str) -> None:
    data = get()
    data["watchlist"] = [w for w in data["watchlist"] if w["ticker"] != ticker]
    save(data)


# --------------------------------------------------------------------------- #
# Übungsdepot
# --------------------------------------------------------------------------- #
def open_trade(ticker: str, name: str, currency: str, entry: float, shares: int, stop: float,
               target: float, idea: str = "") -> None:
    data = get()
    data["trades"].append({
        "id": uuid.uuid4().hex[:8], "ticker": ticker, "name": name, "currency": currency,
        "opened": now(), "entry": round(float(entry), 4), "shares": int(shares),
        "stop": round(float(stop), 4), "target": round(float(target), 4), "idea": idea,
        "status": "open", "closed": None, "exit": None, "reason": None})
    save(data)


def close_trade(trade_id: str, price: float, reason: str) -> None:
    data = get()
    for t in data["trades"]:
        if t["id"] == trade_id and t["status"] == "open":
            t.update(status="closed", closed=now(), exit=round(float(price), 4), reason=reason)
    save(data)


def delete_trade(trade_id: str) -> None:
    data = get()
    data["trades"] = [t for t in data["trades"] if t["id"] != trade_id]
    save(data)


def update_settings(**kwargs) -> None:
    data = get()
    data["settings"].update(kwargs)
    save(data)
