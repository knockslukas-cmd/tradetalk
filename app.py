"""tradetalk – Streamlit-App.

Seiten (Navigation links):
  Dashboard      Marktlage, Top-Setups und Auffälligkeiten
  Scanner        alle liquiden Aktien, filter- und sortierbar
  Aktienanalyse  automatische Recherche zu einer Aktie

Lokal starten:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="tradetalk", page_icon="📈", layout="wide")

from tt_app import analysis, common, dashboard, scanner, updater  # noqa: E402

pages = {
    "dashboard": st.Page(dashboard.render, title="Dashboard", icon="📊", url_path="dashboard",
                         default=True),
    "scanner": st.Page(scanner.render, title="Scanner", icon="🔎", url_path="scanner"),
    "analysis": st.Page(analysis.render, title="Aktienanalyse", icon="🔬", url_path="analyse"),
}
common.PAGES.update(pages)

nav = st.navigation(list(pages.values()))
with st.sidebar:
    updater.update_panel()
    st.divider()
nav.run()
