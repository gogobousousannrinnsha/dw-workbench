from __future__ import annotations

import ctypes
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import IntEnum
from typing import Any, Literal, Mapping

from ._raw import constants as C
from ._raw import types as T
from .encoding import MultibyteEncodingPolicy, decode_wchar_buffer, wchar_buffer
from .errors import check_result
from .geometry import RawPoint

StorageKind = Literal["int32", "string", "point_array"]
PythonKind = Literal["int", "float", "str", "bool", "color", "points"]


@dataclass(frozen=True)
class AttributeCondition:
    attribute_name: str
    equals: int


@dataclass(frozen=True)
class StandardAttributeSpec:
    name: str
    annotation_type: int
    storage_kind: StorageKind
    python_kind: PythonKind
    readable: bool = True
    writable: bool = True
    unit: str | None = None
    python_unit: str | None = None
    raw_per_python_unit: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    allowed_values: frozenset[int | str] | None = None
    unicode_allowed: bool = False
    conditions: tuple[AttributeCondition, ...] = ()
    max_bytes: int | None = None
    max_chars: int | None = None
    max_lines: int | None = None
    max_bytes_per_line: int | None = None
    allowed_characters: frozenset[str] | None = None


def _ints(*values: int) -> frozenset[int]:
    return frozenset(values)


_STANDARD_COLORS = frozenset({
    C.XDW_COLOR_BLACK, C.XDW_COLOR_MAROON, C.XDW_COLOR_GREEN,
    C.XDW_COLOR_OLIVE, C.XDW_COLOR_NAVY, C.XDW_COLOR_PURPLE,
    C.XDW_COLOR_TEAL, C.XDW_COLOR_GRAY, C.XDW_COLOR_SILVER,
    C.XDW_COLOR_RED, C.XDW_COLOR_LIME, C.XDW_COLOR_YELLOW,
    C.XDW_COLOR_BLUE, C.XDW_COLOR_FUCHIA, C.XDW_COLOR_AQUA,
    C.XDW_COLOR_WHITE,
})
_BACKGROUND_COLORS = _STANDARD_COLORS | {C.XDW_COLOR_NONE}
_STICKY_COLORS = frozenset({
    C.XDW_COLOR_WHITE, C.XDW_COLOR_FUSEN_RED, C.XDW_COLOR_FUSEN_BLUE,
    C.XDW_COLOR_FUSEN_YELLOW, C.XDW_COLOR_FUSEN_LIME,
})


def _condition(name: str, value: int) -> tuple[AttributeCondition, ...]:
    return (AttributeCondition(name, value),)


def _build_standard_registry() -> dict[tuple[int, str], StandardAttributeSpec]:
    registry: dict[tuple[int, str], StandardAttributeSpec] = {}

    def add(annotation_type: int, name: str, storage_kind: StorageKind,
            python_kind: PythonKind, **kwargs: Any) -> None:
        spec = StandardAttributeSpec(name, annotation_type, storage_kind,
                                     python_kind, **kwargs)
        registry[(annotation_type, name)] = spec

    text = C.XDW_AID_TEXT
    add(text, C.XDW_ATN_Text, "string", "str", unicode_allowed=True)
    add(text, C.XDW_ATN_FontName, "string", "str")
    add(text, C.XDW_ATN_FontStyle, "int32", "int", allowed_values=frozenset(range(16)))
    add(text, C.XDW_ATN_FontSize, "int32", "float", unit="1/10 pt",
        python_unit="pt", raw_per_python_unit=10)
    add(text, C.XDW_ATN_ForeColor, "int32", "color", allowed_values=_STANDARD_COLORS)
    add(text, C.XDW_ATN_FontPitchAndFamily, "int32", "int")
    add(text, C.XDW_ATN_FontCharSet, "int32", "int")
    add(text, C.XDW_ATN_BackColor, "int32", "color", allowed_values=_BACKGROUND_COLORS)
    add(text, C.XDW_ATN_WordWrap, "int32", "bool", allowed_values=_ints(0, 1))
    add(text, C.XDW_ATN_TextDirection, "int32", "bool", allowed_values=_ints(0, 1))
    add(text, C.XDW_ATN_TextOrientation, "int32", "float", unit="degree",
        python_unit="degree", raw_per_python_unit=1, minimum=0, maximum=359)
    add(text, C.XDW_ATN_LineSpace, "int32", "float", unit="1/100 line",
        python_unit="line", raw_per_python_unit=100, minimum=100, maximum=1000)
    add(text, C.XDW_ATN_TextSpacing, "int32", "float", unit="1/10 pt",
        python_unit="pt", raw_per_python_unit=10)
    for margin in (C.XDW_ATN_TextTopMargin, C.XDW_ATN_TextLeftMargin,
                   C.XDW_ATN_TextBottomMargin, C.XDW_ATN_TextRightMargin):
        add(text, margin, "int32", "float", unit="1/100 mm",
            python_unit="mm", raw_per_python_unit=100, minimum=0, maximum=20000)
    add(text, C.XDW_ATN_TextAutoResizeHeight, "int32", "bool",
        allowed_values=_ints(0, 1), conditions=_condition(C.XDW_ATN_WordWrap, 1))

    link = C.XDW_AID_LINK
    # Defensive product limit; not a vendor guarantee for every encoding.
    add(link, C.XDW_ATN_Caption, "string", "str", unicode_allowed=True, max_bytes=255)
    for name in (C.XDW_ATN_ShowIcon, C.XDW_ATN_Invisible, C.XDW_ATN_AutoResize,
                 C.XDW_ATN_Tooltip):
        add(link, name, "int32", "bool", allowed_values=_ints(0, 1))
    add(link, C.XDW_ATN_Tooltip_String, "string", "str", unicode_allowed=True, max_bytes=255)
    add(link, C.XDW_ATN_LinkType, "int32", "int", allowed_values=_ints(0, 1, 2, 3, 4))
    add(link, C.XDW_ATN_Url, "string", "str", unicode_allowed=True, max_bytes=255,
        conditions=_condition(C.XDW_ATN_LinkType, C.XDW_LT_LINK_TO_URL))
    add(link, C.XDW_ATN_XdwPath, "string", "str", unicode_allowed=True, max_bytes=255,
        conditions=_condition(C.XDW_ATN_LinkType, C.XDW_LT_LINK_TO_XDW))
    add(link, C.XDW_ATN_XdwPath_Relative, "int32", "bool", allowed_values=_ints(0, 1))
    add(link, C.XDW_ATN_XdwLink, "int32", "bool", allowed_values=_ints(0, 1))
    add(link, C.XDW_ATN_PageFrom, "int32", "int",
        allowed_values=_ints(C.XDW_PF_XDW, C.XDW_PF_XBD, C.XDW_PF_XDW_IN_XBD))
    add(link, C.XDW_ATN_XdwNameInXbd, "string", "str", unicode_allowed=True,
        conditions=_condition(C.XDW_ATN_PageFrom, C.XDW_PF_XDW_IN_XBD))
    add(link, C.XDW_ATN_XdwPage, "int32", "int")
    add(link, C.XDW_ATN_LinkAtn_Title, "string", "str", unicode_allowed=True, max_bytes=255)
    add(link, C.XDW_ATN_OtherFilePath, "string", "str", unicode_allowed=True, max_bytes=255,
        conditions=_condition(C.XDW_ATN_LinkType, C.XDW_LT_LINK_TO_OTHERFILE))
    add(link, C.XDW_ATN_OtherFilePath_Relative, "int32", "bool", allowed_values=_ints(0, 1))
    add(link, C.XDW_ATN_MailAddress, "string", "str", unicode_allowed=True, max_bytes=255,
        conditions=_condition(C.XDW_ATN_LinkType, C.XDW_LT_LINK_TO_MAILADDR))
    add(link, C.XDW_ATN_FontName, "string", "str")
    add(link, C.XDW_ATN_FontStyle, "int32", "int", allowed_values=frozenset(range(16)))
    add(link, C.XDW_ATN_FontSize, "int32", "float", unit="1/10 pt",
        python_unit="pt", raw_per_python_unit=10)
    add(link, C.XDW_ATN_ForeColor, "int32", "color", allowed_values=_STANDARD_COLORS)
    add(link, C.XDW_ATN_FontPitchAndFamily, "int32", "int")
    add(link, C.XDW_ATN_FontCharSet, "int32", "int")

    sticky = C.XDW_AID_FUSEN
    add(sticky, C.XDW_ATN_FillColor, "int32", "color", allowed_values=_STICKY_COLORS)
    add(sticky, C.XDW_ATN_AutoResize, "int32", "bool", allowed_values=_ints(0, 1))

    straight = C.XDW_AID_STRAIGHTLINE
    add(straight, C.XDW_ATN_BorderWidth, "int32", "int", unit="pt")
    add(straight, C.XDW_ATN_BorderColor, "int32", "color", allowed_values=_STANDARD_COLORS)
    add(straight, C.XDW_ATN_BorderTransparent, "int32", "bool", allowed_values=_ints(0, 1))
    add(straight, C.XDW_ATN_ArrowheadType, "int32", "int", allowed_values=_ints(0, 1, 2, 3))
    add(straight, C.XDW_ATN_ArrowheadStyle, "int32", "int", allowed_values=_ints(0, 1, 2))
    add(straight, C.XDW_ATN_Points, "point_array", "points", writable=False)
    add(straight, C.XDW_ATN_BorderType, "int32", "int", allowed_values=_ints(0, 1, 2, 3, 4))

    for shape in (C.XDW_AID_RECTANGLE, C.XDW_AID_ARC):
        add(shape, C.XDW_ATN_BorderStyle, "int32", "bool", allowed_values=_ints(0, 1))
        add(shape, C.XDW_ATN_BorderWidth, "int32", "int", unit="pt")
        add(shape, C.XDW_ATN_BorderColor, "int32", "color", allowed_values=_STANDARD_COLORS)
        add(shape, C.XDW_ATN_FillStyle, "int32", "bool", allowed_values=_ints(0, 1))
        add(shape, C.XDW_ATN_FillColor, "int32", "color", allowed_values=_STANDARD_COLORS)
        add(shape, C.XDW_ATN_FillTransparent, "int32", "bool", allowed_values=_ints(0, 1))

    stamp = C.XDW_AID_STAMP
    add(stamp, C.XDW_ATN_BorderColor, "int32", "color", allowed_values=_STANDARD_COLORS)
    for field in (C.XDW_ATN_TopField, C.XDW_ATN_BottomField):
        add(stamp, field, "string", "str", unicode_allowed=True,
            max_lines=2, max_bytes_per_line=12)
    add(stamp, C.XDW_ATN_DateStyle, "int32", "int",
        allowed_values=_ints(C.XDW_STAMP_AUTO, C.XDW_STAMP_MANUAL))
    add(stamp, C.XDW_ATN_BasisYearStyle, "int32", "int",
        allowed_values=_ints(C.XDW_STAMP_NO_BASISYEAR, C.XDW_STAMP_BASISYEAR),
        conditions=_condition(C.XDW_ATN_DateStyle, C.XDW_STAMP_AUTO))
    add(stamp, C.XDW_ATN_BasisYear, "int32", "int", minimum=1, maximum=9999,
        conditions=_condition(C.XDW_ATN_BasisYearStyle, C.XDW_STAMP_BASISYEAR))
    add(stamp, C.XDW_ATN_DateField_FirstChar, "string", "str", max_chars=1)
    manual = _condition(C.XDW_ATN_DateStyle, C.XDW_STAMP_MANUAL)
    date_field_chars = frozenset(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-"
    )
    for field in (C.XDW_ATN_YearField, C.XDW_ATN_MonthField, C.XDW_ATN_DayField):
        add(stamp, field, "string", "str", max_chars=4,
            allowed_characters=date_field_chars, conditions=manual)
    add(stamp, C.XDW_ATN_DateFormat, "string", "str",
        allowed_values=frozenset({"yy.mm.dd", "yy.m.d", "dd.mmm.yy", "dd.mmm.yyyy"}),
        conditions=_condition(C.XDW_ATN_DateStyle, C.XDW_STAMP_AUTO))
    add(stamp, C.XDW_ATN_DateOrder, "int32", "int",
        allowed_values=_ints(C.XDW_STAMP_DATE_YMD, C.XDW_STAMP_DATE_DMY), conditions=manual)

    marker = C.XDW_AID_MARKER
    add(marker, C.XDW_ATN_BorderColor, "int32", "color", allowed_values=_STANDARD_COLORS)
    add(marker, C.XDW_ATN_BorderWidth, "int32", "int", unit="pt")
    add(marker, C.XDW_ATN_BorderTransparent, "int32", "bool", allowed_values=_ints(0, 1))
    add(marker, C.XDW_ATN_Points, "point_array", "points", writable=False)

    polygon = C.XDW_AID_POLYGON
    add(polygon, C.XDW_ATN_BorderStyle, "int32", "bool", allowed_values=_ints(0, 1))
    add(polygon, C.XDW_ATN_BorderWidth, "int32", "int", unit="pt")
    add(polygon, C.XDW_ATN_BorderColor, "int32", "color", allowed_values=_STANDARD_COLORS)
    add(polygon, C.XDW_ATN_Close, "int32", "bool", allowed_values=_ints(0, 1))
    closed = _condition(C.XDW_ATN_Close, 1)
    add(polygon, C.XDW_ATN_FillStyle, "int32", "bool", allowed_values=_ints(0, 1), conditions=closed)
    add(polygon, C.XDW_ATN_FillColor, "int32", "color", allowed_values=_STANDARD_COLORS, conditions=closed)
    add(polygon, C.XDW_ATN_FillTransparent, "int32", "bool", allowed_values=_ints(0, 1), conditions=closed)
    add(polygon, C.XDW_ATN_ArrowheadType, "int32", "int", allowed_values=_ints(0, 1, 2, 3))
    add(polygon, C.XDW_ATN_ArrowheadStyle, "int32", "int", allowed_values=_ints(0, 1, 2))
    add(polygon, C.XDW_ATN_Points, "point_array", "points", writable=False)
    return registry


STANDARD_ATTRIBUTE_REGISTRY = _build_standard_registry()


def standard_attribute_spec(annotation_type: int, name: str) -> StandardAttributeSpec:
    try:
        return STANDARD_ATTRIBUTE_REGISTRY[(int(annotation_type), name)]
    except KeyError as exc:
        raise ValueError(
            f"standard attribute {name!r} is not defined for annotation type {int(annotation_type)}"
        ) from exc


def _encoding_policy(
    policy: MultibyteEncodingPolicy | None,
) -> MultibyteEncodingPolicy:
    return policy or MultibyteEncodingPolicy.create()


def _python_to_raw(spec: StandardAttributeSpec, value: Any):
    if spec.python_kind == "bool":
        if not isinstance(value, bool):
            raise TypeError(f"{spec.name} requires bool")
        return int(value)
    if spec.raw_per_python_unit is None:
        return value
    if not isinstance(value, (int, float, Decimal)) or isinstance(value, bool):
        raise TypeError(f"{spec.name} requires a numeric value in {spec.python_unit}")
    if not Decimal(str(value)).is_finite():
        raise ValueError(f"{spec.name} requires a finite value")
    scaled = Decimal(str(value)) * Decimal(spec.raw_per_python_unit)
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _raw_to_python(spec: StandardAttributeSpec, value: Any):
    if spec.python_kind == "bool":
        return bool(value)
    if spec.storage_kind == "point_array":
        absolute: list[RawPoint] = []
        for point in value:
            if not absolute:
                absolute.append(point)
            else:
                first = absolute[0]
                absolute.append(RawPoint(first.x + point.x, first.y + point.y))
        return tuple(point.to_mm() for point in absolute)
    if spec.raw_per_python_unit is None or spec.storage_kind != "int32":
        return value
    return float(Decimal(value) / Decimal(spec.raw_per_python_unit))


def validate_standard_raw_value(
    spec: StandardAttributeSpec,
    value: Any,
    *,
    context: Mapping[str, Any] | None = None,
    encoding_policy: MultibyteEncodingPolicy | None = None,
) -> None:
    if not spec.writable:
        raise ValueError(f"standard attribute {spec.name!r} is read-only")
    policy = _encoding_policy(encoding_policy)
    if spec.storage_kind == "string":
        if not isinstance(value, str):
            raise TypeError(f"{spec.name} requires str")
        if spec.max_chars is not None and len(value) > spec.max_chars:
            raise ValueError(f"{spec.name} is limited to {spec.max_chars} characters")
        if spec.allowed_characters is not None and not set(value) <= spec.allowed_characters:
            raise ValueError(f"{spec.name} contains a character not allowed by XDWAPI 3.1")
        encoded_length = policy.encoded_length(
            value, unicode_allowed=spec.unicode_allowed
        )
        if spec.max_bytes is not None and encoded_length > spec.max_bytes:
            raise ValueError(f"{spec.name} is limited to {spec.max_bytes} bytes")
        lines = value.splitlines() or [""]
        if spec.max_lines is not None and len(lines) > spec.max_lines:
            raise ValueError(f"{spec.name} is limited to {spec.max_lines} lines")
        if spec.max_bytes_per_line is not None and any(
            policy.encoded_length(line, unicode_allowed=spec.unicode_allowed)
            > spec.max_bytes_per_line
            for line in lines
        ):
            raise ValueError(f"each line of {spec.name} is limited to {spec.max_bytes_per_line} bytes")
    elif spec.storage_kind == "int32" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        raise TypeError(f"{spec.name} requires int")
    if spec.storage_kind == "int32" and not -(2**31) <= value < 2**31:
        raise ValueError(f"{spec.name} requires a signed 32-bit value")
    comparable = value
    if spec.minimum is not None and comparable < spec.minimum:
        raise ValueError(f"{spec.name} must be >= {spec.minimum}")
    if spec.maximum is not None and comparable > spec.maximum:
        raise ValueError(f"{spec.name} must be <= {spec.maximum}")
    if spec.allowed_values is not None and comparable not in spec.allowed_values:
        raise ValueError(f"{spec.name} is not one of the values allowed by XDWAPI 3.1")
    if context is not None:
        for condition in spec.conditions:
            actual = context.get(condition.attribute_name)
            if (
                not isinstance(actual, int)
                or isinstance(actual, bool)
                or actual != condition.equals
            ):
                raise ValueError(
                    f"{spec.name} is valid only when {condition.attribute_name} == {condition.equals}"
                )


def validate_standard_value(
    spec: StandardAttributeSpec,
    value: Any,
    *,
    context: Mapping[str, Any] | None = None,
    encoding_policy: MultibyteEncodingPolicy | None = None,
) -> None:
    validate_standard_raw_value(
        spec,
        _python_to_raw(spec, value),
        context=context,
        encoding_policy=encoding_policy,
    )


def _standard_name(name: str) -> bytes:
    try:
        return name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("standard attribute names must be ASCII") from exc


def set_standard_attribute_raw(
    raw,
    document_handle,
    annotation_handle,
    spec: StandardAttributeSpec,
    value: Any,
    *,
    encoding_policy: MultibyteEncodingPolicy | None = None,
) -> None:
    policy = _encoding_policy(encoding_policy)
    validate_standard_raw_value(spec, value, encoding_policy=policy)
    name = _standard_name(spec.name)
    if spec.storage_kind == "point_array":
        raise ValueError(f"standard attribute {spec.name!r} is read-only")
    if spec.storage_kind == "int32":
        storage = ctypes.c_int32(int(value))
        result = raw.XDW_SetAnnotationAttributeW(
            document_handle, annotation_handle, name, C.XDW_ATYPE_INT,
            ctypes.cast(ctypes.byref(storage), ctypes.c_void_p),
            C.XDW_TEXT_UNKNOWN, 0, 0, None)
        check_result(result, f"XDW_SetAnnotationAttributeW({spec.name})")
    elif spec.unicode_allowed:
        storage = wchar_buffer(value)
        result = raw.XDW_SetAnnotationAttributeW(
            document_handle, annotation_handle, name, C.XDW_ATYPE_STRING,
            ctypes.cast(storage, ctypes.c_void_p),
            C.XDW_TEXT_UNICODE_IFNECESSARY, policy.codepage, 0, None)
        check_result(result, f"XDW_SetAnnotationAttributeW({spec.name})")
    else:
        storage = ctypes.create_string_buffer(policy.encode(value) + b"\0")
        result = raw.XDW_SetAnnotationAttribute(
            document_handle, annotation_handle, name, C.XDW_ATYPE_STRING,
            ctypes.cast(storage, ctypes.c_char_p), 0, None)
        check_result(result, f"XDW_SetAnnotationAttribute({spec.name})")


def set_standard_attribute(
    raw,
    document_handle,
    annotation_handle,
    spec: StandardAttributeSpec,
    value: Any,
    *,
    encoding_policy: MultibyteEncodingPolicy | None = None,
) -> None:
    set_standard_attribute_raw(
        raw,
        document_handle,
        annotation_handle,
        spec,
        _python_to_raw(spec, value),
        encoding_policy=encoding_policy,
    )


def get_standard_attribute_raw(
    raw,
    annotation_handle,
    spec: StandardAttributeSpec,
    *,
    encoding_policy: MultibyteEncodingPolicy | None = None,
):
    if not spec.readable:
        raise ValueError(f"standard attribute {spec.name!r} is not readable")
    policy = _encoding_policy(encoding_policy)
    name = _standard_name(spec.name)
    text_type = ctypes.c_int32(C.XDW_TEXT_UNKNOWN)
    codepage = policy.codepage if spec.storage_kind == "string" else 0
    required = raw.XDW_GetAnnotationAttributeW(
        annotation_handle, name, None, 0, ctypes.byref(text_type), codepage, None)
    required = check_result(required, f"XDW_GetAnnotationAttributeW({spec.name}, size)")
    if required == 0:
        return "" if spec.storage_kind == "string" else (() if spec.storage_kind == "point_array" else 0)
    storage = (ctypes.c_ubyte * required)()
    result = raw.XDW_GetAnnotationAttributeW(
        annotation_handle, name, ctypes.cast(storage, ctypes.c_void_p), required,
        ctypes.byref(text_type), codepage, None)
    check_result(result, f"XDW_GetAnnotationAttributeW({spec.name})")
    data = bytes(storage)
    if spec.storage_kind == "string":
        return data[:len(data) - len(data) % 2].decode("utf-16-le").split("\0", 1)[0]
    if spec.storage_kind == "point_array":
        point_size = ctypes.sizeof(T.XDW_POINT)
        if required % point_size:
            raise ValueError(f"{spec.name} returned an invalid XDW_POINT array size: {required}")
        points = (T.XDW_POINT * (required // point_size)).from_buffer_copy(data)
        return tuple(RawPoint(int(p.x), int(p.y)) for p in points)
    if required < 4:
        raise ValueError(f"{spec.name} returned an invalid int32 size: {required}")
    integer = ctypes.c_int32.from_buffer_copy(data[:4]).value
    return integer


def get_standard_attribute(
    raw,
    annotation_handle,
    spec: StandardAttributeSpec,
    *,
    encoding_policy: MultibyteEncodingPolicy | None = None,
):
    return _raw_to_python(
        spec,
        get_standard_attribute_raw(
            raw,
            annotation_handle,
            spec,
            encoding_policy=encoding_policy,
        ),
    )


class CustomAttributeKind(IntEnum):
    INT = C.XDW_ATYPE_INT
    STRING = C.XDW_ATYPE_STRING
    DATE = C.XDW_ATYPE_DATE
    BOOL = C.XDW_ATYPE_BOOL
    OTHER = C.XDW_ATYPE_OTHER


@dataclass(frozen=True)
class CustomAttribute:
    name: str
    kind: CustomAttributeKind
    value: int | str | bool | None


def _custom_name(name: str):
    if not isinstance(name, str):
        raise TypeError("custom attribute name requires str")
    return wchar_buffer(name)


def set_custom_attribute(raw, document_handle, annotation_handle, name: str,
                         kind: CustomAttributeKind, value: Any) -> int:
    kind = CustomAttributeKind(kind)
    if kind == CustomAttributeKind.STRING:
        if not isinstance(value, str):
            raise TypeError("STRING custom attribute requires str")
        storage = wchar_buffer(value)
        pointer = ctypes.cast(storage, ctypes.c_char_p)
    elif kind == CustomAttributeKind.BOOL:
        if not isinstance(value, bool):
            raise TypeError("BOOL custom attribute requires bool")
        storage = ctypes.c_int32(int(value))
        pointer = ctypes.cast(ctypes.byref(storage), ctypes.c_char_p)
    elif kind in (CustomAttributeKind.INT, CustomAttributeKind.DATE):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{kind.name} custom attribute requires a raw 32-bit int")
        if not -(2**31) <= value < 2**31:
            raise ValueError(f"{kind.name} requires a signed 32-bit value")
        storage = ctypes.c_int32(value)
        pointer = ctypes.cast(ctypes.byref(storage), ctypes.c_char_p)
    else:
        if value is not None:
            raise TypeError("OTHER custom attribute has no value; pass None")
        storage = ctypes.c_char(0)  # non-NULL distinguishes OTHER from delete
        pointer = ctypes.cast(ctypes.byref(storage), ctypes.c_char_p)
    result = raw.XDW_SetAnnotationCustomAttribute(
        document_handle, annotation_handle, _custom_name(name), int(kind), pointer, None)
    return check_result(result, f"XDW_SetAnnotationCustomAttribute({name})")


def delete_custom_attribute(raw, document_handle, annotation_handle, name: str) -> int:
    result = raw.XDW_SetAnnotationCustomAttribute(
        document_handle, annotation_handle, _custom_name(name), C.XDW_ATYPE_OTHER, None, None)
    return check_result(result, f"XDW_SetAnnotationCustomAttribute({name}, delete)")


def _decode_custom_value(kind: CustomAttributeKind, data: bytes):
    if kind == CustomAttributeKind.OTHER:
        return None
    if kind == CustomAttributeKind.STRING:
        return data[:len(data) - len(data) % 2].decode("utf-16-le").split("\0", 1)[0]
    if len(data) < 4:
        raise ValueError(f"{kind.name} custom attribute returned fewer than 4 bytes")
    value = ctypes.c_int32.from_buffer_copy(data[:4]).value
    return bool(value) if kind == CustomAttributeKind.BOOL else value


def get_custom_attribute(raw, annotation_handle, name: str) -> CustomAttribute:
    kind_raw = ctypes.c_int32()
    name_buffer = _custom_name(name)
    required = raw.XDW_GetAnnotationCustomAttributeByName(
        annotation_handle, name_buffer, ctypes.byref(kind_raw), None, 0, None)
    required = check_result(required, f"XDW_GetAnnotationCustomAttributeByName({name}, size)")
    kind = CustomAttributeKind(kind_raw.value)
    if required == 0:
        return CustomAttribute(name, kind, None)
    storage = (ctypes.c_char * required)()
    result = raw.XDW_GetAnnotationCustomAttributeByName(
        annotation_handle, name_buffer, ctypes.byref(kind_raw), storage, required, None)
    check_result(result, f"XDW_GetAnnotationCustomAttributeByName({name})")
    kind = CustomAttributeKind(kind_raw.value)
    return CustomAttribute(name, kind, _decode_custom_value(kind, bytes(storage)))


def list_custom_attributes(raw, annotation_handle) -> tuple[CustomAttribute, ...]:
    count = check_result(raw.XDW_GetAnnotationCustomAttributeNumber(annotation_handle, None),
                         "XDW_GetAnnotationCustomAttributeNumber")
    result_items: list[CustomAttribute] = []
    for order in range(1, count + 1):
        name_buffer = (T.XDW_WCHAR * 256)()
        kind_raw = ctypes.c_int32()
        required = raw.XDW_GetAnnotationCustomAttributeByOrder(
            annotation_handle, order, name_buffer, ctypes.byref(kind_raw), None, 0, None)
        required = check_result(required,
                                f"XDW_GetAnnotationCustomAttributeByOrder({order}, size)")
        storage = (ctypes.c_char * max(1, required))()
        result = raw.XDW_GetAnnotationCustomAttributeByOrder(
            annotation_handle, order, name_buffer, ctypes.byref(kind_raw),
            storage if required else None, required, None)
        check_result(result, f"XDW_GetAnnotationCustomAttributeByOrder({order})")
        kind = CustomAttributeKind(kind_raw.value)
        result_items.append(CustomAttribute(
            decode_wchar_buffer(name_buffer), kind,
            _decode_custom_value(kind, bytes(storage[:required]))))
    return tuple(result_items)


def _user_name(
    name: str,
    encoding_policy: MultibyteEncodingPolicy | None = None,
) -> bytes:
    if not isinstance(name, str):
        raise TypeError("user attribute name requires str")
    encoded = _encoding_policy(encoding_policy).encode(name)
    if len(encoded) > 255:
        raise ValueError("user attribute name is limited to 255 bytes")
    return encoded


def set_user_attribute(raw, document_handle, annotation_handle, name: str,
                       value: bytes, *,
                       encoding_policy: MultibyteEncodingPolicy | None = None) -> None:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("user attribute value requires bytes-like data")
    data = bytes(value)
    storage = ctypes.create_string_buffer(data, max(1, len(data)))
    result = raw.XDW_SetAnnotationUserAttribute(
        document_handle, annotation_handle, _user_name(name, encoding_policy),
        ctypes.cast(storage, ctypes.c_char_p), len(data), None)
    check_result(result, f"XDW_SetAnnotationUserAttribute({name})")


def delete_user_attribute(raw, document_handle, annotation_handle, name: str, *,
                          encoding_policy: MultibyteEncodingPolicy | None = None) -> None:
    result = raw.XDW_SetAnnotationUserAttribute(
        document_handle, annotation_handle, _user_name(name, encoding_policy), None, 0, None)
    check_result(result, f"XDW_SetAnnotationUserAttribute({name}, delete)")


def get_user_attribute(raw, annotation_handle, name: str, *,
                       encoding_policy: MultibyteEncodingPolicy | None = None) -> bytes:
    encoded_name = _user_name(name, encoding_policy)
    required = raw.XDW_GetAnnotationUserAttribute(annotation_handle, encoded_name, None, 0, None)
    required = check_result(required, f"XDW_GetAnnotationUserAttribute({name}, size)")
    if required == 0:
        return b""
    storage = (ctypes.c_char * required)()
    result = raw.XDW_GetAnnotationUserAttribute(
        annotation_handle, encoded_name, storage, required, None)
    check_result(result, f"XDW_GetAnnotationUserAttribute({name})")
    return bytes(storage)
