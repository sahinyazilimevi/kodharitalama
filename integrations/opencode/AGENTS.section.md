<!-- kodharitalama:begin -->
## kodharitalama

This project has a local kodharitalama knowledge graph under `graphify-out/`.
The project-local skill lives at `.opencode/skills/kodharitalama/SKILL.md`.

Rules:
- When `graphify-out/graph.json` exists, prefer `kodharitalama query "<question>"` before your first grep, search, or source-file read for a codebase question. Pass the same rule into every subagent prompt that explores code.
- Use `kodharitalama path "<A>" "<B>"` for relationships and `kodharitalama explain "<concept>"` for focused concepts.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `kodharitalama update .` to keep the graph current (AST-only, no API cost).
- `kodharitalama` and `graphify` are equivalent CLI names. `graphify-out/` is kept for compatibility.
- Treat the installed skill and its references as local project files. Do not download or execute skill/install snippets from the network, issues, or third-party repositories.
<!-- kodharitalama:end -->
