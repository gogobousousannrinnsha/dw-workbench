from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from ..errors import PlatformNotSupportedError, RuntimeBundleConflictError
from .models import DllBundle


_LOAD_LOCK = RLock()
_LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008


@dataclass
class LoadedNativeBundle:
    main: Any
    dependencies: tuple[Any, ...]
    directory_handle: Any | None


def _loaded_module_path(name: str) -> Path | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleFileNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    kernel32.GetModuleFileNameW.restype = ctypes.c_uint32
    handle = kernel32.GetModuleHandleW(name)
    if not handle:
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    if not kernel32.GetModuleFileNameW(handle, buffer, len(buffer)):
        return None
    return Path(buffer.value).resolve()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def load_native_bundle(bundle: DllBundle, *, reject_conflicts: bool = True) -> LoadedNativeBundle:
    if os.name != "nt":
        raise PlatformNotSupportedError("XDWAPIはWindowsでのみ利用できます")
    expected = {
        "xdwapi.dll": bundle.xdwapi,
        "xdwapia.dll": bundle.xdwapia,
        "xdwapib.dll": bundle.xdwapib,
    }
    with _LOAD_LOCK:
        if reject_conflicts:
            for name, path in expected.items():
                loaded = _loaded_module_path(name)
                if loaded is not None and not _same_path(loaded, path):
                    raise RuntimeBundleConflictError(
                        f"{name}は別bundleから既にロードされています: {loaded}; requested: {path}"
                    )

        directory_handle = os.add_dll_directory(str(bundle.directory))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
        kernel32.GetDllDirectoryW.restype = ctypes.c_uint32
        kernel32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        kernel32.SetDllDirectoryW.restype = ctypes.c_int
        size = kernel32.GetDllDirectoryW(0, None)
        previous_buffer = ctypes.create_unicode_buffer(size + 1)
        previous = ""
        if size:
            kernel32.GetDllDirectoryW(len(previous_buffer), previous_buffer)
            previous = previous_buffer.value
        if not kernel32.SetDllDirectoryW(str(bundle.directory)):
            directory_handle.close()
            raise OSError(ctypes.get_last_error(), "SetDllDirectoryW failed")
        try:
            main = ctypes.WinDLL(
                str(bundle.xdwapi), winmode=_LOAD_WITH_ALTERED_SEARCH_PATH
            )
        finally:
            kernel32.SetDllDirectoryW(previous or None)
        return LoadedNativeBundle(main, (), directory_handle)
