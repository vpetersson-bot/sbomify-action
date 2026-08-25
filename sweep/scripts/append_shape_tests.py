#!/usr/bin/env python3
"""Append the selection tests to the ecosystem-lock suite."""

import pathlib

TESTS = '''

class TestTheRabbitmqShape:
    """Selection, not just detection: an Erlang repository whose only readable
    input belongs to a JavaScript sub-project."""

    @staticmethod
    def _selected(tmp_path, files, discovered):
        from sbomify_action.cli.wizard.screens.discover import DiscoverScreen
        from sbomify_action.cli.wizard.state import DiscoveredLockfile

        touch(tmp_path, *files)
        rows = [
            DiscoveredLockfile(
                path=tmp_path / rel,
                rel_path=Path(rel),
                ecosystem=eco,
                suggested_name=rel.replace("/", "-"),
            )
            for rel, eco in discovered
        ]

        wizard = type(
            "W",
            (),
            {
                "state": type("S", (), {"discovered": rows})(),
                "opts": type("O", (), {"repo_root": tmp_path})(),
            },
        )()
        screen = DiscoverScreen.__new__(DiscoverScreen)
        # The screen reaches the wizard through a property on the base class;
        # bypassing Textual's app plumbing keeps this a unit test of the rule.
        object.__setattr__(screen, "__dict__", {"_wizard": wizard})
        return DiscoverScreen._default_selected.__get__(screen)()

    def test_an_erlang_project_does_not_default_to_its_selenium_harness(self, tmp_path):
        selected = self._selected(tmp_path, ["rebar.config", "erlang.mk"], [("selenium/package.json", "javascript")])

        assert selected == set(), "offered a JavaScript sub-project as an Erlang repository's SBOM"

    def test_a_c_project_does_not_default_to_its_python_test_requirements(self, tmp_path):
        selected = self._selected(tmp_path, ["CMakeLists.txt"], [("tests/requirements.txt", "python")])

        assert selected == set()

    def test_the_projects_own_input_is_still_chosen(self, tmp_path):
        selected = self._selected(
            tmp_path, ["rebar.config"], [("rebar.lock", "erlang"), ("selenium/package.json", "javascript")]
        )

        assert selected == {0}, "should take the Erlang input and leave the JavaScript one"

    def test_a_silent_root_still_gets_a_default(self, tmp_path):
        """The rule must not turn every monorepo into an empty selection."""
        selected = self._selected(
            tmp_path, ["README.md"], [("frontend/package.json", "javascript"), ("backend/go.sum", "go")]
        )

        assert selected == {0, 1}

    def test_a_polyglot_root_keeps_both(self, tmp_path):
        selected = self._selected(
            tmp_path,
            ["package.json", "composer.json"],
            [("package-lock.json", "javascript"), ("composer.lock", "php")],
        )

        assert selected == {0, 1}
'''

path = pathlib.Path(
    "/home/ubuntu/code/sbomify-action/.claude/worktrees/purrfect-beaming-snowglobe/tests/test_ecosystem_lock.py"
)
path.write_text(path.read_text() + TESTS)
print("appended")
