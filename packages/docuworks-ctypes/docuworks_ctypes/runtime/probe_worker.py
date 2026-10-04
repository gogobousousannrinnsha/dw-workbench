from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

from .._raw import constants as C
from .._raw import types as T
from .._raw.api import RawApi
from ..encoding import decode_wchar_buffer, wchar_buffer
from ..errors import XdwError, check_result
from .models import DllBundle


def _version_text(raw) -> str:
    buffer = (T.XDW_WCHAR * 256)()
    result = raw.XDW_GetInformationW(
        C.XDW_GI_VERSION, buffer, ctypes.sizeof(buffer), None
    )
    check_result(result, "XDW_GetInformationW(XDW_GI_VERSION)")
    return decode_wchar_buffer(buffer)


def _probe_document(raw, path: Path) -> int:
    mode = T.XDW_OPEN_MODE_EX()
    mode.nSize = ctypes.sizeof(mode)
    mode.nOption = C.XDW_OPEN_READONLY
    mode.nAuthMode = C.XDW_AUTH_NODIALOGUE
    handle = T.XDW_DOCUMENT_HANDLE()
    result = raw.XDW_OpenDocumentHandleW(
        wchar_buffer(str(path)),
        ctypes.byref(handle),
        ctypes.cast(ctypes.byref(mode), ctypes.POINTER(T.XDW_OPEN_MODE)),
    )
    check_result(result, "XDW_OpenDocumentHandleW(runtime probe)")
    try:
        info = T.XDW_DOCUMENT_INFO()
        info.nSize = ctypes.sizeof(info)
        check_result(
            raw.XDW_GetDocumentInformation(handle, ctypes.byref(info)),
            "XDW_GetDocumentInformation(runtime probe)",
        )
        return int(info.nPages)
    finally:
        check_result(
            raw.XDW_CloseDocumentHandle(handle, None),
            "XDW_CloseDocumentHandle(runtime probe)",
        )


def main() -> int:
    payload = json.loads(sys.argv[1])
    directory = Path(payload["directory"])
    bundle = DllBundle.from_directory(directory, payload["source"])
    result = {
        "get_information_ok": False,
        "reported_version": None,
        "document_probe_requested": bool(payload.get("verification_document")),
        "document_open_ok": None,
        "document_page_count": None,
        "error_type": None,
        "error_message": None,
        "xdw_error_code": None,
    }
    try:
        raw = RawApi.load_bundle(bundle)
        result["reported_version"] = _version_text(raw)
        result["get_information_ok"] = True
        verification_document = payload.get("verification_document")
        if verification_document:
            result["document_page_count"] = _probe_document(
                raw, Path(verification_document)
            )
            result["document_open_ok"] = True
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)
        if isinstance(exc, XdwError):
            result["xdw_error_code"] = exc.unsigned_result
        if result["document_probe_requested"] and result["get_information_ok"]:
            result["document_open_ok"] = False
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
