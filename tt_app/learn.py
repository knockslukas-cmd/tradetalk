"""Seite "Lern-Ecke": kurze Erklärungen und Einrichtung der Zusatzfunktionen."""

from __future__ import annotations

import streamlit as st

from tt_app import ai, storage
from tt_app import style as s

LESSONS = [
    ("📈 Was ist ein Aufwärtstrend?",
     "Ein Aufwärtstrend heißt: Der Kurs macht über Wochen und Monate höhere Hochs und höhere Tiefs. "
     "Die App misst das einfach: Liegt der Kurs über seinem **Durchschnitt der letzten 200 Tage** "
     "(etwa ein Jahr), ist die Aktie langfristig im Aufwärtstrend. Liegt er auch über dem "
     "**50-Tage-Durchschnitt**, läuft es auch kurzfristig gut.\n\n"
     "Warum das wichtig ist: Aktien im Aufwärtstrend steigen öfter weiter, als dass sie plötzlich "
     "drehen. Gegen den Trend zu kaufen ist für Einsteiger meist ein Verlustgeschäft."),
    ("🚪 Warum eine Ausstiegsmarke?",
     "Niemand liegt immer richtig – auch Profis nicht. Der Unterschied: Profis legen **vor dem Kauf** "
     "fest, ab welchem Kurs sie zugeben, dass die Idee falsch war, und verkaufen dann.\n\n"
     "So bleiben Verluste klein. Wenn die Gewinne der guten Trades etwa **doppelt so groß** sind wie "
     "die Verluste der schlechten, kommst du sogar ins Plus, wenn nur jeder dritte Trade klappt. "
     "Genau so ist der Plan in der App aufgebaut."),
    ("⚖️ Wie viel Geld pro Trade?",
     "Faustregel: Riskiere pro Trade höchstens **1–2 % deines Börsengelds**. Bei 10.000 € sind das "
     "100–200 €, die du im schlechten Fall verlierst – nicht der ganze Einsatz!\n\n"
     "Der Rechner in der Aktienanalyse macht genau das: Er rechnet aus, wie viele Aktien du kaufen "
     "kannst, damit du an der Ausstiegsmarke nicht mehr als diesen Betrag verlierst. Deine Werte "
     "stellst du unter **Mein Bereich → Einstellungen** ein."),
    ("🌡️ Was bedeutet „überhitzt“?",
     "Wenn eine Aktie sehr schnell und ohne Pause gestiegen ist, gilt sie als überhitzt. Oft kommt dann "
     "erst ein Rücksetzer, bevor es weitergeht. Wer genau dann kauft, kauft teuer.\n\n"
     "Die App misst das mit einer Zahl zwischen 0 und 100 (Fachbegriff RSI): über 70 = überhitzt, "
     "unter 30 = stark abverkauft."),
    ("🔊 Warum ist das Handelsvolumen wichtig?",
     "Das Volumen zeigt, wie viele Aktien gehandelt wurden. Steigt ein Kurs bei **ungewöhnlich viel "
     "Handel**, kaufen oft große Anleger wie Fonds – das stützt die Bewegung. Steigt er bei wenig "
     "Handel, steht die Bewegung auf wackligen Beinen."),
    ("🌦️ Warum das Börsenwetter?",
     "Etwa drei von vier Aktien folgen dem Gesamtmarkt. Fällt der Markt, werden auch gute Aktien mit "
     "nach unten gezogen. Deshalb zeigt die App oben das Börsenwetter: Bei schlechtem Wetter lieber "
     "weniger und kleiner handeln – oder ganz abwarten."),
    ("🧪 Warum erst üben?",
     "Im Übungsdepot handelst du mit Spielgeld nach genau den Regeln, die du später echt anwenden "
     "willst. Nach 20–30 Übungstrades siehst du ehrlich, ob du dich an Ausstiegsmarken hältst und "
     "wie deine Bilanz aussieht – bevor echtes Geld im Spiel ist."),
    ("📊 Funktionieren die Ideen?",
     "Unter **Erfolgskontrolle** prüft die App sich selbst – mit allen Ideen der letzten zwei Jahre. "
     "Ehrliches Ergebnis: Die Ideen sind kein Wundermittel, im Schnitt liegen sie leicht im Plus. "
     "Ideen mit mehr Sternen schneiden etwas besser ab. Die App ist eine **Vorauswahl**, die dir "
     "Arbeit abnimmt – die Entscheidung bleibt bei dir."),
]


def check(ok: bool) -> str:
    return s.pill("eingerichtet ✓", "up") if ok else s.pill("noch nicht eingerichtet", "warn")


def setup_section() -> None:
    s.section("⚙️ Einrichtung der Zusatzfunktionen")
    st.caption("Alles hier ist freiwillig. Die App funktioniert auch ohne.")

    with st.expander("💾 Merkliste & Übungsdepot dauerhaft speichern"):
        s.html_block(check(storage.status() == "gist"))
        st.markdown(
            "1. Öffne **https://github.com/settings/personal-access-tokens** und klicke auf **tradetalk-app**.\n"
            "2. Klicke auf **Edit**.\n"
            "3. Unter **Permissions** den Reiter **Account** wählen → **Add permissions** → **Gists** → "
            "**Read and write**.\n"
            "4. Ganz unten **Update** klicken. Fertig – der Schlüssel bleibt derselbe.")

    with st.expander("📲 Benachrichtigungen aufs Handy (Telegram)"):
        st.markdown(
            "Nach jedem automatischen Lauf bekommst du eine Nachricht, wenn ein Übungstrade Ziel oder "
            "Ausstieg erreicht, eine Aktie auf deiner Merkliste auffällt, das Börsenwetter dreht oder es "
            "neue Top-Ideen gibt.\n\n"
            "**A. Einen eigenen Telegram-Bot anlegen**\n"
            "1. Telegram öffnen und nach **@BotFather** suchen.\n"
            "2. `/newbot` schicken, einen Namen (z. B. *tradetalk*) und einen Benutzernamen, der auf "
            "*bot* endet, vergeben.\n"
            "3. BotFather antwortet mit einem **Token** (z. B. `123456:ABC…`). Kopieren.\n\n"
            "**B. Deine Chat-ID herausfinden**\n"
            "1. Deinem neuen Bot in Telegram irgendeine Nachricht schicken, z. B. *Hallo*.\n"
            "2. Im Browser öffnen: `https://api.telegram.org/bot<DEIN-TOKEN>/getUpdates` "
            "(Token einsetzen).\n"
            "3. Dort steht `\"chat\":{\"id\":12345678` – diese Zahl ist deine Chat-ID.\n\n"
            "**C. Bei GitHub hinterlegen**\n"
            "1. Öffne **https://github.com/knockslukas-cmd/tradetalk/settings/secrets/actions**.\n"
            "2. **New repository secret**: Name `TELEGRAM_BOT_TOKEN`, Wert = Token aus A.\n"
            "3. Noch einmal: Name `TELEGRAM_CHAT_ID`, Wert = Zahl aus B.\n"
            "4. Optional, damit auch Merkliste und Übungsdepot gemeldet werden: Name `TRADETALK_TOKEN`, "
            "Wert = dein GitHub-Schlüssel *tradetalk-app* (mit der Gist-Berechtigung von oben). Den "
            "Schlüssel siehst du nicht mehr – erstelle dafür bei Bedarf einen neuen mit denselben "
            "Rechten.\n\n"
            "Ab dem nächsten Lauf kommen die Nachrichten.")

    with st.expander("🤖 KI-Zusammenfassung"):
        s.html_block(check(ai.available()))
        st.markdown(
            "Die KI (Claude von Anthropic) fasst auf Knopfdruck zusammen, was bei einer Aktie los ist. "
            "Jede Zusammenfassung kostet ein paar Cent.\n\n"
            "1. Auf **https://console.anthropic.com** ein Konto anlegen und unter *Billing* ein "
            "kleines Guthaben aufladen (z. B. 5 $).\n"
            "2. Unter **API Keys** einen Schlüssel erstellen und kopieren (beginnt mit `sk-ant-`).\n"
            "3. Auf **share.streamlit.io** bei deiner App → ⋮ → **Settings** → **Secrets** unter den "
            "bisherigen Zeilen einfügen:\n")
        st.code('[anthropic]\napi_key = "HIER_DEN_SCHLUESSEL_EINFUEGEN"', language="toml")
        st.markdown("4. **Save** klicken. Den Schlüssel bitte nirgendwo sonst teilen.")


def render() -> None:
    s.page_head('<span class="tt-logo">tradetalk</span> Lern-Ecke',
                "Börse verständlich erklärt · Einrichtung")
    s.section("📚 Kurz erklärt")
    cols = st.columns(2, gap="large")
    for i, (title, text) in enumerate(LESSONS):
        with cols[i % 2]:
            with st.expander(title):
                st.markdown(text)
    setup_section()
