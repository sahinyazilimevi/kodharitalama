# kodharitalama

Local, security-hardened code knowledge graph for **Claude Code**, **OpenCode**,
and **Antigravity IDE**.

**Brand:** Şahin Yazılım Evi · **Developer:** Murat ŞAHİN · **Version:** 0.30.103

> `kodharitalama` is an adaptation of the Graphify project. The upstream
> copyright and license notices are retained. See [`NOTICE`](NOTICE),
> [`REFERENCES.md`](REFERENCES.md), and [`LICENSE`](LICENSE).
>
> The Python import package remains `graphify`, and the historical `graphify`
> command is kept as an alias. The primary command is `kodharitalama`.

---

## What it does

`kodharitalama` turns a folder of source code, documents, papers, images, or
videos into a persistent, queryable knowledge graph:

- **god nodes** and community structure;
- cross-file relationships and architecture summaries;
- interactive HTML, GraphRAG-ready JSON, and `GRAPH_REPORT.md`;
- optional wiki, GraphML, SVG, Neo4j, FalkorDB, MCP, and watch modes.

For coding agents, the important part is retrieval: instead of grepping a large
repository, the agent asks a scoped question and receives a small subgraph.

```text
kodharitalama .                       # build a graph for the current folder
kodharitalama query "auth flow"       # ask a scoped question
kodharitalama explain "TokenCache"    # inspect one concept
kodharitalama path "A" "B"            # find a relationship
kodharitalama update .                # AST-only incremental refresh
kodharitalama --help                  # full command list
```

Output is written to `graphify-out/` for compatibility with the upstream tool
and existing integrations.

---

## Security posture

This build is intentionally conservative:

- **No telemetry** and no automatic upload.
- **No dynamic third-party skill installation.** Skills ship in this checkout.
- **Deny-by-default URL fetching** with scheme/host checks, private-IP and
  DNS-rebinding protection, no redirects by default, time and size limits.
- **Path containment** for include traversal and generated paths.
- **No `shell=True`, `os.system`, or `os.popen`** in the runtime package;
  subprocesses use argument arrays.
- **Untrusted documents are data**, not instructions.
- **Pinned dependencies** and a hash-locked default closure.
- **Project-local, manifest-tracked IDE installation** via
  `tools/install_skills.py`.

Read [`SECURITY.md`](SECURITY.md) before running the tool against untrusted
code. The tool is not a sandbox; use a container or VM for unknown repositories.

---

## Requirements

| Requirement | Notes |
| --- | --- |
| Python | 3.10–3.13 recommended. Python 3.15 has no wheels for the pinned NumPy 1.26.4 line. |
| OS | Windows 10/11, macOS, Linux |
| Disk | A few hundred MB for the default dependency closure |
| Network | Only for the initial dependency install; runtime fetching is opt-in |

The full runtime needs `networkx`, `numpy`, `rapidfuzz`, `PyYAML`, and the
tree-sitter grammars. `pytest` is only needed for the test suite.

---

## Quick start from this checkout

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --require-hashes --no-deps -r requirements.lock
python -m pip install setuptools==84.2.1 wheel==0.48.0
python -m pip install --no-build-isolation --no-deps -e .
kodharitalama --help
```

### macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --require-hashes --no-deps -r requirements.lock
python -m pip install setuptools==84.2.1 wheel==0.48.0
python -m pip install --no-build-isolation --no-deps -e .
kodharitalama --help
```

> `requirements.lock` covers the default runtime closure only. Optional extras
> (`mcp`, `neo4j`, `falkordb`, and the large language packs) are resolved
> separately. Review them before enabling.
>
> Do **not** install `graphifyy` from a package index. This checkout is the
> supported source.

Without installing the project, you can still run it from the checkout after
installing the dependencies:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m graphify --help
```

---

## IDE integration

The installer writes project-local files only. It never downloads anything and
never writes outside `--dest`.

### One command for all three IDEs

```powershell
python tools\install_skills.py --ide all --dest .
```

```bash
python3 tools/install_skills.py --ide all --dest .
```

Use `--dest C:\path\to\another-project` to install into a different project.
Use `--dry-run` first if you want to see the planned writes.

### Per-IDE commands

| IDE | Command | Skill location | Always-on instructions |
| --- | --- | --- | --- |
| Claude Code | `python tools/install_skills.py --ide claude-code --dest .` | `.claude/skills/kodharitalama/SKILL.md` | `.claude/CLAUDE.md` |
| OpenCode | `python tools/install_skills.py --ide opencode --dest .` | `.opencode/skills/kodharitalama/SKILL.md` | `AGENTS.md` |
| Antigravity IDE | `python tools/install_skills.py --ide antigravity --dest .` | `.agents/skills/kodharitalama/SKILL.md` | `.agents/rules/kodharitalama.md`, `.agents/workflows/kodharitalama.md` |

Each skill is installed with its `references/` sidecar. The installer rewrites
the skill front matter to `name: kodharitalama`; the body keeps the compatible
`graphify` command examples, and both command names work.

### Installed layout

```text
my-project/
├─ .claude/
│  ├─ CLAUDE.md                          # marked kodharitalama section
│  └─ skills/kodharitalama/
│     ├─ SKILL.md
│     └─ references/*.md
├─ .opencode/
│  └─ skills/kodharitalama/
│     ├─ SKILL.md
│     └─ references/*.md
├─ .agents/
│  ├─ rules/kodharitalama.md             # Antigravity always-on rule
│  ├─ workflows/kodharitalama.md
│  └─ skills/kodharitalama/
│     ├─ SKILL.md
│     └─ references/*.md
├─ AGENTS.md                             # marked kodharitalama section
└─ .kodharitalama/
   └─ skills-manifest.json               # installed files and SHA-256 hashes
```

`tools/install_skills.py` is idempotent. Re-run it after updating the checkout to
refresh the skills.

### Verify, update, remove

```powershell
python tools\install_skills.py --check --dest .       # compare with packaged sources
python tools\install_skills.py --ide all --dest .     # refresh
python tools\install_skills.py --uninstall --ide all --dest .   # remove only managed files
```

The installer refuses to overwrite unmanaged or locally modified files unless
`--force` is given. `--uninstall` removes only paths recorded in the manifest and
leaves user content in `AGENTS.md` and `.claude/CLAUDE.md` intact.

### Optional MCP configuration

The skills work through the CLI. If you prefer MCP, add a server entry that
points at the generated graph:

**Claude Code** (`.mcp.json`):

```json
{
  "mcpServers": {
    "kodharitalama": {
      "command": "python",
      "args": ["-m", "graphify.serve", "graphify-out/graph.json"]
    }
  }
}
```

**OpenCode** (`opencode.json`):

```json
{
  "mcp": {
    "kodharitalama": {
      "type": "local",
      "command": ["python", "-m", "graphify.serve", "graphify-out/graph.json"],
      "enabled": true
    }
  }
}
```

**Antigravity** (`~/.gemini/antigravity/mcp_config.json`):

```json
{
  "mcpServers": {
    "kodharitalama": {
      "command": "python",
      "args": ["-m", "graphify.serve", "${workspace.path}/graphify-out/graph.json"]
    }
  }
}
```

MCP is optional. Keep the server bound to the project graph and do not expose it
on a network interface unless you add authentication.

---

## Usage notes

- The graph is only as good as the input. Start with `kodharitalama .` in the
  repository root.
- `--update` is AST-only and does not call an LLM.
- `--mode deep` produces richer inferred edges and is slower.
- `--watch` keeps the graph current while files change.
- `--mcp` serves the graph over stdio.
- `--wiki` produces an agent-crawlable wiki under `graphify-out/wiki/`.
- `--no-viz` skips HTML when you only need JSON and the report.

The packaged skills describe the full command surface, including Obsidian,
Neo4j, FalkorDB, GraphML, SVG, transcription, and cross-repo graphs. Read the
installed `SKILL.md` before using a mode for the first time.

---

## Repository layout

```text
kodharitalama/
├─ graphify/                      # import package, CLI, extractors, exporters, skills
├─ integrations/
│  ├─ claude-code/CLAUDE.section.md
│  ├─ opencode/AGENTS.section.md
│  └─ antigravity/{rules.md,workflow.md}
├─ tools/
│  ├─ install_skills.py           # project-local IDE installer
│  ├─ generate_requirements_lock.py
│  └─ scan_untrusted_docs.py
├─ tests/                         # security, include-resolution, installer tests
├─ docs/                          # audit and operating notes
├─ requirements.lock              # hashed default dependency closure
├─ pyproject.toml
├─ SECURITY.md
├─ AGENTS.md
├─ REFERENCES.md
├─ Açıklama.md                    # Turkish description of this README
└─ README.md
```

---

## Verification

Run these from the checkout root:

```powershell
python -m compileall -q graphify tools tests
python tools/install_skills.py --check --dest .
python tools/scan_untrusted_docs.py
```

The full test suite additionally requires `pytest`, `networkx`, and the
tree-sitter grammars:

```powershell
python -m pytest -q
```

If a dependency is unavailable, record the skipped check instead of assuming it
passed. The audit report in [`docs/DENETIM_RAPORU_TR.md`](docs/DENETIM_RAPORU_TR.md)
lists what was verified statically and what could not be executed in the build
environment.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `pip` cannot find a NumPy wheel | You are on Python 3.14/3.15. Use Python 3.12 or 3.13. |
| `ModuleNotFoundError: networkx` | The runtime closure is not installed. Run the `requirements.lock` step. |
| `ModuleNotFoundError: tree_sitter` | A grammar or the runtime is missing. Reinstall the default closure. |
| `kodharitalama` is not recognized | The editable install did not run. Use `python -m graphify` or reinstall. |
| Skill is not listed by the IDE | Check the path in the table above and restart the IDE. |
| `--check` reports drift | The checkout changed after installation. Re-run the installer. |
| Installer refuses to overwrite | The file is unmanaged or was edited. Inspect it, then use `--force` if appropriate. |

---

## License and attribution

- Apache License 2.0: [`LICENSE`](LICENSE)
- MIT-licensed portions: [`LICENSE-MIT`](LICENSE-MIT)
- Upstream and adaptation notice: [`NOTICE`](NOTICE)
- Upstream project and integration references: [`REFERENCES.md`](REFERENCES.md)

Upstream Graphify: <https://github.com/Graphify-Labs/graphify>.
The upstream project does not maintain, sponsor, or endorse this distribution.
