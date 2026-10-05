> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# OCR文字訂正基盤の検証記録

検証日: 2026-09-12。対象: Integrations **0.7.0.dev1**、開発版ベース **57cf72aec7d5b315c825104fee1f81e604c19b26**。
Windows x64上で、合成bundleを使って実行しました。実原稿・GPU・DocuWorks DLL・Viewerの試験は今回の対象外です。

## 実行結果

| 対象 | 結果 | 記録 |
|---|---|---|
| Python 3.10、新しい訂正API | 56成功 | [JUnit](../evidence/corrections-0.7.0/results310.xml) |
| Python 3.11、Integrations回帰 | 183成功 | [JUnit](../evidence/corrections-0.7.0/results311.xml) |
| Python 3.12、Integrations回帰 | 183成功 | [JUnit](../evidence/corrections-0.7.0/results312.xml) |
| Python 3.13、Integrations回帰 | 183成功 | [JUnit](../evidence/corrections-0.7.0/results313.xml) |
| Core既存試験（Python 3.13） | 102成功 | [JUnit](../evidence/corrections-0.7.0/core313.xml) |
| 配布ガード・使用例 | 58成功 | [JUnit](../evidence/corrections-0.7.0/audit-tests.xml) |
| 導入済みwheelの訂正API | 56成功 | [JUnit](../evidence/corrections-0.7.0/wheel-tests.xml) |
| 展開したsdistの訂正API | 56成功 | [JUnit](../evidence/corrections-0.7.0/sdist-tests.xml) |

Coreでは既存CIと同じく実機試験とホスト固有の `installed_bundle_allows_companion_patch_difference` を除外しました。
表の試験はすべて失敗・エラー・skip 0件です。既存のViewer編集制約が解消したことを示す結果ではありません。
GitHub Actionsには3.10専用ジョブを追加しましたが、リモートへのpushやActions実行は行っていません。

## 検証した動作

- 元bundleの全ファイルのSHA-256不変、文字だけの変更、座標・順序・元信頼度の保持。
- Canonical 1.0/1.1、旧run、複数ページ、空ページ、空修正セット、移動後・外部原本なしの利用。
- 不正形式、別run、ハッシュ不一致、重複ID、不明ID、before_text不一致、空白・無変更訂正の拒否。
- 日本語・改行・引用符・前後空白の保持、既存JSONLが元文字を出力する互換性。
- メモリ上のbbox等の改変、読込後のファイル変更、出力途中の入力変更の検出。
- 部分書込み・fsync・確定失敗、同時作成された出力の保全、掃除失敗時の元例外保持。
- 修正JSON・利用用JSONLのSchema検証と配布ガード。実行例はリポジトリ側の試験で検証。

## 配布物

`python -m build --no-isolation` でsdistを作成し、そのsdistからwheelをビルドしました。
Integrations wheelのパッケージ内部31ファイルは、作業ソースの同名ファイルと全バイト一致しています。
新モジュールと2つのJSON Schemaの同梱を確認しました。

Core 1.0.0とIntegrations 0.7.0.dev1のwheel・sdist計4アーカイブで `twine check` と内容監査が成功しました。
Coreのソース変更はありません。Coreの再ビルド品はこの開発版の検証用依存であり、新しいCoreリリースではありません。

別venvへwheelを導入し、`pip check` 成功を確認しました。リポジトリ外の実行例で、
元run作成→訂正保存→再読込→適用→JSONL出力を実行し、Core・Pillow・Paddle・NumPy・jsonschemaのimportがないことを確認しました。
さらに、リポジトリ外へ複製した訂正テストを導入済みwheelに対して実行し、展開したsdistでも同じテストを実行しました。

配布用のSHA-256一覧は [配布物ハッシュ](../evidence/corrections-0.7.0/distributions.json) にあります。
完全な開発ソース、仕様、使用例、検証記録は別途作成するソースZIPにも含めます。
`source-manifest.json` は自身を除く配布ソースのサイズとハッシュです。

## 環境由来の再実行

制限環境ではGitの子プロセスとPython一時ディレクトリーのACLで失敗したため、
clone、ビルド、既存Core試験、配布物の読込みは通常権限で再実行しました。セキュリティ設定は変更していません。
Python 3.10付属pipの証明書問題には、Python 3.13でTLS検証して取得したwheelからのオフライン導入で対応しました。
最終結果には再実行して成功したものを記録しています。
