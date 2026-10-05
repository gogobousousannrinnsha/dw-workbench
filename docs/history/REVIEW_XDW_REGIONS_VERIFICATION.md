> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# 複数領域XDW 0.7.0.dev3 検証記録

基準は **0.7.0.dev2／8a0671a／sdist-reproducible**、作業ブランチはfeat/xdw-review-multiple-regionsです。
Coreは1.0.0を維持しています。新しい確認セットは形式2.0、既存1領域APIは形式1.0のままです。
**複数領域：SDK往復検証済み。Viewerでは同一文字2領域の片方だけを編集・別名保存後に取り込む正常1ケースを検証済み。**
SDK実装の基準は0.7.0.dev3／0d26beb／multiple-regionsです。以下の2026-09-12の試験履歴はその基準の記録として残します。
2026-09-13のViewer確認は下記に分けて記録し、1領域版のViewer確認結果の流用ではありません。

## 試験結果（2026-09-12、Windows x64）

| 対象 | 成功数 | 証跡 |
|---|---|---|
| Python 3.10：訂正56＋既存レビュー43＋新規57 | 156 | [JUnit](../evidence/review-regions-0.7.0/dev3-3.10.xml) |
| Python 3.11：Integrations回帰 | 283 | [JUnit](../evidence/review-regions-0.7.0/dev3-3.11.xml) |
| Python 3.12：Integrations回帰 | 283 | [JUnit](../evidence/review-regions-0.7.0/dev3-3.12.xml) |
| Python 3.13：Integrations回帰 | 283 | [JUnit](../evidence/review-regions-0.7.0/dev3-3.13.xml) |
| Python 3.13：複数領域SDK往復 | 15 | [JUnit](../evidence/review-regions-0.7.0/dev3-sdk.xml) |
| 配布ガード・既存例と新しい使用例：Python 3.11 | 66 | [JUnit](../evidence/review-regions-0.7.0/dev3-guards.xml) |
| 導入済みwheel：上記156＋既存結果18＋既存SDK13＋新SDK15、Python 3.11 | 202 | [JUnit](../evidence/review-regions-0.7.0/dev3-wheel.xml) |
| 未加工sdist：訂正・既存レビュー・新規レビュー、Python 3.11 | 156 | [JUnit](../evidence/review-regions-0.7.0/dev3-sdist.xml) |

表の試験は失敗・エラー・skipなしです。Python 3.10ではライブラリ全体・SDKを再検証していません。
Coreの実装は変更せず、既存の検証結果を維持しています。
GitHub Actionsには新試験を追加しましたが、push・リモートCI実行・公開リリースは行っていません。

## 同じ文字を持つ2領域のSDK検証

新しい合成runに、同一ページ上のSAME TEXTを2領域、選択対象外のUNSELECTEDを1領域配置しました。
DocuWorksの画像取込APIで原本XDWを作成し、既存save_ocr_resultで合成のOCR形式bundleを保存しました。
OCRエンジンは実行しておらず、認識精度を測定した試験ではありません。
画像作成に使ったPillowは試験用原本の準備だけに必要で、レビューAPIの依存ではありません。

SDKで次を確認しました。

- 同じ文字の片方だけを訂正しても、他方・選択対象外の領域は不変。
- 両方を個別に訂正、逆順のID指定、表示位置の入替え、全件未変更。
- 日本語・改行・引用符・前後空白の保存と再読込。
- 削除、属性付き／属性なしコピー、属性欠落・破損・重複、種類変更、ページ追加、別確認セットの拒否。
- 正しい訂正と空白訂正の混在を候補として読み、既存save_correctionsで全体の保存を拒否。
- 元bundle・初期確認セット、元のID・ページ・順序・座標・信頼度を保持。

新規57件ではさらに、Canonical 1.0／1.1、列挙順の変更、不正指定・形式・別run、保存先衝突、
2番目の注釈保存失敗、確定失敗、入力変更、元runと確認セットの移動、予約属性衝突、遅延importを確認しました。
文字訂正の検証・保存・適用をXDW側に再実装していません。

実DLLはXDWAPI申告版10.1.1、ファイル版10.1.0.17、製品ファイル版10.1.0.0です。
DLLハッシュ・実機要約は[実行証跡](../evidence/review-regions-0.7.0/runtime.json)に保存しています。

## 配布物の検証

Python 3.11の通常のbuildコマンドでsdistを作成し、そのsdistからwheelを作成しました。
テスト用conftest.pyに加え、SDK試験のソースもsdistへ収録しています。実文書・SDK・DLLは含めません。
未加工sdistでは156件に必要なファイルを補完せず、展開ソースのimportと収録ファイル不変を確認しました。
試験中に生成されたPythonキャッシュ5ファイルは別記録です。

通常のvenv作成とpip installで新規環境へCore 1.0.0・Integrations 0.7.0.dev3を導入し、pip checkとCLIヘルプが成功しました。
この導入では個別インストーラー、一時フォルダー処理の差し替え、制限外実行を使用していません。
新規環境の実行例は、Pillow、Paddle、NumPy、pytest、jsonschemaをimportせずにSDK往復とJSONL出力まで成功しました。
202件のpytest試験は、試験依存のある別環境へ同じwheelを通常のpipで導入して実行しました。

配布ガード・使用例66件は、このホストのpytest一時フォルダー制限に対応するため、既存fixtureを
テストプラグインとして指定しました。未加工sdistの156件には外部fixtureを指定していません。
Core／Integrationsの4アーカイブでメタデータ検査と内容監査が成功しています。
[配布物ハッシュ](../evidence/review-regions-0.7.0/distributions.json)と[sdist検証条件](../evidence/review-regions-0.7.0/sdist.json)を記録しています。

新しい納品先はdist/ocr-review-0.7.0.dev3-multiple-regionsです。
最終コミット、ソースZIP、収録ファイル一覧とハッシュは同フォルダーのartifact-manifest.jsonで対応付けます。
8a0671aの成果物と元の検証run・Viewer保存済みファイルは保全します。

## 利用者向け生成物

ローカルのwork/dev3-sdk-demoに、編集前review/review.xdw、SDK編集後edited.xdw、
corrections.json、effective.jsonl、日本語の確認結果.txtを保存しました。
例ではp0001-r000001だけを「訂正済み FIRST ONLY」に変更し、p0001-r000002とp0001-r000003は元のままです。
これらの文書・訂正文を含む出力は配布ソースに含めません。
利用者によるコード実行やBAT、新しいViewer操作は不要です。

## Viewerの正常1ケース確認（2026-09-13）

0d26bebの未編集review.xdwと対応JSONを別の確認フォルダーへコピーし、初期状態が未変更の2領域であることを照合しました。
上側の領域だけを編集してsaved.xdwへ別名保存し、再表示する手順を日本語で案内しました。
利用者から「別名保存・再表示とも問題なし」と報告がありました。表示・操作は利用者報告であり、担当側によるGUIの直接観察とは区別します。

担当側はsaved.xdwだけを読み取り、次をコードで検証しました。別ファイルへの代替読込みは行っていません。

- p0001-r000001だけに指定どおりの訂正があり、同じ元文字を持つp0001-r000002は未変更。
- 選択対象外のp0001-r000003も元の結果を維持。
- 確認セット・元run・識別属性・ページ数・注釈数を既存review_xdwで検証。
- 既存save_corrections → apply_corrections → export_effective_jsonlで全3領域と訂正来歴を照合。
- 元の座標・順序・信頼度を含む文字以外の領域情報と、元bundle全ファイルが不変。
- 初期確認ファイル、以前のSDK結果、multiple-regionsの配布物が不変。読取り前後の入力ハッシュも一致。

実行はPython 3.11.9、導入済みCore 1.0.0／Integrations 0.7.0.dev3と実DLLを使用しました。
DLLのSHA-256は前回と一致しています。[個人情報と訂正文を除いたViewer証跡](../evidence/review-regions-0.7.0/viewer-confirmed.json)を収録しています。
ローカルの検証補助は事前にSDK編集コピーで自己試験していますが、それをViewer操作の証跡には使いません。

今回完了したViewer確認は、1ページ・2選択領域・原本重ね合わせ型で片方だけを訂正する正常1ケースです。
複数領域のコピー・削除・空白などのViewer異常操作や白紙型は未確認です。
形式1.0の1領域版の6ケースは別の過去記録として維持します。コピー・削除の構造確認はreview_xdw、空白訂正の拒否はsave_correctionsの責任です。

## Viewer確認後の成果物

版番号と公開APIは変更せず、識別を0.7.0.dev3／multiple-regions-viewer-verifiedとします。
作業ブランチはdocs/xdw-review-regions-viewer-verifiedです。実装比較基準0d26bebと、Viewer証跡を含む最終コミットは区別します。
最終コミットと成果物の対応はdist/ocr-review-0.7.0.dev3-multiple-regions-viewer-verifiedのartifact-manifest.jsonに記録します。

更新したパッケージREADMEからsdistを作り、そのsdistからwheelを再作成しました。wheelの説明文が更新済みREADMEと一致しています。
新しい独立環境へ通常のpip installを実行し、pip checkと実際のsaved.xdwの取り込み・JSONL出力に成功しました。
試験依存のある別環境にも同じwheelを通常のpipで導入し、site-packagesからのimportを確認して試験しました。

| 今回再作成した配布物の確認（Python 3.11.9） | 結果 |
|---|---|
| 導入済みwheel：訂正・1領域レビュー・複数領域レビュー | [156件成功](../evidence/review-regions-0.7.0/viewer-wheel.xml) |
| 未加工sdist：同じ対象、外部ファイル補完なし | [156件成功](../evidence/review-regions-0.7.0/viewer-sdist.xml) |
| 新規環境への通常pip導入、pip check、保存済みViewerファイルの往復 | 成功 |
| wheel本体の全34ファイル | 0d26bebのwheelおよび作業ソースとバイト一致 |
| Core／Integrationsの4配布物の内容監査・メタデータ検査 | 成功 |

sdistの元の収録63ファイルは不変で、試験中のPythonキャッシュ5ファイルだけを別記録としています。
上記の新しい検証と、0d26bebのSDK15件・wheel202件・各Python回帰283件は区別します。後者を今回再実行したとは扱いません。
Python 3.10のライブラリ全体や実DLLを今回検証済みとは記載しません。
[新配布物と検証条件](../evidence/review-regions-0.7.0/viewer-distributions.json)を参照してください。

旧配布物とCore配布物は保全します。最終コミットの管理対象から作るソースZIPを展開し、
source-manifest.jsonの全一覧・サイズ・SHA-256およびコミットの内容と照合します。ライセンス変換は行いません。
実文書・SDK・DLL・個人設定・訂正結果・ローカル検証補助は配布ソースへ含めず、BATも追加しません。
Core、既存CLI、公開Portableを変更せず、push・公開リリースは行いません。

利用者向けにはwork/dev3-viewer-check/results内に最終確認結果.txtと訂正JSONLを保存しています。
利用者によるコード実行や、完了済みViewer操作の再実施は不要です。
