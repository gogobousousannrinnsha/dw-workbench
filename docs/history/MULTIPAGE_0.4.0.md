> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# Integrations 0.4.0：複数ページOCR

## 選択と実行

ocr-xdwは未指定なら1ページ目、--page 3なら3ページ目、--pages 1,3-5なら1・3・4・5ページ、--all-pagesなら全ページを処理します。3種類の選択オプションは同時指定できません。重複は除去し昇順に処理します。空指定、0、負数、逆順・範囲外は画像化・モデル読込み前に拒否します。CLIの数値指定は展開量を制限するため100000以下です。

```powershell
python -m docuworks_integrations ocr-xdw --input-xdw local-data/input.xdw --all-pages --model-root models --run-dir local-data/all-pages
python -m docuworks_integrations ocr-xdw --input-xdw local-data/input.xdw --pages 1,3-5 --model-root models --run-dir local-data/selected-pages
python -m docuworks_integrations mark-region --run-dir local-data/all-pages --region-id p0003-r000001 --output-xdw local-data/marked.xdw --dry-run
```

Pythonではrecognition.ocr_xdw_pages(input_xdw, run_dir, model_root, *, pages=None, dpi=300, dll_path=None, engine=None)を追加しました。pages=Noneは全ページ、指定時は整数列です。既存recognition.ocr_xdw(..., page=1, ...)は単一ページの入口として維持します。workflowの旧形式APIは変更していません。

文書コピーと読み取りハンドルは1回、OCRエンジンは1インスタンスを使い、ページごとに画像化・推論・保存します。各ページの画像配列をまとめてメモリに保持しません。ページ別寸法からpx/mmを換算し、元のページ番号をIDに使います。dpiは選択ページ共通の300または600です。進捗・モデルログはstderr、完成manifestはstdoutです。

## OCR Result 1.1

新規OCRはschema_version="1.1"を保存します。ページごとのrecognition_statusは、領域ありならTEXT_DETECTED、正常推論で0件ならNO_TEXT_DETECTEDです。後者ではregions=[]を許容し、Raw・画像・プレビュー・一覧も保存します。検出0件を白紙と断定しません。全ページ0件でもCOMPLETEになります。

readerは1.0と1.1に対応します。1.0の空ページ禁止は維持し、0.2.0からの移行は1.0のままです。save_ocr_resultは入力の形式版を保持します。旧0.3.0 readerは1.1を読めないため、利用側も0.4.0へ更新してください。

構造定義はパッケージ内のocr-result-1.1.schema.jsonです。manifest構造は維持し、ocrにselected_pages、page_timings、elapsed_secondsを記録します。総ページ数はsource.page_count、処理したページだけがmanifest.pagesに含まれます。ページ3だけを処理してもp0003-r000001を使用します。

JSONLは元ページ番号・領域順に出力します。0件ページはJSONLの行を作らず、全0件なら空ファイルになります。ページ情報はbundleに残ります。マーカーは1回1領域で、複数処理ページの整数選択は拒否します。存在しない領域や0件ページへの選択はSDK呼出し前に失敗します。

## 失敗と公開

SDK・GPU・座標不正・原本変更・中断では停止します。完成manifestは公開せず、run-dir/error.jsonに失敗ページ・段階・完了ページ・時間を保存し、途中データはdiagnostics以下に残します。失敗ページのRawが取れた場合だけ保存し、前ページのRawは転用しません。診断はconsumerから利用できません。再実行には別のrun名を使います。

既存出力は上書きせず、全選択ページ終了後の形式・ハッシュ・原本照合に成功してから完成bundleを公開します。診断の保存自体がストレージ障害等で失敗した場合は一時作業フォルダを残し、元の例外を保持します。

複数文書、並列実行、再開、部分結果利用、回転・傾き補正、一括マーカーは今回の対象外です。Paddle検出器の内部サイズ制限によりA3等は内部で縮小される場合があります。保存画像の寸法と返された元画像座標で変換します。

## 検証の分担

DLL不要CIでページ選択、異寸法、空ページ、1.0/1.1、モデル再利用、途中失敗・中断、結果利用を検証します。既存の公開・配布監査を維持します。
ローカル実機ではA4縦・白紙A4・A3横の3ページを作成し、全ページと非連続ページ、後方ページのマーカー保存を確認します。scripts/create_multipage_fixture.pyは--output-dirと--dll-pathを要求し、利用者のローカル専用文書を生成します。生成データはGitへ追加しません。
今回の実機結果は全ページ1/0/1領域、ページ1・3指定成功、3ページ目マーカーの保存・再オープン成功です。原本と他ページ画像は不変、点列誤差は最大0.003256mm未満でした。Viewerは未確認で、自動検証と分けて記録します。
