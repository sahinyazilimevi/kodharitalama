---
name: kodharitalama
description: Turn any folder of files into a navigable knowledge graph
---

# Workflow: kodharitalama

Follow the project-local skill at `.agents/skills/kodharitalama/SKILL.md` to run the full pipeline.

If no path argument is given, use `.` (the current directory).

Safety defaults:
- Keep generated output inside `graphify-out/`.
- Do not pass credentials, tokens, or private URLs to the graph builder.
- Do not install anything from the network while following the skill.
