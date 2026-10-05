from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = SOURCE_ROOT / "examples"


def _common_module():
    spec = importlib.util.spec_from_file_location("simple_example_common", EXAMPLES / "_common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_output_copies_without_modifying_source(tmp_path):
    common = _common_module()
    source = tmp_path / "source.xdw"
    output = tmp_path / "nested" / "output.xdw"
    source.write_bytes(b"fixture")
    assert common.prepare_output(source, output) == output.resolve()
    assert source.read_bytes() == b"fixture"
    assert output.read_bytes() == b"fixture"


def test_prepare_output_rejects_same_or_existing_output(tmp_path):
    common = _common_module()
    source = tmp_path / "source.xdw"
    output = tmp_path / "output.xdw"
    source.write_bytes(b"source")
    output.write_bytes(b"existing")
    with pytest.raises(ValueError):
        common.prepare_output(source, source)
    with pytest.raises(FileExistsError):
        common.prepare_output(source, output)
    assert source.read_bytes() == b"source"
    assert output.read_bytes() == b"existing"


def test_prepare_output_requires_xdw_paths(tmp_path):
    common = _common_module()
    source = tmp_path / "source.txt"
    source.write_bytes(b"not xdw")
    with pytest.raises(ValueError):
        common.prepare_output(source, tmp_path / "output.xdw")


@pytest.mark.parametrize(
    "script",
    sorted(path for path in EXAMPLES.glob("[0-9][0-9]_*.py")),
    ids=lambda path: path.name,
)
def test_example_help_is_runnable(script):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
