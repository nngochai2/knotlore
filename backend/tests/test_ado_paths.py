"""Folding TFVC server paths, diff paths and checkout paths onto one code
root + repo-relative path (ADR-0035, ADR-0037)."""

from app.pipeline.sources.azure_devops.paths import CodeRoot, CodeRoots, ResolvedPath

ROOTS = CodeRoots(
    [
        CodeRoot(name="billing", prefixes=("$/Proj/Main/", "$/Proj/Dev/")),
        CodeRoot(name="tools", prefixes=("$/Proj/Main/tools/",)),
    ],
    diff_code_root="billing",
)


def test_tfvc_paths_from_different_branches_fold_onto_one_path() -> None:
    main = ROOTS.resolve_server_path("$/Proj/Main/src/Invoice.cs")
    dev = ROOTS.resolve_server_path("$/Proj/Dev/src/Invoice.cs")

    assert main == ResolvedPath(root="billing", path="src/Invoice.cs")
    assert dev == main


def test_longest_matching_prefix_wins_across_roots() -> None:
    assert ROOTS.resolve_server_path("$/Proj/Main/tools/gen.py") == ResolvedPath(
        root="tools", path="gen.py"
    )


def test_server_prefix_match_ignores_case_like_tfvc_does() -> None:
    assert ROOTS.resolve_server_path("$/proj/main/src/Invoice.cs") == ResolvedPath(
        root="billing", path="src/Invoice.cs"
    )


def test_server_path_under_no_root_is_unmapped() -> None:
    assert ROOTS.resolve_server_path("$/Other/Main/x.cs") is None


def test_repo_relative_diff_path_lands_in_the_diff_code_root() -> None:
    assert ROOTS.resolve_diff_path("src/Invoice.cs") == ResolvedPath(
        root="billing", path="src/Invoice.cs"
    )
    assert ROOTS.resolve_diff_path("./src/Invoice.cs") == ResolvedPath(
        root="billing", path="src/Invoice.cs"
    )


def test_server_path_inside_a_tf_style_diff_resolves_like_a_changeset_path() -> None:
    assert ROOTS.resolve_diff_path("$/Proj/Dev/src/Invoice.cs") == ResolvedPath(
        root="billing", path="src/Invoice.cs"
    )
    assert ROOTS.resolve_diff_path("$/Other/x.cs") is None


def test_diff_paths_are_unmapped_when_no_diff_code_root_is_configured() -> None:
    roots = CodeRoots([CodeRoot(name="billing", prefixes=("$/Proj/Main/",))], diff_code_root=None)

    assert roots.resolve_diff_path("src/Invoice.cs") is None
