"""One source file, one identity: code root + repo-relative path
(ADR-0035, ADR-0037).

A TFVC changeset reports server paths (`$/Proj/Main/src/Foo.cs`), a
`tf diff` attachment the same, and a git-style diff or a checkout
repo-relative paths (`src/Foo.cs`, after `diff.py` strips `a/`/`b/`). The
config's code roots fold all of them onto one `ResolvedPath`. A server path
matches the longest configured prefix across all roots, case-insensitively
as TFVC does; a repo-relative path belongs to `diff_code_root`. Anything
else is unmapped (`None`) and the caller counts it in a warning.
"""

from __future__ import annotations

from dataclasses import dataclass


def to_posix(path: str) -> str:
    return path.replace("\\", "/")


@dataclass(frozen=True)
class CodeRoot:
    name: str
    prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPath:
    root: str
    path: str


def _clean(path: str) -> str:
    path = to_posix(path)
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


class CodeRoots:
    def __init__(self, roots: list[CodeRoot], diff_code_root: str | None) -> None:
        self._prefixes = sorted(
            ((to_posix(prefix), root.name) for root in roots for prefix in root.prefixes),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
        self._diff_code_root = diff_code_root

    def resolve_server_path(self, server_path: str) -> ResolvedPath | None:
        path = to_posix(server_path)
        folded = path.casefold()
        for prefix, root in self._prefixes:
            if folded.startswith(prefix.casefold()):
                rest = _clean(path[len(prefix) :])
                return ResolvedPath(root=root, path=rest) if rest else None
        return None

    def resolve_relative_path(self, path: str) -> ResolvedPath | None:
        """A diff or checkout path: a TFVC server path if it is one,
        otherwise repo-relative under `diff_code_root`."""
        if path.startswith("$/"):
            return self.resolve_server_path(path)
        if self._diff_code_root is None:
            return None
        relative = _clean(path)
        return ResolvedPath(root=self._diff_code_root, path=relative) if relative else None
