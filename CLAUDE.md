# meteo-volt-ha

Home-Assistant-Integration, Python. **Geht an Endnutzer.**

Ein Feature arbeitet auf seinem **eigenen Branch** und wird fertig nach `beta` gemergt.
Default ist `master`; dorthin mergt keine Session.

`custom_components/` ist Endnutzer-Code — HACS paketiert genau dieses Verzeichnis und sonst
nichts. Was dort nicht liegt, erreicht keinen Nutzer: `tests/`, `scripts/` und die Fixtures
also nicht.

Venv: `.venv`.

## Betas gehen über HACS, nicht über Kopieren

Ein Stand erreicht die Testinstanz als **GitHub-Prerelease**, nicht als kopiertes Verzeichnis.

- **Ein Tag zeigt auf einen Commit, nicht auf einen Branch.** Was danach auf den Branch kommt,
  erreicht niemanden. Ein Tag wird **nie verschoben** — sonst bedeutet dieselbe Nummer je nach
  Zeitpunkt etwas anderes, und HACS meldet den Wechsel nicht, weil die Zahl gleich blieb.
- **Eine neue Beta je prüfbarem Stand, nicht je Commit.** Zehn Commits, dann `1.1.0-beta.4`.
- **Manifest zuerst, dann taggen.** `manifest.json` auf die neue Nummer, committen, pushen, und
  *dann* das Release auf diesen Commit legen. Laufen Tag und Manifest auseinander, zeigt HACS
  die eine Zahl und Home Assistant die andere.
- Im Release **„Set as a pre-release" an**, „Set as the latest release" aus.
- Die Beta-Linie läuft weiter, bis ihr `x.y.0` final erscheint. `1.1.0` ist noch offen.

Auf der Testinstanz meldet HACS Prereleases nur, wenn `switch.<name>_pre_release` an ist. Der
ist von HACS aus deaktiviert und muss in Home Assistant erst aktiviert werden; ohne ihn steht
die Version zwar im Herunterladen-Dialog, HACS weist aber nie von selbst darauf hin. Und HACS
frischt Custom-Repos nur alle ~48 h auf — ein frisches Release wird erst nach
„Repository-Informationen aktualisieren" sichtbar.

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
Kontraktregeln, `docs/FEATURES.md` für den Stand. Dieses Repo betreffen `S1`, `C1`–`C7` und
`D2`.
