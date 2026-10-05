# Migration from 0.9.0 to 1.0.0

No source-code migration is required. Version 1.0.0 keeps the 0.9.0 Simple,
Core, Raw, Runtime Resolver, registry, unit, exception, save, and lifecycle
contracts unchanged.

Replace the installed local wheel and verify the version:

```powershell
py -m pip install --force-reinstall .\docuworks_ctypes-1.0.0-py3-none-any.whl
py -c "import docuworks_ctypes; print(docuworks_ctypes.__version__)"
```

The expected output is `1.0.0`. Applications using undocumented internals are
not covered by the 1.x compatibility guarantee.
