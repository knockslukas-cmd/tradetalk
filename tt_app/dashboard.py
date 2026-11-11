"""Seite "Dashboard": Marktbericht, Trade-Ideen und was heute auffällt."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tt_app import common as c
from tt_app import explain as x
from tt_app import sectors
from tt_app import style as s

IDEA_KINDS = {"Alle Ideen": None, "Neues Jahreshoch": "breakout_52w",
              "Rücksetzer im Aufwärtstrend": "pullback_sma50",
              "Trendwende nach oben": "golden_cross",
              "Zurück im Aufwärtstrend": "reclaim_sma200",
              "Stark gefallen, Trend hält": "oversold_trend"}


# --------------------------------------------------------------------------- #
# Marktbericht
# --------------------------------------------------------------------------- #
def index_tile(name: str, value: float, series: list[float], pills: str, digits: int = 0,
               spark_color: str | None = None) -> str:
    chg = (series[-1] / series[-2] - 1) * 100 if len(series) > 1 else float("nan")
    return (
        f'<div class="tt-tile"><div class="tt-row"><div style="min-width:0">'
        f'<div class="tt-k">{s.esc(name)}</div>'
        f'<div class="tt-v">{c.fmt_num(value, digits)}</div>'
        f'<div class="tt-s"><span class="{s.tone(chg)}-t">{c.fmt_pct(chg)}</span> heute</div></div>'
        f'<div style="width:46%">{s.sparkline(series[-90:], 140, 44, color=spark_color)}</div></div>'
        f'<div style="margin-top:.55rem">{pills}</div></div>'
    )


def trend_pills(i: dict) -> str:
    return (s.pill(f"kurzfristig {'↑' if i['above_short'] else '↓'}",
                   "up" if i["above_short"] else "down")
            + s.pill(f"langfristig {'↑' if i['above_long'] else '↓'}",
                     "up" if i["above_long"] else "down"))


def report_section() -> None:
    stored = c.stored_regime()
    with st.spinner("Lade aktuelle Börsendaten …"):
        live = c.live_regime()
    regime = live or stored
    if not regime:
        st.warning("Keine Marktdaten vorhanden.")
        return
    rep = x.market_report(regime, stored.get("breadth"))
    verdict = regime["verdict"]
    color = s.VERDICT_COLOR.get(verdict, s.MUTED)
    glow = {"Rückenwind": "rgba(38,208,124,.22)", "neutral": "rgba(245,165,36,.18)",
            "Gegenwind": "rgba(240,80,110,.22)"}.get(verdict, "rgba(139,149,167,.15)")
    pos = (max(-4, min(4, regime["points"])) + 4) / 8 * 100
    source = "live" if live else f"Stand {c.berlin(stored['generated_at'])}"

    icons = {"up": "✓", "warn": "•", "down": "!"}
    cls = {"up": "pro", "warn": "mid", "down": "con"}
    points = "".join(f'<li class="{cls[t]}"><span class="tt-ic">{icons[t]}</span>'
                     f'<span>{s.esc(p)}</span></li>' for p, t in rep["points"])
    advice = "".join(f"<li>{s.esc(a)}</li>" for a in rep["advice"])

    symbols = tuple(i["symbol"] for i in regime["indices"]) + (c.config()["market_regime"]["vix"],)
    series = c.closes(symbols, "6mo")
    tiles = []
    for i in regime["indices"]:
        if not i.get("available"):
            tiles.append(s.tile(i["name"], "–"))
            continue
        name = {"Nasdaq Composite": "Nasdaq"}.get(i["name"], i["name"])
        tiles.append(index_tile(name, i["close"], series.get(i["symbol"], [i["close"]]),
                                trend_pills(i)))
    if regime.get("vix"):
        v = regime["vix"]
        mood = {"ruhig": ("ruhig", "up"), "erhöht": ("nervös", "warn"),
                "Stress": ("ängstlich", "down")}.get(v["label"], (v["label"], "muted"))
        tiles.append(index_tile("Angst (VIX)", v["value"],
                                series.get(symbols[-1], [v["value"]]), s.pill(mood[0], mood[1]),
                                digits=1, spark_color=s.WARN))

    s.html_block(
        f'<div class="tt-hero" style="--glow:{glow}"><div class="tt-hero-grid">'
        f'<div><div class="tt-label">Marktbericht · {s.esc(source)}</div>'
        f'<div class="tt-verdict" style="color:{color}">{rep["icon"]} {s.esc(rep["headline"])}</div>'
        f'<div class="tt-scale"><div class="tt-marker" style="left:{pos:.0f}%"></div></div>'
        f'<div class="tt-scale-labels"><span>schwierig</span><span>gemischt</span><span>gut</span></div>'
        f'<ul class="tt-list tt-report">{points}</ul></div>'
        f'<div><div class="tt-grid c4">{"".join(tiles)}</div>'
        f'<div class="tt-advice"><div class="tt-label">Was heißt das für dich?</div>'
        f'<ul>{advice}</ul></div></div></div></div>'
    )


def breadth_section(stored: dict) -> None:
    b = stored.get("breadth")
    if not b:
        return
    total_ad = (b["advancers"] + b["decliners"]) or 1
    total_hl = (b["new_highs"] + b["new_lows"]) or 1
    adv = b["advancers"] / total_ad * 100
    hi = b["new_highs"] / total_hl * 100
    tiles = [
        s.tile("Langfristig steigend", c.fmt_num(b["above_sma200_pct"], 0, " %"),
               "der Aktien über ihrem Jahresdurchschnitt", s.bar([(b["above_sma200_pct"], s.ACCENT)])),
        s.tile("Kurzfristig steigend", c.fmt_num(b["above_sma50_pct"], 0, " %"),
               "der Aktien über ihrem 50-Tage-Durchschnitt", s.bar([(b["above_sma50_pct"], s.INFO)])),
        s.tile("Steigen / fallen heute",
               f'<span class="up-t">{b["advancers"]}</span> / <span class="down-t">{b["decliners"]}</span>',
               "Anzahl Aktien", s.bar([(adv, s.UP), (100 - adv, s.DOWN)])),
        s.tile("Neues Jahreshoch / -tief",
               f'<span class="up-t">{b["new_highs"]}</span> / <span class="down-t">{b["new_lows"]}</span>',
               "Anzahl Aktien", s.bar([(hi, s.UP), (100 - hi, s.DOWN)])),
        s.tile("Ideen / Warnsignale",
               f'<span class="up-t">{b["setups"]}</span> / <span class="down-t">{b["warnings"]}</span>',
               "von ~2.900 geprüften Aktien"),
    ]
    s.html_block(f'<div class="tt-grid c5" style="margin-top:.8rem">{"".join(tiles)}</div>')

    hist = c.history()
    if len(hist) > 1:
        with st.expander("📈 Wie hat sich das Börsenwetter entwickelt?"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hist["date"], y=hist["points"], name="Börsenwetter (Punkte)",
                                     line=dict(color=s.ACCENT, width=2), mode="lines+markers"))
            if "above_sma200_pct" in hist:
                fig.add_trace(go.Scatter(x=hist["date"], y=hist["above_sma200_pct"],
                                         name="% Aktien im Aufwärtstrend", yaxis="y2",
                                         line=dict(color=s.WARN, dash="dot")))
            fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              yaxis=dict(title="Punkte", gridcolor="#1a2130"),
                              yaxis2=dict(title="%", overlaying="y", side="right", range=[0, 100]),
                              legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Trade-Ideen
# --------------------------------------------------------------------------- #
def idea_card(r: pd.Series, spark: list[float]) -> str:
    story = x.idea_story(r)
    why = "".join(f'<li class="pro"><span class="tt-ic">✓</span><span>{s.esc(w)}</span></li>'
                  for w in story["why"])
    watch = "".join(f'<li class="mid"><span class="tt-ic">👀</span><span>{s.esc(w)}</span></li>'
                    for w in story["watch"])
    caution = "".join(f'<li class="con"><span class="tt-ic">!</span><span>{s.esc(w)}</span></li>'
                      for w in story["caution"])
    cur = s.esc(r["currency"])
    return (
        f'<a class="tt-card tt-idea" href="analyse?ticker={s.esc(r["ticker"])}" target="_self">'
        f'<div class="tt-top"><div style="min-width:0">'
        f'<div class="tt-idea-title">{s.esc(story["title"])}</div>'
        f'<div class="tt-tk">{s.esc(r["ticker"])} <span class="tt-nm" style="display:inline">'
        f'{s.esc(r["name"])}</span></div></div>'
        f'<div class="tt-px">{c.fmt_num(r["close"])} <small>{cur}</small><br>'
        f'<span class="{s.tone(r["chg_1d"])}-t" style="font-size:.85rem">{c.fmt_pct(r["chg_1d"])} heute</span>'
        f'</div></div>'
        f'<div class="tt-stars" title="Qualität der Idee">{x.stars(r.get("stars", 0))}</div>'
        f'<div class="tt-spark">{s.sparkline(spark, 300, 48)}</div>'
        f'<ul class="tt-list">{why}{watch}{caution}</ul>'
        f'<div class="tt-plan">'
        f'<div><span>Kurs jetzt</span><b>{c.fmt_num(r["close"])}</b></div>'
        f'<div><span>Ausstieg, falls falsch</span><b class="down-t">{c.fmt_num(r["stop"])}</b>'
        f'<em>{c.fmt_pct(-r["risk_pct"])}</em></div>'
        f'<div><span>Mögliches Ziel</span><b class="up-t">{c.fmt_num(r.get("target"))}</b>'
        f'<em>{c.fmt_pct(r.get("target_pct"))}</em></div>'
        f'<div><span>Chance : Risiko</span><b>{c.fmt_num(r.get("reward_risk"), 1)} : 1</b></div>'
        f'</div><div class="tt-cta">Genauer prüfen →</div></a>'
    )


def ideas_section(scan: pd.DataFrame) -> None:
    ideas = scan[scan["has_setup"] & (scan["score"] > 0)].sort_values("score", ascending=False)
    s.section("💡 Trade-Ideen heute", f"{len(ideas)} Kandidaten")
    st.caption("Die App hat alle ~2.900 Aktien geprüft und zeigt die stärksten Ideen. Jede Karte "
               "erklärt, warum die Aktie auffällt, worauf du achten solltest und ab wann die Idee "
               "falsch ist. Klick auf eine Karte für die ausführliche Prüfung.")
    if ideas.empty:
        st.info("Heute keine überzeugenden Ideen gefunden – das ist auch eine Information.")
        return
    choice = st.segmented_control("Art", list(IDEA_KINDS), default="Alle Ideen",
                                  label_visibility="collapsed", key="idea_kind") or "Alle Ideen"
    if IDEA_KINDS[choice]:
        ideas = ideas[ideas["signal_keys"].str.contains(IDEA_KINDS[choice])]
    top = ideas.head(6)
    if top.empty:
        st.caption("Heute keine Ideen dieser Art.")
        return
    sparks = c.closes(tuple(top["ticker"]), "3mo")
    cards = "".join(idea_card(r, sparks.get(r["ticker"], [])) for _, r in top.iterrows())
    s.html_block(f'<div class="tt-grid c3">{cards}</div>')
    with st.expander("Wie entstehen die Ideen und Sterne?"):
        st.markdown(
            "- Die App sucht nach typischen Mustern: **neues Jahreshoch**, **Rücksetzer in einem "
            "Aufwärtstrend**, **Trendwende nach oben** usw.\n"
            "- **Mehr Sterne** bekommt eine Idee, wenn die Aktie insgesamt stärker als andere läuft, "
            "viel gehandelt wird und die mögliche Chance deutlich größer ist als das Risiko.\n"
            "- **Weniger Sterne** gibt es, wenn die Aktie schon überhitzt ist, sehr wild schwankt "
            "oder gleichzeitig Warnsignale zeigt.\n"
            "- **Ausstieg, falls falsch:** liegt etwa zwei normale Tagesschwankungen unter dem Kurs. "
            "Fällt die Aktie so weit, hat sich die Idee nicht bestätigt.\n"
            "- **Mögliches Ziel:** das Jahreshoch, oder – wenn die Aktie schon dort ist – das "
            "Doppelte des Risikos.\n\n"
            "Das sind Denkanstöße zur eigenen Prüfung, keine Kaufempfehlungen.")


# --------------------------------------------------------------------------- #
# Was heute auffällt
# --------------------------------------------------------------------------- #
def pick_table(df: pd.DataFrame, columns: dict, key: str) -> None:
    if df.empty:
        st.caption("Heute nichts Auffälliges.")
        return
    view = df[list(columns)].reset_index(drop=True)
    event = st.dataframe(view, column_config=columns, hide_index=True, use_container_width=True,
                         height=min(36 * (len(view) + 1) + 3, 400), on_select="rerun",
                         selection_mode="single-row", key=key)
    rows = event.selection.rows if event and event.selection else []
    if rows:
        c.open_analysis(view.iloc[rows[0]]["ticker"])


def anomalies_section(scan: pd.DataFrame) -> None:
    s.section("⚡ Was heute auffällt", "Zeile anklicken zum Prüfen")
    base = {
        "ticker": st.column_config.TextColumn("Kürzel"),
        "name": st.column_config.TextColumn("Name", width="medium"),
        "close": st.column_config.NumberColumn("Kurs", format="%.2f"),
        "chg_1d": st.column_config.NumberColumn("Heute %", format="%+.1f"),
    }
    vol = {**base, "vol_ratio": st.column_config.NumberColumn(
        "Handel × normal", format="%.1f", help="Wie viel mehr gehandelt wurde als üblich")}
    gap = {**base, "gap_pct": st.column_config.NumberColumn(
        "Sprung zum Start %", format="%+.1f", help="Unterschied Eröffnung zu gestern")}
    hi = {**base, "perf_3m": st.column_config.NumberColumn("3 Monate %", format="%+.1f"),
          "rs_rank": st.column_config.ProgressColumn("Stärker als … % der Aktien", min_value=0,
                                                     max_value=100, format="%.0f")}
    warn = {**base, "signals": st.column_config.TextColumn("Was ist passiert?", width="medium")}

    tabs = st.tabs(["🔊 Ungewöhnlich viel Handel", "↕️ Kurssprünge", "🚀 Größte Gewinner",
                    "📉 Größte Verlierer", "🏔️ Neues Jahreshoch", "⚠️ Warnsignale"])
    with tabs[0]:
        st.caption("Hier wurde deutlich mehr gehandelt als sonst – oft steckt eine Nachricht dahinter.")
        df = scan[scan["vol_ratio"] >= 2].sort_values("vol_ratio", ascending=False).head(15)
        pick_table(df, vol, "t_vol")
    with tabs[1]:
        st.caption("Diese Aktien sind mit einem großen Sprung in den Tag gestartet.")
        df = scan[scan["gap_pct"].abs() >= 4]
        df = df.reindex(df["gap_pct"].abs().sort_values(ascending=False).index).head(15)
        pick_table(df, gap, "t_gap")
    with tabs[2]:
        pick_table(scan.sort_values("chg_1d", ascending=False).head(15), vol, "t_win")
    with tabs[3]:
        pick_table(scan.sort_values("chg_1d").head(15), vol, "t_lose")
    with tabs[4]:
        st.caption("So teuer wie seit einem Jahr nicht – Zeichen von Stärke.")
        df = scan[scan["new_52w_high"]].sort_values("perf_3m", ascending=False).head(15)
        pick_table(df, hi, "t_high")
    with tabs[5]:
        st.caption("Bei diesen bekannten Aktien hat sich der Trend verschlechtert.")
        df = scan[scan["has_warning"]].sort_values("avg_dollar_volume", ascending=False).head(15)
        pick_table(df, warn, "t_warn")


def _search_picked() -> None:
    t = st.session_state.get("dash_search")
    if t:
        st.session_state["_open_from_search"] = t


def _search_typed() -> None:
    t = st.session_state.get("dash_search_free", "").strip().upper()
    if t:
        st.session_state["_open_from_search"] = t


def search_bar(df: pd.DataFrame) -> None:
    """Suchleiste: Aktie eintippen -> ausführliche Prüfung öffnen."""
    if st.session_state.get("_open_from_search"):
        ticker = st.session_state.pop("_open_from_search")
        st.session_state["dash_search"] = None
        st.session_state["dash_search_free"] = ""
        c.open_analysis(ticker)
    labels = {t: f"{t} – {n}" for t, n in zip(df["ticker"], df["name"])} if len(df) else {}
    left, right = st.columns([3, 1])
    left.selectbox("🔍 Aktie suchen", list(labels), index=None, key="dash_search",
                   format_func=lambda t: labels.get(t, t), on_change=_search_picked,
                   placeholder="Name oder Kürzel eintippen, z. B. Apple, SAP, Rheinmetall …",
                   label_visibility="collapsed")
    right.text_input("Anderes Kürzel", key="dash_search_free", on_change=_search_typed,
                     placeholder="… oder Kürzel, z. B. TSLA", label_visibility="collapsed",
                     help="Für Aktien, die nicht im Scan sind. Deutsche Aktien enden auf .DE")
    st.caption("Tippe eine Aktie ein – die App prüft sie für dich: Trend, Stärke, Zeitpunkt, "
               "ein möglicher Plan und auf Wunsch eine KI-Zusammenfassung.")


def data_warnings(stored: dict) -> None:
    """Hinweise, wenn die Daten alt sind oder Yahoo viele Aktien nicht geliefert hat."""
    if not stored:
        return
    age = pd.Timestamp.now(tz="UTC") - pd.Timestamp(stored["generated_at"])
    workdays = len(pd.bdate_range(pd.Timestamp(stored["generated_at"]).tz_convert(None).normalize(),
                                  pd.Timestamp.now().normalize())) - 1
    if workdays >= 2:
        st.warning(f"Die Daten sind {age.days} Tage alt – die automatische Aktualisierung hat "
                   "wohl nicht geklappt. Drücke links auf **Markt jetzt aktualisieren** oder schau "
                   "auf GitHub unter Actions nach.", icon="⏰")
    failed, total = stored.get("failed_count", 0), stored.get("universe_count", 0) or 1
    if failed / total > 0.05:
        st.warning(f"Yahoo Finance hat beim letzten Lauf für {failed} von {total} Aktien keine Kurse "
                   "geliefert. Einige Ideen und Zahlen können fehlen. Meist ist das beim nächsten "
                   "Lauf wieder in Ordnung.", icon="📡")


def render() -> None:
    df = c.scan()
    stored = c.stored_regime()
    sub = ""
    if stored:
        sub = (f"Daten vom {c.berlin(stored['generated_at'])} · "
               f"{stored.get('liquid_count', len(df))} Aktien geprüft")
    s.page_head('<span class="tt-logo">tradetalk</span>', sub)
    search_bar(df)
    data_warnings(stored)
    report_section()
    breadth_section(stored)
    sectors.render_section()
    if df.empty:
        st.error("Noch keine Scan-Ergebnisse vorhanden.")
        return
    if not c.has_signals(df):
        st.info("Die Trade-Ideen erscheinen nach der nächsten Aktualisierung.")
        return
    ideas_section(df)
    anomalies_section(df)
    s.html_block(f'<div class="tt-disclaimer">{s.esc(c.DISCLAIMER)}</div>')
