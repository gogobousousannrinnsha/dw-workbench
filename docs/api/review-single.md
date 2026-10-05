# 1ページ・1領域の確認用XDW — 0.7.0

正式版0.7.0はd31c2cbの機能を維持しています。以下の比較基準は各機能の開発履歴です。

保存済みOCRの1領域を、原本の対象ページと重ねた編集用テキストとしてXDWへ出し、
編集後の文字を既存の修正基盤へ渡すPython APIです。比較基準は `fd9e8a4`、Coreは1.0.0のままです。
**1ページ・1領域・原本重ね合わせ型のSDK往復と、Viewer編集・別名保存後の取り込みを検証済みです。**
Viewerの表示・操作は利用者確認、保存後の領域識別・JSONL出力はコードによる確認として、[検証記録](../REVIEW_XDW_VERIFICATION.md)に分けて記載しています。

## 使い方

```python
from pathlib import Path
from docuworks_integrations import (
    create_review_xdw, read_review_edit, load_ocr_result,
    save_corrections, apply_corrections, export_effective_jsonl,
)

run_dir = Path("work/run")
review_dir = create_review_xdw(
    run_dir, "p0003-r000001", "work/review-001",
    # dll_path=...  # 必要な場合は使用する製品DLLを明示する
)

# review-001/review.xdwを別ファイルへコピーして編集・保存する。
# 最初の自動試験ではSDKで編集する。Viewer操作の検証は別途行う。
candidate = read_review_edit(run_dir, review_dir, "work/edited.xdw")
source = load_ocr_result(run_dir)
if (source.run_id, source.manifest_sha256) != (candidate.run_id, candidate.manifest_sha256):
    raise RuntimeError("元runが変わりました")

output = Path("work/revision-002")
output.mkdir(exist_ok=False)
edits = [] if candidate.correction is None else [candidate.correction]
saved = save_corrections(run_dir, edits, output / "corrections.json")
effective = apply_corrections(run_dir, saved)
export_effective_jsonl(effective, output / "effective.jsonl")
```

run・領域IDは実際の保存結果に合わせます。runの場所は明示し、近くのファイルを自動採用しません。
[実行例 use_review_xdw.py](../../examples/use_review_xdw.py) は `prepare()` と `finish()` を提供します。
finishは元runに加え、対応JSONと編集XDWのハッシュも保存直前に再確認します。
製品CLI、BAT、settings.iniへのコマンド追加はありません。

## APIと責任範囲

| 公開API | 契約 |
|---|---|
| `create_review_xdw(run_dir, region_id: str, output_dir, *, dll_path=None) -> Path` | 新規確認フォルダーを生成し、絶対Pathを返す。親フォルダーは既存であること |
| `read_review_edit(run_dir, review_dir, edited_xdw, *, dll_path=None) -> ReviewEditCandidate` | 対応する編集済みXDWを読み取り専用で検証し、一領域の候補を返す |

パス引数はstrまたはPathです。領域IDは完全な文字列IDを指定します。整数の略記は受け付けません。
readでは対応JSONと指定したedited_xdwを読みます。初期review.xdwのハッシュは、編集後の照合には使用しません。
したがって別名保存・移動後も使えます。元runと対応JSONの位置が変わった場合も、新しいパスで呼び直します。

戻り値 `review_xdw.ReviewEditCandidate` はfrozen dataclassで、次を保持します。

| フィールド | 意味 |
|---|---|
| `run_id`, `manifest_sha256` | 読み取った元OCR結果の識別情報 |
| `review_id` | 確認セットごとのUUID |
| `review_manifest_sha256` | review.jsonの実バイト列のSHA-256 |
| `edited_xdw_sha256` | 読み取った編集済みXDWのSHA-256 |
| `correction` | `TextCorrection`、または元文字と同じ場合の`None` |

候補のbefore_textは元runから取得します。XDWの文字が空・空白のみでも候補の読み取り自体は行い、
訂正としての拒否は既存 `save_corrections()` が担当します。未編集の場合は空の修正セットを保存できます。
利用用結果・座標・信頼度・JSONLの仕様は [訂正基盤](../CORRECTIONS_0.7.0.md) を引き継ぎます。

## 確認セットと識別情報

確認フォルダーには `review.xdw` と `review.json` を保存します。
元bundle内への出力、既存出力の上書き、内部用 `.review-<32桁hex>` というフォルダー名は拒否します。
一時フォルダーで生成・保存・再読込検証した後にフォルダー全体を確定します。
失敗時はこの処理が作った一時フォルダーだけを掃除します。原本・元bundle・既存出力は削除しません。

XDWは元run内の原本コピーから対象ページを `XDW_GetPageW` で取り出します。
元ページが3ページ目でも確認XDWは1ページ目です。元内容と既存アノテーションを保持し、
元領域の左上へ12pt・赤字のテキストを1個追加します。自動縮小、折返し幅の調整、配置最適化は行いません。
ページ寸法と初期位置は保存・再読込後に0.01mm以内で照合します。

`review.json` の識別名は `docuworks-ocr-review`、形式版は `1.0` です。
status=COMPLETE、review_id、run_id、manifest_sha256、region_id、original_text、source_page、
review_page=1、page_width_mm、page_height_mm、annotation_countを持ちます。絶対パスは保存しません。

対象テキストの任意データ属性 `DW-OCR.ReviewIdentity` にUTF-8 JSONバイト列を保存します。
識別名は `docuworks-ocr-review-identity`、形式版は `1.0`。
review_id、run_id、manifest_sha256、region_idとreview_manifest_sha256を保持します。
対応JSONの書式だけを変えてもハッシュが変わるため、対応が崩れたものとして拒否します。
両形式の [JSON Schema](../../packages/docuworks-integrations/docuworks_integrations/ocr-review-1.0.schema.json) を同梱します。
ハッシュは内容の照合用であり、署名や編集者認証ではありません。

## 取り込み時の検証

- 元runの全必須ファイルを既存ローダーで検証し、対応JSONの元run・領域・元文字・ページ寸法を照合。
- 確認XDWは1ページのみとし、子アノテーションを含めて列挙。対応属性を持つ対象がちょうど1個のテキストであることを要求。
- 対象の識別情報と対応JSONのハッシュを照合し、注釈総数が生成時と同じであることを確認。
- 対象削除、属性欠落・破損・重複、別run・別確認セット、対象種類変更、ページ追加、注釈追加を拒否。
- 対象テキストの移動は許容。出力座標には移動後の表示位置を使わず、元OCR座標を維持。
- 読み取り前後で元run、対応JSON、編集済みXDWが変わっていないことを再確認。

元ページに `DW-OCR.ReviewIdentity` が既に存在する場合は、空の属性でも生成を拒否します。
初回サイズ取得での「属性が存在しない」応答だけを区別し、他のSDKエラー、データ取得時のエラー、
二段階読込でのサイズ変化は隠しません。検証環境では未存在属性の応答は `XDW_E_INVALIDARG` でした。
他の製品版で異なる応答が返る場合は、その版の確認なしに読み飛ばしません。

同時編集のロック、複数人の履歴統合、位置や文字の類似による復元は提供しません。
対象テキストの文字変更・移動だけを行い、それ以外の構造変更は避けてください。

## 例外・依存・検証範囲

不正な対応や構造にはValueError、読み取り中の変更や保存後の不一致にはRuntimeErrorを返します。
不足ファイルはFileNotFoundError、既存出力はFileExistsError、I/O障害はOSError、
SDKの処理失敗は既存CoreのXdwError等をそのまま伝えます。文字訂正の例外は訂正基盤の契約を継承します。

APIのimportは標準ライブラリだけで可能です。XDWの生成・読取り実行時だけCoreとDocuWorks DLLを読み込みます。
GPU、Paddle、PillowはXDW往復に不要です。実機試験はPython 3.13で行います。
3.10は訂正基盤・新規ロジックのDLL不要試験、3.11〜3.13は既存回帰も含めて確認します。
3.10でライブラリ全体やSDK往復が検証済みという表記はしません。

仕様根拠: DocuWorks SDK 9.1.7同梱XDWAPI.xdwの2.36、2.118、8.10、および同梱ヘッダー。
Viewerから直接操作できない任意データ属性を使用しますが、Viewerで編集・保存した際の保持は別途検証が必要です。
実機の製品・DLLの版、試験件数、配布物検証は [検証記録](../REVIEW_XDW_VERIFICATION.md) に記録します。

## Viewer確認手順

実施状況と保存後ファイルの検証結果は [検証記録](../REVIEW_XDW_VERIFICATION.md#viewer確認の追記2026-09-12) を参照してください。

1. 生成したreview.xdwのコピーをViewerで開き、赤いテキストを編集する。
2. 別名保存し、一度閉じて再度開く。文字を移動したケースも別ファイルとして保存する。
3. read_review_editで取り込み、元の領域ID・元座標と訂正文を確認する。
4. 属性付きコピー・削除・空欄のケースについて、取り込み／訂正保存の拒否を確認する。
5. 表示、編集、別名保存後の再表示、識別情報保持を別項目で記録する。

SDK試験での成功だけではこの手順を確認済みにしません。
白紙型、複数領域、検索、手動テンプレート、再OCR、分割・結合は対象外です。
