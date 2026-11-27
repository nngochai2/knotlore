"""The Azure DevOps adapter through the real `Pipeline.run` and `HashStore`
(ADR-0036, ADR-0037): incremental skips, removals, and the `REFERENCES`
rebuild that ordering and changeset hashes exist for.

`OwnershipGraph` models Neo4jSink's ownership semantics, which is what
these properties depend on (Cypher shape is covered in
test_neo4j_sink.py):
- relationships MERGE on (from, type, to) and create bare endpoints;
- cleanup deletes the document's own relationships, then `DETACH DELETE`s
  its own nodes, taking *every* edge touching them, including edges other
  documents wrote;
- shared (`SOURCE_FILE`) nodes have no owner and are collected once no
  relationship is left on them.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from app.jobs.store import HashStore, connect
from app.pipeline.core import Pipeline
from app.pipeline.sources.azure_devops.adapter import AzureDevOpsSourceAdapter, issue_node_id
from app.pipeline.sources.azure_devops.client import AzureDevOpsError
from app.pipeline.sources.azure_devops.config import azure_devops_config_from_dict
from app.pipeline.types import DeleteReport, ExtractionResult, SinkReport

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "azure_devops"
PROJECT = "https://ado.example.test/DefaultCollection/Sample"
CONFIG = azure_devops_config_from_dict(
    {
        "name": "Sample project",
        "requirement_id": {"pattern": r"\bBR[-\s]?(\d+)\b", "flags": "IGNORECASE", "format": "BR-{:02d}"},
        "code_roots": [{"name": "billing", "prefixes": ["$/Sample/Main/", "$/Sample/Dev/"]}],
    }
)
SHARED = {"SOURCE_FILE"}


@dataclass
class OwnershipGraph:
    sink_type: str = "ownership"
    nodes: dict[str, dict[str, object]] = field(default_factory=dict)
    rels: dict[tuple[str, str, str], dict[str, object]] = field(default_factory=dict)
    writes: int = 0

    def write(self, doc_id: str, result: ExtractionResult) -> SinkReport:
        self.writes += 1
        for e in result.entities:
            owner = None if e.type in SHARED else doc_id
            self.nodes[e.id] = {"type": e.type, "owner": owner, **e.properties}
        for r in result.relationships:
            for endpoint in (r.from_id, r.to_id):
                self.nodes.setdefault(endpoint, {"type": None, "owner": None})
            self.rels[(r.from_id, r.type, r.to_id)] = {"owner": doc_id, **r.properties}
        return SinkReport(sink_type=self.sink_type)

    def delete_non_curated_for_doc(self, doc_id: str) -> DeleteReport:
        before = len(self.nodes) + len(self.rels)
        self.rels = {k: v for k, v in self.rels.items() if v["owner"] != doc_id}
        owned = {n for n, props in self.nodes.items() if props["owner"] == doc_id}
        self.rels = {k: v for k, v in self.rels.items() if k[0] not in owned and k[2] not in owned}
        for n in owned:
            del self.nodes[n]
        linked = {k[0] for k in self.rels} | {k[2] for k in self.rels}
        for n in [n for n, p in self.nodes.items() if p["type"] in SHARED and n not in linked]:
            del self.nodes[n]
        return DeleteReport(deleted_count=before - len(self.nodes) - len(self.rels))

    def of_type(self, entity_type: str) -> dict[str, dict[str, object]]:
        return {n: p for n, p in self.nodes.items() if p["type"] == entity_type}

    def rel_types_into(self, node_id: str, rel_type: str) -> set[str]:
        return {k[0] for k in self.rels if k[1] == rel_type and k[2] == node_id}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "project"
    shutil.copytree(FIXTURE, dest)
    return dest


def run(source_path: str, graph: OwnershipGraph, store: HashStore, adapter: AzureDevOpsSourceAdapter | None = None):  # type: ignore[no-untyped-def]
    return Pipeline().run(
        adapter or AzureDevOpsSourceAdapter(CONFIG),
        source_path,
        [graph],
        CONFIG,
        progress=lambda doc_id, fraction: None,
        store=store,
    )


def bump(project: Path, work_item_id: int, new_rev: int) -> None:
    path = project / "workitems" / f"{work_item_id}.json"
    text = path.read_text(encoding="utf-8")
    old_rev = text.split('"rev": ', 1)[1].split(",", 1)[0]
    path.write_text(text.replace(f'"rev": {old_rev}', f'"rev": {new_rev}', 1), encoding="utf-8")


def test_first_run_writes_every_document_and_an_unchanged_rerun_writes_nothing(project: Path) -> None:
    graph, store = OwnershipGraph(), HashStore(connect(":memory:"))

    first = run(f"fixture:{project}", graph, store)
    assert [s.outcome for s in first.doc_statuses] == ["updated"] * 5
    assert len(graph.of_type("ISSUE")) == 3
    assert len(graph.of_type("COMMIT")) == 2
    writes = graph.writes

    second = run(f"fixture:{project}", graph, store)
    assert [s.outcome for s in second.doc_statuses] == ["skipped"] * 5
    assert graph.writes == writes


def test_changing_a_work_item_rebuilds_references_from_its_unchanged_changesets(project: Path) -> None:
    graph, store = OwnershipGraph(), HashStore(connect(":memory:"))
    run(f"fixture:{project}", graph, store)
    issue_102 = issue_node_id(PROJECT, 102)
    assert len(graph.rel_types_into(issue_102, "REFERENCES")) == 2

    bump(project, 102, 9)
    result = run(f"fixture:{project}", graph, store)

    outcomes = {s.doc_id.rsplit(":", 2)[-2] + s.doc_id.rsplit(":", 1)[-1]: s.outcome for s in result.doc_statuses}
    assert outcomes == {"wi100": "skipped", "wi101": "skipped", "wi102": "updated", "cs2001": "updated", "cs2002": "updated"}
    # The ISSUE node was DETACH DELETEd and rebuilt; both changesets wrote
    # their REFERENCES edges into it again afterwards.
    assert len(graph.rel_types_into(issue_102, "REFERENCES")) == 2


def test_a_work_item_leaving_the_query_is_cleaned_up_with_what_only_it_linked(project: Path) -> None:
    graph, store = OwnershipGraph(), HashStore(connect(":memory:"))
    run(f"fixture:{project}", graph, store)
    assert "src/Billing/Rounding.cs" in {p["path"] for p in graph.of_type("SOURCE_FILE").values()}

    (project / "workitems" / "102.json").unlink()
    result = run(f"fixture:{project}", graph, store)

    removed = {s.doc_id for s in result.doc_statuses if s.outcome == "removed"}
    assert removed == {f"azure_devops:{PROJECT}:wi:102", f"azure_devops:{PROJECT}:cs:2002"}
    assert issue_node_id(PROJECT, 102) not in graph.nodes
    assert len(graph.of_type("COMMIT")) == 1
    # Rounding.cs was linked only from work item 102's patch and changeset
    # 2002, so the shared node is collected; Invoice.cs is still linked.
    paths = {p["path"] for p in graph.of_type("SOURCE_FILE").values()}
    assert "src/Billing/Rounding.cs" not in paths
    assert "src/Billing/Invoice.cs" in paths
    # Changeset 2001 re-ingested (one fewer linker) and references only 101.
    assert graph.rel_types_into(issue_node_id(PROJECT, 101), "REFERENCES") != set()


def test_a_failed_discovery_fails_the_run_before_anything_is_removed(project: Path) -> None:
    graph, store = OwnershipGraph(), HashStore(connect(":memory:"))
    run(f"fixture:{project}", graph, store)
    nodes, rels = dict(graph.nodes), dict(graph.rels)

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    config = azure_devops_config_from_dict(
        {
            "name": "Sample project",
            "requirement_id": {"pattern": r"BR-(\d+)"},
            "code_roots": [{"name": "billing", "prefixes": ["$/Sample/Main/"]}],
            "auth": {"pat_env": "PATH"},  # any variable that is set
        }
    )
    live = AzureDevOpsSourceAdapter(config, transport=httpx.MockTransport(unavailable))
    with pytest.raises(AzureDevOpsError, match="503"):
        run(PROJECT, graph, store, adapter=live)

    assert graph.nodes == nodes
    assert graph.rels == rels


def test_changesets_wait_for_a_failed_work_item_so_their_references_survive_its_retry(project: Path) -> None:
    graph, store = OwnershipGraph(), HashStore(connect(":memory:"))
    run(f"fixture:{project}", graph, store)
    issue_102 = issue_node_id(PROJECT, 102)

    # Work item 102 changes, but its patch can't be downloaded this run.
    patch = project / "attachments" / "0a1b2c3d-0000-4000-8000-000000000201"
    saved = patch.read_bytes()
    patch.unlink()
    bump(project, 102, 9)
    failing = run(f"fixture:{project}", graph, store)

    outcomes = {s.doc_id.rsplit(":", 2)[-2] + s.doc_id.rsplit(":", 1)[-1]: s.outcome for s in failing.doc_statuses}
    # Its changesets are held back too, so they re-ingest with it later.
    assert outcomes["wi102"] == "failed"
    assert outcomes["cs2001"] == "failed"
    assert outcomes["cs2002"] == "failed"

    patch.write_bytes(saved)
    retried = run(f"fixture:{project}", graph, store)

    assert {s.outcome for s in retried.doc_statuses if s.doc_id.endswith((":wi:102", ":cs:2001", ":cs:2002"))} == {"updated"}
    assert len(graph.rel_types_into(issue_102, "REFERENCES")) == 2
