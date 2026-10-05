> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# GitHub Actions CI

`/.github/workflows/ci.yml` automates the DLL-free verification and publication audit described in `MAINTENANCE.md`.

## DLL-free tests

On every push and pull request, GitHub-hosted Windows runners test Python 3.11, 3.12, and 3.13.

The workflow installs `requirements/dev.txt` and `requirements/results.txt`, then runs the existing non-integration suites as separate processes:

```powershell
python -m pytest packages/docuworks-integrations/tests --ignore=packages/docuworks-integrations/tests/integration -p no:cacheprovider

Push-Location packages/docuworks-ctypes
python -m pytest tests --ignore=tests/integration -k "not installed_bundle_allows_companion_patch_difference" -p no:cacheprovider
Pop-Location
```

The excluded Core test is the host-specific DLL companion-patch check already documented in `MAINTENANCE.md`. Tests under `tests/integration` remain local/real-machine tests because they require DocuWorks and disposable XDW fixtures.

## Publication audit

The publication job uses Windows/Python 3.13 and performs these gates:

1. `python scripts/audit_publication.py` checks the tracked/source publication set.
2. `python -m build` creates wheel and sdist archives for both packages.
3. `twine check` validates distribution metadata/README rendering.
4. `python scripts/audit_distributions.py dist` requires exactly one wheel and one sdist for each package, and rejects unexpected files in `dist/`. It checks every archive member without extracting it: only source/text/metadata file types are allowed. Documents, images, model weights/configuration, SDK headers/binaries, credential files, links and unsafe paths are rejected. UTF-8 content is checked for private user paths, recognizable tokens/private keys, JSON credential fields and OCR result payloads. Files over 1 MB and archives with over 20 MB of uncompressed content are rejected. Error messages never echo matched content or archive member paths.
5. A fresh virtual environment installs only the built wheels, then runs `pip check`, imports both packages from outside the repository, and runs `python -m docuworks_integrations --help`.
6. The audited `dist/*` files are uploaded as a workflow artifact.

No PyPI upload or GitHub Release publication occurs automatically.

Every native command in a multi-command PowerShell step checks `$LASTEXITCODE` immediately. A failed install, build, dependency check or import therefore cannot be hidden by a later successful command. Publication-guard tests run before the audits, including synthetic forbidden wheel/sdist contents and failure injection into the actual workflow smoke block. These tests do not use real credentials, models or documents.

The content checks detect known patterns, not all possible sensitive information in arbitrary prose. Manual review remains necessary before sharing new source/data. The policy deliberately does not permit binary package assets; extending this requires an explicit policy and regression-test update.

## Manual run

The workflow includes `workflow_dispatch`, so it can also be started manually from the repository's **Actions** tab.
