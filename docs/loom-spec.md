# Knotlore (repo: `loom`) — Project Specification

> **Audience:** Claude Code (implementation agent) and human reviewers.
> **Status:** v1.1 — amended for the Knotlore v0.1 scope (ADR-0027–0036). v1.0 was the Loom write-path spec.
> **Product name:** **Knotlore** — *give your AI assistant the requirements and history your code doesn't contain* ([ADR-0027](adr/0027-product-positioning-knotlore.md)). "Loom" remains the repo and module name until the rename (#36); this spec says "Loom" where it means the existing code.

---

## 1. Context and motivation

We have an existing internal tool, **NAA**, which grew to cover document parsing (Obsidian, docx), knowledge-graph ingestion, *and* MCP server hosting/configuration. It has become scattered: the write path (batch parsing, human-in-the-loop config) and the read path (long-running MCP services consumed by agents) were bundled into one app with one UI, and neither is served well.

Loom was first built as the write path alone, with NAA slimmed down to the read path separately. That split is superseded: **Knotlore is one product in one repo, grown from Loom** ([ADR-0028](adr/0028-one-product-loom-base-naa-read-side-merged-in.md)). NAA's knowledge-graph MCP server and its MCP plugin management move in; NAA's parsing code is retired, not ported again.

**Audience:** teams maintaining long-lived systems whose real requirements live in documents, not code. **First use case:** requirements traceability — spec/requirement ↔ issues ↔ commits/files ("which requirements does this file touch, where are they specified, and which issues changed them?"). The knowledge layer (ingestion + graph + knowledge MCP) is the product; the control-plane UI is supporting infrastructure (ADR-0027).

The engineering boundary survives inside the product. **Ingestion and the MCP server are separate processes that never communicate directly. The database is the contract**: ingestion writes to Neo4j; the MCP server reads from it. The shared graph schema (`kg-schema`) is the only coupling point and is treated as a versioned artifact (see §5). The MCP server never imports pipeline code.

**Public material is generic** (ADR-0027): no employer documents, schemas, rule files, system or company names. Demos and fixtures use synthetic data.

### Existing assets to reuse (lift, do not rewrite)

> **Corrected after grilling against the actual NAA source** (`D:\Cloned Projects\NAA`) — see [ADR-0001](adr/0001-lift-deterministic-extraction-not-llm.md). The extraction logic in NAA is **deterministic, regex/rule-based** — not LLM-based. There is no Obsidian CLI anywhere in NAA, no LlamaIndex usage in `pipeline/` or `webapp/`, and no benchmark harness matching an F1/KGGen/MINE-1 methodology. The mess in NAA is in the glue and the shell, not the core — that part of the original claim holds; the *mechanism* claim didn't.

- **Obsidian ingestion** — `NAA/pipeline/src/parser.py` + `config.py`: hand-rolled regex over raw `.md` text (wikilinks, a custom non-YAML header). Lift this as-is. Vault-specific classification config (folder→type map, keyword signals, relationship-inference keywords, included folders) moves into per-config YAML rather than staying hardcoded — see [ADR-0004](adr/0004-classification-rules-in-yaml-config.md).
- **docx extraction** — `NAA/webapp/src/docx_generic_parser.py` (`DocxRuleParser`): reads a YAML rule file and applies regex patterns to table rows. Lift this. Only the generic parent-link path is lifted, not NAA's project-specific `Flow → UseCase → Document` hierarchy or its unused `SqlView`/`OraclePackage` machinery — see [ADR-0006](adr/0006-generic-docx-parent-link-only.md).
- **Neo4j schema mapping** — NAA's real vocabulary seeds Loom's fixed, versioned entity/relationship enum; it is not lifted wholesale (docx's `BR` type is project-specific and excluded). See [ADR-0002](adr/0002-fixed-versioned-schema-not-dynamic-labels.md) and [ADR-0003](adr/0003-schema-vocabulary-source.md).

Source paths (resolved — no longer HUMAN INPUT REQUIRED):
- Obsidian: `NAA/pipeline/src/parser.py`, `NAA/pipeline/src/models.py`, `NAA/pipeline/src/config.py`
- docx: `NAA/webapp/src/docx_generic_parser.py`, example rule file `NAA/parsing-rules/br_requirements.yml`
- Neo4j writes: `NAA/pipeline/src/graph.py` (only `upsert_notes`/`upsert_relationships`/generic `upsert_requirements` are live — SQL/Oracle-specific methods are dead code, not lifted)

Treat these as read-only references; copy code into Loom's structure, adapting to the adapter protocols in §4.

---

## 2. Goals and non-goals

### Goals (the entire product)

Ingestion is **one pipeline** with pluggable sources and sinks. Core features:

1. Parse documents (docx first; xlsx/pptx later) into a **graph database** (Neo4j).
2. Parse an **Obsidian vault** into the graph database.
3. Ingest an **Azure DevOps Server** (on-prem, 2019+) project into the graph database: work items, the TFVC changesets associated with them, and unified diffs attached to them, linked to the files they change and the requirements they cite ([ADR-0035](adr/0035-azure-devops-server-tracker-tfvc-changesets-and-attached-diffs.md), superseding [ADR-0030](adr/0030-traceability-sources-git-history-and-issue-tracker.md)'s Jira and git-history choice). Read-only: ingestion never writes to the tracker.
4. Serve the graph to AI assistants through the **knowledge MCP server** (Streamable HTTP) with **traceability-shaped tools** ("which requirements does this file touch", "where is requirement X specified and which issues/commits changed it") rather than raw graph lookups ([ADR-0034](adr/0034-v0-1-release-scope-and-quickstart-criterion.md)).
5. **MCP plugin manifest v1** with support tiers: the control plane starts, stops, health-checks and registers MCP plugins, including external servers by URL ([ADR-0031](adr/0031-mcp-plugin-manifest-v1-and-support-tiers.md); tier list per ADR-0035).
6. Parse documents into a **vector database** (ChromaDB first) — **after v0.1** (ADR-0034).

Side features:

7. **User-friendly parsing-rule configuration** — a form-based editor generated from a JSON Schema of the YAML config format, with **live extraction preview** against a sample document. YAML remains the source of truth on disk.
8. **Graph correction canvas** — an NVL-based view where a user can create, retype, and delete relationships. Framed strictly as a *correction loop for extraction errors*, not a general graph editor. **After v0.1** (ADR-0034).
9. **Opt-in LLM-based prose extraction** — for docx documents' free-text sections (prose paragraphs, non-tabular content) that regex cannot meaningfully extract structured entities from. Runs against a local model (Ollama) only — no document content ever leaves the machine. Additive alongside regex extraction, not a replacement; see [ADR-0018](adr/0018-llm-prose-extraction-narrows-adr-0001.md)–[ADR-0022](adr/0022-partial-success-on-prose-extraction-failure.md). It stays opt-in and **off in the quickstart**: all core extraction and linking is deterministic (ADR-0027).

### Non-goals (hard boundaries — do not implement, do not scaffold "for later")

- ❌ Document storage, versioning, folders, or file permissions. Knotlore *points at* documents; it never becomes a document manager.
- ❌ A general-purpose MCP hub. Knotlore hosts its own knowledge MCP and can start, stop and register MCP plugins (ADR-0028, ADR-0031) — nothing more: no per-tool policy, proxying or marketplace features.
- ❌ A code graph. Code structure (classes, methods, call graphs) is never ingested; the graph holds only what an agent can't recover from the repository, and traceability ends at the file ([ADR-0029](adr/0029-no-code-graph-graph-holds-what-agents-cannot-derive.md)). Commits and file paths enter the graph only as link targets.
- ❌ Write actions on trackers during ingestion. Creating or updating issues belongs to optional MCP plugins (ADR-0030).
- ❌ Multi-tenancy, auth beyond a single shared instance, SharePoint integration. Knotlore targets a shared team server on a trusted network with no per-user auth in v0.1; every service binds to `127.0.0.1` unless the operator opts in to network exposure through one documented setting ([ADR-0032](adr/0032-trusted-network-deployment-localhost-default.md)). (The Instances page, [ADR-0025](adr/0025-instance-catalog-concept.md)/[ADR-0026](adr/0026-instances-nav-tab-amends-shell.md), is a catalog over this one shared instance, not an exception to this line — see [CONTEXT.md](../CONTEXT.md#instance).)
- ❌ A visual drag-and-drop rule builder. The form editor + preview (§7) is the ceiling for config UX in v1.
- ❌ General node CRUD in the graph canvas. v1 correction scope is **relationships only** (create/retype/delete). Node label/property editing is deferred.

---

## 3. Tech stack (fixed — do not substitute)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI | |
| Graph DB | Neo4j Community Edition (self-hosted), `neo4j` bolt driver | Driver lives in exactly one module (§4) |
| Vector DB | ChromaDB | Sink added in Phase 5 only — after v0.1 (ADR-0034) |
| Tracker access | `httpx` against the Azure DevOps Server REST API (WIQL, `api-version 5.0`) | Fixture mode is an injected `httpx` transport serving recorded files, not a second code path (ADR-0035) |
| MCP transport | Streamable HTTP | SSE is deprecated in the MCP spec; servers moving in from NAA migrate (ADR-0031) |
| Operational store | SQLite | Jobs, hashes, correction log — never in Neo4j |
| Extraction | Stdlib `re` (regex) for tabular content; opt-in local LLM (Ollama) for prose content | Regex is deterministic, rule-driven — see [ADR-0001](adr/0001-lift-deterministic-extraction-not-llm.md). Prose extraction is additive and opt-in per rule file — see [ADR-0018](adr/0018-llm-prose-extraction-narrows-adr-0001.md)–[ADR-0022](adr/0022-partial-success-on-prose-extraction-failure.md) |
| Local LLM serving | Ollama (self-hosted, `docker-compose`) | HTTP-local only — document content never leaves the machine. See [ADR-0019](adr/0019-ollama-local-llm-serving.md) |
| Frontend | React + Vite + TypeScript + Tailwind | |
| Graph rendering | `@neo4j-nvl/react` (fall back to `@neo4j-nvl/base` if the wrapper is limiting) | Set `disableTelemetry: true` in nvlOptions |
| Rule form | react-jsonschema-form (or equivalent JSON-Schema-driven form lib) | |
| API client | Generated from FastAPI's OpenAPI schema, never hand-written | A backend contract change that breaks the frontend fails at typecheck in CI ([ADR-0033](adr/0033-frontend-adrs-apply-product-wide-generated-api-client.md)) |

**Security invariant:** the bolt driver and all DB credentials live exclusively in server-side processes (the backend and the knowledge MCP server). The browser never connects to Neo4j directly.

---

## 4. Architecture

### 4.1 Pipeline (the core abstraction)

```
[SourceAdapter] → [Extraction] → [RuleEngine] → [SinkAdapter(s)]
```

Everything is one pipeline. Obsidian, docx and Azure DevOps Server are source adapters; Neo4j vs ChromaDB are sink adapters; "parse to both" is two sinks on one extraction output. Every source gets the same incremental, curated-immunity and tombstone behaviour (§6). Ingestion plugins are not a formal contract in v0.1: new sources implement this internal `SourceAdapter` protocol (ADR-0031).

```python
# pipeline/sources/base.py
class SourceAdapter(Protocol):
    source_type: str  # "obsidian" | "docx" | "azure_devops" | ...

    def discover(self, source_path: str) -> list[SourceDoc]:
        """Enumerate documents. SourceDoc carries path, doc_id, content_hash."""

    def load(self, doc: SourceDoc) -> LoadedDoc:
        """Read one document into text + structural metadata.
        For Obsidian: wikilinks are emitted as explicit edges here,
        tagged origin='explicit' — they bypass extraction inference."""
```

```python
# pipeline/sinks/base.py
class SinkAdapter(Protocol):
    sink_type: str  # "neo4j" | "chroma" | "dryrun"

    def write(self, doc_id: str, result: ExtractionResult) -> SinkReport: ...
    def delete_non_curated_for_doc(self, doc_id: str) -> int:
        """Remove origin='extracted' AND origin='explicit' elements sourced
        from doc_id, skipping any that are tombstoned as deleted (§6.4).
        Never touches origin='curated'. See §6.1, §6.2, ADR-0009, ADR-0010."""
```

```python
# pipeline/core.py
class Pipeline:
    def run(self, source: SourceAdapter, source_path: str,
            sinks: list[SinkAdapter], config: ParsingConfig,
            progress: ProgressCallback) -> JobResult:
        # 1. discover docs; compare content_hash against SQLite → skip unchanged
        # 2. per changed doc: load → extract → apply rules
        # 3. per sink: delete_non_curated_for_doc(doc) → write(result)
        # 4. diff discovered doc_ids against SQLite's previously-seen set;
        #    for each doc_id now missing, treat as removed: delete_non_curated_for_doc(doc)
        #    on every sink, then drop its SQLite hash-table row (ADR-0008)
        # 5. detect orphaned curated edges (§6.3) → include in JobResult
        # 6. record hashes + per-doc status (including "removed") in SQLite
```

**Design test:** the `preview` endpoint (§8) must be implementable as `Pipeline.run` with a `DryRunSink` that collects instead of writes. If preview needs a separate code path, the abstraction has failed — fix the abstraction.

### 4.2 Repository layout

```
loom/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── jobs.py
│   │   │   ├── configs.py
│   │   │   └── graph.py
│   │   ├── pipeline/
│   │   │   ├── core.py
│   │   │   ├── types.py            # SourceDoc, LoadedDoc, ExtractionResult, JobResult
│   │   │   ├── sources/{base,obsidian,docx,azure_devops}.py
│   │   │   ├── extraction/{chunking,entities,prose_llm}.py   # prose_llm.py: Phase 6, ADR-0018 — calls Ollama, never core.py or other sources
│   │   │   ├── rules/{engine,schema}.py
│   │   │   └── sinks/{base,neo4j,vector,dryrun}.py
│   │   ├── jobs/{runner,store}.py
│   │   └── db/neo4j_client.py      # the ONLY module importing the bolt driver
│   ├── cli.py                      # Phase 1 entry point: run pipeline without API/UI
│   └── tests/
│       └── fixtures/               # mini Obsidian vault + sample docx files
├── frontend/
│   └── src/
│       ├── pages/{Landing,Ingest,Rules,Graph,Instances,Plugins}.tsx
│       ├── components/
│       └── api/                    # generated from OpenAPI (ADR-0033)
├── mcp/                            # knowledge MCP server + plugin manifests (exact layout decided at the move, ADR-0028)
└── kg-schema/
    ├── schema.json                 # source of truth (§5)
    ├── __init__.py                 # Python constants derived from schema.json
    └── VERSION
```

`kg-schema/` is the contract both processes import: the pipeline writes against it and the knowledge MCP server reads against it. Write it so it can be extracted into a standalone package (no imports from `app/`).

---

## 5. The schema contract (`kg-schema`)

`schema.json` defines, versioned (current: **1.2.0**). Rule files and source adapters map their output onto an entity/relationship type already in this enum — they never declare a Neo4j label directly (see [ADR-0002](adr/0002-fixed-versioned-schema-not-dynamic-labels.md)):

- **Entity types:**
  - *Obsidian* (seeded from NAA's real classifier — see [ADR-0003](adr/0003-schema-vocabulary-source.md)): `ARCHITECTURE`, `CONVENTION`, `TASK`, `BUSINESS_TERM`, `NOTE`, `TAG`.
  - *Docx*: `REQUIREMENT` (added in 1.1.0 with the first docx rule file). It is the generic type; project-specific labels such as NAA's `BR` are ID *prefixes* matched by the rule file's `id_pattern`, never types (ADR-0030).
  - *Traceability* (1.2.0, [ADR-0036](adr/0036-traceability-types-and-shared-entity-nodes.md)): `ISSUE` (tracker-agnostic; carries `tracker`, e.g. `azure-devops`, and `kind`, e.g. Bug/Task/PBI — an Azure DevOps work item), `COMMIT` (a git commit or a TFVC changeset alike; carries `vcs: git | tfvc` and its native id), `SOURCE_FILE` (keyed by code root + normalised repo-relative path; raw paths kept as properties — ADR-0035).
- **Relationship types:**
  - *Lifted from NAA's wikilink-context keyword map:* `DEPENDS_ON`, `EXTENDS`, `USES`, `CONNECTS_TO`, `IMPLEMENTS`, `RELATES_TO`, `FIXES`, `RESOLVES`, `CAUSED_BY`, `FOLLOWS`, `VIOLATES`, `LINKS_TO` (default when no keyword matches), `TAGGED_WITH` (tag-section wikilinks).
  - *Traceability (1.2.0):* `REFERENCES` (commit → issue: a changeset associated with a work item) and `CHANGES` (commit → source file, and issue → source file from an attached diff). Both are `origin: explicit` and carry a **`via`** property recording link provenance (`changeset 123`, `attachment fix.diff`). The wikilink-derived types are not reused for these, because they claim meaning the source never states.
- **Requirement references are a property, not an edge.** `ISSUE` and `COMMIT` nodes carry `requirement_ids` (normalised IDs matched with the docx rule file's `id_pattern`). The knowledge MCP joins them to `REQUIREMENT.req_id` at query time, so the link works whatever order the work item and the spec were ingested in (ADR-0036).
- **Shared entity types** (`shared_entity_types`; 1.2.0: `SOURCE_FILE` only). A shared node is linked to by many documents and **owned by none**: it is written without `source_doc` and `content_hash` (written as `null`, which also strips an owner a pre-1.2.0 write left behind), so no document's cleanup deletes it, and it is garbage-collected once no relationship is left on it (§6.7). Edges into a shared node are still owned by the document that wrote them.
- **Mandatory properties on every node and relationship written by the pipeline:**

| Property | Type | Values / notes |
|---|---|---|
| `origin` | string | `extracted` (inferred by pipeline) · `explicit` (ground truth from source, e.g. wikilinks, changeset associations, diff headers) · `curated` (created/edited by a human in the canvas) |
| `source_doc` | string | doc_id of originating document; absent on `curated` and on shared entity types |
| `content_hash` | string | hash of source doc at write time; absent on `curated` and on shared entity types |
| `rule_id` | string | id of the parsing rule that produced it; absent on `explicit`/`curated` |
| `schema_version` | string | value of `kg-schema/VERSION` at write time |
| `created_at` / `updated_at` | ISO 8601 | |

Adding new entity/relationship types (or new shared entity types) later is a schema-version bump. The Python constants module is generated from (or validated against) `schema.json` in CI — the JSON is authoritative. The knowledge MCP server reads against the same `kg-schema`; it is the only contract between ingestion and the MCP server (ADR-0028).

---

## 6. Behavioral invariants (the rules that keep this sane)

### 6.1 Incremental by default
Every job computes `content_hash` per discovered document and compares against SQLite. Unchanged docs are **skipped** and reported as such. Changed docs are re-processed: `delete_non_curated_for_doc` then `write`. A document removed from the source entirely (no longer found by `discover()`) is treated the same way — `delete_non_curated_for_doc` runs against it and its SQLite hash-table row is dropped (see ADR-0008). There is no separate "full re-ingest" button in v1; deleting the SQLite hash table is the escape hatch for a from-scratch rebuild.

`delete_non_curated_for_doc` removes both `origin: extracted` **and** `origin: explicit` elements sourced from the doc (e.g. a wikilink removed from a note's body is cleaned up on re-ingestion, not left stale forever — see ADR-0009). `origin: curated` is never touched, and any edge tombstoned per §6.4 is skipped on rewrite rather than recreated. Shared entity nodes are never matched by it, since they have no `source_doc`; they are garbage-collected instead (§6.7).

For the Azure DevOps Server source, a "document" is **one work item** (owning its `ISSUE` node, its diff-derived `CHANGES` edges and its `requirement_ids`) or **one changeset** (owning its `COMMIT` node and that commit's `REFERENCES`/`CHANGES` edges). Re-ingestion is incremental from a `System.ChangedDate` watermark; changesets never change after check-in, so the content hash skips them. A work item that leaves the instance's query is treated as a removed document (ADR-0035, ADR-0036).

### 6.2 Curated is immune
Elements with `origin: curated` survive every re-ingestion, unconditionally. If a re-parse produces an extracted or explicit edge duplicating a curated edge (same endpoints + type), **the curated edge wins** and the duplicate is not written. Correspondingly, `POST /graph/relationships` (§8) MERGEs on `(from_id, to_id, type)`: creating a relationship over an already-existing edge of that type **promotes** it to curated rather than creating a parallel duplicate (see ADR-0011).

### 6.3 Orphans are flagged, never auto-deleted
If re-ingestion (including a doc-removal cleanup, §6.1) removes a node that a curated edge depends on, do **not** delete the curated edge and do not silently keep a dangling reference. Mark the edge `orphaned: true`, surface it in the `JobResult`, and let the human resolve it in the Graph page. Automation never overrules a person silently.

### 6.4 Corrections are logged, and deletions are tombstoned
Every canvas action writes to the SQLite `corrections` table **before** the graph write:

```sql
corrections(id, timestamp, action /* create|retype|delete */,
            rel_type, from_node_id, to_node_id,
            originating_rule_id /* nullable — the rule that created the edge being corrected */)
```

Purpose: per-rule correction-rate analytics later ("rule X has a 30% correction rate"). No analytics UI in v1 — just capture the data.

A `delete` correction is durable across re-ingestion: it acts as a **tombstone** that `delete_non_curated_for_doc`'s rewrite step consults, so a human's deletion of an extracted or explicit edge isn't silently undone the next time its source doc is reprocessed and would otherwise still produce it. This is symmetric with §6.2's curated-wins rule for creates/retypes (see ADR-0010). Phase 4's gate (§10) includes asserting that a deleted edge stays deleted across a subsequent re-ingestion.

### 6.5 One driver, one door
Within the backend, all Cypher goes through `db/neo4j_client.py`. Sinks and API modules call it; nothing else in the backend imports the driver. The knowledge MCP server is a separate process that only reads the graph; it has its own single driver module and never imports backend or pipeline code (ADR-0028).

### 6.6 Instances are a catalog, not a partition
An **Instance** ([ADR-0025](adr/0025-instance-catalog-concept.md)) is identified by source type + source path + sink(s) only — the rule config is mutable across its history. For Azure DevOps Server, the "source path" is **collection + project, with an optional area-path or WIQL filter** (ADR-0035). Every job belongs to exactly one instance (`jobs.instance_id`, `NOT NULL`); there is no more anonymous run. Deleting an instance removes only its catalog bookkeeping — name, config link, job history — never the graph/vector data its runs wrote, since nodes/edges carry no `instance_id` tag. See [CONTEXT.md](../CONTEXT.md#instance).

### 6.7 Shared nodes are owned by none, and collected when unlinked
A node of a shared entity type (§5) is written with no `source_doc`/`content_hash`, so no document owns it. At the end of each `delete_non_curated_for_doc` call, every shared node with no relationships left is deleted with a plain `DELETE` (not `DETACH DELETE`), so a node still holding any edge — curated or not — can't be removed. This keeps work item A's links into a file intact when work item B, which links the same file, is re-ingested ([ADR-0036](adr/0036-traceability-types-and-shared-entity-nodes.md)).

### 6.8 Both link sources are kept
When a TFVC changeset and an attached diff both link a work item to files, **both** links are written, each with its own `via`. Knowledge MCP tools return the union and show where each link came from; a disagreement between delivered and checked-in scope is information, not noise (ADR-0035).

---

## 7. Parsing-rule configuration

- Configs are **YAML files on disk**, the source of truth. The API reads/writes them; the UI never invents a second format.
- `pipeline/rules/schema.py` defines a **JSON Schema** for the config format, derived from NAA's real rule-file shape (`NAA/parsing-rules/br_requirements.yml`, lifted per [ADR-0001](adr/0001-lift-deterministic-extraction-not-llm.md)) — not chunking parameters. See `id`/`rule_id` in [CONTEXT.md](../CONTEXT.md#rule-id).
- The Rules page renders a form **generated from the JSON Schema**. Validation errors surface inline before save.
- **Live preview** is the centerpiece: user picks a fixture or uploads a sample doc, the backend runs the real pipeline with `DryRunSink`, and the UI shows extracted entities and relationships (a simple list/table is sufficient in v1; rendering the preview in NVL is a nice-to-have, not required). Rule editing without preview is the failure mode this feature exists to eliminate — "writing YAML blind and discovering it's wrong after a 20-minute run."

Config shape (resolved against NAA's real format — see [CONTEXT.md](../CONTEXT.md#rule-file)):
- **Docx rule files:** `id_pattern`/`id_format` (item-id recognition), `title_from`, `category_signals` (regex, all matches collected), `named_extractions` (regex with `group`/`transform`/`filter`/`deduplicate`/`sort`), `context` collection flags. Each `category_signal`/`named_extraction` carries a stable `id` in addition to its editable `name` (see below).
- **Docx `context.prose_extraction` (opt-in, default off):** `enabled`, a stable generated `id` (same pattern as above), `target_entity_types`/`target_relationship_types` (subsets of `kg-schema`'s enum). Runs a local LLM (Ollama) over the same prose text already collected by `context.include_paragraphs`/`include_non_br_tables`, alongside — not instead of — the regex path above. See [ADR-0018](adr/0018-llm-prose-extraction-narrows-adr-0001.md).
- **Obsidian source config:** folder→entity-type mapping, fallback keyword signals, relationship-inference keywords, and which vault folders to scan — moved out of NAA's hardcoded Python into this same per-config YAML (see [ADR-0004](adr/0004-classification-rules-in-yaml-config.md)).
- **Azure DevOps Server source config** (ADR-0035): collection URL and project, an optional area-path or WIQL filter, credentials (a personal access token is the documented path; username/password basic auth is also accepted — both stored per source config, never committed), **prefix mappings** that normalise TFVC server paths, diff paths and checkout paths to one code root + repo-relative path, the diff-attachment filename glob (default `*.diff, *.patch`), and the requirement `id_pattern` (the same pattern the docx rule file uses) for scanning work-item text fields. Spec documents attached to a work item are linked to the already-ingested document they match by filename or content hash. It gets a JSON Schema so the Configs API and the Rules page can edit and preview it like any other config (ADR-0030).
- No chunking parameters. Regex rules take no LLM prompts and remain deterministic pattern matching (ADR-0001); the opt-in `prose_extraction` block above is the one exception, scoped to prose content only.

**Rule IDs must be stable across edits** — they are the join key for correction analytics (§6.4). Each `category_signal`/`named_extraction` gets a separate, generated `id` field independent of its editable `name`; the Rules page form never lets renaming change the `id`. See [ADR-0005](adr/0005-stable-rule-id-separate-from-name.md).

---

## 8. API surface (complete — do not grow without spec change)

```
POST   /jobs                      {instance_id, config_id} → {job_id}
GET    /jobs                      → job history (paginated); ?instance_id= filters to one instance
GET    /jobs/{id}                 → status, progress %, per-doc results
                                    (skipped | updated | failed | orphan-flags)
POST   /jobs/{id}/cancel

POST   /instances                 {name?, source_type, source_path, sinks[]} → {instance_id}
                                    (name auto-generated from source_path if omitted; rejects
                                    a duplicate (source_type, source_path, sinks), ADR-0025)
GET    /instances                 → list, most-recently-run first
GET    /instances/{id}            → source_type, source_path, sinks, latest job summary
PATCH  /instances/{id}            {name} → rename
DELETE /instances/{id}            → catalog-only (ADR-0025); underlying graph/vector data untouched

GET    /configs                   → list rule sets
GET    /configs/{id}
POST   /configs                   (validated against JSON Schema)
PUT    /configs/{id}
POST   /configs/{id}/preview      {sample: fixture_id | uploaded file} → ExtractionResult (no writes)

GET    /graph/subgraph            ?center_id&depth&types[] → {nodes[], relationships[]} shaped for NVL
GET    /graph/search              ?q= → node hits (to find a center node for the canvas)
POST   /graph/relationships       {from_id, to_id, type} → MERGE on (from_id, to_id, type):
                                    creates with origin=curated, or promotes an existing
                                    same-type edge to curated if one already exists (ADR-0011) (logs §6.4)
PUT    /graph/relationships/{id}  {type} → retype; origin becomes curated              (logs §6.4)
DELETE /graph/relationships/{id}  → logs §6.4 first (tombstones the edge, ADR-0010), then deletes

GET    /plugins                   → every plugin manifest (ADR-0031): id, label, support tier
                                    (core | maintained | example), local or external, status/health,
                                    and the connection details an AI assistant needs
GET    /plugins/{id}              → one plugin: manifest, status, credential fields (secret values never returned)
POST   /plugins                   {manifest} → register a plugin; an external server needs only its URL
                                    (manifest validated against its versioned JSON Schema)
POST   /plugins/{id}/start        → local plugins only
POST   /plugins/{id}/stop         → local plugins only
PUT    /plugins/{id}/credentials  {fields} → writes the plugin's own env file (never committed)
```

The `/plugins` block is the v0.1 surface for MCP/plugin status and management; exact request/response shapes are fixed by #33. The knowledge MCP's own traceability tools are MCP tools served on its Streamable HTTP endpoint, not REST routes of the backend.

Jobs run in-process via async task + a runner that supports progress reporting and cancellation. No external queue (no Celery/Redis) — single-user/small-team tool; SQLite job store is enough.

The built frontend is served by the FastAPI backend, so the product deploys as one service ([ADR-0033](adr/0033-frontend-adrs-apply-product-wide-generated-api-client.md)); its TypeScript client is generated from this API's OpenAPI schema.

Relationship creation validates `type` against `kg-schema` and rejects unknown types. `GET /graph/subgraph` enforces a node cap (default 300) and returns a `truncated` flag when hit.

---

## 9. Frontend pages

ADRs 0013–0017 and 0023–0026 govern the whole UI, including pages that came from NAA; NAA's UI is not ported (ADR-0033). The top nav grows beyond Ingest/Rules/Graph/Instances to MCP/Plugins (v0.1) and Settings (later).

**v0.1 pages** (ADR-0034): Landing, Ingest (with Instances), Rules, Instances, MCP/Plugins. The Graph page (correction canvas) ships **after v0.1**.

### Landing
Entry point at `/`, outside the nav shell (ADR-0023) — no persistent top nav, branding-only navbar. Compact hero copy plus shortcut cards visible without scrolling, each a single click straight into the Ingest page with source and sink pre-filled. The cards **lead with the traceability flow** (ADR-0027, ADR-0034), alongside Obsidian→Graph and Documents→Graph; the Documents→Vector card waits until the vector sink ships after v0.1. A plain link ("configure manually") drops into the blank Ingest form for the source×sink combinations the cards don't cover.

### Ingest
Instance picker first (ADR-0026): choose an existing instance (pre-fills source type, path, sink, and config from its last run) or "New instance" + a name field (auto-named from path if left blank, ADR-0025). Each doc folder, vault or Azure DevOps project is an Instance. Then: source type picker (Obsidian / docx folder / Azure DevOps Server) → path input (for Azure DevOps: collection + project, optional area-path/WIQL filter) → sink checkboxes (graph; vector after v0.1) → config selector → Run. Accepts pre-filled source/sink values when arriving from a Landing card, landing on "New instance." Live progress (poll `GET /jobs/{id}`; SSE is explicitly avoided — it has caused problems in our corporate proxy environment). Results table per doc: skipped / updated / failed / orphan warnings, with error detail expandable.

### Rules
Two panes. Left: schema-generated form for the selected config. Right: preview panel with two tabs (ADR-0024) — Table: sample selector, "Preview" button, extracted entities & relationships table with the `rule_id` that produced each; Graph: an NVL-rendered, read-only rendering of the same preview call's output (all edges `origin: extracted`, styled per ADR-0017), click-to-inspect a node/edge via a side panel showing its properties. Both tabs populate from the same "Preview" click — no per-keystroke live update, no merge with existing Neo4j graph state. Save writes YAML.

### Graph *(after v0.1)*
Search box → pick center node → NVL canvas renders `subgraph`. Interactions, in NVL terms:
- Click = select (NVL selection state); Ctrl/Cmd-click = multi-select.
- With exactly two nodes selected in order: "Create relationship" button → type dropdown (from kg-schema) → `POST /graph/relationships` → `addAndUpdateElementsInGraph` to sync canvas without refetch.
- Select an edge: side panel shows properties (`origin`, `rule_id`, `source_doc`) + Retype / Delete actions → `removeRelationshipsWithIds` on success.
- Visual encoding: edge style differs by `origin` (e.g. solid = explicit, dashed = extracted, colored = curated); `orphaned: true` edges rendered in warning color.
- Expand-node (fetch neighbors of a node and merge into canvas) is in scope; it is a second `subgraph` call centered on that node.

No node creation, no node property editing, no bulk operations in v1. Requirement ↔ issue links are a property joined at query time (§5), so the canvas doesn't draw them until it gains display-only derived edges, and they can't be curated (ADR-0036).

### Instances
Fourth persistent nav tab (ADR-0026). List view (`/instances`): name, source type + path, sink(s), config in use, most recent run's status + timestamp, job count — sorted most-recently-run first. Row click → detail view (`/instances/{id}`): full job history (`GET /jobs?instance_id=`), rename, "Run again" (navigates to Ingest pre-filled from the instance's last run), delete (catalog-only, ADR-0025).

### MCP/Plugins
Nav tab (ADR-0033). Lists every plugin from its manifest (`GET /plugins`): label, **support tier** (core / maintained / example), local or external, status/health, and the connection details users need to configure their AI assistant. Start/stop for local plugins, credential entry, and registering an external server by URL. v0.1 tiers (ADR-0035): **core** — the knowledge MCP; **maintained** — Azure DevOps; **example** — Jira, Git, Jenkins, Oracle.

---

## 10. Build phases and acceptance criteria

Each phase has a gate; a phase is done only when its gate passes. Phases 1–6 were the original Loom plan, built in order except that Phase 6 landed before Phases 3–5 finished. The v0.1 release (ADR-0034) needs Phases 1–3 and 7–10; **Phases 4 and 5 move to after v0.1**. Within the v0.1 phases, follow the issue dependencies (#31 needs the 1.2.0 schema; #33 needs #32; #35 needs everything else).

### Phase 1 — Pipeline core via CLI (no API, no UI)
Lift NAA extraction into the adapter architecture. `cli.py` runs: `python cli.py ingest --source obsidian --path ./fixtures/vault --sink neo4j --config default.yml`.

**Gate:**
- Fixture vault and fixture docx set ingest successfully into a local Neo4j.
- Obsidian wikilinks appear as `origin: explicit` edges; inferred edges as `origin: extracted` with a `rule_id`.
- Re-running with no changes reports all docs skipped and performs zero graph writes.
- Modifying one fixture doc and re-running updates only that doc's extracted elements.
- A manually inserted `origin: curated` edge survives the re-run (§6.2), and deleting its endpoint's source content flags it orphaned (§6.3).
- **Golden-fixture parity check:** run NAA's current parser and Loom's ported adapter against the same fixture vault/docx and assert the extracted nodes/edges match — proves the port preserved NAA's behavior. Replaces the original F1-benchmark language, which assumed LLM-based extraction; see [ADR-0007](adr/0007-golden-fixture-parity-gate.md).

### Phase 2 — Job runner + FastAPI (jobs, configs, preview)
**Gate:** a job started via `POST /jobs` is observable through completion via polling; cancel works mid-run; `preview` returns the identical extraction a real run would produce for the same doc+config (assert by comparison in a test); invalid config rejected with schema errors.

### Phase 3 — Rules page
**Gate:** a user can open a config, change a rule, preview against a fixture, see the diff in extracted output in both the table and the graph view (ADR-0024), and save — without touching a YAML file by hand. The saved YAML round-trips (load → form → save) byte-stably apart from formatting.

### Phase 4 — Graph page *(after v0.1)*
**Gate:** search → render subgraph → create a typed relationship between two selected nodes → it persists in Neo4j with `origin: curated` → a subsequent re-ingestion of the underlying docs leaves it intact. Delete and retype work and are recorded in `corrections`; a deleted edge stays deleted across a subsequent re-ingestion of its source doc (tombstoning, ADR-0010), not silently recreated. Creating a relationship over an already-existing same-type edge promotes it to curated rather than duplicating it (ADR-0011). Edge styling reflects `origin`.

### Phase 5 — Vector sink *(after v0.1)*
**Gate:** adding ChromaDB touches only `pipeline/sinks/vector.py` + registration + UI checkbox. If it requires edits to `core.py` or source adapters, stop and fix the abstraction instead. "Both" sinks in one job produces graph + vector output from a single extraction pass. The vector sink chunks each document's raw text independently of the entity-extraction rule engine and embeds those chunks (ADR-0012); chunking parameters live in sink-specific config, not the rule YAML (§7).

### Phase 6 — LLM-based prose extraction (opt-in, docx only)
**Gate:** a rule file with `context.prose_extraction.enabled: true` and a `target_entity_types`/`target_relationship_types` subset, run against a fixture docx with prose sections, produces `origin: extracted` entities/relationships tagged with the `prose_extraction` block's stable `id` as `rule_id` — merged into the same `ExtractionResult` as that document's regex-derived output, without disturbing it. Re-running with an unchanged document, model, and `prompt_version` skips prose re-extraction (§6.1 semantics); bumping either the model or `prompt_version` forces re-extraction via `delete_non_curated_for_doc` + rewrite (ADR-0020), leaving curated edges untouched (§6.2) and tombstones honored (§6.4). Ollama being unreachable mid-run degrades that document to partial success — regex output still writes, a warning surfaces, the job continues (ADR-0022) — rather than failing the document or the job. The recall-oriented fixture gate (ADR-0021) passes: all "must contain" items from the curated prose fixture appear in output.

### Phase 7 — Azure DevOps Server source adapter (#31)
**Gate:** run through the real adapter in fixture mode (an injected `httpx` transport serving recorded, synthetic REST responses — no live server), an instance produces one `ISSUE` document per work item and one `COMMIT` document per changeset. Changeset associations become `REFERENCES` edges and changed files become `CHANGES` edges; attached diffs matching the glob become `CHANGES` edges from the issue; every link carries its `via`, and changeset and diff links to the same file are both kept (§6.8). TFVC, diff and checkout paths for the same file land on one `SOURCE_FILE` node via the prefix mappings. `requirement_ids` holds the IDs the work item's text fields cite. Re-ingesting work item B leaves work item A's links into a shared file intact, and an unlinked `SOURCE_FILE` is collected (§6.7). An unchanged re-run skips every document; a work item leaving the query is cleaned up like a removed document. PAT and username/password both authenticate.

### Phase 8 — Knowledge MCP server (#32)
**Gate:** the knowledge MCP moves in from NAA as a separate process on Streamable HTTP, reading the graph against `kg-schema` and importing no pipeline code. Its traceability tools answer "which requirements does this file touch", "where is requirement X specified" and "which issues/commits changed it" by joining `requirement_ids` to `REQUIREMENT.req_id` at query time, returning the union of link sources with each link's `via`. Tests run against fixtures, without a live Azure DevOps Server.

### Phase 9 — MCP plugin manifest v1 + MCP/Plugins page (#33)
**Gate:** the manifest has a versioned JSON Schema and invalid manifests are rejected with a clear error; external servers can be registered by URL only; the UI shows each plugin's support tier and status; credentials are written to the plugin's own env file and never committed.

### Phase 10 — Quickstart, frontend CI and rename (#34, #35, #36)
**Gate (the v0.1 release criterion, ADR-0034):** from a fresh clone, `docker compose up` brings up **one** Neo4j, the backend serving the built UI, and the knowledge MCP, all bound to `127.0.0.1` by default (ADR-0032), and gives a working traceability answer from the bundled **synthetic sample project** — an Obsidian vault, a docx spec with requirement tables, and recorded Azure DevOps REST fixtures with work items, attached `.diff` files and associated TFVC changesets (ADR-0035) — **in under 5 minutes**. CI has a frontend job (generate client → typecheck → lint → build) and a stale generated client fails it. The README and package names say Knotlore and state plainly: no authentication — run only on a trusted network.

---

## 11. Testing expectations

- Unit tests for: hash-skip logic, curated-immunity, orphan detection, rule engine application, schema validation of configs.
- Integration test per phase gate, runnable against a disposable Neo4j (docker-compose file included in repo).
- Fixtures: a mini Obsidian vault (≥ 8 notes with wikilinks, at least one note that links to a non-existent note) and ≥ 3 docx files (one plain prose, one with tables, one that intentionally triggers zero extractions).
- Phase 6 only: a recall-oriented (subset-assertion, not exact-match) fixture for the LLM prose-extraction path — see [ADR-0021](adr/0021-recall-oriented-test-gate-for-llm-extraction.md). Requires a local Ollama instance in CI/dev, distinct from the disposable-Neo4j requirement above.
- Azure DevOps adapter and knowledge MCP (Phases 7–8): tests against **synthetic recorded REST fixtures** through the fixture-mode `httpx` transport. The golden-fixture parity gate (ADR-0007) doesn't apply to them. Those fixtures double as the quickstart's sample project; no test or quickstart step needs a live Azure DevOps Server (ADR-0035).
- Every fixture is synthetic and contains no employer data (ADR-0027).

## 12. Explicitly deferred (recorded so they are not re-litigated)

**After v0.1** (ADR-0034, ADR-0035): graph correction canvas (Phase 4) · vector sink / ChromaDB (Phase 5) · git history source adapter (reuses the `COMMIT` type unchanged; picks up `AB#123`-style links if the team adopts them) · Jira Data Center/Server and GitHub/GitLab issue adapters · authentication (per-user tokens, then OAuth — revisit on the first untrusted network, ADR-0032) · a formal ingestion plugin contract · Settings page · display-only derived requirement ↔ issue edges in the canvas, and curating them (ADR-0036).

**Deferred indefinitely:** xlsx/pptx source adapters · node CRUD in canvas · correction-rate analytics UI · visual rule builder (editing rules by manipulating a graph directly — distinct from the read-only preview graph reopened by ADR-0024) · SharePoint · multi-tenancy · full-reingest UI · per-instance graph partitioning (tagging nodes/edges with `instance_id` — the Instances page, ADR-0025, is catalog-only and doesn't need this).

**Not deferred — ruled out:** a code graph (ADR-0029) · a general-purpose MCP hub (ADR-0028) · LLM-based extraction in the core path (ADR-0027).

## 13. Open items requiring human input before Phase 1

Items 1–4 were resolved by grilling against the actual NAA source (`D:\Cloned Projects\NAA`) — see §1, §5, §7, and `docs/adr/0001`–`0007`.

1. ~~Paths to NAA source~~ — resolved, see §1.
2. ~~Example of the current NAA YAML parsing config~~ — resolved: `NAA/parsing-rules/br_requirements.yml`, see §7.
3. ~~Location of the extraction validation dataset~~ — moot: no such dataset or LLM-benchmark harness exists in NAA; replaced by the golden-fixture parity gate (ADR-0007).
4. ~~Confirmation of Obsidian mappings~~ — resolved: note→type and wikilink→relationship mappings are real code (`NAA/pipeline/src/config.py`), now moving into per-config YAML (ADR-0004) rather than staying fixed.
5. Neo4j and ChromaDB connection details for local dev (put in `.env`, never in code) — still open; an operational/setup task, not a design decision.
