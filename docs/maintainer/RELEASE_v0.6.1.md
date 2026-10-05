# DW-OCR v0.6.1 Pre-release の構成と検証方針

Core 1.0.1 / Integrations 0.12.0を維持し、Portableへ「テンプレート適用.bat」とscripts/apply_template.pyを追加します。Core・Integrationsの処理、OCRモデル、Python環境はv0.6.0から変更しません。

## 変更内容

- 校正結果と登録済みテンプレートの版を選び、既存のapply-templateコマンドで項目を抽出します。
- 結果はPortable内のstructured/result-日時-IDへ新規保存します。入力・登録版・過去の結果は上書きしません。
- 取得完了・要確認・適用不可と診断・保存先を表示します。選択のキャンセルでは結果を作りません。
- 1文書・1登録版を扱います。CSV出力は既存CLIを利用します。
- 操作手順、配布一覧、READMEを同梱BATに合わせます。

## 配布と確認

v0.6.0を保持し、新しい場所へ展開します。自作部分の既存MIT条件と第三者資産の条件を維持します。利用者の文書、テンプレート、下書き、SDK DLLは配布物に含めません。

専用入口と配布構成のテスト、公開変換の監査、ソース・wheel・Portableの照合、分割復元を実施します。展開したPortableでOCRからReviewed・テンプレート適用BAT・CSVまでを合成文書で確認し、入力と既存結果の不変を検証します。最終成果物の実測結果とSHA-256は配布する検証報告を正とします。

Viewer手操作、ネイティブのフォルダー選択画面の手操作、Excel画面、実帳票、DocuWorks 9.1は自動検証の範囲外です。SDKによる編集や選択応答の注入を手動確認とは扱いません。

[利用者向け手順](../user/README.md) / [テンプレート適用](../user/template-apply.md) / [前版の構成](RELEASE_v0.6.0.md)
