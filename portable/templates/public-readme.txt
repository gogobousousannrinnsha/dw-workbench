# DW-OCR @RELEASE_VERSION@

Core @CORE_VERSION@ / Integrations @INTEGRATIONS_VERSION@。Windows x64用Pre-releaseです。

DW-Workbench 0.4.0を同梱するPortable候補です。`Workbench開始.bat`から、文書登録・テンプレート設定・OCR・原文確認と訂正・Excel出力・台帳照合とXDW注釈へ進めます。[操作の流れ](docs/WORKFLOW_UI_JA.md)、[一括テンプレート適用](docs/BULK_TEMPLATE_JA.md)、[台帳照合](docs/LEDGER_MARKUP_JA.md)、[別PCへの移動](docs/user/portable-transfer.md)を参照してください。

`OCR確認一覧.bat`は元OCRの領域IDと原本座標を保持した確認一覧を出力します。訂正はWorkbenchの採用欄または従来のReviewed取り込みで保存します。[OCR確認一覧](docs/user/ocr-review-report.md)を参照してください。

- [一括・分割の選択と比較](portable/README_AB.md)
- [利用者向け操作・設定・保存先](docs/user/README.md)
- [校正結果の全文Excel出力](docs/user/reviewed-excel.md)
- [矩形テンプレートからCSV一覧まで](docs/user/template-csv.md)
- [テンプレート作成画面と改訂](docs/user/template-editor.md)
- [テンプレート適用BAT](docs/user/template-apply.md)
- [Python API・結果形式・訂正](docs/api/README.md)
- [保守・配布と構成管理](docs/maintainer/README.md)
- [履歴・公開済み基準・検証](docs/history/README.md)

OCR開始.batは全ページOCR・白紙Review・矩形付きXDW・確認画像と任意の元OCR JSONLを生成します。Viewerでreview.xdwを編集・保存して閉じ、校正結果取込.batへドロップすると独立したReviewed ResultとJSONLを保存します。取り込みは1文書ずつです。

テンプレート作成.batで見本を選び、Viewerで描いた複数の矩形へ項目名・適用条件を設定して登録・改訂できます。下書きはtemplate-drafts、登録版と改訂用の見本はtemplatesへ保存します。テンプレート適用.batで校正結果と登録版を選び、取得値・判定・保存先を確認します。結果はstructured/result-日時-IDへ新規保存します。同じ登録版の結果を1文書1レコードのCSVへまとめる場合は、docuworks-integrations.batのexport-structured-csvを使います。

取り込み・テンプレート・作成画面の自動試験は合成文書を使った確認です。Viewer手操作・Excel画面・実帳票・DocuWorks 9.1・別の物理PCは未確認です。[構成と検証方針](docs/maintainer/RELEASE_v0.8.0.md)と、Releaseに添付する最終検証報告を参照してください。旧版は保持し、新しいフォルダーへ展開してください。

自作部分はMIT、第三者資産は各条件を維持します。SDK・DLL・実文書は同梱しません。[ライセンス](LICENSE) ／ [第三者条件](THIRD_PARTY_NOTICES.md)

確認用XDWの文字背景は塗りつぶしなしです。新規白紙Reviewの追加処理に加え、矩形生成時のページ情報の再取得を減らしています。
