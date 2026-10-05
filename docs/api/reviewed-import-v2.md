# ID照合中心のReviewed取り込み（Integrations 0.9.0）

[確定した取り込み仕様](../specs/reviewed-import-1.0.md)を実装する新しい経路です。
APIの既定値は従来の厳格検証です。開発版の校正結果取込BATは、新しいID照合中心の経路を選択します。

## 保存形式と互換性

| 対象 | 従来 | ID照合中心の経路 |
|---|---|---|
| Review Session・identity・そのmanifest | 1.0 | 1.0のまま |
| 文書属性 `DW-OCR.SessionDocument` | review_id / identity_sha256 | 同じ識別情報を使用 |
| 初期テキスト属性 `DW-OCR.SessionText` | 単一参照 | 従来の属性も読める |
| 明示設定後のテキスト属性 | 対象外 | docuworks-review-origins / 2.0 |
| Reviewed JSON / JSONL / manifest | 1.0 | 2.0 |
| 読込API | load_reviewed_result | 同じAPIが版に応じて検証 |

既存のSession・結果を自動変換しません。旧結果は旧契約で読み込みます。旧経路で新しい複数参照属性を読むと、本文は保持しますが単一参照としては解釈できず、不正な参照の診断になります。

## 取り込み

```python
from docuworks_integrations import import_reviewed_result

result = import_reviewed_result(
    "work/session", "work/edited.xdw", "work/result-new",
    validation_mode="identity",
)
print(result.data["validation"])
# {"mode": "identity", "identity_checked": True,
#  "page_structure_checked": False}
```

`validation_mode="strict"`（省略時）は保存形式1.0と従来のページ構造・付箋内文字の拒否規則を維持します。未知のモードは拒否します。

新しい経路では文書属性のreview_idとidentity_sha256をSessionの期待値と比較します。identityには原本ハッシュ、run_id、Canonical manifestハッシュが含まれます。Sessionと完成結果の固定ファイルのハッシュ検証も続けます。

ページ構造はSessionと比較しません。保存済みXDWの全ページについて実測の寸法・回転と本文を記録します。page_idは各取り込みで作るスナップショット内の識別子で、原本ページとの対応を保証しません。ページ追加・削除・並べ替え・寸法変更・ページ回転は運用対象外です。読み込み後も「ページ構造未検証」の状態を維持します。

通常テキストは空文字・空白・改行もそのまま保持し、空文字等にはEMPTY_TEXTを付けます。本文0件でもページ情報と空のJSONLを保存します。SDKの読取失敗を空文字に置き換えません。

付箋とその子孫のテキストは本文から除外します。付箋に見た目だけ重なる通常テキストは残ります。除外した付箋本体の数をexcluded_sticky_countへ記録し、固定コピーのXDWにはメモを残します。付箋以外の未対応構造内に通常テキストがあれば、文書全体を拒否します。

## 複数参照と診断

2.0の項目はorigins配列を持ち、各参照はrun_id・canonical_manifest_sha256・region_idで識別します。参照は重複を除去しregion_id順に保存します。配列順は文字の結合順を意味しません。同じ原本領域を複数項目が参照できます。文字列や位置から参照を推定しません。

origin_evidenceは元属性のraw_base64と判定を保存します。

| status | 意味 |
|---|---|
| none | 参照なし。正常な空配列 |
| matched | 参照全体が有効 |
| partial | 有効部分をoriginsへ残したが不正な部分もある |
| invalid | 不正な形式・存在しない領域などで、有効な参照なし |
| foreign | 異なるSession・Canonicalの参照で、有効な参照なし |

不正部分はissuesに0始まりの配列indexとreasonを記録します。属性全体の問題ではindex=nullです。ORIGIN_PARTIAL / ORIGIN_INVALID / ORIGIN_FOREIGNを診断へ追加します。本文は保持します。参照なしと不正な参照は異なる件数として表示します。

`get_reviewed_origins(item)`は検証済みの旧・新形式の項目から、有効なregion_idのタプルを返します。旧形式のduplicateも共有参照として利用できます。診断や元情報は元の項目に残ります。後続処理で原本座標を使う場合は、参照先Canonicalを再照合してください。

## 複数参照を明示設定する最小API

```python
from docuworks_integrations import set_review_origins

# resultは上の取り込み結果。同じ保存済みXDWを指定する。
assigned = set_review_origins(
    "work/session", "work/edited.xdw", "work/assigned-new.xdw",
    [{"page": 1, "order": 1, "region_ids": ["r001", "r002"]}],
    expected_source_sha256=result.data["source_xdw_sha256"],
)
```

region_idsにはSessionに実在する領域IDを指定してください。pageは保存済みXDWの1始まりのページ番号、orderはそのページの通常テキストだけを数えた1始まりの順番です。取り込み結果のpage/orderを使えます。空のregion_idsは明示的な参照なしを設定します。同じ対象の重複指定、未知の領域、入力ハッシュ不一致は拒否します。XDWを再編集した場合は取り込みをやり直して位置指定とハッシュを更新してください。

設定は新規XDWコピーに対して行い、保存・再読込で属性と本文・位置の一致を検証してから確定します。入力XDW、Canonical、Sessionの固定ファイル、完成済み結果を書き換えません。assigned-new.xdwを再度identityモードで取り込めます。専用GUI、編集履歴の追跡、自動的な参照の結合は含みません。

## 配布と確認範囲

4つの2.0 SchemaはPythonパッケージに同梱します。JSONLはReviewed JSONから生成し、読み込み時に一致を検証します。出力先は新規とし、文書全体の検証後に完成結果として確定します。

[受け入れ条件と試験記録](../maintainer/REVIEWED_IMPORT_V2_ACCEPTANCE.md)で、自動試験・実SDK・Viewer・実文書の確認範囲を分けています。
