from __future__ import annotations

import ctypes
import os
import platform
import sys
import winreg
from datetime import datetime
from pathlib import Path

import pytest

from docuworks_ctypes import XdwApi

from tests.integration.support import EvidenceWriter, sha256_file


def _docuworks_registry_info() -> dict[str, int] | None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\FUJIFILM\MPM3\SystemInfo"
        ) as key:
            return {
                name: int(winreg.QueryValueEx(key, name)[0])
                for name in (
                    "MajorVersion",
                    "MinorVersion",
                    "PatchVersion",
                    "TrialVersion",
                )
            }
    except OSError:
        return None


def _source_from_env(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set; this is not an integration success")
    source = Path(value).expanduser().resolve()
    if not source.is_file():
        pytest.fail(f"{name} does not exist: {source}")
    return source


@pytest.fixture(scope="session")
def artifact_root() -> Path:
    configured = os.environ.get("DOCUWORKS_ARTIFACT_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = (Path.cwd() / "integration-artifacts" / stamp).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="session")
def evidence_writer(artifact_root: Path) -> EvidenceWriter:
    return EvidenceWriter(artifact_root)


@pytest.fixture(scope="session")
def api(evidence_writer: EvidenceWriter):
    if not os.environ.get("DOCUWORKS_TEST_XDW") and not os.environ.get(
        "DOCUWORKS_DATE_STAMP_XDW"
    ):
        pytest.skip(
            "both integration fixtures are unset; this is not an integration success"
        )
    dll = os.environ.get("DOCUWORKS_DLL")
    codepage = os.environ.get("DOCUWORKS_CODEPAGE")
    try:
        loaded = XdwApi.load(
            dll_path=dll or None,
            multibyte_codepage=int(codepage) if codepage else None,
            verification_document=os.environ.get("DOCUWORKS_TEST_XDW"),
        )
    except Exception as exc:
        evidence_writer.write_json(
            "environment.json",
            {
                "os": platform.platform(),
                "python": sys.version,
                "python_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
                "windows_acp": ctypes.windll.kernel32.GetACP(),
                "docuworks_registry": _docuworks_registry_info(),
                "requested_dll": dll,
                "load_error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        raise
    runtime = loaded.diagnose()
    dll_path = runtime.dll_path or (Path(dll).resolve() if dll else None)
    evidence_writer.write_json(
        "environment.json",
        {
            "os": platform.platform(),
            "python": sys.version,
            "python_bits": runtime.python_bits,
            "windows_acp": ctypes.windll.kernel32.GetACP(),
            "docuworks_registry": _docuworks_registry_info(),
            "selected_codepage": loaded.multibyte_encoding.codepage,
            "selected_codec": loaded.multibyte_encoding.codec,
            "xdwapi_version": runtime.version_text,
            "dll_path": dll_path,
            "dll_file_version": runtime.dll_file_version,
            "dll_product_version": runtime.dll_product_version,
            "dll_sha256": runtime.dll_sha256,
            "runtime_source": runtime.runtime_source,
            "bundle_files": runtime.bundle_files,
            "runtime_resolution": (
                runtime.resolution_report.to_dict()
                if runtime.resolution_report is not None
                else None
            ),
        },
    )
    return loaded


@pytest.fixture(scope="session")
def blank_fixture_source(evidence_writer: EvidenceWriter):
    source = _source_from_env("DOCUWORKS_TEST_XDW")
    before = sha256_file(source)
    evidence_writer.record("blank_fixture", "source_before", path=source, sha256=before)
    yield source
    after = sha256_file(source)
    evidence_writer.record("blank_fixture", "source_after", path=source, sha256=after)
    if after != before:
        pytest.fail("DOCUWORKS_TEST_XDW was modified; fixture immutability violated")


@pytest.fixture(scope="session")
def date_stamp_fixture_source(evidence_writer: EvidenceWriter):
    source = _source_from_env("DOCUWORKS_DATE_STAMP_XDW")
    before = sha256_file(source)
    evidence_writer.record("date_stamp_fixture", "source_before", path=source, sha256=before)
    yield source
    after = sha256_file(source)
    evidence_writer.record("date_stamp_fixture", "source_after", path=source, sha256=after)
    if after != before:
        pytest.fail("DOCUWORKS_DATE_STAMP_XDW was modified; fixture immutability violated")


@pytest.fixture
def xdw_copy(request, blank_fixture_source: Path, evidence_writer: EvidenceWriter) -> Path:
    return evidence_writer.copy_fixture(blank_fixture_source, request.node.name)


@pytest.fixture
def date_xdw_copy(
    request, date_stamp_fixture_source: Path, evidence_writer: EvidenceWriter
) -> Path:
    return evidence_writer.copy_fixture(date_stamp_fixture_source, request.node.name)


@pytest.fixture
def evidence(request, evidence_writer: EvidenceWriter, record_property):
    def record(stage: str, **details):
        item = evidence_writer.record(request.node.name, stage, **details)
        record_property(stage, str(item))
        return item

    return record
