import ctypes
from decimal import Decimal

import pytest

from docuworks_ctypes import XdwApi
from docuworks_ctypes._raw import constants as C
from docuworks_ctypes.attributes import (
    get_standard_attribute,
    get_standard_attribute_raw,
    set_standard_attribute,
    set_standard_attribute_raw,
    standard_attribute_spec,
    validate_standard_raw_value,
    validate_standard_value,
    set_user_attribute,
)
from docuworks_ctypes.encoding import MultibyteEncodingPolicy, system_ansi_codepage


class AttributeRaw:
    def __init__(self, values=None):
        self.values = values or {}
        self.calls = []
        self.set_int32 = []

    def XDW_SetAnnotationAttributeW(self, *args):
        self.calls.append(("set_w", args))
        if args[3] == C.XDW_ATYPE_INT:
            self.set_int32.append(
                ctypes.cast(args[4], ctypes.POINTER(ctypes.c_int32)).contents.value
            )
        return 0

    def XDW_SetAnnotationAttribute(self, *args):
        self.calls.append(("set_mb", args))
        return 0

    def XDW_GetAnnotationAttributeW(self, *args):
        self.calls.append(("get_w", args))
        name = args[1].decode("ascii")
        value = self.values[name]
        if isinstance(value, str):
            data = value.encode("utf-16-le") + b"\0\0"
        else:
            data = int(value).to_bytes(4, "little", signed=True)
        if args[2] is None:
            return len(data)
        ctypes.memmove(args[2], data, min(len(data), args[3]))
        return len(data)


def test_system_ansi_codepage_and_override_are_validated():
    assert system_ansi_codepage() > 0
    assert MultibyteEncodingPolicy.create(932).codec == "cp932"
    assert MultibyteEncodingPolicy.create(65001).codec in {"utf-8", "cp65001"}
    with pytest.raises(ValueError):
        MultibyteEncodingPolicy.create(99999)


def test_xdwapi_from_raw_exposes_the_selected_policy():
    api = XdwApi.from_raw(object(), multibyte_codepage=1252)
    assert api.multibyte_encoding.codepage == 1252
    assert api.multibyte_encoding.codec == "cp1252"


def test_w_getter_uses_multibyte_codepage_not_utf16_codepage():
    raw = AttributeRaw({C.XDW_ATN_Text: "ABC"})
    policy = MultibyteEncodingPolicy.create(1252)
    spec = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_Text)
    assert get_standard_attribute(raw, 1, spec, encoding_policy=policy) == "ABC"
    assert [call[1][5] for call in raw.calls] == [1252, 1252]


def test_unicode_setter_uses_ifnecessary_and_selected_codepage():
    raw = AttributeRaw()
    policy = MultibyteEncodingPolicy.create(932)
    spec = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_Text)
    set_standard_attribute(raw, 1, 2, spec, "ABC", encoding_policy=policy)
    _, args = raw.calls[-1]
    assert args[5] == C.XDW_TEXT_UNICODE_IFNECESSARY
    assert args[6] == 932


def test_non_unicode_setter_uses_selected_multibyte_codec():
    raw = AttributeRaw()
    policy = MultibyteEncodingPolicy.create(1252)
    spec = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_FontName)
    set_standard_attribute(raw, 1, 2, spec, "Café", encoding_policy=policy)
    name, args = raw.calls[-1]
    assert name == "set_mb"
    assert ctypes.string_at(args[4]) == "Café".encode("cp1252")
    with pytest.raises(UnicodeEncodeError):
        set_standard_attribute(raw, 1, 2, spec, "日本語", encoding_policy=policy)


def test_user_attribute_name_uses_the_selected_multibyte_codec():
    class UserRaw:
        args = None

        def XDW_SetAnnotationUserAttribute(self, *args):
            self.args = args
            return 0

    raw = UserRaw()
    policy = MultibyteEncodingPolicy.create(1252)
    set_user_attribute(raw, 1, 2, "café", b"", encoding_policy=policy)
    assert raw.args[2] == "café".encode("cp1252")
    assert raw.args[3] is not None
    assert raw.args[4] == 0


@pytest.mark.parametrize(
    ("name", "python_value", "raw_value"),
    [
        (C.XDW_ATN_FontSize, 12.0, 120),
        (C.XDW_ATN_TextSpacing, Decimal("1.25"), 13),
        (C.XDW_ATN_LineSpace, 1.25, 125),
        (C.XDW_ATN_TextTopMargin, 1.7, 170),
        (C.XDW_ATN_TextOrientation, 12.5, 13),
    ],
)
def test_natural_units_encode_with_half_up_rounding(name, python_value, raw_value):
    raw = AttributeRaw()
    spec = standard_attribute_spec(C.XDW_AID_TEXT, name)
    set_standard_attribute(raw, 1, 2, spec, python_value)
    assert raw.set_int32 == [raw_value]


def test_natural_and_raw_getters_are_distinct():
    raw = AttributeRaw({C.XDW_ATN_FontSize: 120})
    spec = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_FontSize)
    assert get_standard_attribute_raw(raw, 1, spec) == 120
    assert get_standard_attribute(raw, 1, spec) == 12.0


def test_raw_setter_bypasses_unit_conversion_but_keeps_validation():
    raw = AttributeRaw()
    spec = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_FontSize)
    set_standard_attribute_raw(raw, 1, 2, spec, 12)
    assert raw.set_int32 == [12]
    with pytest.raises(TypeError):
        set_standard_attribute_raw(raw, 1, 2, spec, 12.0)


def test_bool_natural_and_raw_contracts_are_distinct():
    spec = standard_attribute_spec(C.XDW_AID_RECTANGLE, C.XDW_ATN_FillTransparent)

    getter = AttributeRaw({C.XDW_ATN_FillTransparent: 1})
    assert get_standard_attribute_raw(getter, 1, spec) == 1
    assert type(get_standard_attribute_raw(getter, 1, spec)) is int
    assert get_standard_attribute(getter, 1, spec) is True

    natural_setter = AttributeRaw()
    set_standard_attribute(natural_setter, 1, 2, spec, True)
    assert natural_setter.set_int32 == [1]
    with pytest.raises(TypeError):
        set_standard_attribute(natural_setter, 1, 2, spec, 1)

    raw_setter = AttributeRaw()
    set_standard_attribute_raw(raw_setter, 1, 2, spec, 0)
    set_standard_attribute_raw(raw_setter, 1, 2, spec, 1)
    assert raw_setter.set_int32 == [0, 1]
    with pytest.raises(TypeError):
        set_standard_attribute_raw(raw_setter, 1, 2, spec, True)
    with pytest.raises(ValueError):
        set_standard_attribute_raw(raw_setter, 1, 2, spec, 2)


def test_raw_bool_condition_context_uses_integer_storage_values():
    spec = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_TextAutoResizeHeight)
    validate_standard_raw_value(
        spec,
        1,
        context={C.XDW_ATN_WordWrap: 1},
    )
    with pytest.raises(ValueError):
        validate_standard_raw_value(
            spec,
            1,
            context={C.XDW_ATN_WordWrap: 0},
        )
    with pytest.raises(ValueError):
        validate_standard_raw_value(
            spec,
            1,
            context={C.XDW_ATN_WordWrap: True},
        )


def test_unicode_byte_boundaries_follow_ifnecessary_storage_choice():
    policy = MultibyteEncodingPolicy.create(932)
    spec = standard_attribute_spec(C.XDW_AID_STAMP, C.XDW_ATN_TopField)
    validate_standard_value(spec, "日" * 6, encoding_policy=policy)
    validate_standard_value(spec, "A" * 12, encoding_policy=policy)
    validate_standard_value(spec, "😀" * 3, encoding_policy=policy)
    with pytest.raises(ValueError):
        validate_standard_value(spec, "日" * 7, encoding_policy=policy)
    with pytest.raises(ValueError):
        validate_standard_value(spec, "A" * 13, encoding_policy=policy)
    with pytest.raises(ValueError):
        validate_standard_value(spec, "😀" * 4, encoding_policy=policy)
