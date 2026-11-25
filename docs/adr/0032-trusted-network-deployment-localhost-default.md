# 0032 — Deployment: shared server on a trusted network, no auth, localhost by default

## Status
Accepted (2026-11-25)

## Context
The real deployment is a shared team server: one PC runs the app, IT has configured a subnet so teammates' machines reach the webapp and MCP endpoints, and each subnet belongs to one team. NAA's MCP endpoints have no authentication, and the webapp has only a single shared password.

Per-user bearer tokens for MCP endpoints were considered and judged out of scope: the network already isolates each team. An open-source user who runs the quickstart on a cloud VM or a shared office network doesn't have that isolation, though.

## Decision
- Knotlore targets a **shared team server on a trusted network**. No per-user auth on MCP endpoints in v0.1; `loom-spec.md` §2's "no auth beyond a single shared instance" still holds.
- **Safe by default:** every service binds to `127.0.0.1` unless the operator explicitly opts in to network exposure through one documented setting (e.g. a `KNOTLORE_BIND` variable).
- The README states plainly: **no authentication — run only on a trusted network.**
- Local single-user mode (everything on localhost) is the quickstart path.

## Consequences
- The design-partner deployment needs one setting changed to keep working as it does today.
- Revisit (per-user tokens, then OAuth) when the first user needs it on a network that isn't trusted, or when write-capable plugins need per-user attribution beyond each user's own tracker PAT.
