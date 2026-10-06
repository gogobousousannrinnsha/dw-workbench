# v0.8.1 / Workbench 0.4.1 共通Portable Pre-release

[ダウンロード](https://github.com/gogobousousannrinnsha/dw-ocr/releases/tag/v0.8.1)。OCR v0.8.1 / Workbench 0.4.1 / Integrations 0.14.0 / Core 1.0.1 / Python 3.13.15。

未操作の採用欄へ最新の有効なOCRを自動入力しますが、状態は未確認です。原文と照合し「確認して次へ」またはCtrl+Enterで確認して進みます。手編集、意図的な空欄、確認済み、履歴不明の旧値は再OCRで上書きしません。寸法不一致は通常作業からスキップし、件数と一覧に残します。未割当は未完了のままです。保存形式2を維持します。

8個の `ocr_part_001_transport.zip` ～ `ocr_part_008_transport.zip` と `ocr_join_tools.zip` を取得し、同じ新しいフォルダーへ展開します。`join_parts.bat`で検査・結合し、できた`dw_ocr_with_code.zip`を別の新しいフォルダーへ展開して`Workbench開始.bat`を実行してください。旧版と元データを保持し、使用中のPortableへ上書きしないでください。移動前に保存してアプリとワーカーを通常終了します。

起動は同梱runtime/modelsを使い、開発checkoutやCodexに依存しません。Windows x64、DocuWorks本体/XDWAPI、対応NVIDIA GPU・ドライバーが必要です。DocuWorks本体/SDK/XDWAPI/ドライバーは同梱しません。全ZIP・部品・完成ZIP・展開後を保持する場合は空き16GB以上を目安にしてください。

## 検証と制限

Workbench244件、Core/Integrations803件、梱包120件、OCR CIガード5件、復元17件が通過。条件付き195件はスキップです。初回のUI1件の時間切れは単独再実行で通過しました。WorkbenchでOCR専用CIを探した5件はOCR側のCI文脈で通過し、今回の公開CIにはWorkbenchの3wheel外部起動確認と梱包テストを追加しました。最終公開commitのCI結果はReleaseで報告します。

新ランタイムだけで実GPU OCR、自動入力4件、再OCR保護4件、連続確認、空欄と手修正保護、Excel/CSV、先頭ゼロ、台帳注釈2か所、連打・キャンセル、保存・再読込、フォルダー移動、実BAT起動、8分割の実結合を確認しました。実SDK再読込の3ページ注釈数は[1,0,1]です。公開向け説明・CI・ソース一覧を更新しますが、実機検証した実装と同梱ランタイムのバイトは保持します。

DocuWorks 10.1.1とRTX 3060の本PCで合成データを確認済みです。DocuWorks 9.1、別の物理PC、Viewer手操作、全DPI、CPU専用OCR、現地実帳票は未確認です。台帳注釈出力でWindows共有違反(WinError 32)が一度発生し、保存済みプレビューから再試行して成功しました。原本・確定データは保持されましたが、再現条件の特定と自動リトライ修正は未実施です。

## 配布境界

実文書、実台帳、案件DB、利用者設定、ログ、キャッシュ、認証情報、PC固有パス、開発アカウント詳細を配布しません。projects/settings/INPUT/OUTPUT等は初期状態で空です。既公開教材の合成XDW/XLSX/CSVと画像は既公開版と同一のものを保持します。第三者LICENSE/NOTICE、固定モデルハッシュ、対応ソースを保持します。採用値の正本は案件DB、領域IDと原本ページ・mm座標を表示位置から分離します。
