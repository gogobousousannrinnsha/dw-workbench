from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from compatibility_smoke import prepare_copy
from generate_public_api import public_api_snapshot
from verify_distribution import verify


ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_smoke_copy_contract(tmp_path):
    source = tmp_path / "source.xdw"
    output = tmp_path / "nested" / "output.xdw"
    source.write_bytes(b"fixture")
    resolved_source, resolved_output, before = prepare_copy(source, output)
    assert resolved_source == source.resolve()
    assert resolved_output == output.resolve()
    assert source.read_bytes() == output.read_bytes() == b"fixture"
    assert before
    with pytest.raises(FileExistsError):
        prepare_copy(source, output)
    with pytest.raises(ValueError):
        prepare_copy(source, source)


def test_distribution_audit_compares_python_and_rejects_forbidden_files(tmp_path):
    wheel = tmp_path / "package.whl"
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("docuworks_ctypes/__init__.py", "VERSION = 'x'\n")
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("project/docuworks_ctypes/__init__.py", "VERSION = 'x'\n")
    assert verify(wheel, source)["verified"] is True
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr("project/xdwapi.dll", b"forbidden")
    result = verify(wheel, source)
    assert result["verified"] is False
    assert result["source_errors"]


def test_simple_api_reference_covers_fixed_public_surface():
    reference = (ROOT / "SIMPLE_API_REFERENCE_0.9.0.md").read_text(encoding="utf-8")
    for name in (
        "open_xdw", "SimpleDocument", "SimplePage", "SimpleAnnotation",
        "annotations", "text", "rectangle", "sticky", "ellipse", "line",
        "polygon", "marker", "link", "move_to", "resize", "delete",
    ):
        assert name in reference
    for contract in (
        "1-based", "mm", "pt", "save()", "ClosedHandleError",
        "ReadOnlyDocumentError", "XdwError", "preorder", "identity",
    ):
        assert contract in reference


def test_release_documents_exist_and_version_is_consistent():
    from docuworks_ctypes import __version__

    assert __version__ == "1.0.1"
    for name in (
        "COMPATIBILITY_1.0.md",
        "RELEASE_POLICY.md",
        "CHANGELOG_1.0.0.md",
        "KNOWN_RUNTIME_BEHAVIORS.md",
        "API_STABILITY_1.0.md",
        "MIGRATION_0.9_TO_1.0.md",
        "SIMPLE_API_REFERENCE_1.0.md",
        "PUBLIC_API_1.0.json",
    ):
        assert (ROOT / name).is_file()


def test_public_api_matches_frozen_1_0_snapshot():
    expected = __import__("json").loads(
        (ROOT / "PUBLIC_API_1.0.json").read_text(encoding="utf-8")
    )
    assert public_api_snapshot() == expected
