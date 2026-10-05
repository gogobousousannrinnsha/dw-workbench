# OCR文字訂正基盤 0.7.0

正式版0.7.0はd31c2cbの機能を維持しています。以下の比較基準は各機能の開発履歴です。

保存済みrunの文字をPythonから訂正し、元結果を変更せずに利用用結果とJSONLを生成します。
開発版57cf72a / Integrations 0.6.0への追加機能です。Coreは1.0.0のままです。
ライブラリの版、修正JSONの形式版1.0、元OCRの形式版1.0/1.1は別のものです。

## 最初の利用例

既存のPython環境に開発版wheelを導入して使います。修正処理そのものは標準ライブラリだけで動き、
GPU、Paddle、Pillow、DocuWorks DLL、Coreのimportを必要としません。
パッケージの導入依存 `docuworks-ctypes>=1.0,<2` は従来どおり維持します。

```python
from pathlib import Path
from docuworks_integrations import (
    load_ocr_result, get_region, TextCorrection,
    save_corrections, load_corrections, apply_corrections,
    export_effective_jsonl,
)

run_dir = Path("work/run")              # 既存の保存run
output_dir = Path("work/revision-001")  # 元runの外側
output_dir.mkdir(exist_ok=False)
original = load_ocr_result(run_dir)
region = get_region(original, "p0001-r000003")
print(repr(region.text))                # 元の文字・前後空白を確認する

# before_textは確認した元OCR文字を完全一致で指定する。
corrections = save_corrections(
    run_dir,
    [TextCorrection("p0001-r000003", "A8-100", "AB-100")],
    output_dir / "corrections.json",
)
saved = load_corrections(corrections.path)
effective = apply_corrections(run_dir, saved)
export_effective_jsonl(effective, output_dir / "effective.jsonl")
```

領域ID・元文字は実際のrunに合わせて指定してください。不一致なら訂正を保存しません。
実行可能な例は [correct_saved_ocr.py](../../examples/correct_saved_ocr.py) です。
この例は単一訂正を扱います。APIは複数領域を一つの修正セットとして扱います。
既存の製品CLI、BAT、settings.iniには変更を加えていません。

## Python API

以下はすべて `docuworks_integrations` からimportできます。パス引数は文字列またはPathです。

| API | 戻り値・動作 |
|---|---|
| `TextCorrection(region_id: str, before_text: str, after_text: str)` | 一領域の訂正。保存時に検証する値型 |
| `save_corrections(run_dir, edits, output) -> CorrectionSet` | TextCorrectionの反復可能オブジェクトを検証し、新しいJSONへ保存 |
| `load_corrections(path) -> CorrectionSet` | JSON形式・内容を検証し、同じ読込バイト列のSHA-256を計算。元runとの照合は適用時 |
| `apply_corrections(run_dir, corrections: CorrectionSet) -> EffectiveOcrResult` | 保存済み修正セットを再読込・照合して、訂正後のスナップショットを生成 |
| `export_effective_jsonl(result: EffectiveOcrResult, output) -> Path` | 元run、修正JSON、利用用結果を再検証し、新しいJSONLへ保存 |

整数による領域指定は修正APIでは受け付けません。`p0001-r000003` のような文字列IDを指定します。
apply/exportには保存ファイルが必要です。保存していない自作CorrectionSetは利用しません。
`save_ocr_result()` や既存の `export_jsonl()` には元のOcrDocumentResultを渡します。
EffectiveOcrResultはその代用品ではありません。修正後JSONLは専用APIで出力します。

### 型と情報の意味

- `CorrectionSet`: `correction_set_id`, `run_id`, `manifest_sha256`, `edits`（tuple）, `path`（絶対Path）, `correction_set_sha256`, `schema_version`。
- `EffectiveOcrResult`: `run_id`, `manifest_sha256`, `correction_set_id`, `correction_set_sha256`, `source`, `ocr`, `pages`, `schema_version`（元OCR形式版）, `root`（元runの絶対Path）, `corrections`。
- `EffectiveOcrPage`: OcrPageResultと同じページ属性を持ち、`regions` はEffectiveOcrRegionのtuple。
- `EffectiveOcrRegion`: `id`, `text`, `confidence`, `polygon_px`, `bbox_px`, `polygon_mm`, `bbox_mm`, `original_text`, `is_corrected`。

`text` は利用する文字、`original_text` は元OCR文字です。`is_corrected` は訂正の有無であり、
未訂正を確認済みと扱いません。`confidence` は訂正後も元OCRの信頼度（0〜1またはNone）です。
ページ番号は元文書の1始まり。座標・px/mmの単位・領域ID・順序は元結果をそのまま引き継ぎます。

型はfrozen dataclassですが、bbox、source、ocr内の辞書まで読み取り専用になるわけではありません。
元結果と可変データは共有せず、利用用結果内の辞書を含む改変は出力時の再構築・比較で拒否します。
値は読み取り専用として扱い、訂正の追加は新しい修正セットを作ってください。

## 修正JSON 1.0

識別名は `docuworks-ocr-corrections` です。
構造は [JSON Schema](../../packages/docuworks-integrations/docuworks_integrations/ocr-corrections-1.0.schema.json) を参照してください。

| フィールド | 契約 |
|---|---|
| `schema`, `schema_version` | 識別名と文字列 `1.0` |
| `correction_set_id` | 保存ごとに新規生成するUUID |
| `run_id`, `manifest_sha256` | 元runの識別子とmanifestのSHA-256 |
| `edits` | `region_id`, `before_text`, `after_text` を持つ配列 |

JSONに場所情報や計算済みの自己ハッシュは保存しません。対応付けはIDとハッシュで行います。
SHA-256は内容の同一性の検査であり、署名や編集者の認証ではありません。
旧runでは既存ローダーが生成するrun_idと、run.jsonのハッシュを使います。
Canonical形式への変換後はmanifestが変わるため、変換前の修正セットは自動移行しません。

未知フィールド、重複JSONキー、NaN/Infinity、未対応版、不正ID・ハッシュ、同一領域の重複を拒否します。
元文字は完全一致で照合し、空文字・空白のみ・変更前後が同じ訂正を拒否します。
日本語、改行、引用符、前後空白は保持し、正規化やtrimはしません。UTF-8で表せない孤立サロゲートは拒否します。
空の修正配列は有効です。領域の削除、座標変更、分割・結合、確認状態の管理は含みません。

## 修正後JSONL

一領域一行。ページ番号の昇順、各ページの元の領域順で全領域を出力します。
識別名は `docuworks-ocr-effective-region`、形式版は `1.0` です。
[行のJSON Schema](../../packages/docuworks-integrations/docuworks_integrations/ocr-effective-region-1.0.schema.json) を同梱しています。

各行には元JSONLの `run_id`, `manifest_sha256`, `page` と領域属性に加え、
`schema`, `schema_version`, `original_text`, `is_corrected`, `correction_set_id`, `correction_set_sha256` を含めます。
未訂正領域も同じ来歴を持ちます。文字がないページは行を生成しません。
全ページに文字がない場合は0バイトのJSONLです。その場合の来歴は修正JSONとEffectiveOcrResultに保持されます。
修正セットを指定しない既存 `export_jsonl()` は引き続き元OCR文字を出力します。

## 保存・移動・再訂正

元runの全ファイルは変更しません。修正JSON・JSONLは元bundle外の新規ファイルに限定し、
出力の親フォルダーは呼出し側で作成します。既存ファイルやリンク先への上書きを拒否します。
一時ファイルへの書込み・flush/fsyncの後、入力を再検証して、上書きしない方法で確定します。
書込み・検証・確定が失敗した場合は、一時ファイルだけを掃除し、既存成果物を削除しません。
掃除にも失敗した場合は元の例外を保持し、一時ファイルが残る場合があります。
元runや修正JSONを同時に編集する運用は対象外です。入力のロックや複数人編集の統合は提供しません。

フォルダーを移動した後は、新しいrunパスと修正JSONパスでload/applyをやり直します。
元runの内部ファイルが揃っていれば、OCR時の外部原本やGPU環境は不要です。
読み込み済みオブジェクトのroot/pathを書き換えて再利用しないでください。

再訂正時は元OCR文字をbefore_textにして新しい修正セットを作ります。
前回の訂正も維持するなら、残したい訂正をすべて新しいeditsへ明示してください。
二つの修正セットを順番に重ねたり、近隣ファイルを自動採用したりしません。

### 主な例外

| 例外 | 原因 |
|---|---|
| `ValueError` | 不正形式・ID・文字、別run、before_text不一致、元bundle内への新規出力など |
| `RuntimeError` | 元bundleのハッシュ不一致、読込後の修正ファイル変更、利用用結果の改変 |
| `FileNotFoundError` | 入力ファイルまたは出力親フォルダーがない |
| `FileExistsError` | 出力先が既に存在する（同時作成を含む） |
| `OSError` | 権限、容量、fsync、確定処理の失敗 |

不正UTF-8はUnicodeError（ValueErrorの派生）になります。元runの読込みは既存ローダーの例外契約を継承します。
一件でも不正なら修正セット全体を拒否し、部分適用しません。

## 検証と機能の境界

確認用XDWとの接続は実装済みです。[複数領域レビュー](review-regions.md)を参照してください。標準BATへの自動接続・検索・テンプレートは未実装です。検証履歴と今回の確認は[検証案内](../history/README.md)で区別します。
