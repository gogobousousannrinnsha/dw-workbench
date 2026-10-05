> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# 確認用XDW 0.7.0.dev2 検証記録

2026-09-12、Windows x64で検証しました。比較基準は `fd9e8a4`、Coreは1.0.0です。
**SDK往復検証済み／Viewer操作・別名保存は利用者確認済み、別名保存後6ファイルの取り込みも検証済み**。
実文書、原OCR内容、SDK、DLLは配布物に含めません。

## 試験結果

| 対象 | 結果 | 記録 |
|---|---|---|
| Python 3.10：訂正56件＋レビュー連携43件 | 99成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-3.10.xml) |
| Python 3.11：Integrations回帰 | 226成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-3.11.xml) |
| Python 3.12：Integrations回帰 | 226成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-3.12.xml) |
| Python 3.13：Integrations回帰 | 226成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-3.13.xml) |
| SDK実機：Python 3.13 | 13成功 | [JUnit](../evidence/review-xdw-0.7.0/review-sdk.xml) |
| Core既存試験：Python 3.13 | 102成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-core.xml) |
| 配布ガード・実行例 | 63成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-audit.xml) |
| 導入済みwheel：SDK13件＋訂正・レビュー99件＋既存結果18件 | 130成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-wheel.xml) |
| 展開sdist：訂正・レビュー連携 | 99成功 | [JUnit](../evidence/review-xdw-0.7.0/dev2-sdist.xml) |

表の試験は失敗・エラー・skipすべて0件です。Coreは既存CIと同じく実機試験と
ホスト固有の `installed_bundle_allows_companion_patch_difference` を除外しています。
wheel試験の独立フォルダーでは、pytestのintegrationマーカー未登録警告が1件ありました。試験自体は実行され成功しています。
Python 3.10でライブラリ全体・実DLL往復が検証済みという意味ではありません。
GitHub Actionsの設定は更新しましたが、push・リモートCI実行・公開リリースは行っていません。

## 実機で確認したこと

既存検証runの3ページ目・1領域を用い、確認XDWの1ページ目への対応を検証しました。
原本コピーからのページ取出し、12pt・赤字テキストの追加、識別属性の保存・再読込が成功しました。
元文字・初期位置・ページ寸法を照合し、SDKで文字と表示位置を変えて別ファイルへ保存した後も、
元の領域IDで取り込めました。訂正保存・適用・JSONL出力には既存の修正APIを使用しています。

次のケースを実SDKで確認しました。

- 正常訂正＋移動、未編集、空白訂正の既存基盤による拒否。
- 対象削除、識別属性削除・破損、識別付き複製、識別なし複製、対象種類変更、ページ追加の拒否。
- 同じrunの別確認セット、異なるrunとの組合せの拒否。
- 既存テキストと他アプリ用属性の保持、元ページに予約属性がある場合の生成拒否。
- 全ケースで元bundleと生成直後の確認セットのファイルハッシュが不変。
- 修正後も元のページ・領域順・座標・OCR信頼度を維持。

書込み・確定失敗、同時出力作成、読取り中の入力変更、対応JSONの変更、異常なSDK応答の伝播はDLL不要試験で検証しました。
既存の訂正基盤56件も維持しています。

実行環境はPython **3.13.15**、XDWAPI申告版 **10.1.1**、DLLファイル版 **10.1.0.17**、
導入製品版 **10.1.1**です。バイナリハッシュ等は [実機要約](../evidence/review-xdw-0.7.0/runtime.json) に保存しています。
任意データ属性が存在しない場合、初回サイズ問合せは `XDW_E_INVALIDARG` を返しました。
この応答だけを属性なしと扱い、データ取得時の同じエラーや他のエラーは伝えることを試験しました。

## 配布物の検証

sdistを作成し、そのsdistからwheelをビルドしました。
wheel内のパッケージ33ファイルはソースと全バイト一致し、新モジュールとSchemaを含みます。
Core 1.0.0の検証用配布物と合わせた4アーカイブで、メタデータ検査と内容監査が成功しました。
Coreのソースには変更を加えていません。

新規venvにwheelを導入して `pip check` が成功しました。リポジトリ外からSDK往復とJSONL出力を行い、
Pillow、Paddle、NumPy、OpenCV、pytest、jsonschemaをimportしていないことも確認しました。
別途、導入済みwheelを対象とする130件と、展開したsdistを対象とする99件を実行しました。
配布物の識別は [ハッシュ一覧](../evidence/review-xdw-0.7.0/distributions.json) を参照してください。

## 再実行と残る確認

DLL不要試験は既存のCIと同じ手順です。実機試験は次の環境変数を設定して実行します。

```powershell
$env:DOCUWORKS_REVIEW_RUN = '<既存検証runのパス>'
$env:DOCUWORKS_REVIEW_DLL = '<導入済みDocuWorksのxdwapi.dll>'
$env:DOCUWORKS_REVIEW_REGION = 'p0003-r000001'
python -m pytest packages/docuworks-integrations/tests/integration/test_review_xdw_roundtrip.py -q
```

この実機テストは元の3ページ目に対象領域がある検証run用です。入力は読み取り専用で扱い、派生物はテスト用フォルダーへ作ります。
継続確認用の実行例は [use_review_xdw.py](../../examples/use_review_xdw.py) です。
ローカルの `work/review-sdk-demo` には確認XDW、SDK編集後XDW、訂正JSON、JSONL、ハッシュ記録を残しました。配布用ソースには含めません。

Viewer操作と保存後の検証結果は以下に記録します。
[Viewer確認手順](../REVIEW_XDW_0.7.0.md#viewer確認手順) は再確認にも利用できます。
自動試験の成功を白紙型・複数領域への対応済みとは扱いません。

## Viewer確認の追記（2026-09-12）

利用者から「Viewer確認完了問題なし」との報告を受けました。表示・編集などの画面上の
確認は利用者報告に基づき、以下のファイル検証とは区別します。
導入済み0.7.0.dev2 wheelとPython 3.13で、Viewer操作後のファイルを読み取り専用で再検証しました。

| ケース | 保存後ファイルから確認した結果 |
|---|---|
| 文字編集 | 任意データ属性を保持。実際の訂正文を既存修正基盤で保存・適用し、JSONLへ完全一致で出力 |
| 文字移動 | 表示位置が変わっても同じ領域を識別。文字変更なしとして取り込み、元OCR座標を維持 |
| 未変更 | 未変更として取り込み、空修正セットの保存・適用・JSONL出力に成功 |
| コピー | 識別属性付き注釈が2個になり、取り込みを拒否 |
| 削除 | 対象注釈が0個になり、取り込みを拒否 |
| 空白 | 全角・半角空白だけの文字を取得し、既存修正基盤が保存を拒否。訂正ファイルは残らない |

正常3ケースで元領域のページ・順序・座標・信頼度など文字以外の全フィールドと、
JSONLの修正セットID・ハッシュを照合しました。元bundleの全ファイルのハッシュは準備時と一致し、
今回の読取り検証中も入力ファイルは不変でした。

初回は各ケースの `input.xdw` を検証しました。その後、利用者から「別名保存  できました」と
報告を受け、6ケースすべての `saved.xdw` が存在することを確認しました。
これらの別名保存後ファイルを対象に検証を再実行し、正常3ケースの訂正保存・適用・JSONL出力と、
異常3ケースの拒否がすべて想定どおりでした。元bundleは準備時から不変で、再検証中も
入力・既存の検証成果物は不変でした。これにより別名保存の確認待ちは解消しました。
文字編集ケースは実際に保存された非空白の訂正文をそのまま用いて検証しています。

機械検証の要約は [Viewer保存後の検証要約](../evidence/review-xdw-0.7.0/viewer-post-save.json) に保存しています。
実文書・訂正文を含む詳細結果とJSONLはローカルの
`work/viewer-check-20260912-194756/verification-20260912-195745` に保存し、配布物に含めません。
初回の検証結果も `verification-20260912-195438` に保持しています。
この時点の追記では既存のwheel・sdist・ソースZIPを変更していません。後続の成果物確定は以下に記録します。

## Viewer確認後の開発成果物確定

実装基準は `329512b` です。Viewer確認結果、トップ／パッケージREADME、API仕様を整合させ、
0.7.0.dev2の文書・証跡更新として固定しました。最終コミットは新しい成果物のartifact-manifest.jsonに記録します。
Core・Integrationsのパッケージ実装、公開API、既存CLI、公開Portableは変更していません。
ユーザーの希望に従って新しいBATは追加せず、担当側で作成済みdocuworks-ctypes 1.0.0を用いて検証しました。
ユーザーによるコード実行やViewer操作の再実施は不要です。

| 対象 | 結果 | 証跡 |
|---|---|---|
| 新しいwheelを独立環境へ導入：訂正56＋レビュー43＋既存結果18＋SDK実機13 | 130成功、失敗・エラー・skipなし | [JUnit](../evidence/review-xdw-0.7.0/viewer-final-wheel.xml) |
| bf57d9bのsdist（リポジトリのconftest.pyを補完） | 条件付き99成功、失敗・エラー・skipなし | [JUnit](../evidence/review-xdw-0.7.0/viewer-final-sdist.xml) |
| 新しいwheelとCoreで別名保存済みXDWを再読込 | 正常3件成功、異常3件を想定した責任範囲で拒否 | [要約](../evidence/review-xdw-0.7.0/viewer-final.json) |
| Core／Integrationsのwheel・sdist | メタデータと内容監査に成功 | [更新後ハッシュ](../evidence/review-xdw-0.7.0/viewer-final-distributions.json) |

今回の実行環境はPython 3.13.15です。上記130件には、独立した試験フォルダーでのintegrationマーカー未登録警告が1件あります。
sdistにはWindows用テスト一時フォルダーfixtureのconftest.pyが収録されないため、試験時だけリポジトリの同ファイルを補いました。
パッケージ本体や配布アーカイブは、この試験用補助の追加では変更していません。
Python 3.10〜3.13の既存検証範囲は冒頭の表のとおりで、3.10のライブラリ全体を検証済みとは扱いません。

このホストではビルドフロントエンドの一時フォルダー作成後にアクセス拒否が発生したため、
同じsetuptoolsのビルド基盤を直接呼び出してsdistを作成し、その展開ソースからwheelを作成しました。
独立環境へのpip導入では、作業フォルダーのアクセス権を継承する一時ディレクトリをその処理内で使用しました。
端末のセキュリティ設定・ユーザーのPython環境・元文書は変更していません。

新しい配布物はローカルの `dist/ocr-review-0.7.0.dev2-viewer-verified` に保存します。
確認前の `dist/ocr-review-0.7.0.dev2` は保全し、バージョンは同じでも別の文書・証跡更新であることを
成果物一覧のコミットとSHA-256で識別します。旧ハッシュ記録も保持しています。
ソースZIPには更新済み文書・証跡・source-manifest.jsonを含め、実文書・ローカル設定・訂正文は含めません。
公開用のライセンス変換、push、公開リリースは行っていません。

利用者が読む日本語の確認結果と生成済みJSONLは、ローカルの
`work/viewer-check-20260912-194756/results/20260912-202207-a8cd050b` に保存しています。
元bundleは準備時のハッシュを維持し、今回の検証中も入力・既存の出力は不変でした。

## 配布検証条件の補完

上記bf57d9bのsdist試験は補助ファイル追加を伴う結果であり、sdistをそのまま展開した試験とは区別します。
同コミットのwheel導入ではpip自体を呼び出していましたが、一時フォルダー作成処理の差し替えを伴うため、
通常のpipコマンドによる導入確認とは区別します。

後続の文書・配布設定更新では、conftest.pyをsdistへ収録しました。新しいsdistを未加工で展開して99件成功し、
通常のpipコマンドによる新規環境への導入とpip checkも成功しています。
この更新の識別子は **0.7.0.dev2 / sdist-reproducible / artifact-manifest.jsonのコミットとSHA-256** です。
詳細な条件・再現手順・証跡は[配布検証の補完記録](../SDIST_REPRODUCIBILITY_0.7.0.md)を参照してください。
従来のviewer-verified成果物とその条件付き試験記録は履歴として保管しています。
