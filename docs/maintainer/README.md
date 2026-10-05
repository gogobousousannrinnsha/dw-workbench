# 保守・配布

[v0.6.1 Pre-releaseの構成・更新内容・検証方針](RELEASE_v0.6.1.md)（Core 1.0.1 / Integrations 0.12.0）

[Reviewed取り込み2.0の受け入れ条件と確認範囲](REVIEWED_IMPORT_V2_ACCEPTANCE.md)（Integrations 0.9.0開発候補）

[v0.4.0の構成・互換性・公開検証条件](RELEASE_v0.4.0.md)

以下の整理・0.8.0.dev1・v0.4.0検証記録は、その時点の履歴です。今回の操作と確認範囲はv0.6.1の構成書とReleaseの最終検証報告を参照してください。

[今回の整理に対する検証記録](VERIFICATION.md)

[PaddleOCR空文字の再現・修正検証](PADDLE_BLANK_TEXT.md)

[白紙Review・Reviewed Result 0.8.0.dev1の実装検証](REVIEWED_RESULT_VERIFICATION.md)

[白紙Review XDW・Reviewed Resultの設計調査](../research/reviewed-result-20260915/README.md)（2026-09-15、未実装の提案とSDK検証結果）

## 構造と変更前後

| 領域 | 管理元・責任 | 整理による変更 |
|---|---|---|
| Core | packages/docuworks-ctypes | 実装・APIは変更なし |
| OCR・結果・訂正 | packages/docuworks-integrations | プレビューを内部共通部品へ移設。workflow互換口は維持 |
| 文書処理 | batchはOCR専用、jobsは派生出力付き | 統合しない。保存構成と返却型の差を明記 |
| 自作Portableファイル | portableとlayout.json | 既存9本のBAT・環境確認・起動スクリプトをソース管理 |
| 公開向け原稿 | portable/templates | READMEを原稿から生成。説明文の二重管理を終了 |
| 第三者資産 | ハッシュ固定した基準ZIP | Python・依存ライブラリ・モデル・第三者通知を保持 |
| 公開ソース | 開発ソースからexport | 旧公開版のBAT・文書を暗黙補充しない |

公開版は別実装ではありません。公開変換では自作部分のMIT条件、非公開情報の除去、第三者条件を維持し、開発・公開・導入済みwheelの機能本体をハッシュ比較します。

## ローカル検証と候補作成

Python 3.10～3.13でIntegrationsとCoreのDLL不要試験、配布物の監査を行います。SDK・GPUはPython 3.13で別途実行します。Core 1.0.1での例外保持などの修正と確認範囲は[対応台帳](CORE_1.0.1_ISSUES.md)を参照してください。

```powershell
python -m pytest packages/docuworks-integrations/tests --ignore=packages/docuworks-integrations/tests/integration -p no:cacheprovider
python -m pytest scripts/tests -p no:cacheprovider
python scripts/audit_publication.py
python scripts/export_public_source.py --repo . --baseline-public <既存公開ソース> --output <新規公開候補> --release-version v0.6.1
python -m build <新規公開候補>/packages/docuworks-integrations --sdist --outdir <新規配布先>
```

Coreの既存検証済み公開wheelを保持し、Integrationsはsdistを新規展開してwheelを作ります。通常pipで独立環境へ導入し、pip check・リポジトリ外import・未加工sdist試験を確認します。旧配布物へ上書きしません。具体的なPortable作成引数はscripts/build_portable_candidate.py --helpを参照してください。基準ZIPの期待SHA-256、Core/Integrationsのwheel、公開候補のportable、公開候補source、新規出力先を明示します。

layout.jsonに宣言した自作ファイルが不足すれば開始前に拒否します。起動ファイルを旧ZIPから補完しません。修復BATの版は対象wheelから決定します。配布READMEはportable/templatesの原稿から生成します。生成物reference/distribution-files.jsonは自作ソース・wheel・生成・基準ZIPの由来を区別します（一覧自身を除く）。

文書は開発側を正本とし、公開候補へ一式コピーします。PortableにはAPI文書が参照するパッケージ文書も含めます。実文書・DLL/SDK・OCR結果・ローカル設定を公開ソースに含めません。元runとViewer編集ファイルは読取り専用の検証入力として扱います。

## 記録と公開の境界

今回の配布構成はv0.6.1 / Integrations 0.12.0 / Core 1.0.1です。公開前の候補はコミットID・SHA-256・未公開の表示で区別します。過去の0.7.0/v0.3.0整理時の証拠は履歴として保持します。

候補検証、GitHubへのpush・main統合、Release公開は別工程です。公開済みタグ・23添付物・凍結証跡を変更しません。CIの試験・ビルド・監査とartifact保管を区別し、アップロード失敗を試験成功だけで隠しません。過去の容量制限例外を将来の公開へ自動適用しません。
