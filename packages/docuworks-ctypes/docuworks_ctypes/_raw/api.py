from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Any

from ..runtime.loader import load_native_bundle
from ..runtime.models import DllBundle
from .functions import FUNCTION_SPECS

class RawApi:
    """Lazily binds generated XDWAPI signatures to a loaded WinDLL."""

    def __init__(self, dll: Any, dll_path: Path | None = None, *, native_bundle=None):
        self._dll = dll
        self.dll_path = dll_path
        self.native_bundle = native_bundle
        self._functions: dict[str, Any] = {}

    @classmethod
    def load_bundle(cls, bundle: DllBundle) -> "RawApi":
        native = load_native_bundle(bundle)
        return cls(native.main, bundle.xdwapi, native_bundle=native)

    @classmethod
    def load(cls, dll_path: str | Path | None = None) -> "RawApi":
        from ..runtime.resolver import RuntimeResolver

        resolution = RuntimeResolver().resolve(dll_path=dll_path)
        assert resolution.selected is not None
        return cls.load_bundle(resolution.selected)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._functions:
            return self._functions[name]
        try:
            result_type, argument_types = FUNCTION_SPECS[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
        try:
            function = getattr(self._dll, name)
        except AttributeError as exc:
            raise AttributeError(f"xdwapi.dllに{name}がありません") from exc
        function.restype = result_type
        function.argtypes = list(argument_types)
        self._functions[name] = function
        return function

    def has_function(self, name: str) -> bool:
        if name not in FUNCTION_SPECS:
            return False
        try:
            getattr(self, name)
        except AttributeError:
            return False
        return True
