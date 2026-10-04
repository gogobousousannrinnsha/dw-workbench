from __future__ import annotations

import ctypes

from ._raw.constants import ERROR_NAMES


class DocuWorksError(Exception):
    """Base exception for docuworks-ctypes."""


class PlatformNotSupportedError(DocuWorksError):
    pass


class DllNotFoundError(DocuWorksError):
    pass


class BitnessMismatchError(DocuWorksError):
    pass


class UnsupportedVersionError(DocuWorksError):
    pass


class ReadOnlyDocumentError(DocuWorksError):
    pass


class ClosedHandleError(DocuWorksError):
    pass


class AnnotationRefreshError(DocuWorksError):
    pass


class RuntimeResolutionError(DocuWorksError):
    def __init__(self, message: str, report=None):
        self.report = report
        super().__init__(message)


class RuntimeBundleConflictError(DocuWorksError):
    pass


class XdwError(DocuWorksError):
    def __init__(self, result: int, operation: str):
        self.result = ctypes.c_int32(result).value
        self.unsigned_result = ctypes.c_uint32(result).value
        self.operation = operation
        self.symbol = ERROR_NAMES.get(self.result)
        detail = f"{operation}に失敗しました: 0x{self.unsigned_result:08X}"
        if self.symbol:
            detail += f" ({self.symbol})"
        super().__init__(detail)


def check_result(result: int, operation: str) -> int:
    signed = ctypes.c_int32(result).value
    if signed < 0:
        raise XdwError(signed, operation)
    return signed
