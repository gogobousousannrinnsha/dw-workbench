# API Stability Policy 1.0

`docuworks-ctypes 1.0.0` freezes the public contract proven by 0.9.0.

## Stable through 1.x

- Top-level names listed in `PUBLIC_API_1.0.json`.
- `docuworks_ctypes.simple` exports and recorded signatures.
- Public enum member names and integer values.
- Natural units: millimetres for geometry and points for font sizes.
- One-based page numbers, explicit `save()`, and no implicit context-manager save.
- Simple enumeration order, snapshot semantics, wrapper invalidation, and exception types.
- Standard, Custom, and User attribute separation and the documented Core raw contracts.

Backward-compatible additions and defect corrections may be released in 1.x.
Removal, renaming, unit changes, save/lifecycle changes, enum contract changes, or
exception changes require 2.0 and migration documentation.

## Deliberately outside 1.0

New date-stamp creation, persistent annotation IDs, implicit save, XDW page
rendering, OCR, OpenCV, CAD, AI, and database integration are not part of this
package. Those integrations belong to a separately versioned adapter layer.

## Machine check

Run `py -3.11 generate_public_api.py --output candidate.json` and compare the
result byte-for-byte with `PUBLIC_API_1.0.json`. Contract tests perform this
comparison automatically.
