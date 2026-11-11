"""tradetalk – Streamlit-App.

Seiten (Navigation links):
  Dashboard          Börsenwetter, Branchen, Trade-Ideen, Auffälligkeiten
  Aktienanalyse      geführte Prüfung einer Aktie mit Plan
  Scanner            alle geprüften Aktien, filter- und sortierbar
  Mein Bereich       Merkliste, Übungsdepot, Einstellungen
  Termine            Quartalszahlen und Dividenden
  Erfolgskontrolle   Was ist aus den Ideen geworden?
  Lern-Ecke          Erklärungen und Einrichtung

Lokal starten:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="tradetalk", page_icon="📈", layout="wide")

from tt_app import (analysis, calendar_page, common, dashboard, depot, learn,  # noqa: E402
                    performance, scanner, style, updater)

style.inject()

pages = {
    "dashboard": st.Page(dashboard.render, title="Dashboard", icon="📊", url_path="dashboard",
                         default=True),
    "analysis": st.Page(analysis.render, title="Aktienanalyse", icon="🔬", url_path="analyse"),
    "scanner": st.Page(scanner.render, title="Scanner", icon="🔎", url_path="scanner"),
    "depot": st.Page(depot.render, title="Mein Bereich", icon="⭐", url_path="mein-bereich"),
    "calendar": st.Page(calendar_page.render, title="Termine", icon="📅", url_path="termine"),
    "performance": st.Page(performance.render, title="Erfolgskontrolle", icon="✅",
                           url_path="erfolgskontrolle"),
    "learn": st.Page(learn.render, title="Lern-Ecke", icon="🎓", url_path="lernen"),
}
common.PAGES.update(pages)

nav = st.navigation({
    "Markt": [pages["dashboard"], pages["analysis"], pages["scanner"]],
    "Für dich": [pages["depot"], pages["calendar"]],
    "Wissen": [pages["performance"], pages["learn"]],
})
with st.sidebar:
    updater.update_panel()
    st.divider()
nav.run()
