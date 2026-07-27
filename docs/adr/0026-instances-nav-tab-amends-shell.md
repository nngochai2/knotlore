# 0026 — Instances page: fourth persistent nav tab, amends ADR-0013

## Status
Accepted

## Context
ADR-0013 fixed the persistent top nav at exactly three tabs (Ingest/Rules/Graph), sized for a desktop-only, single-user tool. ADR-0025 introduces "Instance" as a catalog concept that needs a home for *returning to* existing work — distinct from Landing (ADR-0023), which is specifically for *starting new* work and deliberately sits outside the shell with no persistent nav. Resolved via `/grill-with-docs`.

## Decision
- Add a **fourth persistent nav tab, "Instances"** (Ingest / Rules / Graph / Instances) — amending ADR-0013's fixed three-tab shell.
- **List view** (`/instances`): one row per instance — name, source type + path, sink(s), config in use, most recent run's status + timestamp, job count; sorted most-recently-run first.
- **Detail view** (`/instances/{id}`), a separate route, not an inline accordion: full job-run history (`GET /jobs?instance_id=`), a rename control, a "Run again" button that navigates to `/ingest` with source/sink/config pre-filled from the instance's last run — the same pre-fill mechanism Landing's cards use (ADR-0023) — and delete (catalog-only, ADR-0025).
- **Ingest page gains an instance picker** at the top: choose an existing instance (pre-fills its source/sink/config) or "New instance" + a name field. Landing's three shortcut cards (ADR-0023) continue to pre-fill source/sink only, landing on "New instance" with the name left blank for the user to fill in or skip (auto-named per ADR-0025).

## Consequences
- `frontend/src/pages/Instances.tsx` (list) and `frontend/src/pages/InstanceDetail.tsx` (detail) join the ADR-0013 shell alongside Ingest/Rules/Graph; the shell's nav component (`App.tsx`) grows a fourth tab.
- Ingest page (issue #10) gains the instance-picker control; Landing (issue #21) needs no behavior change beyond confirming its pre-fill still lands on "New instance."
- If Landing is ever asked to show existing instances too (e.g. a "continue" shortcut before the three fresh-start cards), that reopens ADR-0023 and should be its own decision, not folded in here.
- **"Run again" does not actually use Landing's pre-fill mechanism (issue #23).** Landing's cards pre-fill source/sink as blank-slate query params landing on "New instance" (ADR-0023) — reusing that verbatim for "Run again" would resubmit the exact same `(source_type, source_path, sinks)` tuple as a *new* instance and hit ADR-0025's duplicate-instance rejection every time. "Run again" instead links to `/ingest?instance_id=<id>`, which the instance picker resolves through its existing "existing instance" path (pre-filled and locked, same as picking it manually from the picker's dropdown). Functionally equivalent outcome, structurally a different mechanism than this ADR originally specified.
