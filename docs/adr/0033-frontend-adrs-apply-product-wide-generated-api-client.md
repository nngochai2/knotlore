# 0029 — Frontend: ADRs 0013–0017 apply product-wide, plus an OpenAPI-generated API client

## Status
Accepted (2026-11-25). Extends ADR-0013 to 0017.

## Context
NAA's UI is one large hand-written `index.html` plus one large `app.js` calling an untyped API. It breaks easily because nothing checks that the frontend and backend agree. ADRs 0013–0017 already settle Loom's frontend: a desktop-only top-nav shell with react-router, shadcn/ui on Radix and Tailwind, TanStack Query for server state, and conventions for toasts, confirm dialogs and graph edges. ADRs 0023–0026 add the Landing page, the Rules-page graph preview and the Instances tab on the same stack. The merged product (ADR-0028) adds pages Loom didn't plan: MCP/plugin status and management, and settings.

## Decision
- ADRs 0013–0017 and 0023–0026 govern the **whole Knotlore UI**, including the pages that came from NAA. NAA's UI is not ported; its features are rebuilt on this stack.
- **The TypeScript API client is generated from FastAPI's OpenAPI schema** (e.g. orval or openapi-typescript), never hand-written. A backend contract change that breaks the frontend fails at typecheck in CI, not in the browser.
- The top nav (ADR-0013, already amended to four tabs by ADR-0026) grows beyond Ingest/Rules/Graph/Instances to include MCP/Plugins and Settings. It stays a top nav until there are too many tabs to fit, at which point ADR-0013 is revisited.

## Consequences
- CI gains a frontend job: generate client → typecheck → lint → build. A stale generated client fails the build.
- The built frontend is served by the FastAPI backend, so the product deploys as one service (ADR-0034).
