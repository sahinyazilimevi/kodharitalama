# References and Attribution

## Upstream project

- **Name:** Graphify
- **Repository:** https://github.com/Graphify-Labs/graphify
- **Reference revision:** `v8` source archive used for the audit
- **License:** Apache License 2.0, with MIT-licensed portions retained in
  `LICENSE-MIT`
- **Copyright:** 2026 Safi Shamsi and the Graphify contributors

The upstream project is referenced for attribution only. It does not maintain,
sponsor, or endorse this distribution.

## This distribution

- **Name:** kodharitalama
- **Version:** 0.30.103
- **Brand:** Şahin Yazılım Evi
- **Developer:** Murat ŞAHİN

## What changed

The adaptation keeps the `graphify` import package and the historical
`graphify` CLI alias so existing integrations keep working, then adds:

- a `kodharitalama` distribution name, CLI, and MCP entry point;
- local-only, manifest-tracked skill installation for Claude Code, OpenCode,
  and Antigravity IDE;
- SSRF and path-containment hardening;
- sandboxed Fortran include preprocessing and C/C++ include-edge validation;
- an opt-in gate for tokenizer downloads;
- pinned dependency metadata and a hashed default lock file;
- sanitized skill documentation with no package-index or third-party install
  snippets.

## Documentation used for the integration layout

- Claude Code project skills: `.claude/skills/<name>/SKILL.md` and project
  instructions in `CLAUDE.md`.
- OpenCode project skills: `.opencode/skills/<name>/SKILL.md` and project
  instructions in `AGENTS.md`.
- Antigravity project skills: `.agents/skills/<name>/SKILL.md`, always-on rules
  in `.agents/rules/`, and workflows in `.agents/workflows/`.

These paths are enforced by `tools/install_skills.py`; consult the vendor
documentation for the current version of each IDE before changing them.

## License texts

- `LICENSE` — Apache License 2.0
- `LICENSE-MIT` — MIT license for portions contributed before relicensing
- `NOTICE` — upstream copyright and adaptation notice
