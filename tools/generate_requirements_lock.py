"""Generate requirements.lock from uv.lock (hash-locked default runtime set).

Usage:
    python tools/generate_requirements_lock.py

The generated file contains every package in the default (non-extra) runtime
closure, pinned to the version resolved in uv.lock and carrying the SHA-256
hash of every published sdist and wheel. This lets an offline/reviewed install
run with:

    python -m pip install --require-hashes --no-deps -r requirements.lock

The project itself is installed afterwards from the local checkout:

    python -m pip install --no-deps -e .
"""
from __future__ import annotations

import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "uv.lock"
OUT = ROOT / "requirements.lock"


def _and(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return f"({left}) and ({right})"


def _or(markers: list[str]) -> str | None:
    unique = list(dict.fromkeys(m for m in markers if m))
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]
    return " or ".join(f"({m})" if " or " in m else m for m in unique)


def _resolution_marker(pkg: dict) -> str | None:
    return _or(pkg.get("resolution-markers", []))


def main() -> int:
    data = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    packages = data["package"]
    by_name: dict[str, list[dict]] = defaultdict(list)
    by_key: dict[tuple[str, str], dict] = {}
    for pkg in packages:
        by_name[pkg["name"]].append(pkg)
        if "version" in pkg:
            by_key[(pkg["name"], pkg["version"])] = pkg

    root = next(
        (p for p in packages if p["name"] in ("graphifyy", "kodharitalama")), None
    )
    if root is None:
        print("uv.lock has no graphifyy/kodharitalama root package", file=sys.stderr)
        return 1

    # (name, version-or-None) -> set of environment markers under which the
    # package is reachable from the default dependency set.
    reachable: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    queue: list[tuple[dict, str | None]] = [
        (dep, dep.get("marker")) for dep in root.get("dependencies", [])
    ]

    while queue:
        dep, parent_marker = queue.pop(0)
        name = dep["name"]
        version = dep.get("version")
        candidates = (
            [by_key[(name, version)]]
            if version and (name, version) in by_key
            else by_name.get(name, [])
        )
        if not candidates:
            print(f"warning: unresolved dependency {name!r}", file=sys.stderr)
            continue

        for pkg in candidates:
            marker = _and(parent_marker, _resolution_marker(pkg))
            key = (pkg["name"], pkg.get("version"))
            if marker in reachable[key]:
                continue
            reachable[key].add(marker)
            for child in pkg.get("dependencies", []):
                child_marker = _and(marker, child.get("marker"))
                queue.append((child, child_marker))

    lines = [
        "# Auto-generated from uv.lock by tools/generate_requirements_lock.py.",
        "# Do not edit by hand.",
        "#",
        "# Default runtime dependency closure only (no optional extras).",
        "# Install with:",
        "#   python -m pip install --require-hashes --no-deps -r requirements.lock",
        "#   python -m pip install --no-deps -e .",
        "",
    ]

    pinned = 0
    warnings: list[str] = []
    for (name, version), markers in sorted(
        reachable.items(), key=lambda item: (item[0][0], item[0][1] or "")
    ):
        pkg = by_key.get((name, version)) if version else None
        if pkg is None:
            warnings.append(f"{name}: no locked package entry")
            continue

        hashes: list[str] = []
        sdist = pkg.get("sdist")
        if sdist and sdist.get("hash"):
            hashes.append(sdist["hash"])
        for wheel in pkg.get("wheels", []):
            if wheel.get("hash"):
                hashes.append(wheel["hash"])
        hashes = list(dict.fromkeys(hashes))
        if not hashes:
            warnings.append(f"{name}=={version}: no hashes in uv.lock")
            continue

        env_marker = _or(list(markers))
        spec = f"{name}=={version}"
        if env_marker:
            spec += f"; {env_marker}"
        body = " \\\n    ".join(f"--hash={h}" for h in hashes)
        lines.append(f"{spec} \\\n    {body}")
        pinned += 1

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {pinned} pinned distributions")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
