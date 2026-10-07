"""Prueft, dass jede vendorte Datei zu ihrem Eintrag in contract.lock.json passt.

Das Gegenstueck zu `npm run check:contract` im Gateway-Repo, und aus demselben
Grund vorhanden: eine Handaenderung an einer generierten Datei muss auffallen,
OHNE dass ein Brain-Checkout danebenliegt. Der vollstaendige Drift-Vergleich
gegen den aktuellen Brain-Stand bleibt dort, wo alle drei Checkouts vorliegen
(meteo-volt-brain/scripts/check_contract_drift.py).

Warum als pytest-Datei UND als Skript (scripts/check_contract.py): das Skript
traegt die gesamte Logik, diese Datei ruft sie nur auf. Im Gateway-Repo muss
`npm run check:contract` von Hand angestossen werden; hier laeuft dieselbe
Pruefung bei jedem `pytest tests/` mit, das ein C5/C6-Entwickler ohnehin
ausfuehrt -- vergessen kann man sie damit nicht.

Die Mutationstests unten laufen auf einer KOPIE des Repos in tmp_path. Der
Arbeitsbaum wird dabei nie angefasst; ohne diese Tests waere allein durch
"gruen auf dem echten Repo" nicht belegt, dass die Pruefung ueberhaupt
Zaehne hat.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Das Pruefskript per Pfad laden statt es zu importieren: scripts/ ist kein
# Paket, und custom_components/ bleibt unberuehrt. Dieselbe Technik benutzt
# check_contract_drift.py im Brain-Repo, um export_contract.py zu laden.
_SPEC = importlib.util.spec_from_file_location(
    "check_contract", REPO_ROOT / "scripts" / "check_contract.py")
check_contract = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_contract)

VENDOR_DIR = check_contract.VENDOR_DIR
LOCK_NAME = check_contract.LOCK_NAME


def _clone(tmp_path: Path) -> Path:
    """Legt eine vollstaendige, unveraenderte Kopie der gepruefften Dateien an."""
    shutil.copytree(REPO_ROOT / VENDOR_DIR, tmp_path / VENDOR_DIR)
    shutil.copyfile(REPO_ROOT / LOCK_NAME, tmp_path / LOCK_NAME)
    return tmp_path


def _lock(root: Path) -> dict:
    return json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))


def _write_lock(root: Path, lock: dict) -> None:
    (root / LOCK_NAME).write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")


def _any_entry(lock: dict) -> str:
    """Irgendein Eintrag, aber deterministisch -- ein zufaellig gewaehlter
    Eintrag machte einen Fehlschlag nicht reproduzierbar."""
    return sorted(lock["files"])[0]


def test_repository_is_in_sync():
    assert check_contract.problems(REPO_ROOT) == []


def test_untouched_clone_is_in_sync(tmp_path):
    """Ohne diesen Test koennte jeder Mutationstest unten aus dem falschen
    Grund gruen sein -- naemlich weil die Kopie selbst schon kaputt ist."""
    assert check_contract.problems(_clone(tmp_path)) == []


# --- Mutationen: die Pruefung muss anschlagen ---------------------------
#
# Jeder Test hier veraendert die KOPIE und verlangt eine Meldung. Eine
# Pruefung, die nur auf dem gesunden Repo gruen ist, hat noch nichts
# bewiesen.


def test_hand_edited_value_is_reported(tmp_path):
    """Der wichtigste Fall: ein einzelner geaenderter Zahlenwert.

    Weder die Schemavalidierung noch die Paarungstests in
    test_contract_fixtures.py sehen das -- 0.0409 statt 0.0509 ist
    schemakonform.
    """
    root = _clone(tmp_path)
    target = root / VENDOR_DIR / "minimal.request.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["vehicles"][0]["soc_pct"] = 48.0
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    assert any("minimal.request.json" in p and "sha256" in p
               for p in check_contract.problems(root))


def test_deleted_file_is_reported(tmp_path):
    root = _clone(tmp_path)
    (root / VENDOR_DIR / "full.response.json").unlink()
    assert any("full.response.json" in p and "fehlt" in p
               for p in check_contract.problems(root))


def test_removed_lock_entry_is_reported(tmp_path):
    """Gegenrichtung: die Datei liegt da, ihr Lock-Eintrag ist weg.

    Der Vorwaertslauf geht ueber lock["files"] -- was dort fehlt, sieht er
    nicht. Ohne diese Gegenrichtung machte das Loeschen eines Eintrags die
    Pruefung LEISER statt lauter.
    """
    root = _clone(tmp_path)
    lock = _lock(root)
    del lock["files"]["tests/fixtures/contract/full.response.json"]
    _write_lock(root, lock)
    assert any("full.response.json" in p and "Lock-Eintrag" in p
               for p in check_contract.problems(root))


def test_empty_lock_is_reported_instead_of_silently_green(tmp_path):
    """Der degenerierte Fall. "files": {} pruefte null Dateien und kaeme
    ohne Gegenrichtung als gruen durch -- "nichts geprueft" darf sich nie
    als "alles in Ordnung" lesen."""
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["files"] = {}
    _write_lock(root, lock)
    assert check_contract.problems(root)


def test_lock_without_do_not_edit_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["do_not_edit"] = False
    _write_lock(root, lock)
    assert any("do_not_edit" in p for p in check_contract.problems(root))


def test_unknown_scope_is_reported(tmp_path):
    """Ein unbekannter scope darf niemals auf "document" zurueckfallen --
    das waere wieder ein stilles Raten statt einer Pruefung."""
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["files"][_any_entry(lock)]["scope"] = "components.schemas"
    _write_lock(root, lock)
    assert any("scope" in p for p in check_contract.problems(root))


def test_lock_entry_without_sha256_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    del lock["files"][_any_entry(lock)]["sha256"]
    _write_lock(root, lock)
    assert any("sha256" in p for p in check_contract.problems(root))


def test_lock_entry_outside_the_vendor_directory_is_reported(tmp_path):
    """Die Gegenrichtung glob-t tests/fixtures/contract/. Vendort der Brain
    eines Tages woandershin, deckte sie diesen Pfad lautlos nicht mehr ab --
    dann muss dieses Skript es lernen, statt weniger zu pruefen als es
    behauptet."""
    root = _clone(tmp_path)
    lock = _lock(root)
    entry = _any_entry(lock)
    lock["files"]["config/anderswo.json"] = lock["files"][entry]
    _write_lock(root, lock)
    # Die Datei wird MIT angelegt, damit ihr Eintrag sauber durchhasht --
    # sonst faenge ihn schon "Datei fehlt", und der blinde Fleck der
    # Gegenrichtung bliebe unbewiesen.
    (root / "config").mkdir()
    shutil.copyfile(root / entry, root / "config" / "anderswo.json")
    assert any("config/anderswo.json" in p and VENDOR_DIR in p
               for p in check_contract.problems(root))


def test_added_fixture_without_lock_entry_is_reported(tmp_path):
    """Eine von Hand dazugelegte Datei im generierten Verzeichnis."""
    root = _clone(tmp_path)
    (root / VENDOR_DIR / "selbstgebaut.request.json").write_text(
        '{"schema_version": 1}\n', encoding="utf-8", newline="\n")
    assert any("selbstgebaut.request.json" in p
               for p in check_contract.problems(root))


def test_broken_json_is_reported(tmp_path):
    root = _clone(tmp_path)
    target = root / VENDOR_DIR / "minimal.response.json"
    target.write_text("{kaputt", encoding="utf-8", newline="\n")
    assert any("minimal.response.json" in p for p in check_contract.problems(root))


def test_missing_lock_is_reported(tmp_path):
    """Ohne Lock gibt es nichts zu vergleichen -- das ist ein Fehler, kein
    leerer Befund."""
    root = _clone(tmp_path)
    (root / LOCK_NAME).unlink()
    assert any(LOCK_NAME in p for p in check_contract.problems(root))


def test_hand_edited_stamp_is_reported(tmp_path):
    """Der Stempel liegt im blinden Fleck des Lock-Hashes.

    content_sha256 entfernt x-meteo-volt-contract VOR dem Hashen -- eine
    Aenderung am Stempel selbst (brain_commit gefaelscht, do_not_edit auf
    false gedreht) laesst den Lock-Hash also voellig unberuehrt. Der
    Stempel traegt seinen eigenen sha256 ueber denselben Inhalt; genau
    daran faellt er auf.
    """
    root = _clone(tmp_path)
    target = root / VENDOR_DIR / "plan-request.schema.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["x-meteo-volt-contract"]["brain_commit"] = "deadbee"
    payload["x-meteo-volt-contract"]["do_not_edit"] = False
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    # Der Lock-Hash bleibt gruen -- das ist der Punkt.
    assert check_contract.content_sha256(payload) == \
        _lock(root)["files"][f"{VENDOR_DIR}/plan-request.schema.json"]["sha256"]
    assert any("plan-request.schema.json" in p and "Stempel" in p
               for p in check_contract.problems(root))


def test_cli_returns_zero_on_the_real_repository():
    assert check_contract.main([]) == 0


def test_cli_returns_nonzero_on_problems(tmp_path):
    root = _clone(tmp_path)
    (root / VENDOR_DIR / "full.response.json").unlink()
    assert check_contract.main(["--root", str(root)]) == 1
