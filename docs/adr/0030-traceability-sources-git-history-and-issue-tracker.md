# 0030 — Traceability sources: git history and issue tracker as read-only source adapters

## Status
Accepted (2026-11-25). Requires a `kg-schema` version bump. Revisits the entity-type scope of ADR-0003.

## Context
The first use case (ADR-0027) is requirements traceability: requirement ↔ issues ↔ commits/files. Cross-cutting questions ("which issues changed requirement X, and in which files?") can't be answered by calling a live tracker MCP per question; the links must already exist in the graph.

Loom today has Obsidian and docx sources only. ADR-0003 deliberately shipped docx entity types empty and excluded NAA's project-specific `BR` type.

## Decision
- Add two **source adapters** that go through the existing pipeline (Source → Extraction → Rules → Sinks), with the same incremental, curated-immunity and tombstone behaviour as every other source:
  - **Git history**: commits → referenced issue keys → changed file paths.
  - **Issue tracker**: issues imported as **read-only** nodes. The first and only maintained tracker is **Jira Data Center/Server** (self-hosted Jira, which the design-partner team uses; authenticated with a personal access token). Other trackers come after v0.1.
- **Linking rules are YAML config**, like docx rule files: issue-key regex, and where to look (commit message, branch name). Both locations are supported from the start; the design-partner team's real convention is still to be confirmed against its commit log.
- Requirement IDs are linked through the same configurable patterns. The docx rule file's existing `id_pattern` already recognises them, so no project-specific prefix is baked into code.
- `kg-schema` gains **generic** types for this use case: a requirement entity, issue, commit and source-file entities, and the relationships between them (e.g. a commit references an issue, a commit changes a file, an issue or commit references a requirement). Exact names are fixed in the schema-bump change, following ADR-0002/0003 (a fixed, versioned enum; no dynamic labels). "Requirement" is the generic type. `BR` stays a project-specific ID *prefix*, not a type.
- Write actions on trackers (create/update issues) are **not** part of ingestion. They stay in optional MCP plugins (ADR-0031).

## Consequences
- New source configs need JSON Schemas so the Configs API and the Rules page can edit and preview them like existing rule files.
- The golden-fixture parity gate (ADR-0007) doesn't apply to the new adapters. They get their own fixture tests against synthetic repos and issue fixtures (ADR-0034).
- Tracker credentials (PAT) are configured per source config, never committed. See also ADR-0032.
