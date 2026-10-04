# 白紙Review・Reviewed Result 1.0 / Integrations 0.8.1

## 責任範囲と利用の流れ

全ページのCanonical OCR Result → 白紙Review Session生成 → Viewerで保存 → Reviewed Resultへ取り込み、の順に使います。
Canonicalは機械OCRの原記録です。Reviewedは保存済みXDWの文字と位置を独立して記録します。
既存CorrectionSet、1ページReview APIの契約は変更しません。Portableから白紙Review生成とReviewed取り込みを実行できます。

## Python API

```python
from docuworks_integrations import (
    ReviewSession, ReviewedResult,
    create_review_session, load_review_session,
    import_reviewed_result, load_reviewed_result, export_reviewed_jsonl,
)

session = create_review_session(run_dir, session_dir, dll_path=dll_path)
# 利用者が session.review_xdw をViewerで編集・保存し、閉じる。
result = import_reviewed_result(session.root, session.review_xdw, result_dir,
                                dll_path=dll_path)
loaded = load_reviewed_result(result.root)
export_reviewed_jsonl(loaded, another_jsonl_path)
```

| シグネチャ | 動作・返値 |
|---|---|
| `create_review_session(run_dir, output_dir, *, dll_path=None) -> ReviewSession` | Canonical 1.0/1.1と固定コピーの元XDWを検査し、新しいSessionフォルダーを確定する。DocuWorks、Core、Pillowが必要。 |
| `load_review_session(session_dir) -> ReviewSession` | 初期XDWを含む固定ファイルのハッシュとメタデータを検証する。編集用XDWは検査しない。DLL不要。 |
| `import_reviewed_result(session_dir, edited_xdw, output_dir, *, dll_path=None) -> ReviewedResult` | 保存済み編集XDWの固定コピーをSDKで読み、文書全体を検証し、新しい結果フォルダーを確定する。CanonicalやPillowは不要。 |
| `load_reviewed_result(result_dir) -> ReviewedResult` | ハッシュ、形式、ページ対応、来歴分類、JSONLとの一致を検証する。DLL・Canonical・外部Sessionは不要。 |
| `export_reviewed_jsonl(result, output_path) -> Path` | 読込済み結果の不変性を再検査し、新規ファイルへ出力する。 |

引数のパスは `str` / `Path`。`dll_path=None` はCoreのDLL解決規則を使います。
出力先の親は先に作成してください。既存出力、固定入力フォルダー内の出力、シンボリックリンク経由のパスを拒否します。
SDKはファイルを読んで閉じます。Viewerの未保存編集は取得できません。取り込み前に保存して閉じてください。

`ReviewSession` は `root: Path`, `manifest_sha256: str`, `review_id: str`, `review_xdw: Path`, `identity: dict`, `data: dict`, `pages: tuple` を公開します。
`ReviewedResult` は `root: Path`, `manifest_sha256: str`, `result_id: str`, `review_id: str`, `data: dict`, `pages: tuple` を公開します。
両方とも固定された読込スナップショットです。`data` / `identity` / `pages` は毎回コピーを返し、編集しても保存ファイルは変わりません。
項目型は `docuworks_integrations.reviewed_types` の `ReviewOrigin`, `ReviewedItem`, `ReviewedPage`, `ReviewedData` を参照できます。

## Sessionフォルダー

```text
identity.json  文書・ページ・初期文字のID、元Canonical参照、初期文字と左上位置
session.json   生成時刻・環境、保存再読込した実測値、identityとinitialのハッシュ
initial.xdw    編集前の固定原本
review.xdw     利用者が編集する作業コピー
manifest.json  COMPLETE状態と固定3ファイルのSHA-256
```

文書全ページの `source.page_count` と連続したページ1～Nが必要です。元XDWのページ数・寸法も照合します。
未処理ページを空ページとして補完しません。全ページ文字0件は有効です。
生成ページは元と同寸法の白紙で、ページ回転0度です。OCR領域の左上に赤12pt・背景の塗りつぶしなし・横書き・回転0度・折り返しなしのテキストを置きます。
保存して閉じ、再度開いて文字・位置・サイズ・書字方向・回転・色・折り返し・IDを確認します。
フォント名と実測サイズはSessionへ記録します。OCR検出枠の幅高さをテキスト枠に強制しません。

`identity.json` には完成XDWのハッシュを入れません。XDWのユーザー属性はSession IDとidentityファイルのハッシュを参照します。
完成した `initial.xdw` のハッシュは外側のSessionとmanifestに保存し、循環参照を避けます。
`review.xdw` は編集されるため固定ファイルのハッシュ一覧に含めません。

## Reviewedフォルダー

```text
reviewed.json      正本。全文書・空ページ・文字項目・診断
reviewed.jsonl     正本から生成する1テキスト1行の派生物
source-review.xdw  取り込みに用いた保存済みXDWの固定コピー
identity.json     照合に使用したSession識別情報のコピー
session.json      照合に使用した初期Session情報のコピー
manifest.json     COMPLETE状態と上記5ファイルのSHA-256
```

正本の `result_id` は取り込みごとの新しいUUIDです。同じ入力を再取り込みしても別IDになります。
`review_id` はSessionのUUID、`created_at` はタイムゾーン付きUTC日時、`source_xdw_sha256` は入力XDWのハッシュ、`session_sha256` は同梱Sessionのハッシュです。
ページには `page`（1始まり）、`page_id`、`width_mm`、`height_mm`、`rotation`（0）、`items` を保持します。
文字が0個でもページは残ります。JSONLには文字のないページの行は出しません。

### 文字項目

| フィールド | 意味 |
|---|---|
| `item_id` | 結果内で一意な新しいUUID。SDKハンドルや列挙番号を使わない。再取り込み間の同一性は示さない。 |
| `order` | そのページでのSDK取得順。1始まり。文章の読み順ではない。 |
| `text` | 保存済み文字列そのもの。Unicode、改行、前後空白、空文字を保持する。 |
| `x`, `y`, `width`, `height` | SDK保存再読込後の実際の外接矩形。mm。左上原点、右+x、下+y。回転文字では回転後の外接矩形。 |
| `rotation` | SDK `%TextOrientation` の角度（整数0～359度）。 |
| `direction` | SDK `%TextDirection`。0=横書き、1=縦書き。 |
| `origin` | 任意の元領域参照とその状態。文字採否の条件にはしない。 |
| `diagnostics` | `EMPTY_TEXT` と来歴診断。空白のみも `EMPTY_TEXT`。項目の削除とは区別する。 |

`confidence` は保存しません。フォント・色・折り返し設定を再現するファイル形式ではありません。それらを含む編集原本は同梱XDWに残ります。
座標・寸法はSDKの1/100mm値を100で割った数値です。外接枠を指定サイズと比較せず、保存後の実測値と比較します。

### 任意の来歴

`origin` は `status`, `annotation_id`, `region_id`, `raw_base64` の4フィールドです。
属性の元バイト列を `raw_base64` に保存します。属性がなければnullです。

| status | 意味 |
|---|---|
| `matched` | このSessionの初期文字ID・元領域IDと整合する属性が1件ある。 |
| `duplicate` | 同じ初期文字IDを複数の現在文字が持つ。コピーの可能性がある。全項目を保持する。 |
| `missing` | 属性がない。新規追加など。 |
| `invalid` | 破損JSON、ID形式不正、このSessionにない初期文字ID、元領域IDとの不整合など。 |
| `foreign` | 形式は有効だが別Session IDまたは別identityハッシュを参照する。 |

matched/duplicate以外のID欄はnullで、元属性はrawに残します。対応は「属性が整合した」という意味で、編集履歴や人間の意図を保証しません。
来歴の欠落・コピー・不正によって文字を捨てません。将来の訂正差分・分割結合推定は別機能です。

## 検証・エラー・確定

ページに直接貼られた全テキストを色に関係なく取り込みます。非テキストは無視しますが、その子孫にテキストがあればグループ・付箋内の未対応構造として文書全体を拒否します。
文書／ページ属性の欠落・不一致、ページ数・順序・寸法・回転の変更、SDK読取エラーも文書全体のエラーです。
特に180度のページ回転も確認します。ページ構成編集は対象外です。

形式・不整合は `ValueError`、ハッシュ変更は `RuntimeError`、既存出力は `FileExistsError`、ファイル入出力は `OSError` 派生、SDK失敗はCoreの例外を送出します。
同一ボリュームの非公開一時フォルダーで全出力を作成・検証し、新規出力フォルダーとして確定します。途中失敗を完成結果として返しません。
元文書・Canonical・初期XDW・過去のReviewedを変更しません。ハッシュは整合性検査であり電子署名ではありません。

同梱の `review-session-identity-1.0.schema.json`, `review-session-1.0.schema.json`, `reviewed-result-1.0.schema.json`, `reviewed-text-1.0.schema.json` と2種のmanifest SchemaはDraft 2020-12です。
Schemaは構造を規定し、APIはさらにファイルハッシュ・IDの一意性・ページ対応・来歴と診断の意味的整合を検査します。

## 開発検証

新機能のDLL不要試験はPython 3.10～3.13、Integrations全体は3.11～3.13で実施します。
実SDK試験は `DOCUWORKS_REVIEWED_DLL` と `DOCUWORKS_INTEGRATIONS_TEST_TMP` を指定し、`tests` をimport pathに追加して実行します。
生成用 `tests/reviewed_fixture.py` のCanonicalは明示的な合成データです。実OCR検証では、その実XDWを固定モデルのPaddleへ入力し、実行結果からSessionを作ります。
Viewer操作の人間による確認とSDK自動照合は別記録です。実施状況は開発検証記録を参照してください。Core全体のPython 3.10問題を解消する変更ではありません。

## 0.8.1の生成処理

新規白紙Reviewの生成中だけ、ページオブジェクトと次の追加位置を保持します。
ページが空であることを最初に確認し、追加APIが返したハンドルと予想位置の実情報を照合します。
ハンドル不一致または位置の無効時は、そのページの最適化を解除してCoreの従来探索へ戻ります。
その他のSDKエラーはそのまま伝えます。既存文書の編集や再オープンにはこの状態を持ち越しません。
文字・識別属性・保存後の全検査とReview Session / Reviewed Result 1.0の形式は維持します。

Core 1.0.1以降を使用します。Review Session / Reviewed Resultの保存形式1.0は変更しません。

## 追加仕様: ID照合中心の取り込み2.0（Integrations 0.9.0）

この節より前は従来の1.0契約です。import_reviewed_resultのvalidation_modeは既定strictで、1.0を保存します。identityを明示すると新形式2.0を保存し、Sessionとのページ数・順序・寸法・回転・ページ識別の照合を行いません。文書のreview_idとidentity_sha256、および固定ファイルのハッシュ検証は維持します。保存済みXDWの全ページと実測寸法・回転を記録し、validation={mode: identity, identity_checked: true, page_structure_checked: false}をJSONとJSONLへ持たせます。page_idは結果内の識別子です。ページ構造変更は運用対象外です。

2.0のReviewed JSON・JSONL・manifestと、明示設定用docuworks-review-origins属性は版2.0です。Session・identity・そのmanifestは1.0のままです。文書属性DW-OCR.SessionDocumentも維持します。テキスト属性DW-OCR.SessionTextは既存の単一参照と新しい複数参照の両方を解釈します。4つの2.0 JSON Schemaを同梱します。

項目のoriginsは{run_id, canonical_manifest_sha256, region_id}の配列です。同じ領域を複数項目が参照でき、空配列は正常です。参照はregion_id順で重複を除去します。自動推定は行いません。origin_evidenceはstatus（none / matched / partial / invalid / foreign）、raw_base64、issues（0始まりindexまたはnullとreason）を保持します。不正部分は原本参照へ使わず、本文・有効部分・元情報を残します。不正時はORIGIN_PARTIAL / ORIGIN_INVALID / ORIGIN_FOREIGNを診断に記録し、参照なしとは区別します。get_reviewed_origins(item)は検証済み旧・新項目の有効なregion_idをタプルで返し、元の診断・証拠は項目に残ります。

付箋本体とその子孫のテキストは本文から除外し、excluded_sticky_countで付箋数を記録します。固定XDWコピーにはメモが残ります。通常テキストが付箋と視覚的に重なっても保持します。付箋以外の未対応構造内のテキストは文書単位で拒否します。空文字・空白だけの本文も保持してEMPTY_TEXTを記録し、全本文0件でも成功します。SDK読取失敗を空文字に変換しません。

set_review_origins(session_dir, edited_xdw, output_xdw, assignments, *, expected_source_sha256, dll_path=None)は新規XDWコピーへ複数参照を明示設定します。assignmentsは{page, order, region_ids}のリストで、pageは1始まりのページ番号、orderはページ直下の通常テキストだけの1始まり順序です。同じXDWの取り込み結果のpage/orderとsource_xdw_sha256を使います。入力が変わっていれば拒否し、Sessionに実在する領域だけを設定します。空のregion_idsも有効です。保存・再読込で変更対象の属性と本文・配置の一致を検証し、元データ・Session固定ファイル・完成済み結果を変更しません。

load_reviewed_resultはmanifestの版に応じて旧・新契約を選択します。新形式の再読込で旧ページ検証を再適用しません。JSONLはJSONから生成し一致を検証します。旧結果を自動変換せず、取り込みは毎回新しい結果を作ります。
