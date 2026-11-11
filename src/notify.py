"""Benachrichtigungen per Telegram nach dem Tageslauf.

Meldet
- Übungstrades, die heute ihr Ziel oder die Ausstiegsmarke erreicht haben
- Aktien auf der Merkliste mit neuen Signalen
- neue Top-Ideen (4–5 Sterne, nur beim Abendlauf)
- einen Wechsel des Börsenwetters

Benötigt (als GitHub-Secrets, sonst wird still übersprungen):
  TELEGRAM_BOT_TOKEN   Token deines Telegram-Bots (von @BotFather)
  TELEGRAM_CHAT_ID     deine Chat-ID
  TRADETALK_TOKEN      optional: GitHub-Token mit "Gists: Read" für Merkliste/Depot

Aufruf aus dem Projektordner:  python3 src/notify.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("notify")
GIST_DESCRIPTION = "tradetalk-userdata"
GIST_FILE = "tradetalk.json"


def fmt(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def load_userdata(token: str | None) -> dict:
    if not token:
        return {}
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        r = requests.get("https://api.github.com/gists", headers=h, params={"per_page": 100}, timeout=15)
        r.raise_for_status()
        for g in r.json():
            if g.get("description") == GIST_DESCRIPTION and GIST_FILE in g.get("files", {}):
                full = requests.get(g["url"], headers=h, timeout=15).json()
                return json.loads(full["files"][GIST_FILE]["content"])
    except Exception as exc:
        log.warning("Merkliste/Depot nicht lesbar: %s", exc)
    return {}


def trade_alerts(trades: list[dict], prices_dir: Path) -> list[str]:
    out = []
    for t in trades:
        if t.get("status") != "open":
            continue
        path = filters.price_path(prices_dir, t["ticker"])
        if not path.exists():
            continue
        bar = pd.read_parquet(path).dropna(subset=["Close"]).iloc[-1]
        if bar["Low"] <= t["stop"]:
            out.append(f"🔴 <b>{t['ticker']}</b>: Ausstiegsmarke {fmt(t['stop'])} erreicht "
                       f"(Kurs {fmt(bar['Close'])}). Die Idee hat nicht funktioniert – im Übungsdepot verkaufen.")
        elif bar["High"] >= t["target"]:
            out.append(f"🟢 <b>{t['ticker']}</b>: Ziel {fmt(t['target'])} erreicht "
                       f"(Kurs {fmt(bar['Close'])}). Gewinn mitnehmen oder Ausstieg nachziehen.")
    return out


def watch_alerts(watchlist: list[dict], scan: pd.DataFrame) -> list[str]:
    out = []
    idx = scan.set_index("ticker")
    for w in watchlist:
        if w["ticker"] in idx.index and idx.loc[w["ticker"], "signals"]:
            r = idx.loc[w["ticker"]]
            out.append(f"⭐ <b>{w['ticker']}</b> ({fmt(r['close'])}, {r['chg_1d']:+.1f} %): {r['signals']}")
    return out


def regime_alert(results: Path) -> list[str]:
    path = results / "regime_history.csv"
    if not path.exists():
        return []
    hist = pd.read_csv(path)
    if len(hist) < 2 or hist.iloc[-1]["verdict"] == hist.iloc[-2]["verdict"]:
        return []
    names = {"Rückenwind": "☀️ gutes", "neutral": "⛅ gemischtes", "Gegenwind": "🌧️ schwieriges"}
    return [f"Das Börsenwetter hat gedreht: jetzt {names.get(hist.iloc[-1]['verdict'], '')} Börsenwetter "
            f"(vorher {names.get(hist.iloc[-2]['verdict'], '')})."]


def idea_alerts(scan: pd.DataFrame, n: int = 3) -> list[str]:
    if "stars" not in scan:
        return []
    top = scan[(scan["stars"] >= 4) & scan["has_setup"]].sort_values("score", ascending=False).head(n)
    return [f"💡 <b>{r.ticker}</b> {r.name[:30]} – {r.signals} ({'★' * int(r.stars)}) · "
            f"Ausstieg {fmt(r.stop)}, Ziel {fmt(r.target)}" for r in top.itertuples()]


def send(token: str, chat_id: str, text: str) -> None:
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                      json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True})
    r.raise_for_status()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    tg_token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tg_token or not chat:
        log.info("Kein Telegram eingerichtet – keine Benachrichtigung.")
        return 0
    cfg = filters.load_config()
    results = ROOT / cfg["paths"]["results_dir"]
    scan = pd.read_parquet(results / "scan_latest.parquet")
    user = load_userdata(os.environ.get("TRADETALK_TOKEN"))
    evening = datetime.now(timezone.utc).hour >= 21

    parts = []
    trades = trade_alerts(user.get("trades", []), ROOT / cfg["paths"]["prices_dir"])
    if trades:
        parts.append("<b>Dein Übungsdepot</b>\n" + "\n".join(trades))
    watch = watch_alerts(user.get("watchlist", []), scan)
    if watch:
        parts.append("<b>Deine Merkliste</b>\n" + "\n".join(watch))
    parts += regime_alert(results)
    if evening:
        ideas = idea_alerts(scan)
        if ideas:
            parts.append("<b>Top-Ideen heute</b>\n" + "\n".join(ideas))
    if not parts:
        log.info("Nichts zu melden.")
        return 0
    text = "📈 <b>tradetalk</b>\n\n" + "\n\n".join(parts) + "\n\n<i>Denkanstöße, keine Anlageberatung.</i>"
    try:
        send(tg_token, chat, text[:4000])
        log.info("Benachrichtigung gesendet (%d Abschnitte).", len(parts))
    except Exception as exc:
        log.error("Telegram-Versand fehlgeschlagen: %s", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
