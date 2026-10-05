# OCR確認一覧とWorkbench未完了項目移動：ローカル実装記録

2026年10月5日。実装・合成資料でのローカル検証まで。公開・push・PR・merge・タグ・Release・外部送信は行っていません。

## 調査した現状

| 管理対象 | 基準 |
|---|---|
| 開発DW-OCR `gogobousousannrinnsha/dw-ocr` | main `df867033ce6ca9419fec623a4cc0fbf65f3fbfb6`、v0.7.0 |
| 公開DW-OCR `gogobousousannrinnsha/dw-ocr` | main `c5c94edeeb7644f113e71453d5d94da358479ebf`、v0.7.0 |
| Workbench開発候補 | 同じ開発リポジトリの独立パッケージ。detached HEAD `43418a5adf3e36d71b3d30f2b4ba618c3f12fbe4`、v0.2.0 |
| 公開Workbench `gogobousousannrinnsha/dw-workbench` | main `38c59f7f638a5d134387b5839a89333ff05901a2`、v0.2.0 |

3つのリモートmainを読取専用で照合しました。Workbenchは10月4日の独立公開ソースも存在し、開発候補とアプリ9モジュールがバイト単位で一致しました。
Workbenchには既にページ用／文書用テンプレート、独立した採用値・確認状態、案件一括Excel／CSV、履歴、保存再試行、バックアップと旧案件移行があります。
透明リンク・Web画面を必須仕様として追加せず、現在のデスクトップと不変な原記録を使用しました。

主要な開発チェックアウトは未コミット変更なしでした。公開Workbench作業場所では説明書・JSON等35ファイルに変更表示があり、今回そこへ書き込んでいません。
元のPortable・原案件・履歴・memoryファイルも保持しました。専用コピーの`feat/local-review-navigation-20261005`で変更しています。

## 選んだ追加機能と責任

**DW-OCR：確認優先一覧。** 既存Canonicalの信頼度・領域を参照し、閾値未満、信頼度なし、文字未検出ページ、未処理ページを別々に表示・JSON出力します。
原記録にある領域ID・文字・実ページ・原本SHA256・mm矩形と四隅をそのまま参照します。閾値は既定0.8、等値は低信頼度に含めません。
信頼度は人の確認状態とは別です。訂正の正本を追加せず、派生JSONの編集を逆取り込みしません。
入力検査・一時出力の再読込・入力再検査後に確定し、既存出力・元bundle内への書込みを拒否します。
標準ライブラリだけで利用でき、SDK・GPUなしでも既存の結果から一覧を作れます。

**Workbench：次の未完了項目へ移動。** 原本登録順・実ページ順・項目定義順で、未取得・未確認・保留を探し、最後から先頭へ循環します。
確認済みと理由付き任意項目の対象外は完了とします。ページ自体の対象外・過去の記録は対象にしません。
テンプレート未選択は作業一覧へ、登録未完了は再開の案内へ移動します。
入力を保存してから移動し、保存失敗では入力と表示位置を保持します。移動で値・原本座標・確認状態を自動変更しません。
既存の完了規則を`field_complete`へまとめ、出力判定と移動判定を一致させました。保存形式・DB版は変えていません。

## 変更ファイル

| 対象 | 主なファイル |
|---|---|
| OCR API／CLI | `packages/docuworks-integrations/docuworks_integrations/review_report.py`、`cli.py`、`__init__.py` |
| OCR起動・配置 | `portable/OCR確認一覧.bat`、`portable/scripts/review_report.py`、`portable/layout.json` |
| OCR試験 | `packages/docuworks-integrations/tests/test_review_report.py`、`scripts/tests/test_review_report_portable.py` |
| Workbench | `packages/dw-workbench/dw_workbench/application.py`、`domain.py`、`ui.py` |
| Workbench試験 | `tests/test_review_navigation.py`、`tests/test_v020_ui.py`、`tests/conftest.py`（環境変数で試験先を指定） |
| 操作説明 | `docs/user/ocr-review-report.md`、`docs/user/README.md`、`docs/WORKBENCH_JA.md` |

## 検証

証跡は作業コピーと並ぶ`evidence`フォルダーに保存しています。合成文書以外は試験入力に使用していません。

| 確認 | 結果・証跡 |
|---|---|
| Workbench全体 | 118件成功：`workbench-all.xml` |
| 追加した実Tk操作 | 3件成功：`new-ui-final.xml`。項目／ページ／文書の連続移動、保存・再読込、拡大時の座標、保存失敗、履歴の拒否、中断した登録の循環 |
| 追加機能ロジック・起動スクリプト | 20件成功：`new-logic-final.xml`（Workbench2、OCR11、Portable7。上のGUIを合わせて23件） |
| 最終OCR差分 | 関連18件成功：`report-final.xml`。Python 3.10で確認一覧11件成功：`report-python310.xml` |
| DW-OCR単独の集約 | 最新開発main df867033にOCR差分だけを反映し、788件成功：`ocr-isolated-all.xml` |
| Coreの既存DLL不要試験 | 136件成功：`core-all.xml`。既存CIと同じinstalled bundleケースを除外 |
| 実SDK／GPU | 1ページの合成XDW、5認識領域。ID・文字・mm座標一致、原本ハッシュ不変：`local-smoke.json`、`sdk-ocr-report.json` |
| 表示したTk画面 | 合成画像で起動・保存・ボタン移動をassert：`local-smoke.json` |
| 実BAT | 日本語・空白を含む場所で起動、2対象領域出力、既存出力保持・終了コード1：`bat-smoke.json`。QA用venvであり、全Portableの移動試験ではありません |
| wheel | 両wheelをローカル生成、ZIP CRC、Pythonモジュール全件とソースの一致：`wheel-source-check.json` |
| 静的検査 | 変更PythonのAST構文検査、`git diff --check`、`audit_publication.py`成功 |

Windowsの長い試験パスで既存bundle保存のrenameが`WinError 5`になり、短い一時フォルダーでは成功しました。
Portableには試験用openpyxl/jsonschemaがなかったため、保存済みwheelまたは既存の試験環境を独立して参照しました。
pytestの0700一時フォルダーはホストで拒否されたため、証跡内の`windows_test_paths.py`で通常のmkdirを使用しました。製品のセキュリティ設定を変えていません。

Workbenchを含む開発候補全体でのOCR／スクリプト集約は787件中776件成功・11件失敗です。
失敗は`portable/workbench/launch.bat`がDW-OCR用の厳密な配布一覧に含まれない既存の構成不一致です。
変更前43418a5の独立コピーでも同じ11件が失敗しました（`baseline-packaging.xml`、19件中8成功・11失敗）。今回の機能変更で試験結果を隠したり、配布ガードを緩めたりしていません。
DW-OCR単独のdf867033にOCR差分だけを反映した集約は788件成功しています（`ocr-isolated-all.xml`）。
集約実行後に既存出力（dangling linkも含む）の存在検査を補強し、その最終ソースに対して関連18件とPython 3.10の11件を再実施しました。

画面画像取得は`OSError: screen grab failed`のため、見た目のQAは成功扱いにしていません。
Viewer手操作、実帳票、DocuWorks 9.1、今回の全PortableのC／E移動、静的型チェッカーは未実施です。型チェッカー設定・実行ツールは今回確認した環境にありません。
実SDK／GPU合成成功を実帳票の認識精度やViewer受け入れに置き換えません。

## 利用と次の公開工程

OCRは[確認一覧の説明](../user/ocr-review-report.md)、Workbenchは[保存・確認・再開](../WORKBENCH_JA.md#保存確認再開)に従って操作します。
既存Portableへは今回の変更を導入していません。wheelは既存の版番号を維持したソース照合用ローカル候補です。
更新した別Portableを組み立てた後に、OCRの「OCR確認一覧.bat」とWorkbenchの「次の未完了項目へ（案件全体）」を使用します。

公開する場合は、次の工程を別途承認・実行してください。

1. 2つの追加機能の差分を別々にレビューします。開発Workbench基準には未統合の既存Workbench実装も含まれます。
2. OCRは開発／公開のv0.7.0基準へOCR差分だけを反映し、Workbenchは独立公開main38c59f7へWorkbench差分を反映します。アカウント・ライセンス・リポジトリの役割を照合します。
3. 製品版・配布版・source snapshotを更新します。開発用の結合チェックアウトからDW-OCR Portableを作る場合は、上記の既存配布一覧不一致を責任別に解決する必要があります。
4. 新しいPortableを別フォルダーへ組み立て、wheelとコード照合、pip check、実BAT、保存／再開、復元、日本語・空白パス、C／E移動を確認します。
5. 現地代表帳票とViewerの受け入れ、画面の視覚確認を行い、その後に開発PR・公開変換・公開側PR・Releaseを進めます。

公開用の既存変更、実帳票、案件、OCR本文、モデル、SDKバイナリ、資格情報をソース差分へ追加しないでください。
