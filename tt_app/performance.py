"""Seite "Erfolgskontrolle": Was ist aus den Trade-Ideen geworden?"""

from __future__ import annotations

import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tt_app import common as c
from tt_app import explain as x
from tt_app import style as s

sys.path.insert(0, str(c.ROOT / "src"))
import tracking  # noqa: E402

KIND_NAMES = {k: x.TITLES.get(k, k) for k in x.PRIORITY}
BACKTEST = c.RESULTS / "ideas_backtest.parquet"
LIVE = c.RESULTS / "ideas_eval.parquet"


@st.cache_data(show_spinner=False)
def _load(path_str: str, _m: float) -> pd.DataFrame:
    return pd.read_parquet(path_str)


def load(path) -> pd.DataFrame:
    return _load(str(path), c.mtime(path)) if path.exists() else pd.DataFrame()


def verdict_text(row: pd.Series) -> tuple[str, str]:
    avg = row["avg_result"]
    if avg >= 1.5:
        return "up", "Die Ideen haben im Schnitt klar Geld gebracht."
    if avg > 0.2:
        return "warn", ("Die Ideen lagen im Schnitt nur leicht im Plus. Ohne Gebühren knapp lohnend – "
                        "mit Gebühren und Fehlern beim Umsetzen schnell bei null.")
    if avg > -0.2:
        return "warn", "Die Ideen waren im Schnitt etwa ein Nullsummenspiel."
    return "down", "Die Ideen haben im Schnitt Geld gekostet."


def overview(ev: pd.DataFrame, title: str) -> None:
    summ = tracking.summarize(ev)
    if summ.empty:
        st.info("Noch keine abgeschlossenen Ideen.")
        return
    r = summ.iloc[0]
    tone, text = verdict_text(r)
    color = {"up": s.UP, "warn": s.WARN, "down": s.DOWN}[tone]
    s.html_block(
        f'<div class="tt-summary" style="--vbg:rgba(139,149,167,.08)">'
        f'<div class="tt-label muted-t" style="font-size:.75rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.08em">{s.esc(title)}</div>'
        f'<div class="tt-vt" style="color:{color}">Ø {c.fmt_pct(r["avg_result"], 2)} pro Idee</div>'
        f'<div class="tt-text">{s.esc(text)}</div></div>')
    s.html_block('<div class="tt-grid c5">' + "".join([
        s.tile("Ausgewertete Ideen", c.fmt_num(r["anzahl"], 0)),
        s.tile("Mit Gewinn beendet", c.fmt_num(r["trefferquote"], 0, " %"),
               "nötig: ca. 33 % (Ziel = 2× Risiko)"),
        s.tile("Ø Gewinn / Ø Verlust",
               f'<span class="up-t">{c.fmt_pct(r["avg_win"])}</span> / '
               f'<span class="down-t">{c.fmt_pct(r["avg_loss"])}</span>'),
        s.tile("Ziel erreicht", c.fmt_num(r["ziel_quote"], 0, " %"),
               f'Ausstieg: {c.fmt_num(r["ausstieg_quote"], 0)} %'),
        s.tile("Ø Dauer", f'{c.fmt_num(r["avg_days"], 0)} Tage', "bis Ziel/Ausstieg"),
    ]) + "</div>")


def breakdown(ev: pd.DataFrame) -> None:
    by_stars = tracking.summarize(ev, "stars")
    by_kind = tracking.summarize(ev, "kind")
    a, b = st.columns(2, gap="large")
    with a:
        s.section("Helfen die Sterne?")
        if len(by_stars):
            fig = go.Figure(go.Bar(
                x=[f"{int(v)} ★" for v in by_stars["stars"]], y=by_stars["avg_result"],
                marker_color=[s.UP if v > 0 else s.DOWN for v in by_stars["avg_result"]],
                text=[c.fmt_pct(v, 2) for v in by_stars["avg_result"]], textposition="outside"))
            fig.update_layout(height=260, margin=dict(l=0, r=0, t=20, b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              yaxis=dict(title="Ø Ergebnis %", gridcolor="#1a2130"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.caption("Ø Ergebnis pro Idee nach Sternen. Steigt die Kurve von links nach rechts, "
                       "sind die Sterne ein guter Hinweis.")
    with b:
        s.section("Welche Art funktioniert?")
        if len(by_kind):
            view = by_kind.assign(art=by_kind["kind"].map(KIND_NAMES)).sort_values("avg_result",
                                                                                ascending=False)
            st.dataframe(view[["art", "anzahl", "trefferquote", "avg_result", "avg_days"]],
                         hide_index=True, use_container_width=True, column_config={
                             "art": st.column_config.TextColumn("Art der Idee", width="medium"),
                             "anzahl": st.column_config.NumberColumn("Anzahl", format="%d"),
                             "trefferquote": st.column_config.NumberColumn("mit Gewinn %", format="%.0f"),
                             "avg_result": st.column_config.NumberColumn("Ø Ergebnis %", format="%+.2f"),
                             "avg_days": st.column_config.NumberColumn("Ø Tage", format="%.0f"),
                         })


def monthly(ev: pd.DataFrame) -> None:
    done = ev[ev["outcome"] != "offen"].copy()
    if done.empty:
        return
    done["month"] = pd.to_datetime(done["date"]).dt.to_period("M").dt.to_timestamp()
    m = done.groupby("month")["result_pct"].mean().reset_index()
    s.section("Wann hat es funktioniert?")
    fig = go.Figure(go.Bar(x=m["month"], y=m["result_pct"],
                           marker_color=[s.UP if v > 0 else s.DOWN for v in m["result_pct"]]))
    fig.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(title="Ø Ergebnis %", gridcolor="#1a2130"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("Ø Ergebnis der Ideen je Monat (nach Datum der Idee). In schwachen Börsenphasen "
               "funktionieren Kauf-Ideen meist deutlich schlechter – deshalb ist das Börsenwetter wichtig.")


def recent(ev: pd.DataFrame) -> None:
    s.section("Letzte Ideen und was daraus wurde")
    view = ev.sort_values(["date", "score"], ascending=[False, False]).head(200).copy()
    view["art"] = view["kind"].map(KIND_NAMES)
    st.dataframe(view[["date", "ticker", "name", "art", "stars", "entry", "outcome", "result_pct", "days"]],
                 hide_index=True, use_container_width=True, height=420, column_config={
                     "date": st.column_config.TextColumn("Datum"),
                     "ticker": st.column_config.TextColumn("Kürzel"),
                     "name": st.column_config.TextColumn("Name", width="medium"),
                     "art": st.column_config.TextColumn("Art"),
                     "stars": st.column_config.NumberColumn("Sterne", format="%d ★"),
                     "entry": st.column_config.NumberColumn("Kurs damals", format="%.2f"),
                     "outcome": st.column_config.TextColumn("Ergebnis"),
                     "result_pct": st.column_config.NumberColumn("%", format="%+.1f"),
                     "days": st.column_config.NumberColumn("Tage", format="%d"),
                 })


def render() -> None:
    s.page_head('<span class="tt-logo">tradetalk</span> Erfolgskontrolle',
                "Funktionieren die Ideen wirklich?")
    st.markdown(
        "Hier prüft die App sich selbst: Für jede Idee wird nachgeschaut, ob der Kurs danach **zuerst "
        "das Ziel** oder **zuerst die Ausstiegsmarke** erreicht hat (höchstens 60 Handelstage). "
        "Einstieg ist der Schlusskurs am Tag der Idee. Gebühren sind nicht eingerechnet.")
    live, back = load(LIVE), load(BACKTEST)
    tabs = st.tabs(["📅 Seit Start der App", "🔁 Rückblick (2 Jahre)"])
    with tabs[0]:
        if live.empty:
            st.info("Ab jetzt wird jeden Tag mitgeschrieben, welche Ideen die App zeigt. Erste "
                    "Ergebnisse gibt es nach ein paar Tagen bis Wochen – bis dahin hilft der Rückblick.")
        else:
            done = (live["outcome"] != "offen").sum()
            st.caption(f"{len(live)} Ideen mitgeschrieben, davon {done} abgeschlossen.")
            overview(live, "Seit Start der App")
            if done:
                breakdown(live)
            recent(live)
    with tabs[1]:
        if back.empty:
            st.info("Noch kein Rückblick berechnet (Skript: src/backtest.py).")
            return
        st.caption("So hätten die Ideen in den letzten 2 Jahren abgeschnitten – mit genau den Regeln "
                   "von heute, jede Woche neu berechnet. Hinweis: Es fehlen Firmen, die es heute nicht "
                   "mehr gibt; die Ergebnisse sind daher eher etwas zu gut.")
        overview(back, "Rückblick auf 2 Jahre")
        breakdown(back)
        monthly(back)
        with st.expander("Was heißt das für mich?"):
            st.markdown(
                "- **Kein Wundermittel:** Die Ideen sind eine Vorauswahl. Viele Trades enden an der "
                "Ausstiegsmarke – das ist normal und gehört dazu.\n"
                "- **Die Ausstiegsmarke rettet dich:** Verluste bleiben klein, Gewinne sind etwa doppelt "
                "so groß. Nur so kommt man trotz vieler Fehlschläge ins Plus.\n"
                "- **Wähle aus:** Ideen mit mehr Sternen und bei gutem Börsenwetter schneiden besser ab.\n"
                "- **Erst üben:** Probiere Ideen im Übungsdepot aus, bevor du echtes Geld einsetzt.")
        recent(back)
