from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path

import pytest

from docuworks_ctypes import RuntimeResolutionError
from docuworks_ctypes.api import XdwApi
from docuworks_ctypes.runtime.probe_worker import _version_text
from docuworks_ctypes._raw import types as T
from docuworks_ctypes.runtime.models import (
    DllBundle,
    DllFileInfo,
    InstalledDocuWorksInfo,
    ProbeResult,
    StaticValidation,
)
from docuworks_ctypes.runtime.pe import IMAGE_FILE_MACHINE_AMD64
from docuworks_ctypes.runtime.resolver import RuntimeResolver


def _bundle(tmp_path: Path, name: str, source: str) -> DllBundle:
    return DllBundle.from_directory(tmp_path / name, source)


def _static(bundle: DllBundle, version: tuple[int, ...]) -> StaticValidation:
    files = tuple(
        DllFileInfo(path, IMAGE_FILE_MACHINE_AMD64, version, version, path.name)
        for path in (bundle.xdwapi, bundle.xdwapia, bundle.xdwapib)
    )
    return StaticValidation(True, (), files, ())


class _FakeResolver(RuntimeResolver):
    def __init__(self, bundles, statics, probes, installed=(10, 1, 1)):
        super().__init__()
        self._bundles = tuple(bundles)
        self._statics = statics
        self._probes = probes
        self._installed = InstalledDocuWorksInfo(installed, True)

    def installed_docuworks(self):
        return self._installed

    def discover(self, **kwargs):
        if kwargs.get("dll_path") is not None:
            return (self._bundles[0],)
        return self._bundles

    def validate_static(self, bundle):
        return self._statics[bundle.identity]

    def probe(self, bundle, verification_document):
        return self._probes[bundle.identity]


def _success(document=False):
    return ProbeResult(
        attempted=True,
        get_information_ok=True,
        reported_version="10.1.1",
        document_probe_requested=document,
        document_open_ok=True if document else None,
    )


class _InformationRaw:
    def __init__(self):
        self.sizes = []

    def XDW_GetInformationW(self, _index, buffer, size, _reserved):
        self.sizes.append(size)
        data = "10.1.1\0".encode("utf-16-le")
        ctypes.memmove(buffer, data, len(data))
        return len(data)


@pytest.mark.parametrize("reader", [XdwApi._get_version_text, _version_text])
def test_get_information_w_receives_allocated_byte_count(reader):
    raw = _InformationRaw()
    assert reader(raw) == "10.1.1"
    assert raw.sizes == [ctypes.sizeof(T.XDW_WCHAR * 256)]
    assert raw.sizes == [512]


def test_installed_bundle_wins_same_major_even_when_search_path_is_newer(tmp_path):
    installed = _bundle(tmp_path, "installed", "installed")
    search = _bundle(tmp_path, "search", "search_path")
    resolver = _FakeResolver(
        [installed, search],
        {
            installed.identity: _static(installed, (10, 0, 0, 1)),
            search.identity: _static(search, (10, 9, 0, 1)),
        },
        {installed.identity: _success(), search.identity: _success()},
    )
    assert resolver.resolve().selected == installed


def test_docuworks_major_match_beats_installed_source(tmp_path):
    installed = _bundle(tmp_path, "installed", "installed")
    matching = _bundle(tmp_path, "matching", "search_path")
    resolver = _FakeResolver(
        [installed, matching],
        {
            installed.identity: _static(installed, (9, 1, 7, 1)),
            matching.identity: _static(matching, (10, 0, 0, 1)),
        },
        {installed.identity: _success(), matching.identity: _success()},
    )
    assert resolver.resolve().selected == matching


def test_document_probe_failure_makes_candidate_ineligible(tmp_path):
    failed = _bundle(tmp_path, "failed", "installed")
    passed = _bundle(tmp_path, "passed", "search_path")
    resolver = _FakeResolver(
        [failed, passed],
        {
            failed.identity: _static(failed, (10, 1, 0, 1)),
            passed.identity: _static(passed, (10, 0, 0, 1)),
        },
        {
            failed.identity: ProbeResult(
                attempted=True,
                get_information_ok=True,
                document_probe_requested=True,
                document_open_ok=False,
                error_message="XDW_E_NOT_INSTALLED",
            ),
            passed.identity: _success(document=True),
        },
    )
    document = tmp_path / "probe.xdw"
    document.write_bytes(b"probe")
    report = resolver.resolve(verification_document=document)
    assert report.selected == passed
    assert report.candidates[0].rejection_reason == "XDW_E_NOT_INSTALLED"


def test_explicit_candidate_failure_does_not_fallback(tmp_path):
    explicit = _bundle(tmp_path, "explicit", "explicit")
    resolver = _FakeResolver(
        [explicit],
        {explicit.identity: _static(explicit, (10, 0, 0, 1))},
        {
            explicit.identity: ProbeResult(
                attempted=True,
                get_information_ok=False,
                error_message="probe failed",
            )
        },
    )
    with pytest.raises(RuntimeResolutionError) as caught:
        resolver.resolve(dll_path=explicit.xdwapi)
    assert caught.value.report.explicit is True
    assert caught.value.report.selected is None


def test_invalid_probe_json_is_diagnostic(monkeypatch, tmp_path):
    bundle = _bundle(tmp_path, "candidate", "search_path")
    resolver = RuntimeResolver()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "not-json", ""),
    )
    result = resolver.probe(bundle, None)
    assert result.error_type == "InvalidProbeOutput"
    assert result.eligible is False


def test_probe_timeout_is_diagnostic(monkeypatch, tmp_path):
    bundle = _bundle(tmp_path, "candidate", "search_path")
    resolver = RuntimeResolver(probe_timeout=0.01)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 0.01)

    monkeypatch.setattr(subprocess, "run", timeout)
    result = resolver.probe(bundle, None)
    assert result.timed_out is True
    assert result.error_type == "TimeoutExpired"


@pytest.mark.skipif(not Path(r"C:\Windows\System32\xdwapi.dll").is_file(), reason="no installed XDWAPI")
def test_installed_bundle_allows_companion_patch_difference():
    resolver = RuntimeResolver()
    bundle = resolver.discover()[0]
    validation = resolver.validate_static(bundle)
    assert validation.valid is True
    assert validation.missing_exports == ()
    assert validation.files[0].file_version != validation.files[1].file_version
