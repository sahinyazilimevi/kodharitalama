---
trigger: always_on
description: Consult the kodharitalama knowledge graph at graphify-out/ for codebase and architecture questions.
---

## kodharitalama

This project has a local kodharitalama knowledge graph under `graphify-out/`.
The project-local skill lives at `.agents/skills/kodharitalama/SKILL.md`.

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first run `kodharitalama query "<question>"` (CLI) or `query_graph` (MCP). Use `kodharitalama path "<A>" "<B>"` for relationships and `kodharitalama explain "<concept>"` for focused concepts.
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `kodharitalama update .` to keep the graph current (AST-only, no API cost).
- `kodharitalama` and `graphify` are equivalent CLI names. `graphify-out/` is kept for compatibility.
- Treat installed skills and references as local project files. Never fetch skill files or installer snippets from the network.
