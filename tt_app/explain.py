"""Übersetzt Kennzahlen in verständliche Sätze – ohne Fachbegriffe.

Alles hier ist regelbasiert: aus Trend, Schwung, Handelsaktivität und
Schwankung werden kurze Erklärungen, Überlegungen und ein möglicher Plan
gebaut. Es sind Denkanstöße zur eigenen Prüfung, keine Empfehlungen.
"""

from __future__ import annotations

import math

from tt_app.common import fmt_num, fmt_pct

# Erklärungen für Begriffe, die trotzdem vorkommen (als Tooltip)
GLOSSARY = {
    "trend_kurz": "Durchschnittskurs der letzten 50 Handelstage (ca. 2½ Monate). "
                  "Liegt der Kurs darüber, läuft es kurzfristig gut.",
    "trend_lang": "Durchschnittskurs der letzten 200 Handelstage (ca. 1 Jahr). "
                  "Liegt der Kurs darüber, ist die Aktie langfristig im Aufwärtstrend.",
    "staerke": "Vergleich mit allen ~2.900 Aktien im Scan: 90 heißt, die Aktie lief in den "
               "letzten Monaten besser als 90 % aller anderen.",
    "ueberhitzung": "Misst, wie schnell und einseitig der Kurs zuletzt gestiegen oder gefallen ist "
                    "(Fachbegriff: RSI). Über 70 = überhitzt, unter 30 = stark abverkauft.",
    "schwankung": "Um wie viel Prozent sich der Kurs an einem normalen Tag bewegt.",
    "handel": "Wie viele Aktien heute gehandelt wurden im Vergleich zum Durchschnitt. "
              "2× heißt doppelt so viel wie üblich – oft ein Zeichen, dass große Anleger aktiv sind.",
    "ausstieg": "Die Marke, ab der die Idee als gescheitert gilt. Fällt der Kurs darunter, "
                "steigst du aus und begrenzt so deinen Verlust.",
    "ziel": "Ein realistisches erstes Kursziel, z. B. das Jahreshoch.",
    "chance_risiko": "Wie viel du im guten Fall gewinnen kannst im Verhältnis zu dem, was du im "
                     "schlechten Fall verlierst. 2 heißt: doppelt so viel Chance wie Risiko.",
    "kgv": "Kurs-Gewinn-Verhältnis: Wie viele Jahresgewinne die Aktie kostet. "
           "Niedrig = eher günstig, hoch = Anleger erwarten viel Wachstum.",
    "beta": "Wie stark die Aktie im Vergleich zum Gesamtmarkt schwankt. 1 = wie der Markt, "
            "2 = doppelt so stark.",
}


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


# --------------------------------------------------------------------------- #
# Marktbericht
# --------------------------------------------------------------------------- #
def index_sentence(i: dict) -> tuple[str, str]:
    """(Satz, Ton) für einen Index."""
    name = {"S&P 500": "Die US-Börse (S&P 500)", "Nasdaq Composite": "Die US-Technologiewerte (Nasdaq)",
            "DAX": "Der DAX"}.get(i["name"], i["name"])
    if i["above_short"] and i["above_long"]:
        return f"{name} läuft gut – kurz- und langfristig geht es aufwärts.", "up"
    if i["above_long"]:
        return (f"{name} ist langfristig im Aufwärtstrend, macht aber gerade eine "
                "Verschnaufpause."), "warn"
    if i["above_short"]:
        return f"{name} erholt sich gerade, ist langfristig aber noch angeschlagen.", "warn"
    return f"{name} ist im Abwärtstrend.", "down"


def fear_sentence(vix: float) -> tuple[str, str]:
    if vix < 15:
        return "Die Anleger sind sehr entspannt – kaum Angst im Markt.", "up"
    if vix < 20:
        return "Die Stimmung ist ruhig, keine Panik.", "up"
    if vix < 30:
        return "Die Anleger sind nervös – es kann größere Schwankungen geben.", "warn"
    return "Es herrscht Angst im Markt – es geht hektisch und unberechenbar zu.", "down"


def market_report(regime: dict, breadth: dict | None) -> dict:
    verdict = regime["verdict"]
    headline = {
        "Rückenwind": "Gutes Börsenwetter",
        "neutral": "Gemischtes Börsenwetter",
        "Gegenwind": "Schwieriges Börsenwetter",
    }.get(verdict, "Marktlage")
    icon = {"Rückenwind": "☀️", "neutral": "⛅", "Gegenwind": "🌧️"}.get(verdict, "🌤️")

    points = []
    for i in regime["indices"]:
        if i.get("available"):
            points.append(index_sentence(i))
    if regime.get("vix"):
        points.append(fear_sentence(regime["vix"]["value"]))
    if breadth:
        p = breadth["above_sma200_pct"]
        if p >= 60:
            points.append((f"Die breite Masse zieht mit: {fmt_num(p, 0)} % aller Aktien sind "
                           "langfristig im Aufwärtstrend.", "up"))
        elif p >= 40:
            points.append((f"Der Markt ist gespalten: nur {fmt_num(p, 0)} % der Aktien sind "
                           "langfristig im Aufwärtstrend – es kommt auf die Auswahl an.", "warn"))
        else:
            points.append((f"Die meisten Aktien laufen schlecht: nur {fmt_num(p, 0)} % sind "
                           "langfristig im Aufwärtstrend.", "down"))
        hi, lo = breadth["new_highs"], breadth["new_lows"]
        if hi > lo * 1.5 and hi >= 10:
            points.append((f"{hi} Aktien erreichen ein neues Jahreshoch, nur {lo} ein Jahrestief – "
                           "ein gutes Zeichen.", "up"))
        elif lo > hi * 1.5 and lo >= 10:
            points.append((f"{lo} Aktien fallen auf ein neues Jahrestief, nur {hi} steigen auf ein "
                           "Jahreshoch – Vorsicht.", "down"))

    advice = {
        "Rückenwind": [
            "Das Umfeld spricht für Aktien, die nach oben laufen.",
            "Trotzdem für jede Idee vorher festlegen, wann du aussteigst.",
        ],
        "neutral": [
            "Nur die besten Ideen anschauen (4–5 Sterne).",
            "Mit kleineren Beträgen arbeiten als sonst.",
            "Die Ausstiegsmarke unbedingt vorher festlegen und einhalten.",
        ],
        "Gegenwind": [
            "In diesem Umfeld scheitern viele Ideen – Abwarten ist auch eine Entscheidung.",
            "Wenn überhaupt, nur sehr kleine Beträge und enge Ausstiegsmarken.",
        ],
    }.get(verdict, [])
    return {"headline": headline, "icon": icon, "points": points, "advice": advice}


# --------------------------------------------------------------------------- #
# Trade-Ideen
# --------------------------------------------------------------------------- #
PRIORITY = ["breakout_52w", "pullback_sma50", "golden_cross", "reclaim_sma200", "oversold_trend"]

TITLES = {
    "breakout_52w": "Steigt auf ein neues Jahreshoch",
    "pullback_sma50": "Verschnaufpause im Aufwärtstrend",
    "golden_cross": "Der Trend dreht nach oben",
    "reclaim_sma200": "Zurück im Aufwärtstrend",
    "oversold_trend": "Stark gefallen, aber der Trend hält",
}


def main_setup(keys: str) -> str | None:
    ks = [k for k in str(keys).split(",") if k]
    for k in PRIORITY:
        if k in ks:
            return k
    return None


def idea_story(r) -> dict:
    """Überlegungen zu einer Trade-Idee in Alltagssprache."""
    keys = [k for k in str(r["signal_keys"]).split(",") if k]
    kind = main_setup(r["signal_keys"])
    why, watch, caution = [], [], []

    if kind == "breakout_52w":
        why.append("Die Aktie ist so teuer wie seit einem Jahr nicht. Darüber gibt es keine "
                   "enttäuschten Käufer von früher, die beim Einstandskurs verkaufen wollen.")
        watch.append(f"Bleibt der Kurs in den nächsten Tagen über dem alten Hoch? Rutscht er "
                     f"schnell wieder darunter, war der Ausbruch ein Fehlsignal.")
    elif kind == "pullback_sma50":
        why.append("Die Aktie ist seit Monaten im Aufwärtstrend und ist jetzt etwas zurückgekommen – "
                   "bis an ihren 50-Tage-Durchschnitt, wo sie in Aufwärtstrends oft wieder Halt findet.")
        watch.append("Dreht der Kurs hier wieder nach oben? Ein kräftiger grüner Tag mit viel "
                     "Handel wäre ein gutes Zeichen.")
    elif kind == "golden_cross":
        why.append("Der Durchschnittskurs der letzten 50 Tage ist über den der letzten 200 Tage "
                   "gestiegen – oft der Beginn eines neuen Aufwärtstrends.")
        watch.append("Solche Wenden brauchen Zeit. Steigt der Kurs in den nächsten Wochen weiter?")
    elif kind == "reclaim_sma200":
        why.append("Die Aktie ist wieder über ihren Jahresdurchschnitt gestiegen und damit "
                   "langfristig zurück im Aufwärtstrend.")
        watch.append("Hält sie sich darüber? Fällt sie gleich wieder zurück, war es nur ein Strohfeuer.")
    elif kind == "oversold_trend":
        why.append("Die Aktie ist in kurzer Zeit stark gefallen, liegt aber noch über ihrem "
                   "Jahresdurchschnitt. Solche Übertreibungen gleichen sich oft wieder aus.")
        watch.append("Nicht ins fallende Messer greifen: Warte auf ein Zeichen, dass der Fall stoppt "
                     "(z. B. ein kräftiger grüner Tag).")

    rs = r.get("rs_rank")
    if not _nan(rs) and rs >= 70:
        why.append(f"Lief in den letzten Monaten besser als {fmt_num(rs, 0)} % aller Aktien.")
    v = r.get("vol_ratio")
    if not _nan(v) and v >= 1.5 and r["chg_1d"] > 0:
        why.append(f"Heute wurde {fmt_num(v, 1)}-mal so viel gehandelt wie üblich – große Käufer "
                   "scheinen aktiv zu sein.")

    rsi_v, atr_v = r.get("rsi14"), r.get("atr_pct")
    if not _nan(rsi_v) and rsi_v >= 75:
        caution.append("Ist schon stark gestiegen – nicht hinterherlaufen. Ein kleiner Rücksetzer "
                       "wäre oft der bessere Einstieg.")
    if not _nan(atr_v) and atr_v >= 6:
        caution.append(f"Schwankt sehr stark (an normalen Tagen ±{fmt_num(atr_v, 1)} %) – nur mit "
                       "kleinem Betrag.")
    if "gap_up" in keys:
        caution.append("Ist heute mit einem Kurssprung gestartet. Solche Lücken schließen sich oft "
                       "teilweise wieder.")
    if r.get("has_warning"):
        caution.append("Es gibt gleichzeitig ein Warnsignal – genauer prüfen.")
    if not _nan(r.get("reward_risk")) and r["reward_risk"] < 1.5:
        caution.append("Die mögliche Chance ist im Verhältnis zum Risiko eher klein.")

    wrong_if = (f"Fällt der Kurs unter {fmt_num(r['stop'])} {r.get('currency', '')} "
                f"({fmt_pct(-r['risk_pct'])}), ist die Idee gescheitert – dann aussteigen.")
    return {
        "kind": kind,
        "title": TITLES.get(kind, "Auffällige Aktie"),
        "why": why[:3],
        "watch": watch[:1],
        "caution": caution[:2],
        "wrong_if": wrong_if,
    }


def stars(n) -> str:
    n = 0 if _nan(n) else int(n)
    return "★" * n + "☆" * (5 - n)


# --------------------------------------------------------------------------- #
# Aktienanalyse
# --------------------------------------------------------------------------- #
def trend_check(m: dict) -> tuple[str, str, str]:
    """(Ampel, Kurztext, Erklärung) zum Trend der Aktie."""
    if m["uptrend"] and m["dist_sma50"] > 0:
        return ("up", "Klarer Aufwärtstrend",
                "Der Kurs liegt über seinem 50- und 200-Tage-Durchschnitt – kurz- und langfristig "
                "geht es nach oben.")
    if m["uptrend"]:
        return ("warn", "Aufwärtstrend mit Pause",
                "Langfristig geht es aufwärts, kurzfristig ist die Aktie aber etwas zurückgekommen.")
    if not _nan(m["dist_sma200"]) and m["dist_sma200"] > 0:
        return ("warn", "Uneinheitlich",
                "Der Kurs liegt über dem Jahresdurchschnitt, aber die Durchschnitte zeigen noch "
                "keinen klaren Aufwärtstrend.")
    return ("down", "Abwärtstrend",
            f"Der Kurs liegt {fmt_pct(m['dist_sma200'])} unter seinem Jahresdurchschnitt – "
            "langfristig geht es abwärts.")


def strength_check(rs_rank, rel_3m: float, bench: str) -> tuple[str, str, str]:
    if _nan(rs_rank) and _nan(rel_3m):
        return ("muted", "Keine Vergleichsdaten", "")
    parts = []
    if not _nan(rel_3m):
        parts.append(f"In den letzten 3 Monaten {'besser' if rel_3m > 0 else 'schlechter'} als der "
                     f"{bench} ({fmt_pct(rel_3m)}).")
    if not _nan(rs_rank):
        parts.append(f"Lief besser als {fmt_num(rs_rank, 0)} % aller Aktien im Scan.")
    good = (not _nan(rs_rank) and rs_rank >= 70) or (_nan(rs_rank) and rel_3m > 5)
    bad = (not _nan(rs_rank) and rs_rank < 40) or (_nan(rs_rank) and rel_3m < -5)
    if good:
        return ("up", "Stärker als der Markt", " ".join(parts))
    if bad:
        return ("down", "Schwächer als der Markt", " ".join(parts))
    return ("warn", "Durchschnittlich", " ".join(parts))


def timing_check(m: dict) -> tuple[str, str, str]:
    r = m["rsi14"]
    keys = m["signal_keys"]
    if not _nan(r) and r >= 75:
        return ("down", "Gerade überhitzt",
                "Die Aktie ist zuletzt sehr schnell gestiegen. Wer jetzt einsteigt, kauft teuer – "
                "oft kommt erst ein Rücksetzer.")
    if "pullback_sma50" in keys:
        return ("up", "Rücksetzer – oft ein guter Moment",
                "Die Aktie ist im Aufwärtstrend etwas zurückgekommen und an einer Stelle, an der sie "
                "oft wieder dreht.")
    if "breakout_52w" in keys:
        return ("up", "Ausbruch nach oben",
                "Die Aktie steigt gerade auf ein neues Jahreshoch – Schwung ist da.")
    if not _nan(r) and r <= 30:
        if m["uptrend"]:
            return ("warn", "Stark abverkauft",
                    "Kurzfristig stark gefallen, der langfristige Trend hält aber. Auf ein Zeichen "
                    "der Stabilisierung warten.")
        return ("down", "Im freien Fall",
                "Stark gefallen und im Abwärtstrend – hier nicht ins fallende Messer greifen.")
    if m["has_warning"]:
        return ("down", "Warnsignal", "Es gibt gerade ein Warnsignal – lieber abwarten.")
    return ("warn", "Kein besonderer Anlass",
            "Gerade passiert nichts Auffälliges. Abwarten, bis sich eine Gelegenheit ergibt.")


def risk_check(m: dict) -> tuple[str, str, str]:
    atr_v, rr = m["atr_pct"], m["reward_risk"]
    swing = f"An normalen Tagen bewegt sich der Kurs um etwa ±{fmt_num(atr_v, 1)} %."
    if not _nan(atr_v) and atr_v >= 6:
        return ("down", "Sehr wilde Schwankungen", swing + " Nur mit kleinem Betrag.")
    if not _nan(rr) and rr >= 2:
        return ("up", "Chance deutlich größer als Risiko",
                swing + f" Bis zum Ziel ist {fmt_num(rr, 1)}-mal so viel drin wie bis zur Ausstiegsmarke.")
    if not _nan(rr) and rr < 1.5:
        return ("warn", "Wenig Luft nach oben",
                swing + " Bis zum Jahreshoch ist nicht mehr viel Platz im Verhältnis zum Risiko.")
    return ("warn", "Normales Risiko", swing)


def overall(checks: list[tuple[str, str, str]], market_verdict: str | None) -> tuple[str, str, str]:
    score = sum({"up": 1, "down": -1}.get(c[0], 0) for c in checks)
    if market_verdict == "Gegenwind":
        score -= 1
    if score >= 3:
        return ("up", "Sieht interessant aus",
                "Trend, Stärke und Zeitpunkt passen. Eine Idee, die man sich genauer anschauen kann.")
    if score >= 1:
        return ("warn", "Beobachten",
                "Einiges spricht dafür, aber nicht alles passt. Auf die Beobachtungsliste setzen und "
                "auf einen besseren Moment warten.")
    return ("down", "Eher Finger weg",
            "Gerade spricht mehr dagegen als dafür.")
