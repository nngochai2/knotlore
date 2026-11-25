# 0030 — v0.1 release scope and the 5-minute quickstart criterion

## Status
Accepted (2026-11-25)

## Context
An open-source visitor gives up within minutes if setup needs Python, Docker, two Neo4j instances and several `.env` files, as NAA does today. The first release has to show the traceability use case (ADR-0027) working, and contain nothing a solo maintainer can't support.

## Decision
**Release criterion:** from a fresh clone, `docker compose up` gives a working traceability answer from the bundled sample project **in under 5 minutes**.

**v0.1 contains exactly:**
1. The merged repo under the Knotlore name (Loom base + NAA's MCP layer; ADR-0028).
2. `docker compose up` → **one** Neo4j, backend + UI, and the knowledge MCP, bound to localhost (ADR-0032). It ships with a **synthetic sample project**: an Obsidian vault, a docx spec with requirement tables, a small git repo whose commits reference issue keys, and issue fixtures.
3. Source adapters: Obsidian and docx (existing), git history and Jira Data Center (ADR-0030).
4. The knowledge MCP on Streamable HTTP, with traceability-shaped tools (e.g. "which requirements does this file touch", "where is requirement X specified and which issues/commits changed it") rather than raw graph lookups.
5. UI: Landing (ADR-0023, with cards revised to lead with traceability instead of the post-v0.1 vector sink), ingestion with Instances (ADR-0025/0026: each git repo, Jira project or doc folder is an Instance), rule-config editing with table and graph preview (ADR-0024), and MCP/plugin status (ADR-0033).
6. Plugin manifest v1 with support tiers (ADR-0031).

**After v0.1:** graph correction canvas, vector sink (ChromaDB), other tracker adapters (Azure DevOps, GitHub/GitLab issues), authentication, ingestion plugin contract.

## Consequences
- The two-Neo4j setup (doc graph + code graph) collapses to one (ADR-0029).
- The sample project is synthetic, contains no employer data (ADR-0027), and doubles as an end-to-end test fixture.
- Fixing NAA issue #43 is required only if Oracle ships in v0.1. Since Oracle is an "example" plugin, it may ship marked unsafe-to-expose or be left out.
