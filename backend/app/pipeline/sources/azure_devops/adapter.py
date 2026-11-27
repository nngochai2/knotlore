"""Azure DevOps Server source adapter (spec §4.1; ADR-0035, ADR-0036,
ADR-0037).

Documents: one per in-scope work item (owning its `ISSUE` node and its
diff-derived `CHANGES` edges) and one per changeset linked from an
in-scope work item (owning its `COMMIT` node and that commit's
`REFERENCES`/`CHANGES` edges).

Ordering and hashing carry the incremental contract (ADR-0037):
- a work item's hash is its revision, so any change re-ingests it;
- a changeset's hash names the revisions of the in-scope work items that
  link it, and `discover()` lists every work item before any changeset.
  A changed work item's `ISSUE` node is rebuilt first, and its changesets
  then re-ingest in the same run and rewrite their `REFERENCES` edges
  into it.

`source_path` is the project URL, or `fixture:<dir>` for the file-serving
transport (`fixtures.py`). `discover` and `load` do all network reads;
`extract` is pure.
"""

from __future__ import annotations

import fnmatch
import hashlib
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.pipeline.rules.engine import format_requirement_id, parse_flags
from app.pipeline.sources.azure_devops.client import AzureDevOpsClient
from app.pipeline.sources.azure_devops.config import AzureDevOpsConfig
from app.pipeline.sources.azure_devops.diff import parse_diff
from app.pipeline.sources.azure_devops.fixtures import FixtureTransport, fixture_project_url
from app.pipeline.sources.azure_devops.paths import ResolvedPath
from app.pipeline.types import Entity, ExtractionResult, LoadedDoc, Relationship, SourceDoc

FIXTURE_PREFIX = "fixture:"
_CHANGESET_LINK_RE = re.compile(r"^vstfs:///VersionControl/Changeset/(\d+)$", re.IGNORECASE)
_WORK_ITEM_URL_RE = re.compile(r"/_apis/wit/workItems/(\d+)$", re.IGNORECASE)
_BLOCK_TAG_RE = re.compile(r"<\s*(?:br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


# ── identity ─────────────────────────────────────────────────────────────


def _node_id(*parts: object) -> str:
    return hashlib.sha1("::".join(str(p) for p in parts).encode()).hexdigest()[:16]


def issue_node_id(project_url: str, work_item_id: int) -> str:
    return _node_id("ISSUE", project_url, work_item_id)


def commit_node_id(project_url: str, changeset_id: int) -> str:
    return _node_id("COMMIT", project_url, "tfvc", changeset_id)


def source_file_node_id(resolved: ResolvedPath) -> str:
    # TFVC paths are case-insensitive, so file identity is too.
    return _node_id("SOURCE_FILE", resolved.root, resolved.path.casefold())


# ── small parsers ────────────────────────────────────────────────────────


def html_to_text(raw: str) -> str:
    """Rich-text work item fields as plain text: block-level tags become
    line breaks, other tags are dropped, entities decoded."""
    text = _TAG_RE.sub(" ", _BLOCK_TAG_RE.sub("\n", raw))
    text = html.unescape(text).replace("\xa0", " ")
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def changeset_ids_linked_from(work_item: dict[str, Any]) -> list[int]:
    ids = set()
    for rel in work_item.get("relations") or []:
        if rel.get("rel") == "ArtifactLink":
            match = _CHANGESET_LINK_RE.match(str(rel.get("url", "")))
            if match:
                ids.add(int(match.group(1)))
    return sorted(ids)


def _work_item_link_target(url: str) -> int | None:
    match = _WORK_ITEM_URL_RE.search(url)
    return int(match.group(1)) if match else None


def _is_diff(name: str, globs: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, g.lower()) for g in globs)


# A TFVC change counts when it touches content; pure branch/merge entries
# can list thousands of files per changeset and are skipped (ADR-0037).
_CONTENT_CHANGES = {"add", "edit", "delete", "rename", "undelete"}


def _changeset_change_kind(change_type: str) -> str | None:
    kinds = {part.strip().lower() for part in change_type.split(",")}
    if not kinds & _CONTENT_CHANGES:
        return None
    if "delete" in kinds:
        return "delete"
    if "add" in kinds or "undelete" in kinds:
        return "add"
    if "rename" in kinds:
        return "rename"
    return "edit"


@dataclass(frozen=True)
class Attachment:
    name: str
    md5: str  # "" when the file was over the size cap and not downloaded
    diff_text: str | None
    oversized_diff: bool = False


@dataclass
class _FileLinks:
    """`CHANGES` edges from one node to source files, one edge per file.
    The sink MERGEs a relationship on (from, type, to), so several sources
    of the same link from one node share an edge and list every `via`."""

    _by_file: dict[str, tuple[ResolvedPath, str, str, set[str]]] = field(default_factory=dict)

    def add(self, resolved: ResolvedPath, change: str, raw_path: str, via: str) -> None:
        node_id = source_file_node_id(resolved)
        existing = self._by_file.get(node_id)
        if existing is None:
            self._by_file[node_id] = (resolved, change, raw_path, {via})
        else:
            existing[3].add(via)

    def build(self, from_id: str) -> tuple[tuple[Entity, ...], tuple[Relationship, ...]]:
        entities: list[Entity] = []
        relationships: list[Relationship] = []
        ordered = sorted(self._by_file.items(), key=lambda kv: (kv[1][0].root, kv[1][0].path))
        for node_id, (resolved, change, raw_path, vias) in ordered:
            entities.append(
                Entity(
                    id=node_id,
                    type="SOURCE_FILE",
                    name=resolved.path,
                    origin="explicit",
                    properties={"code_root": resolved.root, "path": resolved.path},
                )
            )
            relationships.append(
                Relationship(
                    from_id=from_id,
                    to_id=node_id,
                    type="CHANGES",
                    origin="explicit",
                    properties={
                        "via": "; ".join(sorted(vias)),
                        "change": change,
                        "raw_path": raw_path,
                    },
                )
            )
        return tuple(entities), tuple(relationships)


def connect(
    source_path: str,
    config: AzureDevOpsConfig,
    transport: httpx.BaseTransport | None = None,
) -> AzureDevOpsClient:
    if source_path.startswith(FIXTURE_PREFIX):
        directory = Path(source_path[len(FIXTURE_PREFIX) :])
        return AzureDevOpsClient(
            fixture_project_url(directory),
            config,
            transport=FixtureTransport(directory),
            require_auth=False,
        )
    return AzureDevOpsClient(source_path, config, transport=transport)


class AzureDevOpsSourceAdapter:
    source_type = "azure_devops"

    def __init__(
        self, config: AzureDevOpsConfig, transport: httpx.BaseTransport | None = None
    ) -> None:
        """`transport` overrides httpx's for a live `source_path` (tests);
        a `fixture:` path always uses the fixture transport."""
        self.config = config
        self._transport = transport
        self._client: AzureDevOpsClient | None = None
        self._work_items: dict[str, dict[str, Any]] = {}
        self._changesets: dict[str, tuple[int, list[int]]] = {}

    @property
    def client(self) -> AzureDevOpsClient:
        if self._client is None:
            raise RuntimeError("discover() must run before load()/extract()")
        return self._client

    def _doc_id(self, kind: str, native_id: int) -> str:
        return f"azure_devops:{self.client.project_url}:{kind}:{native_id}"

    # ── discover ─────────────────────────────────────────────────────────

    def discover(self, source_path: str) -> list[SourceDoc]:
        """Lists every in-scope work item, then every changeset they link.
        Any request failure propagates, failing the job before the
        pipeline computes removals (ADR-0037)."""
        self._client = connect(source_path, self.config, self._transport)
        client = self._client
        work_items = client.get_work_items(client.query_work_item_ids())
        work_items.sort(key=lambda item: int(item["id"]))

        self._work_items = {}
        linkers: dict[int, list[tuple[int, int]]] = {}
        docs: list[SourceDoc] = []
        for item in work_items:
            item_id, rev = int(item["id"]), int(item["rev"])
            doc_id = self._doc_id("wi", item_id)
            self._work_items[doc_id] = item
            docs.append(
                SourceDoc(
                    doc_id=doc_id,
                    path=f"{client.project_url}/_workitems/edit/{item_id}",
                    content_hash=f"rev:{rev}",
                )
            )
            for changeset_id in changeset_ids_linked_from(item):
                linkers.setdefault(changeset_id, []).append((item_id, rev))

        self._changesets = {}
        for changeset_id in sorted(linkers):
            doc_id = self._doc_id("cs", changeset_id)
            linked = sorted(linkers[changeset_id])
            self._changesets[doc_id] = (changeset_id, [i for i, _ in linked])
            revisions = ",".join(f"{i}@{r}" for i, r in linked)
            docs.append(
                SourceDoc(
                    doc_id=doc_id,
                    path=f"{client.project_url}/_versionControl/changeset/{changeset_id}",
                    content_hash=f"cs:{changeset_id}|{revisions}",
                )
            )
        return docs

    # ── load: every network read for one document ───────────────────────

    def load(self, doc: SourceDoc) -> LoadedDoc:
        """Fetches what `extract` needs. Any request failure propagates, so
        the pipeline marks this document failed and retries it next run
        (ADR-0037)."""
        if doc.doc_id in self._work_items:
            return self._load_work_item(doc)
        if doc.doc_id in self._changesets:
            return self._load_changeset(doc)
        raise KeyError(f"{doc.doc_id} was not discovered by this adapter")

    def _load_work_item(self, doc: SourceDoc) -> LoadedDoc:
        item = self._work_items[doc.doc_id]
        attachments: list[Attachment] = []
        for rel in item.get("relations") or []:
            if rel.get("rel") != "AttachedFile":
                continue
            attributes = rel.get("attributes") or {}
            name = str(attributes.get("name", ""))
            size = int(attributes.get("resourceSize", 0) or 0)
            is_diff = _is_diff(name, self.config.diff_globs)
            if size > self.config.max_attachment_bytes:
                attachments.append(Attachment(name, md5="", diff_text=None, oversized_diff=is_diff))
                continue
            data = self.client.download(str(rel["url"]))
            attachments.append(
                Attachment(
                    name,
                    md5=hashlib.md5(data).hexdigest(),
                    diff_text=data.decode("utf-8-sig", errors="replace") if is_diff else None,
                )
            )
        return LoadedDoc(
            doc=doc,
            content=str((item.get("fields") or {}).get("System.Title", "")),
            metadata={"kind": "work_item", "item": item, "attachments": attachments},
        )

    def _load_changeset(self, doc: SourceDoc) -> LoadedDoc:
        changeset_id, linked_ids = self._changesets[doc.doc_id]
        changeset = self.client.get_changeset(changeset_id)
        changes = list(self.client.iter_changeset_changes(changeset_id))
        return LoadedDoc(
            doc=doc,
            content=str(changeset.get("comment", "")),
            metadata={
                "kind": "changeset",
                "changeset": changeset,
                "changes": changes,
                "work_item_ids": linked_ids,
            },
        )

    # ── extract: pure, from what `load` fetched ─────────────────────────

    def extract(self, loaded: LoadedDoc, config: Any) -> ExtractionResult:
        if loaded.metadata.get("kind") == "work_item":
            return self._extract_work_item(loaded)
        return self._extract_changeset(loaded)

    def _requirement_ids(self, *texts: str) -> list[str]:
        rule = self.config.requirement_id
        pattern = re.compile(rule.pattern, parse_flags(rule.flags))
        return sorted(
            {format_requirement_id(m, rule.format) for text in texts for m in pattern.finditer(text)}
        )

    def _field(self, fields: dict[str, Any], logical: str) -> Any:
        for reference_name in self.config.fields.get(logical, ()):
            if fields.get(reference_name) not in (None, ""):
                return fields[reference_name]
        return None

    def _extract_work_item(self, loaded: LoadedDoc) -> ExtractionResult:
        item: dict[str, Any] = loaded.metadata["item"]  # type: ignore[assignment]
        attachments: list[Attachment] = loaded.metadata["attachments"]  # type: ignore[assignment]
        fields = item.get("fields") or {}
        item_id = int(item["id"])
        title = str(fields.get("System.Title", ""))
        description = html_to_text(str(self._field(fields, "description") or ""))
        acceptance = html_to_text(str(self._field(fields, "acceptance_criteria") or ""))

        parent_id: int | None = None
        related: list[int] = []
        for rel in item.get("relations") or []:
            target = _work_item_link_target(str(rel.get("url", "")))
            if target is None:
                continue
            if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
                parent_id = target
            elif rel.get("rel") == "System.LinkTypes.Related":
                related.append(target)

        issue = Entity(
            id=issue_node_id(self.client.project_url, item_id),
            type="ISSUE",
            name=title,
            origin="explicit",
            properties={
                "tracker": "azure-devops",
                "project_url": self.client.project_url,
                "work_item_id": item_id,
                "kind": fields.get("System.WorkItemType"),
                "state": fields.get("System.State"),
                "area_path": fields.get("System.AreaPath"),
                "iteration_path": fields.get("System.IterationPath"),
                "estimate": self._field(fields, "estimate"),
                "description": description,
                "acceptance_criteria": acceptance,
                "requirement_ids": self._requirement_ids(title, description, acceptance),
                "parent_id": parent_id,
                "related_ids": sorted(related),
                "attachment_names": [a.name for a in attachments],
                "attachment_md5s": [a.md5 for a in attachments],
            },
        )

        roots = self.config.code_root_map()
        files = _FileLinks()
        unmapped = 0
        warnings: list[str] = []
        for attachment in attachments:
            if attachment.oversized_diff:
                warnings.append(f"skipped {attachment.name}: larger than max_attachment_bytes")
            if attachment.diff_text is None:
                continue
            for change in parse_diff(attachment.diff_text):
                resolved = roots.resolve_diff_path(change.path)
                if resolved is None:
                    unmapped += 1
                    continue
                files.add(resolved, change.change, change.path, f"attachment {attachment.name}")
        if unmapped:
            warnings.append(f"{unmapped} diff path(s) matched no code root")

        file_entities, relationships = files.build(issue.id)
        return ExtractionResult(
            doc_id=loaded.doc.doc_id,
            content_hash=loaded.doc.content_hash,
            entities=(issue, *file_entities),
            relationships=relationships,
            warning="; ".join(warnings) or None,
        )

    def _extract_changeset(self, loaded: LoadedDoc) -> ExtractionResult:
        changeset: dict[str, Any] = loaded.metadata["changeset"]  # type: ignore[assignment]
        changes: list[dict[str, Any]] = loaded.metadata["changes"]  # type: ignore[assignment]
        work_item_ids: list[int] = loaded.metadata["work_item_ids"]  # type: ignore[assignment]
        project_url = self.client.project_url
        changeset_id = int(changeset["changesetId"])
        comment = str(changeset.get("comment") or "")
        via = f"changeset {changeset_id}"

        commit = Entity(
            id=commit_node_id(project_url, changeset_id),
            type="COMMIT",
            name=f"C{changeset_id}",
            origin="explicit",
            properties={
                "vcs": "tfvc",
                "native_id": str(changeset_id),
                "project_url": project_url,
                "author": (changeset.get("author") or {}).get("displayName"),
                "committed_at": changeset.get("createdDate"),
                "comment": comment,
                "requirement_ids": self._requirement_ids(comment),
            },
        )
        references = tuple(
            Relationship(
                from_id=commit.id,
                to_id=issue_node_id(project_url, work_item_id),
                type="REFERENCES",
                origin="explicit",
                properties={"via": via},
            )
            for work_item_id in work_item_ids
        )

        roots = self.config.code_root_map()
        files = _FileLinks()
        unmapped = 0
        for change in changes:
            kind = _changeset_change_kind(str(change.get("changeType", "")))
            if kind is None:
                continue
            raw_path = str((change.get("item") or {}).get("path", ""))
            resolved = roots.resolve_server_path(raw_path)
            if resolved is None:
                unmapped += 1
                continue
            files.add(resolved, kind, raw_path, via)

        file_entities, file_links = files.build(commit.id)
        return ExtractionResult(
            doc_id=loaded.doc.doc_id,
            content_hash=loaded.doc.content_hash,
            entities=(commit, *file_entities),
            relationships=references + file_links,
            warning=f"{unmapped} changeset path(s) matched no code root" if unmapped else None,
        )
