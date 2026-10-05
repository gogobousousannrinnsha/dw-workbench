import ctypes

from docuworks_ctypes._raw import constants as C
from docuworks_ctypes.attributes import (
    CustomAttributeKind,
    get_user_attribute,
    set_custom_attribute,
    set_standard_attribute,
    set_user_attribute,
    standard_attribute_spec,
)


class RecordingRaw:
    def __init__(self):
        self.calls = []
        self.int32_values = []

    def __getattr__(self, name):
        def call(*args):
            if name == "XDW_SetAnnotationAttributeW" and args[3] == C.XDW_ATYPE_INT:
                self.int32_values.append(
                    ctypes.cast(args[4], ctypes.POINTER(ctypes.c_int32)).contents.value
                )
            if name == "XDW_SetAnnotationCustomAttribute" and args[3] in {
                C.XDW_ATYPE_INT, C.XDW_ATYPE_DATE, C.XDW_ATYPE_BOOL
            }:
                self.int32_values.append(
                    ctypes.cast(args[4], ctypes.POINTER(ctypes.c_int32)).contents.value
                )
            self.calls.append((name, args))
            return 0
        return call


def test_standard_bool_uses_standard_int_not_custom_bool():
    raw = RecordingRaw()
    spec = standard_attribute_spec(C.XDW_AID_RECTANGLE, C.XDW_ATN_FillTransparent)
    set_standard_attribute(raw, 1, 2, spec, True)
    name, args = raw.calls[-1]
    assert name == "XDW_SetAnnotationAttributeW"
    assert args[3] == C.XDW_ATYPE_INT
    assert raw.int32_values == [1]


def test_only_allowlisted_standard_strings_use_wide_setter():
    raw = RecordingRaw()
    text = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_Text)
    font = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_FontName)
    set_standard_attribute(raw, 1, 2, text, "確認")
    set_standard_attribute(raw, 1, 2, font, "Arial")
    assert raw.calls[0][0] == "XDW_SetAnnotationAttributeW"
    assert raw.calls[1][0] == "XDW_SetAnnotationAttribute"


def test_custom_date_is_raw_int32_and_other_uses_non_null_no_value_pointer():
    raw = RecordingRaw()
    set_custom_attribute(raw, 1, 2, "date", CustomAttributeKind.DATE, -123)
    _, date_args = raw.calls[-1]
    assert date_args[3] == C.XDW_ATYPE_DATE
    assert raw.int32_values == [-123]

    set_custom_attribute(raw, 1, 2, "marker", CustomAttributeKind.OTHER, None)
    _, other_args = raw.calls[-1]
    assert other_args[3] == C.XDW_ATYPE_OTHER
    assert other_args[4] is not None


def test_zero_byte_user_attribute_is_a_non_null_value_not_delete():
    raw = RecordingRaw()
    set_user_attribute(raw, 1, 2, "empty", b"")
    _, args = raw.calls[-1]
    assert args[3] is not None
    assert args[4] == 0


def test_zero_byte_user_attribute_can_be_read():
    raw = RecordingRaw()
    assert get_user_attribute(raw, 2, "empty") == b""
    assert raw.calls == [("XDW_GetAnnotationUserAttribute", (2, b"empty", None, 0, None))]


def test_old_merged_annotation_api_is_gone():
    from docuworks_ctypes.document import Annotation
    assert not hasattr(Annotation, "set_attribute")
    assert not hasattr(Annotation, "get_attribute")
    for method in (
        "set_standard_attribute", "get_standard_attribute",
        "set_standard_attribute_raw", "get_standard_attribute_raw",
        "set_custom_attribute", "get_custom_attribute", "custom_attributes",
        "set_user_attribute", "get_user_attribute",
    ):
        assert hasattr(Annotation, method)
