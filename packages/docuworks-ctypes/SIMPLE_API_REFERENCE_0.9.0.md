# Simple API Reference 0.9.0

この文書は`SIMPLE_API_SPEC_0.7.0.md`で固定された公開APIを、利用者向けに
まとめたリファレンスです。0.9.0で公開シグネチャは変更していません。

## 共通契約

- 座標と寸法はmm、font sizeはpt、page番号は1-basedです。
- 更新は`SimpleDocument.save()`を呼んだ場合だけ永続化されます。
- context終了時に暗黙保存しません。
- 色、線種、矢印、link種別は対応するenumだけを受理し、raw整数は拒否します。
- 作成メソッドはすべて`SimpleAnnotation`を返します。

## open_xdw

```python
open_xdw(
    path: str | Path,
    *,
    writable: bool = False,
    dll_path: str | Path | None = None,
    codepage: int | None = None,
) -> SimpleDocument
```

`path`を開きます。`writable=False`はread-only、`True`は更新用です。
`dll_path`はruntime bundleの厳格な強制指定で、失敗時に自動fallbackしません。
`codepage`省略時はWindows ACPを使用します。open／runtime失敗は`XdwError`または
対応するruntime例外をそのまま送出します。

## SimpleDocument

| 操作 | 引数 | 戻り値 | 契約 |
|---|---|---|---|
| `page(number=1)` | 1-based page番号 | `SimplePage` | 範囲外は`IndexError` |
| `save()` | なし | `None` | 更新をXDWへ保存。read-onlyは`ReadOnlyDocumentError` |
| `close()` | なし | `None` | 文書を閉じ、既存wrapperを無効化。暗黙保存なし |
| `core` | property | Core `Document` | 高度な操作へのescape hatch |

`with`終了時は`close()`だけを行います。

## SimplePage

### 列挙

```python
annotations(*, recursive: bool = False) -> tuple[SimpleAnnotation, ...]
```

現在状態のsnapshot tupleを返します。既定はtop-levelだけです。
`recursive=True`はDocuWorks列挙順のflat preorderで、親の直後に子孫を返します。
安定した独自sort、wrapper identity、wrapper equalityは保証しません。

### 作成

| メソッド | 必須入力 | 主な任意入力 | 単位 |
|---|---|---|---|
| `text(text, *, x, y, ...)` | text、x、y | font_size、font_name、fore_color、back_color | x/y mm、font_size pt |
| `rectangle(*, x, y, width, height, ...)` | 矩形 | border／fill設定 | mm |
| `sticky(*, x, y, width, height, ...)` | 付箋矩形 | fill_color、auto_resize、子text | mm |
| `ellipse(*, x, y, width, height, ...)` | 楕円矩形 | border／fill設定 | mm |
| `line(*, x1, y1, x2, y2, ...)` | 始点・終点 | border、`BorderType`、`ArrowheadType`、`ArrowheadStyle` | mm |
| `polygon(points, *, close=True, ...)` | 絶対座標`Sequence[PointMM]` | border／fill／arrowhead | mm |
| `marker(points, *, ...)` | 絶対座標`Sequence[PointMM]` | border_color、border_width、border_transparent | mm |
| `link(caption, *, x, y, link_type, ...)` | caption、位置、`LinkType` | target、auto_resize、width/height、fore_color、font_size | mm／pt |

全作成メソッドは`SimpleAnnotation`を返します。値域、サイズ、Points、link target、
resize条件はCoreが検証します。無効なenumは`TypeError`、geometry・条件違反は
`ValueError`、read-only文書は`ReadOnlyDocumentError`、XDWAPI失敗は`XdwError`です。

新規日付印作成メソッドはありません。既存日付印は`annotations()`で列挙できます。

## SimpleAnnotation

| 操作 | 戻り値 | 契約 |
|---|---|---|
| `type` | `AnnotationType | int` | 既知型はenum、未知型は元のint |
| `position` | `PointMM` | Coreが保持する最新の自然単位位置 |
| `size` | `SizeMM | None` | サイズを持たない種類は`None` |
| `core` | Core `Annotation` | Standard／Custom／User／raw操作へのescape hatch |
| `move_to(*, x, y)` | `None` | mm単位で移動。明示saveが必要 |
| `resize(*, width, height)` | `None` | mm単位。種類別条件をCoreで検証 |
| `delete()` | `None` | 構造削除。明示save後に永続化 |

削除後と文書close後は、全propertyと全methodが`ClosedHandleError`を送出します。
削除後は他の古いsnapshot wrapperも破棄し、再列挙してください。

## 例外一覧

| 状況 | 例外 |
|---|---|
| enum以外またはraw整数enum | `TypeError` |
| geometry、値域、条件違反 | `ValueError` |
| page範囲外 | `IndexError` |
| read-only更新 | `ReadOnlyDocumentError` |
| 削除済み／close済みhandle | `ClosedHandleError` |
| XDWAPI呼出し失敗 | `XdwError` |

Simple固有例外への変換は行いません。
