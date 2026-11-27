"""Azure DevOps Server source config: JSON Schema + typed config
(spec §7; ADR-0035, ADR-0037).

The config never holds a secret: `auth` names the environment variables
that do. The filter (`area_paths`, `wiql_where`) lives here, not in the
Instance, so it can change over an Instance's history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator, ValidationError

from app.pipeline.sources.azure_devops.paths import CodeRoot, CodeRoots

DEFAULT_DIFF_GLOBS = ("*.diff", "*.patch")
DEFAULT_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

# Candidate field reference names per logical field, first present wins.
# Covers the Agile, Scrum and CMMI process templates; a config overrides
# any entry with its own list.
DEFAULT_FIELDS: dict[str, tuple[str, ...]] = {
    "description": ("System.Description", "Microsoft.VSTS.TCM.ReproSteps"),
    "acceptance_criteria": ("Microsoft.VSTS.Common.AcceptanceCriteria",),
    "estimate": (
        "Microsoft.VSTS.Scheduling.OriginalEstimate",
        "Microsoft.VSTS.Scheduling.Effort",
        "Microsoft.VSTS.Scheduling.StoryPoints",
        "Microsoft.VSTS.Scheduling.Size",
    ),
}

_ENV_NAME = {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"}

AZURE_DEVOPS_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Azure DevOps Server source config",
    "type": "object",
    "required": ["name", "requirement_id", "code_roots"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "area_paths": {
            "description": "Area paths to include (matched with UNDER). Empty means the whole project.",
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "wiql_where": {
            "description": "Extra WIQL WHERE clause, ANDed with the project and area-path filter.",
            "type": "string",
            "minLength": 1,
        },
        "auth": {
            "description": "Names of the environment variables holding credentials. Never the values.",
            "oneOf": [
                {
                    "type": "object",
                    "required": ["pat_env"],
                    "additionalProperties": False,
                    "properties": {"pat_env": _ENV_NAME},
                },
                {
                    "type": "object",
                    "required": ["username_env", "password_env"],
                    "additionalProperties": False,
                    "properties": {
                        "username_env": _ENV_NAME,
                        "password_env": _ENV_NAME,
                        "scheme": {"enum": ["ntlm", "basic"], "default": "ntlm"},
                    },
                },
            ],
        },
        "ca_bundle": {
            "description": "Path to a CA bundle for a server with an internal certificate authority.",
            "type": "string",
            "minLength": 1,
        },
        "verify_tls": {
            "description": "Verify the server's TLS certificate. false adds a warning to every document.",
            "type": "boolean",
            "default": True,
        },
        "fields": {
            "description": "Override the work item field reference names tried for each logical field.",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                name: {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1}
                for name in DEFAULT_FIELDS
            },
        },
        "requirement_id": {
            "description": "How requirement IDs are found in work item text and changeset comments.",
            "type": "object",
            "required": ["pattern"],
            "additionalProperties": False,
            "properties": {
                "pattern": {"type": "string", "minLength": 1},
                "flags": {"type": "string"},
                "format": {"type": "string"},
            },
        },
        "code_roots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "prefixes"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "prefixes": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
        "diff_code_root": {
            "description": "Code root that repo-relative diff paths belong to. Defaults to the first code root.",
            "type": "string",
            "minLength": 1,
        },
        "diff_globs": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "default": list(DEFAULT_DIFF_GLOBS),
        },
        "max_attachment_bytes": {
            "type": "integer",
            "minimum": 1,
            "default": DEFAULT_MAX_ATTACHMENT_BYTES,
        },
    },
}


def validate_azure_devops_config(raw: dict[str, Any]) -> None:
    Draft202012Validator(AZURE_DEVOPS_CONFIG_SCHEMA).validate(raw)
    roots = {r["name"] for r in raw["code_roots"]}
    diff_root = raw.get("diff_code_root")
    if diff_root is not None and diff_root not in roots:
        raise ValidationError(
            f"diff_code_root {diff_root!r} is not one of the code_roots {sorted(roots)}",
            path=["diff_code_root"],
        )
    re.compile(raw["requirement_id"]["pattern"])


@dataclass(frozen=True)
class PatAuth:
    pat_env: str


@dataclass(frozen=True)
class PasswordAuth:
    username_env: str
    password_env: str
    scheme: Literal["ntlm", "basic"] = "ntlm"


@dataclass(frozen=True)
class RequirementIdRule:
    pattern: str
    flags: str = ""
    format: str = "{}"


@dataclass(frozen=True)
class AzureDevOpsConfig:
    name: str
    requirement_id: RequirementIdRule
    code_roots: tuple[CodeRoot, ...]
    diff_code_root: str
    area_paths: tuple[str, ...] = ()
    wiql_where: str | None = None
    auth: PatAuth | PasswordAuth | None = None
    ca_bundle: str | None = None
    verify_tls: bool = True
    fields: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_FIELDS))
    diff_globs: tuple[str, ...] = DEFAULT_DIFF_GLOBS
    max_attachment_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES

    def path_resolver(self) -> CodeRoots:
        return CodeRoots(list(self.code_roots), diff_code_root=self.diff_code_root)


def azure_devops_config_from_dict(raw: dict[str, Any]) -> AzureDevOpsConfig:
    validate_azure_devops_config(raw)
    auth_raw = raw.get("auth")
    auth: PatAuth | PasswordAuth | None
    if auth_raw is None:
        auth = None
    elif "pat_env" in auth_raw:
        auth = PatAuth(pat_env=auth_raw["pat_env"])
    else:
        auth = PasswordAuth(
            username_env=auth_raw["username_env"],
            password_env=auth_raw["password_env"],
            scheme=auth_raw.get("scheme", "ntlm"),
        )
    roots = tuple(CodeRoot(name=r["name"], prefixes=tuple(r["prefixes"])) for r in raw["code_roots"])
    fields = dict(DEFAULT_FIELDS)
    fields.update({k: tuple(v) for k, v in raw.get("fields", {}).items()})
    req = raw["requirement_id"]
    return AzureDevOpsConfig(
        name=raw["name"],
        requirement_id=RequirementIdRule(
            pattern=req["pattern"], flags=req.get("flags", ""), format=req.get("format", "{}")
        ),
        code_roots=roots,
        diff_code_root=raw.get("diff_code_root", roots[0].name),
        area_paths=tuple(raw.get("area_paths", ())),
        wiql_where=raw.get("wiql_where"),
        auth=auth,
        ca_bundle=raw.get("ca_bundle"),
        verify_tls=raw.get("verify_tls", True),
        fields=fields,
        diff_globs=tuple(raw.get("diff_globs", DEFAULT_DIFF_GLOBS)),
        max_attachment_bytes=raw.get("max_attachment_bytes", DEFAULT_MAX_ATTACHMENT_BYTES),
    )


def load_azure_devops_config(path: str) -> AzureDevOpsConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return azure_devops_config_from_dict(raw)
