"""Prueft die vendorten Kontrakt-Artefakte gegen contract.lock.json.

Faengt eine Handaenderung an einer generierten Datei, ohne dass ein
Brain-Checkout vorhanden sein muss -- dasselbe Ziel wie
`npm run check:contract` im Gateway-Repo.

    python scripts/check_contract.py

Der Kanonisierer ist bewusst KEINE dritte Handkopie. Der sha256 in
contract.lock.json wird ueber das kanonisierte JSON gebildet, und dieses
Verfahren -- ECMAScript-Zahlformatierung, UTF-16-Schluesselsortierung --
ist RFC 8785 (JSON Canonicalization Scheme). Das sagt der Brain in
export_contract.canonical_number selbst: "eine anerkannte Regel, keine
Hausregel dieses Projekts". Dieses Repo konsumiert deshalb die NORM
(Paket rfc8785) statt die Implementierung des Brains abzuschreiben.

Der Unterschied ist der Punkt: eine abgeschriebene Implementierung waere
eine dritte Liste, die driften kann -- und anders als die beiden
bestehenden haette sie kein Orakel, das sie beweist (der Brain haelt seine
Kopie mit test_canonical_cross_language.py gegen echtes node, das
Gateway IST node). Eine unabhaengige Implementierung derselben Norm kann
dagegen nicht mit einer Projektaenderung mitdriften, und wenn sie doch
einmal vom Brain abweicht, ist genau das ein Befund: dann folgt eine der
beiden Seiten der Norm nicht, der sie zu folgen behauptet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    import rfc8785
except ModuleNotFoundError as exc:  # pragma: no cover - Umgebungsfehler
    # Laut scheitern, nicht ueberspringen: ohne Kanonisierer kann diese
    # Pruefung nichts beweisen, und ein stiller Durchlauf laese "nichts
    # geprueft" als "alles in Ordnung" lesen.
    raise ModuleNotFoundError(
        "rfc8785 fehlt -- ohne Kanonisierer beweist diese Pruefung nichts. "
        "pip install -r tests/requirements-test.txt"
    ) from exc

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "contract.lock.json"
STAMP_KEY = "x-meteo-volt-contract"

# Wo die vendorten Artefakte in DIESEM Repo liegen. Keine Liste von
# Dateien -- die kommt aus dem Lock bzw. aus dem Verzeichnis selbst.
VENDOR_DIR = "tests/fixtures/contract"

# Muss zu SCOPE_DOCUMENT in meteo-volt-brain/scripts/export_contract.py
# passen. Der zweite dort definierte Wert (components.schemas) gehoert zu
# einem Artefakt, das nur ins Gateway-Repo vendort wird; ihn hier
# nachzubauen hiesse, eine Regel zu pflegen, die dieses Repo nie braucht.
# Taucht er hier doch auf, ist das ein lauter Fehler, keine Vermutung.
SCOPE_DOCUMENT = "document"


def content_sha256(payload: dict) -> str:
    """sha256 ueber das kanonisierte Dokument, ohne den Stempel.

    Gehasht wird der GEPARSTE Inhalt, nicht die Bytes der Datei -- eine
    Fixture darf also 58.0 auf der Platte stehen haben, solange sie
    kanonisiert 58 ergibt. Genau diese Zahlform steht in den Fixtures
    massenhaft; ein naives json.dumps(sort_keys=True) traefe den Hash
    deshalb bei praktisch keiner Datei.

    Nachgemessen an allen 35 vendorten Dateien und an der Zahlenbatterie
    aus test_canonical_cross_language.py im Brain (2.0, -0.0, 1e-07, 1e21,
    5e-324, 1.7976931348623157e308, Nicht-ASCII-Schluessel jenseits der
    BMP): rfc8785 und der Brain stimmen ueberein. Der einzige bekannte
    Unterschied liegt bei Ganzzahlen jenseits von 2**53, die JSON.parse
    ohnehin runden wuerde -- der Brain rundet sie mit, rfc8785 lehnt sie
    mit IntegerDomainError ab. Das ist die sichere Richtung: laut statt
    still, und im Kontrakt gibt es keine solchen Werte (die Ganzzahlen
    sind Zaehler und Prozente).
    """
    body = {k: v for k, v in payload.items() if k != STAMP_KEY}
    return hashlib.sha256(rfc8785.dumps(body)).hexdigest()


def scoped_hash(payload: dict, scope: str) -> str:
    """Hash ueber genau den Ausschnitt, den scope benennt."""
    if scope == SCOPE_DOCUMENT:
        return content_sha256(payload)
    raise ValueError(
        f"scope {scope!r} ist in diesem Repo nicht vorgesehen -- bisher "
        f"vendort der Brain hierher ausschliesslich {SCOPE_DOCUMENT!r}"
    )


def problems(root: Path) -> list[str]:
    """Alle gefundenen Abweichungen als lesbare Zeilen; leer heisst in sync.

    Die Pruefung laeuft in BEIDE Richtungen. Vorwaerts ueber die
    Lock-Eintraege -- das faengt eine geaenderte oder geloeschte Datei.
    Rueckwaerts ueber das Verzeichnis -- das faengt eine Datei ohne
    Lock-Eintrag, die vorwaerts unsichtbar waere. Ohne die Gegenrichtung
    machte das Loeschen eines Eintrags die Pruefung leiser statt lauter;
    genau diese Luecke hat check_contract_drift.py im Brain-Repo mit
    seinem dritten Pass geschlossen.
    """
    found: list[str] = []
    lock_path = root / LOCK_NAME
    if not lock_path.exists():
        # Kein Lock heisst nicht "nichts zu tun", sondern "nicht pruefbar".
        return [f"{LOCK_NAME} fehlt in {root} -- ohne Lock ist nichts pruefbar"]
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{LOCK_NAME}: kein gueltiges JSON ({exc})"]

    if lock.get("do_not_edit") is not True:
        found.append(
            f"{LOCK_NAME}: do_not_edit ist nicht true -- das Lock wird vom "
            "Exporter geschrieben und nie von Hand bearbeitet"
        )

    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        # Der degenerierte Fall: ohne Eintraege pruefte die Schleife unten
        # null Dateien und meldete nichts. "nichts geprueft" darf sich nie
        # als "alles in Ordnung" lesen.
        found.append(
            f"{LOCK_NAME}: keine pruefbaren Eintraege unter \"files\" -- "
            "Exporter mit --to-ha erneut laufen lassen"
        )
        files = files if isinstance(files, dict) else {}

    # --- Vorwaerts: jeder Lock-Eintrag gegen seine Datei -----------------
    for relative, entry in sorted(files.items()):
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("sha256"), str)
                or not isinstance(entry.get("scope"), str)):
            # Ein unvollstaendiger Eintrag darf nicht uebersprungen werden:
            # uebersprungen hiesse ungeprueft, und ungeprueft kaeme als
            # gruen durch.
            found.append(
                f"{relative}: Lock-Eintrag ohne sha256/scope -- kann nicht "
                "geprueft werden"
            )
            continue

        if not relative.startswith(f"{VENDOR_DIR}/"):
            # Die Gegenrichtung unten durchsucht genau VENDOR_DIR. Ein
            # Eintrag ausserhalb waere von ihr nicht abgedeckt -- dann
            # prueft dieses Skript weniger, als es behauptet, und das muss
            # es sagen, statt es zu verschweigen.
            found.append(
                f"{relative}: Lock-Eintrag ausserhalb von {VENDOR_DIR}/ -- "
                "die Gegenrichtung deckt diesen Pfad nicht ab, "
                "scripts/check_contract.py muss ihn lernen"
            )

        target = root / relative
        if not target.exists():
            found.append(f"{relative}: Datei fehlt -- Exporter mit --to-ha "
                         "erneut laufen lassen")
            continue
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            actual = scoped_hash(payload, entry["scope"])
        except Exception as exc:
            # Kaputtes JSON oder ein unbekannter scope landen hier -- als
            # Befund gemeldet, nicht als Abbruch des ganzen Laufs, und
            # ausdruecklich nicht als "in sync".
            found.append(f"{relative}: {exc}")
            continue
        if actual != entry["sha256"]:
            found.append(
                f"{relative}: sha256 weicht vom Lock-Eintrag ab (erwartet "
                f"{entry['sha256'][:12]}, gefunden {actual[:12]}) -- Datei "
                "wurde von Hand bearbeitet"
            )
            continue
        found.extend(_stamp_problems(relative, payload, actual, entry["scope"]))

    # --- Rueckwaerts: jede Datei im Verzeichnis gegen das Lock -----------
    vendor = root / VENDOR_DIR
    if not vendor.is_dir():
        found.append(f"{VENDOR_DIR}/ fehlt -- Exporter mit --to-ha erneut "
                     "laufen lassen")
        return found
    for path in sorted(vendor.rglob("*.json")):
        relative = path.relative_to(root).as_posix()
        if relative not in files:
            found.append(
                f"{relative}: kein Lock-Eintrag -- unter {VENDOR_DIR}/ liegt "
                "ausschliesslich Generiertes; eigene Fixtures gehoeren "
                "woandershin"
            )
    return found


def _stamp_problems(relative: str, payload: dict, actual: str,
                    scope: str) -> list[str]:
    """Der Stempel liegt im blinden Fleck des Lock-Hashes.

    content_sha256 entfernt x-meteo-volt-contract VOR dem Hashen. Eine
    Aenderung AM STEMPEL laesst den Lock-Hash also unberuehrt und kaeme
    sonst durch. Der Stempel traegt seinen eigenen sha256 ueber denselben
    Inhalt -- daran ist er pruefbar.

    Was hier bewusst NICHT geprueft werden kann: brain_commit. Welcher
    Commit die Datei erzeugt hat, weiss nur der Brain; dafuer ist
    check_contract_drift.py zustaendig. Nur die drei Schema-Dateien tragen
    ueberhaupt einen Stempel, die Fixtures nicht -- ein fehlender Stempel
    ist deshalb kein Befund, ein widerspruechlicher schon.
    """
    stamp = payload.get(STAMP_KEY)
    if not isinstance(stamp, dict) or scope != SCOPE_DOCUMENT:
        return []
    problems_found: list[str] = []
    if stamp.get("do_not_edit") is not True:
        problems_found.append(
            f"{relative}: Stempel sagt do_not_edit != true -- die Datei "
            "wird generiert und nie von Hand bearbeitet"
        )
    if stamp.get("sha256") != actual:
        problems_found.append(
            f"{relative}: Stempel nennt sha256 {str(stamp.get('sha256'))[:12]}, "
            f"der Inhalt ergibt {actual[:12]} -- Stempel von Hand bearbeitet"
        )
    return problems_found


def _entry_count(root: Path) -> int:
    """Nur fuer die Ausgabe. Ein blosses "in sync" liesse offen, ob
    ueberhaupt etwas geprueft wurde -- die Zahl beantwortet das. Sicher
    lesbar, weil main() das nur aufruft, wenn problems() nichts gefunden
    hat, und ein fehlendes oder leeres Lock dort bereits ein Befund ist.
    """
    return len(json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))["files"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT,
        help="zu pruefendes Checkout (Vorgabe: dieses Repository)")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    found = problems(root)
    for problem in found:
        print(f"FAIL {problem}")
    if found:
        print(f"{len(found)} Abweichung(en)")
        return 1
    print(f"Kontrakt in sync ({_entry_count(root)} Dateien geprueft)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
