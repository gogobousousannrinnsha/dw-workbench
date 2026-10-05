# Core Verification Complete

`docuworks-ctypes` Core verification formally completed with the 0.6.2 run
`20260831-210828-734`. Version 0.6.3 adopts that result as the frozen Core
verification baseline without changing Core, Raw, Runtime Resolver, registry,
or Simple behavior.

## Verified baseline

- Platform: Windows x64
- Python: 3.11
- Runtime: installed System32 XDWAPI 10.1.1
- Contract tests: 68 passed
- Real integration tests: 111 passed, 0 failed, 0 skipped
- Standard Attribute registry: 9 annotation types, 89 pairs
- Immediate and save/reopen persistence: 89/89
- Representative Viewer review: 9/9 annotation types
- Fixture originals: SHA-256 unchanged after testing

Formal status:

- `CONTRACT VERIFIED`
- `FULL PERSISTENCE VERIFIED`
- `FULL VIEWER VERIFIED`

Canonical evidence archive:

```text
integration-evidence-0.6.2-final-viewer.zip
SHA-256 3A96E0A5914970B4BFBAED0979D64FFF5917B50BF50642B495A88ED56B5607E2
```

The evidence scope is the environment above. It is not a blanket claim for
other DocuWorks, XDWAPI, Windows, architecture, or Python versions.

## Core change gate

Core is now a verified foundation. Changes are limited to defect corrections,
compatibility work, or behavior strictly required by the Simple facade.
Any Core behavior change requires:

1. all DLL-free contract tests;
2. all real integration tests with zero failure and zero skip;
3. immediate and save/reopen persistence for all 89 registry pairs;
4. unchanged SHA-256 for both source fixtures;
5. a complete, independently verified evidence manifest;
6. an explicit changelog entry, with a breaking release when the public
   contract changes.

Changes confined to Simple delegation do not require repeating all 89 Viewer
checks. A Core or rendering change must identify and repeat the affected Viewer
cases.

## Preserved contracts and limitation

- Standard, Custom, and User attributes remain separate systems.
- Generic Standard values use natural units; explicit raw methods expose XDW
  storage units.
- Custom DATE remains a raw signed 32-bit value.
- User zero-byte SET is accepted by XDWAPI 10.1.1, but the tested GET forms
  return `XDW_E_UNEXPECTED`. This is a known runtime limitation and is excluded
  from Full Persistence.
- Context manager exit closes but never implicitly saves.

Development after 0.6.3 is the Simple API productization phase described in
`SIMPLE_API_ROADMAP.md`.

## 1.0 stable confirmation

Version 1.0.0 re-ran 103 DLL-free contract/API snapshot tests and 117 real
integration tests, retained Standard Persistence 89/89, and changed only the
package version value from the verified 0.9.0 implementation. The change gate
above remains mandatory for all later Core changes.
