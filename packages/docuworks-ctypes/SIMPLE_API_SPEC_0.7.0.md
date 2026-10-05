# Simple API Specification 0.7.0

This document is the normative public contract for the 0.7.0 Simple facade.
Core remains the verified 0.6.3 baseline beneath this API.

## Layer and persistence

```text
Simple -> Core -> Raw ctypes -> XDWAPI
```

Simple uses mm for coordinates and dimensions, and pt for font size. Page
numbers are 1-based. `SimpleDocument.page()` defaults to page 1. Mutations are
not persisted until `SimpleDocument.save()` is called. Context manager exit
closes the document and never saves implicitly.

## Public types and signatures

```python
def open_xdw(
    path: str | Path,
    *,
    writable: bool = False,
    dll_path: str | Path | None = None,
    codepage: int | None = None,
) -> SimpleDocument: ...

class SimpleDocument:
    core: Document
    def page(self, number: int = 1) -> SimplePage: ...
    def save(self) -> None: ...
    def close(self) -> None: ...

class SimplePage:
    core: Page
    def annotations(
        self, *, recursive: bool = False
    ) -> tuple[SimpleAnnotation, ...]: ...

class SimpleAnnotation:
    def __init__(self, core: Annotation): ...
    @property
    def type(self) -> AnnotationType | int: ...
    @property
    def position(self) -> PointMM: ...
    @property
    def size(self) -> SizeMM | None: ...
    @property
    def core(self) -> Annotation: ...
    def move_to(self, *, x: float, y: float) -> None: ...
    def resize(self, *, width: float, height: float) -> None: ...
    def delete(self) -> None: ...
```

`SimpleAnnotation`, `SimpleDocument`, `SimplePage`, and `open_xdw` are exported
from `docuworks_ctypes.simple`.

## Enumeration

`SimplePage.annotations()` returns a fully materialized snapshot tuple in XDW
enumeration order. The default contains top-level annotations only.
`recursive=True` returns a flat preorder sequence: each parent immediately
followed by its descendants. For example, Sticky child Text is included only
in recursive enumeration.

Each call creates new wrapper objects. Wrapper identity and equality across
calls are not guaranteed. Parent and children properties are not part of
0.7.0. After a structural deletion, callers discard other previously obtained
snapshot wrappers and enumerate again.

Known annotation types are returned as `AnnotationType`; a future unknown type
is preserved as its integer value so enumeration remains possible. Existing
date stamps can be enumerated, but there is no `page.date_stamp()` creation API.

## Creation methods

`SimplePage` provides `text`, `rectangle`, `sticky`, `ellipse`, `line`,
`polygon`, `marker`, and `link`. Every method returns `SimpleAnnotation`.
All optional style parameters are explicit keyword-only parameters; the public
API contains no variadic `**style` parameter.

Colors accept `Color` only. Border, arrowhead, and link kinds accept their exact
`BorderType`, `ArrowheadType`, `ArrowheadStyle`, and `LinkType` enums only.
Raw integer equivalents are rejected with `TypeError` before Core is called.
Arbitrary COLORREF integers and custom RGB types are outside Simple 1.0.

`ellipse` exposes the same explicit border/fill arguments as `rectangle`.
`polygon` explicitly exposes `close`, border/fill arguments, and arrowhead
arguments. Point sequences use absolute `PointMM` values and remain delegated
to Core for validation and XDW conversion.

## Lifecycle and errors

Properties validate the live Core annotation before returning cached Core
information. `move_to`, `resize`, and `delete` delegate to Core and return
`None` on success.

After `delete()`, every property including `core`, every mutation, and a second
`delete()` on that wrapper raises `ClosedHandleError`. The same rule applies
after its document is closed.

Simple defines no new exception hierarchy:

- invalid enum object: `TypeError` before Core or XDWAPI;
- invalid geometry, size range, or resize condition: `ValueError`;
- invalid page number: `IndexError`;
- mutation on a read-only document: `ReadOnlyDocumentError`;
- deleted annotation or closed document: `ClosedHandleError`;
- XDWAPI failure: `XdwError`.

Standard, Custom, User, raw values, ctypes handles, and arbitrary XDW constants
are not re-exposed by Simple. Use the validated `core` escape hatch when those
features are required.
