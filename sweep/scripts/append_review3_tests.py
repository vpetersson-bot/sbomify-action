#!/usr/bin/env python3
"""Append tests for the third review round's three findings."""

import pathlib

BASE = pathlib.Path("/home/ubuntu/code/sbomify-action/.claude/worktrees/purrfect-beaming-snowglobe/tests")

SUBSTITUTION = '''

def test_a_symlinked_lockfile_keeps_its_own_path(project):
    """Resolving the candidate rewrites both its name and its parent. A
    project-local `uv.lock -> shared/base.lock` would reach the generator as
    `shared/base.lock`, scanning the wrong directory under a name nothing
    recognises."""
    shared = project / "shared"
    shared.mkdir()
    (shared / "base.lock").write_text("")
    (project / "uv.lock").symlink_to(shared / "base.lock")

    result = _expand_lock_file_or_substitute("poetry.lock")

    assert result.endswith("uv.lock"), "handed back the symlink target instead of the project's own path"


def test_a_dotnet_project_file_can_substitute(project):
    """.csproj and friends are matched by suffix, not by name, so a scan over
    fixed names alone could never find one -- a stale packages.lock.json
    failed even with exactly one project file beside it."""
    (project / "Thing.csproj").write_text("<Project />")

    assert _expand_lock_file_or_substitute("packages.lock.json").endswith("Thing.csproj")


def test_two_dotnet_project_files_are_still_ambiguous(project):
    (project / "One.csproj").write_text("<Project />")
    (project / "Two.csproj").write_text("<Project />")

    with pytest.raises(FileProcessingError):
        _expand_lock_file_or_substitute("packages.lock.json")
'''

PINNED = '''

class TestPinnedMeansEveryVersionIsDecided:
    """`==` is necessary and not sufficient, and a file that defers to another
    file has not decided anything."""

    @pytest.mark.parametrize(
        "contents",
        [
            "flask==3.1.0\\n-r unpinned.txt\\n",       # defers to a file we do not read
            "flask==3.1.0\\n-c constraints.txt\\n",    # same, via constraints
            "flask==3.1.0\\n-e .\\n",                  # an editable install
            "package==1.*\\n",                        # equality against a wildcard
        ],
    )
    def test_these_are_not_pinned(self, tmp_path, contents):
        (tmp_path / "requirements.txt").write_text(contents)

        assert resolution_was_inferred(str(tmp_path / "requirements.txt"))

    def test_pip_options_do_not_make_it_unpinned(self, tmp_path):
        """--index-url and --hash configure pip; they do not request a package."""
        (tmp_path / "requirements.txt").write_text(
            "--index-url https://pypi.org/simple\\n"
            "flask==3.1.0 --hash=sha256:abc\\n"
        )

        assert not resolution_was_inferred(str(tmp_path / "requirements.txt"))
'''

for name, block in (("test_lock_file_substitution.py", SUBSTITUTION), ("test_inferred_resolution.py", PINNED)):
    path = BASE / name
    path.write_text(path.read_text() + block)
    print(f"appended to {name}")
