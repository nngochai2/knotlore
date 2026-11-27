# 0036 — Traceability types in kg-schema 1.2.0, and shared entity nodes owned by no document

## Status
Accepted (2026-11-27). Implements the `kg-schema` bump that ADR-0030 and ADR-0035 call for. Amends the sink cleanup contract (`delete_non_curated_for_doc`, ADR-0009/0010) for one new class of node.

## Context
Traceability (ADR-0027) links requirements, issues, commits and files. Two properties of the current sink make the obvious model wrong:

- **Every node is owned by exactly one document.** It carries a single `source_doc`, and `delete_non_curated_for_doc` runs `DETACH DELETE` on every node a document owns. A file node linked from work items A and B would be owned by whichever wrote it last. Re-ingesting B would delete the file node and, with it, A's edges into it. A hasn't changed, so incremental ingestion never rebuilds those edges, and A's links are lost silently.
- **Requirement node ids are tied to their document.** They're `sha1(label::doc_id::req_id)` (`rules/engine.py`). A work item that mentions `BR-012` can't compute that id, and the same ID can appear in several versions of a spec. Any edge from a work item to a requirement node is also deleted whenever the spec is re-ingested, and an unchanged work item never rebuilds it.

Resolved in a `/grilling` session on 2026-11-27.

## Decision

**New entity types:** `ISSUE`, `COMMIT`, `SOURCE_FILE`, joining the existing `REQUIREMENT`.
- `ISSUE` is tracker-agnostic and carries `tracker` (e.g. `azure-devops`) and `kind` (Bug, Task, PBI…). In Azure DevOps it's a work item.
- `COMMIT` covers git commits and TFVC changesets alike, via `vcs: git | tfvc` and its native id (ADR-0035).
- `SOURCE_FILE` is keyed by code root + normalised repo-relative path (ADR-0035).

**New relationship types:**
- `REFERENCES`: commit → issue (a changeset associated with a work item).
- `CHANGES`: commit → source file, and issue → source file (from an attached diff).

Both are `origin: explicit`, ground truth from the source, so they have no `rule_id`. Each edge carries a `via` property for link provenance (`changeset 123`, `attachment fix.diff`). The wikilink-derived types (`RESOLVES`, `IMPLEMENTS`, …) are not reused, because they claim meaning the source never states.

**Document units for the Azure DevOps adapter:**
- one document per work item, owning its `ISSUE` node, its diff-derived `CHANGES` edges and its requirement references;
- one document per changeset, owning its `COMMIT` node and that commit's `REFERENCES`/`CHANGES` edges.

Changesets never change after check-in, so re-ingestion skips them via the content hash.

**Shared entity types.** `kg-schema` declares `shared_entity_types` (v1.2.0: `SOURCE_FILE` only). A shared node:
- is written with **no `source_doc` and no `content_hash`**. These two mandatory properties are marked `absent_for_shared_entity_types`. Writing them as `null` also strips any owner a pre-1.2.0 write left behind.
- is therefore **never matched** by `delete_non_curated_for_doc`'s owned-node delete.
- is **garbage-collected** at the end of each `delete_non_curated_for_doc` call, once it has no relationships left. This is a plain `DELETE`, not `DETACH`, so a node holding up any edge, curated or not, can't be removed.

Edges into a shared node are still owned by the document that wrote them, exactly as before.

**Requirement references are a property, not an edge.** `ISSUE` and `COMMIT` nodes carry `requirement_ids` (a list of normalised IDs, matched with the docx rule file's `id_pattern`). MCP tools join it to `REQUIREMENT.req_id` at query time. This works whatever order the work item and the spec were ingested in, and adds nothing new to the sink.

**Version:** `kg-schema` 1.1.0 → **1.2.0**. The bump is additive: no existing type changes meaning.

## Consequences
- The Graph page won't draw requirement ↔ issue links until it gains display-only derived edges, and those links can't be curated in v0.1. Revisit if curating them turns out to matter.
- A shared node that is deleted and then rewritten within one re-ingestion gets a fresh `created_at`. That's harmless, since the shared node holds no owned facts of its own.
- The GC query is global, not doc-scoped. Its cost scales with the number of `SOURCE_FILE` nodes, and an index on that label is cheap if it ever shows up in profiles.
- Future shared types (e.g. a tracker-independent requirement key) can be added to `shared_entity_types` without changing the sink.
