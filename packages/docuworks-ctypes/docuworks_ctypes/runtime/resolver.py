from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import winreg
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .._raw.functions import FUNCTION_SPECS
from ..errors import (
    BitnessMismatchError,
    DllNotFoundError,
    PlatformNotSupportedError,
    RuntimeResolutionError,
)
from .models import (
    CandidateReport,
    DllBundle,
    InstalledDocuWorksInfo,
    ProbeResult,
    ResolutionReport,
    StaticValidation,
)
from .pe import IMAGE_FILE_MACHINE_AMD64, inspect_dll, pe_exports


class RuntimeResolver:
    def __init__(self, *, probe_timeout: float = 15.0):
        self.probe_timeout = probe_timeout

    @staticmethod
    def installed_docuworks() -> InstalledDocuWorksInfo | None:
        if os.name != "nt":
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\FUJIFILM\MPM3\SystemInfo",
            ) as key:
                version = tuple(
                    int(winreg.QueryValueEx(key, name)[0])
                    for name in ("MajorVersion", "MinorVersion", "PatchVersion")
                )
                try:
                    trial = bool(winreg.QueryValueEx(key, "TrialVersion")[0])
                except OSError:
                    trial = None
                return InstalledDocuWorksInfo(version, trial)
        except OSError:
            return None

    @staticmethod
    def _as_directory(value: str | os.PathLike[str]) -> Path:
        path = Path(value).expanduser()
        return path.parent if path.name.casefold() == "xdwapi.dll" else path

    def discover(
        self,
        *,
        dll_path: str | os.PathLike[str] | None = None,
        search_paths: Iterable[str | os.PathLike[str]] = (),
    ) -> tuple[DllBundle, ...]:
        if os.name != "nt":
            raise PlatformNotSupportedError("XDWAPIはWindowsでのみ利用できます")
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise BitnessMismatchError("docuworks-ctypesは64-bit Pythonのみ対応しています")
        if dll_path is not None:
            path = Path(dll_path).expanduser()
            if not path.is_absolute():
                raise DllNotFoundError(f"dll_pathには絶対パスを指定してください: {path}")
            path = path.resolve()
            if path.name.casefold() != "xdwapi.dll":
                raise DllNotFoundError(f"dll_pathにはxdwapi.dllを指定してください: {path}")
            if not path.is_file():
                raise DllNotFoundError(f"xdwapi.dllが見つかりません: {path}")
            return (DllBundle.from_directory(path.parent, "explicit"),)

        sources: list[tuple[Path, str]] = []
        windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
        sources.append((windows / "System32", "installed"))
        for value in search_paths:
            sources.append((self._as_directory(value), "search_path"))
        for value in os.environ.get("DOCUWORKS_XDWAPI_PATHS", "").split(os.pathsep):
            if value.strip():
                sources.append((self._as_directory(value.strip()), "environment"))

        bundles = []
        seen = set()
        for directory, source in sources:
            bundle = DllBundle.from_directory(directory, source)
            if bundle.identity not in seen:
                seen.add(bundle.identity)
                bundles.append(bundle)
        return tuple(bundles)

    @staticmethod
    def validate_static(bundle: DllBundle) -> StaticValidation:
        errors = []
        required_paths = (bundle.xdwapi, bundle.xdwapia, bundle.xdwapib)
        missing = [str(path) for path in required_paths if not path.is_file()]
        if missing:
            return StaticValidation(False, tuple(f"missing DLL: {path}" for path in missing))
        files = []
        for path in required_paths:
            try:
                info = inspect_dll(path)
                files.append(info)
                if info.machine != IMAGE_FILE_MACHINE_AMD64:
                    errors.append(f"architecture mismatch: {path} machine=0x{info.machine:04X}")
            except Exception as exc:
                errors.append(f"cannot inspect {path}: {exc}")
        majors = {
            info.product_version[0]
            for info in files
            if info.product_version and info.product_version[0]
        }
        if len(majors) > 1:
            errors.append(f"bundle ProductVersion major mismatch: {sorted(majors)}")
        missing_exports: tuple[str, ...] = ()
        if files:
            try:
                exports = pe_exports(bundle.xdwapi)
                missing_exports = tuple(sorted(set(FUNCTION_SPECS) - exports))
                if missing_exports:
                    errors.append(f"missing {len(missing_exports)} required exports")
            except Exception as exc:
                errors.append(f"cannot inspect exports: {exc}")
        return StaticValidation(not errors, tuple(errors), tuple(files), missing_exports)

    def probe(
        self,
        bundle: DllBundle,
        verification_document: Path | None,
    ) -> ProbeResult:
        payload = {
            "directory": str(bundle.directory),
            "source": bundle.source,
            "verification_document": (
                str(verification_document) if verification_document else None
            ),
        }
        command = [
            sys.executable,
            "-m",
            "docuworks_ctypes.runtime.probe_worker",
            json.dumps(payload),
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.probe_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ProbeResult(
                attempted=True,
                document_probe_requested=verification_document is not None,
                error_type="TimeoutExpired",
                error_message=str(exc),
                timed_out=True,
                duration_seconds=time.monotonic() - started,
            )
        duration = time.monotonic() - started
        if completed.returncode != 0:
            return ProbeResult(
                attempted=True,
                document_probe_requested=verification_document is not None,
                error_type="ProbeProcessError",
                error_message=(completed.stderr or completed.stdout).strip(),
                crashed=True,
                duration_seconds=duration,
            )
        try:
            data = json.loads(completed.stdout.strip())
        except json.JSONDecodeError:
            return ProbeResult(
                attempted=True,
                document_probe_requested=verification_document is not None,
                error_type="InvalidProbeOutput",
                error_message=completed.stdout.strip(),
                duration_seconds=duration,
            )
        return ProbeResult(attempted=True, duration_seconds=duration, **data)

    @staticmethod
    def _score(
        report: CandidateReport,
        installed: InstalledDocuWorksInfo | None,
    ) -> tuple[int, ...]:
        main = report.static.main_file
        version = tuple(main.file_version if main else ())
        padded = (version + (0, 0, 0, 0))[:4]
        major = main.product_version[0] if main and main.product_version else 0
        major_match = int(installed is not None and major == installed.version[0])
        installed_source = int(report.bundle.source == "installed")
        return (major_match, installed_source, *padded)

    def inspect(
        self,
        *,
        dll_path: str | os.PathLike[str] | None = None,
        search_paths: Iterable[str | os.PathLike[str]] = (),
        verification_document: str | os.PathLike[str] | None = None,
    ) -> ResolutionReport:
        document = None
        if verification_document is not None:
            document = Path(verification_document).expanduser().resolve()
            if not document.is_file():
                raise FileNotFoundError(document)
        installed = self.installed_docuworks()
        explicit = dll_path is not None
        reports = []
        for bundle in self.discover(dll_path=dll_path, search_paths=search_paths):
            static = self.validate_static(bundle)
            if static.valid:
                probe = self.probe(bundle, document)
            else:
                probe = ProbeResult(
                    attempted=False,
                    document_probe_requested=document is not None,
                )
            report = CandidateReport(bundle, static, probe)
            score = self._score(report, installed)
            rejection = None
            if not static.valid:
                rejection = "; ".join(static.errors)
            elif not probe.eligible:
                rejection = probe.error_message or "runtime probe failed"
            reports.append(replace(report, score=score, rejection_reason=rejection))

        eligible = [item for item in reports if item.static.valid and item.probe.eligible]
        selected = None
        if eligible:
            selected_report = max(eligible, key=lambda item: item.score)
            selected = selected_report.bundle
            reports = [
                item.mark_selected() if item.bundle.identity == selected.identity else item
                for item in reports
            ]
        return ResolutionReport(tuple(reports), selected, installed, document, explicit)

    def resolve(self, **kwargs) -> ResolutionReport:
        report = self.inspect(**kwargs)
        if report.selected is None:
            reasons = " | ".join(
                f"{item.bundle.xdwapi}: {item.rejection_reason or 'not eligible'}"
                for item in report.candidates
            )
            raise RuntimeResolutionError(
                f"利用可能なXDWAPI DLL bundleがありません: {reasons}", report
            )
        return report
