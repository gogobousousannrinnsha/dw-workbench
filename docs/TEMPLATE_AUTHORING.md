# テンプレート作成 1.0

Integrations 0.12.0の作成画面と保存処理。利用手順は[テンプレート作成](user/template-editor.md)、既存定義は[矩形テンプレート1.0](RECTANGLE_TEMPLATE.md)を参照。

## 責任範囲

- `template_editor.py`: Tkinter/ttk画面、選択、入力、自動保存、表示座標の変換。
- `_template_editor_worker.py`: JSON要求を受ける独立プロセス。SDKが終了しても画面は継続する。
- `template_authoring.py`: 見本固定、下書き検証、設定と矩形の対応、既存抽出処理での確認、新規版の登録。
- `_template_authoring_sdk.py`: 所有する作業コピーだけにUUIDとテンプレート属性を書き込む。保存後に再度開いて検証する。
- `_authoring_storage.py`: OSロック、下書きの原子的置換、固定Reviewedの検証付きコピー。

元Reviewed、Canonical、過去の登録版は書き換えない。画面の取得例と最終確認は既存`_template_extract`を共用し、登録は既存`register_rectangle_template`を通す。ネイティブ処理中は入力操作を止め、子プロセスの完了を画面のイベントループで待つ。

## 下書き

`template-drafts/<draft_id>/draft.json`はschema=`docuworks-template-draft`、schema_version=`1.0`。
`draft_id`、`name`、単調増加`revision`、`sample_manifest_sha256`、`body_sha256`、`base_template_id`、`generation`、`settings`、`registered`、`notices`、`created_at`を保存する。読込済み世代があれば`work_sha256`と`snapshot_sha256`を持つ。

`settings`は矩形UUIDをキーとし、`name`、`purpose`（取得/適用判定）、`expected`、`required`、`join`（連結/空白/改行）、`order`を持つ。名前・期待文字の未完成状態を保存できる。改訂のテンプレート名は変更しない。

`working.xdw`はViewer用。`sample-reviewed/`は固定見本。`snapshots/<generation>/`は読み取り確定時点のXDWと矩形情報。`previews/`は固定見本の画像キャッシュ。画面のピクセル座標は保存定義に使わず、SDKのmm座標を使う。

直接の矩形Annotationへユーザー属性`DW-OCR.TemplateRectangle`としてASCII UUIDを保存する。既知のUUIDが一意に残る場合だけ設定を引き継ぐ。複製で重複したUUIDは該当する全矩形へ新UUIDを付与し、未設定に戻す。消えた矩形の設定は削除する。文字列や近い位置による推定はしない。

本文指紋はReview SDKで読み取った文書・ページ識別情報、ページ数・寸法・回転、通常テキストの文字・位置・寸法・方向・書体情報・由来属性から作る。矩形と付箋の作業メモは指紋の対象外。本文とページの不一致は再取り込みを促す。画像描画を含むあらゆるXDW編集の同一性保証ではない。

## 登録と改訂

`templates/<name>/vNNN/`の定義・manifestは既存テンプレート1.0のままとする。追加の`authoring/`は別契約であり、既存適用APIは従来のmanifestを検証して利用できる。

`authoring/manifest.json`はschema=`docuworks-template-authoring`、schema_version=`1.0`、status=`COMPLETE`、`template_manifest_sha256`、`files`を持つ。filesは`state.json`と固定した`sample-reviewed`の全必要ファイルのSHA-256。`state.json`は設定、見本manifestのハッシュ、本文指紋、作成下書きID、親テンプレートIDを持つ。元環境の絶対パスに依存しない。

改訂では追加契約も検証し、保存した見本と登録済みXDWから下書きを作る。追加契約が存在するのに壊れている場合は従来版扱いへ降格しない。旧版に追加契約がなければ、利用者が選んだReviewedのページ情報を照合し、その作業コピーへ旧版の矩形定義を移す。

項目名や範囲の構造エラー、条件不一致は登録不可。候補なし・空文字・未対応文字方向・由来診断・適用条件なしは明示確認を要する。元データの診断は消去しない。

下書きと登録ルートをプロセス間ロックし、revisionの比較で古い画面からの上書きを拒否する。専用の一時コピーへ属性を設定し、保存・再読込・本文・矩形・定義・ハッシュを検証してから完成フォルダーを一度だけ公開する。失敗時は完成版を表示せず、下書きを保持する。登録完了直後に下書きへの完了記録が失敗しても、保存した下書きIDにより再試行を同じ登録版へ戻す。

## 配布と試験

新規ランチャーは`portable/layout.json`で管理する。ユーザーの`templates/`・`template-drafts/`をPortableの基底ZIPから引き継がない。公開ソースの`portable/templates/`はREADME生成用であり、利用者データのディレクトリと区別する。

DLL不要の保存・改訂・失敗注入試験、実Tkウィジェット試験、実SDKの合成文書試験を分ける。Viewer手操作、実帳票、DocuWorks 9.1の確認は別途必要。今回の範囲にGUIでの矩形描画、自動テンプレート選択、一括適用、CSV作成画面、Excel出力、原本へのマーカー付与は含めない。
