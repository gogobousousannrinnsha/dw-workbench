import ctypes
import inspect
import json
from pathlib import Path
from typing import get_type_hints

import pytest

from docuworks_ctypes import (
    AnnotationType,
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
    LinkType,
    PointMM,
    RawPoint,
    SizeMM,
)
from docuworks_ctypes._raw import constants as C
from docuworks_ctypes._raw import types as T
from docuworks_ctypes.attributes import (
    get_standard_attribute,
    get_standard_attribute_raw,
    standard_attribute_spec,
)
from docuworks_ctypes.document import Document, Page
from docuworks_ctypes.enums import OpenMode
from docuworks_ctypes.errors import ClosedHandleError, ReadOnlyDocumentError
from docuworks_ctypes.simple import SimpleAnnotation, SimpleDocument, SimplePage
from generate_standard_coverage import generate


class PointsRaw:
    def XDW_GetAnnotationAttributeW(self, *args):
        points = (T.XDW_POINT * 3)()
        points[0].x, points[0].y = 1000, 2000
        points[1].x, points[1].y = 500, -500
        points[2].x, points[2].y = -250, 1000
        data = bytes(points)
        if args[2] is None:
            return len(data)
        ctypes.memmove(args[2], data, len(data))
        return len(data)


def test_points_raw_and_natural_contracts_are_distinct():
    spec = standard_attribute_spec(C.XDW_AID_POLYGON, C.XDW_ATN_Points)
    raw = PointsRaw()
    assert get_standard_attribute_raw(raw, 1, spec) == (
        RawPoint(1000, 2000),
        RawPoint(500, -500),
        RawPoint(-250, 1000),
    )
    assert get_standard_attribute(raw, 1, spec) == (
        PointMM(10.0, 20.0),
        PointMM(15.0, 15.0),
        PointMM(7.5, 30.0),
    )


def test_polygon_initial_points_use_first_absolute_then_relative_vectors():
    storage = Page._initial_point_array(
        [PointMM(10, 20), PointMM(15, 15), PointMM(12.5, 25)]
    )
    assert [(point.x, point.y) for point in storage] == [
        (1000, 2000),
        (500, -500),
        (250, 500),
    ]


def test_link_target_contract_rejects_before_xdwapi_call():
    class NoAddRaw:
        called = False

        def XDW_AddAnnotation(self, *args):
            self.called = True
            return 0

    raw = NoAddRaw()
    page = Page(Document(raw, 1, Path("fixture.xdw"), OpenMode.UPDATE), 1)
    with pytest.raises(ValueError):
        page.add_link(PointMM(1, 1), "URL", link_type=LinkType.URL)
    with pytest.raises(ValueError):
        page.add_link(
            PointMM(1, 1),
            "self",
            link_type=LinkType.THIS_DOCUMENT,
            target="unexpected",
        )
    assert raw.called is False


class FakeAnnotation:
    def __init__(self, annotation_type=AnnotationType.RECTANGLE):
        self.annotation_type = annotation_type
        self.position = PointMM(1, 2)
        self.size = SizeMM(30, 40)
        self.valid = True

    def _ensure_valid(self):
        if not self.valid:
            raise ClosedHandleError("closed")

    def set_position(self, position):
        self._ensure_valid()
        self.position = position

    def set_size(self, size):
        self._ensure_valid()
        self.size = size

    def remove(self):
        self._ensure_valid()
        self.valid = False


class RecordingPage:
    def __init__(self, annotations=()):
        self.current_annotations = tuple(annotations)
        self.calls = []
        self.recursive_values = []

    def annotations(self, recursive=True):
        self.recursive_values.append(recursive)
        return iter(self.current_annotations)

    def _add(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        return FakeAnnotation()

    def add_text(self, *args, **kwargs):
        return self._add("text", args, kwargs)

    def add_rectangle(self, *args, **kwargs):
        return self._add("rectangle", args, kwargs)

    def add_sticky(self, *args, **kwargs):
        return self._add("sticky", args, kwargs)

    def add_ellipse(self, *args, **kwargs):
        return self._add("ellipse", args, kwargs)

    def add_line(self, *args, **kwargs):
        return self._add("line", args, kwargs)

    def add_polygon(self, *args, **kwargs):
        return self._add("polygon", args, kwargs)

    def add_marker(self, *args, **kwargs):
        return self._add("marker", args, kwargs)

    def add_link(self, *args, **kwargs):
        return self._add("link", args, kwargs)


def test_simple_page_delegates_natural_units_and_wraps_core_annotations():
    core = RecordingPage()
    page = SimplePage(core)
    text = page.text("確認", x=10, y=20, font_size=12, fore_color=Color.BLUE)
    rectangle = page.rectangle(x=1, y=2, width=30, height=40)
    assert isinstance(text, SimpleAnnotation)
    assert isinstance(rectangle, SimpleAnnotation)
    assert core.calls[0][1] == (PointMM(10, 20), "確認")
    assert core.calls[0][2]["font_size"] == 12
    assert core.calls[0][2]["fore_color"] is Color.BLUE
    assert core.calls[1][1][0].width == 30


def test_simple_annotations_are_snapshot_tuples_with_top_level_default():
    annotations = (FakeAnnotation(AnnotationType.STICKY), FakeAnnotation(999999))
    core = RecordingPage(annotations)
    page = SimplePage(core)
    top_level = page.annotations()
    recursive = page.annotations(recursive=True)
    assert isinstance(top_level, tuple)
    assert [annotation.type for annotation in top_level] == [
        AnnotationType.STICKY,
        999999,
    ]
    assert [annotation.type for annotation in recursive] == [
        AnnotationType.STICKY,
        999999,
    ]
    assert core.recursive_values == [False, True]
    assert top_level[0] is not recursive[0]


def test_simple_annotation_lifecycle_and_natural_unit_mutations():
    core = FakeAnnotation()
    annotation = SimpleAnnotation(core)
    assert annotation.type is AnnotationType.RECTANGLE
    assert annotation.position == PointMM(1, 2)
    assert annotation.size == SizeMM(30, 40)
    assert annotation.core is core
    assert annotation.move_to(x=5, y=6) is None
    assert annotation.position == PointMM(5, 6)
    assert annotation.resize(width=50, height=60) is None
    assert annotation.size == SizeMM(50, 60)
    assert annotation.delete() is None
    for access in (
        lambda: annotation.type,
        lambda: annotation.position,
        lambda: annotation.size,
        lambda: annotation.core,
        lambda: annotation.move_to(x=1, y=1),
        lambda: annotation.resize(width=1, height=1),
        annotation.delete,
    ):
        with pytest.raises(ClosedHandleError):
            access()


def test_simple_annotation_propagates_core_exceptions():
    class ReadOnlyAnnotation(FakeAnnotation):
        def set_position(self, position):
            raise ReadOnlyDocumentError("read only")

    with pytest.raises(ReadOnlyDocumentError):
        SimpleAnnotation(ReadOnlyAnnotation()).move_to(x=1, y=2)


@pytest.mark.parametrize(
    ("call", "expected_name"),
    [
        (
            lambda page: page.text(
                "text", x=1, y=2, fore_color=Color.BLUE
            ),
            "text",
        ),
        (
            lambda page: page.rectangle(x=1, y=2, width=30, height=40),
            "rectangle",
        ),
        (
            lambda page: page.sticky(x=1, y=2, width=30, height=40),
            "sticky",
        ),
        (
            lambda page: page.ellipse(x=1, y=2, width=30, height=40),
            "ellipse",
        ),
        (
            lambda page: page.line(
                x1=1,
                y1=2,
                x2=3,
                y2=4,
                border_type=BorderType.DASH,
                arrowhead_type=ArrowheadType.ENDING,
                arrowhead_style=ArrowheadStyle.POLYGON,
            ),
            "line",
        ),
        (
            lambda page: page.polygon(
                (PointMM(1, 1), PointMM(2, 1), PointMM(2, 2)),
                fill_color=Color.YELLOW,
            ),
            "polygon",
        ),
        (
            lambda page: page.marker((PointMM(1, 1), PointMM(2, 2))),
            "marker",
        ),
        (
            lambda page: page.link(
                "link", x=1, y=2, link_type=LinkType.THIS_DOCUMENT
            ),
            "link",
        ),
    ],
)
def test_all_simple_creation_methods_return_simple_annotations(call, expected_name):
    core = RecordingPage()
    result = call(SimplePage(core))
    assert isinstance(result, SimpleAnnotation)
    assert core.calls[0][0] == expected_name


@pytest.mark.parametrize(
    "call",
    [
        lambda page: page.text("text", x=1, y=2, fore_color=1),
        lambda page: page.rectangle(
            x=1, y=2, width=30, height=40, border_color=1
        ),
        lambda page: page.sticky(x=1, y=2, width=30, height=40, fill_color=1),
        lambda page: page.ellipse(
            x=1, y=2, width=30, height=40, fill_color=1
        ),
        lambda page: page.line(x1=1, y1=2, x2=3, y2=4, border_type=1),
        lambda page: page.polygon(
            (PointMM(1, 1), PointMM(2, 1), PointMM(2, 2)),
            arrowhead_type=1,
        ),
        lambda page: page.marker(
            (PointMM(1, 1), PointMM(2, 2)), border_color=1
        ),
        lambda page: page.link("link", x=1, y=2, link_type=1),
    ],
)
def test_simple_rejects_raw_enum_integers_before_calling_core(call):
    core = RecordingPage()
    with pytest.raises(TypeError):
        call(SimplePage(core))
    assert core.calls == []


def test_simple_public_signatures_have_no_variadic_keyword_parameters():
    methods = (
        SimplePage.annotations,
        SimplePage.text,
        SimplePage.rectangle,
        SimplePage.sticky,
        SimplePage.ellipse,
        SimplePage.line,
        SimplePage.polygon,
        SimplePage.marker,
        SimplePage.link,
        SimpleAnnotation.move_to,
        SimpleAnnotation.resize,
        SimpleAnnotation.delete,
    )
    for method in methods:
        assert all(
            parameter.kind is not inspect.Parameter.VAR_KEYWORD
            for parameter in inspect.signature(method).parameters.values()
        )
    assert inspect.signature(SimplePage.annotations).parameters["recursive"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )


def test_simple_public_return_annotations_are_fixed():
    assert get_type_hints(SimplePage.annotations)["return"] == tuple[
        SimpleAnnotation, ...
    ]
    for name in (
        "text",
        "rectangle",
        "sticky",
        "ellipse",
        "line",
        "polygon",
        "marker",
        "link",
    ):
        assert get_type_hints(getattr(SimplePage, name))["return"] is SimpleAnnotation
    assert not hasattr(SimplePage, "date_stamp")


def test_standard_coverage_is_registry_driven_and_requires_both_stages(tmp_path):
    from docuworks_ctypes import STANDARD_ATTRIBUTE_REGISTRY

    evidence = tmp_path / "evidence.jsonl"
    rows = []
    for annotation_type, attribute in STANDARD_ATTRIBUTE_REGISTRY:
        for stage in ("coverage_immediate", "coverage_persistence"):
            rows.append(
                json.dumps(
                    {
                        "case": f"{annotation_type}-{attribute}",
                        "stage": stage,
                        "annotation_type": annotation_type,
                        "attribute": attribute,
                    }
                )
            )
    evidence.write_text("\n".join(rows) + "\n", encoding="utf-8")
    report = generate(evidence)
    assert report["registry_count"] == 89
    assert report["complete_count"] == 89
    assert report["full_persistence_verified"] is True


def test_simple_document_context_does_not_implicitly_save():
    class FakeDocument:
        saved = 0
        closed = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed += 1
            return False

        def save(self):
            self.saved += 1

        def close(self):
            self.closed += 1

    core = FakeDocument()
    with SimpleDocument(core):
        pass
    assert core.saved == 0
    assert core.closed == 1
