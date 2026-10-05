# Portableの利用手順

ローカル開発候補には[OCR確認一覧](ocr-review-report.md)を追加しました。低信頼度・信頼度なしの領域と、文字未検出／未処理ページを原記録から確認できます。

校正結果取込の後に[全文Excel出力](reviewed-excel.md)も使えます。テンプレートを使わず通常テキスト全件を出力します。

本書はDW-OCR v0.7.0 Pre-release（Core 1.0.1 / Integrations 0.13.0）の操作手順です。旧版v0.4.1にはテンプレート・CSV機能は含まれません。配布物の確認範囲はReleaseの検証報告を参照してください。

[テンプレート作成画面](template-editor.md)で見本を選び、Viewerで描いた矩形へ項目名・適用条件を設定し、登録・改訂できます。

## 導入と標準操作

[DW-OCRのRelease一覧](https://github.com/gogobousousannrinnsha/dw-ocr/releases)からv0.6.1の配布物を使います。結合ツールと同じ版の全てのtransport ZIPを同じフォルダーに置き、join_parts.batで復元ZIPを作り、新規の短い書込み可能な場所に展開します。部品数はsplit_manifest.jsonに記録されています。取得物・ZIP・展開先には20GB以上とOCR結果分の空きが必要です。旧版は保持します。

Windows x64、対応DocuWorks製品・x64 DLL、NVIDIA GPUと対応ドライバーが必要です。Python 3.13.15、Paddle GPU 3.2.2、PaddleOCR 3.7.0、PaddleX 3.7.2、PP-OCRv6 mediumは同梱構成を使います。CPUへの自動切替はありません。

1. INPUTへXDWを置き、OCR開始.batを開くか、XDW・フォルダーをBATへドロップします。
2. 全ページを順にOCRし、文書ごとの白紙Review、矩形付きXDWと確認画像を生成します。
3. 終了画面の保存先を開きます。エラーの詳細はjob.jsonに残ります。
4. 表示されたreview.xdwをViewerで編集し、保存して閉じます。
5. 編集済みXDWを「校正結果取込.bat」へドロップします。1文書ずつ取り込み、新しいReviewed ResultとJSONLを保存します。
6. 帳票の種類ごとに初回だけ、「テンプレート作成.bat」で見本から矩形テンプレートを登録します。
7. 「テンプレート適用.bat」で校正結果と登録版のフォルダーを選び、項目ごとの取得値・判定・保存先を確認します。結果はstructured/result-日時-IDへ新規保存します。[適用の操作手順](template-apply.md)を参照してください。
8. 必要に応じて同じ登録テンプレートの結果を選び、1文書1レコードのCSVへまとめます。CSV出力はdocuworks-integrations.batへコマンドを入力します。手順は[テンプレートからCSVまで](template-csv.md)を参照してください。

一括・分割の選択は`ocr開始（一括）.bat` / `ocr開始（分割）.bat`を使います。分割は校正用XDWの作成方式であり、OCRの途中保存・再開ではありません。

## 出力と用語

| 名前 | 内容・扱い |
|---|---|
| 元OCR結果（run / bundle） | 1文書の認識結果一式。編集せず保持する |
| 矩形付きXDW（annotated.xdw） | 認識した位置を枠で示す。文字訂正の入力ではない |
| マーカー付きXDW | 選択領域の強調表示。文字訂正の入力ではない |
| 白紙Review（review.xdw） | 元文書と同寸法の白紙に赤12pt文字を置いた校正作業コピー |
| 確認画像（text-maps） | 白地文字図と重ね図。組版再現・訂正済みの証明ではない |
| Reviewed Result | Viewerで保存した文字・実際の位置・サイズ・方向を独立して記録する |
| 登録テンプレート | 項目名・範囲・適用条件を固定した定義。変更したら別の版として再登録する |
| Structured Result | 取得値・適用可否・参照元・診断を保存する。structured.jsonが正本 |
| CSV一覧 | 同じ登録テンプレートの結果をまとめた派生物。編集しても正本へ反映しない |

```text
runs/job-…/doc-000001/           元結果・原本コピー・ページ画像
OUTPUT/job-…/job.json            文書とrunの対応、段階ごとの成否
OUTPUT/job-…/doc-000001/
  annotated.xdw                 矩形付きXDW
  rectangles-report.json        矩形の保存検証
  text-maps/                    確認画像とレポート
  regions.jsonl                 設定を有効にした場合のみ
  review-session/               Session情報、編集前initial.xdw、編集用review.xdw
  reviewed/result-日時-ID/      校正後JSON・JSONL・入力XDW固定コピー・Session情報・ハッシュ
```

runのmanifest.jsonが入口です。原本コピー、ページ別の画像・文字・座標・信頼度とハッシュを持ちます。OUTPUTだけでは再利用に必要なrunが揃いません。停止後に移動するときはアプリ全体、または参照関係を保ったOUTPUTとrunsを保持してください。原本・OCR本文・画像・元パスを含むため、結果をそのまま公開しないでください。

## 設定

settings.iniの[ocr]を編集します。未知の項目・不正値は開始前にエラーになります。

| 項目 | 既定値 | 意味 |
|---|---|---|
| recursive | false | フォルダーの下層も探索するか |
| dpi | 300 | 300または600 |
| min_confidence | 0 | 矩形・確認画像の表示対象の下限。元OCR文字は削除しない |
| padding_mm | 0.5 | 矩形の余白、0以上 |
| minimum_mm | 3 | 矩形の最小寸法、3以上 |
| color | red | red / blue / green / black / yellow / purple / teal |
| font | 空 | 確認画像用フォント。空ならWindowsの日本語フォントを探す |
| jsonl | false | 元OCR結果のJSONLを出力するか |

相対fontはアプリのフォルダー基準です。JSONLは1領域1行、元ページ番号・保存順で出力します。文字0件のページは正常に保存し、JSONLの行は作りません。検出0件を白紙と断定しません。

## 互換入口と訂正機能

OCR開始.batを標準入口とします。ocr_rectangles.batは旧引数互換で共通処理を呼び、ocr_xdw.batは指定ページOCR（既定1ページ目）、text_maps.batは保存runから画像だけを生成します。上級操作はdocuworks-integrations.bat、環境確認はverify_environment.batです。python.bat・shell.bat・repair_project_wheels.batは保守用です。

白紙Reviewは1文書の全ページを対象とし、空ページも保持します。修正・追加・削除・移動・コピー・回転・縦書きを取り込めます。色とOCR信頼度による取り込み除外はありません。校正後JSONLは元OCRのjsonl設定にかかわらず出力します。

校正結果取込.batには、編集済みXDWまたはreview-sessionフォルダーを1つ渡します。引数なしの場合はパスを入力します。別の場所へ保存したXDWでは、元のSessionフォルダーのパスを入力してください。Session一式は移動できます。取り込みにCanonicalは不要です。

Viewerではinitial.xdwやJSONを編集せず、review.xdwを編集・保存して閉じます。Sessionの識別情報を失うと取り込めません。開発版ではID照合中心で取り込み、付箋とその中の作業メモを本文から除外します。見た目だけ付箋に重なる通常テキストは残します。付箋以外のグループ内テキストは全体を拒否します。ページ追加・削除・並べ替え・寸法変更・ページ回転は対象外で、自動検出を保証しません。画面に「ID照合済み／ページ構造未検証」と表示します。参照なし項目数と不正な参照の項目数は別々に表示します。再取り込みは新しい結果として保存し、過去の結果を上書きしません。

以前のCorrectionSetと1ページReview APIは従来どおり使えます。[APIの流れ](../api/README.md)を参照してください。新しいBATはReviewed Resultを扱います。テンプレート適用は専用BAT、CSVはdocuworks-integrations.batのコマンドから実行します。各機能のCLI入口も維持しています。検索機能は未実装です。

## 失敗・制約

出力は毎回新規です。原本と完成runの上書き、再開・自動再試行・並列処理はありません。文書固有の既知エラーは記録して続行し、GPU・保存領域・整合性・未知のエラーは停止します。OCRが失敗した文書の派生出力は作りません。job.jsonの段階別成否を確認してください。対象なしはNO_INPUTです。

失敗runのerror.jsonは診断先を相対パスで示します。内部一時フォルダーは完成runとして利用しません。アクセス拒否は保護設定を変更して迂回しません。SDK画像パスは255 UTF-16単位以内です。PaddleのWindowsコードページで表現できない文字を含む場合は短い英数字の配置先を使用します。

向き分類・傾き補正・unwarp、検索用OCRテキスト層の埋込みはありません。Structured Resultから原本コピーへマーカーを付ける機能も未実装です。Core 1.0.1の修正内容と、Markerなどに残るViewer確認事項は[対応台帳](../maintainer/CORE_1.0.1_ISSUES.md)を参照してください。
