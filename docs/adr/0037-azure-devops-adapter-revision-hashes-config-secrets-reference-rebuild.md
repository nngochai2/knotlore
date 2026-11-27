# 0037 — Azure DevOps adapter: revision hashes, filter and secrets in config, and rebuilding REFERENCES

## Status
Accepted (2026-11-27). Amends ADR-0035 (watermark, Instance filter, credential storage) and ADR-0036 (changeset document hash). Everything else in those ADRs still holds.

## Context
Designing the Azure DevOps Server adapter (#31) against the real pipeline and sink showed four places where ADR-0035/0036 don't fit the code:

- **Watermark.** ADR-0035 says re-ingestion is incremental from a `System.ChangedDate` watermark. But `Pipeline.run` detects removed documents by diffing `discover()`'s full result against SQLite, so `discover()` has to list every in-scope work item on every run anyway. `content_hash` is an opaque string compared between runs, so a separate watermark would be redundant state.
- **Instance filter.** ADR-0035 makes the area-path/WIQL filter part of the Instance. Instance identity is `source_type + source_path + sinks` and is immutable (ADR-0025), so editing the filter would orphan the old Instance and start a new one.
- **Credentials.** ADR-0035 stores them "per source config". `GET /configs/{id}` returns the whole config YAML to the browser, and config folders are easy to commit by accident.
- **Lost `REFERENCES` edges.** The sink `DETACH DELETE`s every node a document owns before rewriting it. When a work item changes, its `ISSUE` node is rebuilt, and the `REFERENCES` edges that *unchanged* changeset documents wrote into it are deleted with it. ADR-0036 makes the changeset document own those edges, and a changeset never changes, so its hash would skip it and the edges would never be written again.

Resolved in a `/grilling` session on 2026-11-27.

## Decision

**Revision as content hash, no watermark.** Each run, one WIQL query lists every in-scope work item ID (WIQL caps results at 20,000, which is documented as a v0.1 limit). A batched fetch reads each item's `System.Rev`, and `content_hash = rev:<n>`. Any change bumps the revision, including a new attachment or a newly associated changeset. The pipeline's existing hash skip does the rest.

**Changesets.** Only changesets linked from in-scope work items are discovered. A changeset's `content_hash` is its id plus the sorted `(work item id, rev)` pairs of the in-scope work items that link to it, and `discover()` lists **all work items before all changesets**. A changed work item therefore re-ingests its changesets later in the same run, after its `ISSUE` node is rebuilt, and their `REFERENCES` edges are rewritten. A changeset that no in-scope work item links to anymore drops out of discovery and is cleaned up as a removed document.

**Filter in the config.** An Azure DevOps Instance's `source_path` is `https://<server>/<collection>/<project>`. The filter (`area_paths`, matched with `UNDER`, and an optional raw `wiql_where` clause, ANDed) lives in the source config, which may change over an Instance's history. Narrowing it removes work items through normal removed-document cleanup. A `source_path` of `fixture:<dir>` selects the file-serving `httpx` transport instead. Everything after the transport is the same code path.

**Secrets are environment variable names.** The config holds `auth: {pat_env: ...}` or `auth: {username_env: ..., password_env: ...}`. The values live in the backend's environment (`.env`). They are never in YAML and never returned by the API.

**Identity.**
- doc_ids: `azure_devops:<project URL>:wi:<id>` and `azure_devops:<project URL>:cs:<n>`.
- `ISSUE` and `COMMIT` node ids are hashed from the project URL and native id, so two projects that link the same changeset get separate `COMMIT` nodes.
- A `SOURCE_FILE` id is the code root's name plus the normalised path. Code root names are global, so two Instances that use the same root name share file nodes.

**Properties joined at query time, not edges.** For the same ownership reason as ADR-0036's `requirement_ids`, these are all `ISSUE` properties:
- `parent_id` and `related_ids`: work item links;
- `attachment_names` and `attachment_md5s`: attachments, as parallel lists, because Neo4j properties can't hold maps. MD5 matches the docx adapter's `content_hash`. An attachment over the size cap records an empty hash.

**Failure semantics.**
- If `discover()` fails (WIQL, auth or network), the job fails before any removal runs, so an outage never looks like every work item being deleted.
- A failed fetch for one document, including an attachment download, marks that document failed. Its hash isn't recorded, so the next run retries it, and its previous graph state is untouched.

## Consequences
- No watermark table; the existing SQLite hash store is enough.
- A changed work item re-ingests its linked changesets too. Work items have few changesets each, so this is cheap.
- The quickstart sample is an Instance whose `source_path` is `fixture:<dir>`.
- Pure branch/merge TFVC changes are not recorded as `CHANGES` edges, because one branch operation can list thousands of files.
