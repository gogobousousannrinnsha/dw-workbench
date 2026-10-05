# 1ページ・複数領域の確認用XDW — 0.7.0

現行Integrations 0.7.0のAPI仕様です。開発時の比較基準は履歴に保存しています。
原本重ね合わせ型で、同じページの指定領域を1ページの確認用XDWへ出力します。
**複数領域はSDK往復検証済み。Viewerでは同一文字2領域の片方だけを編集・別名保存し、取り込む正常1ケースを検証済みです。**
操作・再表示は利用者報告、保存後の領域対応・JSONL反映・元データ保全はコード検証です。
複数領域のViewer異常操作は未確認で、形式1.0の1領域版の6ケースとは区別します。
[検証記録](../REVIEW_XDW_REGIONS_VERIFICATION.md)に証跡と確認範囲を記載しています。
この機能はPython APIです。標準OCRのBATには自動接続されていません。

## 公開API

```python
create_review_xdw_regions(run_dir, region_ids, output_dir, *, dll_path=None) -> Path
read_review_edits(run_dir, review_dir, edited_xdw, *, dll_path=None) -> ReviewEditsCandidate
```

どちらの関数とReviewEditsCandidateもdocuworks_integrations直下から遅延importできます。
importには標準ライブラリのみを使用し、実行時にCoreとDocuWorks DLLを読み込みます。
補助資料生成用のPillowはAPIの実行には不要です。

region_idsは領域ID文字列の反復可能オブジェクトです。1件以上が必要で、文字列単体、空指定、
重複、不明ID、異なるページの混在を拒否します。1件だけの指定も形式2.0になります。
入力順にかかわらず、注釈の追加・対応情報・返却候補は保存runの既存領域順に揃えます。

ReviewEditsCandidateは変更不可のデータクラスで、次を保持します。

| 項目 | 内容 |
|---|---|
| run_id、manifest_sha256 | 元runの識別 |
| review_id、review_manifest_sha256 | 確認セットと対応JSONの実バイト列ハッシュ |
| edited_xdw_sha256 | 読み取った編集後XDWのハッシュ |
| corrections | 文字が変わった領域だけのTextCorrectionのtuple |
| unchanged_region_ids | 選択対象のうち文字が変わらなかった領域IDのtuple |

未変更には、文字を動かしただけの領域も含みます。「人が確認済み」を意味しません。
候補のbefore_textは常に保存runから取得します。文字の正規化・トリミングを行いません。

## 形式・照合規則

出力フォルダーにはreview.xdwとreview.jsonを保存します。対応JSONのschemaはdocuworks-ocr-review、
schema_versionは2.0です。共通のrun識別・確認セットID・元ページと確認ページ1の対応・ページ寸法・
生成時の注釈総数と、regions配列のregion_id／original_textを保持します。
形式の機械可読定義はパッケージ内のocr-review-2.0.schema.jsonです。

対象注釈それぞれのDW-OCR.ReviewIdentityに形式2.0の識別情報を格納します。
領域ID、確認セットID、元runとmanifestのハッシュ、対応JSONの実バイト列ハッシュを照合し、
対象IDの集合と各IDがちょうど1個であることを確認します。
ハンドル、列挙順、表示位置、文字の一致・類似は識別に使いません。

原本コピーから対象ページを取り出し、元内容・既存注釈を保持したうえで、対象ごとに12pt・赤字の
テキスト注釈を元領域の左上へ追加します。座標はmmです。縮小・自動配置は行いません。
元ページに予約属性が存在する場合は生成を拒否します。生成時は全対象の文字・位置・寸法・識別を再読込検証します。

取り込みでは移動を許容しますが、ページ数・寸法・注釈総数を維持する必要があります。
対象削除、属性付き／属性なしコピー、識別情報の欠落・破損・重複、別run・別確認セット、種類変更を拒否します。
1件でも構造・識別が不正なら、修正候補を一部だけ返すことはありません。SDK読取失敗もそのままエラーにします。

## 訂正基盤への接続

```python
from docuworks_integrations import (
    read_review_edits, save_corrections, apply_corrections, export_effective_jsonl,
)

# 各パスは明示指定。保存先は元bundle外の新規ファイル。
candidate = read_review_edits(run_dir, review_dir, edited_xdw)
saved = save_corrections(run_dir, candidate.corrections, correction_path)
effective = apply_corrections(run_dir, saved)
export_effective_jsonl(effective, jsonl_path)
```

実際の使用例は[use_review_xdw_regions.py](../../examples/use_review_xdw_regions.py)です。
読み取り後、保存直前にrun・対応JSON・編集XDWの識別を再確認してから、候補全体を渡します。
全件未変更では空修正セットを保存します。空白だけの訂正はread_review_editsの段階では候補に含め、
save_correctionsで拒否します。正常な訂正と空白訂正が混在しても、修正セット全体を保存しません。
文字以外の元領域ID・ページ・順序・座標・信頼度は変更せず、選択対象外の領域も元のままJSONLへ出力します。

入力読取り前後の変更確認と、生成フォルダーの一時保存・再読込検証・確定を行います。
元bundle内への出力、既存出力の上書き、未公開の一時フォルダーを使った取り込みを拒否します。
フォルダー移動後も保存bundleと対応ファイルが揃っていれば利用できます。外部の原本は不要です。
同時編集のロック・履歴統合は提供しません。

形式不正・対象不一致はValueError、入力変更・生成時の保存後不一致はRuntimeError、
不足ファイルはFileNotFoundError、出力衝突はFileExistsError、入出力／SDK失敗はOSErrorやXdwError等です。
後続の保存・JSONL出力は既存corrections APIの例外・保全規則を引き継ぎます。

## 互換性と検証範囲

従来のcreate_review_xdw／read_review_editは形式1.0のままです。
新APIは形式2.0のみを扱い、既存ファイルを自動変換しません。Canonical 1.0／1.1、既存の訂正形式は変更しません。
Core、既存CLI、公開Portableは変更しません。

合成検証runに同じ文字の2領域と選択対象外の1領域を用意し、SDKで片方だけの訂正・両方の訂正・
位置の入替え・未変更・異常操作を検証しました。このrunは実OCR測定結果ではありません。
[検証記録](../REVIEW_XDW_REGIONS_VERIFICATION.md)に試験条件、Python版、配布物の識別を記載します。
複数ページ、白紙型、検索、テンプレート、再OCR、領域の追加・削除・分割・結合は今回の対象外です。
