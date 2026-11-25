# 0024 — One product, one repo: Loom is the base, NAA's read side moves in

## Status
Accepted (2026-11-25). Narrows `loom-spec.md` §1 and the §2 non-goal "MCP server hosting, configuration, or management of any kind".

## Context
`loom-spec.md` §1 split the system in two: Loom (write path) and NAA (read path: MCP servers), coupled only through the graph database and the versioned `kg-schema`. That split was right as an engineering boundary, but as two products it costs an open-source user two installs, two READMEs and two concepts, and costs a solo maintainer two CIs and two issue trackers (ADR-0027).

Loom's codebase is the stronger base: a pipeline abstraction, the `kg-schema` contract, incremental re-ingestion with curated immunity, `mypy --strict`, a large test suite, and already-decided frontend ADRs (0013–0017). NAA's parsing (`pipeline/`, `webapp/src/docx_generic_parser.py`, `webapp/src/processor.py`) is what Loom already replaced, with the golden-fixture parity gate (ADR-0007) as proof.

## Decision
- **Knotlore is one product in one repo, grown from this (Loom) repo.**
- NAA's **read side moves in**: the knowledge-graph MCP server and the MCP plugin manifest/management (ADR-0031). NAA's `pipeline/` and webapp parsing code are retired, not ported again.
- **The engineering boundary survives inside the product.** Ingestion and the MCP server remain separate processes. `kg-schema` remains the only contract between them: the MCP server reads the graph and never imports pipeline code. What changes is packaging, release and UI, not coupling.
- The §2 non-goal on MCP hosting is narrowed. Knotlore hosts its own knowledge MCP and can start, stop and register MCP plugins (ADR-0031). It is still **not** a general-purpose MCP hub, and it doesn't do per-tool policy, proxying or marketplace features.
- The NAA repo stays in place until its parsing is retired and its MCP layer has moved, then it is archived with a pointer to Knotlore.

## Consequences
- `loom-spec.md` §1, §2 (non-goals) and §8 ("API surface — complete") need amending to cover MCP/plugin status endpoints and the merged scope.
- Repository layout gains an MCP area alongside `backend/` (for example `mcp/knowledge/`). The exact layout is decided when the move happens.
- The NAA issues that only concern its own webapp (e.g. splitting `app.js` into ES modules) are closed as superseded.
