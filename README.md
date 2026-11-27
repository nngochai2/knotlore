# Knotlore

**Give your AI assistant the requirements and history your code doesn't contain.**

Knotlore is for teams maintaining long-lived systems whose real requirements live in documents (Word specs, wikis, Obsidian vaults) and in an issue tracker, not in the code. It ingests them into a self-hosted Neo4j knowledge graph with **deterministic, rule-driven extraction** and serves that graph to AI coding assistants over MCP. An assistant can then answer questions like:

> *Which requirements does this file touch, where are they specified, and which work items changed them?*

> **Status: pre-release, working toward v0.1.** Document ingestion, the job API and the Ingest/Instances UI work today. The Azure DevOps Server adapter, the knowledge MCP server and the one-command quickstart are in progress; see the [v0.1 milestone](https://github.com/nngochai2/knotlore/milestones). The project was renamed from its working name, `loom`, which the code still uses in places.

## How it works

```
[SourceAdapter] → [Extraction] → [RuleEngine] → [SinkAdapter(s)] → Neo4j ← knowledge MCP ← your AI assistant
```

- **Sources.** Obsidian vaults and `.docx` specs today. **Azure DevOps Server** (on-prem) is coming in v0.1: work items, associated TFVC changesets and attached `.diff` files, linked to the files they change and the requirements they cite.
- **Deterministic extraction.** YAML rule files (regex over document tables and text, edited through a form with live preview) map content onto a fixed, versioned schema, [`kg-schema`](kg-schema/schema.json). No LLM in the core path. An opt-in, local-only (Ollama) LLM pass exists for prose sections.
- **Provenance on everything.** Every node and edge records its `origin` (`extracted` / `explicit` / `curated`), source document, content hash, the rule that produced it and the schema version. Traceability links also record where they came from (`via: changeset 123`, `via: attachment fix.diff`).
- **Incremental and safe to re-run.** Unchanged documents are skipped by content hash. Changed or removed ones are cleaned up and rewritten. Human corrections (`curated`) always survive re-ingestion, and edges left dangling by a re-ingest are flagged, never silently deleted.
- **Knowledge MCP** *(v0.1)*: traceability-shaped tools over Streamable HTTP, not raw graph queries.

What Knotlore deliberately is **not**: a document manager, a code graph (your assistant already reads code well), or a general-purpose MCP hub.

## Security model

**No authentication: run Knotlore only on a trusted network.** From v0.1, every service binds to `127.0.0.1` by default and exposing it to a network is an explicit choice. Until then, note that the development `docker-compose.yml` publishes Neo4j's and Ollama's ports on all interfaces. See [SECURITY.md](SECURITY.md) and [ADR-0032](docs/adr/0032-trusted-network-deployment-localhost-default.md).

## Getting started (development)

The v0.1 target is `docker compose up` → a working traceability answer from a bundled synthetic sample in under 5 minutes. Until then:

Requires Python 3.11+, [`uv`](https://github.com/astral-sh/uv), Node.js 22+ and Docker.

```bash
# Neo4j (and Ollama, only needed for the opt-in prose extraction)
docker compose up -d

# Backend
cd backend
uv venv && uv pip install -e ".[dev]"
cp .env.example .env          # NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
uvicorn app.main:create_app --factory --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Or ingest from the CLI without the API or UI:

```bash
cd backend
python cli.py ingest --source obsidian --path ./path/to/vault \
    --sink neo4j --config ./path/to/vault-config.yml --db ./loom.sqlite3
python cli.py ingest --source docx --path ./path/to/docs \
    --sink neo4j --config ./path/to/rules.yml --db ./loom.sqlite3
```

Run the checks with `mypy app cli.py` and `pytest` in `backend/`. They need no live Neo4j. More detail is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

- [`docs/loom-spec.md`](docs/loom-spec.md): the full specification, including behavioural invariants, the API surface and build phases.
- [`docs/adr/`](docs/adr/): one file per architectural decision. Start with [ADR-0027](docs/adr/0027-product-positioning-knotlore.md) (positioning) and [ADR-0034](docs/adr/0034-v0-1-release-scope-and-quickstart-criterion.md) (v0.1 scope).
- [`CONTEXT.md`](CONTEXT.md): domain glossary.

## Repository layout

```
backend/      FastAPI app, ingestion pipeline (sources, rules, sinks), job runner, CLI
frontend/     React + Vite + TypeScript UI
kg-schema/    versioned entity/relationship schema, the contract between ingestion and the MCP server
docs/         spec, ADRs, agent workflow conventions
```

## Contributing

Issues and PRs are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## License

[MIT](LICENSE)
