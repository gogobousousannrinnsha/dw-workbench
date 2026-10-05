# Reviewed取り込み2.0: 受け入れ条件と確認範囲

対象はIntegrations 0.9.0開発候補です。2026年9月19日、開発mainのf78b360aを基に、[確定仕様](../specs/reviewed-import-1.0.md)の実装を検証しました。Coreの実装は変更していません。

## 条件別の証拠

自動試験は[2.0の単体試験](../../packages/docuworks-integrations/tests/test_reviewed_v2.py)、実SDK試験は[2.0の保存・再読込試験](../../packages/docuworks-integrations/tests/integration/test_reviewed_v2_roundtrip.py)です。従来の[1.0単体試験](../../packages/docuworks-integrations/tests/test_reviewed.py)と[1.0実SDK試験](../../packages/docuworks-integrations/tests/integration/test_reviewed_roundtrip.py)も実行しました。

| 条件 | 今回の確認 |
|---|---|
| A01 文書識別 | 一致・欠落・不一致・不正な属性を自動試験。実SDKでも識別属性の欠落を拒否 |
| A02 現在の本文と再取り込み | 編集・追加・移動・削除・別結果生成を試験。実SDKで全削除と文字・配置の保持 |
| A03 複数参照の明示設定 | 複数／空参照を設定し、保存・再読込・取り込み。古いハッシュ・未知の領域・重複対象を拒否 |
| A04 共有・空参照 | 同じ参照を共有する複数項目と空参照を正常扱い。旧duplicateの共通参照取得 |
| A05 不正・異なる由来・一部不正 | 本文・有効部分・元属性・診断を保持。実SDKでもpartialとforeignを確認 |
| A06 付箋メモと見た目の重なり | 実SDKの付箋メモだけを除外し通常テキストを保持。固定XDWのハッシュ不変。入れ子付箋の所有関係は模擬構造でも試験 |
| A07 未対応構造 | 実SDKのグループ内文字を文書単位で拒否 |
| A08 空文字・本文0件 | 空文字・空白のみを保持＋診断。全削除時もページと空のJSONLを保存 |
| A09 文字列・実測配置 | Unicode・改行・空白・移動・文字回転・縦書きを実SDKで保存・再読込 |
| A10 ID照合と再読込 | 全実ページを記録し、検証範囲を維持。追加・削除・回転の実SDK試験は取り込み時の欠落防止の検証であり、ページ編集の運用対応を認定しない |
| A11 旧形式 | 旧単体試験と旧実SDK試験を実行。既定strictは1.0、新経路は明示選択 |
| A12 失敗と不変性 | SDK失敗・入力／Session変更・保存／確定失敗・破損・再ハッシュ後の意味的不整合を拒否。入力・Canonical・Session・前結果の不変性を確認 |

## 自動試験と配布パッケージ

Python 3.13.15でIntegrationsと保守スクリプト541件、Core136件、計677件が成功しました。Coreは既存CIと同じ対象で、installed_bundle_allows_companion_patch_differenceは除外しています。新規Schemaの検証、Portableの表示・新方式の選択も含みます。

両パッケージのwheel/sdist計4ファイルを生成し、メタデータと同梱内容の監査が成功しました。未変更のIntegrations sdistから314件を再実行し、展開したソースの既存ファイルが変わらないことを確認しました。リポジトリ外の独立Pythonへwheelだけを導入し、新旧取り込み、複数参照設定、Portable取り込みスクリプト、4つのSchemaの同梱を確認しました。GPU・モデルを含む完全なPortable配布物の再構築は今回の対象外です。

## 実SDK試験の環境と限界

Python 3.13.15、Windows x64、DocuWorks API 10.1.1（DLLファイル版10.1.0.17）を使用しました。合成の3ページ文書をケースごとに複製し、既存24件＋新規13件、計37件が成功しました。新規13件はmulti、sticky、overlap、group、partial、foreign、empty、all-delete、geometry、page-extra、page-remove、page-rotate、doc-idです。試験中のSessionは0.9.0.dev1表記で生成し、0.9.0表記に揃えたwheelでも取り込みと参照設定を確認しています。

Viewerの手動操作、利用者の実文書、DocuWorks 9.1環境は今回未確認です。過去の旧版Viewer確認を新しい複数参照・付箋除外の操作確認へ流用しません。専用GUI、編集履歴の取得、自動参照統合、Structured Result・Excel・マーカー出力はこの変更に含みません。

## 再実行

DLL不要の試験は通常のCIで実行します。実SDK試験はDOCUWORKS_REVIEWED_DLLに対象DLL、DOCUWORKS_INTEGRATIONS_TEST_TMPに新規の書込み可能な試験領域を設定し、両版のintegration/test_reviewed*_roundtrip.pyを実行してください。合成文書と出力は機密文書を含まない独立領域へ生成します。

配布時は4つの2.0 Schema、形式文書、版情報、Portableの明示的なidentity選択を確認します。公開版への反映・リリース操作は別工程です。
