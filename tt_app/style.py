"""Gestaltung: Stylesheet und kleine HTML-Bausteine (Kacheln, Pills, Sparklines)."""

from __future__ import annotations

import html
import math
from typing import Iterable

import streamlit as st

UP = "#26d07c"
DOWN = "#f0506e"
WARN = "#f5a524"
INFO = "#5b9cf6"
ACCENT = "#2dd4a3"
MUTED = "#8b95a7"
SURFACE = "#131925"
BORDER = "#222a38"

VERDICT_COLOR = {"Rückenwind": UP, "neutral": WARN, "Gegenwind": DOWN}

CSS = f"""
<style>
:root {{
  --up:{UP}; --down:{DOWN}; --warn:{WARN}; --info:{INFO}; --accent:{ACCENT};
  --muted:{MUTED}; --surface:{SURFACE}; --border:{BORDER};
}}
/* Grundlayout */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }}
[data-testid="stAppDeployButton"], [data-testid="stDecoration"] {{ display:none; }}
h1, h2, h3 {{ letter-spacing: -0.02em; }}
[data-testid="stMetricValue"], .tt-num {{ font-variant-numeric: tabular-nums; }}
[data-testid="stSidebarNav"] a span {{ font-weight: 600; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
hr {{ border-color: var(--border) !important; }}

/* Seitentitel */
.tt-pagehead {{ display:flex; align-items:baseline; justify-content:space-between;
  gap:1rem; flex-wrap:wrap; margin-bottom:1.2rem; }}
.tt-pagehead h1 {{ font-size:1.9rem; margin:0; padding:0; }}
.tt-pagehead .tt-sub {{ color:var(--muted); font-size:.85rem; }}
.tt-logo {{ background:linear-gradient(90deg,var(--accent),var(--info));
  -webkit-background-clip:text; background-clip:text; color:transparent; }}

/* Abschnittstitel */
.tt-section {{ display:flex; align-items:center; gap:.6rem; margin:1.8rem 0 .8rem; }}
.tt-section h3 {{ margin:0; padding:0; font-size:1.2rem; }}
.tt-section .tt-count {{ color:var(--muted); font-size:.8rem; font-weight:600;
  background:var(--surface); border:1px solid var(--border); border-radius:99px;
  padding:.1rem .55rem; }}

/* Hero (Marktlage) */
.tt-hero {{ position:relative; overflow:hidden; border-radius:16px; padding:1.4rem 1.6rem;
  border:1px solid var(--border);
  background:radial-gradient(120% 140% at 0% 0%, var(--glow) 0%, transparent 55%),
             linear-gradient(180deg,#141a27,#10151f); }}
.tt-hero .tt-label {{ color:var(--muted); font-size:.78rem; font-weight:700;
  text-transform:uppercase; letter-spacing:.08em; }}
.tt-hero .tt-verdict {{ font-size:2.4rem; font-weight:800; line-height:1.1; margin:.2rem 0 .4rem; }}
.tt-hero .tt-text {{ color:#c4cbd8; font-size:.95rem; max-width:640px; }}
.tt-hero-grid {{ display:grid; grid-template-columns: minmax(260px,1.1fr) 2fr; gap:1.6rem;
  align-items:center; }}
@media (max-width: 900px) {{ .tt-hero-grid {{ grid-template-columns:1fr; }} }}
.tt-scale {{ position:relative; height:8px; border-radius:99px; margin:.9rem 0 .35rem;
  background:linear-gradient(90deg,var(--down),var(--warn) 50%,var(--up)); opacity:.9; }}
.tt-scale .tt-marker {{ position:absolute; top:-5px; width:18px; height:18px; border-radius:50%;
  background:#fff; border:3px solid #0b0e14; transform:translateX(-50%);
  box-shadow:0 0 0 2px rgba(255,255,255,.25); }}
.tt-scale-labels {{ display:flex; justify-content:space-between; color:var(--muted);
  font-size:.72rem; }}

/* Kacheln */
.tt-grid {{ display:grid; gap:.8rem; }}
.tt-grid.c4 {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
.tt-grid.c5 {{ grid-template-columns:repeat(5,minmax(0,1fr)); }}
.tt-grid.c3 {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
.tt-grid.c6 {{ grid-template-columns:repeat(6,minmax(0,1fr)); }}
@media (max-width: 1100px) {{ .tt-grid.c5, .tt-grid.c6 {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} }}
@media (max-width: 900px) {{ .tt-grid.c4, .tt-grid.c3 {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
@media (max-width: 560px) {{ .tt-grid.c3 {{ grid-template-columns:1fr; }}
  .tt-grid.c4, .tt-grid.c5, .tt-grid.c6 {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .tt-tile .tt-v {{ font-size:1.2rem; }} .tt-hero {{ padding:1.1rem; }}
  .tt-hero .tt-verdict {{ font-size:2rem; }} }}
.tt-tile {{ background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:.9rem 1rem; min-width:0; }}
.tt-tile .tt-k {{ color:var(--muted); font-size:.76rem; font-weight:600; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.tt-tile .tt-v {{ font-size:1.45rem; font-weight:700; margin-top:.15rem;
  font-variant-numeric:tabular-nums; white-space:nowrap; }}
.tt-tile .tt-s {{ font-size:.8rem; margin-top:.15rem; color:var(--muted); }}
.tt-tile .tt-row {{ display:flex; justify-content:space-between; align-items:flex-end; gap:.5rem; }}
.tt-bar {{ height:6px; border-radius:99px; background:#222a38; overflow:hidden; margin-top:.55rem;
  display:flex; }}
.tt-bar > span {{ display:block; height:100%; }}

/* Pills */
.tt-pill {{ display:inline-flex; align-items:center; gap:.3rem; font-size:.74rem; font-weight:600;
  padding:.18rem .55rem; border-radius:99px; border:1px solid transparent; white-space:nowrap;
  margin:0 .25rem .25rem 0; }}
.tt-pill.up {{ color:var(--up); background:rgba(38,208,124,.12); border-color:rgba(38,208,124,.25); }}
.tt-pill.down {{ color:var(--down); background:rgba(240,80,110,.12); border-color:rgba(240,80,110,.25); }}
.tt-pill.warn {{ color:var(--warn); background:rgba(245,165,36,.12); border-color:rgba(245,165,36,.25); }}
.tt-pill.info {{ color:var(--info); background:rgba(91,156,246,.12); border-color:rgba(91,156,246,.25); }}
.tt-pill.muted {{ color:#c4cbd8; background:#1a2130; border-color:var(--border); }}
.up-t {{ color:var(--up); }} .down-t {{ color:var(--down); }} .warn-t {{ color:var(--warn); }}
.muted-t {{ color:var(--muted); }}

/* Setup-Karten */
a.tt-card, a.tt-card:hover {{ text-decoration:none; color:inherit; }}
.tt-card {{ display:block; background:var(--surface); border:1px solid var(--border);
  border-radius:16px; padding:1rem 1.05rem .9rem; transition:all .15s ease; height:100%; }}
.tt-card:hover {{ border-color:rgba(45,212,163,.55); transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(0,0,0,.35); }}
.tt-card .tt-top {{ display:flex; justify-content:space-between; gap:.6rem; }}
.tt-card .tt-tk {{ font-size:1.15rem; font-weight:800; letter-spacing:-.01em; }}
.tt-card .tt-nm {{ color:var(--muted); font-size:.78rem; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; max-width:180px; }}
.tt-card .tt-px {{ text-align:right; font-weight:700; font-variant-numeric:tabular-nums; }}
.tt-card .tt-px small {{ color:var(--muted); font-weight:500; }}
.tt-card .tt-spark {{ margin:.55rem 0 .45rem; }}
.tt-card .tt-stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:.3rem;
  border-top:1px solid var(--border); padding-top:.6rem; margin-top:.35rem; }}
.tt-card .tt-stats div {{ font-size:.7rem; color:var(--muted); }}
.tt-card .tt-stats b {{ display:block; color:#e6eaf2; font-size:.85rem; font-variant-numeric:tabular-nums; }}
.tt-score {{ font-size:.7rem; font-weight:700; color:#0b0e14; background:var(--accent);
  border-radius:6px; padding:.05rem .4rem; margin-left:.35rem; vertical-align:middle; }}

/* Analyse */
.tt-quote {{ display:flex; align-items:flex-end; gap:1rem; flex-wrap:wrap; margin:.3rem 0 1rem; }}
.tt-quote .tt-price {{ font-size:2.6rem; font-weight:800; line-height:1; font-variant-numeric:tabular-nums; }}
.tt-quote .tt-chg {{ font-size:1.05rem; font-weight:700; }}
.tt-verdict-box {{ border-radius:14px; padding:1rem 1.1rem; border:1px solid var(--border);
  background:linear-gradient(180deg,var(--vbg),var(--surface) 70%); }}
.tt-verdict-box .tt-vt {{ font-size:1.35rem; font-weight:800; }}
.tt-list {{ list-style:none; padding:0; margin:.4rem 0 0; }}
.tt-list li {{ display:flex; gap:.55rem; padding:.45rem 0; border-bottom:1px solid var(--border);
  font-size:.88rem; line-height:1.35; }}
.tt-list li:last-child {{ border-bottom:none; }}
.tt-list .tt-ic {{ flex:0 0 18px; height:18px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:.7rem; font-weight:800; margin-top:.05rem; }}
.tt-list .pro .tt-ic {{ background:rgba(38,208,124,.18); color:var(--up); }}
.tt-list .con .tt-ic {{ background:rgba(240,80,110,.18); color:var(--down); }}
.tt-news a {{ color:#e6eaf2; text-decoration:none; font-weight:600; font-size:.9rem; }}
.tt-news a:hover {{ color:var(--accent); }}
.tt-news .tt-item {{ padding:.6rem 0; border-bottom:1px solid var(--border); }}
.tt-news .tt-meta {{ color:var(--muted); font-size:.75rem; margin-top:.15rem; }}
.tt-disclaimer {{ color:var(--muted); font-size:.75rem; margin-top:2rem; text-align:center; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def tone(x, neutral_band: float = 0.0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "muted"
    if x > neutral_band:
        return "up"
    if x < -neutral_band:
        return "down"
    return "muted"


def pill(text: str, kind: str = "muted") -> str:
    return f'<span class="tt-pill {kind}">{esc(text)}</span>'


def sparkline(values: Iterable[float], width: int = 260, height: int = 46,
              color: str | None = None, fill: bool = True) -> str:
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = width / (len(vals) - 1)
    pts = [(i * step, height - 3 - (v - lo) / span * (height - 6)) for i, v in enumerate(vals)]
    color = color or (UP if vals[-1] >= vals[0] else DOWN)
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = ""
    if fill:
        gid = f"g{abs(hash((len(vals), vals[0], vals[-1]))) % 10**8}"
        area = (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0%" stop-color="{color}" stop-opacity=".28"/>'
                f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
                f'<polygon fill="url(#{gid})" points="0,{height} {line} {width},{height}"/>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'preserveAspectRatio="none" role="img" aria-label="Kursverlauf">{area}'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" '
            f'stroke-linecap="round" points="{line}"/></svg>')


def tile(label: str, value: str, sub: str = "", extra: str = "") -> str:
    return (f'<div class="tt-tile"><div class="tt-k">{esc(label)}</div>'
            f'<div class="tt-v">{value}</div>'
            + (f'<div class="tt-s">{sub}</div>' if sub else "") + extra + "</div>")


def bar(parts: list[tuple[float, str]]) -> str:
    spans = "".join(f'<span style="width:{max(p, 0):.1f}%;background:{c}"></span>' for p, c in parts)
    return f'<div class="tt-bar">{spans}</div>'


def section(title: str, count: str | None = None) -> None:
    badge = f'<span class="tt-count">{esc(count)}</span>' if count else ""
    html_block(f'<div class="tt-section"><h3>{esc(title)}</h3>{badge}</div>')


def page_head(title_html: str, sub: str = "") -> None:
    html_block(f'<div class="tt-pagehead"><h1>{title_html}</h1>'
               f'<div class="tt-sub">{esc(sub)}</div></div>')
