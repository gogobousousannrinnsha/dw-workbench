# 矩形テンプレート 1.0

Portable候補での操作順は[テンプレートからCSVまで](user/template-csv.md)を参照してください。

1つのXDWへ複数の四角形アノテーションを配置します。ページに直接置いた
四角形だけが対象です。Viewerの［プロパティ］→［ユーザー定義］で以下の属性を設定します。

| 属性名 | 属性の種類 | 値・既定値 |
| --- | --- | --- |
| 用途 | 文字列 | `取得` または `適用判定`。必須 |
| 項目名 | 文字列 | 必須。同じ用途の中で重複不可 |
| 期待文字 | 文字列 | 適用判定用のみ必須。前後の空白なし |
| 必須 | 有無 | 取得用。省略時は有 |
| 出力順 | 整数 | 取得用。1以上。省略可 |
| 結合方法 | 文字列 | `連結`・`空白`・`改行`。省略時は連結 |

取得用の矩形が1つ以上必要です。通常の文字・付箋は無視しますが、四角形の
属性漏れ、四角形以外へのテンプレート属性、付箋・グループ内の矩形や
テンプレート属性は登録エラーです。ページ外の矩形や回転ページも未対応です。

```python
from docuworks_integrations import register_rectangle_template, load_rectangle_template

template = register_rectangle_template('帳簿A.xdw', 'templates/帳簿A-001')
template = load_rectangle_template('templates/帳簿A-001')
```

登録は元XDWを変更せず、保存済みXDWの固定コピー・定義JSON・ハッシュ付きmanifestを
新しいフォルダーへまとめて保存します。既存フォルダーへの上書きはできません。
修正後は別フォルダーへ再登録します。登録だけがDocuWorks SDKを必要とし、
保存済み定義の読込みはSDK不要です。JSON Schemaと追加の整合性検証を併用します。

座標は原本のCanonical座標ではなく、校正後のReviewed座標へ適用する契約です。
SDKによる合成文書の保存・再読込み検証と、Viewerでの手操作確認は別に扱います。

## 適用と取得の規則

- ページ数、0.01mm単位で四捨五入したページ寸法、ページ回転を比較します。
  自動拡大縮小・位置補正はしません。現在は回転なしのテンプレートのみ登録可能です。
- 適用判定用の矩形で得た文字列の前後空白だけを除き、期待文字と完全一致させます。
  内部空白や全角・半角は変換しません。複数条件はすべて一致が必要です。
  条件がない場合はページ情報のみの判定であることを警告します。
- 適用不可なら取得項目を出力せず、不一致理由と判定に使った候補を残します。
- Reviewedの文字枠の中心が矩形内にある項目を選択します。境界上も含めます。
  文字列を部分的に切り取りません。重なる複数矩形が同じ項目を取得しても構いません。
- 中心Y順で走査し、行の先頭項目との中心Y差が小さい方の高さの半分以内なら
  同じ行へまとめます。行の基準は更新しません。行は上から下、行内は左から右、
  同位置ならReviewedの既存順です。結合時も各項目の文字は変更しません。
- 取得候補に回転文字または縦書きがあれば、自動結合せず候補を残して要確認にします。
- 候補なし（missing）と空文字・空白だけ（empty）は区別します。必須項目なら要確認です。
  由来情報の欠落・不正があっても文字を保持し、元の情報と診断を保存します。
- 出力順の指定がある取得項目を先に並べます。同順位・未指定はページ順、矩形順です。
- テンプレート適用の成功によってReviewedのページ構造検証済みフラグを変更しません。

## 登録・確認・適用

以下は開発用Python環境で実行します。出力先の親フォルダーは先に作り、毎回新しい
出力フォルダーを指定してください。

```text
python -m docuworks_integrations register-template --template-xdw 帳簿A.xdw --output-dir templates/帳簿A-001
python -m docuworks_integrations check-template --template-dir templates/帳簿A-001
python -m docuworks_integrations check-template --template-dir templates/帳簿A-001 --reviewed-dir reviewed/result-001
python -m docuworks_integrations apply-template --template-dir templates/帳簿A-001 --reviewed-dir reviewed/result-001 --output-dir structured/result-001
```

`register-template`は`--name`と`--dll-path`を指定できます。
`check-template`は登録内容を検証して表示します。`--reviewed-dir`指定時は抽出結果も
保存せず表示します。`apply-template`は日本語の結果表示に加え、独立した結果を保存します。
これら3コマンドと共通ヘルプのリダイレクト出力はUTF-8です。
終了コードは0=正常、2=適用不可または要確認、1=入力不正・処理失敗です。
適用不可・要確認でも有効な診断結果を保存します。入力不正や保存失敗は未完成の結果を公開しません。

```python
from docuworks_integrations import apply_rectangle_template, load_structured_result

result = apply_rectangle_template('templates/帳簿A-001', 'reviewed/result-001', 'structured/result-001')
result = load_structured_result('structured/result-001')
for field in result.data['fields']:
    print(field['name'], field['value'], field['status'])
```

## Structured Result 1.0

1文書につき1結果です。`structured.json`を正本とし、`structured.jsonl`は同じ内容を
1行にした派生物です。適用不可の結果も1行として保持します。

| 保存ファイル | 内容 |
| --- | --- |
| structured.json / structured.jsonl | 適用可否、状態、条件判定、項目名・値、診断、取得候補 |
| template.json / template-manifest.json | 使用したテンプレート定義と登録時manifest |
| reviewed.json / reviewed-manifest.json | 入力Reviewedの全項目と保存時manifest |
| identity.json / session.json | Reviewedの識別情報とReview Session定義 |
| manifest.json | COMPLETE状態、保存ファイル一覧とSHA-256 |

項目ごとの`sources`に取得元の`result_id`、ページとページID、Reviewed項目全体を保存します。
`item_id`、結合前の文字、既存順序、位置、複数originまたは旧形式originも保持します。
回転・縦書きのため結合しなかった候補も残します。値が`null`のmissing/unsupportedと、
空文字などのemptyは区別できます。originの診断だけでは取得を中止しません。

Structuredの読込みでは保存された定義とReviewedから抽出を再計算し、正本・派生JSONL・
候補・参照情報の一致も検証します。元のCanonical、Review Session、テンプレートの
登録フォルダー、入力Reviewedがなくても読めます。大きなXDWは重複コピーせず、その
ハッシュを元manifestに保持します。したがってオフライン読込みが検証するのは保存された
JSONの整合性であり、手元にない元XDWの現物ではありません。

新しいUUIDとフォルダーへまとめて保存し、既存結果・入力の内部への書込みは拒否します。
入力変更や失敗を検出した場合は公開前に中止します。ハッシュは整合性検査であり署名ではありません。
Reviewed 1.0/2.0の両方を受け付け、1.0の厳格検証と2.0のID照合中心の検証範囲を区別します。

今回の範囲は固定位置の単一文書・単一テンプレートによる取得と保存です。
[CSV一覧出力](STRUCTURED_CSV.md)は後段の独立した機能として利用できます。
XLSX出力、マーカー、繰り返し明細、自動テンプレート選択、位置補正、GUI、Portable作成、
Viewer手操作・実文書での運用確認は後続工程です。
