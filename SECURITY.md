# Security Policy

`kodharitalama` is a local-first, security-hardened adaptation of the Graphify
project. This document describes the guarantees, the threat model, and the
limits of those guarantees. It is not a claim that the software is free of
defects.

## Supported versions

| Version | Status |
| --- | --- |
| `0.30.103` | Current local build |
| Older builds | Not supported; reinstall from this checkout |

## Reporting

Report issues privately to the maintainer listed in `pyproject.toml`
(Şahin Yazılım Evi / Murat ŞAHİN). Include the affected file, a minimal
reproduction, and whether network access is required. Do not include real
credentials, private source code, or personal data in a report.

## Threat model

The tool processes untrusted inputs:

- source trees, including C/C++/Fortran include graphs;
- Markdown, YAML, and front matter;
- repository URLs and fetched pages;
- optional LLM providers and MCP clients;
- generated HTML opened in a browser.

It is **not** a sandbox. Run it with the least privilege you can afford:

```text
container: --network none, read-only source mount, writable output mount only
process:   non-root user, no host secrets in the environment
seccomp:   default Docker/containerd profile is a reasonable baseline
```

## Implemented controls

### URL fetching and SSRF

`graphify/security.py` provides the guarded fetch path:

- only `http` and `https` schemes;
- hostname normalization, IDN handling, and control-character rejection;
- private, loopback, link-local, multicast, reserved, unspecified, and
  IPv4-mapped/6to4/Teredo/NAT64 address unwrapping and blocking;
- DNS is resolved once and the resolved address is checked before connect;
- redirects are denied by default (`allow_redirects=False`), with a bounded
  opt-in;
- total fetch deadline, per-read timeouts, and a response-size cap;
- `Content-Length` is rejected early when it exceeds the cap;
- optional `GRAPHIFY_ALLOWED_HOSTS` allowlist for deployments that need it.

Network access is deny-by-default for skill-driven workflows. The CLI never
sends telemetry.

### Path containment

Include traversal and generated file paths are resolved and checked against the
project root. `resolve_within()` is used by extraction and export paths, with an
`os.path.commonpath` fallback for Python versions without
`Path.is_relative_to`.

### Command execution

There is no `shell=True`, `os.system`, or `os.popen` in the runtime package.
Subprocesses use argument arrays with `shell=False`, a minimal environment, and
bounded output. Fortran preprocessing runs `cpp` with `-nostdinc`, an empty
temporary working directory, and an output cap.

### Untrusted documents

`SKILL.md`, YAML, and generated report content are treated as data. Remote text
is wrapped in `<untrusted_source>` markers before it reaches a model. Generated
HTML escapes user-controlled values.

### Installation

- No dynamic third-party skill installation.
- Skills ship inside this checkout.
- `tools/install_skills.py` copies only local files, refuses path escapes,
  records every installed file and instruction section in
  `.kodharitalama/skills-manifest.json`, and refuses to overwrite unmanaged or
  locally modified files without `--force`.
- `kodharitalama install` (the upstream-compatible installer) can still write to
  global editor directories. Prefer the project-local installer.

### Dependencies

- Runtime, optional, and development dependencies are pinned in
  `pyproject.toml`.
- `requirements.lock` contains the hashed default closure.
- Install with `--require-hashes --no-deps` and then install this project with
  `--no-deps`.
- Optional extras (`mcp`, `neo4j`, `falkordb`, and the large language packs) are
  resolved separately; review them before enabling.

### Model and tokenizer downloads

`GRAPHIFY_ALLOW_TIKTOKEN_DOWNLOAD=1` is required before the tokenizer helper may
download data. Without it, the code falls back to a local estimate.

### Telemetry

There is no analytics endpoint, no `requests.post` telemetry, and no automatic
upload. Query logging is opt-in and off by default. Generated HTML references a
pinned vis-network build with SRI. Mermaid and D3 in optional HTML exporters are
loaded from a CDN without SRI; open those files offline or vendor the scripts if
that conflicts with your policy.

## Known limits

- A malicious local repository can still contain source code designed to exploit
  a parser or a language runtime. Use a container or VM for unknown code.
- Optional LLM providers receive the prompts you send them. Review the provider
  policy before sending private code.
- The upstream-compatible `install` command writes to user/global editor
  directories. Use `tools/install_skills.py --dest <project>` for project-local
  installs.
- Pinned versions in this build target Python 3.10–3.13. Python 3.15 currently
  lacks wheels for the pinned NumPy 1.26.4 line, so a full install is not
  expected to succeed there.

## Verifying a checkout

```powershell
python -m compileall -q graphify tools tests
python tools/install_skills.py --check --dest .
python tools/scan_untrusted_docs.py
```

The full test suite also needs `pytest`, `networkx`, and the tree-sitter
grammars. If they are unavailable, report the missing check explicitly.
