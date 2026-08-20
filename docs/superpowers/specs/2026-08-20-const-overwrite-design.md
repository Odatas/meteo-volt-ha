# `const_overwrite.json` — gegen die Dev-API testen

Stand 2026-08-20.

## Zweck

Die Integration soll sich auf eine andere API-URL umstellen lassen, ohne dass
diese URL im ausgelieferten Code steht. Ein Tester legt eine Datei ab, startet
Home Assistant neu, fertig. Ein normaler Nutzer bemerkt nichts und erfährt die
Dev-URL nicht.

## Verhalten

`custom_components/meteo_volt/const_overwrite.json`, neben dem Modul. Wird beim
Setup und beim Config-Flow gelesen, nicht zwischengespeichert.

```json
{ "api_url": "https://.../v1/prediction" }
```

| Lage | Wirkung | Log |
|---|---|---|
| Datei fehlt | Prod-URL aus `const.py` | nichts |
| gültig | URL aus der Datei | WARNING mit vollständiger URL |
| kaputtes JSON | Prod-URL | WARNING |
| `api_url` fehlt oder kein nicht-leerer String | Prod-URL | WARNING |
| unbekannter Schlüssel | übrige gültige Schlüssel wirken | WARNING mit Namen |

Kein Log, wenn die Datei fehlt: das ist der Normalfall bei jedem Nutzer, eine
Meldung bei jedem Start wäre Rauschen. Bei jeder **vorhandenen** Datei steht
dagegen immer eine Zeile im Log — auch im Erfolgsfall. Sonst wäre der
gefährliche Fall nicht der Absturz, sondern die stille Annahme, man teste gegen
Dev, während Prod antwortet. Der WARNING auf unbekannte Schlüssel fängt den
Tippfehler `api_ur`, der sonst genau dorthin führt.

Die vollständige URL steht bewusst im Log. Wer die Datei abgelegt hat, kennt sie;
der Preis ist, dass sie in geteilten Logs auftaucht.

## Aufbau

**`overrides.py`** (neu) — liest die Datei, liefert die wirksamen Werte.
**Keine Home-Assistant-Importe**, reines stdlib: die Testabhängigkeiten sind
`pytest`, `jsonschema`, `rfc8785`, kein `pytest-homeassistant-custom-component`.
Alles mit HA-Import wäre hier nicht unit-testbar. Deshalb liegt die gesamte
Logik in diesem Modul und die Verdrahtung bleibt klein genug, um sie mit dem
Auge zu prüfen.

**`const.py`** unverändert. `API_URL` bleibt die hartkodierte Prod-URL und der
Default.

**`api.py`** — `MeteoVoltApiClient.__init__(api_token, api_url=API_URL)`. Der
Client zieht die URL nicht mehr aus einer Modulkonstante, sondern bekommt sie
übergeben. Das ist der Kern der Änderung; nebenbei wird der Client testbar.

**Beide Aufrufstellen** lösen auf und übergeben:
`__init__.py::async_setup_entry` und `config_flow.py::validate_input`. Der
Config-Flow validiert den Token gegen die API — griffe die Umschaltung nur an
einer Stelle, richtete man gegen Prod ein und pollte gegen Dev.

Gelesen wird über `hass.async_add_executor_job`; Dateizugriff gehört bei Home
Assistant nicht in den Event-Loop.

## Nebenwirkungen

`const_overwrite.json` kommt in `.gitignore`, damit die Dev-URL nicht
versehentlich committet wird.

HACS ersetzt bei jedem Update das gesamte Verzeichnis
`custom_components/meteo_volt/`. Die Datei ist danach weg und muss erneut
abgelegt werden — bewusst so entschieden, der Ablageort neben der Integration
war gewünscht.

## Tests

`tests/test_overrides.py`: keine Datei · gültige Datei · kaputtes JSON ·
fehlender Schlüssel · falscher Typ · unbekannter Schlüssel. Dazu ein Test, dass
`MeteoVoltApiClient` die übergebene URL tatsächlich benutzt.
