"""One source file, one identity: code root + repo-relative path
(ADR-0035, ADR-0037).

A TFVC changeset reports server paths (`$/Proj/Main/src/Foo.cs`), a
`tf diff` attachment the same, and a git-style diff repo-relative paths
(`src/Foo.cs`, after `diff.py` strips `a/`/`b/`). The config's code roots
fold all of them onto one `ResolvedPath`. A server path matches the longest
configured prefix across all roots, case-insensitively as TFVC does; a
repo-relative diff path belongs to `diff_code_root`. Anything else is
unmapped (`None`) and the caller counts it in a warning.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeRoot:
    name: str
    prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPath:
    root: str
    path: str


def _clean(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


class CodeRoots:
    def __init__(self, roots: list[CodeRoot], diff_code_root: str | None) -> None:
        self._prefixes = sorted(
            ((prefix.replace("\\", "/"), root.name) for root in roots for prefix in root.prefixes),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
        self._diff_code_root = diff_code_root

    def resolve_server_path(self, server_path: str) -> ResolvedPath | None:
        path = server_path.replace("\\", "/")
        folded = path.casefold()
        for prefix, root in self._prefixes:
            if folded.startswith(prefix.casefold()):
                rest = _clean(path[len(prefix) :])
                return ResolvedPath(root=root, path=rest) if rest else None
        return None

    def resolve_diff_path(self, diff_path: str) -> ResolvedPath | None:
        if diff_path.startswith("$/"):
            return self.resolve_server_path(diff_path)
        if self._diff_code_root is None:
            return None
        path = _clean(diff_path)
        return ResolvedPath(root=self._diff_code_root, path=path) if path else None
