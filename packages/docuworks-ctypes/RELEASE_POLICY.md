# Release and Compatibility Policy

## 1.0 stable line

1.0.0 promotes the verified 0.9 contract without behavioral changes. The
machine-readable stability boundary is `PUBLIC_API_1.0.json`.

## 0.9 Release Candidate history

0.9.0 freezes the 0.7.0 Simple public contract while installation,
documentation, Python compatibility, runtime compatibility, and distribution
contents are verified. No new Simple feature is accepted into the RC unless it
is required to correct a demonstrated defect.

## 1.0 and later

- `1.0.x`: backward-compatible bug, security, packaging, and documentation fixes.
- `1.x`: backward-compatible additions. Existing signatures and behavior remain valid.
- `2.0`: intentional breaking changes with migration documentation.

Removing or renaming public symbols, changing units, accepting different enum
contracts, changing save behavior, changing exception types, or changing
enumeration/lifecycle semantics requires a new major version after 1.0.

Core changes remain subject to the gate in `CORE_VERIFICATION_COMPLETE.md`:
full contract, real integration, 89-pair persistence, fixture immutability,
package equivalence, and evidence manifest verification.

## Supported scope

Support claims always name the Python, Windows architecture, DocuWorks, and
XDWAPI versions actually tested. ABI validation, smoke verification, full
persistence, and Viewer verification are reported separately.
