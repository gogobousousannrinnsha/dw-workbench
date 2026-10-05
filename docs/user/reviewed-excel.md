# 校正結果の全文をExcelへ出力

1. 校正用XDWをViewerで編集・保存して閉じ、`校正結果取込.bat`でReviewedを作成します。
2. `全文Excel出力.bat`を起動します。
3. `reviewed.json`がある結果フォルダーを選びます。取込で作成された`result-日時-ID`を選んでください。
4. 完了と保存先を確認します。Excelは選択した結果フォルダーの隣に新規保存されます。

結果フォルダーや`reviewed.json`をBATへドロップする操作も使えます。選択キャンセル時は何も作成しません。
ファイル名は`結果フォルダー名_全文_日時_ID.xlsx`です。再出力は別ファイルとなります。

## 内容

- **全文一覧**: 通常テキストアノテーション1個につき1行。ページ、取得順、本文、分割番号・総数、位置・寸法(mm)、書字方向、回転、項目ID、原本参照状態、確認事項を保存します。
- **文書・ページ情報**: 結果ID、形式、日時、入力ハッシュ、検証内容、付箋除外数、件数と全ページの寸法・文字項目数を保存します。空ページも残ります。

並び順はページ、取得順、分割番号です。取得順はSDKの取得順であり、文章の読み順ではありません。
本文は文字列として保存します。先頭ゼロ・長い番号・数式に見える文字・URL・Unicode・改行・前後空白を自動変換しません。
同じ文章や空文字の項目も残します。`EMPTY_TEXT`は空文字・空白だけの項目、`ORIGIN_...`は原本参照の診断で、本文の除外は行いません。
原本参照状態は保存形式の値を表示します（`matched`: 有効、`none`/`missing`: 参照なし、`invalid`: 不正、`foreign`: 対応外、`partial`: 一部不正、旧形式`duplicate`: 参照重複）。

長文はセルの上限（32,767 UTF-16単位・253改行）以内に分割します。同じ項目IDの本文を分割番号順に、区切りを追加せず連結すると元の文字列に戻ります。
一覧が1シートの行数上限を超えた場合は`全文一覧_2`以降へ続きます。セルの表示高は制限しているため、長い本文は数式バーでも確認してください。

## 対象と制限

対象はReviewedに収録された通常テキスト全件です。Reviewed 2.0の付箋メモは取込時に除外されており、このExcelには入りません。
画像や元の書式の再現、読み順推定、帳票のセルへの自動再配置、ExcelからReviewedへの逆取込はありません。
Reviewed 1.0/2.0、一括・分割の両作成方式に対応します。旧形式にない付箋除外数は「記録なし」と表示します。
出力時にOCR・GPU・DocuWorks SDK・Excel本体は不要です。元のReviewedは変更しません。

入力破損・処理中の変更、出力先の権限・容量不足、Excelで表現できない制御文字がある場合は、エラーを表示して完成品を作りません。
一時ファイルは出力先の隣に作り、通常の失敗・中断時は自分の一時領域のみ削除します。強制終了や削除失敗では残ることがあります。
ライブラリ不足は`repair_project_wheels.bat`で修復できます。処理中の入力を移動・編集しないでください。

## API・CLI

Python環境には`docuworks-integrations[xlsx]`を導入します。PortableにはXlsxWriterを同梱します。

```python
from docuworks_integrations import load_reviewed_result, export_reviewed_xlsx
result = load_reviewed_result("reviewed/result-example")
export_reviewed_xlsx(result, "reviewed/result-example_全文.xlsx")
```

```text
docuworks-integrations.bat export-reviewed-xlsx --reviewed-dir "reviewed/result-example" --output "reviewed/result-example_全文.xlsx"
```

任意のAPIコールバック`progress(phase, current, total)`のphaseは`validate`/`write`/`save`/`verify`です。完了はAPI正常終了後に通知してください。
CLI終了コードは成功0、失敗1、中断130です。Portableの選択キャンセルは0です。
