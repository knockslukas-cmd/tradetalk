"""KI-Zusammenfassung einer Aktie mit Claude (Anthropic API).

Benötigt in den Streamlit-Secrets:

    [anthropic]
    api_key = "sk-ant-..."

Die Zusammenfassung wird nur auf Knopfdruck erstellt (kostet ein paar Cent)
und 6 Stunden zwischengespeichert.
"""

from __future__ import annotations

import json

import streamlit as st

try:  # anthropic 1.x braucht Python >= 3.10; lokal (3.9) ist die Funktion dann aus
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

MODEL = "claude-opus-5-5"

SYSTEM = """Du bist ein erfahrener Börsenjournalist und erklärst Aktien für Einsteiger ohne Fachwissen.
Schreibe auf Deutsch, in kurzen, klaren Sätzen und ohne Fachbegriffe (falls unvermeidbar, erkläre sie in
Klammern). Gib keine Kauf- oder Verkaufsempfehlung und keine persönliche Anlageberatung – beschreibe nur,
was die Daten und Nachrichten zeigen und worauf man achten sollte.

Aufbau deiner Antwort (Markdown):
**Worum geht es bei der Firma?** – 1–2 Sätze.
**Was ist gerade los?** – 2–4 Sätze zu Kursverlauf und Nachrichten. Ordne jede wichtige Nachricht als
eher gut, eher schlecht oder neutral für die Aktie ein.
**Worauf achten?** – 2–3 Stichpunkte (z. B. Termine, Risiken, was die Idee bestätigen oder widerlegen würde).

Nutze nur die gelieferten Informationen. Wenn keine Nachrichten vorliegen, sag das kurz und stütze dich
auf die Kursdaten. Erfinde keine Zahlen."""


def available() -> bool:
    return anthropic is not None and bool(_key())


def _key() -> str | None:
    try:
        return st.secrets["anthropic"]["api_key"]
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def summarize(ticker: str, facts_json: str, news_json: str) -> str:
    """facts_json/news_json als Text, damit der Cache-Schlüssel stabil ist."""
    client = anthropic.Anthropic(api_key=_key())
    payload = (f"Aktie: {ticker}\n\nDaten aus der Analyse (JSON):\n{facts_json}\n\n"
               f"Aktuelle Nachrichten (JSON, evtl. leer):\n{news_json}")
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
    except anthropic.AuthenticationError:
        return "⚠️ Der Anthropic-API-Schlüssel ist ungültig. Bitte in den Streamlit-Secrets prüfen."
    except anthropic.RateLimitError:
        return "⚠️ Gerade zu viele Anfragen – bitte in einer Minute noch einmal versuchen."
    except anthropic.APIStatusError as exc:
        return f"⚠️ Die KI ist gerade nicht erreichbar (Fehler {exc.status_code})."
    except anthropic.APIConnectionError:
        return "⚠️ Keine Verbindung zur KI. Bitte später noch einmal versuchen."
    if response.stop_reason == "refusal":
        return "Die KI konnte zu dieser Aktie keine Zusammenfassung erstellen."
    return "".join(b.text for b in response.content if b.type == "text").strip()


def facts(name: str, info: dict, m: dict, checks: list, verdict: str, currency: str,
          last: float) -> str:
    data = {
        "name": name, "branche": info.get("sector"), "industrie": info.get("industry"),
        "beschreibung": (info.get("longBusinessSummary") or "")[:1200],
        "kurs": round(float(last), 2),
        "waehrung": currency,
        "veraenderung_prozent": {k: round(m[k], 1) for k in
                                 ["chg_1d", "perf_1w", "perf_1m", "perf_3m", "perf_1y"]
                                 if m.get(k) == m.get(k)},
        "abstand_jahreshoch_prozent": round(m["dist_52w_high"], 1),
        "ueberhitzung_rsi": round(m["rsi14"], 0) if m["rsi14"] == m["rsi14"] else None,
        "typische_tagesschwankung_prozent": round(m["atr_pct"], 1) if m["atr_pct"] == m["atr_pct"] else None,
        "auffaelligkeiten": m.get("signals"),
        "pruefschritte": [{"titel": h, "text": t} for _, h, t in checks],
        "gesamteinschaetzung_der_app": verdict,
        "kursziel_analysten": info.get("targetMeanPrice"),
        "analystenurteil": info.get("recommendationKey"),
    }
    return json.dumps(data, ensure_ascii=False, default=str)
