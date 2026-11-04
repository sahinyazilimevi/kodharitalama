"""Scan instruction files for prompt-injection / supply-chain red flags.

Read-only. Usage:  python tools/scan_untrusted_docs.py [repo-root]

Exits 1 when a red flag is found, so it can be used as a check.

The scanner intentionally ignores generated IDE copies (``.claude/``,
``.opencode/``, ``.agents/``) and virtual environments: it checks the packaged
skill sources, integration templates, and repository documentation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Directories that contain generated copies or third-party material.
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules",
    ".claude", ".opencode", ".agents", ".kodharitalama", "graphify-out",
    "audit", "build", "dist",
}

# Lines that explicitly warn against an action are not findings.
NEGATION = re.compile(r"\b(?:do\s+not|don't|never|avoid|must\s+not)\b", re.I)
LOCKED_INSTALL = re.compile(r"--require-hashes|--no-deps\s+-e\s+\.|--no-build-isolation")

PATTERNS = {
    "shell-download-exec": re.compile(r"(?:curl|wget)\s+[^\n|]*\|\s*(?:ba|z|da)?sh", re.I),
    # Installing the product from a package index or a remote URL.
    "untrusted-package-install": re.compile(
        r"\b(?:pip|pip3|uv|uvx)\s+(?:install|add)\b[^\n]*?\b(?:graphifyy|graphify)\b",
        re.I,
    ),
    # Fetching a skill or installer from a remote source.
    "remote-skill-fetch": re.compile(
        r"(?:curl|wget|invoke-webrequest|iwr)\b[^\n]*?(?:SKILL\.md|skill\.md|install\.sh|install\.ps1)",
        re.I,
    ),
    "ignore-instructions": re.compile(
        r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+(?:instructions|prompts?)",
        re.I,
    ),
    "secret-path": re.compile(r"(?:\.ssh/|\.aws/|id_rsa|credentials\.json)", re.I),
    "exfiltration": re.compile(r"\b(?:exfiltrat|upload\s+to|post\s+to\s+https?://)", re.I),
    "destructive": re.compile(r"\brm\s+-rf\s+[/~]", re.I),
    "encoded-payload": re.compile(r"base64\s+(?:-d|--decode)", re.I),
    "auto-approve": re.compile(
        r"--dangerously-skip-permissions|--yes\s+--no-confirm|auto[_-]?approve", re.I
    ),
}


def _skipped(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part in SKIP_DIRS for part in relative.parts)


def scan(root: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml", ".skill"}:
            continue
        if _skipped(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pattern in PATTERNS.items():
                if not pattern.search(line):
                    continue
                if name == "untrusted-package-install" and (
                    NEGATION.search(line) or LOCKED_INSTALL.search(line)
                ):
                    continue
                findings.append((path, lineno, name, line.strip()[:200]))
    return findings


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    findings = scan(root)
    for path, lineno, name, line in findings:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"{rel}:{lineno}: [{name}] {line}")
    print(f"\n{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
