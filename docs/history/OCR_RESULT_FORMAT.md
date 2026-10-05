> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

0.4.0では新規OCRに形式1.1を使用し、空ページとrecognition_statusを追加しました。1.0も読込み可能です。 詳細は[0.4.0仕様](../MULTIPAGE_0.4.0.md)を参照してください。以下は継承した1.0仕様です。

# OCR Result 1.0 公開契約

## 保存形式

manifest.jsonが完成runの入口です。schema=docuworks-ocr-result、schema_version="1.0"、status=COMPLETEです。未対応版は拒否します。
run_idはUUID。sourceはtype/path/original_path/sha256/page_countを持ちます。移行元に総ページ数がない場合のみpage_count=null、page_count_provenance=unknown-in-legacyです。
ocrは新規実行時にエンジン・パッケージ版・モデル別ファイルハッシュ・Python・device・前処理設定・時間・DLL位置を持ちます。旧runからモデル情報を推測しません。
source/source.xdwは原本コピー。pages/page-0001内にimage.png、raw-paddle.json、result.json、preview.png、regions.mdを保存します。旧runにRawがない場合はraw=nullです。
filesは相対パス→SHA-256です。必須ファイル登録、ハッシュ、bundle外へ抜けるパスを検証します。manifestのハッシュは読込み時に計算し後処理で参照します。ハッシュは署名ではありません。

## 座標とID

ページは元文書の1始まり番号、page_width_mm/page_height_mm、image_width_px/image_height_px、render_dpi、image/raw/preview/listingの相対パス、regionsを持ちます。coordinate_system=top-left-x-right-y-down、rotation=0です。
領域はid/text/confidence/polygon_px/bbox_px/polygon_mm/bbox_mmを持ちます。polygonは周回順の4組の[x,y]、bboxはx/y/width/heightです。自交差・面積0・画像外を拒否します。confidenceは0〜1またはnull。空白のみの文字列は拒否しますが、文字列の正規化やtrimはしません。
mm=px×page_size_mm/image_size_pxです。dpi単独から換算しません。pxと保存mm、四隅と外接矩形は1e-7以内の一致を要求します。SDK向け0.01mm丸めは注釈保存時だけです。
IDはp0001-r000003形式。ページ番号と保存順序から決まり、移行時に並べ替えません。複製・移行は同じrun_idを維持し、別OCRは新run_idを生成します。後処理は(run_id, region_id, manifest_sha256)で参照します。
構造定義はocr-result-1.0.schema.jsonです。JSON Schema以外に、実装で座標整合性、IDの一意性、ページ対応、ファイルハッシュを検証します。

## Python API

以下はdocuworks_integrationsからimportできます。共通形式は標準ライブラリだけで動きます。

- load_ocr_result(run_dir) -> OcrDocumentResult：新旧runを検証して読込み。外部原本の存在は不要。
- save_ocr_result(result, output_dir, *, assets=None, expected_hashes=None) -> OcrDocumentResult：新規bundleを一時保存後に公開。assetsは相対パス→既存ファイル辞書。ロード済み結果の複製時は省略可能、新規型の保存時は必須。expected_hashesは期待ハッシュ辞書。
- get_region(result, region_id) -> CanonicalOcrRegion：文字列IDで選択。整数と数字文字列は1処理ページのみ許容。
- export_jsonl(result, output) -> Path：保存済み結果を再検証し、run_id/manifest_sha256/pageと領域情報を1行ずつ出力。bundle外の新規ファイルを指定。

OcrDocumentResultはrun_id/source/ocr/pages/schema_versionと、ロード時のroot/manifest_sha256を持ちます。OcrPageResultとCanonicalOcrRegionは対応JSONと同名のフィールドです。dataclass内の辞書は変更せず値として扱い、分析結果は別に保存してください。
不正形式・座標・IDはValueError（構造によってTypeError/KeyError）、変更はRuntimeError、欠落はFileNotFoundError、既存出力はFileExistsErrorです。
OCR失敗・0件はerror.jsonを持つ診断ディレクトリを残し、完成manifestや注釈を作りません。

## 利用層と互換性

consumers.mark_region(run_dir, region_id, output_xdw, *, dry_run=False, dll_path=None, input_xdw=None)は共通形式から既存のマーカー計画・実行機能を呼びます。原本とbundleを再検証します。
マーカーは黄色・透過・水平2点、線幅は領域高さをptへ換算し四捨五入した整数、最小1ptです。
既存のOcrRegionと注釈APIは維持しています。workflowモジュールの旧関数はPython互換口、新CLIはrecognition/results/consumersを使います。
