# docuworks-integrations 0.14.0

0.14.0では[元OCRの確認一覧](../../docs/user/ocr-review-report.md)を追加します。領域ID・原本座標・認識文字・信頼度を保持し、確認が必要な理由をJSONへ出力します。元結果を書き換えず、訂正は既存の採用・Reviewed経路で保存します。0.13.0の校正用XDW作成方式の選択と全文Excel出力を維持します。以下の0.12.0以前の記述は履歴です。

保存済みOCR結果を中心に、OCR実行・矩形と確認画像・文字訂正・編集用XDWを提供します。Core 1.0.1を使用します。

0.12.0は[テンプレート作成画面](../../docs/user/template-editor.md)と[下書き・見本付き改訂](../../docs/TEMPLATE_AUTHORING.md)を追加します。既存テンプレート1.0の登録形式と適用APIを維持します。画面にはTkinterとPillowが必要です。

0.11.0開発候補は、同じ登録テンプレートのStructured Resultを文書ごとの行にまとめる[CSV出力](../../docs/STRUCTURED_CSV.md)を追加します。文書名を明示し、値・状態・確認事項・結果IDをUTF-8で出力します。登録済みデータの形式変更や追加の実行時依存はありません。[Reviewedの保存形式とAPI](REVIEWED_RESULT_FORMAT.md)、[テンプレート仕様と操作例](../../docs/RECTANGLE_TEMPLATE.md)も参照してください。

この開発候補ではPaddleの空文字・空白だけの認識結果を除外し、正常文字を保持して処理を継続します。
不正な座標・信頼度・非文字列は引き続き拒否します。この空文字対策は公開Portable v0.4.0にも反映済みです。
[再現手順と検証範囲](https://github.com/gogobousousannrinnsha/dw-ocr/blob/v0.8.1/docs/maintainer/PADDLE_BLANK_TEXT.md)

- [全体のAPI案内](https://github.com/gogobousousannrinnsha/dw-ocr/blob/v0.8.1/docs/api/README.md)
- [保存形式とAPIの正本](OCR_RESULT_FORMAT.md)
- [白紙Review・独立したReviewed Result 1.0の仕様とAPI](REVIEWED_RESULT_FORMAT.md)
- [訂正の検証・保存・適用](https://github.com/gogobousousannrinnsha/dw-ocr/blob/v0.8.1/docs/api/corrections.md)
- [編集用XDW：1ページ内の指定領域](https://github.com/gogobousousannrinnsha/dw-ocr/blob/v0.8.1/docs/api/review-regions.md)
- [利用手順](https://github.com/gogobousousannrinnsha/dw-ocr/blob/v0.8.1/docs/user/README.md) ／ [検証範囲](https://github.com/gogobousousannrinnsha/dw-ocr/blob/v0.8.1/docs/history/README.md)

標準OCRのBATは全ページOCR・白紙Review・矩形・確認画像と任意JSONLを生成します。校正結果取込BATは1文書ずつ独立したReviewed Resultへ取り込みます。元runを変更せず、文字以外の座標・順序・信頼度を維持します。

旧workflow APIは0.2.0形式との互換用です。新規コードではrecognition、results、consumersを利用してください。新規OCRはResult 1.1、1.0・旧runは読込み互換です。

新しい白紙Reviewは全ページの独立SessionとReviewed Resultを提供し、Portableから生成・取り込みできます。Viewerの基本編集は利用者確認済みで、その他はSDK代替操作の検証です。検索・テンプレートは対象外です。
