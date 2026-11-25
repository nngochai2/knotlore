# 0023 — Product positioning: Knotlore, the requirements and history your code doesn't contain

## Status
Accepted (2026-11-25)

## Context
NAA grew around one person's day-job needs: a bundle of MCP servers (Git, Jira, Azure DevOps, Jenkins, Oracle, code graph, knowledge graph) plus a control-plane webapp. Loom (this repo) was split off as the rebuilt write path. Neither had an explicit answer to "who is this for, and why would they pick it over alternatives?"

Two pressures forced the question:
- **Breadth by bundling doesn't attract users.** GitHub, Atlassian, Azure DevOps and most databases ship official MCP servers, and generic MCP hubs (Docker MCP Toolkit, MetaMCP, …) already exist. Another bundle of tracker MCPs competes with the vendors themselves.
- **The genuinely differentiated part is the knowledge layer**: deterministic, rule-driven extraction of requirements from documents into a versioned, provenance-carrying graph. Generic RAG and doc-search tools don't produce this.

Resolved via a `/grilling` session on 2026-11-25.

## Decision

**Name.** The merged product is **Knotlore** — record-keeping knots (continuing Loom's weaving lineage) + tribal knowledge. "Loom" is dropped as a public name because it collides with Atlassian's Loom in exactly the audience that uses Jira; "NAA" is dropped as non-descriptive. Collision check (2026-11-25): `knotlore` unused on PyPI, npm, GitHub users and GitHub repo names. Quipu, Heddle, Selvedge, Stele, Scholia, Marginalia, Palimpsest and Knot were rejected because each is already used by an AI-memory / knowledge-graph / MCP project.

**Goal.** Open-source adoption. The maintainer's own work team is design partner #1 and the proving ground. Commercial use is out of scope. Planning assumes one maintainer at ~5–10 h/week.

**Audience.** Teams maintaining **long-lived systems whose real requirements live in documents, not code** (FDD/SDD specs, Word documents, wikis/vaults). Self-hosting is a design constraint and a selling point, not the headline. Regulated/compliance work is a strong use case, not the audience definition.

**Product.** *Give your AI assistant the requirements and history your code doesn't contain.* The knowledge layer (ingestion + graph + knowledge MCP) is the product. The control plane is supporting infrastructure for operating it, not the pitch.

**First use case.** Requirements traceability: spec/requirement ↔ issues ↔ commits/files. "Which requirements does this file touch, where are they specified, and which issues changed them?" (See ADR-0029, ADR-0030.)

**LLM-free core.** All core extraction and linking is deterministic. The opt-in LLM prose extraction path (ADR-0018–0022) stays opt-in and off in the quickstart.

**Public material is generic.** Only generic mechanisms are published. No employer documents, schemas, rule files or company names; demos and fixtures use synthetic data.

## Consequences
- README, repo description and package names move to Knotlore before the first public release (ADR-0034). Internal module renames can follow.
- Feature requests are judged against the traceability use case and the 5–10 h/week budget. Anything that can't be maintained is demoted to "example" status (ADR-0031) or declined.
- The Landing page's shortcut cards (ADR-0023) should lead with the traceability flow. The "Documents → Vector" card waits until the vector sink ships after v0.1 (ADR-0034).
- Supersedes the framing in `loom-spec.md` §1 ("Loom is the write path… NAA slimmed down separately"); see ADR-0028.
