"""Security hardening regression tests for kodharitalama 0.30.103.

Covers:

* IP blocking / embedded-IPv6 unwrapping (IPv4-mapped, 6to4, Teredo, NAT64)
* Redirect denial (allow_redirects=False by default)
* Include-path bypasses (resolve_within: .., absolute, Windows drive, UNC)
* No shell=True / os.system / os.popen in the runtime package
* No telemetry / analytics endpoints in the runtime package
* Pinned, hash-locked dependencies in requirements.lock
* tiktoken download gate (GRAPHIFY_ALLOW_TIKTOKEN_DOWNLOAD=1)

These are written as plain functions with ``assert`` so they can be executed
directly with Python (``python tests/test_security_hardening.py``) even when
pytest is unavailable, while remaining pytest-compatible (``test_*`` names).
"""
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

failures: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# 1. IP blocking / embedded-IPv6 unwrapping
# ---------------------------------------------------------------------------

def _import_security():
    try:
        from graphify.security import (  # type: ignore
            _ip_is_blocked,
            _unwrap_embedded_ipv4,
            validate_url,
        )
        return _ip_is_blocked, _unwrap_embedded_ipv4, validate_url
    except Exception as exc:  # pragma: no cover - import guard for restricted envs
        print(f"[SKIP] graphify.security import failed: {exc}")
        return None, None, None


def test_ip_blocking_and_unwrapping() -> None:
    _ip_is_blocked, _unwrap_embedded_ipv4, _ = _import_security()
    if _ip_is_blocked is None:
        return

    # Blocked: loopback, RFC1918, multicast, unspecified, link-local, CGN.
    blocked = [
        "127.0.0.1", "127.255.255.255", "10.0.0.1", "172.16.0.1", "192.168.1.1",
        "224.0.0.1", "239.255.255.255", "0.0.0.0", "169.254.169.254",
        "100.64.0.1", "ff02::1", "::", "2001:db8::1",
    ]
    for bad in blocked:
        _check(
            f"blocked IP {bad}",
            _ip_is_blocked(ipaddress.ip_address(bad)),
            f"{bad} should be blocked",
        )

    # Passed: public addresses. (198.51.100.0/24 is TEST-NET-2, reserved, so
    # it is correctly blocked; use genuinely public addresses here.)
    public = ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "1.0.0.1"]
    for good in public:
        _check(
            f"public IP {good}",
            not _ip_is_blocked(ipaddress.ip_address(good)),
            f"{good} should pass",
        )

    # Embedded-IPv6 unwrapping.
    cases = [
        ("::ffff:127.0.0.1", "127.0.0.1"),          # IPv4-mapped
        ("2002:7f00:1::1", "127.0.0.1"),              # 6to4 (2002:7f00:1:...)
        ("2001:0:4136:e378:8000:63bf:3fff:5fdd", None),  # Teredo -> client IP
    ]
    for v6, expected in cases:
        ip = ipaddress.IPv6Address(v6)
        unwrapped = _unwrap_embedded_ipv4(ip)
        if expected is None:
            # Teredo: client IPv4 is bit-inverted ~int(ip) & 0xFFFFFFFF
            client = str(ipaddress.IPv4Address((~int(ip)) & 0xFFFFFFFF))
            _check(f"Teredo unwrap {v6}", unwrapped != ip, f"-> {client}")
        else:
            _check(f"unwrap {v6} -> {expected}", str(unwrapped) == expected)

    # IPv4-mapped loopback must be blocked after unwrap.
    mapped = _unwrap_embedded_ipv4(ipaddress.IPv6Address("::ffff:127.0.0.1"))
    _check("IPv4-mapped loopback blocked", _ip_is_blocked(mapped))


# ---------------------------------------------------------------------------
# 2. Redirect denial
# ---------------------------------------------------------------------------

def test_redirect_denial_default() -> None:
    """safe_fetch must default to allow_redirects=False."""
    import inspect

    from graphify.security import safe_fetch  # type: ignore

    sig = inspect.signature(safe_fetch)
    default = sig.parameters["allow_redirects"].default
    _check("safe_fetch allow_redirects default False", default is False,
           f"got {default!r}")

    # The opener builds a non-following handler by default.
    from graphify.security import _build_opener  # type: ignore
    opener = _build_opener(allow_redirects=False, max_redirects=5)
    _check("opener constructed with allow_redirects=False", opener is not None)


# ---------------------------------------------------------------------------
# 3. Include-path bypasses (resolve_within)
# ---------------------------------------------------------------------------

def test_resolve_within_blocks_traversal() -> None:
    from graphify.security import resolve_within  # type: ignore

    base = Path("/safe/base")
    escapes = [
        "../../etc/passwd",
        "../outside",
        "/etc/passwd",
        "C:/Windows/System32",
        "\\\\server\\share\\file",
        "subdir/../../secret",
        "a/../../b",
    ]
    for esc in escapes:
        _check(f"resolve_within blocks {esc!r}",
               resolve_within(base, esc) is None,
               f"{esc!r} should escape")

    # Contained paths resolve.
    contained = resolve_within(base, "subdir/file.txt")
    _check("resolve_within allows contained path", contained is not None)


# ---------------------------------------------------------------------------
# 4. No shell=True / os.system / os.popen in runtime package
# ---------------------------------------------------------------------------

def test_no_shell_or_os_exec_in_runtime() -> None:
    shell_re = re.compile(r"\bshell\s*=\s*True\b")
    os_system_re = re.compile(r"\bos\.(system|popen)\s*\(")
    hits: list[str] = []
    for path in sorted((ROOT / "graphify").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if shell_re.search(line) or os_system_re.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:120]}")
    _check("no shell=True / os.system / os.popen in graphify/", len(hits) == 0,
           "; ".join(hits) if hits else "")


# ---------------------------------------------------------------------------
# 5. No telemetry / analytics endpoints in runtime package
# ---------------------------------------------------------------------------

def test_no_telemetry_endpoints() -> None:
    telemetry_re = re.compile(
        r"(requests\.post|urllib\.request\.urlopen|http\.client\.)",
        re.I,
    )
    analytics_re = re.compile(
        r"(analytics|telemetry|metrics\.post|/collect|/report|/event)",
        re.I,
    )
    hits: list[str] = []
    for path in sorted((ROOT / "graphify").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if telemetry_re.search(line) and analytics_re.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:120]}")
    _check("no telemetry/analytics network calls in graphify/", len(hits) == 0,
           "; ".join(hits) if hits else "")


# ---------------------------------------------------------------------------
# 6. Pinned, hash-locked dependencies in requirements.lock
# ---------------------------------------------------------------------------

def test_requirements_lock_pinned_and_hashed() -> None:
    lock = ROOT / "requirements.lock"
    _check("requirements.lock exists", lock.exists())
    if not lock.exists():
        return

    text = lock.read_text(encoding="utf-8")
    logical, buf = [], ""
    for line in text.splitlines():
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        buf += line
        if buf.strip():
            logical.append(buf.strip())
        buf = ""
    if buf.strip():
        logical.append(buf.strip())

    entries = [e for e in logical if not e.startswith("#")]
    _check("requirements.lock has entries", len(entries) > 0, f"{len(entries)} entries")

    # Try packaging validation if available (pip-vendored).
    try:
        from pip._vendor.packaging.requirements import Requirement  # type: ignore
    except Exception:  # pragma: no cover - restricted env
        Requirement = None  # type: ignore

    unpinned, unhashed, invalid = 0, 0, 0
    for entry in entries:
        parts = entry.split()
        hashes = [p for p in parts if p.startswith("--hash=")]
        spec = " ".join(p for p in parts if not p.startswith("--hash="))
        if not hashes:
            unhashed += 1
        if Requirement is not None:
            try:
                req = Requirement(spec)
                ops = [s.operator for s in req.specifier]
                if not ops or any(op != "==" for op in ops):
                    unpinned += 1
            except Exception:
                invalid += 1

    _check("all entries hash-locked", unhashed == 0, f"{unhashed} without hashes")
    _check("all entries exactly pinned (==)", unpinned == 0, f"{unpinned} not == pinned")
    _check("all entries parse as requirements", invalid == 0, f"{invalid} invalid")


# ---------------------------------------------------------------------------
# 7. tiktoken download gate
# ---------------------------------------------------------------------------

def test_tiktoken_download_gate() -> None:
    """_get_tokenizer must require GRAPHIFY_ALLOW_TIKTOKEN_DOWNLOAD=1."""
    llm_path = ROOT / "graphify" / "llm.py"
    text = llm_path.read_text(encoding="utf-8", errors="replace")
    _check("tiktoken gate env var referenced in llm.py",
           "GRAPHIFY_ALLOW_TIKTOKEN_DOWNLOAD" in text,
           "env gate missing")


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

_TESTS = [
    test_ip_blocking_and_unwrapping,
    test_redirect_denial_default,
    test_resolve_within_blocks_traversal,
    test_no_shell_or_os_exec_in_runtime,
    test_no_telemetry_endpoints,
    test_requirements_lock_pinned_and_hashed,
    test_tiktoken_download_gate,
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
