# Simple Workflow Guide 0.8.0

The normative public API remains `SIMPLE_API_SPEC_0.7.0.md`. This guide covers
safe, repeatable document workflows using that contract.

## Safety model

Modification examples take two positional paths: an existing input XDW and a
different output XDW that must not exist. They copy the input with metadata,
open only the copy for update, and call `save()` explicitly. They reject a
missing input, a non-XDW suffix, the same resolved path, and an existing output
before XDWAPI is loaded. No example overwrites its input or output.

Read-only examples take one input path and never call `save()`.

## Examples

Run these after installing the wheel. Add `--dll-path` only to force a specific
runtime bundle and `--codepage` only when the document requires an ACP override.

```powershell
py .\examples\01_add_annotations.py blank.xdw created.xdw
py .\examples\02_list_annotations.py created.xdw
py .\examples\03_move_resize.py created.xdw moved.xdw
py .\examples\04_delete_annotations.py created.xdw deleted.xdw --type RECTANGLE
py .\examples\05_recursive_annotations.py created.xdw
py .\examples\06_use_core_escape_hatch.py created.xdw
```

`01_add_annotations.py` creates Text, Rectangle, Sticky, Ellipse, Straight
Line, Polygon, Marker, and Link on page 1. Sticky also creates a child Text.

`03_move_resize.py` deliberately selects the first Rectangle from the current
snapshot. `04_delete_annotations.py` selects the first top-level annotation of
the requested `AnnotationType`. After structural deletion, enumerate again;
do not reuse other wrappers from the old snapshot.

`05_recursive_annotations.py` prints the top-level snapshot and the flat
preorder snapshot. The recursive sequence places each parent immediately before
its descendants. Repeated enumeration creates new wrappers; identity and
equality across snapshots are not a selection contract.

`06_use_core_escape_hatch.py` demonstrates read-only access to validated Core
operations. Generic Standard, Custom, User, and raw operations remain Core
features and are not duplicated in Simple.

## Persistence workflow

The supported workflow is:

1. Copy the source XDW to a disposable output.
2. Open the output with `writable=True`.
3. Enumerate or create annotations and retain wrappers only while the document
   remains open and no structural deletion invalidates the snapshot.
4. Move, resize, or delete through `SimpleAnnotation`.
5. Call `document.save()` explicitly.
6. Close and reopen the output, then enumerate again to verify persisted state.

Leaving a context without `save()` closes the document and must not be treated
as persistence. A read-only document rejects mutations with
`ReadOnlyDocumentError`. Deleted annotations and annotations belonging to a
closed document raise `ClosedHandleError`.

## Product boundary

0.8.0 adds no Simple public symbols. There is no date-stamp creator, search
API, stable annotation identifier, wrapper equality contract, arbitrary RGB
input, implicit save, or Simple-level generic attribute API.
