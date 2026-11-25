# 0029 — No code graph: the graph holds only what agents can't derive from the repo

## Status
Accepted (2026-11-25)

## Context
NAA has a code-graph MCP (`mcp/codegraph`) that reads a Java class/method/dependency graph built externally by jQAssistant (JVM + Maven/Gradle build required). It was never integrated with the document graph. An in-house tree-sitter ingester was considered as a replacement.

Current coding agents navigate source code well on their own: they search it, read it and follow call sites live, and the result is always up to date. A precomputed code-structure graph duplicates that ability, goes stale, adds a heavy dependency that breaks the 5-minute quickstart (ADR-0034), and costs maintenance per language.

## Decision
- Knotlore does **not** ingest code structure. `mcp/codegraph` is archived and not maintained.
- The graph stores **only what an agent can't recover from the repository**: requirements and the specs they come from, decisions and conventions, and issue history. Commits and file paths enter the graph only as **link targets** (ADR-0030). Classes, methods and call graphs don't.
- Traceability ends at the file: the graph tells the agent *which files* relate to a requirement, and the agent reads the code itself.

## Consequences
- No JVM, jQAssistant or tree-sitter dependency. One Neo4j instance is enough (ADR-0034).
- Supersedes NAA's roadmap "Phase 3 — Code-graph layer (jQAssistant)".
- If agents later prove unable to answer a recurring structural question, revisit this with that concrete question as evidence. Don't revisit it speculatively.
