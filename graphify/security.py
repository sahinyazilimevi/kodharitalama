# Security helpers - URL validation, safe fetch, path guards, label sanitisation
from __future__ import annotations

import html
import http.client
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import ipaddress
import socket

from graphify.paths import GRAPHIFY_OUT, GRAPHIFY_OUT_NAME

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_FETCH_BYTES = 52_428_800   # 50 MB hard cap for binary downloads
_MAX_TEXT_BYTES  = 10_485_760   # 10 MB hard cap for HTML / text

# Graph-load memory-bomb cap: reject .json files larger than this before
# JSON-parsing them into a dict. Without this, a multi-gigabyte (or
# specifically crafted) graph.json can exhaust process memory during
# json.loads + node_link_graph rehydration.
# Default fallback cap. Kept as a module-level constant so the value is
# discoverable and so existing callers/tests that reference it directly keep
# working; the effective cap is resolved at call time by
# ``_max_graph_file_bytes`` (which lets ``GRAPHIFY_MAX_GRAPH_BYTES`` override it).
_MAX_GRAPH_FILE_BYTES = 512 * 1024 * 1024   # 512 MiB


def _max_graph_file_bytes() -> int:
    """Return the graph.json size cap in bytes.

    Honors the ``GRAPHIFY_MAX_GRAPH_BYTES`` environment variable so users with
    large codebases can raise the limit without editing source. The value may
    be plain bytes (``671088640``) or carry an ``MB`` / ``GB`` suffix
    (``640MB``, ``2GB`` — case-insensitive, binary multipliers: ``MB`` is
    1024*1024 and ``GB`` is 1024*1024*1024, i.e. MiB / GiB).
    Falls back to ``_MAX_GRAPH_FILE_BYTES`` (512 MiB) when the env var is unset,
    blank, or unparseable.

    Read fresh on every call so the env var can be set before import and still
    take effect.
    """
    raw = os.environ.get("GRAPHIFY_MAX_GRAPH_BYTES", "").strip()
    if not raw:
        return _MAX_GRAPH_FILE_BYTES
    text = raw.upper()
    multiplier = 1
    if text.endswith("GB"):
        multiplier = 1024 * 1024 * 1024
        text = text[:-2].strip()
    elif text.endswith("MB"):
        multiplier = 1024 * 1024
        text = text[:-2].strip()
    try:
        value = int(text)
    except ValueError:
        return _MAX_GRAPH_FILE_BYTES
    if value <= 0:
        return _MAX_GRAPH_FILE_BYTES
    return value * multiplier

# AWS metadata, link-local, and common cloud metadata endpoints
_BLOCKED_HOSTS = {"metadata.google.internal", "metadata.google.com"}

# RFC 6598 Shared Address Space (CGN) -- is_private misses this on Python <3.11
_CGN_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# RFC 6052 NAT64 prefixes. The well-known prefix is public traffic; the
# local-use prefix may embed private IPv4 addresses, so both are unwrapped and
# the embedded IPv4 is what gets checked.
_NAT64_WKP = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")

# Transition mechanisms that embed an IPv4 address inside an IPv6 address.
# Python's is_global/is_private flags do not look through these wrappers, so an
# attacker could use ``::ffff:127.0.0.1`` / ``2002:7f00:1::`` / a Teredo
# address to reach loopback or RFC1918 space. Every one is unwrapped before the
# allow/deny decision.
_IPV4_MAPPED = ipaddress.ip_network("::ffff:0:0/96")
_SIX_TO_FOUR = ipaddress.ip_network("2002::/16")
_TEREDO = ipaddress.ip_network("2001::/32")

_MAX_HOSTNAME_LEN = 253
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
# Characters that must never appear in a hostname. ``%`` is included because
# percent-decoding is a common parser-differential trick (and IPv6 zone IDs).
_FORBIDDEN_HOST_CHARS = frozenset("\x00\r\n\t\v\f /\\?#@[]%")


def _unwrap_embedded_ipv4(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    """Return the IPv4 address embedded in *ip*, or *ip* unchanged.

    Handles IPv4-mapped IPv6, 6to4, Teredo, and both NAT64 prefixes.
    """
    if not isinstance(ip, ipaddress.IPv6Address):
        return ip
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _SIX_TO_FOUR:
        # 2002:VVVV:VVVV:... -- the embedded IPv4 is bits 16..47.
        return ipaddress.IPv4Address((int(ip) >> 80) & 0xFFFFFFFF)
    if ip in _TEREDO:
        # 2001:0000:...:client-ip, with the client IPv4 stored bit-inverted.
        return ipaddress.IPv4Address((~int(ip)) & 0xFFFFFFFF)
    if ip in _NAT64_WKP or ip in _NAT64_LOCAL:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if *ip* falls in a private/reserved/internal range.

    Shared by validate_url (pre-flight DNS check) and the SSRF-guarded
    connection classes (connect-time check) so both use identical logic.
    Addresses that embed an IPv4 address are unwrapped first, then the strict
    ``not is_global`` test rejects everything that is not routable public
    address space (loopback, RFC1918, link-local, CGNAT, multicast, reserved,
    unspecified, documentation ranges, ...).
    """
    ip = _unwrap_embedded_ipv4(ip)
    if not ip.is_global:
        return True
    return (
        ip.is_private
        or ip.is_reserved
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip in _CGN_NETWORK
    )


def _allowed_hosts() -> tuple[str, ...]:
    """Return the optional ``GRAPHIFY_ALLOWED_HOSTS`` allowlist.

    Comma-separated. An entry is either an exact hostname (``example.com``) or
    a subdomain wildcard (``*.example.com`` / ``.example.com``). Empty means no
    allowlist is configured. Read on every call so tests and long-lived
    processes can change it without a re-import.
    """
    raw = os.environ.get("GRAPHIFY_ALLOWED_HOSTS", "")
    entries: list[str] = []
    for part in raw.split(","):
        entry = part.strip().lower().rstrip(".")
        if entry:
            entries.append(entry)
    return tuple(entries)


def _host_is_allowed(host: str) -> bool:
    """Apply the optional host allowlist. Always True when it is not set."""
    allowed = _allowed_hosts()
    if not allowed:
        return True
    for entry in allowed:
        if entry.startswith("*."):
            suffix = entry[1:]  # ".example.com"
            if len(host) > len(suffix) and host.endswith(suffix):
                return True
        elif entry.startswith("."):
            if len(host) > len(entry) and host.endswith(entry):
                return True
        elif host == entry:
            return True
    return False


def _normalize_hostname(hostname: str, *, url: str) -> str:
    """Validate and canonicalise a hostname or IP literal.

    Rejects empty names, non-ASCII (IDN/punycode-confusion) names, control
    characters or URL-delimiter smuggling, empty labels, over-long labels and
    malformed LDH labels. Trailing dots are stripped so ``example.com.`` cannot
    bypass an exact-match allowlist. IP literals are checked against the
    blocked-range logic here, before any DNS query.
    """
    if not hostname:
        raise ValueError(f"Blocked URL without a hostname. Got: {url!r}")
    if not hostname.isascii():
        raise ValueError(
            f"Blocked non-ASCII (IDN) hostname {hostname!r}. "
            f"Use the punycode (xn--) form explicitly. Got: {url!r}"
        )
    bad = sorted({ch for ch in hostname if ch in _FORBIDDEN_HOST_CHARS or ord(ch) < 0x20})
    if bad:
        raise ValueError(
            f"Blocked URL hostname containing forbidden character(s) {bad!r}. "
            f"Got: {url!r}"
        )

    host = hostname.lower().rstrip(".")
    if not host:
        raise ValueError(f"Blocked URL with an empty hostname. Got: {url!r}")
    if len(host) > _MAX_HOSTNAME_LEN:
        raise ValueError(f"Blocked over-long hostname ({len(host)} chars). Got: {url!r}")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if any(not label for label in labels):
            raise ValueError(f"Blocked hostname with an empty label. Got: {url!r}") from None
        for label in labels:
            if not _HOST_LABEL_RE.match(label):
                raise ValueError(
                    f"Blocked malformed hostname label {label!r}. Got: {url!r}"
                ) from None
    else:
        if _ip_is_blocked(ip):
            raise ValueError(
                f"Blocked private/internal IP {host}. Got: {url!r}"
            )

    if not _host_is_allowed(host):
        raise ValueError(
            f"Blocked host {host!r}: not present in GRAPHIFY_ALLOWED_HOSTS. "
            f"Got: {url!r}"
        )
    return host


def validate_url(url: str) -> str:
    """Raise ValueError if *url* is not http or https, or targets a private/internal IP.

    Blocks file://, ftp://, data:, and any other scheme that could be used
    for SSRF or local file access. Also blocks requests to private/reserved
    IP ranges (127.x, 10.x, 169.254.x, etc.), cloud metadata endpoints, and
    IPv6 transition addresses that embed a private IPv4 address. Setting
    ``GRAPHIFY_ALLOWED_HOSTS`` additionally restricts fetches to an explicit
    host allowlist.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Blocked URL scheme '{parsed.scheme}' - only http and https are allowed. "
            f"Got: {url!r}"
        )

    # Reject control characters / backslashes in the authority before parsing
    # any component out of it: they are interpreted differently by HTTP clients,
    # proxies, and browsers, which is a classic SSRF allowlist bypass.
    if any(ch in parsed.netloc for ch in "\x00\r\n\t\v\f \\"):
        raise ValueError(f"Blocked URL with control or backslash characters. Got: {url!r}")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"Blocked URL containing embedded credentials. Got: {url!r}")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Blocked URL with an invalid port. Got: {url!r}") from exc
    if port == 0:
        raise ValueError(f"Blocked URL with port 0. Got: {url!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Blocked URL without a hostname. Got: {url!r}")

    host = _normalize_hostname(hostname, url=url)
    if host in _BLOCKED_HOSTS:
        raise ValueError(
            f"Blocked cloud metadata endpoint '{host}'. "
            f"Got: {url!r}"
        )

    try:
        ipaddress.ip_address(host)
    except ValueError:
        # Resolve the hostname and block if any resolved address is
        # private/reserved/internal. The actual connection re-resolves once and
        # validates again, so this is the pre-flight half of the DNS-rebind
        # defence.
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(
                f"DNS resolution failed for '{host}': {exc}. Got: {url!r}"
            ) from exc
        if not infos:
            raise ValueError(f"DNS resolution returned no addresses for '{host}'. Got: {url!r}")
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                raise ValueError(
                    f"DNS resolution returned a non-IP address {addr!r} for '{host}'. "
                    f"Got: {url!r}"
                ) from None
            if _ip_is_blocked(ip):
                raise ValueError(
                    f"Blocked private/internal IP {addr} (resolved from '{host}'). "
                    f"Got: {url!r}"
                )

    return url


# ---------------------------------------------------------------------------
# SSRF-guarded connections
#
# Instead of monkey-patching the process-global socket.getaddrinfo (a
# non-thread-safe TOCTOU hazard when multiple fetches run concurrently),
# we subclass the HTTP(S) connection so each connection resolves DNS exactly
# once, validates the resulting IP, and then connects to that exact IP. There
# is no second resolution, so a DNS-rebind attack cannot swap in a private
# address (e.g. 169.254.169.254) between validation and connection.
# ---------------------------------------------------------------------------


def _resolve_and_validate(host: str, port: int) -> tuple[int, str]:
    """Resolve *host* once and return (family, validated_ip).

    The hostname is re-validated here (allowlist, syntax, IP-literal checks)
    because this is the connect-time choke point. All answers are checked; if
    *any* address is private/reserved/internal the connection is refused, which
    also defeats a DNS-rebind response that mixes a public and a private
    address. The first public address is then used verbatim, so there is no
    second resolution between the check and the connect.

    Raises OSError if the name is invalid or every resolved address is blocked,
    matching the failure mode urllib/http.client expect from connect().
    """
    try:
        host = _normalize_hostname(host, url=host)
    except ValueError as exc:
        raise OSError(f"SSRF blocked: {exc}") from exc

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            raise OSError(f"SSRF blocked: IP {host} is private/reserved")
        family = socket.AF_INET6 if literal.version == 6 else socket.AF_INET
        return family, host

    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    chosen: tuple[int, str] | None = None
    blocked: list[str] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_blocked(ip):
            blocked.append(addr)
            continue
        if chosen is None:
            chosen = (family, addr)
    if blocked:
        raise OSError(
            f"SSRF blocked: '{host}' resolved to private/reserved address(es) "
            f"{', '.join(sorted(set(blocked)))}"
        )
    if chosen is None:
        raise OSError(f"SSRF blocked: no usable address resolved from '{host}'")
    return chosen


class _SSRFGuardedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that resolves + validates DNS once, then connects to the
    exact validated IP (no second resolution = no DNS-rebind TOCTOU)."""

    def connect(self) -> None:
        family, ip = _resolve_and_validate(self.host, self.port)
        self.sock = socket.create_connection(
            (ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _SSRFGuardedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection variant of _SSRFGuardedHTTPConnection.

    Connects to the validated IP but performs the TLS handshake with
    server_hostname set to the original hostname so SNI / certificate
    validation work correctly (validating against the IP would break TLS).
    """

    def connect(self) -> None:
        family, ip = _resolve_and_validate(self.host, self.port)
        sock = socket.create_connection(
            (ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _SSRFGuardedHTTPHandler(urllib.request.HTTPHandler):
    """urllib handler that routes http:// through _SSRFGuardedHTTPConnection."""

    def http_open(self, req):
        return self.do_open(_SSRFGuardedHTTPConnection, req)


class _SSRFGuardedHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib handler that routes https:// through _SSRFGuardedHTTPSConnection."""

    def https_open(self, req):
        return self.do_open(_SSRFGuardedHTTPSConnection, req)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse every HTTP redirect.

    Redirects are denied by default: a public URL that 302s to an internal
    address is the simplest way around a pre-flight URL check, and most
    ingestion callers do not need to follow them. Callers that do must opt in
    explicitly (``allow_redirects=True``) and each hop is re-validated.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"Redirect blocked (allow_redirects=False): {newurl}",
            headers,
            fp,
        )


class _RevalidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that re-validates every hop and enforces a hop budget.

    Prevents open-redirect SSRF attacks where a public URL redirects to
    file://, localhost, or a link-local metadata address.
    """

    def __init__(self, max_redirects: int = 5) -> None:
        super().__init__()
        self.max_redirects = max(0, int(max_redirects))
        self._seen = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)          # raises ValueError if the hop is unsafe
        self._seen += 1
        if self._seen > self.max_redirects:
            raise urllib.error.HTTPError(
                req.full_url,
                code,
                f"Too many redirects (> {self.max_redirects}): {newurl}",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener(
    *,
    allow_redirects: bool = False,
    max_redirects: int = 5,
) -> urllib.request.OpenerDirector:
    # build_opener replaces the default HTTP(S)Handlers with our SSRF-guarded
    # subclasses, so every connection resolves+validates DNS once and connects
    # to that exact IP. Thread-safe: no process-global state is mutated.
    redirect_handler = (
        _RevalidatingRedirectHandler(max_redirects)
        if allow_redirects
        else _NoRedirectHandler()
    )
    return urllib.request.build_opener(
        _SSRFGuardedHTTPHandler,
        _SSRFGuardedHTTPSHandler,
        redirect_handler,
    )


# ---------------------------------------------------------------------------
# Safe fetch
# ---------------------------------------------------------------------------

def _remaining(deadline: float, url: str, timeout: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(
            f"Fetch of {url!r} exceeded the total deadline of {timeout:g}s"
        )
    return remaining


def _tighten_read_timeout(resp, seconds: float) -> None:
    """Best-effort: make the response socket honour the remaining deadline.

    ``http.client`` applies the connect timeout to the socket, but a server
    that drips one byte per read can stretch a single ``read`` far past it. We
    shrink the socket timeout before every chunk read so the *total* wall time
    stays bounded.
    """
    fp = getattr(resp, "fp", None)
    raw = getattr(fp, "raw", None)
    sock = getattr(raw, "_sock", None)
    if sock is not None:
        try:
            sock.settimeout(max(0.001, min(seconds, 3_600.0)))
        except OSError:
            pass


def safe_fetch(
    url: str,
    max_bytes: int = _MAX_FETCH_BYTES,
    timeout: float = 30,
    *,
    allow_redirects: bool = False,
    max_redirects: int = 5,
) -> bytes:
    """Fetch *url* and return raw bytes.

    Protections applied:
    - URL scheme validated (http / https only)
    - Hostname syntax, optional ``GRAPHIFY_ALLOWED_HOSTS`` allowlist, and DNS
      answers validated before connecting; DNS is resolved exactly once and the
      validated IP is used for the connection (no rebind TOCTOU)
    - Redirects denied by default; opt in with ``allow_redirects=True`` and
      every hop is re-validated, with a bounded ``max_redirects`` budget
    - Total wall-clock deadline of *timeout* seconds, enforced across reads
    - ``Content-Length`` checked before downloading and the streamed body
      capped at *max_bytes*
    - Non-2xx status raises urllib.error.HTTPError
    - Network errors propagate as urllib.error.URLError / OSError

    Raises:
        ValueError        - disallowed scheme/host or redirect target
        urllib.error.HTTPError  - non-2xx HTTP status (including blocked 3xx)
        urllib.error.URLError   - DNS / connection failure
        OSError / TimeoutError  - size cap or total deadline exceeded
    """
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be positive, got {max_bytes!r}")
    if timeout <= 0:
        raise ValueError(f"timeout must be positive, got {timeout!r}")
    if allow_redirects and max_redirects < 0:
        raise ValueError(f"max_redirects must be >= 0, got {max_redirects!r}")

    validate_url(url)
    deadline = time.monotonic() + float(timeout)
    opener = _build_opener(
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 graphify/1.0"})

    with opener.open(req, timeout=timeout) as resp:
        # urllib raises HTTPError for non-2xx when using urlopen directly;
        # with a custom opener we check manually to be safe.
        status = getattr(resp, "status", None) or getattr(resp, "code", None)
        if status is not None and not (200 <= status < 300):
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", {}, None)

        declared = resp.headers.get("Content-Length") if resp.headers else None
        if declared:
            try:
                declared_len = int(declared)
            except (TypeError, ValueError):
                declared_len = None
            if declared_len is not None and declared_len > max_bytes:
                raise OSError(
                    f"Response from {url!r} declares {declared_len} bytes, exceeds "
                    f"size limit ({max_bytes // 1_048_576} MB). Aborting download."
                )

        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = _remaining(deadline, url, timeout)
            _tighten_read_timeout(resp, remaining)
            chunk = resp.read(65_536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(
                    f"Response from {url!r} exceeds size limit "
                    f"({max_bytes // 1_048_576} MB). Aborting download."
                )
            chunks.append(chunk)

    return b"".join(chunks)


def safe_fetch_text(
    url: str,
    max_bytes: int = _MAX_TEXT_BYTES,
    timeout: float = 15,
    *,
    allow_redirects: bool = False,
    max_redirects: int = 5,
) -> str:
    """Fetch *url* and return decoded text (UTF-8, replacing bad bytes).

    Wraps safe_fetch with tighter defaults for HTML / text content. Redirects
    stay denied unless the caller explicitly opts in.
    """
    raw = safe_fetch(
        url,
        max_bytes=max_bytes,
        timeout=timeout,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
    )
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def validate_graph_path(path: str | Path, base: Path | None = None) -> Path:
    """Resolve *path* and verify it stays inside *base*.

    *base* defaults to the `graphify-out` directory relative to CWD.
    Also requires the base directory to exist, so a caller cannot
    trick graphify into reading files before any graph has been built.

    Raises:
        ValueError  - path escapes base, or base does not exist
        FileNotFoundError - resolved path does not exist
    """
    if base is None:
        resolved_hint = Path(path).resolve()
        for candidate in [resolved_hint, *resolved_hint.parents]:
            if candidate.name == GRAPHIFY_OUT_NAME:
                base = candidate
                break
        if base is None:
            base = Path(GRAPHIFY_OUT).resolve()

    base = base.resolve()
    if not base.exists():
        raise ValueError(
            f"Graph base directory does not exist: {base}. "
            "Run /graphify first to build the graph."
        )

    resolved = Path(path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Path {path!r} escapes the allowed directory {base}. "
            "Only paths inside graphify-out/ are permitted."
        )

    if not resolved.exists():
        raise FileNotFoundError(f"Graph file not found: {resolved}")

    return resolved


def check_graph_file_size_cap(path: Path) -> None:
    """Reject *path* if its size exceeds the configured graph-file cap.

    Protects callers from memory bombs by failing fast before a multi-GiB
    graph.json is read into memory and JSON-parsed. Silently returns when
    ``path.stat()`` cannot be read — the caller's own existence/path check
    is expected to surface a clearer error in that case.

    The cap is resolved on every call via :func:`_max_graph_file_bytes`, so the
    ``GRAPHIFY_MAX_GRAPH_BYTES`` env var can be set before import and still
    apply.

    Raises:
        ValueError - file size exceeds the cap. The message includes the
        observed size, the cap, and how to raise the limit.
    """
    cap = _max_graph_file_bytes()
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size > cap:
        raise ValueError(
            f"graph file {path} is {size:_d} bytes, exceeds {cap:_d}-byte cap\n"
            f"(set GRAPHIFY_MAX_GRAPH_BYTES=<bytes> or "
            f"GRAPHIFY_MAX_GRAPH_BYTES=<N>GB to raise the limit)"
        )


def resolve_within(base: str | Path, candidate: str | Path) -> Path | None:
    """Resolve *candidate* under *base*, returning None if it escapes.

    Intended for source-relative include resolution (C/C++/Fortran). Absolute
    candidates (POSIX root, Windows drive, UNC) and ``..`` components that walk
    out of *base* are rejected. Backslashes are treated as separators so a
    Windows-style include cannot dodge the check on POSIX. Symlinks are resolved
    before containment is checked, so a link inside the tree cannot be used to
    read outside it.
    """
    text = str(candidate)
    if not text or "\x00" in text:
        return None
    norm = text.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        return None

    try:
        base_resolved = Path(base).resolve()
        resolved = (base_resolved / norm).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return resolved


# ---------------------------------------------------------------------------
# Label sanitisation (mirrors code-review-graph's _sanitize_name pattern)
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_LABEL_LEN = 256


# Credential shapes redacted from free text that is persisted into the graph
# (rationale/comment labels). Shape-based only, so it is risk reduction rather
# than a guarantee: vendor-prefixed tokens, PEM private-key blocks and URL
# userinfo. Boundaries are alphanumeric-only lookarounds rather than \b so a
# token glued to an identifier by `_` (`token_ghp_...`, `AKIA..._prod`) still
# matches.
_SECRET_SHAPE_RE = re.compile(
    # Header through the END line, or to end of text when the block is cut off:
    # the base64 body is the secret, not the header.
    r"(?s:-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
    r"(?:.*?-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|.*))"
    r"|(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,}"
    r"|(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{22,}"
    r"|(?<![A-Za-z0-9])xox[abeoprs]-[A-Za-z0-9-]{10,}"
    r"|(?<![A-Za-z0-9])[sr]k_(?:live|test)_[A-Za-z0-9]{10,}"
    # Require a digit so hyphenated prose (`sk-learn-compatible-...`) is left alone.
    r"|(?<![A-Za-z0-9])sk-(?:ant-|proj-)?(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{20,}"
    r"|(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{35}"
    # Payload segment may be tiny (`e30` is `{}`).
    r"|(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{10,}"
    r"|(?<=\bBearer )[A-Za-z0-9._~+/=-]{16,}"
    # Userinfo up to the LAST `@` before the host: the user may be empty
    # (`redis://:pw@host`) and the password may contain `@` or `/`.
    r"|(?<=://)[^\s/@]*:[^\s?#]*(?=@[^\s@/?#]+)"
)

REDACTED_MARKER = "[redacted]"


def redact_secrets(text: str | None) -> str:
    """Replace credential-shaped substrings in *text* with ``[redacted]``.

    Applied to free text copied out of source files (docstrings and ``# WHY:``
    style comments) before it becomes a node label, so a token pasted into a
    comment does not land in graph.json / graph.html / GRAPH_REPORT.md.
    """
    if not text:
        return "" if text is None else text
    return _SECRET_SHAPE_RE.sub(REDACTED_MARKER, str(text))


def sanitize_label(text: str | None) -> str:
    """Strip control characters and cap length.

    Safe for embedding in JSON data (inside <script> tags) and plain text.
    For direct HTML injection, wrap the result with html.escape().
    """
    if text is None:
        return ""
    text = _CONTROL_CHAR_RE.sub("", str(text))
    if len(text) > _MAX_LABEL_LEN:
        text = text[:_MAX_LABEL_LEN]
    return text


# ---------------------------------------------------------------------------
# Metadata sanitisation (recursive, bounded, HTML-safe)
# ---------------------------------------------------------------------------

_METADATA_MAX_VALUE_LEN = 512
_METADATA_MAX_LIST_ITEMS = 50
_METADATA_MAX_ATTRIBUTES = 100


def _sanitize_metadata_string(value: object) -> str:
    """Return a control-character-free, HTML-escaped, bounded string."""
    text = _CONTROL_CHAR_RE.sub("", str(value))
    text = html.escape(text, quote=True)
    if len(text) > _METADATA_MAX_VALUE_LEN:
        text = text[:_METADATA_MAX_VALUE_LEN]
    return text  # html is imported at module level (line 5)


def _sanitize_metadata_value(value: object) -> object:
    """Sanitize a metadata value while preserving simple JSON-compatible types."""
    if isinstance(value, bool):
        # bool is a subclass of int — must be checked first to avoid coercion.
        return value
    if isinstance(value, str):
        return _sanitize_metadata_string(value)
    if isinstance(value, dict):
        return sanitize_metadata(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata_value(item) for item in value[:_METADATA_MAX_LIST_ITEMS]]
    if isinstance(value, (int, float)) or value is None:
        return value
    return _sanitize_metadata_string(value)


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, object]:
    """Sanitize metadata keys and values before graph export.

    Metadata is less constrained than node labels: it can contain nested
    dicts, lists, source snippets, external index symbols, and docstring
    text. This helper keeps the data JSON-compatible, strips control
    characters, escapes HTML-sensitive characters in strings, caps long
    strings/lists, and drops entries whose key becomes empty after
    sanitization.
    """
    if metadata is None:
        return {}

    result: dict[str, object] = {}
    for key, value in metadata.items():
        clean_key = _sanitize_metadata_string(key)
        if not clean_key:
            continue
        result[clean_key] = _sanitize_metadata_value(value)
    return result
