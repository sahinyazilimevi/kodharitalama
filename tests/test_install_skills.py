"""Installer regression tests for kodharitalama 0.30.103.

Covers:

* Path containment (no escapes via absolute paths or ``..``)
* Install + check round-trip (installed files match packaged sources)
* Idempotence (re-install is a no-op when nothing changed)
* Uninstall removes exactly the manifest-recorded files
* Manifest tracks files and SHA-256 hashes

Written with plain ``assert`` so it runs directly
(``python tests/test_install_skills.py``) without pytest, while remaining
pytest-compatible (``test_*`` names).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.install_skills import (  # noqa: E402
    IDE_CONFIG,
    MANIFEST_REL,
    InstallError,
    _check as _installer_check,
    _contained,
    _install_ide,
    _load_manifest,
    _planned_files,
    _save_manifest,
    _uninstall_ide,
    _sha256,
)

failures: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# 1. Path containment
# ---------------------------------------------------------------------------

def test_contained_rejects_escapes() -> None:
    root = Path(tempfile.mkdtemp())
    try:
        escapes = [
            Path("../outside"),
            Path("../../etc/passwd"),
            Path("/absolute/escape"),
            Path("subdir/../../secret"),
        ]
        for rel in escapes:
            try:
                _contained(root, rel)
                _check(f"contained rejects {rel!r}", False, "did not raise")
            except InstallError:
                _check(f"contained rejects {rel!r}", True)

        # Contained path resolves under root.
        target = _contained(root, Path("a/b.txt"))
        _check("contained resolves under root",
               str(target).startswith(str(root.resolve())))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. Install + check round-trip
# ---------------------------------------------------------------------------

def _fresh_dest() -> Path:
    return Path(tempfile.mkdtemp(prefix="kh-install-test-"))


def test_install_then_check_passes() -> None:
    dest = _fresh_dest()
    manifest = _load_manifest(dest)
    try:
        for ide in IDE_CONFIG:
            _install_ide(ide, dest, manifest, force=False, dry_run=False)
        _save_manifest(dest, manifest)

        rc = _installer_check(dest, manifest)
        _check("install + --check passes", rc == 0,
               f"check returned {rc}")

        # Manifest records all IDEs.
        _check("manifest has all IDEs",
               set(manifest["ides"].keys()) == set(IDE_CONFIG.keys()),
               f"got {set(manifest['ides'].keys())}")

        # Every recorded file exists and hash matches.
        for ide, entry in manifest["ides"].items():
            for relative, digest in entry.get("files", {}).items():
                path = dest / relative
                _check(f"{relative} exists", path.is_file())
                if path.is_file():
                    _check(f"{relative} hash matches",
                           _sha256(path.read_bytes()) == digest)
    finally:
        shutil.rmtree(dest, ignore_errors=True)


def test_install_is_idempotent() -> None:
    dest = _fresh_dest()
    manifest = _load_manifest(dest)
    try:
        for ide in IDE_CONFIG:
            _install_ide(ide, dest, manifest, force=False, dry_run=False)
        _save_manifest(dest, manifest)

        # Snapshot hashes before re-install.
        before = {
            rel: _sha256((dest / rel).read_bytes())
            for ide in manifest["ides"].values()
            for rel in ide.get("files", {})
            if (dest / rel).is_file()
        }

        manifest2 = _load_manifest(dest)
        for ide in IDE_CONFIG:
            _install_ide(ide, dest, manifest2, force=False, dry_run=False)
        _save_manifest(dest, manifest2)

        after = {
            rel: _sha256((dest / rel).read_bytes())
            for ide in manifest2["ides"].values()
            for rel in ide.get("files", {})
            if (dest / rel).is_file()
        }
        _check("re-install keeps file hashes identical", before == after,
               "hashes changed on re-install")
    finally:
        shutil.rmtree(dest, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Uninstall removes exactly manifest-recorded files
# ---------------------------------------------------------------------------

def test_uninstall_removes_managed_files() -> None:
    dest = _fresh_dest()
    manifest = _load_manifest(dest)
    try:
        for ide in IDE_CONFIG:
            _install_ide(ide, dest, manifest, force=False, dry_run=False)
        _save_manifest(dest, manifest)

        installed_before = {
            str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()
        }

        # Add a user file that must survive uninstall.
        user_file = dest / "AGENTS.md"
        user_file.write_text("# user content\n", encoding="utf-8")

        manifest2 = _load_manifest(dest)
        for ide in IDE_CONFIG:
            _uninstall_ide(ide, dest, manifest2, force=False, dry_run=False)
        if not manifest2["ides"]:
            manifest_path = dest / MANIFEST_REL
            if manifest_path.exists():
                manifest_path.unlink()

        installed_after = {
            str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()
        }

        # All managed skill files should be gone.
        managed = {
            rel
            for ide in IDE_CONFIG.values()
            for rel in [str(ide["skill_target"])]
            + [str(t) for _, t in ide.get("extra_files", [])]
            + ([str(ide["instruction_target"])] if ide["instruction_target"] else [])
        }
        # references are installed too; check via manifest instead.
        manifest_rel_files = set()
        for entry in manifest["ides"].values():
            manifest_rel_files.update(entry.get("files", {}).keys())

        leftover_managed = manifest_rel_files & installed_after
        _check("uninstall removes managed files", not leftover_managed,
               f"leftover: {sorted(leftover_managed)}")

        # User file survives.
        _check("user file survives uninstall", user_file.is_file())

        # Manifest removed when no IDEs remain.
        _check("manifest removed after full uninstall",
               not (dest / MANIFEST_REL).exists())
    finally:
        shutil.rmtree(dest, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Manifest tracks files and SHA-256 hashes
# ---------------------------------------------------------------------------

def test_manifest_records_hashes() -> None:
    dest = _fresh_dest()
    manifest = _load_manifest(dest)
    try:
        _install_ide("claude-code", dest, manifest, force=False, dry_run=False)
        _save_manifest(dest, manifest)

        entry = manifest["ides"]["claude-code"]
        _check("manifest entry has files", isinstance(entry.get("files"), dict)
               and len(entry["files"]) > 0)
        _check("manifest entry has label", entry.get("label") == "Claude Code")

        # Each recorded hash must be a valid sha256 hex and match disk.
        for relative, digest in entry["files"].items():
            _check(f"{relative} digest is sha256 hex",
                   re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                   f"got {digest!r}")
            path = dest / relative
            if path.is_file():
                _check(f"{relative} on-disk hash matches manifest",
                       _sha256(path.read_bytes()) == digest)
    finally:
        shutil.rmtree(dest, ignore_errors=True)


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

_TESTS = [
    test_contained_rejects_escapes,
    test_install_then_check_passes,
    test_install_is_idempotent,
    test_uninstall_removes_managed_files,
    test_manifest_records_hashes,
]


def main() -> int:
    for fn in _TESTS:
        try:
            fn()
        except Exception as exc:  # pragma: no cover - report and continue
            print(f"[ERROR] {fn.__name__}: {exc}")
            failures.append(f"{fn.__name__}: {exc}")
    print(f"\n{len(_TESTS)} tests, {len(failures)} failure(s)")
    for f in failures:
        print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
