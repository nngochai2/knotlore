# 0027 — MCP plugin manifest v1, Streamable HTTP, and support tiers

## Status
Accepted (2026-11-25)

## Context
NAA bundles seven MCP servers, each with a `meta.yml` (id, label, command, host, port, env file, credential fields) that its webapp reads to start, stop and configure the server. That is most of a plugin manifest already, but it's implicit and unversioned, and it only covers servers that live in the repo.

A solo maintainer (ADR-0027) can't keep seven integrations working against seven external systems. Live tracker MCPs are useful for *actions* (creating or updating issues, triggering builds), but they aren't the core product.

## Decision
- **Formalise `meta.yml` as a versioned plugin manifest (v1).** It declares identity, how to run the server (or, for an **external** server, only its URL), credential fields (secret or not), and a health check. External, third-party MCP servers can be registered by URL without living in the repo.
- **Transport is Streamable HTTP.** The SSE transport NAA's servers use is deprecated in the MCP spec. Existing servers migrate when they move into Knotlore.
- **Support tiers**, shown in the manifest and the UI:
  - **core**: the knowledge MCP (ships in the quickstart).
  - **maintained**: Jira and Git plugins, matching what the design-partner team uses.
  - **example**: Azure DevOps, Jenkins, Oracle. They ship as reference implementations, aren't in the quickstart, and fixes are best-effort. Oracle stays "example" at least until NAA issue #43 (SQL injection / unenforced `ALLOWED_SCHEMAS`) is fixed.
- **Ingestion plugins are not formalised in v1.** New sources go through Loom's internal `SourceAdapter` protocol until it has stabilised across the git and tracker adapters (ADR-0030).

## Consequences
- The control plane's MCP management reads manifests, not hard-coded server lists.
- Plugin credentials keep the current model: written to each plugin's own env file and never committed.
- Promoting an "example" plugin to "maintained" needs a real user who depends on it and tests that cover it.
