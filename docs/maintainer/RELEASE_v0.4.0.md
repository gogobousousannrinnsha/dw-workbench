# v0.4.0 Pre-releaseの構成と公開検証

Integrations 0.8.0 / Core 1.0.0。OCR空文字修正、全ページの白紙Reviewと独立したReviewed Result、Portableの生成・取り込みBATを含みます。

## 動作と互換性

OCR開始.batは従来の出力にreview-sessionを追加します。校正結果取込.batは1文書ずつ、保存済みXDWとSessionを照合してReviewed Resultを新規保存します。
`process_documents(..., review=False)` がPython APIの既定で、既存のジョブ1.0形式を保ちます。`review=True` はジョブ1.1形式となり、review段階の状態・相対保存先・Session識別情報を記録します。標準OCR開始だけが既定で有効にします。
既存のsettings.iniはそのまま使用できます。min_confidenceは矩形と確認画像だけに作用し、白紙Reviewから文字を除外しません。

従来のCorrectionSet・単一ページReviewは既存APIで使用します。旧review.json形式のXDWを新しい取り込みBATへ渡すことはできません。完全なCanonical 1.0/1.1が残っていれば新APIでSessionを作れます。通常操作では新しいOCR開始から生成してください。

## 検証範囲

新しい形式・ジョブ・取り込み入口のDLL不要試験はPython 3.10～3.13、Integrations全体は3.11～3.13で確認します。
公開wheel・未加工sdist・最終Portableでも試験し、実GPU OCR、SDK保存再読込、2本のBATの実行、移動後利用、分割結合を確認します。公開後は全添付物を再ダウンロードしてハッシュ・復元・実行を検証します。
結果数・ハッシュ・環境・コミットはRelease添付のVERIFICATION_JA.mdとRELEASE_PROVENANCE.jsonを正本として記録します。

Viewerの基本編集・保存・再表示・再編集は利用者確認済みです。他の編集操作は利用者の指示によるSDK代替検証であり、Viewer全ケースの目視確認済みとは扱いません。
Core全体のPython 3.10問題と既存Marker 13pt編集問題は今回の解消対象ではありません。

## 公開条件

試験・ビルド・監査の成功が必要です。今回承認された例外は、CI成果物アップロードだけがストレージ容量上限で失敗する場合です。同一の凍結ソースから検証したローカル成果物を使用し、workflow全体成功とは記載しません。他の失敗をこの例外に含めません。
公開物は新しいv0.4.0タグに固定し、旧Release・タグ・添付物を上書きしません。自作部分は公開変換時に既存MIT条件を適用し、第三者ランタイム・モデル・ライセンスは保持します。

利用方法は[Portable手順](../user/README.md)、データ契約は[Reviewed Result仕様](../../packages/docuworks-integrations/REVIEWED_RESULT_FORMAT.md)を参照してください。
