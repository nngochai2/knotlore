"""Which files a unified diff changes (ADR-0035, ADR-0037).

Reads only the `---`/`+++` file headers. Hunk bodies are skipped by
counting the line totals in each `@@ -a,b +c,d @@` header, so a removed
line that happens to start with `-- ` can't be mistaken for a header. A
line that can't belong to a hunk ends it early, for headers that miscount.

Handles git-style diffs (`a/`/`b/` prefixes) and `tf diff /format:unified`
output (TFVC server paths with a `;C<n>` version suffix). Paths are
returned with `/` separators and the `a/`/`b/` prefix stripped; mapping
them onto a code root is `paths.py`'s job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ChangeKind = Literal["add", "edit", "delete"]

_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
_DEV_NULL = "/dev/null"


@dataclass(frozen=True)
class DiffFileChange:
    path: str
    change: ChangeKind


def _header_path(raw: str) -> str:
    # Drop a tab-separated timestamp, then a TFVC `;C123` version suffix.
    path = raw.split("\t", 1)[0].strip()
    path = re.sub(r";C\d+$", "", path)
    path = path.replace("\\", "/")
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def parse_diff(text: str) -> list[DiffFileChange]:
    lines = text.splitlines()
    changes: list[DiffFileChange] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        hunk = _HUNK_RE.match(line)
        if hunk:
            old_left = int(hunk.group(1)) if hunk.group(1) is not None else 1
            new_left = int(hunk.group(2)) if hunk.group(2) is not None else 1
            i += 1
            while i < len(lines) and (old_left > 0 or new_left > 0):
                body = lines[i]
                if body.startswith("-"):
                    old_left -= 1
                elif body.startswith("+"):
                    new_left -= 1
                elif body.startswith("\\"):
                    pass  # "\ No newline at end of file"
                elif body and not body.startswith(" "):
                    # Can't be a hunk line: the header miscounted (common
                    # in hand-edited diffs), so the hunk ends here.
                    break
                else:
                    old_left -= 1
                    new_left -= 1
                i += 1
            continue
        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            old = _header_path(line[4:])
            new = _header_path(lines[i + 1][4:])
            if old == _DEV_NULL and new != _DEV_NULL:
                changes.append(DiffFileChange(path=new, change="add"))
            elif new == _DEV_NULL and old != _DEV_NULL:
                changes.append(DiffFileChange(path=old, change="delete"))
            elif new != _DEV_NULL:
                changes.append(DiffFileChange(path=new, change="edit"))
            i += 2
            continue
        i += 1
    return changes
