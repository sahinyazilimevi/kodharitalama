#!/usr/bin/env python3
"""Install kodharitalama skills into a project for Claude Code, OpenCode and Antigravity.

The installer is deliberately local and boring:

* it copies files from this checkout only (no network access);
* it never writes outside ``--dest``;
* it records every file and merged instruction section in a manifest so
  ``--uninstall`` can remove exactly what it installed;
* it refuses to overwrite unmanaged or locally modified files unless
  ``--force`` is given.

Usage
-----
    python tools/install_skills.py --ide all --dest .
    python tools/install_skills.py --ide claude-code --dest .
    python tools/install_skills.py --check --dest .
    python tools/install_skills.py --uninstall --ide opencode --dest .

Run ``python tools/install_skills.py --list`` for the source/target matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REL = Path(".kodharitalama") / "skills-manifest.json"
SCHEMA_VERSION = 1
PRODUCT = "kodharitalama"
SECTION_BEGIN = "<!-- kodharitalama:begin -->"
SECTION_END = "<!-- kodharitalama:end -->"

IDE_CONFIG: dict[str, dict[str, Any]] = {
    "claude-code": {
        "label": "Claude Code",
        "skill_source": Path("graphify") / "skill.md",
        "refs_source": Path("graphify") / "skills" / "claude" / "references",
        "skill_target": Path(".claude") / "skills" / "kodharitalama" / "SKILL.md",
        "instruction_target": Path(".claude") / "CLAUDE.md",
        "instruction_template": Path("integrations") / "claude-code" / "CLAUDE.section.md",
        "extra_files": [],
    },
    "opencode": {
        "label": "OpenCode",
        "skill_source": Path("graphify") / "skill-opencode.md",
        "refs_source": Path("graphify") / "skills" / "opencode" / "references",
        "skill_target": Path(".opencode") / "skills" / "kodharitalama" / "SKILL.md",
        "instruction_target": Path("AGENTS.md"),
        "instruction_template": Path("integrations") / "opencode" / "AGENTS.section.md",
        "extra_files": [],
    },
    "antigravity": {
        "label": "Antigravity IDE",
        "skill_source": Path("graphify") / "skill.md",
        "refs_source": Path("graphify") / "skills" / "claude" / "references",
        "skill_target": Path(".agents") / "skills" / "kodharitalama" / "SKILL.md",
        "instruction_target": None,
        "instruction_template": None,
        "extra_files": [
            (Path("integrations") / "antigravity" / "rules.md", Path(".agents") / "rules" / "kodharitalama.md"),
            (Path("integrations") / "antigravity" / "workflow.md", Path(".agents") / "workflows" / "kodharitalama.md"),
        ],
    },
}


class InstallError(RuntimeError):
    """A user-actionable installation error."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_version() -> str:
    pyproject = SOURCE_ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise InstallError(f"could not read the version from {pyproject}")
    return match.group(1)


def _contained(dest_root: Path, relative: Path) -> Path:
    """Resolve *relative* under *dest_root* and reject path escapes."""
    if relative.is_absolute():
        raise InstallError(f"absolute paths are not allowed: {relative}")
    target = (dest_root / relative).resolve()
    root = dest_root.resolve()
    try:
        common = Path(os.path.commonpath([str(root), str(target)]))
    except ValueError as exc:  # different Windows drives
        raise InstallError(f"path escapes the destination: {relative}") from exc
    if common != root:
        raise InstallError(f"path escapes the destination: {relative}")
    return target


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rewrite_frontmatter(text: str) -> str:
    """Give the skill the branded name while keeping its packaged body intact."""
    if not text.startswith("---\n"):
        return (
            "---\n"
            f"name: {PRODUCT}\n"
            "description: Build and query a local code knowledge graph.\n"
            "---\n\n" + text
        )
    head, sep, tail = text[3:].partition("\n---\n")
    if not sep:
        return text
    head = re.sub(r"^name:\s*.*$", f"name: {PRODUCT}", head, count=1, flags=re.MULTILINE)
    if not re.search(r"^name:\s*", head, flags=re.MULTILINE):
        head = f"name: {PRODUCT}\n" + head
    return "---\n" + head + "\n---\n" + tail


def _load_manifest(dest_root: Path) -> dict[str, Any]:
    path = _contained(dest_root, MANIFEST_REL)
    if not path.exists():
        return {"schema": SCHEMA_VERSION, "product": PRODUCT, "version": _read_version(), "ides": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"cannot read manifest {path}: {exc}") from exc
    if data.get("product") != PRODUCT or data.get("schema") != SCHEMA_VERSION:
        raise InstallError(f"unexpected manifest format in {path}")
    if not isinstance(data.get("ides"), dict):
        raise InstallError(f"unexpected manifest format in {path}")
    return data


def _save_manifest(dest_root: Path, manifest: dict[str, Any]) -> None:
    path = _contained(dest_root, MANIFEST_REL)
    manifest["version"] = _read_version()
    payload = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _write_atomic(path, payload.encode("utf-8"))


def _planned_files(ide: str, dest_root: Path) -> dict[Path, bytes]:
    """Return every file the given IDE needs, keyed by destination path."""
    cfg = IDE_CONFIG[ide]
    files: dict[Path, bytes] = {}

    skill_src = SOURCE_ROOT / cfg["skill_source"]
    if not skill_src.is_file():
        raise InstallError(f"missing packaged skill: {skill_src}")
    skill_text = _rewrite_frontmatter(_read_text(skill_src))
    if f"name: {PRODUCT}" not in skill_text.split("---", 2)[1]:
        raise InstallError(f"could not set the skill name in {skill_src}")
    files[_contained(dest_root, cfg["skill_target"])] = skill_text.encode("utf-8")

    refs_src = SOURCE_ROOT / cfg["refs_source"]
    if not refs_src.is_dir():
        raise InstallError(f"missing packaged references: {refs_src}")
    root = dest_root.resolve()
    refs_dir = _contained(dest_root, cfg["skill_target"]).parent / "references"
    for source in sorted(refs_src.rglob("*")):
        if source.is_dir():
            continue
        if source.is_symlink():
            raise InstallError(f"refusing to install a symlinked reference: {source}")
        relative = source.relative_to(refs_src)
        files[_contained(dest_root, refs_dir.relative_to(root) / relative)] = source.read_bytes()

    for source_rel, target_rel in cfg["extra_files"]:
        source = SOURCE_ROOT / source_rel
        if not source.is_file():
            raise InstallError(f"missing template: {source}")
        files[_contained(dest_root, target_rel)] = source.read_bytes()

    return files


def _section_for(ide: str) -> str | None:
    path = IDE_CONFIG[ide]["instruction_template"]
    if path is None:
        return None
    return _read_text(SOURCE_ROOT / path)


def _merge_section(existing: str, section: str) -> str:
    """Replace our marked section in place, or append it once."""
    pattern = re.compile(
        re.escape(SECTION_BEGIN) + r".*?" + re.escape(SECTION_END),
        flags=re.DOTALL,
    )
    if pattern.search(existing):
        return pattern.sub(lambda _match: section.rstrip(), existing, count=1).rstrip() + "\n"
    body = existing.rstrip()
    if body:
        return body + "\n\n" + section.rstrip() + "\n"
    return section.rstrip() + "\n"


def _remove_section(existing: str) -> tuple[str, bool]:
    pattern = re.compile(
        r"\n*" + re.escape(SECTION_BEGIN) + r".*?" + re.escape(SECTION_END) + r"\n*",
        flags=re.DOTALL,
    )
    if not pattern.search(existing):
        return existing, False
    cleaned = pattern.sub("\n\n", existing, count=1)
    return cleaned.strip() + "\n" if cleaned.strip() else "", True


def _install_ide(ide: str, dest_root: Path, manifest: dict[str, Any], force: bool, dry_run: bool) -> None:
    cfg = IDE_CONFIG[ide]
    old_entry = manifest["ides"].get(ide, {})
    old_files: dict[str, str] = old_entry.get("files", {})
    planned = _planned_files(ide, dest_root)

    for target, data in planned.items():
        relative = str(target.relative_to(dest_root.resolve())).replace("\\", "/")
        old_hash = old_files.get(relative)
        if target.exists():
            current = target.read_bytes()
            if old_hash is None and not force:
                raise InstallError(
                    f"{relative} already exists and is not managed by kodharitalama; "
                    "re-run with --force only after checking it"
                )
            if old_hash is not None and _sha256(current) != old_hash and not force:
                raise InstallError(
                    f"{relative} was modified after installation; re-run with --force to overwrite"
                )
        if not dry_run:
            _write_atomic(target, data)

    # Drop stale reference files from a previous managed install.
    refs_dir = _contained(dest_root, cfg["skill_target"]).parent / "references"
    for relative in list(old_files):
        old_path = _contained(dest_root, Path(relative))
        if old_path.is_file() and refs_dir in old_path.parents and old_path not in planned:
            if not dry_run:
                old_path.unlink()
            old_files.pop(relative, None)

    section_record = None
    section = _section_for(ide)
    if section is not None and cfg["instruction_target"] is not None:
        instruction = _contained(dest_root, cfg["instruction_target"])
        existing = _read_text(instruction) if instruction.exists() else ""
        merged = _merge_section(existing, section)
        if not dry_run and merged != existing:
            _write_atomic(instruction, merged.encode("utf-8"))
        section_record = {"path": str(cfg["instruction_target"]).replace("\\", "/"), "marker": PRODUCT}

    files = {str(path.relative_to(dest_root.resolve())).replace("\\", "/"): _sha256(data) for path, data in planned.items()}
    manifest["ides"][ide] = {
        "label": cfg["label"],
        "files": files,
        "sections": [section_record] if section_record else [],
    }


def _uninstall_ide(ide: str, dest_root: Path, manifest: dict[str, Any], force: bool, dry_run: bool) -> None:
    entry = manifest["ides"].get(ide)
    if entry is None:
        print(f"{IDE_CONFIG[ide]['label']}: not installed in this project")
        return

    for relative, recorded_hash in entry.get("files", {}).items():
        path = _contained(dest_root, Path(relative))
        if not path.is_file():
            continue
        if not force and _sha256(path.read_bytes()) != recorded_hash:
            raise InstallError(
                f"{relative} was modified after installation; re-run with --force to remove it"
            )
        if not dry_run:
            path.unlink()

    for section in entry.get("sections", []):
        path = _contained(dest_root, Path(section["path"]))
        if not path.is_file():
            continue
        cleaned, removed = _remove_section(_read_text(path))
        if removed and not dry_run:
            if cleaned:
                _write_atomic(path, cleaned.encode("utf-8"))
            else:
                path.unlink()

    if not dry_run:
        manifest["ides"].pop(ide, None)
        _prune_empty_dirs(dest_root, entry.get("files", {}))


def _prune_empty_dirs(dest_root: Path, files: dict[str, str]) -> None:
    root = dest_root.resolve()
    directories = {(_contained(dest_root, Path(relative))).parent for relative in files}
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        current = directory
        while current != root and root in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


def _check(dest_root: Path, manifest: dict[str, Any]) -> int:
    failures: list[str] = []
    for ide, entry in sorted(manifest["ides"].items()):
        if ide not in IDE_CONFIG:
            failures.append(f"{ide}: entry from a newer installer")
            continue
        try:
            planned = _planned_files(ide, dest_root)
        except InstallError as exc:
            failures.append(f"{ide}: {exc}")
            continue
        expected = {
            str(path.relative_to(dest_root.resolve())).replace("\\", "/"): _sha256(data)
            for path, data in planned.items()
        }
        for relative, digest in expected.items():
            path = _contained(dest_root, Path(relative))
            if not path.is_file():
                failures.append(f"{relative}: missing")
            elif _sha256(path.read_bytes()) != digest:
                failures.append(f"{relative}: differs from the packaged source")
        for section in entry.get("sections", []):
            path = _contained(dest_root, Path(section["path"]))
            if not path.is_file() or SECTION_BEGIN not in _read_text(path):
                failures.append(f"{section['path']}: instruction section missing")
    if failures:
        print("kodharitalama skills are out of date:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("kodharitalama skills are up to date.")
    return 0


def _print_list() -> None:
    print(f"{PRODUCT} skill targets\n")
    for ide, cfg in IDE_CONFIG.items():
        print(f"{ide}  ({cfg['label']})")
        print(f"  skill      {cfg['skill_target']}")
        if cfg["instruction_target"] is not None:
            print(f"  rules      {cfg['instruction_target']}")
        for _source, target in cfg["extra_files"]:
            print(f"  always-on  {target}")
        print(f"  source     {cfg['skill_source']} + {cfg['refs_source']}")
        print()


def _parse_ides(values: list[str]) -> list[str]:
    selected: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if part == "all":
                selected = list(IDE_CONFIG)
                continue
            if part not in IDE_CONFIG:
                raise InstallError(f"unknown IDE '{part}'. Choose from: {', '.join(IDE_CONFIG)} or all")
            if part not in selected:
                selected.append(part)
    if not selected:
        raise InstallError("select at least one IDE with --ide (or --ide all)")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install kodharitalama skills into a project for Claude Code, OpenCode and Antigravity IDE."
    )
    parser.add_argument("--ide", action="append", default=[], metavar="NAME",
                        help="claude-code, opencode, antigravity, a comma-separated list, or all")
    parser.add_argument("--dest", default=".", help="project directory (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    parser.add_argument("--force", action="store_true", help="overwrite or remove locally modified files")
    parser.add_argument("--uninstall", action="store_true", help="remove only files recorded in the manifest")
    parser.add_argument("--check", action="store_true", help="verify installed files against the packaged sources")
    parser.add_argument("--list", action="store_true", help="list IDE source and target paths")
    args = parser.parse_args(argv)

    if args.list:
        _print_list()
        return 0

    dest_root = Path(args.dest).expanduser()
    if not dest_root.exists():
        if args.dry_run or args.check or args.uninstall:
            raise InstallError(f"destination does not exist: {dest_root}")
        dest_root.mkdir(parents=True)

    try:
        manifest = _load_manifest(dest_root)
        if args.check:
            if not manifest["ides"]:
                print("no kodharitalama skill installation found in this project")
                return 1
            return _check(dest_root, manifest)

        ides = _parse_ides(args.ide)
        if args.uninstall:
            for ide in ides:
                _uninstall_ide(ide, dest_root, manifest, args.force, args.dry_run)
            if not args.dry_run:
                if manifest["ides"]:
                    _save_manifest(dest_root, manifest)
                else:
                    manifest_path = _contained(dest_root, MANIFEST_REL)
                    if manifest_path.exists():
                        manifest_path.unlink()
                    try:
                        manifest_path.parent.rmdir()
                    except OSError:
                        pass
            print("Uninstall complete." if not args.dry_run else "Dry run complete; nothing was removed.")
            return 0

        for ide in ides:
            _install_ide(ide, dest_root, manifest, args.force, args.dry_run)
        if not args.dry_run:
            _save_manifest(dest_root, manifest)
        summary = ", ".join(IDE_CONFIG[ide]["label"] for ide in ides)
        print(f"{'Would install' if args.dry_run else 'Installed'} {PRODUCT} for: {summary}")
        print(f"Project: {dest_root.resolve()}")
        print("Next: run `kodharitalama --help` (or `python -m graphify --help`) and build a graph with `kodharitalama .`.")
        return 0
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
