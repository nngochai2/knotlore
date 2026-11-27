"""Read-only REST client for one Azure DevOps Server project
(`api-version 5.0`, Server 2019+; ADR-0035).

The transport is injectable: live mode uses httpx's default, fixture mode
a `FixtureTransport`. Everything above the transport is the same code
path. Credentials come from environment variables named in the config
(ADR-0037); they are read here, at connect time, and never stored on the
config.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx

from app.pipeline.sources.azure_devops.config import AzureDevOpsConfig, PasswordAuth, PatAuth

API_VERSION = "5.0"
WORK_ITEM_BATCH = 200  # the REST API's per-request maximum
CHANGES_PAGE = 1000
_TIMEOUT = httpx.Timeout(30.0, read=120.0)


class AzureDevOpsError(RuntimeError):
    """A request to the server failed (network, auth or HTTP status)."""


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise AzureDevOpsError(f"environment variable {name} is not set")
    return value


def _auth(config: AzureDevOpsConfig) -> httpx.Auth | None:
    auth = config.auth
    if auth is None:
        return None
    if isinstance(auth, PatAuth):
        # Azure DevOps takes a PAT as the password of basic auth.
        return httpx.BasicAuth("", _env(auth.pat_env))
    assert isinstance(auth, PasswordAuth)
    username, password = _env(auth.username_env), _env(auth.password_env)
    if auth.scheme == "basic":
        return httpx.BasicAuth(username, password)
    from httpx_ntlm import HttpNtlmAuth  # type: ignore[import-untyped]

    ntlm: httpx.Auth = HttpNtlmAuth(username, password)
    return ntlm


def _verify(config: AzureDevOpsConfig) -> bool | str:
    if config.ca_bundle:
        return config.ca_bundle
    return config.verify_tls


def _wiql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class AzureDevOpsClient:
    def __init__(
        self,
        project_url: str,
        config: AzureDevOpsConfig,
        transport: httpx.BaseTransport | None = None,
        require_auth: bool = True,
    ) -> None:
        self.project_url = project_url.rstrip("/")
        self.project = self.project_url.rsplit("/", 1)[-1]
        self._config = config
        if require_auth and config.auth is None:
            raise AzureDevOpsError("the source config has no `auth`; a live server needs credentials")
        self._http = httpx.Client(
            auth=_auth(config),
            verify=_verify(config),
            timeout=_TIMEOUT,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        params = {"api-version": API_VERSION, **kwargs.pop("params", {})}
        try:
            response = self._http.request(method, url, params=params, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AzureDevOpsError(f"{method} {url} failed: {exc}") from exc
        return response

    def _api(self, path: str) -> str:
        return f"{self.project_url}/_apis/{path}"

    def query_work_item_ids(self) -> list[int]:
        clauses = [f"[System.TeamProject] = {_wiql_string(self.project)}"]
        if self._config.area_paths:
            areas = " OR ".join(f"[System.AreaPath] UNDER {_wiql_string(a)}" for a in self._config.area_paths)
            clauses.append(f"({areas})")
        if self._config.wiql_where:
            clauses.append(f"({self._config.wiql_where})")
        query = f"SELECT [System.Id] FROM WorkItems WHERE {' AND '.join(clauses)} ORDER BY [System.Id]"
        data = self._request("POST", self._api("wit/wiql"), json={"query": query}).json()
        return sorted(int(item["id"]) for item in data.get("workItems", []))

    def get_work_items(self, ids: list[int]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for start in range(0, len(ids), WORK_ITEM_BATCH):
            batch = ids[start : start + WORK_ITEM_BATCH]
            data = self._request(
                "GET",
                self._api("wit/workitems"),
                params={
                    "ids": ",".join(str(i) for i in batch),
                    "$expand": "relations",
                    "errorPolicy": "omit",
                },
            ).json()
            items.extend(item for item in data.get("value", []) if item)
        return items

    def get_changeset(self, changeset_id: int) -> dict[str, Any]:
        data: dict[str, Any] = self._request(
            "GET", self._api(f"tfvc/changesets/{changeset_id}")
        ).json()
        return data

    def iter_changeset_changes(self, changeset_id: int) -> Iterator[dict[str, Any]]:
        skip = 0
        while True:
            page = self._request(
                "GET",
                self._api(f"tfvc/changesets/{changeset_id}/changes"),
                params={"$top": CHANGES_PAGE, "$skip": skip},
            ).json().get("value", [])
            yield from page
            if len(page) < CHANGES_PAGE:
                return
            skip += CHANGES_PAGE

    def download(self, url: str) -> bytes:
        return self._request("GET", url).content
