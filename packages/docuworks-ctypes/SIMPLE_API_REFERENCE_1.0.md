# Simple API Reference 1.0

The normative behavior remains `SIMPLE_API_SPEC_0.7.0.md`. The complete
user-facing signatures, units, return values, errors, enumeration order, and
lifecycle rules are documented in `SIMPLE_API_REFERENCE_0.9.0.md` without
changes and are frozen for 1.x by `PUBLIC_API_1.0.json` and
`API_STABILITY_1.0.md`.

The supported entry point remains:

```python
from docuworks_ctypes.simple import open_xdw
```

Use Simple for ordinary document workflows, Core through the documented `core`
escape hatch for advanced attributes, and Raw only for direct XDWAPI ABI work.
