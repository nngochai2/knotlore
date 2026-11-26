# 0035 — Azure DevOps Server is the v0.1 tracker: work items, TFVC changesets and attached diffs as link sources

## Status
Accepted (2026-11-27). Supersedes parts of ADR-0030 (tracker choice, link sources, credentials), ADR-0031 (support-tier list) and ADR-0034 (sample project, source-adapter list). Everything else in those ADRs still holds.

## Context
ADR-0030 assumed the design-partner team tracks work in self-hosted Jira and links commits to issues through a key in the commit message or branch name. Confirmed with the maintainer on 2026-11-26/27, both assumptions are wrong:

- The team tracks work as **Azure DevOps Server (on-prem) work items**. The client or the team creates an item, then adds the estimate, problem statement and documents. The final delivery is a **unified diff attached to the work item**.
- Day-to-day code lives on an internal git server whose commits don't reference work items. Delivery to the client is a **TFVC check-in** into the client's Azure DevOps Server through a Visual Studio workspace mapping, with the changeset associated with its work item ("Related Work Items").

NAA already has a read-only Azure DevOps MCP. It covers REST + WIQL against `DefaultCollection` at `api-version 5.0` (Server 2019), basic auth, and `AttachedFile` relations with text extraction for .docx/.xlsx/.pdf, but not diffs. It's evidence that this integration is tractable.

Resolved in a `/grilling` session on 2026-11-26/27.

## Decision

**Tracker.** The one maintained tracker source adapter in v0.1 is **Azure DevOps Server (on-prem, 2019+)**. Jira Data Center/Server moves to after v0.1, next to GitHub/GitLab issues. *(Replaces ADR-0030's Jira choice.)*

**Link sources, all in the one Azure DevOps adapter, all deterministic:**
1. **TFVC changesets associated with work items.** These are the most authoritative link: changeset → work item, and changeset → changed files. They're read through the same REST API and credentials. No git involved.
2. **Unified diffs attached to work items.** A diff attachment is recognised by a configurable filename glob (default `*.diff, *.patch`), and its file headers are parsed into paths. This gives work item → changes → file, with no Commit node.
3. **Requirement references.** The work item's text fields (title, description, acceptance criteria) are scanned with the docx rule file's existing `id_pattern`. Spec documents attached to the work item are linked to the already-ingested document they match, by filename or content hash.

**Both changeset and diff links are kept** when both exist, each with its own provenance (`via: changeset 123` / `via: attachment fix.diff`). MCP tools return the union and show where each link came from. A disagreement between delivered scope and checked-in scope is information, not noise.

**`kg-schema` (amends the plan for #28).**
- A TFVC changeset is the **same generic Commit type** as a git commit. It carries `vcs: tfvc | git` and its native id (changeset number or SHA). There is no separate Changeset type.
- A source file's identity is **code root + normalised repo-relative path**. The source config's prefix mappings normalise TFVC server paths (`$/Project/Main/src/Foo.cs`), diff paths (`a/src/Foo.cs`) and checkout paths (`src/Foo.cs`) to one node. Raw paths are kept as properties.

**Instance (ADR-0025).** An Azure DevOps Instance is **collection + project, with an optional area-path or WIQL filter**. Re-ingestion is incremental from a `System.ChangedDate` watermark. Work items that leave the query are tombstoned like any other source's documents.

**Credentials.** A **personal access token** is the documented path. **Username/password** (basic auth) is also accepted, because that is what the design-partner deployment uses today. Both are stored per source config and never committed. *(Amends ADR-0030, which said PAT only.)*

**Git history adapter.** It is **deferred to after v0.1**. It stays the right adapter for teams with `ABC-123` commit conventions, and it reuses the Commit type above unchanged.

**MCP plugin tiers (replaces ADR-0031's list).**
- **core:** the knowledge MCP.
- **maintained:** Azure DevOps (live actions and attachment reading).
- **example:** Jira, Git, Jenkins, Oracle. Agents read the local git checkout themselves, so a Git MCP adds little.

**Sample project (replaces ADR-0034 item 2's git-repo-and-issue-fixtures part).** The synthetic sample ships **recorded Azure DevOps REST fixtures**: work items with attached `.diff` files and associated TFVC changesets. These run through the real adapter in a **fixture mode**, which is an injected `httpx` transport serving files, not a second code path. The fixtures are also the adapter's end-to-end tests. The quickstart never needs a live Azure DevOps Server.

## Consequences
- ADR-0034's adapter list for v0.1 becomes: Obsidian, docx and Azure DevOps Server. The git history adapter is removed from v0.1.
- Issue #31 becomes the Azure DevOps Server adapter. #30 leaves the v0.1 milestone. #28 and #35 are amended to match, and #29's spec amendment cites this ADR.
- The NAA Git MCP's tests (NAA #34) drop to low priority, since that plugin is now "example" tier.
- Public material stays generic. It says "an internal git server" and "Azure DevOps Server", never the employer's systems or the client's names.
- If the design-partner team later links internal git commits to work items (`AB#123`), the deferred git adapter picks that up without a schema change.
