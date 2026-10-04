from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ._raw import constants as C
from ._raw import types as T
from ._raw.api import RawApi
from .document import Document
from .encoding import MultibyteEncodingPolicy, decode_wchar_buffer, wchar_buffer
from .enums import AuthMode, OpenMode
from .errors import UnsupportedVersionError, check_result
from .runtime.models import DllFileInfo, InstalledDocuWorksInfo, ResolutionReport
from .runtime.resolver import RuntimeResolver


MINIMUM_VERSION = (9, 1, 7)


@dataclass(frozen=True)
class RuntimeInfo:
    version_text: str
    version: tuple[int, ...]
    dll_path: Path | None
    python_bits: int
    dll_file_version: tuple[int, ...] = ()
    dll_product_version: tuple[int, ...] = ()
    dll_sha256: str | None = None
    bundle_files: tuple[DllFileInfo, ...] = ()
    runtime_source: str | None = None
    installed_docuworks: InstalledDocuWorksInfo | None = None
    resolution_report: ResolutionReport | None = None


def _parse_version(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", value)
    if not match:
        raise UnsupportedVersionError(f"XDWAPIのバージョンを解釈できません: {value!r}")
    return tuple(int(part) for part in match.group(0).split("."))


def _normalized_version(version: tuple[int, ...], width: int = 3) -> tuple[int, ...]:
    return version[:width] + (0,) * max(0, width - len(version))


class XdwApi:
    def __init__(
        self,
        raw,
        runtime_info: RuntimeInfo,
        multibyte_encoding: MultibyteEncodingPolicy,
    ):
        self.raw = raw
        self.runtime_info = runtime_info
        self.multibyte_encoding = multibyte_encoding

    @classmethod
    def load(
        cls,
        dll_path: str | Path | None = None,
        *,
        multibyte_codepage: int | None = None,
        search_paths: Iterable[str | Path] = (),
        verification_document: str | Path | None = None,
    ) -> "XdwApi":
        resolution = RuntimeResolver().resolve(
            dll_path=dll_path,
            search_paths=search_paths,
            verification_document=verification_document,
        )
        selected = resolution.selected
        assert selected is not None
        raw = RawApi.load_bundle(selected)
        version_text = cls._get_version_text(raw)
        version = _parse_version(version_text)
        if _normalized_version(version) < MINIMUM_VERSION:
            raise UnsupportedVersionError(
                f"XDWAPI 9.1.7以上が必要です。検出版: {version_text}"
            )
        selected_report = resolution.selected_report
        main_file = selected_report.static.main_file if selected_report else None
        return cls(
            raw,
            RuntimeInfo(
                version_text=version_text,
                version=version,
                dll_path=selected.xdwapi,
                python_bits=ctypes.sizeof(ctypes.c_void_p) * 8,
                dll_file_version=main_file.file_version if main_file else (),
                dll_product_version=main_file.product_version if main_file else (),
                dll_sha256=main_file.sha256 if main_file else None,
                bundle_files=selected_report.static.files if selected_report else (),
                runtime_source=selected.source,
                installed_docuworks=resolution.installed_docuworks,
                resolution_report=resolution,
            ),
            MultibyteEncodingPolicy.create(multibyte_codepage),
        )

    @classmethod
    def inspect_runtimes(
        cls,
        *,
        dll_path: str | Path | None = None,
        search_paths: Iterable[str | Path] = (),
        verification_document: str | Path | None = None,
    ) -> ResolutionReport:
        return RuntimeResolver().inspect(
            dll_path=dll_path,
            search_paths=search_paths,
            verification_document=verification_document,
        )

    @classmethod
    def from_raw(
        cls,
        raw,
        *,
        version: tuple[int, ...] = MINIMUM_VERSION,
        multibyte_codepage: int | None = None,
    ) -> "XdwApi":
        return cls(
            raw,
            RuntimeInfo(
                version_text=".".join(str(part) for part in version),
                version=version,
                dll_path=None,
                python_bits=ctypes.sizeof(ctypes.c_void_p) * 8,
            ),
            MultibyteEncodingPolicy.create(multibyte_codepage),
        )

    @staticmethod
    def _get_version_text(raw) -> str:
        buffer = (T.XDW_WCHAR * 256)()
        result = raw.XDW_GetInformationW(
            C.XDW_GI_VERSION, buffer, ctypes.sizeof(buffer), None
        )
        check_result(result, "XDW_GetInformationW(XDW_GI_VERSION)")
        return decode_wchar_buffer(buffer)

    def diagnose(self) -> RuntimeInfo:
        return self.runtime_info

    def open_document(
        self,
        path: str | Path,
        *,
        mode: OpenMode = OpenMode.READONLY,
        auth: AuthMode = AuthMode.NO_DIALOG,
    ) -> Document:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        mode = OpenMode(mode)
        auth = AuthMode(auth)
        if auth not in (AuthMode.NONE, AuthMode.NO_DIALOG):
            raise ValueError("open_document auth supports NONE or NO_DIALOG only")
        open_mode = T.XDW_OPEN_MODE_EX()
        open_mode.nSize = ctypes.sizeof(open_mode)
        open_mode.nOption = int(mode)
        open_mode.nAuthMode = int(auth)
        handle = T.XDW_DOCUMENT_HANDLE()
        path_buffer = wchar_buffer(str(resolved))
        result = self.raw.XDW_OpenDocumentHandleW(
            path_buffer,
            ctypes.byref(handle),
            ctypes.cast(ctypes.byref(open_mode), ctypes.POINTER(T.XDW_OPEN_MODE)),
        )
        check_result(result, "XDW_OpenDocumentHandleW")
        return Document(
            self.raw,
            handle,
            resolved,
            mode,
            self.multibyte_encoding,
        )
