# C3 Backend für Termine und Panel — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Home Assistant speichert Termine je Standort, rollt sie für den Horizont aus und schickt daraus Abwesenheiten, Fahrten (`trips`) und Ladeziele im Request. Actions und Websocket-Befehle sind die Schnittstelle, auf der C8 das Panel baut.

**Architecture:** Was C3 entscheidet, liegt in fünf neuen Modulen ohne Import aus Home Assistant, geprüft gegen erzeugte Termine, erzeugte Pläne und das vendorte Request-Schema: `termine.py` (Ausrollen), `pruefungen.py` (Meldungen aus 2.3, Actions und Felder), `terminbuch.py` (Serien, Absagen, Schritte), `terminanfrage.py` (Fragmente, IDs), `ansicht.py` (was das Panel liest). Drei Module verdrahten es: `terminverwaltung.py` (Store, Schritte, Meldungen, Auslöser), `aktionen.py`, `terminwebsocket.py`. C5 bekommt eine Quelle für Termine und Risiko, drei Auslöser und das Signal „plant". `__init__.py` startet C3 im `try` vor C5.

**Tech Stack:** Python 3.12 (`.venv` im ha-Repo), pytest, jsonschema, neu `tzdata` in den Testabhängigkeiten. Zur Laufzeit Home Assistant 2026.4.1.

**Spec:** `meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md`, Branch `c3-konfig-entitaeten`. Bindend ist die Spec, dieser Plan nicht.

## Zur Freigabe

**1. Präzisierungen der Spec.** Die Spec lässt Formen offen, auf die sich C8 verlassen muss. Vorschlag je Punkt; sie gehen als ein Commit in die C3-Spec, bevor gebaut wird (Diff in „Vor Task 1").

| # | Punkt | Vorschlag |
|---|---|---|
| 1 | `hints` | `{"type": "overlap"}` einmal, `{"type": "driver_busy", "vehicle": <Geräte-ID>}` einmal je anderem Fahrzeug |
| 2 | Meldung von `subscribe` | `event` ist der Name, etwa `"appointments"` |
| 3 | IDs `<eintrag>/<datum>/weg\|ziel` | gehören zur zugesagten Oberfläche; darüber ordnet C8 `reason` und `constraint_id` zu |
| 4 | `meteo_volt/appointments` | Rückkehr nach `start`, Abfahrt vor `end`, nach Abfahrt sortiert: ein laufender Termin gehört dazu |
| 5 | Planwerte eines laufenden Termins | `soc_at_departure` und `soc_after_trip` sind `null`, `running_until` die Rückkehr |
| 6 | `horizon_end` schon vorbei | zählt wie kein Plan: 14 Tage |
| 7 | Platzhalter der Warnungen | setzt das Backend in der Sprache von Home Assistant, wie C6: `15`/`15,5`, `Sa 19.09.`/`Sat 19 Sep` |
| 8 | `entries` beim Ändern | die angelegten oder geänderten Einträge, der mit den neuen Werten vorn |
| 9 | fehlendes `repeat` / `scope` | anlegen `once`, ändern bleibt die Wiederholung; `scope` fehlt heißt `this` |
| 10 | Reihenfolge der Fehler | Eintrag, Datum, Fahrzeug, Felder wie Tabelle 2.3, Umfang; gemeldet wird der erste |
| 11 | Absagen mit unbekanntem Schritt | wird ein eigener Schritt; leere Liste ist `eintrag_unbekannt` |
| 12 | ohne `config_entry` | der zuerst geladene Standort, auch bei mehreren, wie die Dev-Action |
| 13 | Fehler der Websocket-Befehle | `not_found`, `fahrzeug_unbekannt`, `invalid_format` |
| 14 | `site.vehicles` | nur Fahrzeuge mit Gerät aus C6; `grid_fees` negativ ist `null` wie im Request |
| 15 | Schritte | überleben das Neuladen des Eintrags, nicht den Neustart |
| 16 | C3 startet nicht | Request wie vor C3: ohne `risk`, `consumption: none` |
| 17 | Ausrollen scheitert im Lauf | der Lauf scheitert, der letzte Plan bleibt; ohne Termine lüde der Plan in der Abwesenheit |
| 18 | Test der Zeitumstellung | `tzdata` in den Testabhängigkeiten, wie im Brain |

**2. Die Test-venv bekommt `tzdata`.** Unter Windows kennt `ZoneInfo` ohne das Paket keine Zone, die Tests der Zeitumstellung (Spec Abschnitt 10) wären nicht baubar. Einmal `pip install`, eine Zeile in `tests/requirements-test.txt`, wie im Brain. Das weicht von „kein Venv-Update" aus C6 ab; `custom_components/` bleibt ohne neue Abhängigkeit.

## Global Constraints

- **Branch** `c3-konfig-entitaeten` im ha-Repo (Worktree `D:\Projekte\Meteo-Volt\meteo-volt-ha-c3`, von `beta`) und im Brain (Worktree `D:\Projekte\Meteo-Volt\meteo-volt-brain-c3`). Niemals nach `master` oder `main`.
- **Kein Merge nach `beta`, kein Push ohne Rückfrage.** Die Abnahme macht Patrick im Panel, zusammen mit C8. Bis dahin bleibt C3 auf seinem Branch, und C8 baut darauf.
- **Python:** `HAPY=../meteo-volt-ha/.venv/Scripts/python.exe`, im Brain `PY=../meteo-volt-brain/meteovolt_plan/.venv/Scripts/python.exe`. Ein blankes `python` ist der Windows-Store-Alias.
- **Die Suite ist vor jedem Commit grün:** `$HAPY -m pytest -q --rootdir . tests` aus dem ha-Worktree. Ausgangsstand: 316.
- **Die fünf reinen Module importieren nichts aus Home Assistant und nichts aus aiohttp.** Die Tests laden sie über ein Paket, dessen `__init__.py` nicht läuft.
- **Zeitpunkte nur in UTC vergleichen und subtrahieren** (`termine.utc`). Tragen zwei Zeitpunkte dasselbe `tzinfo`, rechnet Python auf der Wanduhr, über die Umstellung falsch.
- **Bestandsschutz:** Die sechs Sensoren, `meteo_volt_{entry_id}_{key}` und `hass.data[DOMAIN]` bleiben unberührt. C3 legt keine Entität an, `VERSION` bleibt 1. C3 wird außerhalb von C3 nur im `try` importiert, und kein Rückruf an `async_on_unload` gibt etwas zurück.
- **Die 35 Kontrakt-Artefakte werden nie von Hand geändert.**
- **Zeilenenden LF am gestagten Blob.** Vor jedem Commit gibt `git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done` nichts aus.
- **Code und Kommentare in ASCII** (`ue`, `ae`, `oe`), Übersetzungen und Markdown mit echten Umlauten.
- **Commit-Nachrichten** englisch, Imperativ, letzte Zeile `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Gegenproben ohne Bytecode-Cache:** `PYTHONDONTWRITEBYTECODE=1`. Eine gleich lange Verfälschung, in derselben Sekunde zurückgeschrieben, ließ Python sonst den alten Bytecode laden.
- **Auf dem VPS wird nichts ausgeführt.** Das Deployment des Plan-Dienstes wird vorgelegt (Task 11).
- **`<scratchpad>`** steht für das Scratchpad-Verzeichnis der ausführenden Sitzung. Was dort liegt, wird nicht committet.

## Dateien

| Datei | Verantwortung |
|---|---|
| `custom_components/meteo_volt/termine.py` | **neu.** Eintrag, Termin, Wiederholung, Ausnahmen, Zeitumstellung, Fenster |
| `custom_components/meteo_volt/pruefungen.py` | **neu.** Die 16 Schlüssel aus 2.3, geprüfte Werte, Warnungen, Neu planen, Actions mit Feldern |
| `custom_components/meteo_volt/terminbuch.py` | **neu.** Store-Inhalt, Anlegen, Ändern mit Umfang, Löschen, Absagen, Schritte, Rückgängig |
| `custom_components/meteo_volt/terminanfrage.py` | **neu.** Bis wohin ausgerollt wird, Fragmente je Fahrzeug, IDs und ihre Zerlegung |
| `custom_components/meteo_volt/ansicht.py` | **neu.** Termine mit Planwerten und Hinweisen, Plan je Fahrzeug, Preise |
| `custom_components/meteo_volt/standort.py` | **ergänzt.** `anfrage_bauen` nimmt `termine` und `risiko` |
| `custom_components/meteo_volt/plankoordinator.py` | **ergänzt.** Quelle für Termine, Signal „plant", Auslöser `termine`, `risiko`, `replan` |
| `custom_components/meteo_volt/const.py` | **ergänzt.** `SIGNAL_PLANUNG` |
| `custom_components/meteo_volt/terminverwaltung.py` | **neu.** Store je Standort, Schritte, Meldungen an das Panel, Auslöser an C5 |
| `custom_components/meteo_volt/aktionen.py` | **neu.** Die sieben Actions |
| `custom_components/meteo_volt/terminwebsocket.py` | **neu.** Die fünf Websocket-Befehle |
| `custom_components/meteo_volt/__init__.py` | **ergänzt.** C3 im `try` vor dem Start von C5, `async_remove_entry` |
| `custom_components/meteo_volt/services.yaml` | **ergänzt.** Die sieben Actions mit Auswahlfeldern |
| `custom_components/meteo_volt/translations/de.json`, `en.json` | **ergänzt.** `services` und `exceptions` |
| `tests/test_termine.py`, `test_pruefungen.py`, `test_terminbuch.py`, `test_terminanfrage.py`, `test_ansicht.py` | **neu.** |
| `tests/test_uebersetzungen.py`, `tests/test_verdrahtung.py` | **ergänzt.** Actions, Felder, Meldungen; C3 nur im `try` |
| `tests/requirements-test.txt` | **ergänzt.** `tzdata` |
| Brain: `docs/features/C3-konfig-entitaeten/spec.md`, `feature.md`, `trail.md` | Präzisierungen, Status `in-arbeit`, Verlauf |

**Was das Gate nicht sieht:** Home Assistant. Store auf der Platte, Actions, Websocket-Befehle, Signale, Rechte und die Verdrahtung prüft die Abnahme. Einmalig geprüft wird jeder benutzte Name gegen Home Assistant 2026.4.1, mit Gegenprobe (Task 10).

**Geprüft beim Schreiben dieses Plans, am 2026-09-18,** in einer Kopie des Worktrees mit dem Python des Brain (hat `tzdata`): alle Tasks grün, 428 Tests ohne die 16 Lock-Tests (dem Brain-Python fehlt `rfc8785`). Jede von 20 Verfälschungen machte ihren Test rot, erst nachdem drei Tests dazukamen: monatlich am 14. und 28., Absagen im selben Eintrag wie das Speichern, ein Fahrer ohne Überschneidung. Die Namensprüfung fand alle 74 Namen und scheiterte mit einem vertippten. Im Quelltext von 2026.4.1 bestätigt: `async_dispatcher_send` fängt Ausnahmen seiner Ziele ab, `websocket_api.async_register_command` braucht kein geladenes `websocket_api`, und `call_service` gibt `translation_key` und Platzhalter eines `ServiceValidationError` an den Websocket weiter.

---

## Vor Task 1: Spec präzisieren, Plan committen, `tzdata`

Erst nach Patricks Freigabe. Die Präzisierungen gehen zuerst in die Spec: Sie ist der einzige Kanal zu C8.

- [ ] **Step 1: Brain — die Spec präzisieren**

Im Brain-Worktree `D:\Projekte\Meteo-Volt\meteo-volt-brain-c3` diesen Diff auf `docs/features/C3-konfig-entitaeten/spec.md` anwenden (von Hand mit dem Editor, Hunk für Hunk):

```diff
--- a/docs/features/C3-konfig-entitaeten/spec.md
+++ b/docs/features/C3-konfig-entitaeten/spec.md
@@ -2,3 +2,3 @@
 
-Stand 2026-09-16
+Stand 2026-09-18
 
@@ -90,3 +90,4 @@ geht, solange diese Einträge seitdem nicht anders geändert wurden, sonst ist e
 Die Schritte liegen nur im Speicher: Ein Neustart vergisst sie, entschieden am 2026-09-16.
-Gehalten werden die letzten 50 je Standort. Das Risiko ist kein Schritt.
+Das Neuladen des Eintrags vergessen sie nicht. Gehalten werden die letzten 50 je Standort. Das
+Risiko ist kein Schritt.
 
@@ -158,3 +159,4 @@ des Admin-Horizonts. Das verlangt die [A0-Spec](../A0-kontrakt/spec.md) 3.6: Was
 liegt, wertet der Planer nicht aus. Gewählt werden die Termine eines Fahrzeugs, deren Rückkehr nach
-jetzt und deren Abfahrt vor dem Ende des Ausrollens liegt.
+jetzt und deren Abfahrt vor dem Ende des Ausrollens liegt. Ein `horizon_end`, das schon vorbei ist,
+zählt wie kein Plan: Sonst ginge nach einem langen Ausfall kein Termin mehr in den Request.
 
@@ -210,5 +212,18 @@ Aufrufer sie verlangt.
 - **`warnings`** ist eine Liste aus `key`, `field` und `placeholders`.
+- **Die Platzhalter setzt das Backend** in der Sprache von Home Assistant, wie C6: `{min}` als Zahl
+  wie `15` oder `15,5`, `{datum}` als `Sa 19.09.` oder `Sat 19 Sep`, `{fahrer}` als Name der Person,
+  `{fahrzeug}` als Titel des Fahrzeugs. `fahrer_doppelt` nennt den ersten Konflikt.
+- **`entries`** sind die Einträge, die der Schritt angelegt oder geändert hat; der mit den neuen
+  Werten steht vorn.
+- **Fehlt `repeat`,** gilt beim Anlegen `once` und beim Ändern die bisherige Wiederholung. Sonst
+  machte ein Ändern ohne das Feld aus einer Serie still einen einmaligen Termin. **Fehlt `scope`,**
+  gilt `this`.
+- **Gemeldet wird der erste Fehler,** geprüft in dieser Reihenfolge: Eintrag, Datum, Fahrzeug, die
+  Felder in der Reihenfolge der Tabelle 2.3, zuletzt der Umfang.
+- **Nennt `cancel_appointments` einen Schritt, den es nicht mehr gibt,** etwa nach einem Neustart,
+  wird das Absagen ein eigener Schritt. Eine leere Liste ist `eintrag_unbekannt`.
 - **`update_appointment` und `delete_appointment`** übergehen `scope` an einem einmaligen Termin.
 - **Gibt es mehrere Standorte**, bestimmt das Fahrzeug den Standort. `set_risk` und `replan` nehmen
-  dann zusätzlich `config_entry`; bei einem Standort darf es fehlen.
+  dann zusätzlich `config_entry`. Fehlt es, gilt der zuerst geladene Standort, wie bei der
+  Dev-Action.
 - **`replan`** plant sofort, ohne Bündelung, und wartet einen laufenden Aufruf ab, wie die
@@ -222,3 +237,5 @@ Aufrufer sie verlangt.
 **Jeder Nutzer darf lesen.** Zeitpunkte sind ISO 8601 mit Offset. Jeder Befehl nimmt optional
-`config_entry`; ohne meint er den einzigen Standort.
+`config_entry`; ohne meint er den zuerst geladenen Standort. Einen Fehler meldet ein Befehl mit dem
+Code `not_found` ohne Standort, `fahrzeug_unbekannt` für ein Gerät, das kein Fahrzeug dieses
+Standorts ist, und `invalid_format` für `start` oder `end` ohne ISO 8601.
 
@@ -227,3 +244,3 @@ Aufrufer sie verlangt.
 | `meteo_volt/site` | – | `risk`, `grid_fees` oder `null`, `vehicles`, `persons` |
-| `meteo_volt/appointments` | `start`, `end`, `vehicle` optional | die Termine im Zeitraum |
+| `meteo_volt/appointments` | `start`, `end`, `vehicle` optional | die Termine, deren Rückkehr nach `start` und deren Abfahrt vor `end` liegt, nach Abfahrt sortiert |
 | `meteo_volt/plan` | `vehicle` | den Plan des Fahrzeugs |
@@ -233,4 +250,6 @@ Aufrufer sie verlangt.
 **`vehicles`:** `vehicle` (Geräte-ID), `title`, `soc_min_pct`, `soc_max_pct`, `max_charge_kw` und
-`soc_pct`, der Ladestand jetzt nach `ladestand_lesen`, sonst `null`. **`persons`:** `entity_id` und
-`name` jeder `person`-Entität.
+`soc_pct`, der Ladestand jetzt nach `ladestand_lesen`, sonst `null`. Genannt werden die Fahrzeuge
+mit Gerät aus C6: Nur sie lassen sich über die Geräte-ID ansprechen. **`persons`:** `entity_id` und
+`name` jeder `person`-Entität. `grid_fees` ist `null`, wenn es fehlt oder negativ ist, wie im
+Request (C5-Spec Abschnitt 4).
 
@@ -248,5 +267,6 @@ Aufrufer sie verlangt.
 `plan` ist `null` für Termine hinter dem `horizon_end` und ohne brauchbaren Plan (C5-Spec
-Abschnitt 8). **`hints`** nennt `overlap`, wenn dasselbe Fahrzeug zur selben Zeit einen anderen
-Termin hat, und `driver_busy` mit Fahrzeug, wenn derselbe Fahrer zur selben Zeit mit einem anderen
-unterwegs ist.
+Abschnitt 8). Läuft der Termin schon, gibt es keinen Slot mit der Abfahrt: `soc_at_departure` und
+`soc_after_trip` sind dann `null`. **`hints`** ist eine Liste: `{"type": "overlap"}` einmal, wenn
+dasselbe Fahrzeug zur selben Zeit einen anderen Termin hat, und `{"type": "driver_busy", "vehicle":
+<Geräte-ID>}` einmal je anderem Fahrzeug, mit dem derselbe Fahrer zur selben Zeit unterwegs ist.
 
@@ -268,3 +288,4 @@ C3 nicht, entschieden am 2026-09-16: Nur der Admin-Tarif brächte sie mit
 **`meteo_volt/subscribe`** meldet `appointments`, `site`, `plan`, `planning` und `prices`, jeweils
-ohne Inhalt. Das Panel liest danach neu. Gemeldet wird jede Änderung, auch die anderer Nutzer.
+ohne Inhalt: Das `event` der Websocket-Meldung ist der Name, etwa `"appointments"`. Das Panel liest
+danach neu. Gemeldet wird jede Änderung, auch die anderer Nutzer.
 
@@ -295,2 +316,5 @@ neu an der zugesagten Oberfläche aus C5-Spec Abschnitt 9.
 - Kein Rückruf an `async_on_unload` gibt etwas zurück.
+- **Scheitert der Start von C3,** geht der Request wie vor C3 raus: ohne `risk`, mit `consumption:
+  none`. Scheitert das Ausrollen in einem Lauf, scheitert der Lauf, und der letzte Plan bleibt: Ein
+  Plan ohne die Termine lüde in der Abwesenheit.
 - Ohne Termin und ohne gesetztes Risiko gibt es keine Datei. Der Request trägt dann zusätzlich
@@ -302,5 +326,6 @@ neu an der zugesagten Oberfläche aus C5-Spec Abschnitt 9.
 
-Darauf darf sich `C8` verlassen: die Semantik aus Abschnitt 2, die Schlüssel aus 2.3, die Actions
-aus Abschnitt 5 mit Feldern und Antworten, die Websocket-Befehle und Meldungen aus Abschnitt 6.
-Alles andere ist nicht zugesagt.
+Darauf darf sich `C8` verlassen: die Semantik aus Abschnitt 2, die Schlüssel aus 2.3, die Form der
+IDs aus Abschnitt 4, die Actions aus Abschnitt 5 mit Feldern und Antworten, die Websocket-Befehle
+und Meldungen aus Abschnitt 6. Alles andere ist nicht zugesagt. Über die IDs ordnet C8 `reason` und
+`constraint_id` einem Termin zu.
 
@@ -312,3 +337,5 @@ ergibt nur mit der Datei Sinn, die es ausliefert.
 **Automatisch** im ha-Repo, die Logik per Pfad geladen wie `tests/test_standort.py`. Bekäme sie
-einen Import aus Home Assistant oder aiohttp, scheiterte schon das Laden.
+einen Import aus Home Assistant oder aiohttp, scheiterte schon das Laden. Die Zeitumstellung prüft
+der Test in `Europe/Berlin`; unter Windows braucht das `tzdata` in den Testabhängigkeiten, wie im
+Brain.
 
```

- [ ] **Step 2: Brain — Status und Verlauf**

In `docs/features/C3-konfig-entitaeten/feature.md` ersetzen:

```toml
status = "spezifiziert"
```

durch:

```toml
status = "in-arbeit"
```

`docs/features/C3-konfig-entitaeten/trail.md` neu anlegen:

```markdown
# Trail — C3 Backend für Termine und Panel

Wächst per Anhängen. Nichts zitiert diese Datei.

## 2026-09-18 — Präzisierungen vor dem Bau

Beim Umsetzungsplan fielen 18 Formen auf, die die Spec offen ließ und auf die sich C8 verlassen
muss: Hinweise und Meldungen, die IDs als zugesagte Oberfläche, Auswahl und Planwerte laufender
Termine, die Reihenfolge der Fehler, ein fehlendes `repeat`, ein abgelaufenes `horizon_end` und
was ohne C3 gilt. Vorgeschlagen im Umsetzungsplan im ha-Repo, freigegeben von Patrick, dann in die
Spec.

Die Test-venv im ha-Repo bekommt `tzdata`: ohne das Paket kennt `ZoneInfo` unter Windows keine
Zone, und die Tests der Zeitumstellung wären nicht baubar.
```

Liegt die Freigabe nicht am 2026-09-18, steht in der Überschrift ihr Datum.

- [ ] **Step 3: Brain — Doku erzeugen, Gate, Commit**

```bash
cd /d/Projekte/Meteo-Volt/meteo-volt-brain-c3
PY=../meteo-volt-brain/meteovolt_plan/.venv/Scripts/python.exe
$PY scripts/build_docs.py
$PY scripts/run_tests.py -q
```

Expected: das Gate grün, `FEATURES.md` und `board/board.html` zeigen C3 „in Arbeit".

```bash
git add docs/features/C3-konfig-entitaeten/spec.md docs/features/C3-konfig-entitaeten/feature.md docs/features/C3-konfig-entitaeten/trail.md docs/FEATURES.md docs/board/board.html
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Settle the forms C8 relies on before C3 is built

Hints, subscription events, the constraint IDs as promised interface,
running appointments, the order of errors, a missing repeat, an
expired horizon and the request without C3. The ha test venv gets
tzdata for the daylight saving tests.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 4: ha — `tzdata` in die Testabhängigkeiten**

Im ha-Worktree `D:\Projekte\Meteo-Volt\meteo-volt-ha-c3`:

```diff
--- a/tests/requirements-test.txt
+++ b/tests/requirements-test.txt
@@ -2,2 +2,5 @@ pytest>=8
 jsonschema>=4.21
 rfc8785>=0.1.4
+# Ohne tzdata ist ZoneInfo("Europe/Berlin") unter Windows nicht baubar, und die Tests
+# der Zeitumstellung scheitern schon beim Laden. Wie im Brain, requirements-dev.txt.
+tzdata>=2024.1; sys_platform == "win32"
```

```bash
cd /d/Projekte/Meteo-Volt/meteo-volt-ha-c3
HAPY=../meteo-volt-ha/.venv/Scripts/python.exe
$HAPY -m pip install -r tests/requirements-test.txt
$HAPY -c "import zoneinfo; print(zoneinfo.ZoneInfo('Europe/Berlin'))"
$HAPY -m pytest -q --rootdir . tests
```

Expected: `Europe/Berlin`, danach `316 passed`.

- [ ] **Step 5: ha — Plan und Testabhängigkeit committen**

```bash
git add docs/superpowers/plans/2026-09-18-c3-konfig-entitaeten.md tests/requirements-test.txt
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Plan C3, the backend for appointments and the panel

The daylight saving tests need tzdata on Windows, as in the brain.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 1: `termine.py` — Wiederholung, Ausnahmen, Zeitumstellung

**Files:**
- Create: `custom_components/meteo_volt/termine.py`
- Test: `tests/test_termine.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - Konstanten `EINMALIG`, `TAEGLICH`, `WERKTAGS`, `WOECHENTLICH`, `MONATLICH`, `JAEHRLICH`, `WIEDERHOLUNGEN`, `ABSTAND`; die Store-Felder `ID`, `FAHRZEUG`, `ABFAHRT`, `DAUER`, `WIEDERHOLUNG`, `STRECKE`, `FAHRER`, `LADESTAND`, `BIS`, `AUSNAHMEN`, `AUSNAHME_FELDER`.
  - `Termin(eintrag, datum, fahrzeug, abfahrt, rueckkehr, strecke_km, fahrer, ladestand, wiederholung, geaendert)`, frozen.
  - `lokal(text, tz) -> datetime`, `plus_dauer(abfahrt, dauer_min, tz) -> datetime`, `utc(zeitpunkt) -> datetime`, `dauer_min(abfahrt, rueckkehr) -> int`.
  - `regeldaten(eintrag, ab, bis) -> Iterator[date]`, `ist_regeldatum(eintrag, datum) -> bool`, `hat_termin(eintrag, datum) -> bool`, `erster_termin(eintrag) -> date | None`.
  - `termin_am(eintrag, datum, tz) -> Termin | None`, `termine_von(eintrag, tz, von, bis) -> list[Termin]`, `ausrollen(eintraege, tz, von, bis, fahrzeug=None) -> list[Termin]`, `ueberschneiden(a, b) -> bool`.

- [ ] **Step 1: Den Test schreiben**

`tests/test_termine.py`:

```python
"""Prueft das Ausrollen der Termine ohne Home Assistant. Spec C3 Abschnitte 2 und 10.

Gerechnet wird in Europe/Berlin, mit echter Zeitumstellung: am 29.03.2026
fehlt 02:00 bis 03:00, am 25.10.2026 gibt es 02:00 bis 03:00 zweimal. Unter
Windows braucht ZoneInfo dafuer das Paket tzdata (tests/requirements-test.txt);
fehlt es, scheitert schon das Laden dieses Tests, statt still gruen zu werden.

Was dieser Test NICHT sieht: den Store auf der Platte und Home Assistant.
"""

import importlib
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

# Geladen ueber ein Paket, dessen __init__.py NICHT laeuft -- die zieht
# homeassistant herein. Bekaeme termine.py einen Import aus Home Assistant
# oder aiohttp, scheiterte schon dieses Laden.
_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
termine = importlib.import_module(f"{_PAKET}.termine")

BERLIN = ZoneInfo("Europe/Berlin")


def _eintrag(abfahrt="2026-09-16T08:00:00", dauer=600, wiederholung="once", **felder):
    return {
        "id": "e1",
        "vehicle": "auto-1",
        "departure": abfahrt,
        "duration_min": dauer,
        "repeat": wiederholung,
        "distance_km": 42,
        "driver": None,
        "soc": None,
        "until": None,
        "exceptions": {},
        **felder,
    }


def _zeit(text: str) -> datetime:
    return termine.lokal(text, BERLIN)


def _daten(eintrag, von="2026-09-14T00:00:00", bis="2026-10-12T00:00:00"):
    return [t.datum.isoformat() for t in termine.termine_von(eintrag, BERLIN, _zeit(von), _zeit(bis))]


# --- Wiederholung, Spec Abschnitt 2 -----------------------------------------


def test_einmalig_nur_die_abfahrt():
    assert _daten(_eintrag()) == ["2026-09-16"]


def test_taeglich_jeden_tag():
    assert _daten(_eintrag(wiederholung="daily"), bis="2026-09-20T00:00:00") == [
        "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"]


def test_werktags_montag_bis_freitag():
    assert _daten(_eintrag(wiederholung="weekdays"), bis="2026-09-23T00:00:00") == [
        "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"]


def test_werktags_ab_einem_samstag_ist_der_erste_termin_der_montag():
    eintrag = _eintrag("2026-09-19T08:00:00", wiederholung="weekdays")
    assert termine.erster_termin(eintrag) == date(2026, 9, 21)
    assert _daten(eintrag, bis="2026-09-23T00:00:00") == ["2026-09-21", "2026-09-22"]


def test_woechentlich_am_wochentag_der_abfahrt():
    assert _daten(_eintrag(wiederholung="weekly")) == [
        "2026-09-16", "2026-09-23", "2026-09-30", "2026-10-07"]


def test_monatlich_am_nten_wochentag():
    # 16.09.2026 ist der dritte Mittwoch: ceil(16 / 7) = 3.
    eintrag = _eintrag(wiederholung="monthly")
    assert _daten(eintrag, bis="2027-01-01T00:00:00") == [
        "2026-09-16", "2026-10-21", "2026-11-18", "2026-12-16"]


def test_monatlich_am_14_der_zweite_und_am_28_der_vierte_wochentag():
    # ceil(14 / 7) = 2: am 14.10.2026, einem Mittwoch, ist das der zweite Mittwoch.
    zweiter = _eintrag("2026-10-14T08:00:00", wiederholung="monthly")
    assert _daten(zweiter, von="2026-10-01T00:00:00", bis="2026-12-01T00:00:00") == [
        "2026-10-14", "2026-11-11"]
    # ceil(28 / 7) = 4 heisst der vierte, nicht der letzte: im April 2026 der 22., nicht der 29.
    vierter = _eintrag("2026-01-28T08:00:00", wiederholung="monthly")
    assert _daten(vierter, von="2026-04-01T00:00:00", bis="2026-05-01T00:00:00") == ["2026-04-22"]


def test_monatlich_ab_dem_29_am_letzten_wochentag():
    # 29.01.2026 ist ein Donnerstag: ceil(29 / 7) = 5, also der letzte Donnerstag.
    eintrag = _eintrag("2026-01-29T08:00:00", wiederholung="monthly")
    assert _daten(eintrag, von="2026-01-01T00:00:00", bis="2026-05-01T00:00:00") == [
        "2026-01-29", "2026-02-26", "2026-03-26", "2026-04-30"]


def test_jaehrlich_am_datum_der_abfahrt():
    eintrag = _eintrag(wiederholung="yearly")
    assert _daten(eintrag, bis="2028-12-31T00:00:00") == ["2026-09-16", "2027-09-16", "2028-09-16"]


def test_der_29_februar_nur_im_schaltjahr():
    eintrag = _eintrag("2028-02-29T08:00:00", wiederholung="yearly")
    assert _daten(eintrag, von="2028-01-01T00:00:00", bis="2033-01-01T00:00:00") == [
        "2028-02-29", "2032-02-29"]


def test_until_beendet_die_serie_vor_dem_datum():
    eintrag = _eintrag(wiederholung="daily", until="2026-09-19")
    assert _daten(eintrag) == ["2026-09-16", "2026-09-17", "2026-09-18"]


# --- Zeitumstellung ---------------------------------------------------------


def test_eine_abfahrt_die_es_nicht_gibt_liegt_eine_stunde_spaeter():
    # 29.03.2026: 02:30 gibt es in Berlin nicht.
    assert _zeit("2026-03-29T02:30:00").isoformat() == "2026-03-29T03:30:00+02:00"


def test_eine_abfahrt_die_es_zweimal_gibt_gilt_beim_ersten_mal():
    # 25.10.2026: 02:30 gibt es zweimal, zuerst in Sommerzeit.
    assert _zeit("2026-10-25T02:30:00").isoformat() == "2026-10-25T02:30:00+02:00"


def test_eine_serie_behaelt_ihre_uhrzeit_ueber_die_umstellung():
    eintrag = _eintrag("2026-10-24T08:00:00", dauer=60, wiederholung="daily")
    reihe = termine.termine_von(eintrag, BERLIN, _zeit("2026-10-24T00:00:00"), _zeit("2026-10-27T00:00:00"))
    assert [t.abfahrt.isoformat() for t in reihe] == [
        "2026-10-24T08:00:00+02:00", "2026-10-25T08:00:00+01:00", "2026-10-26T08:00:00+01:00"]


def test_eine_fahrt_ueber_die_umstellung_behaelt_ihre_dauer():
    # 22:00 Sommerzeit plus 10 h verstrichene Zeit ist 07:00 Winterzeit, nicht 08:00.
    eintrag = _eintrag("2026-10-24T22:00:00", dauer=600)
    (termin,) = termine.termine_von(eintrag, BERLIN, _zeit("2026-10-24T00:00:00"), _zeit("2026-10-26T00:00:00"))
    assert termin.rueckkehr.isoformat() == "2026-10-25T07:00:00+01:00"
    assert termin.rueckkehr.astimezone(timezone.utc) - termin.abfahrt.astimezone(timezone.utc) == timedelta(hours=10)


def test_die_dauer_zaehlt_verstrichene_minuten():
    assert termine.dauer_min(_zeit("2026-10-24T22:00:00"), _zeit("2026-10-25T07:00:00")) == 600
    assert termine.dauer_min(_zeit("2026-03-28T22:00:00"), _zeit("2026-03-29T07:00:00")) == 480


# --- Ausnahmen und Fenster ----------------------------------------------------


def test_eine_abgesagte_ausnahme_fehlt():
    eintrag = _eintrag(wiederholung="daily", exceptions={"2026-09-17": None})
    assert _daten(eintrag, bis="2026-09-19T00:00:00") == ["2026-09-16", "2026-09-18"]
    assert not termine.hat_termin(eintrag, date(2026, 9, 17))


def test_eine_geaenderte_ausnahme_traegt_ihre_werte():
    werte = {"departure": "2026-09-17T09:30:00", "duration_min": 120, "distance_km": 7,
             "driver": "person.anna", "soc": 80}
    eintrag = _eintrag(wiederholung="daily", exceptions={"2026-09-17": werte})
    termin = termine.termin_am(eintrag, date(2026, 9, 17), BERLIN)
    assert termin.geaendert
    assert termin.abfahrt.isoformat() == "2026-09-17T09:30:00+02:00"
    assert termin.rueckkehr.isoformat() == "2026-09-17T11:30:00+02:00"
    assert (termin.strecke_km, termin.fahrer, termin.ladestand) == (7, "person.anna", 80)
    assert not termine.termin_am(eintrag, date(2026, 9, 16), BERLIN).geaendert


def test_eine_verschobene_ausnahme_kommt_ins_fenster_und_geht_hinaus():
    werte = {"departure": "2026-10-05T08:00:00", "duration_min": 60, "distance_km": 7,
             "driver": None, "soc": None}
    eintrag = _eintrag(wiederholung="weekly", exceptions={"2026-09-23": werte})
    assert _daten(eintrag, von="2026-10-05T00:00:00", bis="2026-10-06T00:00:00") == ["2026-09-23"]
    assert _daten(eintrag, von="2026-09-23T00:00:00", bis="2026-09-24T00:00:00") == []


def test_ein_laufender_termin_liegt_im_fenster():
    eintrag = _eintrag("2026-09-16T08:00:00", dauer=600)
    assert _daten(eintrag, von="2026-09-16T12:00:00") == ["2026-09-16"]


def test_die_grenzen_des_fensters_sind_halboffen():
    eintrag = _eintrag("2026-09-16T08:00:00", dauer=600)
    assert _daten(eintrag, von="2026-09-16T18:00:00") == []
    assert _daten(eintrag, von="2026-09-01T00:00:00", bis="2026-09-16T08:00:00") == []


def test_ein_termin_vor_dem_fenster_reicht_hinein():
    # Taeglich 20:00 fuer 23 h: der Termin vom Vortag laeuft ins Fenster.
    eintrag = _eintrag("2026-09-10T20:00:00", dauer=23 * 60, wiederholung="daily")
    assert _daten(eintrag, von="2026-09-16T12:00:00", bis="2026-09-16T13:00:00") == ["2026-09-15"]


def test_ausrollen_sortiert_und_filtert_nach_fahrzeug():
    a = _eintrag("2026-09-17T08:00:00")
    b = {**_eintrag("2026-09-16T08:00:00"), "id": "e2", "vehicle": "auto-2"}
    von, bis = _zeit("2026-09-14T00:00:00"), _zeit("2026-09-20T00:00:00")
    assert [t.eintrag for t in termine.ausrollen([a, b], BERLIN, von, bis)] == ["e2", "e1"]
    assert [t.eintrag for t in termine.ausrollen([a, b], BERLIN, von, bis, fahrzeug="auto-1")] == ["e1"]


def test_ueberschneiden_ist_halboffen():
    eintrag = _eintrag("2026-09-16T08:00:00", dauer=60)
    anschluss = {**_eintrag("2026-09-16T09:00:00", dauer=60), "id": "e2"}
    von, bis = _zeit("2026-09-16T00:00:00"), _zeit("2026-09-17T00:00:00")
    (a,) = termine.termine_von(eintrag, BERLIN, von, bis)
    (b,) = termine.termine_von(anschluss, BERLIN, von, bis)
    assert not termine.ueberschneiden(a, b)
    (c,) = termine.termine_von({**anschluss, "departure": "2026-09-16T08:59:00"}, BERLIN, von, bis)
    assert termine.ueberschneiden(a, c)
```

- [ ] **Step 2: Rot**

Run: `$HAPY -m pytest -q --rootdir . tests/test_termine.py`
Expected: `1 error` beim Sammeln, `ModuleNotFoundError: No module named 'meteo_volt_c3.termine'`

- [ ] **Step 3: Das Modul**

`custom_components/meteo_volt/termine.py`:

```python
"""Termine ohne Home Assistant: wann ein Eintrag stattfindet.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie standort.py. Hier steht, wie ein Eintrag aus dem Store zu
Terminen wird: Wiederholung, Ausnahmen, Ende der Serie, Zeitumstellung.
Was daraus im Request wird, steht in terminanfrage.py, was das Panel liest,
in ansicht.py.

Ein Eintrag ist ein einmaliger Termin oder eine Serie. Ein Termin ist ein
Vorkommen darin, erkannt an Eintrag und Datum seiner urspruenglichen
Abfahrt. Uhrzeiten gelten lokal in der Zeitzone von Home Assistant.
Gespeichert werden Abfahrt und Dauer; die Rueckkehr ist die Abfahrt plus
Dauer als verstrichene Zeit, also in UTC gerechnet.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2 und 3
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo

# --- Wiederholung, Spec Abschnitt 2 -----------------------------------------

EINMALIG = "once"
TAEGLICH = "daily"
WERKTAGS = "weekdays"
WOECHENTLICH = "weekly"
MONATLICH = "monthly"
JAEHRLICH = "yearly"
WIEDERHOLUNGEN = (EINMALIG, TAEGLICH, WERKTAGS, WOECHENTLICH, MONATLICH, JAEHRLICH)

# Der Abstand einer Serie. Dauert ein Termin so lange oder laenger, ist das
# dauer_zu_lang (Spec Abschnitt 2.3).
ABSTAND = {
    TAEGLICH: timedelta(hours=24),
    WERKTAGS: timedelta(hours=24),
    WOECHENTLICH: timedelta(days=7),
    MONATLICH: timedelta(days=28),
    JAEHRLICH: timedelta(days=365),
}

# --- Ein Eintrag im Store, Spec Abschnitt 3 ---------------------------------

ID = "id"
FAHRZEUG = "vehicle"
ABFAHRT = "departure"  # lokal, ISO 8601 ohne Offset
DAUER = "duration_min"
WIEDERHOLUNG = "repeat"
STRECKE = "distance_km"
FAHRER = "driver"
LADESTAND = "soc"
BIS = "until"  # lokales Datum, ab dem die Serie endet, oder None
AUSNAHMEN = "exceptions"  # Datum -> None (abgesagt) oder die Werte unten

AUSNAHME_FELDER = (ABFAHRT, DAUER, STRECKE, FAHRER, LADESTAND)


@dataclass(frozen=True)
class Termin:
    """Ein Vorkommen eines Eintrags."""

    eintrag: str
    datum: date  # der urspruenglichen Abfahrt, lokal
    fahrzeug: str  # subentry_id
    abfahrt: datetime  # mit Zeitzone
    rueckkehr: datetime  # mit Zeitzone
    strecke_km: int
    fahrer: str | None
    ladestand: float | None
    wiederholung: str
    geaendert: bool  # eine geaenderte Ausnahme


def lokal(text: str, tz: tzinfo) -> datetime:
    """'2026-09-21T08:00:00' als Zeitpunkt in tz.

    fold=0 wie beim Planer in _entry_moments: eine Uhrzeit, die es am Tag der
    Umstellung nicht gibt, liegt eine Stunde spaeter; eine, die es zweimal
    gibt, gilt beim ersten Mal. Der Weg ueber UTC schreibt die Uhrzeit
    danach richtig: aus 02:30 wird 03:30.
    """
    zeitpunkt = datetime.fromisoformat(text).replace(tzinfo=tz, fold=0)
    return zeitpunkt.astimezone(timezone.utc).astimezone(tz)


def plus_dauer(abfahrt: datetime, dauer_min: int, tz: tzinfo) -> datetime:
    """Die Rueckkehr: Abfahrt plus Dauer als verstrichene Zeit.

    Nicht abfahrt + timedelta: Python rechnet mit Zeitzone auf der Wanduhr,
    und eine Fahrt ueber die Zeitumstellung dauerte eine Stunde laenger
    oder kuerzer als jede andere.
    """
    return (abfahrt.astimezone(timezone.utc) + timedelta(minutes=dauer_min)).astimezone(tz)


def utc(zeitpunkt: datetime) -> datetime:
    """Fuer jeden Vergleich und jede Differenz.

    Tragen zwei Zeitpunkte dasselbe tzinfo, vergleicht und subtrahiert Python
    sie auf der Wanduhr, ohne fold. Ueber die Umstellung ist das falsch.
    """
    return zeitpunkt.astimezone(timezone.utc)


def dauer_min(abfahrt: datetime, rueckkehr: datetime) -> int:
    """Die verstrichenen Minuten zwischen zwei Zeitpunkten mit Zeitzone."""
    return math.floor((utc(rueckkehr) - utc(abfahrt)).total_seconds() / 60)


# --- Die Daten einer Serie ---------------------------------------------------


def _start(eintrag: dict) -> date:
    return date.fromisoformat(eintrag[ABFAHRT][:10])


def _nter_wochentag(jahr: int, monat: int, wochentag: int, n: int) -> date:
    """Der n-te Wochentag im Monat. n = 5 heisst: der letzte."""
    if n >= 5:
        naechster = date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)
        letzter = naechster - timedelta(days=1)
        return letzter - timedelta(days=(letzter.weekday() - wochentag) % 7)
    erster = date(jahr, monat, 1)
    return erster + timedelta(days=(wochentag - erster.weekday()) % 7 + 7 * (n - 1))


def regeldaten(eintrag: dict, ab: date, bis: date) -> Iterator[date]:
    """Die Daten der regulaeren Termine von ab bis bis, beide eingeschlossen.

    Regulaer heisst: nach der Wiederholung, vor until, abgesagt oder nicht.
    """
    start = _start(eintrag)
    if eintrag.get(BIS) is not None:
        bis = min(bis, date.fromisoformat(eintrag[BIS]) - timedelta(days=1))
    art = eintrag[WIEDERHOLUNG]
    if art == EINMALIG:
        if ab <= start <= bis:
            yield start
        return
    tag = max(start, ab)
    if art in (TAEGLICH, WERKTAGS):
        while tag <= bis:
            if art == TAEGLICH or tag.weekday() < 5:
                yield tag
            tag += timedelta(days=1)
    elif art == WOECHENTLICH:
        tag += timedelta(days=-(tag - start).days % 7)
        while tag <= bis:
            yield tag
            tag += timedelta(days=7)
    elif art == MONATLICH:
        # n = ceil(Tag / 7). Ab dem 29. ist das 5 und heisst "am letzten".
        n = math.ceil(start.day / 7)
        jahr, monat = tag.year, tag.month
        while True:
            kandidat = _nter_wochentag(jahr, monat, start.weekday(), n)
            if kandidat > bis:
                return
            if kandidat >= tag:
                yield kandidat
            jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)
    elif art == JAEHRLICH:
        for jahr in range(tag.year, bis.year + 1):
            try:
                kandidat = start.replace(year=jahr)
            except ValueError:
                continue  # der 29. Februar gibt es nur im Schaltjahr
            if tag <= kandidat <= bis:
                yield kandidat
    else:
        raise ValueError(f"unbekannte Wiederholung: {art}")


def ist_regeldatum(eintrag: dict, datum: date) -> bool:
    return next(regeldaten(eintrag, datum, datum), None) is not None


def hat_termin(eintrag: dict, datum: date) -> bool:
    """Ob der Eintrag an diesem Datum einen Termin hat, der nicht abgesagt ist."""
    ausnahmen = eintrag.get(AUSNAHMEN) or {}
    abgesagt = datum.isoformat() in ausnahmen and ausnahmen[datum.isoformat()] is None
    return ist_regeldatum(eintrag, datum) and not abgesagt


def erster_termin(eintrag: dict) -> date | None:
    """Das Datum des ersten regulaeren Termins. Werktags ab einem Samstag der Montag."""
    start = _start(eintrag)
    return next(regeldaten(eintrag, start, start + timedelta(days=7)), None)


# --- Termine ----------------------------------------------------------------


def termin_am(eintrag: dict, datum: date, tz: tzinfo) -> Termin | None:
    """Der Termin des Eintrags an diesem Datum, oder None, wenn es keinen gibt."""
    if not hat_termin(eintrag, datum):
        return None
    werte = (eintrag.get(AUSNAHMEN) or {}).get(datum.isoformat())
    if werte is None:
        werte = {feld: eintrag[feld] for feld in AUSNAHME_FELDER}
        werte[ABFAHRT] = datum.isoformat() + eintrag[ABFAHRT][10:]
        geaendert = False
    else:
        geaendert = True
    abfahrt = lokal(werte[ABFAHRT], tz)
    return Termin(
        eintrag=eintrag[ID],
        datum=datum,
        fahrzeug=eintrag[FAHRZEUG],
        abfahrt=abfahrt,
        rueckkehr=plus_dauer(abfahrt, werte[DAUER], tz),
        strecke_km=werte[STRECKE],
        fahrer=werte[FAHRER],
        ladestand=werte[LADESTAND],
        wiederholung=eintrag[WIEDERHOLUNG],
        geaendert=geaendert,
    )


def termine_von(eintrag: dict, tz: tzinfo, von: datetime, bis: datetime) -> list[Termin]:
    """Die Termine eines Eintrags, deren Rueckkehr nach von und deren Abfahrt vor bis liegt.

    Eine geaenderte Ausnahme kann ihren Termin an einen anderen Tag legen, in
    das Fenster hinein oder aus ihm heraus. Ihre Daten zaehlen deshalb immer mit.
    """
    ab = von.astimezone(tz).date() - timedelta(days=eintrag[DAUER] // 1440 + 1)
    daten = set(regeldaten(eintrag, ab, bis.astimezone(tz).date()))
    daten |= {
        date.fromisoformat(tag)
        for tag, werte in (eintrag.get(AUSNAHMEN) or {}).items()
        if werte is not None
    }
    ergebnis = []
    for datum in sorted(daten):
        termin = termin_am(eintrag, datum, tz)
        if termin is not None and utc(termin.rueckkehr) > utc(von) and utc(termin.abfahrt) < utc(bis):
            ergebnis.append(termin)
    return ergebnis


def ausrollen(
    eintraege: list[dict],
    tz: tzinfo,
    von: datetime,
    bis: datetime,
    fahrzeug: str | None = None,
) -> list[Termin]:
    """Alle Termine im Fenster, nach Abfahrt sortiert. fahrzeug filtert."""
    termine = [
        termin
        for eintrag in eintraege
        if fahrzeug is None or eintrag[FAHRZEUG] == fahrzeug
        for termin in termine_von(eintrag, tz, von, bis)
    ]
    return sorted(termine, key=_reihenfolge)


def _reihenfolge(termin: Termin) -> tuple:
    return utc(termin.abfahrt), termin.eintrag, termin.datum


def ueberschneiden(a: Termin, b: Termin) -> bool:
    """Zwei Termine liegen zur selben Zeit. Halboffen: Rueckkehr gleich Abfahrt nicht."""
    return utc(a.abfahrt) < utc(b.rueckkehr) and utc(b.abfahrt) < utc(a.rueckkehr)
```

- [ ] **Step 4: Grün**

Run: `$HAPY -m pytest -q --rootdir . tests/test_termine.py`
Expected: `24 passed`

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `340 passed`

- [ ] **Step 5: Commit**

```bash
git add custom_components/meteo_volt/termine.py tests/test_termine.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Roll out appointments with repeats, exceptions and daylight saving

An entry stores departure and duration. Each appointment returns after
the duration as elapsed time, so a trip across the change lasts as
long as any other. Times that do not exist or exist twice resolve with
fold=0, as the planner does.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `pruefungen.py` — die Meldungen aus 2.3

**Files:**
- Create: `custom_components/meteo_volt/pruefungen.py`
- Test: `tests/test_pruefungen.py`

**Interfaces:**
- Consumes: aus Task 1 `termine.lokal`, `termine.utc`, `termine.dauer_min`, `termine.ausrollen`, `termine.ueberschneiden`, `termine.WIEDERHOLUNGEN`, `termine.EINMALIG`, `termine.ABSTAND`; aus `planabruf.py` `PlanNichtAutorisiert`, `PlanRateLimit`; aus `standort.py` `Planstand` (nur im Test).
- Produces:
  - die 16 Schluessel als Konstanten, `MELDUNGEN` (Schluessel -> Platzhalter), `AKTIONEN` (Action -> Felder), `TERMIN_FELDER`, `FAHRER_VORAUS`.
  - `Meldung(schluessel, feld=None, platzhalter={})` mit `als_dict() -> {"key", "field", "placeholders"}`; `Terminfehler(meldung)`; `fehler(schluessel, feld=None, **platzhalter) -> Terminfehler`.
  - `Werte(fahrzeug, abfahrt, dauer_min, wiederholung, strecke_km, fahrer, ladestand)`, frozen.
  - `fahrzeug_aus_geraet(kennungen, domain, fahrzeuge) -> (entry_id, subentry_id)`.
  - `werte_pruefen(felder, fahrzeug, jetzt, tz, vorgabe_wiederholung="once") -> Werte`.
  - `warnungen(werte, eintrag_id, eintraege, tz, jetzt, soc_min, personen, titel, sprache) -> list[Meldung]`, `zahl_text`, `datum_text`.
  - `neu_planen_pruefen(vorher, nachher) -> Meldung | None`.

- [ ] **Step 1: Den Test schreiben**

`tests/test_pruefungen.py`:

```python
"""Prueft die Pruefungen beim Speichern ohne Home Assistant. Spec C3 Abschnitte 2.3 und 10.

Jeder Schluessel aus 2.3 mit seinem Feld. Fuenf davon entstehen woanders
und sind dort geprueft: eintrag_unbekannt, termin_unbekannt,
umfang_unzulaessig und rueckgaengig_unmoeglich in tests/test_terminbuch.py,
fahrzeug_unbekannt, plan_pause und plan_gestoppt hier.

Was dieser Test NICHT sieht: dass Home Assistant aus einem Terminfehler einen
uebersetzten ServiceValidationError macht. Das zeigt die Abnahme.
"""

import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
pruefungen = importlib.import_module(f"{_PAKET}.pruefungen")
termine = importlib.import_module(f"{_PAKET}.termine")
standort = importlib.import_module(f"{_PAKET}.standort")
planabruf = importlib.import_module(f"{_PAKET}.planabruf")

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # 12:00 in Berlin


def _felder(**felder):
    return {"departure": "2026-09-17 08:00:00", "return": "2026-09-17 18:00:00",
            "distance_km": 42, **felder}


def _pruefen(**felder):
    return pruefungen.werte_pruefen(_felder(**felder), "auto-1", JETZT, BERLIN)


def _fehler(schluessel, feld, **felder):
    with pytest.raises(pruefungen.Terminfehler) as info:
        _pruefen(**felder)
    assert (info.value.meldung.schluessel, info.value.meldung.feld) == (schluessel, feld)


# --- Die Werte --------------------------------------------------------------


def test_gueltige_werte_so_wie_der_store_sie_traegt():
    werte = _pruefen(driver="person.anna", soc=80)
    assert werte == pruefungen.Werte(
        fahrzeug="auto-1", abfahrt="2026-09-17T08:00:00", dauer_min=600,
        wiederholung="once", strecke_km=42, fahrer="person.anna", ladestand=80.0)


def test_ohne_wiederholung_gilt_die_vorgabe():
    werte = pruefungen.werte_pruefen(_felder(), "auto-1", JETZT, BERLIN, "weekly")
    assert werte.wiederholung == "weekly"


def test_eine_zeit_mit_offset_wird_lokal():
    werte = _pruefen(departure="2026-09-17T06:00:00+00:00")
    assert werte.abfahrt == "2026-09-17T08:00:00"


def test_die_strecke_wird_kaufmaennisch_gerundet():
    assert _pruefen(distance_km=42.5).strecke_km == 43
    assert _pruefen(distance_km=0).strecke_km == 0


# --- Jeder Fehler mit Schluessel und Feld ------------------------------------


def test_zeit_fehlt():
    _fehler("zeit_fehlt", "departure", departure=None)
    _fehler("zeit_fehlt", "return", **{"return": ""})
    _fehler("zeit_fehlt", "departure", departure="morgen frueh")


def test_rueckkehr_vor_abfahrt():
    _fehler("rueckkehr_vor_abfahrt", "return", **{"return": "2026-09-17 08:00:00"})
    _fehler("rueckkehr_vor_abfahrt", "return", **{"return": "2026-09-17 07:00:00"})


def test_rueckkehr_vorbei_nur_bei_einmalig():
    vergangen = {"departure": "2026-09-15 08:00:00", "return": "2026-09-15 18:00:00"}
    _fehler("rueckkehr_vorbei", "return", **vergangen)
    assert _pruefen(**vergangen, repeat="daily").wiederholung == "daily"


def test_ein_laufender_termin_ist_erlaubt():
    assert _pruefen(departure="2026-09-16 08:00:00", **{"return": "2026-09-16 18:00:00"})


@pytest.mark.parametrize(("wiederholung", "rueckkehr"), [
    ("daily", "2026-09-18 08:00:00"),
    ("weekdays", "2026-09-18 08:00:00"),
    ("weekly", "2026-09-24 08:00:00"),
    ("monthly", "2026-10-15 08:00:00"),
    ("yearly", "2027-09-17 08:00:00"),
])
def test_dauer_zu_lang_ab_dem_abstand(wiederholung, rueckkehr):
    _fehler("dauer_zu_lang", "return", repeat=wiederholung, **{"return": rueckkehr})


def test_eine_minute_unter_dem_abstand_geht():
    assert _pruefen(repeat="daily", **{"return": "2026-09-18 07:59:00"}).dauer_min == 24 * 60 - 1


def test_strecke_fehlt_und_negativ():
    _fehler("strecke_fehlt", "distance_km", distance_km=None)
    _fehler("strecke_negativ", "distance_km", distance_km=-1)


def test_ladestand_bereich():
    _fehler("ladestand_bereich", "soc", soc=-0.1)
    _fehler("ladestand_bereich", "soc", soc=100.1)
    assert _pruefen(soc=0).ladestand == 0.0
    assert _pruefen(soc=100).ladestand == 100.0


def test_die_reihenfolge_der_tabelle():
    """Zwei Fehler zugleich: der aus der frueheren Zeile kommt."""
    _fehler("rueckkehr_vor_abfahrt", "return", distance_km=None, **{"return": "2026-09-17 07:00:00"})


def test_fahrzeug_unbekannt():
    fahrzeuge = {"eintrag-1": {"auto-1"}}
    assert pruefungen.fahrzeug_aus_geraet({("meteo_volt", "auto-1")}, "meteo_volt", fahrzeuge) == (
        "eintrag-1", "auto-1")
    for kennungen in ({("meteo_volt", "eintrag-1")}, {("andere", "auto-1")}, set()):
        with pytest.raises(pruefungen.Terminfehler) as info:
            pruefungen.fahrzeug_aus_geraet(kennungen, "meteo_volt", fahrzeuge)
        assert (info.value.meldung.schluessel, info.value.meldung.feld) == ("fahrzeug_unbekannt", "vehicle")


# --- Die Warnungen ------------------------------------------------------------


def _eintrag(eintrag_id, fahrzeug, abfahrt, fahrer, wiederholung="once"):
    return {"id": eintrag_id, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": 600,
            "repeat": wiederholung, "distance_km": 42, "driver": fahrer, "soc": None,
            "until": None, "exceptions": {}}


def _warnungen(werte, eintraege, sprache="de"):
    return pruefungen.warnungen(
        werte, "neu", eintraege, BERLIN, JETZT, 15.0,
        {"person.anna": "Anna"}, {"auto-1": "ID. Buzz", "auto-2": "Zoe"}, sprache)


def test_ladestand_unter_min_warnt_mit_dem_min_soc():
    (meldung,) = _warnungen(_pruefen(soc=10), [])
    assert meldung.als_dict() == {"key": "ladestand_unter_min", "field": "soc",
                                  "placeholders": {"min": "15"}}
    assert _warnungen(_pruefen(soc=15), []) == []


def test_fahrer_doppelt_nennt_fahrer_datum_und_fahrzeug():
    werte = _pruefen(driver="person.anna", repeat="weekly")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.anna", "weekly")
    anderer = _eintrag("alt", "auto-2", "2026-10-01T12:00:00", "person.anna")
    (meldung,) = _warnungen(werte, [eigener, anderer])
    assert meldung.als_dict() == {"key": "fahrer_doppelt", "field": "driver", "placeholders": {
        "fahrer": "Anna", "datum": "Do 01.10.", "fahrzeug": "Zoe"}}
    (englisch,) = _warnungen(werte, [eigener, anderer], "en-GB")
    assert englisch.platzhalter["datum"] == "Thu 1 Oct"


def test_fahrer_doppelt_nur_in_den_naechsten_acht_wochen_und_mit_anderem_fahrzeug():
    werte = _pruefen(driver="person.anna", repeat="weekly")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.anna", "weekly")
    spaet = _eintrag("alt", "auto-2", "2026-11-19T12:00:00", "person.anna")
    gleiches_auto = _eintrag("alt2", "auto-1", "2026-09-24T12:00:00", "person.anna")
    assert _warnungen(werte, [eigener, spaet, gleiches_auto]) == []


def test_ein_geloeschter_fahrer_warnt_nicht():
    werte = _pruefen(driver="person.weg")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.weg")
    anderer = _eintrag("alt", "auto-2", "2026-09-17T12:00:00", "person.weg")
    assert _warnungen(werte, [eigener, anderer]) == []


# --- Neu planen ---------------------------------------------------------------

VORHER = standort.Planstand(letzter_versuch_um=datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc))
VERSUCHT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def test_plan_pause_nennt_die_restdauer():
    nachher = standort.Planstand(fehler=planabruf.PlanRateLimit(retry_after=41.2), letzter_versuch_um=VERSUCHT)
    meldung = pruefungen.neu_planen_pruefen(VORHER, nachher)
    assert (meldung.schluessel, meldung.platzhalter) == ("plan_pause", {"sekunden": "42"})


def test_ein_alter_rate_limit_ohne_neuen_versuch_ist_kein_fehler():
    nachher = standort.Planstand(fehler=planabruf.PlanRateLimit(retry_after=41.2),
                                 letzter_versuch_um=VORHER.letzter_versuch_um)
    assert pruefungen.neu_planen_pruefen(VORHER, nachher) is None


def test_plan_gestoppt_nach_einem_key_fehler():
    nachher = standort.Planstand(fehler=planabruf.PlanNichtAutorisiert(status=401),
                                 letzter_versuch_um=VORHER.letzter_versuch_um)
    assert pruefungen.neu_planen_pruefen(VORHER, nachher).schluessel == "plan_gestoppt"


def test_jeder_andere_fehler_steht_im_plan():
    for fehler in (None, planabruf.PlanAbgelehnt(status=400), planabruf.PlanNichtVerfuegbar(status=503)):
        nachher = standort.Planstand(fehler=fehler, letzter_versuch_um=VERSUCHT)
        assert pruefungen.neu_planen_pruefen(VORHER, nachher) is None


def test_jeder_schluessel_hat_seine_platzhalter():
    """Die Tabelle in pruefungen.py ist die Quelle fuer tests/test_uebersetzungen.py."""
    assert len(pruefungen.MELDUNGEN) == 16
```

- [ ] **Step 2: Rot**

Run: `$HAPY -m pytest -q --rootdir . tests/test_pruefungen.py`
Expected: `1 error` beim Sammeln, `No module named 'meteo_volt_c3.pruefungen'`

- [ ] **Step 3: Das Modul**

`custom_components/meteo_volt/pruefungen.py`:

```python
"""Die Pruefungen der Termine ohne Home Assistant. Spec C3 Abschnitt 2.3.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Das Panel prueft beim Eingeben, dieses Modul beim Speichern
dasselbe: die Actions gehen auch ohne Panel. Jede Meldung hat einen
Schluessel und ein Feld; der Schluessel ist zugleich der translation_key.
Fehler werfen Terminfehler, Warnungen kommen in der Antwort zurueck.

Hier stehen auch die Actions mit ihren Feldern: eine Quelle fuer das Schema
in aktionen.py, services.yaml und tests/test_uebersetzungen.py.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2.3 und 5
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from . import termine
from .planabruf import PlanNichtAutorisiert, PlanRateLimit

# --- Die Schluessel, Spec Abschnitt 2.3 -------------------------------------

ZEIT_FEHLT = "zeit_fehlt"
RUECKKEHR_VOR_ABFAHRT = "rueckkehr_vor_abfahrt"
RUECKKEHR_VORBEI = "rueckkehr_vorbei"
DAUER_ZU_LANG = "dauer_zu_lang"
STRECKE_FEHLT = "strecke_fehlt"
STRECKE_NEGATIV = "strecke_negativ"
LADESTAND_BEREICH = "ladestand_bereich"
LADESTAND_UNTER_MIN = "ladestand_unter_min"
FAHRER_DOPPELT = "fahrer_doppelt"
FAHRZEUG_UNBEKANNT = "fahrzeug_unbekannt"
EINTRAG_UNBEKANNT = "eintrag_unbekannt"
TERMIN_UNBEKANNT = "termin_unbekannt"
UMFANG_UNZULAESSIG = "umfang_unzulaessig"
RUECKGAENGIG_UNMOEGLICH = "rueckgaengig_unmoeglich"
PLAN_PAUSE = "plan_pause"
PLAN_GESTOPPT = "plan_gestoppt"

# Jeder Schluessel mit den Platzhaltern seines Textes.
MELDUNGEN = {
    ZEIT_FEHLT: (),
    RUECKKEHR_VOR_ABFAHRT: (),
    RUECKKEHR_VORBEI: (),
    DAUER_ZU_LANG: (),
    STRECKE_FEHLT: (),
    STRECKE_NEGATIV: (),
    LADESTAND_BEREICH: (),
    LADESTAND_UNTER_MIN: ("min",),
    FAHRER_DOPPELT: ("fahrer", "datum", "fahrzeug"),
    FAHRZEUG_UNBEKANNT: (),
    EINTRAG_UNBEKANNT: (),
    TERMIN_UNBEKANNT: (),
    UMFANG_UNZULAESSIG: (),
    RUECKGAENGIG_UNMOEGLICH: (),
    PLAN_PAUSE: ("sekunden",),
    PLAN_GESTOPPT: (),
}

# Der Fahrer wird so weit voraus geprueft, Spec Abschnitt 2.3.
FAHRER_VORAUS = timedelta(weeks=8)

# --- Die Actions und ihre Felder, Spec Abschnitt 5 ---------------------------

TERMIN_FELDER = ("vehicle", "departure", "return", "repeat", "distance_km", "driver", "soc")
AKTIONEN = {
    "create_appointment": TERMIN_FELDER,
    "update_appointment": ("entry", "date", "scope", *TERMIN_FELDER),
    "delete_appointment": ("entry", "date", "scope"),
    "cancel_appointments": ("appointments", "step"),
    "undo": ("step",),
    "set_risk": ("risk", "config_entry"),
    "replan": ("config_entry",),
}


@dataclass(frozen=True)
class Meldung:
    schluessel: str
    feld: str | None = None
    platzhalter: dict[str, str] = field(default_factory=dict)

    def als_dict(self) -> dict:
        """Eine Warnung in der Antwort: key, field, placeholders."""
        return {"key": self.schluessel, "field": self.feld, "placeholders": dict(self.platzhalter)}


class Terminfehler(Exception):
    """Ein Fehler aus Abschnitt 2.3. aktionen.py macht daraus einen ServiceValidationError."""

    def __init__(self, meldung: Meldung) -> None:
        super().__init__(meldung.schluessel)
        self.meldung = meldung


def fehler(schluessel: str, feld: str | None = None, **platzhalter: str) -> Terminfehler:
    return Terminfehler(Meldung(schluessel, feld, platzhalter))


@dataclass(frozen=True)
class Werte:
    """Die geprueften Werte eines Termins, so wie der Store sie traegt."""

    fahrzeug: str
    abfahrt: str  # lokal, ISO 8601 ohne Offset
    dauer_min: int
    wiederholung: str
    strecke_km: int
    fahrer: str | None
    ladestand: float | None


# --- Die Pruefung beim Speichern ----------------------------------------------


def fahrzeug_aus_geraet(
    kennungen: set[tuple[str, str]], domain: str, fahrzeuge: dict[str, set[str]]
) -> tuple[str, str]:
    """(entry_id, subentry_id) zu den identifiers eines Geraets.

    fahrzeuge bildet jeden Standort auf seine Fahrzeuge ab. Das Geraet der
    Prognose traegt (meteo_volt, entry_id) und ist kein Fahrzeug.
    """
    for eigene_domain, kennung in kennungen:
        if eigene_domain != domain:
            continue
        for entry_id, ids in fahrzeuge.items():
            if kennung in ids:
                return entry_id, kennung
    raise fehler(FAHRZEUG_UNBEKANNT, "vehicle")


def _lokal_text(wert, tz: tzinfo) -> str | None:
    """Eine Eingabe als lokale Zeit ohne Offset, oder None, wenn sie keine Zeit ist.

    Die Datums-Auswahl von Home Assistant liefert '2026-09-21 08:00:00'. Traegt
    eine Eingabe doch einen Offset, wird sie in die Zeitzone umgerechnet.
    """
    if not isinstance(wert, str) or not wert.strip():
        return None
    try:
        zeitpunkt = datetime.fromisoformat(wert.strip())
    except ValueError:
        return None
    if zeitpunkt.tzinfo is not None:
        zeitpunkt = zeitpunkt.astimezone(tz)
    return zeitpunkt.replace(tzinfo=None).isoformat()


def werte_pruefen(
    felder: dict,
    fahrzeug: str,
    jetzt: datetime,
    tz: tzinfo,
    vorgabe_wiederholung: str = termine.EINMALIG,
) -> Werte:
    """Die Felder eines Termins, geprueft in der Reihenfolge der Tabelle 2.3.

    fahrzeug ist schon aufgeloest: die subentry_id eines Fahrzeugs dieses
    Standorts. Fehlt repeat, gilt vorgabe_wiederholung -- beim Anlegen
    once, beim Aendern die Wiederholung des Eintrags.
    """
    abfahrt_text = _lokal_text(felder.get("departure"), tz)
    rueckkehr_text = _lokal_text(felder.get("return"), tz)
    if abfahrt_text is None:
        raise fehler(ZEIT_FEHLT, "departure")
    if rueckkehr_text is None:
        raise fehler(ZEIT_FEHLT, "return")
    wiederholung = felder.get("repeat") or vorgabe_wiederholung
    if wiederholung not in termine.WIEDERHOLUNGEN:
        raise ValueError(f"unbekannte Wiederholung: {wiederholung}")
    abfahrt = termine.lokal(abfahrt_text, tz)
    rueckkehr = termine.lokal(rueckkehr_text, tz)
    dauer = termine.dauer_min(abfahrt, rueckkehr)
    if dauer <= 0:
        raise fehler(RUECKKEHR_VOR_ABFAHRT, "return")
    if wiederholung == termine.EINMALIG and termine.utc(rueckkehr) <= termine.utc(jetzt):
        raise fehler(RUECKKEHR_VORBEI, "return")
    if wiederholung != termine.EINMALIG and timedelta(minutes=dauer) >= termine.ABSTAND[wiederholung]:
        raise fehler(DAUER_ZU_LANG, "return")
    strecke = felder.get("distance_km")
    if strecke is None:
        raise fehler(STRECKE_FEHLT, "distance_km")
    if strecke < 0:
        raise fehler(STRECKE_NEGATIV, "distance_km")
    ladestand = felder.get("soc")
    if ladestand is not None and not 0 <= ladestand <= 100:
        raise fehler(LADESTAND_BEREICH, "soc")
    return Werte(
        fahrzeug=fahrzeug,
        abfahrt=abfahrt_text,
        dauer_min=dauer,
        wiederholung=wiederholung,
        # Ganze Kilometer, kaufmaennisch gerundet. round() rundete 42.5 auf 42.
        strecke_km=math.floor(strecke + 0.5),
        fahrer=felder.get("driver") or None,
        ladestand=None if ladestand is None else float(ladestand),
    )


# --- Die Warnungen ------------------------------------------------------------

_WOCHENTAGE = {
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
_MONATE_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _sprache(sprache: str) -> str:
    """'de-CH' -> 'de'. Alles ausser Deutsch ist Englisch."""
    return "de" if (sprache or "").split("-")[0].lower() == "de" else "en"


def zahl_text(wert: float, sprache: str) -> str:
    """15.0 -> '15'; 15.5 -> '15,5' deutsch und '15.5' englisch. Wie in ausgabe.py."""
    text = f"{wert:g}"
    return text.replace(".", ",") if _sprache(sprache) == "de" else text


def datum_text(zeitpunkt: datetime, sprache: str) -> str:
    """'Sa 19.09.' deutsch, 'Sat 19 Sep' englisch."""
    if _sprache(sprache) == "de":
        return f"{_WOCHENTAGE['de'][zeitpunkt.weekday()]} {zeitpunkt:%d.%m.}"
    return f"{_WOCHENTAGE['en'][zeitpunkt.weekday()]} {zeitpunkt.day} {_MONATE_EN[zeitpunkt.month - 1]}"


def warnungen(
    werte: Werte,
    eintrag_id: str,
    eintraege: list[dict],
    tz: tzinfo,
    jetzt: datetime,
    soc_min: float,
    personen: dict[str, str],
    titel: dict[str, str],
    sprache: str,
) -> list[Meldung]:
    """Die Warnungen nach dem Speichern. Gespeichert ist trotzdem.

    eintrag_id traegt die neuen Werte, eintraege ist der Stand danach.
    personen bildet jede person-Entitaet auf ihren Namen ab, titel jedes
    Fahrzeug auf seinen Titel.
    """
    meldungen = []
    if werte.ladestand is not None and werte.ladestand < soc_min:
        meldungen.append(Meldung(LADESTAND_UNTER_MIN, "soc", {"min": zahl_text(soc_min, sprache)}))
    if werte.fahrer in personen:
        bis = jetzt + FAHRER_VORAUS
        alle = termine.ausrollen(eintraege, tz, jetzt, bis)
        eigene = [t for t in alle if t.eintrag == eintrag_id and t.fahrer == werte.fahrer]
        andere = [t for t in alle if t.fahrzeug != werte.fahrzeug and t.fahrer == werte.fahrer]
        for termin in eigene:
            konflikt = next((a for a in andere if termine.ueberschneiden(termin, a)), None)
            if konflikt is not None:
                meldungen.append(Meldung(FAHRER_DOPPELT, "driver", {
                    "fahrer": personen[werte.fahrer],
                    "datum": datum_text(termin.abfahrt, sprache),
                    "fahrzeug": titel.get(konflikt.fahrzeug, konflikt.fahrzeug),
                }))
                break
    return meldungen


# --- Neu planen, Spec Abschnitt 5 ----------------------------------------------


def neu_planen_pruefen(vorher, nachher) -> Meldung | None:
    """Was meteo_volt.replan wirft, oder None. vorher und nachher sind Planstaende.

    Nach einem Key-Fehler plant C5 nichts mehr: plan_gestoppt. Eine
    Sendepause nennt ihre Restdauer, aber nur, wenn dieser Lauf gesendet
    hat oder senden wollte -- ohne planbares Fahrzeug bleibt ein alter
    Fehler stehen und hiesse nichts. Jeder andere Fehler steht im Plan.
    """
    if isinstance(nachher.fehler, PlanNichtAutorisiert):
        return Meldung(PLAN_GESTOPPT)
    versucht = nachher.letzter_versuch_um != vorher.letzter_versuch_um
    if isinstance(nachher.fehler, PlanRateLimit) and versucht:
        return Meldung(PLAN_PAUSE, platzhalter={"sekunden": str(math.ceil(nachher.fehler.retry_after))})
    return None
```

- [ ] **Step 4: Grün**

Run: `$HAPY -m pytest -q --rootdir . tests/test_pruefungen.py`
Expected: `27 passed`

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `367 passed`

- [ ] **Step 5: Commit**

```bash
git add custom_components/meteo_volt/pruefungen.py tests/test_pruefungen.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Check appointments on save with the keys the panel knows

Every error carries its key and field and stops the save; the first in
the order of the spec wins. Warnings for a state of charge below the
minimum and for a driver on the road with another vehicle come back
with the response. Replanning reports the send pause and a rejected key.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: `terminbuch.py` — Serien, Absagen, Rückgängig

**Files:**
- Create: `custom_components/meteo_volt/terminbuch.py`
- Test: `tests/test_terminbuch.py`

**Interfaces:**
- Consumes: aus Task 1 `termine.hat_termin`, `termine.erster_termin` und die Store-Felder; aus Task 2 `Werte`, `fehler` und die Schluessel `EINTRAG_UNBEKANNT`, `TERMIN_UNBEKANNT`, `UMFANG_UNZULAESSIG`, `RUECKGAENGIG_UNMOEGLICH`.
- Produces:
  - `DIESER = "this"`, `FOLGENDE = "following"`, `ALLE = "all"`, `UMFAENGE`, `MAX_SCHRITTE = 50`, `RISIKO = "risk"`, `EINTRAEGE = "entries"`.
  - `Schritt(kennung, vorher, nachher)`; `Buch(daten=None, schritte=None)` mit `risiko`, `eintraege` (id -> Eintrag), `schritte` (deque, maxlen 50), `speicherform() -> dict`.
  - `anlegen(buch, werte, neue_id) -> (schritt, [eintrag])`, `aendern(buch, eintrag_id, datum, umfang, werte, neue_id) -> (schritt, eintraege)`, `loeschen(buch, eintrag_id, datum, umfang, neue_id) -> schritt`, `absagen(buch, liste, zu_schritt, neue_id) -> schritt`, `rueckgaengig(buch, kennung) -> None`, `fahrzeuge_bereinigen(buch, fahrzeuge) -> bool`, `schritt_bekannt(buch, kennung) -> bool`.

- [ ] **Step 1: Den Test schreiben**

`tests/test_terminbuch.py`:

```python
"""Prueft Serien, Absagen und Rueckgaengig ohne Home Assistant. Spec C3 Abschnitte 2.1, 2.2 und 10.

Was dieser Test NICHT sieht: den Store auf der Platte, die Signale an das
Panel und den Plan, den ein Schritt ausloest. Das zeigt die Abnahme.
"""

import importlib
import itertools
import sys
import types
from datetime import date
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
terminbuch = importlib.import_module(f"{_PAKET}.terminbuch")
pruefungen = importlib.import_module(f"{_PAKET}.pruefungen")

MI = date(2026, 9, 16)  # der erste Termin der Serien unten, ein Mittwoch
DO = date(2026, 9, 17)
FR = date(2026, 9, 18)


def _werte(abfahrt="2026-09-16T08:00:00", wiederholung="weekdays", fahrzeug="auto-1", **felder):
    return pruefungen.Werte(**{
        "fahrzeug": fahrzeug, "abfahrt": abfahrt, "dauer_min": 600, "wiederholung": wiederholung,
        "strecke_km": 42, "fahrer": None, "ladestand": None, **felder})


def _ids():
    zaehler = itertools.count(1)
    return lambda: f"k{next(zaehler)}"


def _buch_mit_serie(**felder):
    buch, neue_id = terminbuch.Buch(), _ids()
    schritt, (eintrag,) = terminbuch.anlegen(buch, _werte(**felder), neue_id)
    return buch, neue_id, eintrag


def _fehler(schluessel, feld, aufruf, *argumente):
    with pytest.raises(pruefungen.Terminfehler) as info:
        aufruf(*argumente)
    assert (info.value.meldung.schluessel, info.value.meldung.feld) == (schluessel, feld)


# --- Anlegen und einmalige Termine ------------------------------------------


def test_anlegen_legt_einen_eintrag_und_einen_schritt_an():
    buch, _, eintrag = _buch_mit_serie()
    assert buch.eintraege[eintrag] == {
        "id": eintrag, "vehicle": "auto-1", "departure": "2026-09-16T08:00:00", "duration_min": 600,
        "repeat": "weekdays", "distance_km": 42, "driver": None, "soc": None, "until": None,
        "exceptions": {}}
    assert len(buch.schritte) == 1


def test_ein_einmaliger_termin_uebergeht_den_umfang():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="once")
    neu = _werte("2026-09-18T09:00:00", wiederholung="daily", fahrzeug="auto-2")
    _, eintraege = terminbuch.aendern(buch, eintrag, MI, "following", neu, neue_id)
    assert eintraege == [eintrag]
    assert buch.eintraege[eintrag]["departure"] == "2026-09-18T09:00:00"
    assert (buch.eintraege[eintrag]["repeat"], buch.eintraege[eintrag]["vehicle"]) == ("daily", "auto-2")


def test_ein_einmaliger_termin_wird_auch_mit_umfang_ganz_geloescht():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="once")
    terminbuch.loeschen(buch, eintrag, MI, "following", neue_id)
    assert buch.eintraege == {}


# --- Aendern mit Umfang, Spec Abschnitt 2.1 -----------------------------------


def test_this_legt_eine_ausnahme_an():
    buch, neue_id, eintrag = _buch_mit_serie()
    _, eintraege = terminbuch.aendern(
        buch, eintrag, DO, "this", _werte("2026-09-17T09:00:00", strecke_km=7), neue_id)
    assert eintraege == [eintrag]
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-17": {
        "departure": "2026-09-17T09:00:00", "duration_min": 600, "distance_km": 7,
        "driver": None, "soc": None}}
    assert buch.eintraege[eintrag]["departure"] == "2026-09-16T08:00:00"


def test_ohne_umfang_gilt_this():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.aendern(buch, eintrag, DO, None, _werte("2026-09-17T09:00:00"), neue_id)
    assert "2026-09-17" in buch.eintraege[eintrag]["exceptions"]


def test_this_mit_anderer_wiederholung_ist_unzulaessig():
    buch, neue_id, eintrag = _buch_mit_serie()
    _fehler("umfang_unzulaessig", "scope", terminbuch.aendern,
            buch, eintrag, DO, "this", _werte("2026-09-17T08:00:00", wiederholung="daily"), neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {}


def test_this_mit_anderem_fahrzeug_sagt_ab_und_legt_dort_einmalig_an():
    buch, neue_id, eintrag = _buch_mit_serie()
    _, (einmalig, alt) = terminbuch.aendern(
        buch, eintrag, DO, "this", _werte("2026-09-17T08:00:00", fahrzeug="auto-2"), neue_id)
    assert alt == eintrag
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-17": None}
    assert (buch.eintraege[einmalig]["vehicle"], buch.eintraege[einmalig]["repeat"]) == ("auto-2", "once")


def test_following_beendet_die_serie_und_beginnt_eine_neue():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.aendern(buch, eintrag, FR, "this", _werte("2026-09-18T10:00:00"), neue_id)
    terminbuch.aendern(buch, eintrag, date(2026, 9, 22), "this", _werte("2026-09-22T11:00:00"), neue_id)
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    _, (folge, alt) = terminbuch.aendern(
        buch, eintrag, FR, "following", _werte("2026-09-18T09:00:00", strecke_km=50), neue_id)
    assert alt == eintrag
    assert buch.eintraege[eintrag]["until"] == "2026-09-18"
    assert buch.eintraege[eintrag]["exceptions"] == {}
    assert buch.eintraege[folge]["departure"] == "2026-09-18T09:00:00"
    assert buch.eintraege[folge]["distance_km"] == 50
    # Die Ausnahmen danach wandern mit, die am Datum selbst nicht.
    assert set(buch.eintraege[folge]["exceptions"]) == {"2026-09-22", "2026-09-23"}


def test_following_mit_anderem_tag_setzt_die_ausnahmen_zurueck():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="weekly")
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 30))], None, neue_id)
    _, (folge, _) = terminbuch.aendern(
        buch, eintrag, date(2026, 9, 23), "following", _werte("2026-09-24T08:00:00", wiederholung="weekly"),
        neue_id)
    assert buch.eintraege[folge]["exceptions"] == {}


def test_following_mit_anderer_wiederholung_setzt_die_ausnahmen_zurueck():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    _, (folge, _) = terminbuch.aendern(
        buch, eintrag, FR, "following", _werte("2026-09-18T08:00:00", wiederholung="daily"), neue_id)
    assert buch.eintraege[folge]["exceptions"] == {}


def test_following_am_ersten_termin_wirkt_wie_all():
    buch, neue_id, eintrag = _buch_mit_serie()
    _, eintraege = terminbuch.aendern(
        buch, eintrag, MI, "following", _werte("2026-09-16T09:00:00"), neue_id)
    assert eintraege == [eintrag]
    assert list(buch.eintraege) == [eintrag]
    assert buch.eintraege[eintrag]["departure"] == "2026-09-16T09:00:00"


def test_all_verschiebt_den_beginn_um_dieselben_tage():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="weekly", abfahrt="2026-09-16T08:00:00")
    terminbuch.loeschen(buch, eintrag, date(2026, 10, 14), "following", neue_id)
    # Den Termin vom 30.09. auf Donnerstag 01.10. 07:30 legen, fuer alle.
    terminbuch.aendern(
        buch, eintrag, date(2026, 9, 30), "all", _werte("2026-10-01T07:30:00", wiederholung="weekly"), neue_id)
    assert buch.eintraege[eintrag]["departure"] == "2026-09-17T07:30:00"
    assert buch.eintraege[eintrag]["until"] == "2026-10-15"


def test_all_behaelt_die_ausnahmen_ohne_neuen_tag_und_ohne_neue_regel():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    terminbuch.aendern(buch, eintrag, FR, "this", _werte("2026-09-18T10:00:00"), neue_id)
    terminbuch.aendern(buch, eintrag, FR, "all", _werte("2026-09-18T07:00:00"), neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-23": None}
    assert buch.eintraege[eintrag]["departure"] == "2026-09-16T07:00:00"


def test_all_mit_neuer_regel_setzt_die_ausnahmen_zurueck():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    terminbuch.aendern(buch, eintrag, MI, "all", _werte(wiederholung="daily"), neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {}


def test_aendern_ohne_eintrag_oder_termin():
    buch, neue_id, eintrag = _buch_mit_serie()
    _fehler("eintrag_unbekannt", "entry", terminbuch.aendern, buch, "weg", DO, "this", _werte(), neue_id)
    samstag = date(2026, 9, 19)
    _fehler("termin_unbekannt", "date", terminbuch.aendern, buch, eintrag, samstag, "this", _werte(), neue_id)
    terminbuch.absagen(buch, [(eintrag, DO)], None, neue_id)
    _fehler("termin_unbekannt", "date", terminbuch.aendern, buch, eintrag, DO, "this", _werte(), neue_id)


# --- Loeschen ------------------------------------------------------------------


def test_loeschen_this_sagt_einen_termin_ab():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.loeschen(buch, eintrag, DO, "this", neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-17": None}


def test_loeschen_following_beendet_die_serie():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    terminbuch.loeschen(buch, eintrag, FR, "following", neue_id)
    assert buch.eintraege[eintrag]["until"] == "2026-09-18"
    assert buch.eintraege[eintrag]["exceptions"] == {}


def test_loeschen_following_am_ersten_termin_und_all_loeschen_den_eintrag():
    for umfang, datum in (("following", MI), ("all", FR)):
        buch, neue_id, eintrag = _buch_mit_serie()
        terminbuch.loeschen(buch, eintrag, datum, umfang, neue_id)
        assert buch.eintraege == {}


# --- Absagen und Rueckgaengig, Spec Abschnitt 2.2 ------------------------------


def test_absagen_ohne_schritt_ist_ein_eigener_schritt():
    buch, neue_id, serie = _buch_mit_serie()
    _, (einmalig,) = terminbuch.anlegen(buch, _werte(wiederholung="once", fahrzeug="auto-1"), neue_id)
    schritt = terminbuch.absagen(buch, [(serie, DO), (einmalig, MI)], None, neue_id)
    assert buch.eintraege[serie]["exceptions"] == {"2026-09-17": None}
    assert einmalig not in buch.eintraege
    assert len(buch.schritte) == 3
    terminbuch.rueckgaengig(buch, schritt)
    assert buch.eintraege[serie]["exceptions"] == {}
    assert einmalig in buch.eintraege


def test_absagen_mit_schritt_gehoert_zum_speichern_davor():
    buch, neue_id, serie = _buch_mit_serie()
    speichern, (einmalig,) = terminbuch.anlegen(
        buch, _werte("2026-09-17T07:00:00", wiederholung="once"), neue_id)
    assert terminbuch.absagen(buch, [(serie, DO)], speichern, neue_id) == speichern
    assert len(buch.schritte) == 2
    terminbuch.rueckgaengig(buch, speichern)
    assert einmalig not in buch.eintraege
    assert buch.eintraege[serie]["exceptions"] == {}


def test_absagen_im_selben_eintrag_behaelt_den_stand_vor_dem_speichern():
    buch, neue_id, serie = _buch_mit_serie()
    speichern, _ = terminbuch.aendern(buch, serie, DO, "this", _werte("2026-09-17T09:00:00"), neue_id)
    terminbuch.absagen(buch, [(serie, FR)], speichern, neue_id)
    terminbuch.rueckgaengig(buch, speichern)
    assert buch.eintraege[serie]["exceptions"] == {}


def test_absagen_mit_unbekanntem_schritt_wird_ein_eigener():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.absagen(buch, [(serie, DO)], "vergessen", neue_id)
    assert schritt != "vergessen" and terminbuch.schritt_bekannt(buch, schritt)


def test_absagen_prueft_jeden_termin_vor_der_ersten_aenderung():
    buch, neue_id, serie = _buch_mit_serie()
    _fehler("eintrag_unbekannt", "entry", terminbuch.absagen, buch, [(serie, DO), ("weg", DO)], None, neue_id)
    _fehler("termin_unbekannt", "date", terminbuch.absagen, buch, [(serie, DO), (serie, DO)], None, neue_id)
    assert buch.eintraege[serie]["exceptions"] == {}
    assert len(buch.schritte) == 1


def test_rueckgaengig_nach_einer_spaeteren_aenderung_geht_nicht():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.loeschen(buch, serie, DO, "this", neue_id)
    terminbuch.loeschen(buch, serie, FR, "this", neue_id)
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, schritt)


def test_rueckgaengig_geht_einmal():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.loeschen(buch, serie, DO, "this", neue_id)
    terminbuch.rueckgaengig(buch, schritt)
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, schritt)


def test_rueckgaengig_nach_geloeschtem_fahrzeug_geht_nicht():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.loeschen(buch, serie, DO, "this", neue_id)
    assert terminbuch.fahrzeuge_bereinigen(buch, {"auto-2"})
    assert buch.eintraege == {}
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, schritt)


def test_der_51_schritt_verdraengt_den_ersten():
    buch, neue_id = terminbuch.Buch(), _ids()
    erster, _ = terminbuch.anlegen(buch, _werte(), neue_id)
    for _ in range(50):
        terminbuch.anlegen(buch, _werte(), neue_id)
    assert len(buch.schritte) == 50
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, erster)


# --- Speicher -------------------------------------------------------------------


def test_die_speicherform_traegt_das_risiko_nur_wenn_es_gesetzt_ist():
    buch, _, eintrag = _buch_mit_serie()
    assert set(buch.speicherform()) == {"entries"}
    buch.risiko = 3
    wieder = terminbuch.Buch(buch.speicherform())
    assert (wieder.risiko, wieder.eintraege) == (3, buch.eintraege)
    assert terminbuch.Buch().risiko is None
```

- [ ] **Step 2: Rot**

Run: `$HAPY -m pytest -q --rootdir . tests/test_terminbuch.py`
Expected: `1 error` beim Sammeln, `No module named 'meteo_volt_c3.terminbuch'`

- [ ] **Step 3: Das Modul**

`custom_components/meteo_volt/terminbuch.py`:

```python
"""Der Inhalt des Terminspeichers und seine Schritte, ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Hier steht, was Anlegen, Aendern, Loeschen, Absagen und
Rueckgaengig mit den Eintraegen tun: Serien, Ausnahmen, Umfang.

Jeder schreibende Aufruf ist ein Schritt mit einer Kennung. Rueckgaengig
stellt die Eintraege des Schritts her, wie sie vor ihm waren, solange sie
seitdem niemand anders geaendert hat. Die Schritte liegen nur im Speicher,
die letzten 50 je Standort. Das Risiko ist kein Schritt. Speichern, Signale
und neu planen macht terminverwaltung.py.

Jede Operation prueft zuerst und aendert dann: scheitert sie, bleibt das
Buch, wie es war.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2.1, 2.2 und 3
"""

from __future__ import annotations

import copy
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from . import termine
from .pruefungen import (
    EINTRAG_UNBEKANNT,
    RUECKGAENGIG_UNMOEGLICH,
    TERMIN_UNBEKANNT,
    UMFANG_UNZULAESSIG,
    Werte,
    fehler,
)
from .termine import ABFAHRT, AUSNAHMEN, BIS, DAUER, EINMALIG, FAHRER, FAHRZEUG, ID, LADESTAND, STRECKE, WIEDERHOLUNG

# --- Umfang, Spec Abschnitt 2.1 ---------------------------------------------

DIESER = "this"
FOLGENDE = "following"
ALLE = "all"
UMFAENGE = (DIESER, FOLGENDE, ALLE)

MAX_SCHRITTE = 50

# Der Store, Spec Abschnitt 3
RISIKO = "risk"
EINTRAEGE = "entries"


@dataclass
class Schritt:
    """Was ein Schritt geaendert hat: je Eintrag der Stand davor und danach, None fuer 'fehlt'."""

    kennung: str
    vorher: dict[str, dict | None]
    nachher: dict[str, dict | None]


class Buch:
    """Risiko und Eintraege eines Standorts, dazu seine Schritte."""

    def __init__(self, daten: dict | None = None, schritte: deque | None = None) -> None:
        daten = daten or {}
        self.risiko: int | None = daten.get(RISIKO)
        self.eintraege: dict[str, dict] = {eintrag[ID]: eintrag for eintrag in daten.get(EINTRAEGE, [])}
        self.schritte: deque[Schritt] = deque(maxlen=MAX_SCHRITTE) if schritte is None else schritte

    def speicherform(self) -> dict:
        """Was in den Store geht. Das Risiko nur, wenn es jemand gesetzt hat."""
        daten: dict = {EINTRAEGE: [copy.deepcopy(eintrag) for eintrag in self.eintraege.values()]}
        if self.risiko is not None:
            daten[RISIKO] = self.risiko
        return daten


# --- Hilfen -------------------------------------------------------------------


def _eintrag(buch: Buch, eintrag_id: str) -> dict:
    eintrag = buch.eintraege.get(eintrag_id)
    if eintrag is None:
        raise fehler(EINTRAG_UNBEKANNT, "entry")
    return eintrag


def _termin_pruefen(eintrag: dict, datum: date) -> None:
    if not termine.hat_termin(eintrag, datum):
        raise fehler(TERMIN_UNBEKANNT, "date")


def _neuer_eintrag(kennung: str, werte: Werte) -> dict:
    return {
        ID: kennung,
        FAHRZEUG: werte.fahrzeug,
        ABFAHRT: werte.abfahrt,
        DAUER: werte.dauer_min,
        WIEDERHOLUNG: werte.wiederholung,
        STRECKE: werte.strecke_km,
        FAHRER: werte.fahrer,
        LADESTAND: werte.ladestand,
        BIS: None,
        AUSNAHMEN: {},
    }


def _ausnahme(werte: Werte) -> dict:
    return {ABFAHRT: werte.abfahrt, DAUER: werte.dauer_min, STRECKE: werte.strecke_km,
            FAHRER: werte.fahrer, LADESTAND: werte.ladestand}


def _mit_ausnahme(eintrag: dict, datum: date, werte: dict | None) -> dict:
    """Eine Kopie mit der Ausnahme am Datum. None sagt den Termin ab."""
    neu = copy.deepcopy(eintrag)
    neu[AUSNAHMEN][datum.isoformat()] = werte
    return neu


def _beendet(eintrag: dict, datum: date) -> dict:
    """Eine Kopie, deren Serie vor datum endet, ohne die Ausnahmen ab dort."""
    neu = copy.deepcopy(eintrag)
    neu[BIS] = datum.isoformat()
    neu[AUSNAHMEN] = {tag: werte for tag, werte in eintrag[AUSNAHMEN].items() if tag < datum.isoformat()}
    return neu


def _datum(text: str) -> date:
    return date.fromisoformat(text[:10])


def _anwenden(
    buch: Buch,
    aenderungen: dict[str, dict | None],
    neue_id: Callable[[], str],
    zu_schritt: str | None = None,
) -> str:
    """Setzt die Eintraege und haelt fest, wie sie vorher waren. Gibt den Schritt zurueck.

    Mit zu_schritt gehoert die Aenderung zu einem frueheren Schritt: das
    Absagen nach dem Speichern eines Termins. Rueckgaengig nimmt dann beides
    zurueck. Ist der Schritt nicht mehr da, etwa nach einem Neustart, wird
    es ein eigener.
    """
    schritt = next((s for s in buch.schritte if s.kennung == zu_schritt), None)
    if schritt is None:
        schritt = Schritt(neue_id(), {}, {})
        buch.schritte.append(schritt)  # der 51. verdraengt den ersten
    for eintrag_id, neu in aenderungen.items():
        if eintrag_id not in schritt.vorher:
            schritt.vorher[eintrag_id] = copy.deepcopy(buch.eintraege.get(eintrag_id))
        if neu is None:
            buch.eintraege.pop(eintrag_id, None)
        else:
            buch.eintraege[eintrag_id] = neu
        schritt.nachher[eintrag_id] = copy.deepcopy(neu)
    return schritt.kennung


# --- Die Operationen, Spec Abschnitte 2.1 und 2.2 ------------------------------


def anlegen(buch: Buch, werte: Werte, neue_id: Callable[[], str]) -> tuple[str, list[str]]:
    """Ein neuer Eintrag. Gibt (Schritt, [Eintrag]) zurueck."""
    eintrag = _neuer_eintrag(neue_id(), werte)
    return _anwenden(buch, {eintrag[ID]: eintrag}, neue_id), [eintrag[ID]]


def aendern(
    buch: Buch,
    eintrag_id: str,
    datum: date,
    umfang: str | None,
    werte: Werte,
    neue_id: Callable[[], str],
) -> tuple[str, list[str]]:
    """Aendert den Termin am Datum. Gibt (Schritt, Eintraege) zurueck.

    Die Eintraege sind die, die der Schritt angelegt oder geaendert hat; der
    mit den neuen Werten steht vorn. Ein einmaliger Termin kennt keinen
    Umfang, ohne Umfang gilt this.
    """
    eintrag = _eintrag(buch, eintrag_id)
    _termin_pruefen(eintrag, datum)
    if eintrag[WIEDERHOLUNG] == EINMALIG:
        neu = _neuer_eintrag(eintrag_id, werte)
        return _anwenden(buch, {eintrag_id: neu}, neue_id), [eintrag_id]

    umfang = umfang or DIESER
    regel_neu = werte.wiederholung != eintrag[WIEDERHOLUNG]
    tag_neu = _datum(werte.abfahrt) != datum

    if umfang == DIESER:
        if regel_neu:
            raise fehler(UMFANG_UNZULAESSIG, "scope")
        if werte.fahrzeug != eintrag[FAHRZEUG]:
            # Anderes Fahrzeug: hier absagen, dort einmalig anlegen.
            einmalig = _neuer_eintrag(neue_id(), replace(werte, wiederholung=EINMALIG))
            aenderungen = {einmalig[ID]: einmalig, eintrag_id: _mit_ausnahme(eintrag, datum, None)}
            return _anwenden(buch, aenderungen, neue_id), [einmalig[ID], eintrag_id]
        aenderungen = {eintrag_id: _mit_ausnahme(eintrag, datum, _ausnahme(werte))}
        return _anwenden(buch, aenderungen, neue_id), [eintrag_id]

    if umfang == FOLGENDE and datum != termine.erster_termin(eintrag):
        # Die Serie endet vor dem Datum, ab ihm beginnt ein neuer Eintrag.
        folge = _neuer_eintrag(neue_id(), werte)
        folge[BIS] = eintrag[BIS]
        if not (regel_neu or tag_neu):
            # Die Ausnahmen danach wandern mit. Die am Datum selbst nicht: der
            # Termin traegt jetzt die neuen Werte.
            folge[AUSNAHMEN] = {
                tag: copy.deepcopy(w) for tag, w in eintrag[AUSNAHMEN].items() if tag > datum.isoformat()}
        aenderungen = {folge[ID]: folge, eintrag_id: _beendet(eintrag, datum)}
        return _anwenden(buch, aenderungen, neue_id), [folge[ID], eintrag_id]

    # ALLE, oder FOLGENDE am ersten Termin: neue Werte fuer die Serie. Ein
    # verschobenes Datum verschiebt ihren Beginn um dieselben Tage.
    verschiebung = _datum(werte.abfahrt) - datum
    neu = _neuer_eintrag(eintrag_id, werte)
    neu[ABFAHRT] = (_datum(eintrag[ABFAHRT]) + verschiebung).isoformat() + werte.abfahrt[10:]
    if eintrag[BIS] is not None:
        neu[BIS] = (date.fromisoformat(eintrag[BIS]) + verschiebung).isoformat()
    if not (regel_neu or tag_neu):
        neu[AUSNAHMEN] = {
            tag: copy.deepcopy(w) for tag, w in eintrag[AUSNAHMEN].items() if tag != datum.isoformat()}
    return _anwenden(buch, {eintrag_id: neu}, neue_id), [eintrag_id]


def loeschen(
    buch: Buch, eintrag_id: str, datum: date, umfang: str | None, neue_id: Callable[[], str]
) -> str:
    """Loescht den Termin am Datum im Umfang. Gibt den Schritt zurueck."""
    eintrag = _eintrag(buch, eintrag_id)
    _termin_pruefen(eintrag, datum)
    umfang = umfang or DIESER
    if eintrag[WIEDERHOLUNG] == EINMALIG or umfang == ALLE:
        return _anwenden(buch, {eintrag_id: None}, neue_id)
    if umfang == DIESER:
        return _anwenden(buch, {eintrag_id: _mit_ausnahme(eintrag, datum, None)}, neue_id)
    if datum == termine.erster_termin(eintrag):
        return _anwenden(buch, {eintrag_id: None}, neue_id)
    return _anwenden(buch, {eintrag_id: _beendet(eintrag, datum)}, neue_id)


def absagen(
    buch: Buch,
    liste: list[tuple[str, date]],
    zu_schritt: str | None,
    neue_id: Callable[[], str],
) -> str:
    """Sagt Termine ab: bei einer Serie eine Ausnahme, ein einmaliger wird geloescht.

    Nennt der Aufruf den Schritt des Speicherns davor, gehoert das Absagen
    zu ihm (Spec Abschnitt 2.2).
    """
    arbeit: dict[str, dict | None] = {}
    for eintrag_id, datum in liste:
        eintrag = arbeit[eintrag_id] if eintrag_id in arbeit else buch.eintraege.get(eintrag_id)
        if eintrag is None:
            raise fehler(EINTRAG_UNBEKANNT, "entry")
        _termin_pruefen(eintrag, datum)
        arbeit[eintrag_id] = None if eintrag[WIEDERHOLUNG] == EINMALIG else _mit_ausnahme(eintrag, datum, None)
    return _anwenden(buch, arbeit, neue_id, zu_schritt)


def rueckgaengig(buch: Buch, kennung: str) -> None:
    """Stellt die Eintraege des Schritts her, wie sie vor ihm waren.

    Nur solange jeder davon noch so ist, wie der Schritt ihn hinterliess.
    Danach ist der Schritt verbraucht.
    """
    schritt = next((s for s in buch.schritte if s.kennung == kennung), None)
    if schritt is None or any(
        buch.eintraege.get(eintrag_id) != nachher for eintrag_id, nachher in schritt.nachher.items()
    ):
        raise fehler(RUECKGAENGIG_UNMOEGLICH, "step")
    for eintrag_id, vorher in schritt.vorher.items():
        if vorher is None:
            buch.eintraege.pop(eintrag_id, None)
        else:
            buch.eintraege[eintrag_id] = copy.deepcopy(vorher)
    buch.schritte.remove(schritt)


def fahrzeuge_bereinigen(buch: Buch, fahrzeuge: set[str]) -> bool:
    """Entfernt die Eintraege geloeschter Fahrzeuge. Kein Schritt. True, wenn einer ging."""
    weg = [eintrag_id for eintrag_id, e in buch.eintraege.items() if e[FAHRZEUG] not in fahrzeuge]
    for eintrag_id in weg:
        del buch.eintraege[eintrag_id]
    return bool(weg)


def schritt_bekannt(buch: Buch, kennung: str) -> bool:
    return any(s.kennung == kennung for s in buch.schritte)
```

- [ ] **Step 4: Grün**

Run: `$HAPY -m pytest -q --rootdir . tests/test_terminbuch.py`
Expected: `28 passed`

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `395 passed`

- [ ] **Step 5: Commit**

```bash
git add custom_components/meteo_volt/terminbuch.py tests/test_terminbuch.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Edit series by scope, cancel appointments and undo steps

This, following and all behave as the spec says, exceptions reset or
move with the series. Every write is a step; undo restores what the
step changed as long as nobody changed it since, and a cancel that
belongs to a save is undone together with it. Fifty steps per site.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: `terminanfrage.py` und `anfrage_bauen` — Termine im Request

**Files:**
- Create: `custom_components/meteo_volt/terminanfrage.py`
- Modify: `custom_components/meteo_volt/standort.py` (`anfrage_bauen`)
- Test: `tests/test_terminanfrage.py`

**Interfaces:**
- Consumes: aus Task 1 `Termin`, `utc`, `ausrollen` (im Test), `lokal`.
- Produces:
  - `AUSROLLEN_OHNE_PLAN = timedelta(days=14)`, `RISIKO_VORGABE = 2`, `WEG = "weg"`, `ZIEL = "ziel"`.
  - `ausrollen_bis(plan, jetzt) -> datetime`, `kennung(eintrag, datum, art) -> str`, `zerlegen(text) -> (eintrag, date, art) | None`, `fragmente(termine, soc_min, jetzt) -> dict[str, dict]`.
  - `standort.anfrage_bauen(..., termine=None, risiko=None)`: mit `termine` bekommt jedes Fahrzeug seine `consumption` und `constraints`, ohne eigenes Fragment `{"type": "trips", "trips": []}`; mit `risiko` steht `risk` im Request. Ohne beide wie vor C3.

- [ ] **Step 1: Den Test schreiben**

`tests/test_terminanfrage.py`:

```python
"""Prueft, was aus Terminen im Request wird, ohne Home Assistant. Spec C3 Abschnitte 4 und 10.

Der Request wird gegen das vendorte plan-request.schema.json geprueft, mit
der Form trips aus A5V. jsonschema prueft format date-time ohne FormatChecker
nicht; dass jeder Zeitpunkt einen Offset traegt (R1), prueft deshalb ein
eigener Test.

Was dieser Test NICHT sieht: wie der Plan-Dienst trips bucht. Das prueft
der Brain.
"""

import importlib
import json
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
termine = importlib.import_module(f"{_PAKET}.termine")
terminanfrage = importlib.import_module(f"{_PAKET}.terminanfrage")
standort = importlib.import_module(f"{_PAKET}.standort")
stammdaten = importlib.import_module(f"{_PAKET}.stammdaten")

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # 12:00 in Berlin
BIS = JETZT + timedelta(days=7)

_ROH = json.loads((CONTRACT / "plan-request.schema.json").read_text(encoding="utf-8"))
REQUEST_SCHEMA = {k: v for k, v in _ROH.items() if k != "x-meteo-volt-contract"}


def _eintrag(eintrag_id, abfahrt, dauer=600, soc=None, fahrzeug="auto-1", wiederholung="once"):
    return {"id": eintrag_id, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": dauer,
            "repeat": wiederholung, "distance_km": 42, "driver": None, "soc": soc, "until": None,
            "exceptions": {}}


def _fragmente(*eintraege, soc_min=None):
    auswahl = termine.ausrollen(list(eintraege), BERLIN, JETZT, BIS)
    return terminanfrage.fragmente(auswahl, soc_min or {"auto-1": 15.0}, JETZT)


def _anfrage(termine_je_fahrzeug, risiko=2):
    fahrzeug = {**stammdaten.FAHRZEUG_DEFAULTS, stammdaten.FELD_SOC_ENTITAET: "sensor.soc"}
    anfrage, ausgelassen = standort.anfrage_bauen(
        [("wb-1", dict(stammdaten.LADEPUNKT_DEFAULTS))],
        [("auto-1", fahrzeug), ("auto-2", dict(fahrzeug))],
        {fid: standort.Messung(zustand="47.5", gemeldet=JETZT) for fid in ("auto-1", "auto-2")},
        {"grid_fees": 0.0}, "Europe/Berlin", termine=termine_je_fahrzeug, risiko=risiko)
    assert ausgelassen == {}
    return anfrage


# --- Bis wohin ausgerollt wird ----------------------------------------------


def test_ausgerollt_wird_bis_zum_horizont_des_letzten_plans():
    ende = "2026-09-23T00:00:00+02:00"
    assert terminanfrage.ausrollen_bis({"horizon_end": ende}, JETZT) == datetime.fromisoformat(ende)


def test_ohne_plan_oder_mit_abgelaufenem_14_tage():
    for plan in (None, {}, {"horizon_end": "kaputt"}, {"horizon_end": "2026-09-16T12:00:00+02:00"}):
        assert terminanfrage.ausrollen_bis(plan, JETZT) == JETZT + timedelta(days=14), plan


# --- Die IDs ------------------------------------------------------------------


def test_jede_id_zerlegt_sich_zurueck():
    for art in ("weg", "ziel"):
        text = terminanfrage.kennung("3f2a9c", date(2026, 9, 17), art)
        assert text == f"3f2a9c/2026-09-17/{art}"
        assert terminanfrage.zerlegen(text) == ("3f2a9c", date(2026, 9, 17), art)


def test_base_und_fremdes_zerlegen_sich_nicht():
    for text in ("base", None, "", "a/b", "a/2026-09-17/fahrt", "a/2026-13-01/weg", "/2026-09-17/weg"):
        assert terminanfrage.zerlegen(text) is None, text


# --- Die Fragmente, Spec Abschnitt 4 --------------------------------------------


def test_ein_termin_mit_ladestand_ergibt_abwesenheit_fahrt_und_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", soc=80))["auto-1"]
    assert teil["consumption"] == {"type": "trips", "trips": [
        {"departure": "2026-09-17T08:00:00+02:00", "km": 42.0}]}
    assert teil["constraints"] == [
        {"type": "unavailable", "id": "e1/2026-09-17/weg",
         "from": "2026-09-17T08:00:00+02:00", "to": "2026-09-17T18:00:00+02:00"},
        {"type": "target", "id": "e1/2026-09-17/ziel",
         "deadline": "2026-09-17T08:00:00+02:00", "target_soc_pct": 80.0}]


def test_eine_fahrt_ist_kein_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00"))["auto-1"]
    assert [c["type"] for c in teil["constraints"]] == ["unavailable"]


def test_ein_ladestand_unter_dem_min_soc_ergibt_kein_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", soc=14.9))["auto-1"]
    assert [c["type"] for c in teil["constraints"]] == ["unavailable"]
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", soc=15))["auto-1"]
    assert [c["type"] for c in teil["constraints"]] == ["unavailable", "target"]


def test_ein_laufender_termin_ist_nur_abwesenheit():
    teil = _fragmente(_eintrag("e1", "2026-09-16T08:00:00", soc=80))["auto-1"]
    assert teil["consumption"]["trips"] == []
    assert teil["constraints"] == [{"type": "unavailable", "id": "e1/2026-09-16/weg",
                                    "from": "2026-09-16T08:00:00+02:00", "to": "2026-09-16T18:00:00+02:00"}]


def test_vorbei_und_hinter_dem_ende_fehlt():
    vorbei = _eintrag("e1", "2026-09-15T08:00:00")
    dahinter = _eintrag("e2", "2026-09-23T12:00:00")  # BIS ist 23.09. 12:00 Berlin
    assert _fragmente(vorbei, dahinter) == {"auto-1": {"consumption": {"type": "trips", "trips": []}}}


def test_jedes_fahrzeug_bekommt_trips_auch_ohne_termin():
    teile = _fragmente(_eintrag("e1", "2026-09-17T08:00:00"), soc_min={"auto-1": 15.0, "auto-2": 20.0})
    assert teile["auto-2"] == {"consumption": {"type": "trips", "trips": []}}


def test_ein_termin_eines_unbekannten_fahrzeugs_faellt_weg():
    assert _fragmente(_eintrag("e1", "2026-09-17T08:00:00", fahrzeug="weg")) == {
        "auto-1": {"consumption": {"type": "trips", "trips": []}}}


# --- Der Request, gegen das Schema ------------------------------------------------


def test_der_request_mit_terminen_validiert_gegen_das_schema():
    serie = _eintrag("e1", "2026-09-16T08:00:00", soc=80, wiederholung="weekdays")
    anfrage = _anfrage(_fragmente(serie, soc_min={"auto-1": 15.0, "auto-2": 15.0}), risiko=3)
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert anfrage["risk"] == 3
    auto_1, auto_2 = anfrage["vehicles"]
    assert len(auto_1["consumption"]["trips"]) == 5  # Do, Fr, Mo, Di und Mi 08:00 vor BIS 12:00
    assert auto_2["consumption"] == {"type": "trips", "trips": []}
    assert "constraints" not in auto_2
    for auflage in auto_1["constraints"]:
        assert terminanfrage.zerlegen(auflage["id"])[0] == "e1"


def test_jeder_zeitpunkt_im_request_traegt_einen_offset():
    serie = _eintrag("e1", "2026-09-16T08:00:00", soc=80, wiederholung="daily")
    anfrage = _anfrage(_fragmente(serie, soc_min={"auto-1": 15.0, "auto-2": 15.0}))
    zeitpunkte = [f["departure"] for f in anfrage["vehicles"][0]["consumption"]["trips"]]
    for auflage in anfrage["vehicles"][0]["constraints"]:
        zeitpunkte += [auflage[k] for k in ("from", "to", "deadline") if k in auflage]
    assert len(zeitpunkte) > 10
    assert all(datetime.fromisoformat(z).tzinfo is not None for z in zeitpunkte)


def test_ein_fahrzeug_ohne_fragment_bekommt_eine_leere_liste():
    anfrage = _anfrage({})
    assert [f["consumption"] for f in anfrage["vehicles"]] == [{"type": "trips", "trips": []}] * 2
    jsonschema.validate(anfrage, REQUEST_SCHEMA)


def test_ohne_c3_geht_der_request_wie_vorher():
    fahrzeug = {**stammdaten.FAHRZEUG_DEFAULTS, stammdaten.FELD_SOC_ENTITAET: "sensor.soc"}
    anfrage, _ = standort.anfrage_bauen(
        [("wb-1", dict(stammdaten.LADEPUNKT_DEFAULTS))], [("auto-1", fahrzeug)],
        {"auto-1": standort.Messung(zustand="47.5", gemeldet=JETZT)}, {}, "Europe/Berlin")
    assert "risk" not in anfrage
    assert anfrage["vehicles"][0]["consumption"] == {"type": "none"}
```

- [ ] **Step 2: Rot**

Run: `$HAPY -m pytest -q --rootdir . tests/test_terminanfrage.py`
Expected: `1 error` beim Sammeln, `No module named 'meteo_volt_c3.terminanfrage'`

- [ ] **Step 3: Das Modul**

`custom_components/meteo_volt/terminanfrage.py`:

```python
"""Was aus den Terminen im Request wird, ohne Home Assistant. Spec C3 Abschnitt 4.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Aus jedem Termin wird eine Abwesenheit, aus einem kuenftigen eine
Fahrt in consumption.trips (A5-Spec Abschnitt 2), und traegt er einen
Ladestand ab dem Min-SoC, ein Ziel. standort.anfrage_bauen setzt die
Fragmente je Fahrzeug in den Request.

Eine Fahrt ist kein Ziel: ein Termin ohne Ladestand erzeugt kein target.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 4
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .termine import Termin, utc

# Ohne Plan wird so weit ausgerollt: die Laenge des Admin-Horizonts.
AUSROLLEN_OHNE_PLAN = timedelta(days=14)

# Das Risiko, bis jemand es setzt: 2, "Ausgewogen", der Default des Kontrakts.
RISIKO_VORGABE = 2

# Die Art im dritten Teil einer ID, Spec Abschnitt 4.
WEG = "weg"
ZIEL = "ziel"


def ausrollen_bis(plan: dict | None, jetzt: datetime) -> datetime:
    """Bis wohin ausgerollt wird: horizon_end des letzten Plans, sonst 14 Tage.

    Was hinter dem Horizont liegt, wertet der Planer nicht aus (A0-Spec 3.6).
    Ein horizon_end, das schon vorbei ist, zaehlt wie kein Plan -- sonst
    ginge nach einem langen Ausfall kein einziger Termin mehr in den Request.
    """
    try:
        ende = datetime.fromisoformat(plan["horizon_end"])
    except (KeyError, TypeError, ValueError):
        ende = None
    if ende is None or utc(ende) <= utc(jetzt):
        return jetzt + AUSROLLEN_OHNE_PLAN
    return ende


def kennung(eintrag: str, datum: date, art: str) -> str:
    """'<eintrag>/<JJJJ-MM-TT>/<art>'. Je Fahrzeug eindeutig und nie 'base'."""
    return f"{eintrag}/{datum.isoformat()}/{art}"


def zerlegen(text: str | None) -> tuple[str, date, str] | None:
    """Eine ID zurueck in Eintrag, Datum und Art, oder None.

    None fuer 'base' und alles, was keine ID aus kennung() ist: reason eines
    Slots und constraint_id einer Verletzung tragen auch das Basisziel.
    """
    teile = (text or "").split("/")
    if len(teile) != 3 or not teile[0] or teile[2] not in (WEG, ZIEL):
        return None
    try:
        return teile[0], date.fromisoformat(teile[1]), teile[2]
    except ValueError:
        return None


def fragmente(termine: list[Termin], soc_min: dict[str, float], jetzt: datetime) -> dict[str, dict]:
    """consumption und constraints je Fahrzeug.

    termine sind schon ausgewaehlt: Rueckkehr nach jetzt, Abfahrt vor dem Ende
    des Ausrollens. soc_min nennt jedes Fahrzeug des Standorts; jedes bekommt
    trips, ohne Termin als leere Liste. constraints fehlt, wenn es leer waere.
    """
    ergebnis: dict[str, dict] = {
        fahrzeug: {"consumption": {"type": "trips", "trips": []}} for fahrzeug in soc_min
    }
    for termin in termine:
        teil = ergebnis.get(termin.fahrzeug)
        if teil is None:
            continue
        auflagen = teil.setdefault("constraints", [])
        # Immer: laeuft der Termin schon, liegt from in der Vergangenheit.
        auflagen.append({
            "type": "unavailable",
            "id": kennung(termin.eintrag, termin.datum, WEG),
            "from": termin.abfahrt.isoformat(),
            "to": termin.rueckkehr.isoformat(),
        })
        if utc(termin.abfahrt) <= utc(jetzt):
            continue  # R4: vergangener Verbrauch steckt im gemessenen Ladestand
        teil["consumption"]["trips"].append(
            {"departure": termin.abfahrt.isoformat(), "km": float(termin.strecke_km)})
        if termin.ladestand is not None and termin.ladestand >= soc_min[termin.fahrzeug]:
            auflagen.append({
                "type": "target",
                "id": kennung(termin.eintrag, termin.datum, ZIEL),
                "deadline": termin.abfahrt.isoformat(),
                "target_soc_pct": float(termin.ladestand),
            })
    return ergebnis
```

Run: `$HAPY -m pytest -q --rootdir . tests/test_terminanfrage.py`
Expected: `3 failed, 12 passed`, `TypeError: anfrage_bauen() got an unexpected keyword argument 'termine'`

- [ ] **Step 4: `anfrage_bauen` nimmt Termine und Risiko**

```diff
--- a/custom_components/meteo_volt/standort.py
+++ b/custom_components/meteo_volt/standort.py
@@ -86,4 +86,6 @@ def anfrage_bauen(
     haupteintrag: dict,
     zeitzone: str,
+    termine: dict[str, dict] | None = None,
+    risiko: int | None = None,
 ) -> tuple[dict | None, dict[str, str]]:
     """Der Request und die ausgelassenen Fahrzeuge. Spec Abschnitte 2 bis 4.
@@ -94,4 +96,8 @@ def anfrage_bauen(
     Request None.
 
+    termine und risiko kommen aus C3 (C3-Spec Abschnitt 4): je Fahrzeug
+    consumption und constraints, dazu risk. Laeuft C3 nicht, sind beide None,
+    und der Request geht wie vor C3 raus.
+
     now fehlt mit Absicht: die Uhr hat der Dienst, und eine falsch gehende
     Uhr im Haus verschoebe den Beginn des Plans.
@@ -109,13 +115,16 @@ def anfrage_bauen(
             ausgelassen[fahrzeug_id] = grund
             continue
-        fragmente.append(
-            stammdaten.zu_fahrzeug(
-                daten,
-                fahrzeug_id,
-                soc,
-                soc_measured_at=messung.gemeldet.isoformat(),
-                station_id=station_id,
-            )
+        fragment = stammdaten.zu_fahrzeug(
+            daten,
+            fahrzeug_id,
+            soc,
+            soc_measured_at=messung.gemeldet.isoformat(),
+            station_id=station_id,
         )
+        if termine is not None:
+            # Ohne Termin eine leere trips-Liste, nie none: so bleibt die Form
+            # gleich, ob ein Fahrzeug Termine hat oder nicht.
+            fragment.update(termine.get(fahrzeug_id) or {"consumption": {"type": "trips", "trips": []}})
+        fragmente.append(fragment)
     if not fragmente:
         return None, ausgelassen
@@ -123,6 +132,7 @@ def anfrage_bauen(
     anfrage = {
         "schema_version": 1,
-        # Wirkt mit consumption none noch nicht. Ohne sie stimmte der Default
-        # Europe/Berlin still nicht, sobald Z3 Fahrten nach Wochentag schickt.
+        # trips tragen Zeitpunkte mit Offset und brauchen sie nicht. Ohne sie
+        # stimmte der Default Europe/Berlin aber still nicht, sobald ein
+        # Verbrauch nach Tagesgrenzen gebucht wird.
         "timezone": zeitzone,
         "stations": [
@@ -132,4 +142,6 @@ def anfrage_bauen(
         "vehicles": fragmente,
     }
+    if risiko is not None:
+        anfrage["risk"] = risiko
     site = {}
     if CONF_GRID_FEES in haupteintrag and float(haupteintrag[CONF_GRID_FEES]) >= 0:
```

- [ ] **Step 5: Grün**

Run: `$HAPY -m pytest -q --rootdir . tests/test_terminanfrage.py tests/test_standort.py`
Expected: `95 passed` — die 80 aus C5 unverändert

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `410 passed`

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/terminanfrage.py custom_components/meteo_volt/standort.py tests/test_terminanfrage.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Turn appointments into absences, trips and targets in the request

Every appointment is an absence, a future one also a trip, and one
with a state of charge from the minimum on also a target. Every
vehicle sends trips, an empty list without appointments. Without C3
the request stays as before.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: `ansicht.py` — was das Panel liest

**Files:**
- Create: `custom_components/meteo_volt/ansicht.py`
- Test: `tests/test_ansicht.py`

**Interfaces:**
- Consumes: aus `standort.py` `Planstand`, `was_gilt`, `QUELLE_PLAN`; aus Task 1 `Termin`, `ueberschneiden`, `utc`; aus Task 4 `zerlegen`, `ZIEL`.
- Produces:
  - `planwerte(termin, stand, jetzt, soc_min) -> dict | None`, `hinweise(termin, umfeld, geraete, personen) -> list[dict]`, `termine_ansicht(auswahl, umfeld, stand, jetzt, soc_min, geraete, personen) -> list[dict]`.
  - `AUS_DEM_FAHRZEUGPLAN`, `AUS_DEM_KOPF`, `c6_wert(schluessel, zustand, tz)`, `fahrzeugplan(stand, fahrzeug_id, c6, plant) -> dict`.
  - `PREISSLOT`, `preise(prognose, jetzt) -> dict`.

- [ ] **Step 1: Den Test schreiben**

`tests/test_ansicht.py`:

```python
"""Prueft, was das Panel liest, ohne Home Assistant. Spec C3 Abschnitte 6 und 10.

Die Plaene sind hier erzeugt: 48 Slots ab 12:00 in Berlin, soc_end_pct im
Slot i ist 50 + i. So steht jeder erwartete Wert direkt im Test.

Was dieser Test NICHT sieht: die Websocket-Befehle, ihre Meldungen und die
Entitaeten aus C6 in Home Assistant. Das zeigt die Abnahme.
"""

import importlib
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
ansicht = importlib.import_module(f"{_PAKET}.ansicht")
termine = importlib.import_module(f"{_PAKET}.termine")
standort = importlib.import_module(f"{_PAKET}.standort")
planabruf = importlib.import_module(f"{_PAKET}.planabruf")

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # 12:00 in Berlin
BEGINN = datetime(2026, 9, 16, 12, 0, tzinfo=BERLIN)


def _plan(verletzungen=()):
    slots = [{"t": (BEGINN + timedelta(minutes=15 * i)).isoformat(), "charge": False,
              "price": 0.2, "source": "epex", "soc_end_pct": 50.0 + i} for i in range(48)]
    return {
        "slot_minutes": 15,
        "horizon_end": "2026-09-17T00:00:00+02:00",
        "prices_known_until": "2026-09-16T23:45:00+02:00",
        "computed_at": "2026-09-16T11:50:00+02:00",
        "vehicles": [{"id": "auto-1", "slots": slots, "intervals": [], "total_kwh": 0.0,
                      "total_cost_eur": 0.0, "soc_end_pct": 97.0, "violations": list(verletzungen)}],
    }


def _stand(plan=None, erhalten_um=JETZT - timedelta(minutes=5), **felder):
    return standort.Planstand(
        plan=_plan() if plan is None else plan,
        erhalten_um=erhalten_um,
        anfrage={"vehicles": [{"id": "auto-1", "soc_pct": 47.5, "connection": {"station_id": None}}],
                 "stations": []},
        **felder)


def _termin(abfahrt, dauer=60, eintrag="e1", fahrzeug="auto-1", fahrer=None):
    eintrag_dict = {"id": eintrag, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": dauer,
                    "repeat": "once", "distance_km": 42, "driver": fahrer, "soc": None, "until": None,
                    "exceptions": {}}
    (termin,) = termine.termine_von(eintrag_dict, BERLIN, JETZT - timedelta(days=1), JETZT + timedelta(days=3))
    return termin


# --- Planwerte je Termin --------------------------------------------------------


def test_die_ladestaende_vor_und_nach_der_fahrt():
    werte = ansicht.planwerte(_termin("2026-09-16T14:00:00"), _stand(), JETZT, 15.0)
    assert werte == {"soc_at_departure": 57.0, "soc_after_trip": 58.0, "target_missing_kwh": None,
                     "below_min": False, "running_until": None}


def test_die_abfahrt_im_ersten_slot_nimmt_den_ladestand_aus_dem_request():
    werte = ansicht.planwerte(_termin("2026-09-16T12:05:00"), _stand(), JETZT, 15.0)
    assert (werte["soc_at_departure"], werte["soc_after_trip"]) == (47.5, 50.0)


def test_ein_unerreichbares_ziel_nennt_die_fehlenden_kwh():
    verletzung = {"type": "target_unreachable", "constraint_id": "e1/2026-09-16/ziel",
                  "missing_kwh": 13.4, "message": "..."}
    fremd = {**verletzung, "constraint_id": "e2/2026-09-16/ziel", "missing_kwh": 9.9}
    basis = {**verletzung, "constraint_id": "base", "missing_kwh": 1.0}
    stand = _stand(_plan([fremd, basis, verletzung]))
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), stand, JETZT, 15.0)["target_missing_kwh"] == 13.4


def test_unter_dem_min_soc_nach_der_fahrt():
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), _stand(), JETZT, 58.1)["below_min"]
    assert not ansicht.planwerte(_termin("2026-09-16T14:00:00"), _stand(), JETZT, 58.0)["below_min"]


def test_ein_laufender_termin_nennt_seine_rueckkehr():
    werte = ansicht.planwerte(_termin("2026-09-16T11:00:00", dauer=120), _stand(), JETZT, 15.0)
    assert werte == {"soc_at_departure": None, "soc_after_trip": None, "target_missing_kwh": None,
                     "below_min": False, "running_until": "2026-09-16T13:00:00+02:00"}


def test_hinter_dem_horizont_und_ohne_brauchbaren_plan_kein_planwert():
    assert ansicht.planwerte(_termin("2026-09-17T08:00:00"), _stand(), JETZT, 15.0) is None
    alt = _stand(erhalten_um=JETZT - timedelta(hours=12))
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), alt, JETZT, 15.0) is None
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), standort.Planstand(), JETZT, 15.0) is None
    kaputt = _stand({**_plan(), "slot_minutes": "15"})
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), kaputt, JETZT, 15.0) is None


# --- Hinweise -------------------------------------------------------------------


def test_overlap_mit_einem_anderen_termin_desselben_fahrzeugs():
    a = _termin("2026-09-16T14:00:00", eintrag="e1")
    b = _termin("2026-09-16T14:30:00", eintrag="e2")
    anschluss = _termin("2026-09-16T15:00:00", eintrag="e3")
    assert ansicht.hinweise(a, [a, b, anschluss], {}, set()) == [{"type": "overlap"}]
    assert ansicht.hinweise(anschluss, [a, anschluss], {}, set()) == []


def test_driver_busy_nennt_das_andere_fahrzeug():
    eigener = _termin("2026-09-16T14:00:00", eintrag="e1", fahrer="person.anna")
    anderer = _termin("2026-09-16T14:30:00", eintrag="e2", fahrzeug="auto-2", fahrer="person.anna")
    spaeter = _termin("2026-09-16T15:00:00", eintrag="e3", fahrzeug="auto-3", fahrer="person.anna")
    geraete = {"auto-1": "geraet-1", "auto-2": "geraet-2", "auto-3": "geraet-3"}
    assert ansicht.hinweise(eigener, [eigener, anderer, spaeter], geraete, {"person.anna"}) == [
        {"type": "driver_busy", "vehicle": "geraet-2"}]
    assert ansicht.hinweise(eigener, [eigener, anderer], geraete, set()) == []


# --- Die Termine fuer das Panel ------------------------------------------------------


def test_ein_termin_fuer_das_panel():
    termin = _termin("2026-09-16T14:00:00", fahrer="person.weg")
    (eintrag,) = ansicht.termine_ansicht([termin], [termin], _stand(), JETZT, {"auto-1": 15.0},
                                         {"auto-1": "geraet-1"}, set())
    assert eintrag == {
        "entry": "e1", "date": "2026-09-16", "vehicle": "geraet-1",
        "departure": "2026-09-16T14:00:00+02:00", "return": "2026-09-16T15:00:00+02:00",
        "distance_km": 42, "driver": None, "soc": None, "repeat": "once", "changed": False,
        "plan": {"soc_at_departure": 57.0, "soc_after_trip": 58.0, "target_missing_kwh": None,
                 "below_min": False, "running_until": None},
        "hints": []}


# --- Der Plan eines Fahrzeugs ---------------------------------------------------------


def test_der_plan_eines_fahrzeugs():
    stand = _stand(fehler=planabruf.PlanNichtVerfuegbar(status=503))
    c6 = {"charge_now": False, "charge_now_kw": 0.0, "next_charge_start": None}
    plan = ansicht.fahrzeugplan(stand, "auto-1", c6, True)
    assert plan["slots"] == _plan()["vehicles"][0]["slots"]
    assert (plan["soc_end_pct"], plan["horizon_end"]) == (97.0, "2026-09-17T00:00:00+02:00")
    assert plan["received_at"] == "2026-09-16T09:55:00+00:00"
    assert (plan["charge_now"], plan["planning"]) == (False, True)
    assert plan["error"] == "PlanNichtVerfuegbar: Status 503"


def test_ohne_plan_fuer_das_fahrzeug_sind_die_planfelder_leer():
    plan = ansicht.fahrzeugplan(standort.Planstand(), "auto-1", {}, False)
    assert all(plan[k] is None for k in (*ansicht.AUS_DEM_FAHRZEUGPLAN, *ansicht.AUS_DEM_KOPF, "error"))
    assert ansicht.fahrzeugplan(_stand(), "auto-2", {}, False)["slots"] is None


def test_die_werte_aus_c6():
    assert [ansicht.c6_wert("charge_now", z, BERLIN) for z in ("on", "off", "unavailable", None)] == [
        True, False, None, None]
    assert ansicht.c6_wert("charge_now_kw", "11.0", BERLIN) == 11.0
    assert ansicht.c6_wert("charge_now_kw", "unknown", BERLIN) is None
    assert ansicht.c6_wert("next_charge_start", "2026-09-16T20:00:00+00:00", BERLIN) == "2026-09-16T22:00:00+02:00"
    assert ansicht.c6_wert("next_charge_start", "unknown", BERLIN) is None


# --- Die Preise -----------------------------------------------------------------------


def test_die_preise_ab_dem_laufenden_slot():
    prognose = {
        "model": "wx", "computed_at": "2026-09-16T09:50:00+00:00",
        "prices_known_until": "2026-09-16T21:45:00+00:00",
        "slots": [{"target_timestamp": f"2026-09-16T09:{m:02d}:00+00:00", "q10": 0.1, "q50": 0.2,
                   "q90": 0.3, "source": "epex"} for m in (30, 45)]
                 + [{"target_timestamp": "2026-09-16T10:00:00+00:00", "q10": 0.1, "q50": 0.2,
                     "q90": 0.3, "source": "forecast"}],
    }
    preise = ansicht.preise(prognose, JETZT + timedelta(minutes=-1))
    assert [slot["t"] for slot in preise["slots"]] == ["2026-09-16T09:45:00+00:00", "2026-09-16T10:00:00+00:00"]
    assert preise["slots"][1] == {"t": "2026-09-16T10:00:00+00:00", "q10": 0.1, "q50": 0.2, "q90": 0.3,
                                  "source": "forecast"}
    assert (preise["model"], preise["prices_known_until"]) == ("wx", "2026-09-16T21:45:00+00:00")


def test_ohne_prognose_keine_preise():
    assert ansicht.preise(None, JETZT) == {"slots": [], "prices_known_until": None, "computed_at": None,
                                           "model": None}
```

- [ ] **Step 2: Rot**

Run: `$HAPY -m pytest -q --rootdir . tests/test_ansicht.py`
Expected: `1 error` beim Sammeln, `No module named 'meteo_volt_c3.ansicht'`

- [ ] **Step 3: Das Modul**

`custom_components/meteo_volt/ansicht.py`:

```python
"""Was das Panel liest, ohne Home Assistant. Spec C3 Abschnitt 6.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Hier entsteht der Inhalt der Websocket-Befehle: die Termine mit
Planwerten und Hinweisen, der Plan eines Fahrzeugs und die Preise.
terminwebsocket.py liest dafuer aus Home Assistant und schickt ab.

Zeitpunkte gehen als ISO 8601 mit Offset hinaus.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 6
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

from . import standort
from .terminanfrage import ZIEL, zerlegen
from .termine import Termin, ueberschneiden, utc

# Die Prognose rechnet in Viertelstunden.
PREISSLOT = timedelta(minutes=15)


# --- Termine, Spec Abschnitt 6 ----------------------------------------------


def planwerte(termin: Termin, stand: standort.Planstand, jetzt: datetime, soc_min: float) -> dict | None:
    """Die Planwerte eines Termins, oder None.

    None hinter horizon_end und ohne brauchbaren Plan (C5-Spec Abschnitt 8,
    abgelesen ueber was_gilt). Laeuft der Termin schon, gibt es keinen Slot
    mit der Abfahrt: die Ladestaende sind dann None, running_until nennt
    die Rueckkehr.
    """
    if standort.was_gilt(stand, termin.fahrzeug, jetzt, None)["quelle"] != standort.QUELLE_PLAN:
        return None
    try:
        plan = stand.plan
        if utc(termin.abfahrt) >= utc(datetime.fromisoformat(plan["horizon_end"])):
            return None
        fahrzeugplan = next(v for v in plan["vehicles"] if v.get("id") == termin.fahrzeug)
        schritt = timedelta(minutes=plan["slot_minutes"])
        slots = fahrzeugplan["slots"]
        index = next(
            (i for i, slot in enumerate(slots)
             if utc(datetime.fromisoformat(slot["t"])) <= utc(termin.abfahrt)
             < utc(datetime.fromisoformat(slot["t"])) + schritt),
            None,
        )
        bei_abfahrt = nach_fahrt = None
        if index is not None:
            nach_fahrt = slots[index]["soc_end_pct"]
            bei_abfahrt = slots[index - 1]["soc_end_pct"] if index > 0 else _ladestand_im_request(stand, termin.fahrzeug)
        fehlend = next(
            (v.get("missing_kwh") for v in fahrzeugplan.get("violations") or []
             if v.get("type") == "target_unreachable"
             and zerlegen(v.get("constraint_id")) == (termin.eintrag, termin.datum, ZIEL)),
            None,
        )
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError):
        return None  # ein Plan ohne die Form des Kontrakts
    laeuft = utc(termin.abfahrt) <= utc(jetzt) < utc(termin.rueckkehr)
    return {
        "soc_at_departure": bei_abfahrt,
        "soc_after_trip": nach_fahrt,
        "target_missing_kwh": fehlend,
        "below_min": nach_fahrt is not None and nach_fahrt < soc_min,
        "running_until": termin.rueckkehr.isoformat() if laeuft else None,
    }


def _ladestand_im_request(stand: standort.Planstand, fahrzeug_id: str) -> float | None:
    """Liegt die Abfahrt im ersten Slot, gilt der Ladestand aus dem Request."""
    for fahrzeug in (stand.anfrage or {}).get("vehicles", []):
        if fahrzeug.get("id") == fahrzeug_id:
            return fahrzeug.get("soc_pct")
    return None


def hinweise(termin: Termin, umfeld: list[Termin], geraete: dict[str, str], personen: set[str]) -> list[dict]:
    """overlap und driver_busy. umfeld sind alle Termine aller Fahrzeuge um diesen herum.

    overlap einmal, driver_busy einmal je anderem Fahrzeug, mit dessen
    Geraete-ID. Ein geloeschter Fahrer zaehlt nicht.
    """
    ergebnis = []
    if any(
        anderer.fahrzeug == termin.fahrzeug
        and (anderer.eintrag, anderer.datum) != (termin.eintrag, termin.datum)
        and ueberschneiden(termin, anderer)
        for anderer in umfeld
    ):
        ergebnis.append({"type": "overlap"})
    if termin.fahrer in personen:
        belegt: list[str] = []
        for anderer in umfeld:
            if (anderer.fahrzeug != termin.fahrzeug and anderer.fahrer == termin.fahrer
                    and anderer.fahrzeug not in belegt and ueberschneiden(termin, anderer)):
                belegt.append(anderer.fahrzeug)
        ergebnis += [{"type": "driver_busy", "vehicle": geraete.get(fahrzeug)} for fahrzeug in belegt]
    return ergebnis


def termine_ansicht(
    auswahl: list[Termin],
    umfeld: list[Termin],
    stand: standort.Planstand,
    jetzt: datetime,
    soc_min: dict[str, float],
    geraete: dict[str, str],
    personen: set[str],
) -> list[dict]:
    """Die Termine fuer meteo_volt/appointments, nach Abfahrt sortiert. Abgesagte fehlen schon."""
    return [
        {
            "entry": termin.eintrag,
            "date": termin.datum.isoformat(),
            "vehicle": geraete.get(termin.fahrzeug),
            "departure": termin.abfahrt.isoformat(),
            "return": termin.rueckkehr.isoformat(),
            "distance_km": termin.strecke_km,
            # Eine geloeschte Person bleibt im Eintrag, gelesen wird ohne Fahrer.
            "driver": termin.fahrer if termin.fahrer in personen else None,
            "soc": termin.ladestand,
            "repeat": termin.wiederholung,
            "changed": termin.geaendert,
            "plan": planwerte(termin, stand, jetzt, soc_min.get(termin.fahrzeug, 0.0)),
            "hints": hinweise(termin, umfeld, geraete, personen),
        }
        for termin in auswahl
    ]


# --- Der Plan eines Fahrzeugs --------------------------------------------------

AUS_DEM_FAHRZEUGPLAN = ("slots", "intervals", "total_kwh", "total_cost_eur", "soc_end_pct", "violations")
AUS_DEM_KOPF = ("horizon_end", "prices_known_until", "computed_at")


def c6_wert(schluessel: str, zustand: str | None, tz: tzinfo) -> bool | float | str | None:
    """Der Zustand einer Entitaet aus C6 als Wert fuer das Panel, None wenn unbekannt."""
    if zustand is None:
        return None
    if schluessel == "charge_now":
        return {"on": True, "off": False}.get(zustand)
    try:
        if schluessel == "charge_now_kw":
            return float(zustand)
        return datetime.fromisoformat(zustand).astimezone(tz).isoformat()
    except ValueError:
        return None  # unknown, unavailable


def fahrzeugplan(stand: standort.Planstand, fahrzeug_id: str, c6: dict, plant: bool) -> dict:
    """meteo_volt/plan: der Fahrzeugplan der letzten Antwort, unveraendert, dazu der Stand.

    charge_now, charge_now_kw und next_charge_start kommen aus den
    Entitaeten von C6, damit Panel und Entitaeten dasselbe sagen, auch bei
    gesperrtem Block.
    """
    plan = stand.plan if isinstance(stand.plan, dict) else {}
    fahrzeuge = plan.get("vehicles") if isinstance(plan.get("vehicles"), list) else []
    eigener = next((v for v in fahrzeuge if isinstance(v, dict) and v.get("id") == fahrzeug_id), {})
    return {
        **{schluessel: eigener.get(schluessel) for schluessel in AUS_DEM_FAHRZEUGPLAN},
        **{schluessel: plan.get(schluessel) for schluessel in AUS_DEM_KOPF},
        "received_at": None if stand.erhalten_um is None else stand.erhalten_um.isoformat(),
        "charge_now": c6.get("charge_now"),
        "charge_now_kw": c6.get("charge_now_kw"),
        "next_charge_start": c6.get("next_charge_start"),
        "planning": plant,
        "error": None if stand.fehler is None else f"{type(stand.fehler).__name__}: {stand.fehler}",
    }


# --- Die Preise -------------------------------------------------------------------


def preise(prognose: dict | None, jetzt: datetime) -> dict:
    """meteo_volt/prices: ab dem laufenden Slot bis zum Ende der Prognose, ohne Netzentgelt.

    Vergangene Preise liefert C3 nicht, entschieden am 2026-09-16.
    """
    prognose = prognose if isinstance(prognose, dict) else {}
    slots = []
    for slot in prognose.get("slots") or []:
        try:
            beginn = datetime.fromisoformat(slot["target_timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if utc(beginn) + PREISSLOT > utc(jetzt):
            slots.append({
                "t": slot["target_timestamp"],
                "q10": slot.get("q10"),
                "q50": slot.get("q50"),
                "q90": slot.get("q90"),
                "source": slot.get("source"),
            })
    return {
        "slots": slots,
        "prices_known_until": prognose.get("prices_known_until"),
        "computed_at": prognose.get("computed_at"),
        "model": prognose.get("model"),
    }
```

- [ ] **Step 4: Grün**

Run: `$HAPY -m pytest -q --rootdir . tests/test_ansicht.py`
Expected: `14 passed`

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `424 passed`

- [ ] **Step 5: Commit**

```bash
git add custom_components/meteo_volt/ansicht.py tests/test_ansicht.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Build what the panel reads: appointments, the vehicle plan, prices

Each appointment carries its state of charge before and after the trip,
missing energy for an unreachable target and hints for overlaps and a
busy driver. The vehicle plan passes the last answer through unchanged
and takes charge now from the entities of C6.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 6: C5 — Quelle für Termine, Signal „plant", drei Auslöser

**Files:**
- Modify: `custom_components/meteo_volt/const.py` (anhängen)
- Modify: `custom_components/meteo_volt/plankoordinator.py`

**Interfaces:**
- Consumes: aus Task 4 `anfrage_bauen(..., termine, risiko)`.
- Produces:
  - `const.SIGNAL_PLANUNG = "meteo_volt_planung_{}"`, `format(entry_id)`, Nutzlast `True` oder `False`.
  - am Koordinator: `termine_quelle: Callable[[Planstand, datetime], tuple[dict[str, dict], int]] | None`, `plant: bool`, `termine_geaendert()`, `risiko_geaendert()`, `async_neu_planen() -> Planstand`.

Kein automatischer Test: der Koordinator braucht Home Assistant. Der Rumpf von `_async_update_data` wandert unverändert nach `_lauf`, damit Beginn und Ende jedes Laufs im `try`/`finally` gemeldet werden, auch wenn er wirft.

- [ ] **Step 1: Das Signal**

```diff
--- a/custom_components/meteo_volt/const.py
+++ b/custom_components/meteo_volt/const.py
@@ -30,2 +30,6 @@ ISSUE_ABWEICHUNG = "ladung_abweichung"
 ISSUE_SCHNELLER = "ladung_schneller"
 ISSUE_LANGSAMER = "ladung_langsamer"
+
+# C3-Spec Abschnitt 7: C5 meldet Beginn und Ende jedes Laufs, je Eintrag. Nutzlast
+# ist True oder False. format(entry_id).
+SIGNAL_PLANUNG = "meteo_volt_planung_{}"
```

- [ ] **Step 2: Der Koordinator**

```diff
--- a/custom_components/meteo_volt/plankoordinator.py
+++ b/custom_components/meteo_volt/plankoordinator.py
@@ -25,4 +25,5 @@ from homeassistant.core import Event, EventStateChangedData, HomeAssistant, call
 from homeassistant.helpers import issue_registry as ir
 from homeassistant.helpers.debounce import Debouncer
+from homeassistant.helpers.dispatcher import async_dispatcher_send
 from homeassistant.helpers.event import (
     async_call_later,
@@ -37,5 +38,5 @@ from homeassistant.util import dt as dt_util
 from . import stammdaten, standort
 from .api import MeteoVoltApiClient
-from .const import DOMAIN, ISSUE_PLAN_VERALTET
+from .const import DOMAIN, ISSUE_PLAN_VERALTET, SIGNAL_PLANUNG
 from .planabruf import PlanFehler
 
@@ -81,4 +82,11 @@ class MeteoVoltPlanKoordinator(DataUpdateCoordinator[standort.Planstand]):
         self._issue_abbrechen: Callable[[], None] | None = None
         self._entitaeten_abbrechen: list[Callable[[], None]] = []
+        # C3-Spec Abschnitt 4: Termin-Fragmente je Fahrzeug und Risiko. C3 setzt
+        # die Quelle, wenn es laeuft; ohne sie geht der Request wie vor C3 raus.
+        self.termine_quelle: (
+            Callable[[standort.Planstand, datetime], tuple[dict[str, dict], int]] | None
+        ) = None
+        # C3-Spec Abschnitt 7: ob gerade ein Lauf rechnet.
+        self.plant = False
 
     # --- Start und Ende ---------------------------------------------------
@@ -191,59 +199,98 @@ class MeteoVoltPlanKoordinator(DataUpdateCoordinator[standort.Planstand]):
         return self.data
 
+    # --- Ausloeser aus C3, C3-Spec Abschnitt 7 ------------------------------
+
+    @callback
+    def termine_geaendert(self) -> None:
+        """Ein Schritt: anlegen, aendern, loeschen, absagen, rueckgaengig. Gebuendelt."""
+        self._ausloesen("termine")
+
+    @callback
+    def risiko_geaendert(self) -> None:
+        self._ausloesen("risiko")
+
+    async def async_neu_planen(self) -> standort.Planstand:
+        """meteo_volt.replan: sofort, ohne Buendelung, wartet einen laufenden Aufruf ab."""
+        self._ausloeser.add("replan")
+        await self.async_refresh()
+        return self.data
+
     # --- Der Lauf ----------------------------------------------------------
 
     async def _async_update_data(self) -> standort.Planstand:
-        """Ein Lauf. Wirft nie fuer einen PlanFehler, der steht im Planstand."""
+        """Ein Lauf. Meldet Beginn und Ende an C3 (C3-Spec Abschnitt 7)."""
         async with self._sperre:
-            kennung = ",".join(sorted(self._ausloeser)) or "grundtakt"
-            # Spec Abschnitt 7: ein Nachholversuch, der selbst scheitert, plant
-            # keinen weiteren.
-            nur_nachholen = self._ausloeser == {"nachholen"}
-            self._ausloeser.clear()
-            # Spec Abschnitt 7: ein Nachholversuch entfaellt, wenn vorher ein
-            # anderer Aufruf kommt.
-            self._nachholen_absagen()
-            if self._takt == standort.STOPP:
-                # Spec Abschnitt 7: nach einem Key-Fehler geht nichts mehr raus,
-                # bis ein neuer Key den Eintrag neu laedt oder HA neu startet.
-                _LOGGER.debug("Plan %s: gestoppt nach einem Key-Fehler, nichts gesendet", kennung)
-                return self.data
-
-            anfrage, ausgelassen = standort.anfrage_bauen(
-                self._subentries_vom_typ(stammdaten.TYP_LADEPUNKT),
-                self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG),
-                self._messungen(),
-                dict(self.config_entry.data),
-                self.hass.config.time_zone,
-            )
-            stand = replace(self.data, anfrage=anfrage, ausgelassen=ausgelassen)
-            if anfrage is None:
-                # Spec Abschnitt 3: kein Request, der gehaltene Plan bleibt.
-                _LOGGER.debug("Plan %s: kein planbares Fahrzeug, nichts gesendet", kennung)
-                return stand
-
-            versuch_um = dt_util.utcnow()
+            self._planung_melden(True)
             try:
-                plan = await self.client.async_create_plan(self.hass, anfrage)
-            except PlanFehler as fehler:
-                stand = replace(stand, fehler=fehler, letzter_versuch_um=versuch_um)
-            else:
-                stand = replace(
-                    stand,
-                    plan=plan,
-                    erhalten_um=dt_util.utcnow(),
-                    fehler=None,
-                    letzter_versuch_um=versuch_um,
-                )
-            # Kennung und Ergebnisklasse, nie Inhalt: im Request stehen
-            # Ladestaende (Basiskontrakt 3.7).
-            _LOGGER.debug(
-                "Plan %s: %s",
-                kennung,
-                "erhalten" if stand.fehler is None else type(stand.fehler).__name__,
-            )
-            self._nach_dem_aufruf(stand, nur_nachholen)
+                return await self._lauf()
+            finally:
+                self._planung_melden(False)
+
+    @callback
+    def _planung_melden(self, plant: bool) -> None:
+        self.plant = plant
+        async_dispatcher_send(self.hass, SIGNAL_PLANUNG.format(self.config_entry.entry_id), plant)
+
+    async def _lauf(self) -> standort.Planstand:
+        """Wirft nie fuer einen PlanFehler, der steht im Planstand."""
+        kennung = ",".join(sorted(self._ausloeser)) or "grundtakt"
+        # Spec Abschnitt 7: ein Nachholversuch, der selbst scheitert, plant
+        # keinen weiteren.
+        nur_nachholen = self._ausloeser == {"nachholen"}
+        self._ausloeser.clear()
+        # Spec Abschnitt 7: ein Nachholversuch entfaellt, wenn vorher ein
+        # anderer Aufruf kommt.
+        self._nachholen_absagen()
+        if self._takt == standort.STOPP:
+            # Spec Abschnitt 7: nach einem Key-Fehler geht nichts mehr raus,
+            # bis ein neuer Key den Eintrag neu laedt oder HA neu startet.
+            _LOGGER.debug("Plan %s: gestoppt nach einem Key-Fehler, nichts gesendet", kennung)
+            return self.data
+
+        # C3-Spec Abschnitt 4: ausgerollt wird ab jetzt. Scheitert das, scheitert
+        # der Lauf laut -- ein Plan ohne die Termine laede in der Abwesenheit.
+        termine, risiko = (
+            (None, None)
+            if self.termine_quelle is None
+            else self.termine_quelle(self.data, dt_util.utcnow())
+        )
+        anfrage, ausgelassen = standort.anfrage_bauen(
+            self._subentries_vom_typ(stammdaten.TYP_LADEPUNKT),
+            self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG),
+            self._messungen(),
+            dict(self.config_entry.data),
+            self.hass.config.time_zone,
+            termine=termine,
+            risiko=risiko,
+        )
+        stand = replace(self.data, anfrage=anfrage, ausgelassen=ausgelassen)
+        if anfrage is None:
+            # Spec Abschnitt 3: kein Request, der gehaltene Plan bleibt.
+            _LOGGER.debug("Plan %s: kein planbares Fahrzeug, nichts gesendet", kennung)
             return stand
 
+        versuch_um = dt_util.utcnow()
+        try:
+            plan = await self.client.async_create_plan(self.hass, anfrage)
+        except PlanFehler as fehler:
+            stand = replace(stand, fehler=fehler, letzter_versuch_um=versuch_um)
+        else:
+            stand = replace(
+                stand,
+                plan=plan,
+                erhalten_um=dt_util.utcnow(),
+                fehler=None,
+                letzter_versuch_um=versuch_um,
+            )
+        # Kennung und Ergebnisklasse, nie Inhalt: im Request stehen
+        # Ladestaende (Basiskontrakt 3.7).
+        _LOGGER.debug(
+            "Plan %s: %s",
+            kennung,
+            "erhalten" if stand.fehler is None else type(stand.fehler).__name__,
+        )
+        self._nach_dem_aufruf(stand, nur_nachholen)
+        return stand
+
     @callback
     def _nach_dem_aufruf(self, stand: standort.Planstand, nur_nachholen: bool) -> None:
```

- [ ] **Step 3: Suite und Commit**

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `424 passed` — `tests/test_overrides.py` parst dabei jede `.py`-Datei der Integration.

```bash
git add custom_components/meteo_volt/const.py custom_components/meteo_volt/plankoordinator.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Let the coordinator plan with appointments and report each run

C3 sets a source for fragments and risk; without it the request stays
as before. A step and a new risk trigger a bundled run, replan an
immediate one that waits for a running call. Begin and end of every
run go out as a signal per entry.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 7: `terminverwaltung.py` — Store, Schritte, Meldungen

**Files:**
- Create: `custom_components/meteo_volt/terminverwaltung.py`

**Interfaces:**
- Consumes: Tasks 1 bis 6; aus C6 nur die zugesagten `unique_id` und Geräte (C6-Spec Abschnitt 9).
- Produces:
  - `VERWALTUNGEN = "meteo_volt_termine"`, `SCHRITTE = "meteo_volt_schritte"`, `SPEICHER_VERSION = 1`, `SIGNAL_PANEL = "meteo_volt_panel_{}"`, die Meldungen `TERMINE`, `STANDORT`, `PLAN`, `PLANUNG`, `PREISE`, `speicher_schluessel(entry_id)`.
  - `Terminverwaltung` mit `async_anlegen`, `async_aendern`, `async_loeschen`, `async_absagen`, `async_rueckgaengig`, `async_risiko_setzen`, `async_neu_planen`, `standort()`, `termine_im_fenster(start, ende, fahrzeug_id)`, `plan(fahrzeug_id)`, `preise()`, `fahrzeugdaten()`, `zeitzone()`, `entry`.
  - `async_termine_starten(hass, entry, koordinator)`, `async_speicher_entfernen(hass, entry_id)`, `nach_geraet`, `nach_eintrag`, `nach_schritt`, `nach_standort`.

Kein automatischer Test; gestartet wird das Modul erst in Task 9. Befunde aus dem Quelltext von Home Assistant 2026.4.1, auf denen der Code steht:

- `Store.async_load()` gibt `None`, solange es keine Datei gibt; `async_save` schreibt sofort, `async_remove` löscht sie.
- `async_dispatcher_send` fängt Ausnahmen seiner Ziele ab (`helpers/dispatcher.py`). Der Rückruf am Koordinator der Prognose sendet nur ein Signal und kann die sechs Sensoren nicht aufhalten.
- `DataUpdateCoordinator.async_update_listeners` ruft jeden Listener ohne `try`. Ein Listener, der wirft, hielte die übrigen auf; deshalb senden die Listener von C3 nur.
- Update-Listener eines Eintrags laufen bei jeder Änderung an Subentries, ohne ihn neu zu laden (C5-Spec Abschnitt 6).

- [ ] **Step 1: Das Modul**

`custom_components/meteo_volt/terminverwaltung.py`:

```python
"""Die Termine in Home Assistant: Store, Schritte, Meldungen an das Panel, neu planen.

Was C3 entscheidet, steht in termine.py, pruefungen.py, terminbuch.py,
terminanfrage.py und ansicht.py und ist dort ohne Home Assistant geprueft.
Hier steht nur die Verdrahtung: der Store je Standort, die Schritte im
Speicher, die Meldungen an das Panel und die Ausloeser an C5. Das sieht kein
automatischer Test, nur die Abnahme.

Geladen wird dieses Modul nur im try (Spec Abschnitt 8): scheitert es,
laufen Prognose, Plan und die Entitaeten aus C6 weiter, und C5 plant ohne
Termine.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 3 bis 8
"""

from __future__ import annotations

import uuid
from collections import deque
from datetime import date, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
    async_track_state_removed_domain,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import ansicht, pruefungen, stammdaten, standort, terminanfrage, terminbuch, termine
from .const import CONF_GRID_FEES, DOMAIN, SIGNAL_PLANUNG
from .plankoordinator import MeteoVoltPlanKoordinator

# hass.data[VERWALTUNGEN][entry_id]. Nicht unter hass.data[DOMAIN]: das lesen
# die sechs Sensoren (Bestandsschutz Auflage 5).
VERWALTUNGEN = f"{DOMAIN}_termine"
# hass.data[SCHRITTE][entry_id]: die Schritte ueberleben das Neuladen eines
# Eintrags, nicht den Neustart (Spec Abschnitt 2.2).
SCHRITTE = f"{DOMAIN}_schritte"

SPEICHER_VERSION = 1

# Meldungen an das Panel, Spec Abschnitt 6. Nutzlast ist der Name, ohne Inhalt.
SIGNAL_PANEL = f"{DOMAIN}_panel_{{}}"
TERMINE = "appointments"
STANDORT = "site"
PLAN = "plan"
PLANUNG = "planning"
PREISE = "prices"

# Die Entitaeten aus C6, aus denen meteo_volt/plan liest (C6-Spec Abschnitt 9).
C6_WERTE = (("binary_sensor", "charge_now"), ("sensor", "charge_now_kw"), ("sensor", "next_charge_start"))


def speicher_schluessel(entry_id: str) -> str:
    """Spec Abschnitt 3: ein Store je Standort."""
    return f"{DOMAIN}.termine.{entry_id}"


def _neue_id() -> str:
    """Ohne '/': die IDs im Request setzen sich daraus zusammen (Spec Abschnitt 4)."""
    return uuid.uuid4().hex


class Terminverwaltung:
    """Die Termine eines Standorts."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, koordinator: MeteoVoltPlanKoordinator
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.koordinator = koordinator
        self.buch = terminbuch.Buch()
        self._store: Store = Store(hass, SPEICHER_VERSION, speicher_schluessel(entry.entry_id))
        self._fahrzeuge: set[str] = set()
        self._soc_entitaeten: set[str] = set()
        self._c6_entitaeten: set[str] = set()
        self._zustaende_abmelden: CALLBACK_TYPE | None = None

    # --- Start ------------------------------------------------------------------

    async def async_starten(self) -> None:
        schritte = self.hass.data.setdefault(SCHRITTE, {}).setdefault(
            self.entry.entry_id, deque(maxlen=terminbuch.MAX_SCHRITTE))
        # Ohne Datei None: wer nie einen Termin anlegt und nie das Risiko setzt,
        # hat keine (Spec Abschnitt 3). Sie entsteht mit dem ersten Schreiben.
        self.buch = terminbuch.Buch(await self._store.async_load(), schritte)
        self._fahrzeuge = set(self.fahrzeugdaten())
        # Verschwand ein Fahrzeug, waehrend C3 nicht lief, gehen seine Termine jetzt.
        if terminbuch.fahrzeuge_bereinigen(self.buch, self._fahrzeuge):
            await self._speichern()

        entry = self.entry
        entry.async_on_unload(entry.add_update_listener(self._eintrag_geaendert))
        entry.async_on_unload(self.koordinator.async_add_listener(self._plan_geaendert))
        entry.async_on_unload(async_dispatcher_connect(
            self.hass, SIGNAL_PLANUNG.format(entry.entry_id), self._planung_geaendert))
        prognose = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if prognose is not None:
            # Der Rueckruf sendet nur ein Signal und kann die sechs Sensoren
            # nicht aufhalten: der Dispatcher faengt, was dahinter scheitert.
            entry.async_on_unload(prognose.async_add_listener(self._preise_geaendert))
        entry.async_on_unload(async_track_state_added_domain(self.hass, "person", self._person_geaendert))
        entry.async_on_unload(async_track_state_removed_domain(self.hass, "person", self._person_geaendert))
        entry.async_on_unload(self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._register_geaendert))
        entry.async_on_unload(self._zustaende_abbestellen)
        self._zustaende_bestellen()
        # Zuletzt: erst ab hier traegt jeder Request die Termine.
        self.koordinator.termine_quelle = self.fragmente

    # --- Aus Home Assistant lesen --------------------------------------------------

    def fahrzeugdaten(self) -> dict[str, dict]:
        """subentry_id -> data, in Anlagereihenfolge."""
        return {
            subentry_id: dict(subentry.data)
            for subentry_id, subentry in self.entry.subentries.items()
            if subentry.subentry_type == stammdaten.TYP_FAHRZEUG
        }

    def _titel(self) -> dict[str, str]:
        return {subentry_id: self.entry.subentries[subentry_id].title for subentry_id in self.fahrzeugdaten()}

    def _soc_min(self) -> dict[str, float]:
        return {fid: float(daten[stammdaten.FELD_SOC_MIN]) for fid, daten in self.fahrzeugdaten().items()}

    def geraete(self) -> dict[str, str]:
        """subentry_id -> Geraete-ID, fuer jedes Fahrzeug mit Geraet aus C6 (C6-Spec Abschnitt 7)."""
        register = dr.async_get(self.hass)
        geraete = {}
        for fahrzeug_id in self.fahrzeugdaten():
            geraet = register.async_get_device(identifiers={(DOMAIN, fahrzeug_id)})
            if geraet is not None:
                geraete[fahrzeug_id] = geraet.id
        return geraete

    def personen(self) -> dict[str, str]:
        return {zustand.entity_id: zustand.name for zustand in self.hass.states.async_all("person")}

    @property
    def risiko(self) -> int:
        return terminanfrage.RISIKO_VORGABE if self.buch.risiko is None else self.buch.risiko

    @staticmethod
    def zeitzone():
        return dt_util.get_default_time_zone()

    # --- Fuer C5, Spec Abschnitt 4 ------------------------------------------------------

    @callback
    def fragmente(self, stand: standort.Planstand, jetzt: datetime) -> tuple[dict[str, dict], int]:
        bis = terminanfrage.ausrollen_bis(stand.plan, jetzt)
        auswahl = termine.ausrollen(list(self.buch.eintraege.values()), self.zeitzone(), jetzt, bis)
        return terminanfrage.fragmente(auswahl, self._soc_min(), jetzt), self.risiko

    # --- Schreiben, Spec Abschnitt 5 --------------------------------------------------------

    async def async_anlegen(self, fahrzeug_id: str, felder: dict) -> dict:
        jetzt = dt_util.utcnow()
        werte = pruefungen.werte_pruefen(felder, fahrzeug_id, jetzt, self.zeitzone())
        schritt, eintraege = terminbuch.anlegen(self.buch, werte, _neue_id)
        await self._nach_schritt()
        return {"step": schritt, "entry": eintraege[0], "warnings": self._warnungen(werte, eintraege[0], jetzt)}

    async def async_aendern(
        self, eintrag_id: str, datum: date, umfang: str | None, fahrzeug_id: str, felder: dict
    ) -> dict:
        eintrag = self.buch.eintraege[eintrag_id]
        if not termine.hat_termin(eintrag, datum):
            raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date")
        jetzt = dt_util.utcnow()
        # Fehlt repeat, bleibt die Wiederholung. once waere hier eine stille Aenderung.
        werte = pruefungen.werte_pruefen(
            felder, fahrzeug_id, jetzt, self.zeitzone(), eintrag[termine.WIEDERHOLUNG])
        schritt, eintraege = terminbuch.aendern(self.buch, eintrag_id, datum, umfang, werte, _neue_id)
        await self._nach_schritt()
        return {"step": schritt, "entries": eintraege, "warnings": self._warnungen(werte, eintraege[0], jetzt)}

    async def async_loeschen(self, eintrag_id: str, datum: date, umfang: str | None) -> dict:
        schritt = terminbuch.loeschen(self.buch, eintrag_id, datum, umfang, _neue_id)
        await self._nach_schritt()
        return {"step": schritt}

    async def async_absagen(self, liste: list[tuple[str, date]], zu_schritt: str | None) -> dict:
        schritt = terminbuch.absagen(self.buch, liste, zu_schritt, _neue_id)
        await self._nach_schritt()
        return {"step": schritt}

    async def async_rueckgaengig(self, schritt: str) -> None:
        terminbuch.rueckgaengig(self.buch, schritt)
        await self._nach_schritt()

    async def async_risiko_setzen(self, risiko: int) -> None:
        """Das Risiko ist kein Schritt (Spec Abschnitt 2.2)."""
        self.buch.risiko = risiko
        await self._speichern()
        self._melden(STANDORT)
        self.koordinator.risiko_geaendert()

    async def async_neu_planen(self) -> None:
        vorher = self.koordinator.data
        nachher = await self.koordinator.async_neu_planen()
        meldung = pruefungen.neu_planen_pruefen(vorher, nachher)
        if meldung is not None:
            raise pruefungen.Terminfehler(meldung)

    async def _nach_schritt(self) -> None:
        await self._speichern()
        self._melden(TERMINE)
        self.koordinator.termine_geaendert()

    async def _speichern(self) -> None:
        """Sofort, nicht verzoegert (Spec Abschnitt 3)."""
        await self._store.async_save(self.buch.speicherform())

    def _warnungen(self, werte: pruefungen.Werte, eintrag_id: str, jetzt: datetime) -> list[dict]:
        meldungen = pruefungen.warnungen(
            werte, eintrag_id, list(self.buch.eintraege.values()), self.zeitzone(), jetzt,
            self._soc_min()[werte.fahrzeug], self.personen(), self._titel(), self.hass.config.language)
        return [meldung.als_dict() for meldung in meldungen]

    # --- Lesen, Spec Abschnitt 6 ----------------------------------------------------------

    def standort(self) -> dict:
        geraete = self.geraete()
        fahrzeuge = []
        for fahrzeug_id, daten in self.fahrzeugdaten().items():
            if fahrzeug_id not in geraete:
                continue  # ohne Geraet aus C6 laesst es sich nicht ansprechen
            zustand = self.hass.states.get(daten.get(stammdaten.FELD_SOC_ENTITAET) or "")
            fahrzeuge.append({
                "vehicle": geraete[fahrzeug_id],
                "title": self.entry.subentries[fahrzeug_id].title,
                "soc_min_pct": float(daten[stammdaten.FELD_SOC_MIN]),
                "soc_max_pct": float(daten[stammdaten.FELD_SOC_MAX]),
                "max_charge_kw": float(daten[stammdaten.FELD_MAX_LADELEISTUNG]),
                "soc_pct": standort.ladestand_lesen(None if zustand is None else zustand.state),
            })
        netzentgelt = self.entry.data.get(CONF_GRID_FEES)
        return {
            "risk": self.risiko,
            # Wie in C5: ein negativer Wert aus einem alten Eintrag zaehlt als keiner.
            "grid_fees": None if netzentgelt is None or float(netzentgelt) < 0 else float(netzentgelt),
            "vehicles": fahrzeuge,
            "persons": [{"entity_id": eid, "name": name} for eid, name in self.personen().items()],
        }

    def termine_im_fenster(self, start: datetime, ende: datetime, fahrzeug_id: str | None) -> list[dict]:
        """Die Termine, deren Rueckkehr nach start und deren Abfahrt vor ende liegt."""
        tz = self.zeitzone()
        eintraege = list(self.buch.eintraege.values())
        auswahl = termine.ausrollen(eintraege, tz, start, ende, fahrzeug_id)
        umfeld: list[termine.Termin] = []
        if auswahl:
            # Die Hinweise brauchen alle Termine aller Fahrzeuge, die einen der
            # gewaehlten ueberschneiden koennten, auch ausserhalb des Fensters.
            von = min((t.abfahrt for t in auswahl), key=termine.utc)
            bis = max((t.rueckkehr for t in auswahl), key=termine.utc)
            umfeld = termine.ausrollen(eintraege, tz, von, bis)
        return ansicht.termine_ansicht(
            auswahl, umfeld, self.koordinator.data, dt_util.utcnow(), self._soc_min(), self.geraete(),
            set(self.personen()))

    def plan(self, fahrzeug_id: str) -> dict:
        register = er.async_get(self.hass)
        werte = {}
        for plattform, schluessel in C6_WERTE:
            entity_id = register.async_get_entity_id(plattform, DOMAIN, f"{DOMAIN}_{fahrzeug_id}_{schluessel}")
            zustand = self.hass.states.get(entity_id) if entity_id else None
            werte[schluessel] = ansicht.c6_wert(schluessel, None if zustand is None else zustand.state, self.zeitzone())
        return ansicht.fahrzeugplan(self.koordinator.data, fahrzeug_id, werte, self.koordinator.plant)

    def preise(self) -> dict:
        prognose = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        return ansicht.preise(None if prognose is None else prognose.data, dt_util.utcnow())

    # --- Meldungen an das Panel, Spec Abschnitt 6 --------------------------------------

    @callback
    def _melden(self, meldung: str) -> None:
        async_dispatcher_send(self.hass, SIGNAL_PANEL.format(self.entry.entry_id), meldung)

    async def _eintrag_geaendert(self, _hass: HomeAssistant, _entry: ConfigEntry) -> None:
        """Spec Abschnitt 7: ein geloeschtes Fahrzeug nimmt seine Termine mit."""
        fahrzeuge = set(self.fahrzeugdaten())
        if fahrzeuge != self._fahrzeuge:
            self._fahrzeuge = fahrzeuge
            if terminbuch.fahrzeuge_bereinigen(self.buch, fahrzeuge):
                await self._speichern()
                self._melden(TERMINE)
        self._zustaende_bestellen()
        self._melden(STANDORT)

    @callback
    def _plan_geaendert(self) -> None:
        self._melden(PLAN)

    @callback
    def _planung_geaendert(self, _plant: bool) -> None:
        self._melden(PLANUNG)

    @callback
    def _preise_geaendert(self) -> None:
        self._melden(PREISE)

    @callback
    def _person_geaendert(self, _event: Event) -> None:
        self._melden(STANDORT)

    @callback
    def _register_geaendert(self, event: Event) -> None:
        """Legt C6 die Entitaeten eines Fahrzeugs an, werden sie ab jetzt beobachtet."""
        if event.data.get("action") in ("create", "remove", "update"):
            self._zustaende_bestellen()

    @callback
    def _zustaende_bestellen(self) -> None:
        """Ladestand-Entitaeten melden site, die drei Entitaeten aus C6 melden plan."""
        self._zustaende_abbestellen()
        register = er.async_get(self.hass)
        fahrzeuge = self.fahrzeugdaten()
        self._soc_entitaeten = {
            daten[stammdaten.FELD_SOC_ENTITAET] for daten in fahrzeuge.values()
            if daten.get(stammdaten.FELD_SOC_ENTITAET)
        }
        self._c6_entitaeten = set()
        for fahrzeug_id in fahrzeuge:
            for plattform, schluessel in C6_WERTE:
                entity_id = register.async_get_entity_id(plattform, DOMAIN, f"{DOMAIN}_{fahrzeug_id}_{schluessel}")
                if entity_id:
                    self._c6_entitaeten.add(entity_id)
        alle = sorted(self._soc_entitaeten | self._c6_entitaeten)
        if alle:
            self._zustaende_abmelden = async_track_state_change_event(self.hass, alle, self._zustand_geaendert)

    @callback
    def _zustaende_abbestellen(self) -> None:
        if self._zustaende_abmelden is not None:
            self._zustaende_abmelden()
            self._zustaende_abmelden = None

    @callback
    def _zustand_geaendert(self, event: Event[EventStateChangedData]) -> None:
        if event.data["entity_id"] in self._soc_entitaeten:
            self._melden(STANDORT)
        if event.data["entity_id"] in self._c6_entitaeten:
            self._melden(PLAN)


# --- Start, Standorte, Ende ----------------------------------------------------------------


async def async_termine_starten(
    hass: HomeAssistant, entry: ConfigEntry, koordinator: MeteoVoltPlanKoordinator
) -> None:
    verwaltung = Terminverwaltung(hass, entry, koordinator)
    await verwaltung.async_starten()
    hass.data.setdefault(VERWALTUNGEN, {})[entry.entry_id] = verwaltung

    def vergessen() -> None:
        # Ohne Rueckgabewert: aus jedem ausser None macht Home Assistant einen
        # Task, und das Entladen scheiterte (C6-Spec Abschnitt 8).
        hass.data[VERWALTUNGEN].pop(entry.entry_id, None)
        koordinator.termine_quelle = None

    entry.async_on_unload(vergessen)


async def async_speicher_entfernen(hass: HomeAssistant, entry_id: str) -> None:
    """Spec Abschnitt 3: entfernt der Nutzer die Integration, geht der Store mit."""
    await Store(hass, SPEICHER_VERSION, speicher_schluessel(entry_id)).async_remove()
    hass.data.get(SCHRITTE, {}).pop(entry_id, None)


def verwaltungen(hass: HomeAssistant) -> dict[str, Terminverwaltung]:
    return hass.data.get(VERWALTUNGEN, {})


def nach_geraet(hass: HomeAssistant, geraet_id: str | None) -> tuple[Terminverwaltung, str]:
    """Standort und subentry_id zur Geraete-ID eines Fahrzeugs, sonst fahrzeug_unbekannt."""
    geraet = dr.async_get(hass).async_get(geraet_id) if geraet_id else None
    alle = verwaltungen(hass)
    entry_id, fahrzeug_id = pruefungen.fahrzeug_aus_geraet(
        set() if geraet is None else set(geraet.identifiers), DOMAIN,
        {eid: set(verwaltung.fahrzeugdaten()) for eid, verwaltung in alle.items()})
    return alle[entry_id], fahrzeug_id


def nach_eintrag(hass: HomeAssistant, eintrag_id: str | None) -> Terminverwaltung:
    for verwaltung in verwaltungen(hass).values():
        if eintrag_id in verwaltung.buch.eintraege:
            return verwaltung
    raise pruefungen.fehler(pruefungen.EINTRAG_UNBEKANNT, "entry")


def nach_schritt(hass: HomeAssistant, schritt: str | None) -> Terminverwaltung:
    for verwaltung in verwaltungen(hass).values():
        if terminbuch.schritt_bekannt(verwaltung.buch, schritt or ""):
            return verwaltung
    raise pruefungen.fehler(pruefungen.RUECKGAENGIG_UNMOEGLICH, "step")


def nach_standort(hass: HomeAssistant, entry_id: str | None) -> Terminverwaltung | None:
    """Ohne config_entry der zuerst geladene Standort, wie bei der Dev-Action."""
    alle = verwaltungen(hass)
    if entry_id is None:
        return next(iter(alle.values()), None)
    return alle.get(entry_id)
```

- [ ] **Step 2: Suite und Commit**

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `424 passed`

```bash
git add custom_components/meteo_volt/terminverwaltung.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Keep appointments per site and tell the panel what changed

One store per site, written at once and created with the first write.
Steps stay in memory and survive a reload of the entry. A deleted
vehicle takes its appointments along.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Die Actions — `aktionen.py`, `services.yaml`, Übersetzungen

**Files:**
- Create: `custom_components/meteo_volt/aktionen.py`
- Modify: `custom_components/meteo_volt/services.yaml`
- Modify: `custom_components/meteo_volt/translations/de.json`, `en.json`
- Test: `tests/test_uebersetzungen.py` (anhängen)

**Interfaces:**
- Consumes: aus Task 2 `AKTIONEN`, `MELDUNGEN`, `Terminfehler`, `fehler`; aus Task 7 `nach_geraet`, `nach_eintrag`, `nach_schritt`, `nach_standort`, `Terminverwaltung`.
- Produces: `async_aktionen_registrieren(hass)` — die sieben Actions aus Spec Abschnitt 5 unter `meteo_volt`, einmal je Home-Assistant-Lauf.

- [ ] **Step 1: Den Test schreiben**

An `tests/test_uebersetzungen.py` anhängen:

```diff
--- a/tests/test_uebersetzungen.py
+++ b/tests/test_uebersetzungen.py
@@ -232,2 +232,66 @@ def test_das_abweichungs_issue_ist_beschriftet(sprache, schluessel):
     for platzhalter in ("{gemessen}", "{geplant}", "{abweichung}"):
         assert platzhalter in issue.get("description", ""), f"{sprache}/{schluessel}: {platzhalter}"
+
+
+# --- Die Actions und Meldungen aus C3 ------------------------------------------
+# pruefungen.py ist die Quelle: welche Actions es gibt, welche Felder sie
+# nehmen und welche Meldungen mit welchen Platzhaltern.
+
+_PAKET_C3 = "meteo_volt_c3"
+if _PAKET_C3 not in sys.modules:
+    _paket_c3 = types.ModuleType(_PAKET_C3)
+    _paket_c3.__path__ = [str(INTEGRATION)]
+    sys.modules[_PAKET_C3] = _paket_c3
+pruefungen = importlib.import_module(f"{_PAKET_C3}.pruefungen")
+
+
+def _services_yaml() -> dict[str, list[str]]:
+    """Action -> Felder aus services.yaml, ohne YAML-Parser.
+
+    Eine Action steht ohne Einrueckung, ihre Felder mit vier Leerzeichen unter
+    'fields:'. PyYAML steckt nicht in den Testabhaengigkeiten.
+    """
+    aktionen: dict[str, list[str]] = {}
+    aktuell = None
+    for zeile in (INTEGRATION / "services.yaml").read_text(encoding="utf-8").splitlines():
+        if zeile and not zeile.startswith((" ", "#")) and zeile.endswith(":"):
+            aktuell = zeile[:-1]
+            aktionen[aktuell] = []
+        elif aktuell and zeile.startswith("    ") and not zeile.startswith("     ") and zeile.endswith(":"):
+            aktionen[aktuell].append(zeile.strip()[:-1])
+    return aktionen
+
+
+def test_services_yaml_nennt_jede_action_mit_ihren_feldern():
+    yaml = _services_yaml()
+    for aktion, felder in pruefungen.AKTIONEN.items():
+        assert yaml.get(aktion) == list(felder), aktion
+
+
+@pytest.mark.parametrize("sprache", SPRACHEN)
+@pytest.mark.parametrize("aktion", sorted(pruefungen.AKTIONEN))
+def test_jede_action_ist_mit_ihren_feldern_beschriftet(sprache, aktion):
+    """Spec C3 Abschnitt 10. Ohne Namen zeigte Home Assistant den rohen Schluessel."""
+    dienst = _laden(sprache).get("services", {}).get(aktion, {})
+    assert dienst.get("name") and dienst.get("description"), f"{sprache}/{aktion}"
+    felder = dienst.get("fields", {})
+    assert set(felder) == set(pruefungen.AKTIONEN[aktion]), f"{sprache}/{aktion}"
+    assert all(feld.get("name") for feld in felder.values()), f"{sprache}/{aktion}"
+
+
+@pytest.mark.parametrize("sprache", SPRACHEN)
+def test_keine_uebersetzung_ohne_action(sprache):
+    """Die Dev-Action traegt ihren Text in services.yaml und steht hier nicht."""
+    assert set(_laden(sprache).get("services", {})) == set(pruefungen.AKTIONEN)
+
+
+@pytest.mark.parametrize("sprache", SPRACHEN)
+def test_jede_meldung_hat_einen_text_mit_ihren_platzhaltern(sprache):
+    """Spec C3 Abschnitt 2.3: ServiceValidationError sucht exceptions.<schluessel>.message."""
+    meldungen = _laden(sprache).get("exceptions", {})
+    assert set(meldungen) == set(pruefungen.MELDUNGEN), sprache
+    for schluessel, platzhalter in pruefungen.MELDUNGEN.items():
+        text = meldungen[schluessel].get("message", "")
+        assert text, f"{sprache}/{schluessel}"
+        for name in platzhalter:
+            assert f"{{{name}}}" in text, f"{sprache}/{schluessel}: {{{name}}}"
```

- [ ] **Step 2: Rot**

Run: `$HAPY -m pytest -q --rootdir . tests/test_uebersetzungen.py`
Expected: `19 failed, 44 passed` — `services.yaml` kennt die Actions nicht, beide Sprachen haben weder `services` noch `exceptions`.

- [ ] **Step 3: `services.yaml`**

```diff
--- a/custom_components/meteo_volt/services.yaml
+++ b/custom_components/meteo_volt/services.yaml
@@ -1,5 +1,134 @@
+# Die Actions der Termine, C3-Spec Abschnitt 5. Namen und Beschreibungen
+# stehen in den Uebersetzungen; die Felder hier muessen zu pruefungen.AKTIONEN
+# passen, das prueft tests/test_uebersetzungen.py. Jedes Feld ist optional,
+# geprueft wird im Backend.
+create_appointment:
+  fields:
+    vehicle:
+      selector:
+        device:
+          integration: meteo_volt
+    departure:
+      selector:
+        datetime:
+    return:
+      selector:
+        datetime:
+    repeat:
+      selector:
+        select:
+          options: [once, daily, weekdays, weekly, monthly, yearly]
+    distance_km:
+      selector:
+        number:
+          min: 0
+          max: 10000
+          unit_of_measurement: km
+          mode: box
+    driver:
+      selector:
+        entity:
+          domain: person
+    soc:
+      selector:
+        number:
+          min: 0
+          max: 100
+          unit_of_measurement: "%"
+          mode: box
+
+update_appointment:
+  fields:
+    entry:
+      selector:
+        text:
+    date:
+      selector:
+        date:
+    scope:
+      selector:
+        select:
+          options: [this, following, all]
+    vehicle:
+      selector:
+        device:
+          integration: meteo_volt
+    departure:
+      selector:
+        datetime:
+    return:
+      selector:
+        datetime:
+    repeat:
+      selector:
+        select:
+          options: [once, daily, weekdays, weekly, monthly, yearly]
+    distance_km:
+      selector:
+        number:
+          min: 0
+          max: 10000
+          unit_of_measurement: km
+          mode: box
+    driver:
+      selector:
+        entity:
+          domain: person
+    soc:
+      selector:
+        number:
+          min: 0
+          max: 100
+          unit_of_measurement: "%"
+          mode: box
+
+delete_appointment:
+  fields:
+    entry:
+      selector:
+        text:
+    date:
+      selector:
+        date:
+    scope:
+      selector:
+        select:
+          options: [this, following, all]
+
+cancel_appointments:
+  fields:
+    appointments:
+      selector:
+        object:
+    step:
+      selector:
+        text:
+
+undo:
+  fields:
+    step:
+      selector:
+        text:
+
+set_risk:
+  fields:
+    risk:
+      required: true
+      selector:
+        select:
+          options: ["1", "2", "3"]
+    config_entry:
+      selector:
+        config_entry:
+          integration: meteo_volt
+
+replan:
+  fields:
+    config_entry:
+      selector:
+        config_entry:
+          integration: meteo_volt
+
 # Temporaer. Gehoert zur Dev-Action in dev.py und geht mit ihr.
-# Ohne diese Datei warnt Home Assistant bei jedem Laden der
-# Action-Beschreibungen: "Unable to find services.yaml".
 dev_plan:
   name: Dev-Plan
```

- [ ] **Step 4: Die Übersetzungen**

Die Meldungen stehen wörtlich in Spec Abschnitt 2.3. Die Dateien bleiben `json.dumps(..., indent=2, ensure_ascii=False)` mit Zeilenumbruch am Ende.

```diff
--- a/custom_components/meteo_volt/translations/de.json
+++ b/custom_components/meteo_volt/translations/de.json
@@ -202,4 +202,191 @@
       "description": "Gemessen {gemessen} %/h, geplant {geplant} %/h, also {abweichung} % langsamer. Wahrscheinlich ist der Wirkungsgrad zu hoch, die Kapazität zu klein oder die Ladeleistung zu groß eingetragen. Es kann auch sein, dass die Wallbox weniger liefert, die Automation verspätet schaltet oder das Fahrzeug selbst begrenzt."
     }
+  },
+  "services": {
+    "create_appointment": {
+      "name": "Termin anlegen",
+      "description": "Das Fahrzeug ist von der Abfahrt bis zur Rückkehr weg.",
+      "fields": {
+        "vehicle": {
+          "name": "Fahrzeug"
+        },
+        "departure": {
+          "name": "Abfahrt"
+        },
+        "return": {
+          "name": "Rückkehr"
+        },
+        "repeat": {
+          "name": "Wiederholung",
+          "description": "once, daily, weekdays, weekly, monthly oder yearly. Fehlt sie, beim Anlegen once, beim Ändern wie bisher."
+        },
+        "distance_km": {
+          "name": "Strecke (km)"
+        },
+        "driver": {
+          "name": "Fahrer",
+          "description": "Nur zur Anzeige."
+        },
+        "soc": {
+          "name": "Ladestand bei Abfahrt (%)",
+          "description": "Ab dem Min-SoC plant Meteo-Volt ihn als Ziel."
+        }
+      }
+    },
+    "update_appointment": {
+      "name": "Termin ändern",
+      "description": "Bei einer Serie im gewählten Umfang.",
+      "fields": {
+        "entry": {
+          "name": "Eintrag"
+        },
+        "date": {
+          "name": "Datum",
+          "description": "Das Datum der ursprünglichen Abfahrt."
+        },
+        "scope": {
+          "name": "Umfang",
+          "description": "this, following oder all. Fehlt er, this."
+        },
+        "vehicle": {
+          "name": "Fahrzeug"
+        },
+        "departure": {
+          "name": "Abfahrt"
+        },
+        "return": {
+          "name": "Rückkehr"
+        },
+        "repeat": {
+          "name": "Wiederholung",
+          "description": "once, daily, weekdays, weekly, monthly oder yearly. Fehlt sie, beim Anlegen once, beim Ändern wie bisher."
+        },
+        "distance_km": {
+          "name": "Strecke (km)"
+        },
+        "driver": {
+          "name": "Fahrer",
+          "description": "Nur zur Anzeige."
+        },
+        "soc": {
+          "name": "Ladestand bei Abfahrt (%)",
+          "description": "Ab dem Min-SoC plant Meteo-Volt ihn als Ziel."
+        }
+      }
+    },
+    "delete_appointment": {
+      "name": "Termin löschen",
+      "description": "Bei einer Serie im gewählten Umfang.",
+      "fields": {
+        "entry": {
+          "name": "Eintrag"
+        },
+        "date": {
+          "name": "Datum",
+          "description": "Das Datum der ursprünglichen Abfahrt."
+        },
+        "scope": {
+          "name": "Umfang",
+          "description": "this, following oder all. Fehlt er, this."
+        }
+      }
+    },
+    "cancel_appointments": {
+      "name": "Termine absagen",
+      "description": "Bei einer Serie nur diesen Termin, ein einmaliger wird gelöscht.",
+      "fields": {
+        "appointments": {
+          "name": "Termine",
+          "description": "Eine Liste aus entry und date."
+        },
+        "step": {
+          "name": "Schritt",
+          "description": "Optional der Schritt des Speicherns davor. Rückgängig nimmt dann beides zurück."
+        }
+      }
+    },
+    "undo": {
+      "name": "Rückgängig",
+      "description": "Nimmt einen Schritt zurück, solange seine Termine seitdem nicht geändert wurden.",
+      "fields": {
+        "step": {
+          "name": "Schritt"
+        }
+      }
+    },
+    "set_risk": {
+      "name": "Risiko setzen",
+      "description": "Gilt für alle Fahrzeuge.",
+      "fields": {
+        "risk": {
+          "name": "Risiko",
+          "description": "1 Sparsam, 2 Ausgewogen, 3 Sicher."
+        },
+        "config_entry": {
+          "name": "Standort",
+          "description": "Nur bei mehreren Standorten nötig."
+        }
+      }
+    },
+    "replan": {
+      "name": "Neu planen",
+      "description": "Plant sofort neu.",
+      "fields": {
+        "config_entry": {
+          "name": "Standort",
+          "description": "Nur bei mehreren Standorten nötig."
+        }
+      }
+    }
+  },
+  "exceptions": {
+    "zeit_fehlt": {
+      "message": "Abfahrt und Rückkehr brauchen Datum und Uhrzeit."
+    },
+    "rueckkehr_vor_abfahrt": {
+      "message": "Die Rückkehr muss nach der Abfahrt liegen."
+    },
+    "rueckkehr_vorbei": {
+      "message": "Die Rückkehr liegt in der Vergangenheit."
+    },
+    "dauer_zu_lang": {
+      "message": "Der Termin dauert länger, als bis er sich wiederholt."
+    },
+    "strecke_fehlt": {
+      "message": "Strecke fehlt."
+    },
+    "strecke_negativ": {
+      "message": "Die Strecke kann nicht negativ sein."
+    },
+    "ladestand_bereich": {
+      "message": "Der Ladestand liegt zwischen 0 und 100 %."
+    },
+    "ladestand_unter_min": {
+      "message": "Liegt unter dem Min-SoC von {min} % und wird ignoriert."
+    },
+    "fahrer_doppelt": {
+      "message": "{fahrer} ist {datum} zur selben Zeit mit {fahrzeug} unterwegs."
+    },
+    "fahrzeug_unbekannt": {
+      "message": "Das ist kein Fahrzeug von Meteo-Volt."
+    },
+    "eintrag_unbekannt": {
+      "message": "Diesen Termin gibt es nicht mehr."
+    },
+    "termin_unbekannt": {
+      "message": "An diesem Datum gibt es den Termin nicht."
+    },
+    "umfang_unzulaessig": {
+      "message": "Eine geänderte Wiederholung gilt nicht nur für diesen Termin."
+    },
+    "rueckgaengig_unmoeglich": {
+      "message": "Das lässt sich nicht mehr rückgängig machen."
+    },
+    "plan_pause": {
+      "message": "Neu planen geht erst in {sekunden} s wieder."
+    },
+    "plan_gestoppt": {
+      "message": "Der API-Key wurde abgelehnt. Neu planen geht erst nach einem neuen Key oder einem Neustart."
+    }
   }
 }
```

```diff
--- a/custom_components/meteo_volt/translations/en.json
+++ b/custom_components/meteo_volt/translations/en.json
@@ -202,4 +202,191 @@
       "description": "Measured {gemessen} %/h, planned {geplant} %/h, {abweichung} % slower. The charging efficiency is probably set too high, the capacity too low or the charging power too high. The wallbox may also deliver less, the automation may switch late, or the vehicle may limit charging itself."
     }
+  },
+  "services": {
+    "create_appointment": {
+      "name": "Create appointment",
+      "description": "The vehicle is away from departure to return.",
+      "fields": {
+        "vehicle": {
+          "name": "Vehicle"
+        },
+        "departure": {
+          "name": "Departure"
+        },
+        "return": {
+          "name": "Return"
+        },
+        "repeat": {
+          "name": "Repeat",
+          "description": "once, daily, weekdays, weekly, monthly or yearly. If missing, once when creating, unchanged when updating."
+        },
+        "distance_km": {
+          "name": "Distance (km)"
+        },
+        "driver": {
+          "name": "Driver",
+          "description": "For display only."
+        },
+        "soc": {
+          "name": "State of charge at departure (%)",
+          "description": "From the minimum state of charge on, Meteo-Volt plans it as a target."
+        }
+      }
+    },
+    "update_appointment": {
+      "name": "Update appointment",
+      "description": "For a series in the chosen scope.",
+      "fields": {
+        "entry": {
+          "name": "Entry"
+        },
+        "date": {
+          "name": "Date",
+          "description": "The date of the original departure."
+        },
+        "scope": {
+          "name": "Scope",
+          "description": "this, following or all. If missing, this."
+        },
+        "vehicle": {
+          "name": "Vehicle"
+        },
+        "departure": {
+          "name": "Departure"
+        },
+        "return": {
+          "name": "Return"
+        },
+        "repeat": {
+          "name": "Repeat",
+          "description": "once, daily, weekdays, weekly, monthly or yearly. If missing, once when creating, unchanged when updating."
+        },
+        "distance_km": {
+          "name": "Distance (km)"
+        },
+        "driver": {
+          "name": "Driver",
+          "description": "For display only."
+        },
+        "soc": {
+          "name": "State of charge at departure (%)",
+          "description": "From the minimum state of charge on, Meteo-Volt plans it as a target."
+        }
+      }
+    },
+    "delete_appointment": {
+      "name": "Delete appointment",
+      "description": "For a series in the chosen scope.",
+      "fields": {
+        "entry": {
+          "name": "Entry"
+        },
+        "date": {
+          "name": "Date",
+          "description": "The date of the original departure."
+        },
+        "scope": {
+          "name": "Scope",
+          "description": "this, following or all. If missing, this."
+        }
+      }
+    },
+    "cancel_appointments": {
+      "name": "Cancel appointments",
+      "description": "In a series only this appointment, a single one is deleted.",
+      "fields": {
+        "appointments": {
+          "name": "Appointments",
+          "description": "A list of entry and date."
+        },
+        "step": {
+          "name": "Step",
+          "description": "Optionally the step of the save before. Undo then reverts both."
+        }
+      }
+    },
+    "undo": {
+      "name": "Undo",
+      "description": "Reverts a step as long as its appointments have not changed since.",
+      "fields": {
+        "step": {
+          "name": "Step"
+        }
+      }
+    },
+    "set_risk": {
+      "name": "Set risk",
+      "description": "Applies to all vehicles.",
+      "fields": {
+        "risk": {
+          "name": "Risk",
+          "description": "1 economical, 2 balanced, 3 safe."
+        },
+        "config_entry": {
+          "name": "Site",
+          "description": "Only needed with several sites."
+        }
+      }
+    },
+    "replan": {
+      "name": "Replan",
+      "description": "Plans again right away.",
+      "fields": {
+        "config_entry": {
+          "name": "Site",
+          "description": "Only needed with several sites."
+        }
+      }
+    }
+  },
+  "exceptions": {
+    "zeit_fehlt": {
+      "message": "Departure and return need a date and a time."
+    },
+    "rueckkehr_vor_abfahrt": {
+      "message": "The return must be after the departure."
+    },
+    "rueckkehr_vorbei": {
+      "message": "The return is in the past."
+    },
+    "dauer_zu_lang": {
+      "message": "The trip lasts longer than the time until it repeats."
+    },
+    "strecke_fehlt": {
+      "message": "Distance missing."
+    },
+    "strecke_negativ": {
+      "message": "The distance cannot be negative."
+    },
+    "ladestand_bereich": {
+      "message": "The state of charge is between 0 and 100 %."
+    },
+    "ladestand_unter_min": {
+      "message": "Below the minimum state of charge of {min} % and ignored."
+    },
+    "fahrer_doppelt": {
+      "message": "{fahrer} is on the road with {fahrzeug} at the same time on {datum}."
+    },
+    "fahrzeug_unbekannt": {
+      "message": "This is not a Meteo-Volt vehicle."
+    },
+    "eintrag_unbekannt": {
+      "message": "This trip no longer exists."
+    },
+    "termin_unbekannt": {
+      "message": "There is no such trip on this date."
+    },
+    "umfang_unzulaessig": {
+      "message": "A changed repeat cannot apply to this trip only."
+    },
+    "rueckgaengig_unmoeglich": {
+      "message": "This can no longer be undone."
+    },
+    "plan_pause": {
+      "message": "Replanning is possible again in {sekunden} s."
+    },
+    "plan_gestoppt": {
+      "message": "The API key was rejected. Replanning works again after a new key or a restart."
+    }
   }
 }
```

- [ ] **Step 5: Das Modul**

`custom_components/meteo_volt/aktionen.py`:

```python
"""Die Actions der Termine in Home Assistant. Spec C3 Abschnitt 5.

Registriert einmal je Home-Assistant-Lauf unter meteo_volt. Jeder Nutzer
darf sie aufrufen, auch ohne Admin-Rechte. Die Felder stehen in
pruefungen.AKTIONEN und sind im Schema optional; geprueft wird in
pruefungen.py und terminbuch.py, damit jede Meldung aus Spec Abschnitt 2.3
uebersetzt ankommt: als ServiceValidationError mit dem Schluessel als
translation_key. Warnungen stehen in der Antwort.

Geladen wird dieses Modul nur im try (Spec Abschnitt 8). Das Verhalten
sieht kein automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 5
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from . import pruefungen, terminbuch, termine
from .const import DOMAIN
from .terminverwaltung import Terminverwaltung, nach_eintrag, nach_geraet, nach_schritt, nach_standort

_TEXT = vol.Any(None, cv.string)
_ZAHL = vol.Any(None, vol.Coerce(float))

# Die Pruefung der Form. Was Spec Abschnitt 2.3 meldet, prueft das Backend.
_FELDER = {
    "vehicle": _TEXT,
    "departure": _TEXT,
    "return": _TEXT,
    "repeat": vol.Any(None, vol.In(termine.WIEDERHOLUNGEN)),
    "distance_km": _ZAHL,
    "driver": _TEXT,
    "soc": _ZAHL,
    "entry": _TEXT,
    "date": _TEXT,
    "scope": vol.Any(None, vol.In(terminbuch.UMFAENGE)),
    "appointments": vol.Any(None, [{vol.Optional("entry"): _TEXT, vol.Optional("date"): _TEXT}]),
    "step": _TEXT,
    # Fuer das Risiko gibt es keinen Schluessel in 2.3: die Form prueft es ganz.
    "risk": vol.All(vol.Coerce(int), vol.In([1, 2, 3])),
    "config_entry": _TEXT,
}
_PFLICHT = {"risk"}


def _schema(aktion: str) -> vol.Schema:
    return vol.Schema({
        (vol.Required if feld in _PFLICHT else vol.Optional)(feld): _FELDER[feld]
        for feld in pruefungen.AKTIONEN[aktion]
    })


def _datum(text: str | None) -> date:
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date") from None


def _standort(hass: HomeAssistant, entry_id: str | None) -> Terminverwaltung:
    verwaltung = nach_standort(hass, entry_id)
    if verwaltung is None:
        raise HomeAssistantError("Kein Meteo-Volt-Standort mit Terminen geladen")
    return verwaltung


# --- Die sieben Actions --------------------------------------------------------


async def _anlegen(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    verwaltung, fahrzeug_id = nach_geraet(hass, call.data.get("vehicle"))
    return await verwaltung.async_anlegen(fahrzeug_id, dict(call.data))


async def _aendern(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    # Die Reihenfolge der Meldungen: Eintrag, Datum, Fahrzeug, Felder, Umfang.
    verwaltung = nach_eintrag(hass, call.data.get("entry"))
    datum = _datum(call.data.get("date"))
    if not termine.hat_termin(verwaltung.buch.eintraege[call.data["entry"]], datum):
        raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date")
    anderer, fahrzeug_id = nach_geraet(hass, call.data.get("vehicle"))
    if anderer is not verwaltung:
        raise pruefungen.fehler(pruefungen.FAHRZEUG_UNBEKANNT, "vehicle")
    return await verwaltung.async_aendern(
        call.data["entry"], datum, call.data.get("scope"), fahrzeug_id, dict(call.data))


async def _loeschen(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    verwaltung = nach_eintrag(hass, call.data.get("entry"))
    return await verwaltung.async_loeschen(
        call.data["entry"], _datum(call.data.get("date")), call.data.get("scope"))


async def _absagen(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    angaben = call.data.get("appointments") or []
    if not angaben:
        raise pruefungen.fehler(pruefungen.EINTRAG_UNBEKANNT, "entry")
    verwaltung = nach_eintrag(hass, angaben[0].get("entry"))
    liste = [(termin.get("entry"), _datum(termin.get("date"))) for termin in angaben]
    return await verwaltung.async_absagen(liste, call.data.get("step"))


async def _rueckgaengig(hass: HomeAssistant, call: ServiceCall) -> None:
    schritt = call.data.get("step")
    await nach_schritt(hass, schritt).async_rueckgaengig(schritt)


async def _risiko(hass: HomeAssistant, call: ServiceCall) -> None:
    await _standort(hass, call.data.get("config_entry")).async_risiko_setzen(call.data["risk"])


async def _neu_planen(hass: HomeAssistant, call: ServiceCall) -> None:
    await _standort(hass, call.data.get("config_entry")).async_neu_planen()


_AKTIONEN: dict[str, tuple[Callable[[HomeAssistant, ServiceCall], Awaitable], SupportsResponse]] = {
    "create_appointment": (_anlegen, SupportsResponse.OPTIONAL),
    "update_appointment": (_aendern, SupportsResponse.OPTIONAL),
    "delete_appointment": (_loeschen, SupportsResponse.OPTIONAL),
    "cancel_appointments": (_absagen, SupportsResponse.OPTIONAL),
    "undo": (_rueckgaengig, SupportsResponse.NONE),
    "set_risk": (_risiko, SupportsResponse.NONE),
    "replan": (_neu_planen, SupportsResponse.NONE),
}


def _uebersetzt(
    hass: HomeAssistant, ablauf: Callable[[HomeAssistant, ServiceCall], Awaitable]
) -> Callable[[ServiceCall], Awaitable]:
    """Aus einem Terminfehler wird ein ServiceValidationError mit dem Schluessel."""

    async def aufrufen(call: ServiceCall) -> ServiceResponse:
        try:
            return await ablauf(hass, call)
        except pruefungen.Terminfehler as fehler:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=fehler.meldung.schluessel,
                translation_placeholders=fehler.meldung.platzhalter or None,
            ) from None

    return aufrufen


@callback
def async_aktionen_registrieren(hass: HomeAssistant) -> None:
    """Einmal je Home-Assistant-Lauf. Ohne geladenen Standort melden sie das."""
    if hass.services.has_service(DOMAIN, "create_appointment"):
        return
    for aktion, (ablauf, antwort) in _AKTIONEN.items():
        hass.services.async_register(
            DOMAIN, aktion, _uebersetzt(hass, ablauf), schema=_schema(aktion), supports_response=antwort)
```

- [ ] **Step 6: Grün und Commit**

Run: `$HAPY -m pytest -q --rootdir . tests/test_uebersetzungen.py`
Expected: `63 passed`

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `443 passed`

```bash
git add custom_components/meteo_volt/aktionen.py custom_components/meteo_volt/services.yaml custom_components/meteo_volt/translations/de.json custom_components/meteo_volt/translations/en.json tests/test_uebersetzungen.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Offer the appointment actions with translated errors

Seven actions under meteo_volt, open to every user. Fields are optional
in the schema and checked in the backend, so each error arrives as a
ServiceValidationError whose translation key is the key of the spec.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 9: `terminwebsocket.py` und der Start in `__init__.py`

**Files:**
- Create: `custom_components/meteo_volt/terminwebsocket.py`
- Modify: `custom_components/meteo_volt/__init__.py`

**Interfaces:**
- Consumes: aus Task 7 `SIGNAL_PANEL`, `Terminverwaltung`, `nach_geraet`, `nach_standort`, `async_termine_starten`, `async_speicher_entfernen`; aus Task 8 `async_aktionen_registrieren`; aus Task 1 `lokal`.
- Produces: `async_websocket_registrieren(hass)` — `meteo_volt/site`, `meteo_volt/appointments`, `meteo_volt/plan`, `meteo_volt/prices`, `meteo_volt/subscribe`, einmal je Home-Assistant-Lauf. `__init__.py` startet C3 im `try` vor C5 und entfernt den Store mit der Integration.

Kein automatischer Test. Im Quelltext von 2026.4.1: `websocket_api.async_register_command` legt seine Tabelle selbst an, wenn `websocket_api` noch nicht geladen ist.

- [ ] **Step 1: Das Modul**

`custom_components/meteo_volt/terminwebsocket.py`:

```python
"""Die Websocket-Befehle fuer das Panel. Spec C3 Abschnitt 6.

Jeder Nutzer darf lesen: kein Befehl verlangt Admin-Rechte. Jeder nimmt
optional config_entry; ohne meint er den zuerst geladenen Standort. Den
Inhalt baut ansicht.py, hier wird nur gelesen und geschickt.

meteo_volt/subscribe meldet appointments, site, plan, planning und prices,
jeweils nur den Namen. Das Panel liest danach neu.

Geladen wird dieses Modul nur im try (Spec Abschnitt 8). Das Verhalten
sieht kein automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 6
"""

from __future__ import annotations

from datetime import datetime

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import pruefungen, termine
from .const import DOMAIN
from .terminverwaltung import SIGNAL_PANEL, Terminverwaltung, nach_geraet, nach_standort

REGISTRIERT = f"{DOMAIN}_websocket"


def _standort(hass: HomeAssistant, connection, msg: dict) -> Terminverwaltung | None:
    verwaltung = nach_standort(hass, msg.get("config_entry"))
    if verwaltung is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Kein Meteo-Volt-Standort mit Terminen")
    return verwaltung


def _fahrzeug(hass: HomeAssistant, connection, msg: dict, verwaltung: Terminverwaltung) -> str | None:
    """Die subentry_id zur Geraete-ID, oder None nach einer Fehlermeldung."""
    try:
        anderer, fahrzeug_id = nach_geraet(hass, msg.get("vehicle"))
    except pruefungen.Terminfehler:
        anderer = None
    if anderer is not verwaltung:
        connection.send_error(msg["id"], pruefungen.FAHRZEUG_UNBEKANNT, "Kein Fahrzeug dieses Standorts")
        return None
    return fahrzeug_id


def _zeitpunkt(text: str, verwaltung: Terminverwaltung) -> datetime | None:
    """ISO 8601. Ohne Offset gilt die Zeitzone von Home Assistant."""
    try:
        zeitpunkt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return zeitpunkt if zeitpunkt.tzinfo is not None else termine.lokal(text, verwaltung.zeitzone())


@websocket_api.websocket_command(
    {vol.Required("type"): "meteo_volt/site", vol.Optional("config_entry"): str})
@callback
def ws_standort(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is not None:
        connection.send_result(msg["id"], verwaltung.standort())


@websocket_api.websocket_command({
    vol.Required("type"): "meteo_volt/appointments",
    vol.Required("start"): str,
    vol.Required("end"): str,
    vol.Optional("vehicle"): str,
    vol.Optional("config_entry"): str,
})
@callback
def ws_termine(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is None:
        return
    start, ende = _zeitpunkt(msg["start"], verwaltung), _zeitpunkt(msg["end"], verwaltung)
    if start is None or ende is None:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, "start und end sind ISO 8601")
        return
    fahrzeug_id = None
    if msg.get("vehicle") is not None and (fahrzeug_id := _fahrzeug(hass, connection, msg, verwaltung)) is None:
        return
    connection.send_result(msg["id"], verwaltung.termine_im_fenster(start, ende, fahrzeug_id))


@websocket_api.websocket_command({
    vol.Required("type"): "meteo_volt/plan",
    vol.Required("vehicle"): str,
    vol.Optional("config_entry"): str,
})
@callback
def ws_plan(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is None:
        return
    if (fahrzeug_id := _fahrzeug(hass, connection, msg, verwaltung)) is None:
        return
    connection.send_result(msg["id"], verwaltung.plan(fahrzeug_id))


@websocket_api.websocket_command(
    {vol.Required("type"): "meteo_volt/prices", vol.Optional("config_entry"): str})
@callback
def ws_preise(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is not None:
        connection.send_result(msg["id"], verwaltung.preise())


@websocket_api.websocket_command(
    {vol.Required("type"): "meteo_volt/subscribe", vol.Optional("config_entry"): str})
@callback
def ws_abonnieren(hass: HomeAssistant, connection, msg: dict) -> None:
    """Eine Meldung je Aenderung, auch die anderer Nutzer. Ueberlebt das Neuladen des Eintrags."""
    if (verwaltung := _standort(hass, connection, msg)) is None:
        return

    @callback
    def melden(meldung: str) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], meldung))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_PANEL.format(verwaltung.entry.entry_id), melden)
    connection.send_result(msg["id"])


@callback
def async_websocket_registrieren(hass: HomeAssistant) -> None:
    """Einmal je Home-Assistant-Lauf."""
    if hass.data.get(REGISTRIERT):
        return
    hass.data[REGISTRIERT] = True
    for befehl in (ws_standort, ws_termine, ws_plan, ws_preise, ws_abonnieren):
        websocket_api.async_register_command(hass, befehl)
```

- [ ] **Step 2: Start und Ende in `__init__.py`**

```diff
--- a/custom_components/meteo_volt/__init__.py
+++ b/custom_components/meteo_volt/__init__.py
@@ -44,4 +44,7 @@ async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
     try:
         plan_koordinator = MeteoVoltPlanKoordinator(hass, entry, client)
+        # Spec C3 Abschnitt 8: vor dem Start, damit schon der erste Request die
+        # Termine traegt. Scheitert C3, plant C5 ohne sie.
+        await _termine_starten(hass, entry, plan_koordinator)
         plan_koordinator.async_starten()
     except Exception:  # pylint: disable=broad-except
@@ -89,4 +92,34 @@ def _ausgaben_starten(
 
 
+async def _termine_starten(
+    hass: HomeAssistant, entry: ConfigEntry, plan_koordinator: MeteoVoltPlanKoordinator
+) -> None:
+    """Spec C3 Abschnitt 8: Store, Actions und Websocket-Befehle nur im try.
+
+    Der Import steht mit im try. Scheitert etwas, laufen Prognose, Plan und die
+    Entitaeten aus C6 weiter, und der Request geht ohne Termine raus.
+    """
+    try:
+        from .aktionen import async_aktionen_registrieren
+        from .terminverwaltung import async_termine_starten
+        from .terminwebsocket import async_websocket_registrieren
+
+        await async_termine_starten(hass, entry, plan_koordinator)
+        async_aktionen_registrieren(hass)
+        async_websocket_registrieren(hass)
+    except Exception:  # pylint: disable=broad-except
+        _LOGGER.exception("Termine nicht gestartet, Prognose und Plan laufen weiter")
+
+
+async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
+    """Spec C3 Abschnitt 3: entfernt der Nutzer die Integration, geht der Store mit."""
+    try:
+        from .terminverwaltung import async_speicher_entfernen
+
+        await async_speicher_entfernen(hass, entry.entry_id)
+    except Exception:  # pylint: disable=broad-except
+        _LOGGER.exception("Terminspeicher nicht entfernt")
+
+
 async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
     """Unload a config entry."""
```

- [ ] **Step 3: Suite und Commit**

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `443 passed`

```bash
git add custom_components/meteo_volt/terminwebsocket.py custom_components/meteo_volt/__init__.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Start appointments before the coordinator and serve the panel

Five websocket commands for every user; the subscription reports what
changed by name only, from any user. C3 starts inside a try before the
coordinator, so the first request already carries appointments and a
failure leaves forecast and plan running. Removing the integration
removes the store.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 10: Verdrahtung am Quelltext, Namen gegen Home Assistant

**Files:**
- Modify: `tests/test_verdrahtung.py`

**Interfaces:**
- Consumes: alles aus Tasks 1 bis 9.
- Produces: nichts Neues; die Prüfung, dass C3 außerhalb von C3 nur im `try` geladen wird.

- [ ] **Step 1: Der Test prüft C3 mit**

```diff
--- a/tests/test_verdrahtung.py
+++ b/tests/test_verdrahtung.py
@@ -1,3 +1,3 @@
-"""Prueft die Verdrahtung von C6 am Quelltext. Spec C6 Abschnitt 8.
+"""Prueft die Verdrahtung von C6 und C3 am Quelltext. Spec C6 Abschnitt 8, C3 Abschnitt 8.
 
 __init__.py, sensor.py und binary_sensor.py importieren Home Assistant und
@@ -9,4 +9,6 @@ import ast
 from pathlib import Path
 
+import pytest
+
 INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"
 
@@ -37,6 +39,8 @@ def test_kein_rueckruf_fuers_entladen_ist_eine_lambda():
 
 
-# Die Module von C6. Jedes andere Modul laedt sie nur im try.
+# Die Module von C6 und C3. Jedes andere Modul laedt sie nur im try.
 C6 = {"ausgabe", "fahrzeugausgabe", "fahrzeugsensor", "fahrzeugbinaersensor"}
+C3 = {"termine", "pruefungen", "terminbuch", "terminanfrage", "ansicht",
+      "terminverwaltung", "aktionen", "terminwebsocket"}
 
 
@@ -52,23 +56,25 @@ def _importe(knoten: ast.AST, im_try: bool = False):
 
 
-def _laedt_c6(knoten: ast.Import | ast.ImportFrom) -> bool:
+def _laedt(knoten: ast.Import | ast.ImportFrom, gruppe: set[str]) -> bool:
     if not isinstance(knoten, ast.ImportFrom) or knoten.level != 1:
         return False
     if knoten.module is None:  # from . import ausgabe
-        return any(alias.name in C6 for alias in knoten.names)
-    return knoten.module.split(".")[0] in C6
+        return any(alias.name in gruppe for alias in knoten.names)
+    return knoten.module.split(".")[0] in gruppe
 
 
-def test_c6_wird_ausserhalb_von_c6_nur_im_try_importiert():
+@pytest.mark.parametrize(("name", "gruppe"), [("C6", C6), ("C3", C3)])
+def test_die_module_werden_ausserhalb_ihrer_gruppe_nur_im_try_importiert(name, gruppe):
     """Home Assistant 2026.4.1 importiert alle Plattformen, bevor es eine einrichtet.
 
     Ein Importfehler bricht dann das Einrichten des ganzen Eintrags ab, die
     sechs Sensoren der Prognose eingeschlossen. Im try steht er nur im Log.
+    Fuer C3 verlangt das die C3-Spec Abschnitt 8 auch ohne Plattform.
     """
     importe = [
-        (f"{name}:{knoten.lineno}", geschuetzt)
-        for name, baum in _module() if name.removesuffix(".py") not in C6
-        for knoten, geschuetzt in _importe(baum) if _laedt_c6(knoten)
+        (f"{datei}:{knoten.lineno}", geschuetzt)
+        for datei, baum in _module() if datei.removesuffix(".py") not in gruppe
+        for knoten, geschuetzt in _importe(baum) if _laedt(knoten, gruppe)
     ]
-    assert importe, "kein Import von C6 gefunden; prueft der Test noch etwas?"
+    assert importe, f"kein Import von {name} gefunden; prueft der Test noch etwas?"
     assert [stelle for stelle, geschuetzt in importe if not geschuetzt] == []
```

Run: `$HAPY -m pytest -q --rootdir . tests/test_verdrahtung.py`
Expected: `3 passed`

- [ ] **Step 2: Gegenprobe — ein Import von C3 außerhalb des `try`**

```bash
cp custom_components/meteo_volt/__init__.py "<scratchpad>/init.sicherung"
sed -i 's/^from .const import DOMAIN, CONF_API_TOKEN, API_URL$/&\nfrom .terminverwaltung import VERWALTUNGEN/' custom_components/meteo_volt/__init__.py
PYTHONDONTWRITEBYTECODE=1 $HAPY -m pytest -q --rootdir . tests/test_verdrahtung.py; echo "exit=$?"
cp "<scratchpad>/init.sicherung" custom_components/meteo_volt/__init__.py
git status --short custom_components/meteo_volt/__init__.py
```

Expected: `1 failed, 2 passed` mit `__init__.py:12` in der Meldung, danach `exit=1`; `git status` zeigt die Datei nicht mehr als geändert. Zurück per `cp`, nicht per `git checkout` (Hausregeln).

- [ ] **Step 3: Jeden Namen gegen Home Assistant 2026.4.1 prüfen**

Einmalig und nicht committet. Als `<scratchpad>/ha_namen_pruefen.py` speichern:

```python
"""Einmal-Pruefung: gibt es jeden Namen aus Home Assistant, den C3 benutzt, in 2026.4.1?

Das Gate kann Home Assistant nicht laden. Ein falscher Name faellt erst beim
Laden der Integration auf -- in C3 dann ohne Termine, im Plan-Koordinator
ohne jeden Plan.

Aufruf aus dem ha-Repo:  <python> <pfad>/ha_namen_pruefen.py [Integrationsordner]
"""

import ast
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASIS = "https://raw.githubusercontent.com/home-assistant/core/2026.4.1/"
INTEGRATION = Path(sys.argv[1] if len(sys.argv) > 1 else "custom_components/meteo_volt")
DATEIEN = ("terminverwaltung.py", "aktionen.py", "terminwebsocket.py", "plankoordinator.py", "__init__.py")

# Namen, die als Attribut, Methode oder Parameter benutzt und nicht importiert werden.
AUFRUFE = [
    ("homeassistant.helpers.storage", "async_load"),
    ("homeassistant.helpers.storage", "async_save"),
    ("homeassistant.helpers.storage", "async_remove"),
    ("homeassistant.helpers.device_registry", "async_get_device"),
    ("homeassistant.helpers.device_registry", "identifiers"),
    ("homeassistant.helpers.entity_registry", "async_get_entity_id"),
    ("homeassistant.helpers.entity_registry", "EVENT_ENTITY_REGISTRY_UPDATED"),
    ("homeassistant.helpers.update_coordinator", "async_add_listener"),
    ("homeassistant.helpers.update_coordinator", "async_refresh"),
    ("homeassistant.config_entries", "add_update_listener"),
    ("homeassistant.config_entries", "async_on_unload"),
    ("homeassistant.config_entries", "subentries"),
    ("homeassistant.config_entries", "subentry_type"),
    ("homeassistant.core", "async_all"),
    ("homeassistant.core", "async_listen"),
    ("homeassistant.core", "has_service"),
    ("homeassistant.core", "async_register"),
    ("homeassistant.util.dt", "get_default_time_zone"),
    ("homeassistant.util.dt", "utcnow"),
    ("homeassistant.helpers.config_validation", "string"),
    ("homeassistant.components.websocket_api", "ERR_NOT_FOUND"),
    ("homeassistant.components.websocket_api", "ERR_INVALID_FORMAT"),
    ("homeassistant.components.websocket_api", "event_message"),
    ("homeassistant.components.websocket_api", "async_register_command"),
    ("homeassistant.components.websocket_api", "websocket_command"),
    ("homeassistant.components.websocket_api.connection", "send_result"),
    ("homeassistant.components.websocket_api.connection", "send_error"),
    ("homeassistant.components.websocket_api.connection", "send_message"),
    ("homeassistant.components.websocket_api.connection", "subscriptions"),
]

_quellen: dict[str, str | None] = {}


def quelle(modul: str) -> str | None:
    if modul not in _quellen:
        pfad = modul.replace(".", "/")
        _quellen[modul] = None
        for kandidat in (f"{pfad}.py", f"{pfad}/__init__.py"):
            try:
                with urllib.request.urlopen(BASIS + kandidat, timeout=30) as antwort:
                    _quellen[modul] = antwort.read().decode("utf-8")
                    break
            except urllib.error.HTTPError:
                continue
    return _quellen[modul]


def definiert(modul: str, name: str) -> bool:
    text = quelle(modul)
    if text is None:
        return False
    muster = (
        rf"^\s*(?:class|def|async def|type) {re.escape(name)}\b"
        rf"|^\s*(?:self\.)?{re.escape(name)}\s*[:=]"
    )
    if re.search(muster, text, re.MULTILINE):
        return True
    # Weitergereicht, auch ueber mehrere Zeilen, etwa in websocket_api/__init__.py.
    weitergereicht = (
        rf"^\s*from\s+\S+\s+import\s+[^(\n]*\b{re.escape(name)}\b"
        rf"|^\s*{re.escape(name)}\s*(?:as\s+\w+\s*)?,?\s*$"
    )
    if re.search(weitergereicht, text, re.MULTILINE):
        return True
    # from homeassistant.helpers import storage: ein Untermodul.
    return quelle(f"{modul}.{name}") is not None


fehlend = []
geprueft = 0
for datei in DATEIEN:
    baum = ast.parse((INTEGRATION / datei).read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ImportFrom) and (knoten.module or "").startswith("homeassistant"):
            for alias in knoten.names:
                geprueft += 1
                if not definiert(knoten.module, alias.name):
                    fehlend.append(f"{datei}: from {knoten.module} import {alias.name}")
for modul, name in AUFRUFE:
    geprueft += 1
    if not definiert(modul, name):
        fehlend.append(f"{modul}: {name}")

if fehlend:
    print("FEHLT in Home Assistant 2026.4.1:")
    print("\n".join(f"  {zeile}" for zeile in fehlend))
    sys.exit(1)
print(f"alle {geprueft} Namen in Home Assistant 2026.4.1 gefunden")
```

Zuerst die Gegenprobe — eine Prüfung, die nichts findet, darf nicht grün werden:

```bash
rm -rf "<scratchpad>/gegenprobe" && mkdir -p "<scratchpad>/gegenprobe"
cp custom_components/meteo_volt/*.py "<scratchpad>/gegenprobe/"
sed -i 's/async_track_state_removed_domain,/async_track_state_removed_domai,/' "<scratchpad>/gegenprobe/terminverwaltung.py"
$HAPY "<scratchpad>/ha_namen_pruefen.py" "<scratchpad>/gegenprobe"; echo "exit=$?"
```

Expected: `FEHLT in Home Assistant 2026.4.1:` mit genau der Zeile `terminverwaltung.py: from homeassistant.helpers.event import async_track_state_removed_domai`, danach `exit=1`

Run: `$HAPY "<scratchpad>/ha_namen_pruefen.py"`
Expected: `alle 74 Namen in Home Assistant 2026.4.1 gefunden`

- [ ] **Step 4: Suite, Kontrakt, Commit**

Run: `$HAPY -m pytest -q --rootdir . tests`
Expected: `444 passed`

Run: `$HAPY scripts/check_contract.py`
Expected: `Kontrakt in sync (35 Dateien geprueft)`

```bash
git add tests/test_verdrahtung.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Check that C3 is only imported inside a try

A failing import of the appointment modules must not take the six
forecast sensors down with it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 11: Übergabe — Push nach Rückfrage, Deployment vorlegen

**Files:** keine.

**Interfaces:**
- Consumes: den Stand nach Task 10.
- Produces: den Branch `c3-konfig-entitaeten` für C8 und eine Vorlage für das Deployment des Plan-Dienstes.

Keine Beta: C3 hat keine Oberfläche und wird mit C8 abgenommen. `manifest.json` bleibt, wie sie ist.

- [ ] **Step 1: Stand zusammenfassen**

```bash
git log --oneline beta..HEAD
git -C ../meteo-volt-brain-c3 log --oneline beta..HEAD
```

Expected: im ha-Repo elf Commits (Plan und zehn Tasks), im Brain einer.

- [ ] **Step 2: Patrick fragen, dann pushen**

Erst nach seinem Ja, in beiden Worktrees:

```bash
git push -u origin c3-konfig-entitaeten
git ls-remote origin refs/heads/c3-konfig-entitaeten
```

Expected: `ls-remote` nennt den Commit von `git rev-parse HEAD`. Kein Merge nach `beta`.

- [ ] **Step 3: Das Deployment des Plan-Dienstes vorlegen**

Nicht ausführen. Der Plan-Dienst auf dem VPS kennt `trips` noch nicht und weist jeden Request von C3 mit 400 ab (A5-Spec Abschnitt 2.4). Vor der Abnahme braucht er den Stand von `beta` im Brain, der `A5` enthält (`c125d44`). Patrick bekommt die Schritte mit Erklärung je Befehl, zuerst die lesenden:

1. Stand lesen: `cd ~/meteo-volt && git status -sb && git log --oneline -1` — welcher Branch, welcher Commit. Verändert nichts.
2. Heute ablehnen lassen: aus `deploy/abnahme-request.json` einen Request mit `"consumption": {"type": "trips", "trips": []}` bauen und wie in `deploy/README.md`, Abnahme `B2V` Schritt 2, an `127.0.0.1:8081` schicken. Erwartet heute `400`.
3. Nach seinem Ja: `git fetch origin`, `git merge --ff-only origin/beta`, `docker compose -f deploy/compose.yaml up -d --build`, `docker compose -f deploy/compose.yaml ps` bis `healthy`.
4. Derselbe Request aus Schritt 2: jetzt `200`.

Befunde zuerst, geändert wird erst nach seiner Entscheidung je Punkt. Steht der VPS nicht auf `beta`, ist das ein eigener Befund.

---

## Abnahme — macht Patrick, im Panel mit C8

Auf der eigenen Instanz mit Home Assistant 2026.4.1 und der Beta von C8, nach dem Deployment aus Task 11. Die Klickwege stehen im Plan von C8. Vorher ist C3 nicht fertig. Aus Sicht von C3 muss die Abnahme zeigen (Spec Abschnitt 10):

1. Das Update ohne Termin: Die sechs Sensoren und die Fahrzeugentitäten laufen weiter.
2. Ein einmaliger Termin mit Strecke: In der Abwesenheit plant der Plan kein Laden, und vor der Abfahrt reicht der Ladestand für die Strecke.
3. Eine Serie werktags 8–18 Uhr: Jeder Werktag ist im Plan weg. Ein einzeln abgesagter Mittwoch fehlt, ein einzeln geänderter trägt seine Werte.
4. Ein Termin mit 100 %: Ein Ladeblock nennt ihn als Grund. Ist das Ziel unerreichbar, nennt der Termin die fehlenden kWh.
5. Das Risiko wechseln: Ein neuer Plan kommt.
6. Mehrmals schnell „Neu planen": Die Meldung nennt die Restdauer der Sendepause.
7. Ein Fahrzeug löschen: Seine Termine sind weg.
8. Home Assistant neu starten: Die Termine bleiben, Rückgängig geht nicht mehr.
9. Ein zweiter Nutzer ohne Admin-Rechte legt einen Termin an: Das offene Panel des ersten zeigt ihn sofort.
10. Während aller Schritte laufen die sechs Sensoren weiter.

## Nach der Abnahme

Erst nach Patricks Ja, zusammen mit C8:

- **Brain**, Branch `c3-konfig-entitaeten`: `status = "in-arbeit"` auf `status = "fertig"` in `docs/features/C3-konfig-entitaeten/feature.md`, dann `$PY scripts/build_docs.py` und das Gate, Commit.
- **Beide Branches nach `beta` mergen**, im Brain und im ha-Repo, jeweils mit `--no-ff`. Pushen erst nach Rückfrage, danach lokal aufräumen.

## Was dieser Plan nicht baut

| Nicht hier | Wo |
|---|---|
| Das Panel, seine Anmeldung und sein JavaScript | `C8` |
| Laden vor der ersten Fahrt auf Max (`first_need` in `meteovolt_planner/optimizer.py`) | Überarbeitung des Planers |
| Mehrere Fahrzeuge an einem Ladepunkt, wer wann wo lädt | `E1`, `Z4` |
| `earliest_start`, ein Ziel nach der Rückkehr, eine Kalender-Entität, `get_plan` | entfallen, Spec Abschnitt 11 |
| Vergangene Preise | entfallen, Spec Abschnitt 6 |
| Das Deployment auf dem VPS ausführen | Patrick, nach der Vorlage aus Task 11 |
