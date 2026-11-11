# tradetalk – Hinweise für neue Sitzungen

## 1. Projektziel
- Trading-Info-App für **Swingtrading** (Haltedauer Tage bis Wochen) für **Einsteiger ohne Fachwissen**.
- Scannt täglich den **ganzen Markt USA** (Nasdaq-Trader-Listen) **+ DE** (DAX, MDAX, SDAX, TecDAX).
- Zeigt Börsenwetter, Trade-Ideen mit Begründung und Plan (Einstieg/Ausstieg/Ziel), Analyse je Aktie.
- Denkanstöße, **keine Anlageberatung** – das steht so auch in der App.

## 2. Architektur
- **Daten**: Kurse yfinance (kostenlos); US-Ticker nasdaqtrader.com; DE-Indexmitglieder onvista
  (Seite liefert max. 50 → zusätzlich `?order=DESC`); Branchen über US-Sektor-ETFs (XLK, …).
- **Tageslauf** `src/run_daily.py`: universe → fetch → filters → Signale/Scores → Marktumfeld →
  Erfolgskontrolle → schreibt `results/`. Läuft in GitHub Actions (Cron 16:45 + 22:30 UTC, Mo–Fr,
  plus manuell/App-Knopf). Kurs-Cache `data/prices` über `actions/cache`, nur `results/` wird committet.
- `src/universe.py` Tickerliste (Filter: ETFs, Warrants, Units, Vorzugsaktien, Rights, Anleihen raus;
  `symbol_overrides` in config für onvista≠Yahoo, z. B. A4L→SLYG).
- `src/fetch.py` OHLCV als Parquet je Ticker, inkrementell, Batches à 100, `data/failed.csv`.
- `src/filters.py` Liquiditätsfilter (Kurs ≥ 5, Ø Umsatz 20 T ≥ 5 Mio, Daten ≤ 7 Tage alt).
- `src/signals.py` Kennzahlen (RSI, ATR, SMA, rel. Stärke), Signale, Plan (Ausstieg = Kurs − 2×ATR,
  Ziel = Jahreshoch oder 2× Risiko), Score + Sterne.
- `src/market_regime.py` Börsenwetter (S&P 500, Nasdaq, DAX vs. SMA50/200 + VIX → Punkte).
- `src/tracking.py` Ideen-Protokoll + Auswertung; `src/backtest.py` Rückblick (nur lokal, einmalig).
- `src/notify.py` Telegram-Nachrichten nach dem Lauf (nur wenn Secrets gesetzt).
- `app.py` Streamlit-Navigation; `tt_app/`: `dashboard`, `analysis`, `scanner`, `trading` +
  `paper` (Übungstrading: 50.000 € Spielgeld, 1 € Gebühr, Bruchstücke, Orders warten bei
  geschlossener Börse, Auto-Verkauf bei Ausstieg/Ziel), `depot` (Merkliste, Einstellungen),
  `calendar_page`, `performance`, `learn`, `explain` (Texte in
  Alltagssprache), `style` (CSS/HTML-Bausteine), `common` (Daten/Charts), `storage` (Gist),
  `sectors`, `updater` (Aktualisieren-Knopf → GitHub API), `ai` (Claude-Zusammenfassung).
- `results/`: `scan_latest.parquet`, `market_regime.json`, `regime_history.csv`, `ideas_log.csv`,
  `ideas_eval.parquet` (vom Bot) und `ideas_backtest.parquet` (statisch, lokal erzeugt).
- `config.yaml` alle Grenzen/URLs/Sektoren; `.streamlit/config.toml` dunkles Theme.

## 3. Entscheidungen und warum
- **Liquiditätsfilter**: nur handelbare Aktien (Spreads, Manipulation, Datenqualität).
- **Kostenlose Daten** (yfinance, onvista): kein Budget; dafür Lücken/Sperren einkalkulieren.
- **Online-Betrieb** GitHub Actions + Streamlit Community Cloud: kostenlos, Mac muss nicht laufen.
- Nutzerdaten (Merkliste/Depot) in **privatem Gist**, nicht im Repo: Commits würden die
  Streamlit-App jedes Mal neu deployen.
- Backtest in eigener statischer Datei: tägliche Commits sollen klein bleiben.
- **Oberfläche komplett Deutsch, ohne Fachbegriffe** (Zielgruppe Laien); Begriffe per Tooltip erklärt.
- KI: Claude `claude-opus-5-5`, effort low, `fallbacks: "default"`, nur auf Knopfdruck (Kosten).

## 4. Starten und testen (aus dem Projektordner)
- Venv: `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`
- Ganzer Lauf: `.venv/bin/python src/run_daily.py` (~6 Min inkrementell, ~10 Min initial)
- Nur auswerten ohne Download: `.venv/bin/python src/run_daily.py --skip-fetch`
- Einzelteile: `src/fetch.py --limit 200` / `--tickers AAPL SAP.DE`, `src/filters.py`,
  `src/market_regime.py`, `src/notify.py`, `src/backtest.py --weeks 100`
- App: `.venv/bin/streamlit run app.py --server.headless true --server.port 8502`
  (Server nach Code-Änderungen **neu starten** – geänderte Module werden sonst nicht neu geladen)
- Testen im Browser: alle Seiten öffnen, auf Tracebacks prüfen, Desktop + Handybreite.
- **Vor dem Commit** lokale Ergebnisse zurücksetzen: `git checkout -- results/` und neue lokale
  Dateien in `results/` löschen (außer bewusst gewolltem `ideas_backtest.parquet`).

## 5. Aktueller Stand (fertig)
- Universum ~6.100 Ticker, ~2.860 liquide; Kurse 3 Jahre; Workflow läuft erfolgreich.
- App online (privat) auf Streamlit; Aktualisieren-Knopf funktioniert (Token in Secrets).
- Dashboard: Suchleiste, Börsenwetter-Bericht, Marktbreite, Branchen, Trade-Ideen-Karten, Auffälligkeiten.
- Aktienanalyse: Auf einen Blick, 4 Prüfschritte, Chart, „Dein möglicher Plan“ + Rechner, Termine,
  Nachrichten, Unternehmen, Merken, Übungstrade, KI-Zusammenfassung.
- Übungstrading (Depot, Handeln, Aktivität, Ideen-Check), Mein Bereich, Termine,
  Erfolgskontrolle (Rückblick: Ø +0,5 %/Idee, 33 % Treffer), Lern-Ecke.
- Testen ohne Browser: `streamlit.testing.v1.AppTest` (Funktions-Seiten nicht per switch_page).
- Streamlit: `width="stretch"` statt `use_container_width` (bei plotly_chart weglassen).

## 6. Bekannte Probleme / offen
- Eingerichtet (11.11.2026): Gist-Speicher (Token hat Gists RW) und Anthropic-Key in Streamlit –
  beides online getestet. Noch offen: Telegram-Secrets (optional).
- KI-Zusammenfassung lokal nicht testbar (anthropic 1.x braucht Python ≥ 3.10, lokal 3.9).
- Ideen nur knapp profitabel; Backtest ohne Börsenwetter-Filter, mit Survivorship-Bias.
- 16:45-UTC-Lauf: US-Tagesvolumen unvollständig → Volumen-Signale unterschätzt.
- Analyse rechnet live, Dashboard mit Scan-Stand → Abweichungen möglich (Hinweis wird angezeigt).
- yfinance-News zeitweise gestört; onvista-Scraping kann bei Seitenumbau brechen.
- Börsenkürzel „F“ in otherlisted.txt unbekannt (vermutlich NYSE Texas) → „Code F“.
- GitHub-Token (fine-grained) läuft am **09.02.2027** ab.
- `gh` (Intel-Build) liegt unter `~/Desktop/gh_2.103.3_macOS_amd64/bin/gh`, angemeldet; als
  Git-Credential-Helper nur in diesem Repo eingetragen (`gh auth setup-git` scheitert wegen Rosetta).
- Markttermine (Fed/EZB) nicht hinterlegt – `events:` in config.yaml ist leer.

## 7. Nächste Schritte
- Backtest mit Börsenwetter-Filter, Regeln anhand der Erfolgskontrolle verbessern.
- Branche je Aktie im Scan (Filter „starke Branche“), Markttermine pflegen.
- Optional: echte Sektor-Daten je Aktie, mehr Märkte, bessere Handy-Ansicht.

## 8. Regeln für die Arbeit
- Oberfläche **auf Deutsch, verständlich für Laien**, keine Fachbegriffe ohne Erklärung.
- Keine Anlageberatung formulieren („Denkanstoß“, „mögliche Überlegung“), Disclaimer behalten.
- Vor größeren Änderungen **kurz den Plan vorstellen**; nach Änderungen **lokal testen** (Lauf + App).
- Ehrlich berichten (auch schlechte Backtest-Ergebnisse), nichts schönreden.
- Nutzer ist Einsteiger: Anleitungen Schritt für Schritt, Klickpfade konkret benennen.
- Keine Tokens/Passwörter eingeben oder speichern; Secrets nur über GitHub/Streamlit-Secrets.
- Python 3.9 lokal, 3.11 in CI/Streamlit – Code muss auf beiden laufen.
- Push: `git pull --rebase origin main && git push` (über gh-Credential-Helper) oder der Nutzer per
  GitHub Desktop. Der Bot committet `results/` – vor dem Push immer erst pullen.
