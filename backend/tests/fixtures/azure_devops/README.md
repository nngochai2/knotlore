# Synthetic Azure DevOps Server fixture project

Hand-written, synthetic REST data for the Azure DevOps source adapter's fixture mode (ADR-0035, ADR-0037). No real server, company or person is represented. `FixtureTransport` (`app/pipeline/sources/azure_devops/fixtures.py`) serves it as a tiny fake server:

- `server.json`: the project URL every request is made against.
- `workitems/<id>.json`: one work item as returned by `GET _apis/wit/workitems?$expand=relations`. Every file is in the WIQL result (the fake doesn't evaluate WIQL filters).
- `changesets/<n>.json`: one TFVC changeset; its `changes` list is served from `.../changesets/<n>/changes`.
- `attachments/<guid>`: raw attachment bytes, served from `_apis/wit/attachments/<guid>`.

Work items: 100 (Feature, no links), 101 (User Story: changeset 2001, git-style diff, spec attachment, parent 100), 102 (Bug: changesets 2001 and 2002, `tf diff`-style patch, related to 101). Changeset 2003 exists but no work item links it, so it is never discovered.
