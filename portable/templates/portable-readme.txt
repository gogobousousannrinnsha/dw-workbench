DW-OCR @RELEASE_VERSION@ / Integrations @INTEGRATIONS_VERSION@ / Core @CORE_VERSION@
Windows x64用Pre-releaseです。旧版と別の新しいフォルダーへ展開してください。

DW-Workbench 0.4.0はWorkbench開始.batで起動します。
文書登録→読取設定→OCR→確認・訂正→Excel出力→台帳・注釈を案内します。
案件はprojects、共通設定はsettingsへ保存します。初期状態は空です。
操作説明はdocs/WORKFLOW_UI_JA.md、台帳はdocs/LEDGER_MARKUP_JA.md。
別PCの条件と移動方法はdocs/user/portable-transfer.mdを参照してください。
DocuWorks本体・XDWAPI・NVIDIAドライバーは同梱しません。移動先にも導入が必要です。
GPU OCRが使えないPCでは手入力・確認・保存・表出力を利用できます。
OCR確認一覧.batは元OCR領域の低信頼度・空欄などを確認一覧にします。

INPUTへXDWを入れてOCR開始.batを実行、またはXDW・フォルダーをドロップします。
ocr開始（一括）.bat / ocr開始（分割）.batで校正用XDWの作成方式を選べます。
分割はページ別に校正用XDWを作り最後に結合します。両方とも毎回OCRし、途中再開はありません。
全ページOCR、白紙Review、矩形付きXDW、確認画像をOUTPUTへ、元結果をrunsへ保存します。
設定はsettings.ini。詳細はdocs/user/README.md、全体の案内はdocs/README.mdです。
表示されたreview.xdwをViewerで編集・保存して閉じ、校正結果取込.batへドロップします。
校正後の文字・位置を別のReviewed ResultとJSONLへ保存します。取り込みは1文書ずつです。
全文Excel出力.batでReviewedを選ぶと、通常テキスト全文を隣のxlsxへ保存します。テンプレート不要です。
一括・分割どちらのReviewedにも使えます。手順と制限はdocs/user/reviewed-excel.mdを参照してください。
取り込みはID照合中心の保存形式2.0です。付箋の作業メモは本文から除外し、保存済みXDWには残します。
ページ追加・削除・並べ替え・寸法変更・ページ回転は対象外で、自動検出を保証しません。
複数の原本参照の明示設定と旧形式互換はdocs/api/reviewed-import-v2.mdを参照してください。
校正後は、矩形テンプレートを登録・適用して項目を取得し、同じ登録テンプレートの結果をCSVへまとめられます。
登録・確認・適用・CSV出力のCLIはdocuworks-integrations.batを使用します。操作例はdocs/user/template-csv.mdです。
テンプレート作成.batは見本選択、項目名設定、取得結果確認、登録・改訂の画面を開きます。手順はdocs/user/template-editor.mdです。
登録先はtemplates、下書きはtemplate-draftsです。登録版には改訂用の見本も保存します。
テンプレート適用.batで校正結果と登録版のフォルダーを選び、取得値・判定・保存先を確認します。
結果はstructured/result-日時-IDへ新規保存します。操作例はdocs/user/template-apply.mdです。
CSVはUTF-8 BOM付きです。Excelには取得値の列を文字列として取り込み、先頭ゼロなどを保持してください。
Viewer手操作・フォルダー選択画面の手操作・Excel画面・実帳票・DocuWorks 9.1は未確認です。確認範囲はdocs/maintainer/RELEASE_v0.7.0.mdと公開Releaseの最終検証報告を参照してください。
対応DocuWorks・NVIDIA GPUが必要です。旧版と元データは保持してください。

確認用XDWの文字背景は塗りつぶしなしです。新規白紙Reviewの追加処理を軽量化しています。
