# meteo-volt-ha

Home-Assistant-Integration, Python. **Geht an Endnutzer.**

Gearbeitet wird auf **`beta`**. Default ist `master`.

`custom_components/` ist Endnutzer-Code — HACS paketiert genau dieses Verzeichnis und sonst
nichts. Was dort nicht liegt, erreicht keinen Nutzer: `tests/`, `scripts/` und die Fixtures
also nicht.

Venv: `.venv`.

## Der Kontrakt ist generiert

Die 35 Kontrakt-Artefakte in diesem Repo werden **nie von Hand geändert**. Sie entstehen im
Brain und werden hierher verteilt.

```bash
.venv/Scripts/python.exe scripts/check_contract.py
```

Rot heißt: im Brain neu erzeugen und neu verteilen, nicht hier nachziehen.

Das `unique_id`-Schema der bestehenden Sensoren bleibt unverändert. Jede Änderung bricht
Historie, Dashboards und Automationen aller Bestandsnutzer.

## Wo das Projekt dokumentiert ist

Alles Übergreifende liegt im Brain: `https://github.com/Odatas/meteo-volt-brain.git`, Branch
`beta`.

Dort: `docs/PROJEKT.md` für den Überblick, `docs/normen/basiskontrakt.md` für die
Kontraktregeln, `docs/FEATURES.md` für den Stand. Dieses Repo betreffen `S1`, `C1`–`C6` und
`D2`.
