> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# 0.7.0.dev2：sdistの試験再現性と通常のpip導入確認

2026-09-12、Windows x64、Python 3.11.9で検証しました。
bf57d9bのViewer機能検証を維持したまま、配布検証の条件を補完する更新です。
変更はsdist収録設定、配布検証・CI、文書と証跡です。実行時パッケージ33ファイルは変更していません。
Core、既存CLI、公開Portableは変更せず、Viewerの再操作や新しいBATは不要です。

## 確認した結果

| 対象 | 結果 |
|---|---|
| 新しいsdistを展開した訂正・レビュー試験 | 99成功。補助ファイルを追加せず、収録済みconftest.pyを使用 |
| 収録ファイルの試験前後比較 | 全57ファイルが不変。Pythonが生成したキャッシュ5ファイルだけを別記録 |
| 新規venvへの通常のpip install | Core 1.0.0とIntegrations 0.7.0.dev2をローカルwheelから導入成功 |
| 新規venvのpip check・CLIヘルプ | 成功 |
| 通常のpipで導入したwheelの機能試験 | 130成功（訂正56、レビュー43、既存結果18、SDK実機13） |
| 新規venvによるViewer保存済み6ケースの読取り | 正常3件成功、異常3件を想定した処理で拒否 |
| 配布ガード・既存例の試験 | 65成功 |
| 配布物のメタデータ・内容監査 | CoreとIntegrationsの4アーカイブで成功 |

上記99件・130件・65件は失敗・エラー・skipなしです。
この補完試験をPython 3.10〜3.13の全環境で再実施したという意味ではありません。
既存の各Python版の確認範囲とPython 3.13でのSDK・Viewer検証は、[従来の記録](../REVIEW_XDW_VERIFICATION.md)を参照してください。

## 収録・試験方法

IntegrationsのMANIFEST.inでtests/conftest.pyを明示収録しました。実行時wheelにテスト用ファイルは追加していません。
配布物監査でもこのファイルの欠落をエラーにし、CIへ未加工sdistの検証を追加しました。
CI設定はローカルで確認していますが、push・リモートCI実行は今回行っていません。

sdistは通常の `python -m build --no-isolation` で作成し、そのsdistからwheelを作成しました。
ビルド用のbuild・setuptools・wheelは既存の開発環境を使用しています。
今回のPython 3.11では、一時フォルダー関数の差し替えや制限外実行を必要としませんでした。

配布sdistの試験に必要な外部依存はPython、pytest、jsonschema、およびCore 1.0.0です。
依存を用意した環境でsdistを展開し、展開先をカレントフォルダーにして次を実行できます。
元リポジトリからのファイル補完、GPU、Paddle、Pillow、DocuWorks DLLはこの99件には不要です。

```powershell
python -m pytest tests/test_corrections.py tests/test_review_xdw.py -q -p no:cacheprovider
```

ソースZIP内のscripts/verify_sdist.pyは、新しいフォルダーへの展開、展開先からのimport照合、
この99件の実行、収録ファイルのハッシュ不変確認を自動化します。
検証中のPythonキャッシュ生成は認めますが、収録ファイルの変更や補助ソースの追加は認めません。
検証用の作業フォルダーとJUnit・要約JSONは展開ソースの外へ出力します。

配布ガード65件は、ホストのpytest一時フォルダー制限に対応するため、既存のリポジトリfixtureを
テストプラグインとして指定して実行しました。この指定は配布sdistの99件には行っていません。

## 通常の導入確認

新しい環境を通常の `python -m venv` で作成し、その環境のpip 24.0で次の処理を行いました。
コマンド中のdist-folderは検証対象wheelのフォルダーを示すプレースホルダーです。

```powershell
python -m pip install --no-index --find-links dist-folder docuworks-ctypes==1.0.0 docuworks-integrations==0.7.0.dev2
python -m pip check
python -m docuworks_integrations --help
```

今回は個別インストーラーやtempfileの差し替えを使用していません。
新規環境での6ケース検証には、導入したCoreとIntegrationsだけを使用しました。
130件のpytest試験は試験依存を用意した別環境へ同じwheelを通常のpipで導入して実施しました。
標準のpip導入確認と、SDKを含む機能試験の環境を区別して記録しています。

## 成果物の識別

新しい成果物は `dist/ocr-review-0.7.0.dev2-sdist-reproducible` に保存します。
版番号は0.7.0.dev2のまま、revisionはsdist-reproducibleとし、最終コミットとSHA-256を併記します。
旧viewer-verified成果物、元bundle、Viewer保存済みファイルは保全します。
実文書・SDK・DLL・ローカル設定・訂正文は配布物に収録しません。

[検証要約](../evidence/review-xdw-0.7.0/sdist-reproducibility.json)、
[sdist 99件](../evidence/review-xdw-0.7.0/sdist-repro-99.xml)、
[wheel 130件](../evidence/review-xdw-0.7.0/sdist-repro-wheel.xml)、
[配布ガード65件](../evidence/review-xdw-0.7.0/sdist-repro-guards.xml)、
[配布物ハッシュ](../evidence/review-xdw-0.7.0/sdist-repro-distributions.json)を記録しています。
