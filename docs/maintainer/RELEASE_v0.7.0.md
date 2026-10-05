# DW-OCR v0.7.0 Pre-release

Core 1.0.1 / Integrations 0.13.0。校正用XDWの一括・分割作成と、Reviewed全文Excel出力を公開します。

- `ocr開始（一括）.bat`: 全ページの白紙を結合してから文字を配置します。
- `ocr開始（分割）.bat`: ページごとに校正用XDWを作成・保存し、最後に結合します。
- `全文Excel出力.bat`: Reviewedを選択し、通常テキスト全件とページ情報を隣の新規xlsxへ保存します。

`OCR開始.bat`の既定動作を維持します。両方式とも毎回OCRを実行し、ページ単位のOCR保存・再開は含みません。
一括・分割の結果は共通の`校正結果取込.bat`で取り込みます。本文・ページ位置・原本参照を同じ契約で扱います。
Excel出力はReviewed 1.0/2.0に対応し、元データを変更しません。テンプレート不要、文字列の自動型変換なし、長文は分割番号付きで保持します。
付箋メモ、画像、元の書式の再現、読み順推定、ExcelからReviewedへの逆取込は対象外です。

## 配布

自作部分と第三者資産の既存ライセンスを保持します。XlsxWriter 3.2.9を任意依存xlsxとし、Portableには固定版wheelとライセンスを同梱します。
Portable組立には`build_portable_candidate.py --dependency-wheel <XlsxWriter wheel>`を使います。Excel機能付きwheelに依存ライブラリを同梱し忘れた場合は組立を拒否します。
Core 1.0.1の公開wheel/sdistを再利用し、Integrationsを0.13.0としてビルドします。OCRモデル・GPUランタイムはv0.6.1から引き継ぎます。
利用者の文書、校正結果、テンプレート、下書き、SDK DLLは配布しません。

## 検証

Python 3.10～3.13と配布監査の既存5ジョブを使用します。新しい定期CIは追加しません。
配布ソース・wheel/sdistの監査、Portable内のコード照合、分割復元、別フォルダー展開、合成文書のBAT処理を検証します。
検証候補では256ページ・10万項目のExcel出力と本文・座標の全件一致を確認しました。性能は合成資料1回の測定で、業務文書の速度保証ではありません。
Viewer・ネイティブ選択画面・Excel画面の手操作、実帳票、DocuWorks 9.1は未確認です。最終配布物の検証結果とハッシュはRelease添付の報告を正とします。

[全文Excel出力](../user/reviewed-excel.md) / [前版の構成](RELEASE_v0.6.1.md)
