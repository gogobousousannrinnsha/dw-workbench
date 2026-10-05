# Structured ResultのCSV出力

Portable候補での操作順は[テンプレートからCSVまで](user/template-csv.md)を参照してください。

同じ登録テンプレートを使ったStructured Resultを、1文書の結果につき1レコードで
CSVへまとめます。既存のStructured Result 1.0を読み込み、取得値・診断・結果IDを
出力します。正本のJSONや元文書を変更せず、DocuWorks・Excel・GPUは不要です。

## 列と行

| 文書名 | 処理結果 | 部品番号 | 温度 | 確認事項 | 結果ID |
| --- | --- | --- | --- | --- | --- |
| 帳簿001.xdw | 正常 | 001234 | 80℃ | | Structured ResultのUUID |
| 帳簿002.xdw | 要確認 | | 75℃ | 部品番号の候補なし | Structured ResultのUUID |
| 帳簿003.xdw | 適用不可 | | | 帳票の条件が不一致 | Structured ResultのUUID |

固定列は先頭の「文書名」「処理結果」と末尾の「確認事項」「結果ID」です。
間に取得項目をテンプレートの出力順で並べます。明示した出力順が先で、
同順位・未指定はページ順・矩形順です。適用不可だけの一覧でも全項目の列を残します。

取得項目名が固定列と重なる場合だけ、CSV見出しに「項目:」を付けて区別します。
別の項目名とも重なる限り繰り返します。例えば「文書名」と「項目:文書名」が
既にあるなら、前者を「項目:項目:文書名」とし、後者の見出しは維持します。
テンプレートの項目名やStructured Result自体は変更しません。

- 入力として指定した順に出力します。文書名・日時による自動並べ替えはしません。
- 結果は1件以上必要です。同じ結果IDの重複はエラーです。
- 登録テンプレートのID・定義ハッシュ・manifestハッシュが異なる結果は混ぜません。
  同名でも再登録した版は別CSVにします。
- 同一文書を再取り込み・再抽出した場合、出力する結果は利用者が選びます。
  フォルダーを自動探索して最新結果を選ぶ機能はありません。

## 値・状態・文書名

値は文字列のまま出します。先頭ゼロ、全角・半角、前後空白、改行、単位を保持し、
数値化・単位分離・文字列を数式で包む処理はしません。

処理結果はStructuredのok=正常、needs_review=要確認、not_applicable=適用不可です。
候補なし・結合未対応の値は空欄にし、空文字・空白だけの値はそのまま保持します。
確認事項には候補なし、空文字、回転・縦書き、由来情報の不正、ページ・条件不一致、
ページ情報だけの適用判定などを日本語で記録します。適用条件が不一致の場合は
条件名・期待文字・取得文字も残します。任意項目の欠落など、確認事項があっても
Structuredの状態が正常なら、その状態を変更しません。

文書名は利用者が明示する表示名です。保存先フォルダー名やreview.xdwから
原本名を推測しません。APIでは「結果ID→文書名」の対応を全件指定します。
欠落・余分なID・空の名前は拒否し、同名の文書は結果IDで区別できます。
この表示名自体が原本の照合を保証するものではありません。

取得元の項目、座標、originなどの詳細はStructured Resultへ保持します。
結果IDはその正本へ戻る手掛かりです。CSVの編集を正本へ取り込む機能はありません。

## ファイル形式とExcel

UTF-8（BOM付き）、カンマ区切り、レコード区切りCRLF、全項目をダブルクォートで
囲みます。値の引用符は2つへエスケープし、カンマ・改行は引用符内に保持します。
値の改行があるため、1文書1レコードが複数の物理行になる場合があります。

CSVはセルの型を指定できません。引用符で囲んでも、Excelで直接開くと先頭ゼロの
除去や日付・数式への解釈が起こり得ます。Excelの［データ］→［テキスト/CSVから］で
取り込み、自動型変換を適用する前に、取得値の列を文字列として扱ってください。
一覧・出力値を確認してから必要な列だけ数値化します。

参考: [MicrosoftのUTF-8 CSVの説明](https://support.microsoft.com/en-us/excel/opening-csv-utf-8-files-correctly-in-excel)、
[先頭ゼロの保持](https://support.microsoft.com/en-gb/excel/keeping-leading-zeros-and-large-numbers)。

## 開発用コマンド

出力先の親フォルダーを先に作り、新しい.csvファイルを指定します。
`--entry`に結果フォルダーと文書名を対で指定し、文書ごとに繰り返します。

```text
python -m docuworks_integrations export-structured-csv --entry structured/result-001 帳簿001.xdw --entry structured/result-002 帳簿002.xdw --output exports/帳簿A.csv
```

空白を含むパスや名前は引用符で囲んでください。日本語の標準出力・標準エラーの
リダイレクトはUTF-8です。終了コードは0=全件正常、2=出力成功だが要確認または適用不可を
含む、1=読込み・検証・保存の失敗です。コード2でもCSVは完成しています。

入力が破損、不正、出力中に変更された場合は全体を中止します。完成済みCSVの上書きや
保存済み結果の内部への出力は拒否します。途中のCSVは公開せず、検証後に新しい出力先へ
確定します。自動追記はありません。

## Python API

```python
from docuworks_integrations import load_structured_result, export_structured_csv

a = load_structured_result('structured/result-001')
b = load_structured_result('structured/result-002')
output = export_structured_csv(
    [a, b],
    'exports/帳簿A.csv',
    document_names={a.result_id: '帳簿001.xdw', b.result_id: '帳簿002.xdw'},
)
```

戻り値は出力先のPathです。結果は出力前と確定前に再検証します。
元のCanonical・Reviewed・登録テンプレートのフォルダーがなくても、独立した
Structured Resultの保存フォルダーが揃っていれば出力できます。

今回の範囲はCSV出力のAPI・開発用コマンドです。XLSX、Portableへの組込み、
現地運用確認、マーカーとの連携は後続工程です。
