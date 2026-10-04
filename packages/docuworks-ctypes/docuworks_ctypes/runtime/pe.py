from __future__ import annotations

import ctypes
import hashlib
import os
import struct
from pathlib import Path

from .models import DllFileInfo


IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_MACHINE_I386 = 0x014C


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _pe_headers(data: bytes):
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise ValueError("not a PE file")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("invalid PE signature")
    file_header = pe_offset + 4
    machine, section_count = struct.unpack_from("<HH", data, file_header)
    optional_size = struct.unpack_from("<H", data, file_header + 16)[0]
    optional = file_header + 20
    magic = struct.unpack_from("<H", data, optional)[0]
    data_directory = optional + (112 if magic == 0x20B else 96 if magic == 0x10B else -1)
    if data_directory < optional:
        raise ValueError("unsupported PE optional header")
    sections_offset = optional + optional_size
    sections = []
    for index in range(section_count):
        offset = sections_offset + index * 40
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        sections.append((virtual_address, max(virtual_size, raw_size), raw_offset))
    return machine, data_directory, sections


def pe_machine(path: Path) -> int:
    data = path.read_bytes()
    return _pe_headers(data)[0]


def pe_exports(path: Path) -> frozenset[str]:
    data = path.read_bytes()
    _, data_directory, sections = _pe_headers(data)
    export_rva, export_size = struct.unpack_from("<II", data, data_directory)
    if not export_rva or not export_size:
        return frozenset()

    def rva_offset(rva: int) -> int:
        for virtual_address, size, raw_offset in sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_offset + rva - virtual_address
        raise ValueError(f"RVA 0x{rva:X} is outside PE sections")

    export_offset = rva_offset(export_rva)
    number_of_names = struct.unpack_from("<I", data, export_offset + 24)[0]
    names_rva = struct.unpack_from("<I", data, export_offset + 32)[0]
    names_offset = rva_offset(names_rva)
    result = set()
    for index in range(number_of_names):
        name_rva = struct.unpack_from("<I", data, names_offset + index * 4)[0]
        name_offset = rva_offset(name_rva)
        end = data.find(b"\0", name_offset)
        if end < 0:
            raise ValueError("unterminated PE export name")
        result.add(data[name_offset:end].decode("ascii"))
    return frozenset(result)


class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "dwSignature", "dwStrucVersion", "dwFileVersionMS", "dwFileVersionLS",
        "dwProductVersionMS", "dwProductVersionLS", "dwFileFlagsMask",
        "dwFileFlags", "dwFileOS", "dwFileType", "dwFileSubtype",
        "dwFileDateMS", "dwFileDateLS",
    )]


def _split_version(ms: int, ls: int) -> tuple[int, int, int, int]:
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def file_versions(path: Path) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if os.name != "nt":
        return (), ()
    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    version.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
    version.GetFileVersionInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    version.GetFileVersionInfoW.restype = ctypes.c_int
    version.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    version.VerQueryValueW.restype = ctypes.c_int
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return (), ()
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return (), ()
    value = ctypes.c_void_p()
    length = ctypes.c_uint32()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(length)):
        return (), ()
    info = ctypes.cast(value, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
    return (
        _split_version(info.dwFileVersionMS, info.dwFileVersionLS),
        _split_version(info.dwProductVersionMS, info.dwProductVersionLS),
    )


def inspect_dll(path: Path) -> DllFileInfo:
    file_version, product_version = file_versions(path)
    return DllFileInfo(
        path=path.resolve(),
        machine=pe_machine(path),
        file_version=file_version,
        product_version=product_version,
        sha256=sha256_file(path),
    )
