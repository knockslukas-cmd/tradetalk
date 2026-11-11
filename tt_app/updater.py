"""Knopf "Markt jetzt aktualisieren": startet den GitHub-Workflow sofort.

Benötigt in den Streamlit-Secrets (App -> Settings -> Secrets):

    [github]
    token = "github_pat_..."          # Fine-grained Token, nur Repo tradetalk,
                                      # Berechtigung "Actions: Read and write"
    repo = "knockslukas-cmd/tradetalk"
    workflow = "daily_scan.yml"       # optional
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

from tt_app.common import berlin

API = "https://api.github.com"


def _settings() -> dict | None:
    try:
        gh = st.secrets["github"]
        return {"token": gh["token"], "repo": gh["repo"],
                "workflow": gh.get("workflow", "daily_scan.yml")}
    except Exception:
        return None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


@st.cache_data(ttl=15, show_spinner=False)
def latest_run(repo: str, workflow: str, token: str) -> dict | None:
    r = requests.get(f"{API}/repos/{repo}/actions/workflows/{workflow}/runs",
                     headers=_headers(token), params={"per_page": 1}, timeout=10)
    r.raise_for_status()
    runs = r.json().get("workflow_runs", [])
    if not runs:
        return None
    run = runs[0]
    return {k: run.get(k) for k in
            ["status", "conclusion", "created_at", "updated_at", "html_url", "event"]}


def trigger(repo: str, workflow: str, token: str) -> tuple[bool, str]:
    r = requests.post(f"{API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
                      headers=_headers(token), json={"ref": "main"}, timeout=10)
    if r.status_code == 204:
        return True, "Aktualisierung gestartet."
    if r.status_code in (401, 403):
        return False, "GitHub lehnt den Token ab. Bitte Token und Berechtigung prüfen."
    if r.status_code == 404:
        return False, "Repo oder Workflow nicht gefunden. Bitte die Secrets prüfen."
    return False, f"GitHub meldet Fehler {r.status_code}."


STATUS_TEXT = {
    "queued": "⏳ wartet auf einen freien Server …",
    "in_progress": "🔄 läuft gerade …",
    "waiting": "⏳ wartet …",
    "pending": "⏳ wartet …",
}


@st.fragment(run_every=20)
def update_panel() -> None:
    """Kleiner Bereich in der Seitenleiste."""
    s = _settings()
    st.markdown("**Daten aktualisieren**")
    if not s:
        st.caption("Der Knopf ist noch nicht eingerichtet (GitHub-Token fehlt in den "
                   "Streamlit-Secrets).")
        st.button("🔄 Markt jetzt aktualisieren", disabled=True, width="stretch")
        return

    try:
        run = latest_run(s["repo"], s["workflow"], s["token"])
    except Exception:
        run = None
        st.caption("GitHub ist gerade nicht erreichbar.")

    running = bool(run and run["status"] != "completed")
    if st.button("🔄 Markt jetzt aktualisieren", disabled=running, width="stretch",
                 help="Lädt neue Kurse, berechnet Signale und Marktlage neu (ca. 3–8 Minuten)."):
        ok, msg = trigger(s["repo"], s["workflow"], s["token"])
        (st.success if ok else st.error)(msg)
        latest_run.clear()
        st.session_state["update_started"] = pd.Timestamp.now(tz="UTC").isoformat()
        return

    if not run:
        return
    if running:
        st.info(f"Aktualisierung {STATUS_TEXT.get(run['status'], run['status'])}  \n"
                f"gestartet {berlin(run['created_at'])}")
    elif run["conclusion"] == "success":
        st.caption(f"✅ Letzte Aktualisierung: {berlin(run['updated_at'])}")
        started = st.session_state.get("update_started")
        if started and pd.Timestamp(run["updated_at"]) > pd.Timestamp(started):
            st.success("Neue Daten sind da. Die App lädt sie in 1–2 Minuten automatisch.")
            if st.button("Jetzt neu laden", width="stretch"):
                st.session_state.pop("update_started", None)
                st.cache_data.clear()
                st.rerun(scope="app")
    else:
        st.warning(f"Letzte Aktualisierung fehlgeschlagen ({berlin(run['updated_at'])}). "
                   f"[Details auf GitHub]({run['html_url']})")
