# Security Policy

## Supported versions

Knotlore is pre-1.0. Only the latest commit on `main` gets security fixes.

## Reporting a vulnerability

Please **don't open a public issue** for a security problem. Report it privately through this repository's **Security → Report a vulnerability** form (GitHub private vulnerability reporting).

Include what you found, the affected component (backend API, knowledge MCP server, an MCP plugin, the frontend), steps to reproduce, and the impact you expect. You'll get an acknowledgement within a week. This is a one-maintainer project, so fixes are best-effort; you'll be kept updated and credited in the fix unless you'd rather not be.

## What is not a vulnerability

Knotlore is designed for a **trusted network** ([ADR-0032](docs/adr/0032-trusted-network-deployment-localhost-default.md)):

- The web UI, the API and the MCP endpoints have **no authentication** in v0.1.
- From v0.1, every service binds to `127.0.0.1` by default, and exposing it to a network is an explicit operator choice. (The current development `docker-compose.yml` still publishes Neo4j's and Ollama's ports on all interfaces; #35 changes that.)

So "an unauthenticated user on the same network can read the graph" is expected behaviour, not a vulnerability. Reports that break the localhost-by-default guarantee, leak credentials (tracker tokens, database passwords), or let a document or tracker item trigger code execution or injection are very welcome.

Plugins marked **example** tier (see [ADR-0031](docs/adr/0031-mcp-plugin-manifest-v1-and-support-tiers.md)) are reference implementations with best-effort fixes; please still report issues in them.
