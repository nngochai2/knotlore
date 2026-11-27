"""The Azure DevOps source wired into the product: config validation via
the Configs API, preview via `DryRunSink`, and the Instances catalog
(spec §7, §8; ADR-0037)."""

from __future__ import annotations

import shutil
from pathlib import Path

from test_api_preview import FIXTURES_DIR, _client


def _copy_ado_config(configs_dir: Path) -> None:
    shutil.copy(FIXTURES_DIR / "azure_devops_config.yml", configs_dir / "sample_ado.yml")


def test_an_azure_devops_config_is_listed_with_its_source_type_and_schema(tmp_path: Path) -> None:
    _copy_ado_config(tmp_path)
    with _client(str(tmp_path)) as client:
        listed = client.get("/configs").json()
        detail = client.get("/configs/sample_ado").json()

    assert {"id": "sample_ado", "source_type": "azure_devops", "title": "Sample project"} in listed["configs"]
    assert detail["json_schema"]["title"] == "Azure DevOps Server source config"


def test_an_invalid_azure_devops_config_is_rejected_with_schema_errors(tmp_path: Path) -> None:
    body = {
        "id": "broken",
        "source_type": "azure_devops",
        "data": {
            "name": "Broken",
            "requirement_id": {"pattern": r"BR-(\d+)"},
            "code_roots": [{"name": "billing", "prefixes": ["$/P/Main/"]}],
            "auth": {"pat": "a-secret-value"},
        },
    }
    with _client(str(tmp_path)) as client:
        resp = client.post("/configs", json=body)

    assert resp.status_code == 422
    assert not (tmp_path / "broken.yml").exists()


def test_preview_runs_a_fixture_work_item_through_the_real_pipeline(tmp_path: Path) -> None:
    _copy_ado_config(tmp_path)
    with _client(str(tmp_path)) as client:
        resp = client.post("/configs/sample_ado/preview", data={"fixture_id": "101"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["doc_id"].endswith(":wi:101")
    types = sorted(e["type"] for e in body["entities"])
    assert types == ["ISSUE", "SOURCE_FILE", "SOURCE_FILE"]
    assert {r["type"] for r in body["relationships"]} == {"CHANGES"}


def test_preview_of_an_unknown_work_item_is_not_found(tmp_path: Path) -> None:
    _copy_ado_config(tmp_path)
    with _client(str(tmp_path)) as client:
        resp = client.post("/configs/sample_ado/preview", data={"fixture_id": "999"})

    assert resp.status_code == 404


def test_preview_rejects_an_uploaded_sample(tmp_path: Path) -> None:
    _copy_ado_config(tmp_path)
    with _client(str(tmp_path)) as client:
        resp = client.post(
            "/configs/sample_ado/preview", files={"sample": ("x.json", b"{}", "application/json")}
        )

    assert resp.status_code == 422
    assert "fixture" in resp.json()["detail"]


def test_an_azure_devops_instance_is_catalogued_with_its_project_url(tmp_path: Path) -> None:
    with _client(str(tmp_path)) as client:
        created = client.post(
            "/instances",
            json={
                "source_type": "azure_devops",
                "source_path": "https://ado.example.test/DefaultCollection/Sample",
                "sinks": ["neo4j"],
            },
        )
        assert created.status_code == 201, created.text
        listed = client.get("/instances").json()

    instance = listed["instances"][0]
    assert instance["source_type"] == "azure_devops"
    assert instance["name"] == "Azure DevOps project — Sample"
