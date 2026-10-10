"""Prueft die Kontrakt-Kopien gegen contract.lock.json.

Die Dateien unter tests/fixtures/contract/ werden erzeugt und nie von Hand
geaendert. Die Pruefung braucht kein weiteres Repository.

    python scripts/check_contract.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "contract.lock.json"
VENDOR_DIR = "tests/fixtures/contract"
KIND = "text-lf"


def file_sha256(path: Path) -> str:
    """SHA-256 ueber den Inhalt mit LF.

    Der Arbeitsbaum traegt unter Windows CRLF, das Repo LF. Ohne die
    Ersetzung haette dieselbe Datei zwei Fingerabdruecke.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def problems(root: Path) -> list[str]:
    """Alle Abweichungen als lesbare Zeilen. Leer heisst in sync.

    Geprueft wird in beide Richtungen: jeder Lock-Eintrag gegen seine Datei,
    und jede Datei im Verzeichnis gegen das Lock. Ohne die Gegenrichtung
    machte ein geloeschter Eintrag die Pruefung leiser statt lauter.
    """
    lock_path = root / LOCK_NAME
    if not lock_path.exists():
        return [f"{LOCK_NAME} fehlt -- ohne Lock ist nichts pruefbar"]
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{LOCK_NAME}: kein gueltiges JSON ({exc})"]

    found: list[str] = []
    if lock.get("do_not_edit") is not True:
        found.append(f"{LOCK_NAME}: do_not_edit ist nicht true")
    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        # Ohne Eintraege pruefte die Schleife null Dateien und meldete nichts.
        found.append(f"{LOCK_NAME}: keine Eintraege unter \"files\"")
        files = {}

    for relative, entry in sorted(files.items()):
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            found.append(f"{relative}: Lock-Eintrag ohne sha256")
            continue
        if entry.get("kind") != KIND:
            found.append(f"{relative}: unbekannte Art {entry.get('kind')!r}")
            continue
        if not relative.startswith(f"{VENDOR_DIR}/") or ".." in relative.split("/"):
            found.append(f"{relative}: Lock-Eintrag ausserhalb von {VENDOR_DIR}/")
            continue
        target = root / relative
        if not target.is_file():
            found.append(f"{relative}: Datei fehlt")
        elif file_sha256(target) != entry["sha256"]:
            found.append(f"{relative}: weicht vom Lock ab -- von Hand bearbeitet")

    vendor = root / VENDOR_DIR
    if not vendor.is_dir():
        found.append(f"{VENDOR_DIR}/ fehlt")
        return found
    for path in sorted(p for p in vendor.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative not in files:
            found.append(
                f"{relative}: kein Lock-Eintrag -- unter {VENDOR_DIR}/ liegt nur "
                "Erzeugtes; eigene Fixtures gehoeren woandershin")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="zu pruefendes Checkout (Vorgabe: dieses Repository)")
    root = parser.parse_args(argv).root.resolve()

    found = problems(root)
    for problem in found:
        print(f"FAIL {problem}")
    if found:
        print(f"{len(found)} Abweichung(en)")
        return 1
    count = len(json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))["files"])
    print(f"Kontrakt in sync ({count} Dateien geprueft)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
