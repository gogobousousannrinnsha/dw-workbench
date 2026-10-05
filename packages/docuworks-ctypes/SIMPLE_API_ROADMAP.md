# Simple API Productization Roadmap

Core verification is complete. New product-facing work starts at 0.7.0 and
must keep the layer boundary `Simple -> Core -> Raw -> XDWAPI`.

## Fixed principles

- Public geometry uses mm and font sizes use pt.
- Page numbers are 1-based; `SimpleDocument.page()` defaults to page 1.
- `save()` is explicit. Context manager exit closes without saving.
- Validation, encoding, unit conversion, and XDWAPI calls remain in Core.
- Simple does not expose ctypes, handles, raw storage units, or XDW constants.
- Advanced users can leave the facade through a documented `core` property.

## 0.7.0 public-surface stabilization

- Completed: retained `open_xdw`, `SimpleDocument`, `SimplePage`, and the eight verified
  creation methods: `text`, `rectangle`, `sticky`, `ellipse`, `line`,
  `polygon`, `marker`, and `link`.
- Completed: introduced `SimpleAnnotation` as a thin wrapper with type, position, size,
  `move_to`, `resize`, `delete`, and `core`.
- Completed: added existing-annotation enumeration through Simple and return
  `SimpleAnnotation` from creation methods. This return-type change is breaking
  and belongs only in 0.7.0.
- Unsupported resize operations continue through existing Core capability checks;
  do not duplicate capability state in Simple.
- `page.date_stamp()` is not provided. New date-stamp creation is outside the Simple
  1.0 scope; existing date-stamp work remains available through Core.

The normative 0.7.0 contract is `SIMPLE_API_SPEC_0.7.0.md`.

## Later milestones

- 0.8.0 completed: added safe copy-first examples and verified the full Simple
  workflow from creation and enumeration through edit/delete, explicit save,
  close, reopen, and re-enumeration. The 0.7.0 public surface is unchanged.
- 0.9.0 release candidate completed: Quick Start/API documentation, fresh-install checks,
  Python 3.10–3.13/runtime compatibility matrix, consolidated limitations,
  distribution audit, and release policy. The public surface remains unchanged.
- 1.0.0 completed: froze Simple/Core public names, geometry types, enums,
  exceptions, save semantics, and compatibility policy in a machine-readable
  public API snapshot.

OCR, OpenCV, AI, AutoCAD integration, implicit save, and broad wrapping of all
XDWAPI exports are explicitly outside the Simple 1.0 scope.
