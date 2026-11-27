"""Unified-diff header parsing for diffs attached to Azure DevOps work items
(ADR-0035, ADR-0037): which files a delivered diff changes, and how."""

from app.pipeline.sources.azure_devops.diff import DiffFileChange, parse_diff


def test_git_style_diff_yields_each_changed_file_with_prefix_stripped() -> None:
    text = (
        "diff --git a/src/Billing/Invoice.cs b/src/Billing/Invoice.cs\n"
        "index 1111111..2222222 100644\n"
        "--- a/src/Billing/Invoice.cs\n"
        "+++ b/src/Billing/Invoice.cs\n"
        "@@ -1,3 +1,3 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/src/Billing/Tax.cs b/src/Billing/Tax.cs\n"
        "--- a/src/Billing/Tax.cs\n"
        "+++ b/src/Billing/Tax.cs\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
    )

    assert parse_diff(text) == [
        DiffFileChange(path="src/Billing/Invoice.cs", change="edit"),
        DiffFileChange(path="src/Billing/Tax.cs", change="edit"),
    ]


def test_added_and_deleted_files_are_recognised_from_dev_null() -> None:
    text = (
        "--- /dev/null\n"
        "+++ b/src/New.cs\n"
        "@@ -0,0 +1 @@\n"
        "+x\n"
        "--- a/src/Gone.cs\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-x\n"
    )

    assert parse_diff(text) == [
        DiffFileChange(path="src/New.cs", change="add"),
        DiffFileChange(path="src/Gone.cs", change="delete"),
    ]


def test_tf_diff_style_keeps_server_path_and_strips_changeset_suffix() -> None:
    # `tf diff /format:unified` writes TFVC server paths with a ;C<n>
    # version suffix (old side) and sometimes a tab-separated timestamp.
    text = (
        "--- $/Proj/Main/src/Billing/Invoice.cs;C123\n"
        "+++ $/Proj/Main/src/Billing/Invoice.cs\t2026-11-20 10:00:00\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
    )

    assert parse_diff(text) == [
        DiffFileChange(path="$/Proj/Main/src/Billing/Invoice.cs", change="edit"),
    ]


def test_windows_line_endings_and_backslashes_are_normalised() -> None:
    text = "--- a/src\\Billing\\Invoice.cs\r\n+++ b/src\\Billing\\Invoice.cs\r\n@@ -1 +1 @@\r\n"

    assert parse_diff(text) == [DiffFileChange(path="src/Billing/Invoice.cs", change="edit")]


def test_hunk_lines_that_look_like_headers_are_not_mistaken_for_files() -> None:
    # A removed line whose content starts with "-- " shows as "--- " inside
    # a hunk; it must not be read as a new file header.
    text = (
        "--- a/db/schema.sql\n"
        "+++ b/db/schema.sql\n"
        "@@ -1,2 +1,1 @@\n"
        "--- a comment\n"
        " keep\n"
    )

    assert parse_diff(text) == [DiffFileChange(path="db/schema.sql", change="edit")]


def test_text_that_is_not_a_diff_yields_nothing() -> None:
    assert parse_diff("Release notes\nNothing to see here.\n") == []
