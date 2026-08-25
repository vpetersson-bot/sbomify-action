#!/usr/bin/env python3
"""Append the cleanup-safety test to the npm resolution suite."""

import pathlib

TEST = '''

def test_a_failed_cleanup_does_not_mask_the_real_error(tmp_path, monkeypatch, caplog):
    """An unlink raising inside a finally replaces the exception that brought
    us there, so a genuine generation failure would surface as a permissions
    problem. And a surviving lock file reads as a committed resolution
    downstream, suppressing the inference notice -- silently, in the one
    direction that matters."""
    from sbomify_action._generation.generators.cdxgen import CdxgenFsGenerator
    from sbomify_action._generation.protocol import GenerationInput

    (tmp_path / "package.json").write_text('{"name": "thing"}')
    created = tmp_path / "bun.lock"
    created.write_text("{}")

    monkeypatch.setattr("sbomify_action._generation.generators.cdxgen.ensure_runtime", lambda n: Path("/x"))
    monkeypatch.setattr("sbomify_action._generation.generators.cdxgen.resolve_npm_lockfile", lambda d: created)

    def explode(*a, **k):
        raise RuntimeError("the real failure")

    monkeypatch.setattr("sbomify_action._generation.generators.cdxgen.run_command", explode)

    def refuse(self, missing_ok=False):
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "unlink", refuse)

    with caplog.at_level("WARNING"), pytest.raises(RuntimeError, match="the real failure"):
        CdxgenFsGenerator().generate(
            GenerationInput(
                lock_file=str(tmp_path / "package.json"),
                output_file=str(tmp_path / "out.json"),
                output_format="cyclonedx",
            )
        )

    assert "Could not remove bun.lock" in caplog.text
'''

path = pathlib.Path(
    "/home/ubuntu/code/sbomify-action/.claude/worktrees/purrfect-beaming-snowglobe/"
    "tests/test_npm_manifest_resolution.py"
)
path.write_text(path.read_text() + TEST)
print("appended")
