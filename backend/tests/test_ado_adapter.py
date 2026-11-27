"""Azure DevOps Server adapter through its fixture transport (ADR-0035,
ADR-0036, ADR-0037). The synthetic project lives in
tests/fixtures/azure_devops (see its README for what each item links)."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import httpx
import pytest

from app.pipeline.sources.azure_devops.adapter import AzureDevOpsSourceAdapter
from app.pipeline.sources.azure_devops.client import AzureDevOpsError
from app.pipeline.sources.azure_devops.config import azure_devops_config_from_dict
from app.pipeline.types import Entity, ExtractionResult

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "azure_devops"
PROJECT = "https://ado.example.test/DefaultCollection/Sample"

CONFIG = {
    "name": "Sample project",
    "requirement_id": {"pattern": r"\bBR[-\s]?(\d+)\b", "flags": "IGNORECASE", "format": "BR-{:02d}"},
    "code_roots": [{"name": "billing", "prefixes": ["$/Sample/Main/", "$/Sample/Dev/"]}],
}


def make_adapter(**overrides: object) -> AzureDevOpsSourceAdapter:
    return AzureDevOpsSourceAdapter(azure_devops_config_from_dict({**CONFIG, **overrides}))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway copy, so tests can change it without touching the
    committed fixture."""
    dest = tmp_path / "project"
    shutil.copytree(FIXTURE, dest)
    return dest


def wi(n: int) -> str:
    return f"azure_devops:{PROJECT}:wi:{n}"


def cs(n: int) -> str:
    return f"azure_devops:{PROJECT}:cs:{n}"


# ── discover ─────────────────────────────────────────────────────────────


def test_discover_lists_work_items_before_the_changesets_they_link() -> None:
    docs = make_adapter().discover(f"fixture:{FIXTURE}")

    assert [d.doc_id for d in docs] == [wi(100), wi(101), wi(102), cs(2001), cs(2002)]


def test_a_work_items_hash_is_its_revision() -> None:
    docs = {d.doc_id: d for d in make_adapter().discover(f"fixture:{FIXTURE}")}

    assert docs[wi(101)].content_hash == "rev:3"
    assert docs[wi(102)].content_hash == "rev:2"


def test_a_changesets_hash_names_the_revisions_of_the_work_items_linking_it() -> None:
    docs = {d.doc_id: d for d in make_adapter().discover(f"fixture:{FIXTURE}")}

    assert docs[cs(2001)].content_hash == "cs:2001|101@3,102@2"
    assert docs[cs(2002)].content_hash == "cs:2002|102@2"


def test_changing_a_work_item_changes_the_hash_of_its_changesets(project: Path) -> None:
    before = {d.doc_id: d.content_hash for d in make_adapter().discover(f"fixture:{project}")}
    path = project / "workitems" / "102.json"
    path.write_text(path.read_text().replace('"rev": 2', '"rev": 5'), encoding="utf-8")

    after = {d.doc_id: d.content_hash for d in make_adapter().discover(f"fixture:{project}")}

    assert after[wi(101)] == before[wi(101)]
    assert after[cs(2001)] != before[cs(2001)]
    assert after[cs(2002)] != before[cs(2002)]


def test_a_changeset_no_in_scope_work_item_links_is_not_discovered(project: Path) -> None:
    (project / "workitems" / "102.json").unlink()

    ids = [d.doc_id for d in make_adapter().discover(f"fixture:{project}")]

    assert cs(2002) not in ids
    assert cs(2001) in ids


# ── work items ───────────────────────────────────────────────────────────


def extract(adapter: AzureDevOpsSourceAdapter, source_path: str, doc_id: str) -> ExtractionResult:
    docs = {d.doc_id: d for d in adapter.discover(source_path)}
    return adapter.extract(adapter.load(docs[doc_id]), adapter.config)


def only(result: ExtractionResult, entity_type: str) -> Entity:
    matches = [e for e in result.entities if e.type == entity_type]
    assert len(matches) == 1, matches
    return matches[0]


def files_by_path(result: ExtractionResult) -> dict[str, Entity]:
    return {str(e.properties["path"]): e for e in result.entities if e.type == "SOURCE_FILE"}


def test_a_work_item_becomes_a_read_only_issue_node() -> None:
    result = extract(make_adapter(), f"fixture:{FIXTURE}", wi(101))
    issue = only(result, "ISSUE")

    assert issue.name == "Invoice totals include tax"
    assert issue.origin == "explicit"
    assert issue.rule_id is None
    props = issue.properties
    assert props["tracker"] == "azure-devops"
    assert props["work_item_id"] == 101
    assert props["kind"] == "User Story"
    assert props["state"] == "Resolved"
    assert props["area_path"] == r"Sample\Billing"
    assert props["iteration_path"] == r"Sample\Release 1\Sprint 2"
    assert props["estimate"] == 5
    assert props["description"] == "Implements BR-01 & touches br 3.\nSee attached spec."
    assert props["acceptance_criteria"] == "Totals match BR-01\nTax rounding per BR-02"
    assert props["parent_id"] == 100
    assert props["related_ids"] == []


def test_requirement_ids_are_found_in_title_description_and_acceptance_criteria() -> None:
    issue = only(extract(make_adapter(), f"fixture:{FIXTURE}", wi(101)), "ISSUE")

    assert issue.properties["requirement_ids"] == ["BR-01", "BR-02", "BR-03"]


def test_field_fallbacks_cover_other_process_templates() -> None:
    issue = only(extract(make_adapter(), f"fixture:{FIXTURE}", wi(102)), "ISSUE")

    # A Bug has repro steps instead of a description, and an original
    # estimate instead of story points.
    assert issue.properties["description"] == "Totals are off by a cent, violating BR-02."
    assert issue.properties["estimate"] == 2.5
    assert issue.properties["related_ids"] == [101]
    assert issue.properties["parent_id"] is None


def test_attachments_are_recorded_by_name_and_md5_for_query_time_matching() -> None:
    issue = only(extract(make_adapter(), f"fixture:{FIXTURE}", wi(101)), "ISSUE")

    assert issue.properties["attachment_names"] == ["fix-101.diff", "Billing spec.docx"]
    assert issue.properties["attachment_md5s"][1] == "d244c44f3c583b216e62b9b04be0f60f"


def test_an_attached_git_style_diff_links_the_issue_to_the_files_it_changes() -> None:
    result = extract(make_adapter(), f"fixture:{FIXTURE}", wi(101))
    issue = only(result, "ISSUE")
    files = files_by_path(result)

    assert set(files) == {"src/Billing/Invoice.cs", "src/Billing/TaxRule.cs"}
    assert all(f.properties["code_root"] == "billing" for f in files.values())
    changes = {r.to_id: r for r in result.relationships if r.type == "CHANGES"}
    invoice = changes[files["src/Billing/Invoice.cs"].id]
    assert invoice.from_id == issue.id
    assert invoice.origin == "explicit"
    assert invoice.properties["via"] == "attachment fix-101.diff"
    assert invoice.properties["change"] == "edit"
    assert invoice.properties["raw_path"] == "src/Billing/Invoice.cs"
    assert changes[files["src/Billing/TaxRule.cs"].id].properties["change"] == "add"


def test_a_tf_style_patch_resolves_server_paths_and_oversized_diffs_are_skipped_with_a_warning() -> None:
    result = extract(make_adapter(), f"fixture:{FIXTURE}", wi(102))
    files = files_by_path(result)

    assert set(files) == {"src/Billing/Rounding.cs"}
    rel = next(r for r in result.relationships if r.type == "CHANGES")
    assert rel.properties["via"] == "attachment rounding.PATCH"
    assert rel.properties["raw_path"] == "$/Sample/Main/src/Billing/Rounding.cs"
    assert result.warning is not None and "huge.diff" in result.warning
    issue = only(result, "ISSUE")
    assert issue.properties["attachment_md5s"][issue.properties["attachment_names"].index("huge.diff")] == ""


def test_a_work_item_with_no_links_yields_just_its_issue() -> None:
    result = extract(make_adapter(), f"fixture:{FIXTURE}", wi(100))

    assert [e.type for e in result.entities] == ["ISSUE"]
    assert result.relationships == ()
    assert result.warning is None


# ── changesets ───────────────────────────────────────────────────────────


def test_a_changeset_becomes_a_tfvc_commit_referencing_its_work_items() -> None:
    adapter = make_adapter()
    result = extract(adapter, f"fixture:{FIXTURE}", cs(2001))
    commit = only(result, "COMMIT")

    assert commit.name == "C2001"
    assert commit.origin == "explicit"
    assert commit.properties["vcs"] == "tfvc"
    assert commit.properties["native_id"] == "2001"
    assert commit.properties["author"] == "Dev One"
    assert commit.properties["committed_at"] == "2026-11-20T10:00:00Z"
    assert commit.properties["comment"] == "Tax on invoice totals (BR-01)"
    assert commit.properties["requirement_ids"] == ["BR-01"]

    issues = {
        wi_id: only(extract(make_adapter(), f"fixture:{FIXTURE}", wi(wi_id)), "ISSUE").id
        for wi_id in (101, 102)
    }
    references = [r for r in result.relationships if r.type == "REFERENCES"]
    assert {r.to_id for r in references} == set(issues.values())
    assert all(r.from_id == commit.id for r in references)
    assert all(r.origin == "explicit" for r in references)
    assert {r.properties["via"] for r in references} == {"changeset 2001"}
    # The ISSUE nodes belong to the work item documents, not this one.
    assert [e.type for e in result.entities if e.type == "ISSUE"] == []


def test_a_changeset_changes_files_skipping_branch_merge_and_unmapped_paths() -> None:
    result = extract(make_adapter(), f"fixture:{FIXTURE}", cs(2001))
    commit = only(result, "COMMIT")
    files = files_by_path(result)

    assert set(files) == {"src/Billing/Invoice.cs", "src/Billing/TaxRule.cs", "src/Billing/Legacy.cs"}
    changes = {r.to_id: r for r in result.relationships if r.type == "CHANGES"}
    assert all(r.from_id == commit.id for r in changes.values())
    assert changes[files["src/Billing/Invoice.cs"].id].properties == {
        "via": "changeset 2001",
        "change": "edit",
        "raw_path": "$/Sample/Main/src/Billing/Invoice.cs",
    }
    assert changes[files["src/Billing/TaxRule.cs"].id].properties["change"] == "add"
    assert changes[files["src/Billing/Legacy.cs"].id].properties["change"] == "delete"
    assert result.warning is not None and "1 changeset path(s) matched no code root" in result.warning


def test_a_tfvc_path_a_diff_path_and_another_branch_resolve_to_one_file_node() -> None:
    adapter = make_adapter()
    from_changeset = files_by_path(extract(adapter, f"fixture:{FIXTURE}", cs(2001)))
    from_git_diff = files_by_path(extract(adapter, f"fixture:{FIXTURE}", wi(101)))
    from_dev_branch = files_by_path(extract(adapter, f"fixture:{FIXTURE}", cs(2002)))
    from_tf_diff = files_by_path(extract(adapter, f"fixture:{FIXTURE}", wi(102)))

    assert from_changeset["src/Billing/Invoice.cs"].id == from_git_diff["src/Billing/Invoice.cs"].id
    assert from_dev_branch["src/Billing/Rounding.cs"].id == from_tf_diff["src/Billing/Rounding.cs"].id


def test_changeset_and_diff_links_to_the_same_file_are_both_kept_with_their_own_provenance() -> None:
    adapter = make_adapter()
    commit_result = extract(adapter, f"fixture:{FIXTURE}", cs(2001))
    issue_result = extract(adapter, f"fixture:{FIXTURE}", wi(101))
    invoice = files_by_path(issue_result)["src/Billing/Invoice.cs"].id

    vias = {
        r.properties["via"]
        for result in (commit_result, issue_result)
        for r in result.relationships
        if r.type == "CHANGES" and r.to_id == invoice
    }
    assert vias == {"changeset 2001", "attachment fix-101.diff"}


# ── live mode: auth and failures ─────────────────────────────────────────

LIVE = "https://ado.example.test/DefaultCollection/Sample"


def recording_transport(seen: list[httpx.Request], status: int = 200) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/wiql"):
            return httpx.Response(status, json={"workItems": []})
        return httpx.Response(status, json={"value": []})

    return httpx.MockTransport(handle)


def live_adapter(transport: httpx.BaseTransport, **overrides: object) -> AzureDevOpsSourceAdapter:
    config = azure_devops_config_from_dict({**CONFIG, **overrides})
    return AzureDevOpsSourceAdapter(config, transport=transport)


def test_a_pat_is_sent_as_basic_auth_from_the_named_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADO_PAT", "s3cret")
    seen: list[httpx.Request] = []

    live_adapter(recording_transport(seen), auth={"pat_env": "ADO_PAT"}).discover(LIVE)

    assert seen[0].headers["authorization"] == "Basic " + base64.b64encode(b":s3cret").decode()
    assert seen[0].url.params["api-version"] == "5.0"


def test_username_and_password_can_use_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_USER", "svc")
    monkeypatch.setenv("ADO_PASS", "pw")
    seen: list[httpx.Request] = []
    auth = {"username_env": "ADO_USER", "password_env": "ADO_PASS", "scheme": "basic"}

    live_adapter(recording_transport(seen), auth=auth).discover(LIVE)

    assert seen[0].headers["authorization"] == "Basic " + base64.b64encode(b"svc:pw").decode()


def test_the_wiql_query_is_scoped_to_the_project_area_paths_and_extra_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADO_PAT", "x")
    seen: list[httpx.Request] = []

    live_adapter(
        recording_transport(seen),
        auth={"pat_env": "ADO_PAT"},
        area_paths=["Sample\\Billing", "Sample\\O'Brien"],
        wiql_where="[System.WorkItemType] <> 'Test Case'",
    ).discover(LIVE)

    query = json.loads(seen[0].content)["query"]
    assert "[System.TeamProject] = 'Sample'" in query
    assert "[System.AreaPath] UNDER 'Sample\\Billing' OR [System.AreaPath] UNDER 'Sample\\O''Brien'" in query
    assert "([System.WorkItemType] <> 'Test Case')" in query


def test_a_live_server_needs_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AzureDevOpsError, match="auth"):
        live_adapter(recording_transport([])).discover(LIVE)

    monkeypatch.delenv("ADO_PAT", raising=False)
    with pytest.raises(AzureDevOpsError, match="ADO_PAT"):
        live_adapter(recording_transport([]), auth={"pat_env": "ADO_PAT"}).discover(LIVE)


def test_a_failed_query_fails_discover(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_PAT", "x")

    with pytest.raises(AzureDevOpsError, match="401"):
        live_adapter(recording_transport([], status=401), auth={"pat_env": "ADO_PAT"}).discover(LIVE)


def test_a_failed_attachment_download_fails_that_documents_load(project: Path) -> None:
    (project / "attachments" / "0a1b2c3d-0000-4000-8000-000000000101").unlink()
    adapter = make_adapter()
    docs = {d.doc_id: d for d in adapter.discover(f"fixture:{project}")}

    with pytest.raises(AzureDevOpsError, match="404"):
        adapter.load(docs[wi(101)])


def test_username_and_password_default_to_ntlm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # On-prem IIS usually only offers Windows auth. The fake server runs a
    # real NTLM handshake: 401 challenge-request, negotiate -> challenge,
    # authenticate -> 200. pyspnego's pure-Python NTLM acceptor (forced, so
    # Windows doesn't use SSPI instead) reads the accepted credentials from
    # NTLM_USER_FILE.
    import spnego

    users = tmp_path / "ntlm_users"
    users.write_text("DOMAIN:svc:pw\n", encoding="utf-8")
    monkeypatch.setenv("NTLM_USER_FILE", str(users))
    monkeypatch.setenv("ADO_USER", r"DOMAIN\svc")
    monkeypatch.setenv("ADO_PASS", "pw")
    server = spnego.server(protocol="ntlm", options=spnego.NegotiateOptions.use_ntlm)
    legs: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        header = request.headers.get("authorization", "")
        if not header:
            legs.append("anonymous")
            return httpx.Response(401, headers={"WWW-Authenticate": "NTLM"})
        token = base64.b64decode(header.split(" ", 1)[1])
        if not legs or legs[-1] == "anonymous":
            legs.append("negotiate")
            challenge = base64.b64encode(server.step(token) or b"").decode()
            return httpx.Response(401, headers={"WWW-Authenticate": f"NTLM {challenge}"})
        legs.append("authenticate")
        server.step(token)  # raises unless the client proved the password
        return httpx.Response(200, json={"workItems": []})

    auth = {"username_env": "ADO_USER", "password_env": "ADO_PASS"}
    live_adapter(httpx.MockTransport(handle), auth=auth).discover(LIVE)

    assert legs == ["anonymous", "negotiate", "authenticate"]


# ── review follow-ups ────────────────────────────────────────────────────


def test_a_work_item_the_query_returned_but_the_fetch_did_not_fails_discover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Treating it as absent would clean it up as removed (ADR-0037).
    monkeypatch.setenv("ADO_PAT", "x")

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wiql"):
            return httpx.Response(200, json={"workItems": [{"id": 1}, {"id": 2}]})
        return httpx.Response(200, json={"value": [{"id": 1, "rev": 1, "fields": {}}]})

    with pytest.raises(AzureDevOpsError, match="2"):
        live_adapter(httpx.MockTransport(handle), auth={"pat_env": "ADO_PAT"}).discover(LIVE)


def test_a_query_at_the_wiql_cap_fails_instead_of_dropping_work_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADO_PAT", "x")

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"workItems": [{"id": i} for i in range(1, 20001)]})

    with pytest.raises(AzureDevOpsError, match="20,000"):
        live_adapter(httpx.MockTransport(handle), auth={"pat_env": "ADO_PAT"}).discover(LIVE)


def test_turning_tls_verification_off_warns_on_every_document() -> None:
    adapter = make_adapter(verify_tls=False)

    for doc_id in (wi(100), cs(2002)):
        result = extract(adapter, f"fixture:{FIXTURE}", doc_id)
        assert result.warning is not None and "TLS verification is off" in result.warning


def test_a_delete_in_any_attached_diff_wins_over_an_edit_in_another(project: Path) -> None:
    item = project / "workitems" / "101.json"
    item.write_text(
        item.read_text(encoding="utf-8").replace(
            '"rel": "Hyperlink"',
            '"rel": "AttachedFile", "url": "https://ado.example.test/DefaultCollection/_apis/wit/attachments/'
            '0a1b2c3d-0000-4000-8000-000000000103", "attributes": {"name": "followup.diff", "resourceSize": 50}}, '
            '{"rel": "Hyperlink"',
        ),
        encoding="utf-8",
    )
    (project / "attachments" / "0a1b2c3d-0000-4000-8000-000000000103").write_bytes(
        b"--- a/src/Billing/Invoice.cs\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
    )

    result = extract(make_adapter(), f"fixture:{project}", wi(101))
    invoice = files_by_path(result)["src/Billing/Invoice.cs"].id
    rel = next(r for r in result.relationships if r.to_id == invoice)

    assert rel.properties["change"] == "delete"
    assert rel.properties["via"] == "attachment fix-101.diff; attachment followup.diff"
