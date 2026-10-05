from __future__ import annotations

import pytest

from docuworks_ctypes import (
    AnnotationType,
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    ClosedHandleError,
    Color,
    LinkType,
    PointMM,
    SizeMM,
)
from docuworks_ctypes.simple import SimpleAnnotation, open_xdw


pytestmark = pytest.mark.integration


def _state(annotations):
    return [
        {
            "type": int(annotation.type),
            "position": annotation.position,
            "size": annotation.size,
        }
        for annotation in annotations
    ]


def _first(page, annotation_type):
    return next(
        annotation
        for annotation in page.annotations()
        if annotation.type is annotation_type
    )


def test_simple_workflow_creates_all_eight_types_and_persists(xdw_copy, evidence):
    expected_top_level = [
        AnnotationType.TEXT,
        AnnotationType.RECTANGLE,
        AnnotationType.STICKY,
        AnnotationType.ELLIPSE,
        AnnotationType.STRAIGHT_LINE,
        AnnotationType.POLYGON,
        AnnotationType.MARKER,
        AnnotationType.LINK,
    ]
    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        page = document.page(1)
        created = (
            page.text("Simple workflow", x=15, y=15, font_size=12, fore_color=Color.BLUE),
            page.rectangle(
                x=15, y=35, width=30, height=18,
                border_color=Color.RED, fill_color=Color.YELLOW,
            ),
            page.sticky(
                x=55, y=35, width=30, height=25,
                fill_color=Color.STICKY_YELLOW, text="付箋",
            ),
            page.ellipse(
                x=95, y=35, width=30, height=18,
                border_color=Color.RED, fill_color=Color.YELLOW,
            ),
            page.line(
                x1=15, y1=75, x2=50, y2=90,
                border_color=Color.BLUE, border_type=BorderType.DASH,
                arrowhead_type=ArrowheadType.ENDING,
                arrowhead_style=ArrowheadStyle.POLYGON,
            ),
            page.polygon(
                (PointMM(60, 75), PointMM(90, 75), PointMM(80, 95)),
                border_color=Color.BLUE, fill_color=Color.YELLOW,
            ),
            page.marker(
                (PointMM(105, 75), PointMM(125, 82), PointMM(140, 90)),
                border_color=Color.GREEN,
            ),
            page.link(
                "This document", x=15, y=110,
                link_type=LinkType.THIS_DOCUMENT, fore_color=Color.BLUE,
            ),
        )
        assert all(isinstance(annotation, SimpleAnnotation) for annotation in created)
        immediate_top = page.annotations()
        immediate_recursive = page.annotations(recursive=True)
        assert [annotation.type for annotation in immediate_top] == expected_top_level
        assert len(immediate_recursive) == 9
        assert immediate_recursive[2].type is AnnotationType.STICKY
        assert immediate_recursive[3].type is AnnotationType.TEXT
        immediate = _state(immediate_recursive)
        evidence("memory", workflow="create_all", annotations=immediate)
        document.save()

    with open_xdw(xdw_copy, codepage=932) as document:
        persisted_items = document.page(1).annotations(recursive=True)
        persisted = _state(persisted_items)
        assert persisted == immediate
        evidence("persistence", workflow="create_all", annotations=persisted)


def test_simple_workflow_enumerates_moves_resizes_and_persists(xdw_copy, evidence):
    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        document.page(1).rectangle(x=20, y=30, width=30, height=20)
        document.save()

    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        page = document.page(1)
        first_snapshot = page.annotations()
        second_snapshot = page.annotations()
        assert first_snapshot[0] is not second_snapshot[0]
        rectangle = _first(page, AnnotationType.RECTANGLE)
        rectangle.move_to(x=25, y=45)
        rectangle.resize(width=40, height=25)
        assert rectangle.position == PointMM(25, 45)
        assert rectangle.size == SizeMM(40, 25)
        refreshed = _first(page, AnnotationType.RECTANGLE)
        assert refreshed.position == PointMM(25, 45)
        assert refreshed.size == SizeMM(40, 25)
        evidence("memory", workflow="enumerate_edit", annotations=_state((refreshed,)))
        document.save()

    with open_xdw(xdw_copy, codepage=932) as document:
        rectangle = _first(document.page(1), AnnotationType.RECTANGLE)
        assert rectangle.position == PointMM(25, 45)
        assert rectangle.size == SizeMM(40, 25)
        evidence("persistence", workflow="enumerate_edit", annotations=_state((rectangle,)))


def test_simple_workflow_recursive_preorder_is_persistent(xdw_copy, evidence):
    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        page = document.page(1)
        page.sticky(x=20, y=20, width=30, height=25, text="child")
        assert [item.type for item in page.annotations()] == [AnnotationType.STICKY]
        assert [item.type for item in page.annotations(recursive=True)] == [
            AnnotationType.STICKY,
            AnnotationType.TEXT,
        ]
        document.save()

    with open_xdw(xdw_copy, codepage=932) as document:
        page = document.page(1)
        top_level = page.annotations()
        recursive = page.annotations(recursive=True)
        assert [item.type for item in top_level] == [AnnotationType.STICKY]
        assert [item.type for item in recursive] == [
            AnnotationType.STICKY,
            AnnotationType.TEXT,
        ]
        evidence(
            "persistence",
            workflow="recursive_preorder",
            top_level=_state(top_level),
            recursive=_state(recursive),
        )


def test_simple_workflow_deletes_reenumerates_and_persists(xdw_copy, evidence):
    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        page = document.page(1)
        page.rectangle(x=20, y=30, width=30, height=20)
        page.text("keep", x=20, y=60)
        document.save()

    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        page = document.page(1)
        rectangle = _first(page, AnnotationType.RECTANGLE)
        rectangle.delete()
        with pytest.raises(ClosedHandleError):
            _ = rectangle.type
        remaining = page.annotations()
        assert [item.type for item in remaining] == [AnnotationType.TEXT]
        evidence("memory", workflow="delete", remaining=_state(remaining))
        document.save()

    with open_xdw(xdw_copy, codepage=932) as document:
        remaining = document.page(1).annotations()
        assert [item.type for item in remaining] == [AnnotationType.TEXT]
        evidence("persistence", workflow="delete", remaining=_state(remaining))


def test_simple_workflow_only_explicit_save_persists(xdw_copy, evidence):
    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        document.page(1).rectangle(x=20, y=30, width=30, height=20)

    with open_xdw(xdw_copy, codepage=932) as document:
        assert document.page(1).annotations() == ()
        evidence("reopen_without_save", workflow="explicit_save", count=0)

    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        document.page(1).rectangle(x=20, y=30, width=30, height=20)
        document.save()

    with open_xdw(xdw_copy, codepage=932) as document:
        annotations = document.page(1).annotations()
        assert [item.type for item in annotations] == [AnnotationType.RECTANGLE]
        evidence("persistence", workflow="explicit_save", annotations=_state(annotations))
