import pytest

from docuworks_ctypes import STANDARD_ATTRIBUTE_REGISTRY, standard_attribute_spec
from docuworks_ctypes._raw import constants as C
from docuworks_ctypes.attributes import validate_standard_value


def test_section_31_registry_covers_all_nine_annotation_types():
    expected = {
        C.XDW_AID_TEXT: 18,
        C.XDW_AID_LINK: 24,
        C.XDW_AID_FUSEN: 2,
        C.XDW_AID_STRAIGHTLINE: 7,
        C.XDW_AID_RECTANGLE: 6,
        C.XDW_AID_ARC: 6,
        C.XDW_AID_STAMP: 12,
        C.XDW_AID_MARKER: 4,
        C.XDW_AID_POLYGON: 10,
    }
    actual = {kind: sum(key[0] == kind for key in STANDARD_ATTRIBUTE_REGISTRY)
              for kind in expected}
    assert actual == expected
    assert len(STANDARD_ATTRIBUTE_REGISTRY) == 89


def test_every_spec_has_the_required_contract_fields():
    for (annotation_type, name), spec in STANDARD_ATTRIBUTE_REGISTRY.items():
        assert spec.annotation_type == annotation_type
        assert spec.name == name
        assert spec.storage_kind in {"int32", "string", "point_array"}
        assert spec.python_kind in {"int", "float", "str", "bool", "color", "points"}
        assert isinstance(spec.readable, bool)
        assert isinstance(spec.writable, bool)
        assert isinstance(spec.unicode_allowed, bool)
        assert isinstance(spec.conditions, tuple)
        if spec.python_kind == "float":
            assert spec.python_unit is not None
            assert spec.raw_per_python_unit is not None


@pytest.mark.parametrize("kind", [C.XDW_AID_STRAIGHTLINE, C.XDW_AID_MARKER, C.XDW_AID_POLYGON])
def test_points_are_readable_but_not_writable(kind):
    spec = standard_attribute_spec(kind, C.XDW_ATN_Points)
    assert spec.readable is True
    assert spec.writable is False
    assert spec.storage_kind == "point_array"


def test_unicode_allowlist_matches_section_31_exactly():
    actual = {(kind, name) for (kind, name), spec in STANDARD_ATTRIBUTE_REGISTRY.items()
              if spec.unicode_allowed}
    expected = {
        (C.XDW_AID_TEXT, C.XDW_ATN_Text),
        *((C.XDW_AID_LINK, name) for name in (
            C.XDW_ATN_Caption, C.XDW_ATN_Url, C.XDW_ATN_XdwPath,
            C.XDW_ATN_XdwNameInXbd, C.XDW_ATN_Tooltip_String,
            C.XDW_ATN_LinkAtn_Title, C.XDW_ATN_OtherFilePath,
            C.XDW_ATN_MailAddress,
        )),
        (C.XDW_AID_STAMP, C.XDW_ATN_TopField),
        (C.XDW_AID_STAMP, C.XDW_ATN_BottomField),
    }
    assert actual == expected


def test_only_explicit_section_31_constraints_are_strict():
    orientation = standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_TextOrientation)
    validate_standard_value(orientation, 359)
    with pytest.raises(ValueError):
        validate_standard_value(orientation, 360)

    border_width = standard_attribute_spec(C.XDW_AID_RECTANGLE, C.XDW_ATN_BorderWidth)
    validate_standard_value(border_width, 9999)  # no range is stated in 3.1

    fill = standard_attribute_spec(C.XDW_AID_POLYGON, C.XDW_ATN_FillStyle)
    validate_standard_value(fill, True, context={C.XDW_ATN_Close: 1})
    with pytest.raises(ValueError):
        validate_standard_value(fill, True, context={C.XDW_ATN_Close: 0})


def test_annotation_type_specific_color_tables_are_not_merged():
    sticky = standard_attribute_spec(C.XDW_AID_FUSEN, C.XDW_ATN_FillColor)
    rectangle = standard_attribute_spec(C.XDW_AID_RECTANGLE, C.XDW_ATN_FillColor)
    validate_standard_value(sticky, C.XDW_COLOR_FUSEN_RED)
    with pytest.raises(ValueError):
        validate_standard_value(sticky, C.XDW_COLOR_RED)
    validate_standard_value(rectangle, C.XDW_COLOR_RED)
