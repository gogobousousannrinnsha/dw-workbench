> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# 開発・再配布・GitHub反映

## ローカル検証

Windows x64 / Python 3.13。リポジトリルートから実行します。

```powershell
py -3.13 -m venv .venv-dev
.\.venv-dev\Scripts\python.exe -m pip install -r requirements/dev.txt
.\.venv-dev\Scripts\python.exe -m pip install -r requirements/results.txt
$env:DOCUWORKS_INTEGRATIONS_TEST_TMP = Join-Path (Get-Location) 'work/test-temp'
.\.venv-dev\Scripts\python.exe -m pytest packages/docuworks-integrations/tests --ignore=packages/docuworks-integrations/tests/integration -p no:cacheprovider
Push-Location packages/docuworks-ctypes
..\..\.venv-dev\Scripts\python.exe -m pytest tests --ignore=tests/integration -k 'not installed_bundle_allows_companion_patch_difference' -p no:cacheprovider
Pop-Location
```

CoreとIntegrationsのtestsは別プロセスで実行します。Coreの1試験はホスト固有のDLLパッチ版差を要求するため上では除外しています。実機試験は[Coreの既存手順](../../packages/docuworks-ctypes/INTEGRATION_TEST_GUIDE.md)に従い、利用者が用意した使い捨て文書コピーと明示DLLで別に実行します。Core実機用スクリプトはローカルにパス付き証拠を生成するため、そのままGitへ追加しません。

## wheel作成

```powershell
.\.venv-dev\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --wheel-dir dist packages/docuworks-ctypes packages/docuworks-integrations
.\.venv-dev\Scripts\python.exe -m pip check
```

ビルドしたwheelはテスト用の新規venvへ両方インストールし、リポジトリ外のカレントディレクトリからimportとCLIを確認します。README整理によりwheelのMETADATAやzip hashは元wheelと変わり得ます。本体は `docs/evidence/import-provenance.json` の照合を基準とし、再ビルド品を元配布物と同じhashとは表示しません。`dist/` はGitに追加せず、配布時は個別Release assetとして扱います。

## 公開前チェックと取り込み

```powershell
py -3.13 scripts/audit_publication.py
git status --short
git diff --check
git diff --cached --stat
```

監査はテキストソースの拡張子・サイズ、個人ホームパス・代表的な資格情報、相対Markdownリンクを検査します。汎用の秘密検出を完全に保証するものではありません。`.gitignore` は既存追跡ファイルや過去履歴には効きません。リモート取得後は `git ls-files` で追跡対象も確認し、差分をレビューしてください。

`source-manifest.json` は自身と `.git/` を除く初期ソースのサイズ・SHA-256一覧です。`.gitattributes` で改行自動変換を無効にし、元wheelとのバイト一致を保ちます。変更を配布する際はmanifestを再生成します。取り込み元にある2ファイルの末尾空行は保持しています。初期取り込みの `git diff --check` で `capabilities.py` と `test_annotation_refresh.py` に出る末尾空行の指摘はその継承分です。

集約先は新規Privateリポジトリ `gogobousousannrinnsha/dw-ocr` です。今後はbranchを作って変更し、差分と試験結果を確認して通常pushします。Core/IntegrationsのAPI変更はそれぞれ版を更新してください。別リポジトリの履歴・既存ファイルはこの新規リポジトリへ取り込んでいません。
