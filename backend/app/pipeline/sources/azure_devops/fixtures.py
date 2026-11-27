"""Fixture mode (ADR-0035, ADR-0037): an `httpx` transport that serves a
directory of hand-written, synthetic REST data as a tiny fake Azure DevOps
Server. The adapter and client run unchanged on top of it; only the bytes
on the wire come from files.

Layout (see tests/fixtures/azure_devops/README.md):

    server.json              {"project_url": "https://host/Collection/Project"}
    workitems/<id>.json      a work item as `$expand=relations` returns it
    changesets/<n>.json      a TFVC changeset, plus a "changes" list
    attachments/<guid>       raw attachment bytes

WIQL isn't evaluated: every work item file is in the query result.
Anything the fake doesn't serve is a 404, so an unexpected request fails
loudly instead of silently returning nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

_CHANGESET_RE = re.compile(r"/_apis/tfvc/changesets/(\d+)(/changes)?$")
_ATTACHMENT_RE = re.compile(r"/_apis/wit/attachments/([0-9A-Fa-f-]+)$")


def fixture_project_url(directory: Path) -> str:
    data = json.loads((directory / "server.json").read_text(encoding="utf-8"))
    return str(data["project_url"]).rstrip("/")


def _json(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


class FixtureTransport(httpx.BaseTransport):
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def _work_item_ids(self) -> list[int]:
        return sorted(int(p.stem) for p in (self._dir / "workitems").glob("*.json"))

    def _read(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if request.method == "POST" and path.endswith("/_apis/wit/wiql"):
            return _json({"workItems": [{"id": i} for i in self._work_item_ids()]})

        if request.method == "GET" and path.endswith("/_apis/wit/workitems"):
            wanted = [int(i) for i in params.get("ids", "").split(",") if i]
            items = []
            for item_id in wanted:
                file = self._dir / "workitems" / f"{item_id}.json"
                if file.exists():
                    items.append(self._read(file))
            return _json({"count": len(items), "value": items})

        changeset = _CHANGESET_RE.search(path)
        if request.method == "GET" and changeset:
            file = self._dir / "changesets" / f"{changeset.group(1)}.json"
            if not file.exists():
                return _json({"message": "changeset not found"}, 404)
            data = self._read(file)
            changes = data.pop("changes", [])
            if changeset.group(2):
                skip = int(params.get("$skip", "0"))
                top = int(params.get("$top", "100"))
                page = changes[skip : skip + top]
                return _json({"count": len(page), "value": page})
            return _json(data)

        attachment = _ATTACHMENT_RE.search(path)
        if request.method == "GET" and attachment:
            file = self._dir / "attachments" / attachment.group(1)
            if not file.exists():
                return _json({"message": "attachment not found"}, 404)
            return httpx.Response(200, content=file.read_bytes())

        return _json({"message": f"fixture has no route for {request.method} {path}"}, 404)
