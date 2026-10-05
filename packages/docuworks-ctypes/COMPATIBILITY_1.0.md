# Compatibility Matrix 1.0

## Supported platform

- Windows x64
- CPython 3.10, 3.11, 3.12, and 3.13 (64-bit)
- A compatible user-supplied DocuWorks installation and XDWAPI runtime

The package contains no DocuWorks binaries, SDK files, specification files, or
fixtures.

## Required release verification

| Python | Fresh wheel | Fresh source | Contract/API snapshot | Simple persistence smoke | Full integration |
|---|---|---|---|---|---|
| 3.10 | Required | Required | Required | Required | — |
| 3.11 | Required | Required | Required | Required | 117-case baseline |
| 3.12 | Required | Required | Required | Required | — |
| 3.13 | Required | Required | Required | Required | — |

Exact patch versions and results are recorded in the final 1.0 evidence. A
missing interpreter, failure, or skip is not compatibility success.

## Runtime scope

- Installed System32 XDWAPI 10.1.1: full verified baseline.
- SDK 10.0 x64 bundle: static/open/Simple persistence smoke verification.
- SDK 9.1.7 x64 bundle: ABI verified; runtime compatibility remains conditional
  because the current product environment returns `XDW_E_NOT_INSTALLED`.

Claims do not automatically generalize beyond the recorded environment.
