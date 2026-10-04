from __future__ import annotations

import ctypes
import codecs
from dataclasses import dataclass

from ._raw import types as T



def system_ansi_codepage() -> int:
    """Return the Windows ANSI code page used by XDWAPI multibyte strings."""
    get_acp = ctypes.windll.kernel32.GetACP
    get_acp.argtypes = ()
    get_acp.restype = ctypes.c_uint32
    codepage = int(get_acp())
    if codepage <= 0:
        raise RuntimeError(f"GetACP returned an invalid code page: {codepage}")
    return codepage


@dataclass(frozen=True)
class MultibyteEncodingPolicy:
    codepage: int
    codec: str

    @classmethod
    def create(cls, codepage: int | None = None) -> "MultibyteEncodingPolicy":
        resolved = system_ansi_codepage() if codepage is None else int(codepage)
        if resolved <= 0:
            raise ValueError("multibyte code page must be a positive integer")
        requested_codec = f"cp{resolved}"
        try:
            codec = codecs.lookup(requested_codec).name
        except LookupError as exc:
            raise ValueError(
                f"Python does not provide a codec for Windows code page {resolved}"
            ) from exc
        return cls(codepage=resolved, codec=codec)

    def encode(self, value: str) -> bytes:
        validate_text(value)
        return value.encode(self.codec)

    def encoded_length(self, value: str, *, unicode_allowed: bool) -> int:
        try:
            return len(self.encode(value))
        except UnicodeEncodeError:
            if not unicode_allowed:
                raise
            return len(value.encode("utf-16-le"))


def validate_text(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("native text requires str")
    if "\0" in value:
        raise ValueError("native text must not contain an embedded NUL")


def wchar_buffer(value: str):
    validate_text(value)
    encoded = value.encode("utf-16-le") + b"\0\0"
    units = len(encoded) // 2
    array_type = T.XDW_WCHAR * units
    return array_type.from_buffer_copy(encoded)


def decode_wchar_buffer(buffer) -> str:
    raw = ctypes.string_at(ctypes.addressof(buffer), ctypes.sizeof(buffer))
    return raw.decode("utf-16-le").split("\0", 1)[0]
