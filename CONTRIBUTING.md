# Contributing to Knotlore

Thanks for your interest. Knotlore is maintained by one person in a few hours a week, so the most useful contributions are small, focused, and tied to an existing issue.

## Before you start

- **Open or find an issue first.** Issues are triaged with five labels ([`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)). Issues labelled `ready-for-human` or `ready-for-agent` are ready to pick up. Anything still `needs-triage` may change shape, so comment before you start on one.
- **Read the decisions.** The spec is [`docs/loom-spec.md`](docs/loom-spec.md), and each architectural decision is an ADR in [`docs/adr/`](docs/adr/). Domain terms are defined in [`CONTEXT.md`](CONTEXT.md). A change that contradicts an accepted ADR needs a new ADR, not just a PR.
- **Scope.** Feature requests are judged against the requirements-traceability use case ([ADR-0027](docs/adr/0027-product-positioning-knotlore.md)). Some things are ruled out on purpose: a code graph (ADR-0029), a general-purpose MCP hub (ADR-0028), and LLM-based extraction in the core path (ADR-0027).

## Development setup

Requires Python 3.11+, [`uv`](https://github.com/astral-sh/uv), Node.js 22+ and Docker.

```bash
# Backend
cd backend
uv venv && uv pip install -e ".[dev]"
mypy app cli.py      # strict; must stay clean
pytest               # no live Neo4j needed: sinks are tested against fakes

# Frontend
cd frontend
npm install
npx tsc -b --noEmit && npx oxlint && npx vite build
```

`docker compose up -d` starts a local Neo4j for manual end-to-end runs.

## Pull requests

- One logical change per PR, linked to its issue (`Closes #123`).
- Add or update tests. Bug fixes come with a test that fails without the fix.
- CI (backend tests, `mypy --strict`) must pass.
- Update the spec, the ADRs or `CONTEXT.md` when the change affects them.

## Keep public material generic

Fixtures, samples, docs and issues must use **synthetic data**. Never commit real company documents, rule files, schemas, tracker exports, system names or credentials. Tracker tokens and database passwords belong in local `.env` files or per-source configs, which are never committed.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By taking part, you agree to uphold it.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
