"""Prueft, dass jede erzeugte Datei zu ihrem Eintrag in contract.lock.json passt.

Als pytest-Datei und als Skript (scripts/check_contract.py): Das Skript laesst
sich einzeln rufen, der Test laeuft bei jedem Testlauf mit.
"""

import importlib.util
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "check_contract", REPO_ROOT / "scripts" / "check_contract.py")
check_contract = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_contract)

VENDOR_DIR = check_contract.VENDOR_DIR
LOCK_NAME = check_contract.LOCK_NAME
SAMPLE = f"{VENDOR_DIR}/full.response.json"


def _clone(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / VENDOR_DIR, root / VENDOR_DIR)
    shutil.copy(REPO_ROOT / LOCK_NAME, root / LOCK_NAME)
    return root


def _lock(root: Path) -> dict:
    return json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))


def _write_lock(root: Path, lock: dict) -> None:
    (root / LOCK_NAME).write_text(json.dumps(lock), encoding="utf-8")


def _mentions(root: Path, needle: str) -> bool:
    return any(needle in problem for problem in check_contract.problems(root))


def test_repository_is_in_sync():
    assert check_contract.problems(REPO_ROOT) == []


def test_lock_names_every_vendored_file():
    assert len(_lock(REPO_ROOT)["files"]) == 35


def test_untouched_clone_is_in_sync(tmp_path):
    assert check_contract.problems(_clone(tmp_path)) == []


def test_line_endings_do_not_matter(tmp_path):
    root = _clone(tmp_path)
    target = root / SAMPLE
    target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert check_contract.problems(root) == []


def test_hand_edited_value_is_reported(tmp_path):
    root = _clone(tmp_path)
    target = root / SAMPLE
    target.write_bytes(target.read_bytes().replace(b"true", b"false", 1))
    assert _mentions(root, "full.response.json")


def test_deleted_file_is_reported(tmp_path):
    root = _clone(tmp_path)
    (root / SAMPLE).unlink()
    assert _mentions(root, "Datei fehlt")


def test_removed_lock_entry_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    del lock["files"][SAMPLE]
    _write_lock(root, lock)
    assert _mentions(root, "kein Lock-Eintrag")


def test_added_file_without_lock_entry_is_reported(tmp_path):
    root = _clone(tmp_path)
    (root / VENDOR_DIR / "eigenes.json").write_text("{}", encoding="utf-8")
    assert _mentions(root, "eigenes.json")


def test_empty_lock_is_reported_instead_of_silently_green(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["files"] = {}
    _write_lock(root, lock)
    assert _mentions(root, "keine Eintraege")


def test_lock_without_do_not_edit_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["do_not_edit"] = False
    _write_lock(root, lock)
    assert _mentions(root, "do_not_edit")


def test_unknown_kind_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["files"][SAMPLE]["kind"] = "etwas-anderes"
    _write_lock(root, lock)
    assert _mentions(root, "unbekannte Art")


def test_lock_entry_without_sha256_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    del lock["files"][SAMPLE]["sha256"]
    _write_lock(root, lock)
    assert _mentions(root, "ohne sha256")


def test_lock_entry_outside_the_vendor_directory_is_reported(tmp_path):
    root = _clone(tmp_path)
    lock = _lock(root)
    lock["files"]["custom_components/x.json"] = lock["files"][SAMPLE]
    _write_lock(root, lock)
    assert _mentions(root, "ausserhalb")


def test_missing_lock_is_reported(tmp_path):
    root = _clone(tmp_path)
    (root / LOCK_NAME).unlink()
    assert _mentions(root, "fehlt")


def test_cli_returns_zero_on_the_real_repository():
    assert check_contract.main(["--root", str(REPO_ROOT)]) == 0


def test_cli_returns_nonzero_on_problems(tmp_path):
    root = _clone(tmp_path)
    (root / SAMPLE).unlink()
    assert check_contract.main(["--root", str(root)]) == 1
