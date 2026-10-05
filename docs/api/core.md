# docuworks-ctypes 1.0.1 日本語仕様書

1.0.1更新：座標・入力防御・例外保持は[変更記録](../../packages/docuworks-ctypes/CHANGELOG_1.0.1.md)と[対応台帳](../maintainer/CORE_1.0.1_ISSUES.md)を優先します。元の1.0.0検証件数は履歴です。

元資料: 提示された `docuworks_ctypes-1.0.0-py3-none-any.whl` と `docuworks-ctypes-1.0.0-source.zip` の実装。作成日: 2026-09-05。

本書は利用者と保守開発者向けに、実装上の振る舞い、公開インターフェース、制約、検証範囲を整理したものです。1.0.0のコードや既存の安定性契約を変更する文書ではありません。入力資料の説明と実装が異なる箇所は、その差を明記します。旧版の仕様書を別途開かずに主要機能を確認できます。

導入と実行例は [README](../../README.md)、今回の実行環境・検証結果・不具合の再現結果は [検証報告書](../VERIFICATION.md) を参照してください。試験結果の数値は報告書を正とし、本書に示す従来記録を今回の追試結果として扱わないでください。

## 1. 対象機能と層

```text
Simple API  →  Core API  →  Raw ctypes  →  利用者が用意する XDWAPI DLL
```

| 層 | 主な入口 | 対象 |
| --- | --- | --- |
| Simple | `docuworks_ctypes.simple.open_xdw` | 既存XDWを開く、8種類の作成、列挙、移動、サイズ変更、削除、明示保存 |
| Core | `XdwApi`、`Document`、`Page`、`Annotation` | Simpleの基盤、Standard／Custom／User属性、自然単位とraw単位、ANNファイルからの追加 |
| Raw | `XdwApi.raw`、内部パッケージ `docuworks_ctypes._raw` | 141個の生成済みXDWAPI署名によるABI呼出し。引数・バッファ・ハンドル・戻り値を呼出し側で管理 |

Simple／Coreの文書処理対象は既存文書です。新規空白XDW生成、日付印の新規作成、永続アノテーションID、暗黙保存、OCR、ページ描画、CAD、AI、データベース連携は公開ワークフローの対象外です。Rawに関連するネイティブ関数名が存在しても、その機能がSimple／Coreで実装・統合検証済みという意味にはなりません。

### 1.1 対応環境と最低条件

- 対応プラットフォームはWindows x64、64-bit CPythonです。配布資料の対応表はCPython 3.10～3.13です。`pyproject.toml`のメタデータは`requires-python = ">=3.10"`であり、3.14以降の動作を検証済みとする根拠にはなりません。
- 利用者側に互換性のあるDocuWorks製品とXDWAPI DLLが必要です。DLL、SDK原文、試験用XDWは本パッケージに同梱されません。
- `MINIMUM_VERSION = (9, 1, 7)`です。`XdwApi.load()`は選択DLLの`XDW_GetInformationW`で得た版を解析し、先頭3要素でこの値と比較します。最低版の条件と、現在の製品環境で文書を開ける条件は別です。
- wheel名の`py3-none-any`は配布タグです。この名称からOS非依存または32-bit対応を推論できません。
- 公開型のPython型注釈は呼出し時の全入力検証を意味しません。数値・パス・enumの具体的な検証範囲は以下に示します。

## 2. 共通契約

### 2.1 保存と所有関係

`open_xdw()`と`XdwApi.open_document()`の既定モードは読み取り専用です。更新するにはSimpleでは`writable=True`、Coreでは`mode=OpenMode.UPDATE`を指定します。`save()`は現在開いているパスに保存します。別名保存の引数はありません。

`with`の終了は`close()`だけを行い、正常終了でも例外終了でも暗黙保存しません。変更用サンプルでは、原本を未作成の出力パスへコピーしてからそのコピーを開き、すべての操作が成功した末尾で`save()`を呼びます。

`Document`が文書ハンドルを保持し、`Page`は`Document`を、`Annotation`は`Page`を参照します。Simpleのwrapperは対応するCoreオブジェクトを保持します。アノテーションハンドルは文書の生存期間内でのみ操作に使用してください。ガベージコレクションによる自動close、永続ID、文書を開き直した後のハンドル再利用は保証されません。

`Document.close()`は2回目以降を何もせず終了します。最初のネイティブcloseから戻った時点で、戻り値がエラーでもPython側をclosedにし、ハンドルをNULLにしてから例外を送出します。失敗後に同じオブジェクトでcloseを再試行できるという保証はありません。

### 2.2 部分変更と例外時の扱い

複数操作をまとめるトランザクション機構はありません。たとえばText作成は空のアノテーション追加後に本文・フォント等を設定し、Rectangle作成は追加後に線と塗り属性を設定します。後続の入力検証またはDLL呼出しに失敗しても、それまでの文書内変更を自動で取り消しません。呼出しが例外で終了したことだけを根拠に「変更が一切なかった」と判断しないでください。

作成後の公式情報再取得に失敗した`AnnotationRefreshError`でも、ネイティブ追加自体が成功している可能性があります。失敗時に意図しない部分変更を保存しないため、サンプルと運用では例外を外側へ伝播させ、`save()`へ進まずcloseし、必要に応じてコピーを作り直します。明示保存より前でも同一ハンドル上の読み取りには変更が見えます。

### 2.3 座標・寸法・文字列

| 対象 | Python側 | DLL／raw側 |
| --- | --- | --- |
| 位置・幅・高さ | mm、`PointMM`／`SizeMM`／`RectMM` | 1/100 mmの整数 |
| FontSize、TextSpacing | pt | 1/10 ptの整数 |
| BorderWidth | ptの整数 | 同じ整数。1/10 ptへ変換しない |
| LineSpace | line | 1/100 lineの整数 |
| Text各margin | mm | 1/100 mmの整数 |
| TextOrientation | degree | 1 degreeの整数 |
| `%Points`自然getter | 絶対座標の`tuple[PointMM, ...]` | — |
| `%Points`raw getter | `tuple[RawPoint, ...]` | 先頭が絶対座標、以後が第1点からの相対移動量。単位は1/100 mm |

mmと標準属性の単位変換は`Decimal(str(value))`と`ROUND_HALF_UP`で丸めます。ページ番号とANN内番号は1始まりです。親アノテーション上に追加するTextの位置は親に対する座標です。Simpleの付箋に`text=`を指定した場合、Core既定の`PointMM(2, 2)`位置へ子Textを追加します。

`PointMM`／`RawPoint`はfrozen dataclassであり、それ自体に座標範囲の検証はありません。`SizeMM`／`RectMM`は幅・高さが0以下なら`ValueError`です。NaN・無限大・巨大整数・埋込みNUL等に対する全面的な検証は実装されていません。記載するサイズ範囲と属性制約を守り、座標には有限な実数、文字列にはNULを含まない通常の文字列を渡してください。入力エラーが必ず単一の例外型へ統一されるわけではありません。

### 2.4 列挙と寿命の差

| 対象 | 既定の列挙 | 返却形 | 内容／無効化 |
| --- | --- | --- | --- |
| `SimplePage.annotations()` | top-levelだけ | snapshot tuple | その呼出し時点の構成を実体化。`recursive=True`は親→子孫のflat preorder |
| `Page.annotations()` | 再帰あり | iterator | XDWの列挙順で順次取得。反復中の構造変更は避ける |
| `Annotation.descendants()` | 全子孫 | iterator | 保持している子数を起点に子孫を列挙 |

列挙のたびに新しいwrapperが生成されます。別の列挙間のidentity、equality、独自の安定sortは保証しません。あるwrapperから削除した後、同じアノテーションを指す別wrapperや既取得の子孫wrapperを横断して無効化する仕組みはありません。構造削除後は他の古いsnapshotを破棄し、再列挙してください。

`SimpleAnnotation`は`type`、`position`、`size`、`core`を含む全propertyと公開操作の先頭で、文書がopenか、当該Core wrapperが削除済みかを検査します。削除したwrapperの再操作や文書close後の操作は`ClosedHandleError`です。

Coreの`Annotation.position`、`size`、`annotation_type`、`handle`／`handle_value`は、保持する情報をそのまま返し、同じ生存検査をしません。Coreの属性操作、移動、resize、remove等は生存検査を行います。`SimpleDocument.core`と`SimplePage.core`も通常の公開インスタンス属性です。この差を「すべてのCore propertyがclose後に例外」と読み替えないでください。

位置・サイズは各Core wrapperに保持された情報です。当該wrapperの`set_position`／`set_size`成功時は更新されますが、別wrapper、Raw操作、自動サイズ変更を誘発する属性更新などと常時同期されません。最新の公式列挙情報が必要なら再列挙します。`size is None`は保持情報の幅または高さが0以下の場合であり、`None`以外なら必ずresize可能という意味ではありません。

## 3. Simple API

インポート元は`docuworks_ctypes.simple`です。以下は実装から抽出した公開署名です。`self`はinstance method、`*`以降はkeyword-only引数です。`None`既定のstyle引数は当該属性を明示設定せず、DLL側の既定や現在状態に任せます。

```python
class SimpleAnnotation:

    def __init__(self, core: Annotation):
        ...

    @property
    def type(self) -> AnnotationType | int:
        ...

    @property
    def position(self) -> PointMM:
        ...

    @property
    def size(self) -> SizeMM | None:
        ...

    @property
    def core(self) -> Annotation:
        ...

    def move_to(self, *, x: float, y: float) -> None:
        ...

    def resize(self, *, width: float, height: float) -> None:
        ...

    def delete(self) -> None:
        ...

class SimpleDocument:

    def __init__(self, core: Document):
        ...

    def __enter__(self) -> 'SimpleDocument':
        ...

    def __exit__(self, exc_type, exc, traceback) -> bool:
        ...

    def page(self, number: int=1) -> 'SimplePage':
        ...

    def save(self) -> None:
        ...

    def close(self) -> None:
        ...

class SimplePage:

    def __init__(self, core: Page):
        ...

    def annotations(self, *, recursive: bool=False) -> tuple[SimpleAnnotation, ...]:
        ...

    def text(self, text: str, *, x: float, y: float, font_size: float=12.0, font_name: str | None=None, fore_color: Color | None=None, back_color: Color | None=None) -> SimpleAnnotation:
        ...

    def rectangle(self, *, x: float, y: float, width: float, height: float, border_color: Color | None=None, border_width: int | None=None, border_visible: bool | None=None, fill_color: Color | None=None, fill_visible: bool | None=None, fill_transparent: bool | None=None) -> SimpleAnnotation:
        ...

    def sticky(self, *, x: float, y: float, width: float, height: float, fill_color: Color | None=None, auto_resize: bool | None=None, text: str | None=None) -> SimpleAnnotation:
        ...

    def ellipse(self, *, x: float, y: float, width: float, height: float, border_color: Color | None=None, border_width: int | None=None, border_visible: bool | None=None, fill_color: Color | None=None, fill_visible: bool | None=None, fill_transparent: bool | None=None) -> SimpleAnnotation:
        ...

    def line(self, *, x1: float, y1: float, x2: float, y2: float, border_color: Color | None=None, border_width: int | None=None, border_type: BorderType | None=None, border_transparent: bool | None=None, arrowhead_type: ArrowheadType | None=None, arrowhead_style: ArrowheadStyle | None=None) -> SimpleAnnotation:
        ...

    def polygon(self, points: Sequence[PointMM], *, close: bool=True, border_color: Color | None=None, border_width: int | None=None, border_visible: bool | None=None, fill_color: Color | None=None, fill_visible: bool | None=None, fill_transparent: bool | None=None, arrowhead_type: ArrowheadType | None=None, arrowhead_style: ArrowheadStyle | None=None) -> SimpleAnnotation:
        ...

    def marker(self, points: Sequence[PointMM], *, border_color: Color | None=None, border_width: int | None=None, border_transparent: bool | None=None) -> SimpleAnnotation:
        ...

    def link(self, caption: str, *, x: float, y: float, link_type: LinkType, target: str | None=None, auto_resize: bool=True, width: float | None=None, height: float | None=None, fore_color: Color | None=None, font_size: float | None=None) -> SimpleAnnotation:
        ...

def open_xdw(path: str | Path, *, writable: bool=False, dll_path: str | Path | None=None, codepage: int | None=None) -> SimpleDocument:
    ...
```

### 3.1 入口と戻り値

`open_xdw(path, *, writable=False, dll_path=None, codepage=None)`は毎回`XdwApi.load()`を呼び、その`verification_document`に対象文書のパスを渡します。DLL候補を子processでread-only openまで確認してから、呼出し側processで希望モードで開きます。Simpleには`search_paths`、`auth`、既存`XdwApi`を受け取る引数はありません。必要ならCoreで開き、`SimpleDocument(core_document)`で包みます。

`SimpleDocument.page()`は既定で1ページ目の`SimplePage`を返します。`save()`、`close()`、`SimpleAnnotation.move_to()`、`resize()`、`delete()`は成功時に`None`を返します。8種類の作成メソッドはすべて`SimpleAnnotation`です。既知の`type`は`AnnotationType`、未知の値は元の`int`を返します。

### 3.2 作成機能と追加条件

| 方法 | 結果 | 固有の条件 |
| --- | --- | --- |
| `text` | Text | 必須本文と位置。Simpleのfont_size既定は12.0 pt。Coreの既定は`None`なので異なる |
| `rectangle` | Rectangle | サイズ3～2400 mm。線・塗りを任意設定 |
| `sticky` | Sticky | サイズ5～500 mm。`text`指定時は子Textも作成 |
| `ellipse` | Ellipse | サイズ3～2400 mm。Rectangleと同じstyle引数 |
| `line` | Straight Line | 始点と終点から相対ベクトルを作成。線種と矢印を指定可能 |
| `polygon` | Polygon | `PointMM`の非空sequence。`close=True`が既定。開いたpolygonの塗り属性設定は条件違反 |
| `marker` | Marker | `PointMM`の非空sequence。線色・線幅・透過を任意指定 |
| `link` | Link | `LinkType`必須。target条件、sizeとauto_resizeの条件は下記 |

Simpleの色は`Color`、線種は`BorderType`、矢印は`ArrowheadType`／`ArrowheadStyle`、リンク種類は`LinkType`のinstanceのみを受理します。値が同じでも通常のraw整数や他種enumは`TypeError`です。Core呼出し前にこの検査をします。ただし、`Color`に存在するすべての色が全種類の属性で許可されるわけではありません。実際の許容色は第5節のRegistryに従います。

Linkは`THIS_DOCUMENT`で`target=None`、その他では非空の`str`を要求します。`width`と`height`は両方指定または両方省略です。サイズを指定する場合は`auto_resize=False`が必要です。URL等の内容を通信して検証する機能はありません。targetの属性はXDW→`%XdwPath`、URL→`%Url`、OTHER_FILE→`%OtherFilePath`、MAIL_ADDRESS→`%MailAddress`です。THIS_DOCUMENTのリンク先ページ等はCore属性で設定します。

Polygon／Markerは絶対座標をrawの先頭絶対値＋後続相対値へ変換します。実装が検査する点数条件は「1点以上」であり、幾何学上の有効な図形を全面的に検証しません。各符号化座標に−240000～240000の範囲検査があり、後続点では絶対座標ではなく差分へ適用されます。

### 3.3 例外

Simpleは固有の例外へ包み直しません。enum不正は`TypeError`、サイズ・条件違反は`ValueError`、ページ範囲外は`IndexError`、読み取り専用更新は`ReadOnlyDocumentError`、当該wrapper削除済み／文書close済みは`ClosedHandleError`、DLL失敗は`XdwError`が基本です。ファイル不在、DLL探索、エンコード、ネイティブloadの失敗は第8節の該当例外がそのまま伝播します。

## 4. Core API

Coreは`from docuworks_ctypes import ...`で利用します。以下は実装の全公開メソッド・propertyと初期化／context署名です。戻り値注釈がない箇所は元実装にも注釈がありません。実際の値は続く説明に示します。直接コンストラクターでハンドルを構築するより、`XdwApi.load()`→`open_document()`→`page()`／列挙・作成から得る方法を標準とします。

```python
class XdwApi:

    def __init__(self, raw, runtime_info: RuntimeInfo, multibyte_encoding: MultibyteEncodingPolicy):
        ...

    @classmethod
    def load(cls, dll_path: str | Path | None=None, *, multibyte_codepage: int | None=None, search_paths: Iterable[str | Path]=(), verification_document: str | Path | None=None) -> 'XdwApi':
        ...

    @classmethod
    def inspect_runtimes(cls, *, dll_path: str | Path | None=None, search_paths: Iterable[str | Path]=(), verification_document: str | Path | None=None) -> ResolutionReport:
        ...

    @classmethod
    def from_raw(cls, raw, *, version: tuple[int, ...]=MINIMUM_VERSION, multibyte_codepage: int | None=None) -> 'XdwApi':
        ...

    def diagnose(self) -> RuntimeInfo:
        ...

    def open_document(self, path: str | Path, *, mode: OpenMode=OpenMode.READONLY, auth: AuthMode=AuthMode.NO_DIALOG) -> Document:
        ...

class Document:

    def __init__(self, raw, handle, path: Path, mode: OpenMode, multibyte_encoding: MultibyteEncodingPolicy | None=None):
        ...

    def __enter__(self) -> 'Document':
        ...

    def __exit__(self, exc_type, exc, traceback) -> bool:
        ...

    @property
    def closed(self) -> bool:
        ...

    @property
    def page_count(self) -> int:
        ...

    def page(self, number: int) -> 'Page':
        ...

    def save(self) -> None:
        ...

    def close(self) -> None:
        ...

class Page:

    def __init__(self, document: Document, number: int):
        ...

    @property
    def raw(self):
        ...

    def annotations(self, recursive: bool=True) -> Iterator['Annotation']:
        ...

    def add_rectangle(self, rect: RectMM, *, border_color: Color | int | None=None, border_width: int | None=None, border_visible: bool | None=None, fill_color: Color | int | None=None, fill_visible: bool | None=None, fill_transparent: bool | None=None) -> 'Annotation':
        ...

    def add_text(self, position: PointMM, text: str, *, font_name: str | None=None, font_size: float | None=None, font_style: int | None=None, fore_color: Color | int | None=None, back_color: Color | int | None=None, parent: 'Annotation | None'=None) -> 'Annotation':
        ...

    def add_sticky(self, position: PointMM, size: SizeMM, *, fill_color: Color | int | None=None, auto_resize: bool | None=None, text: str | None=None, text_position: PointMM=PointMM(2, 2)) -> 'Annotation':
        ...

    def add_line(self, start: PointMM, end: PointMM, *, border_color: Color | int | None=None, border_width: int | None=None, border_type: BorderType | int | None=None, border_transparent: bool | None=None, arrowhead_type: ArrowheadType | int | None=None, arrowhead_style: ArrowheadStyle | int | None=None) -> 'Annotation':
        ...

    def add_ellipse(self, rect: RectMM, *, border_color: Color | int | None=None, border_width: int | None=None, border_visible: bool | None=None, fill_color: Color | int | None=None, fill_visible: bool | None=None, fill_transparent: bool | None=None) -> 'Annotation':
        ...

    def add_polygon(self, points: Sequence[PointMM], *, close: bool=True, border_color: Color | int | None=None, border_width: int | None=None, border_visible: bool | None=None, fill_color: Color | int | None=None, fill_visible: bool | None=None, fill_transparent: bool | None=None, arrowhead_type: ArrowheadType | int | None=None, arrowhead_style: ArrowheadStyle | int | None=None) -> 'Annotation':
        ...

    def add_marker(self, points: Sequence[PointMM], *, border_color: Color | int | None=None, border_width: int | None=None, border_transparent: bool | None=None) -> 'Annotation':
        ...

    def add_link(self, position: PointMM, caption: str, *, link_type: LinkType | int, target: str | None=None, auto_resize: bool=True, size: SizeMM | None=None, fore_color: Color | int | None=None, font_size: float | None=None) -> 'Annotation':
        ...

    def add_from_ann(self, ann_path: str | Path, position: PointMM, *, index: int=1, parent: 'Annotation | None'=None) -> 'Annotation':
        ...

class Annotation:

    def __init__(self, page: Page, info: T.XDW_ANNOTATION_INFO):
        ...

    @property
    def document(self) -> Document:
        ...

    @property
    def raw(self):
        ...

    @property
    def handle(self):
        ...

    @property
    def handle_value(self) -> int | None:
        ...

    @property
    def annotation_type(self) -> AnnotationType | int:
        ...

    @property
    def position(self) -> PointMM:
        ...

    @property
    def size(self) -> SizeMM | None:
        ...

    def descendants(self) -> Iterator['Annotation']:
        ...

    def set_standard_attribute(self, name: str, value) -> None:
        ...

    def get_standard_attribute(self, name: str):
        ...

    def set_standard_attribute_raw(self, name: str, value) -> None:
        ...

    def get_standard_attribute_raw(self, name: str):
        ...

    def set_custom_attribute(self, name: str, kind: CustomAttributeKind, value) -> int:
        ...

    def get_custom_attribute(self, name: str) -> CustomAttribute:
        ...

    def custom_attributes(self) -> tuple[CustomAttribute, ...]:
        ...

    def delete_custom_attribute(self, name: str) -> int:
        ...

    def set_user_attribute(self, name: str, value: bytes) -> None:
        ...

    def get_user_attribute(self, name: str) -> bytes:
        ...

    def delete_user_attribute(self, name: str) -> None:
        ...

    def set_position(self, position: PointMM) -> None:
        ...

    def set_size(self, size: SizeMM) -> None:
        ...

    def remove(self) -> None:
        ...
```

### 4.1 XdwApiとDocument

`XdwApi.load()`はDLLを探索・検査・loadし、`XdwApi`を返します。`inspect_runtimes()`は`ResolutionReport`を返し、呼出し側processに候補DLLをloadしませんが、候補ごとの子process probeは実施します。「ファイル名を見るだけの静的検査」ではありません。`diagnose()`はload時点で保持した`RuntimeInfo`を返し、その場で再probeしません。

`XdwApi.from_raw(raw, *, version=MINIMUM_VERSION, multibyte_codepage=None)`はfake raw等の注入用です。DLL選定やネイティブ版検査を行わず、渡された版から`RuntimeInfo`を組み立てます。`from_raw`による成功を実機互換性の証明にしないでください。

`open_document()`はパスをexpanduser／resolveし、ファイル存在を確認します。`mode`と`auth`は対応enumへ変換します。認証既定は`AuthMode.NO_DIALOG`です。パスをUTF-16バッファへ変換して`XDW_OpenDocumentHandleW`を呼び、`Document`を返します。`Document.page_count`は呼ぶたびにDLLからページ数を取得します。

### 4.2 Pageと作成

全`add_*`はCore `Annotation`を返します。`add_from_ann()`も含め、追加成功後は実際に返されたハンドルを列挙情報から探して`XDW_ANNOTATION_INFO`を取得します。見つからない場合は架空のサイズ・型情報で補完せず`AnnotationRefreshError`です。

`add_text(..., parent=...)`は親上のTextを追加できます。`add_sticky(..., text=...)`もこの経路を利用します。`add_from_ann()`は存在するANNパスと1始まりindexを使います。親に渡す`Annotation`は同じ文書・同じページの生存オブジェクトに限定して使用してください。所属の全面的なクロスチェックがあるとは保証しません。

Coreのstyle引数はSimpleより広く`Color | int`等を受け取りますが、標準属性のRegistryが許可する値へ制限されます。任意のRGB／COLORREF整数が常に受理されるわけではありません。既存READMEの「任意COLORREFはCoreへ」という案内だけを根拠に許容値を拡張しないでください。

### 4.3 Annotationの操作と戻り値

| 操作群 | 戻り値／意味 |
| --- | --- |
| `document`／`raw` | 所属`Document`／RawApi。所有権移転なし |
| `handle`／`handle_value` | ctypesハンドル／保持する整数値または`None`。直接利用は生存期間に注意 |
| `annotation_type` | 既知型は`AnnotationType`、未知型は`int` |
| `position`／`size` | キャッシュから`PointMM`／`SizeMM \| None` |
| `get_standard_attribute` | Registryに応じ`str`、`int`、`float`、`bool`、`tuple[PointMM, ...]`。色は整数 |
| `get_standard_attribute_raw` | `str`、`int`、`tuple[RawPoint, ...]`。bool意味でも0/1整数 |
| Standard setter、User setter／delete、移動／resize／remove | 成功時`None` |
| `set_custom_attribute`／`delete_custom_attribute` | DLLの非負戻り値を`int`で返す。負値は`XdwError` |
| `get_custom_attribute`／`custom_attributes` | `CustomAttribute`／そのsnapshot tuple |
| `get_user_attribute` | `bytes`。User名を列挙するCore APIはない |

Standard／Custom／Userは別体系です。Standardの`%`付き名称をCustomやUserへ自動振替する機能はありません。標準属性名と種類の未登録組合せは`ValueError`です。`set_standard_attribute_raw()`は単位変換を省きますが、値型・Registry・条件・読み取り専用の検査を迂回しません。

### 4.4 サイズ変更

| 種類 | 幅・高さの範囲 | 追加条件 |
| --- | --- | --- |
| Rectangle、Ellipse | 3～2400 mm | 独立した幅・高さ |
| Text | 5～2400 mm | `%WordWrap == 1`かつ`%TextOrientation == 0` |
| Bitmap | 5～2400 mm | Coreに新規作成facadeはない |
| Link | 5～2400 mm | `%AutoResize == 0` |
| Sticky | 5～500 mm | 独立した幅・高さ |
| Date Stamp | 幅10～500 mm | 高さは指定値でなく幅と同値に正規化 |
| Straight Line、Marker、Polygon、その他 | `set_size`非対応 | `ValueError` |

`ANNOTATION_CAPABILITIES`は7種を収録します。未登録種類を`annotation_capability()`で引くと`resizable=False`の仕様オブジェクトを返します。図形が画面上でサイズを持つことと、XDW_SetAnnotationSize経由で変更できることは別です。

## 5. 属性仕様

### 5.1 Standard Registryの読み方

`STANDARD_ATTRIBUTE_REGISTRY`は`(annotation_type: int, attribute_name: str)`をキーとするdictです。9種類・89組で、全89組が読取り可能、86組が書込み可能、3組が読取り専用の`%Points`です。以下は今回の配布実装から抽出した全項目です。SDK原文の転載や、SDK全体の網羅性を独立に宣言する表ではありません。

`int32`はraw側の整数格納です。自然型`color`のgetterはenumへ自動変換せず整数を返します。自然型`float`は数値入力から指定単位で変換しgetterはfloat、自然型`bool`は真偽値です。rawのbool属性setterは`True`／`False`を拒否し、0／1整数だけを受理します。型注釈がint32でも、範囲未登録の整数について符号付き32-bit全域を明示検証する処理はありません。ctypes変換による切捨てを利用せず、表の範囲と32-bit表現内で渡してください。

表の「制約」はraw値へ適用されます。たとえば`LineSpace`の100～1000は自然単位では1～10 lineです。「追加なし」は当該Registryに追加制約がない意味で、DLLが任意値を許容することではありません。条件はsetterが現在の標準raw属性値を読み出して確認します。getterはsetter条件を事前強制しません。

色集合は、標準色16色、背景色=標準色＋`NONE`、付箋色=`WHITE`／`STICKY_RED`／`STICKY_BLUE`／`STICKY_YELLOW`／`STICKY_LIME`です。正確な名称・整数値は第7節に示します。

### 5.1.1 TEXT — 18項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%Text` | R/W | `str` | `string` | — | 可 | 追加なし |
| `%FontName` | R/W | `str` | `string` | — | — | 追加なし |
| `%FontStyle` | R/W | `int` | `int32` | — | — | 0～15 |
| `%FontSize` | R/W | `float` | `int32` | pt → 1/10 pt | — | 追加なし |
| `%ForeColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%FontPitchAndFamily` | R/W | `int` | `int32` | — | — | 追加なし |
| `%FontCharSet` | R/W | `int` | `int32` | — | — | 追加なし |
| `%BackColor` | R/W | `color` | `int32` | — | — | 背景色17色 |
| `%WordWrap` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%TextDirection` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%TextOrientation` | R/W | `float` | `int32` | degree → degree | — | >= 0; <= 359 |
| `%LineSpace` | R/W | `float` | `int32` | line → 1/100 line | — | >= 100; <= 1000 |
| `%Spacing` | R/W | `float` | `int32` | pt → 1/10 pt | — | 追加なし |
| `%TopMargin` | R/W | `float` | `int32` | mm → 1/100 mm | — | >= 0; <= 20000 |
| `%LeftMargin` | R/W | `float` | `int32` | mm → 1/100 mm | — | >= 0; <= 20000 |
| `%BottomMargin` | R/W | `float` | `int32` | mm → 1/100 mm | — | >= 0; <= 20000 |
| `%RightMargin` | R/W | `float` | `int32` | mm → 1/100 mm | — | >= 0; <= 20000 |
| `%AutoResizeHeight` | R/W | `bool` | `int32` | — | — | 許容{0, 1}; 条件: %WordWrap=1 |

### 5.1.2 LINK — 24項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%Caption` | R/W | `str` | `string` | — | 可 | 暫定防御255 bytes、終端除外。SDK正式上限ではない |
| `%ShowIcon` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%Invisible` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%AutoResize` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%Tooltip` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%TooltipString` | R/W | `str` | `string` | — | 可 | 最大bytes=255 |
| `%LinkType` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2, 3, 4} |
| `%Url` | R/W | `str` | `string` | — | 可 | 条件: %LinkType=2; 最大bytes=255 |
| `%XdwPath` | R/W | `str` | `string` | — | 可 | 条件: %LinkType=1; 最大bytes=255 |
| `%XdwPathRelative` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%XdwLink` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%PageFrom` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2} |
| `%XdwNameInXbd` | R/W | `str` | `string` | — | 可 | 条件: %PageFrom=2 |
| `%XdwPage` | R/W | `int` | `int32` | — | — | 追加なし |
| `%LinkAtnTitle` | R/W | `str` | `string` | — | 可 | 最大bytes=255 |
| `%OtherFilePath` | R/W | `str` | `string` | — | 可 | 条件: %LinkType=3; 最大bytes=255 |
| `%OtherFilePathRelative` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%MailAddress` | R/W | `str` | `string` | — | 可 | 条件: %LinkType=4; 最大bytes=255 |
| `%FontName` | R/W | `str` | `string` | — | — | 追加なし |
| `%FontStyle` | R/W | `int` | `int32` | — | — | 0～15 |
| `%FontSize` | R/W | `float` | `int32` | pt → 1/10 pt | — | 追加なし |
| `%ForeColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%FontPitchAndFamily` | R/W | `int` | `int32` | — | — | 追加なし |
| `%FontCharSet` | R/W | `int` | `int32` | — | — | 追加なし |

### 5.1.3 STICKY — 2項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%FillColor` | R/W | `color` | `int32` | — | — | 付箋色5色 |
| `%AutoResize` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |

### 5.1.4 STRAIGHT_LINE — 7項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%BorderWidth` | R/W | `int` | `int32` | pt | — | 追加なし |
| `%BorderColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%BorderTransparent` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%ArrowheadType` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2, 3} |
| `%ArrowheadStyle` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2} |
| `%Points` | Rのみ | `points` | `point_array` | 絶対mm → 先頭絶対＋後続相対、1/100 mm | — | 追加なし |
| `%BorderType` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2, 3, 4} |

### 5.1.5 RECTANGLE — 6項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%BorderStyle` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%BorderWidth` | R/W | `int` | `int32` | pt | — | 追加なし |
| `%BorderColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%FillStyle` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%FillColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%FillTransparent` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |

### 5.1.6 ELLIPSE — 6項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%BorderStyle` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%BorderWidth` | R/W | `int` | `int32` | pt | — | 追加なし |
| `%BorderColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%FillStyle` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%FillColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%FillTransparent` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |

### 5.1.7 DATE_STAMP — 12項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%BorderColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%TopField` | R/W | `str` | `string` | — | 可 | 最大行数=2; 1行最大bytes=12 |
| `%BottomField` | R/W | `str` | `string` | — | 可 | 最大行数=2; 1行最大bytes=12 |
| `%DateStyle` | R/W | `int` | `int32` | — | — | 許容{0, 1} |
| `%BasisYearStyle` | R/W | `int` | `int32` | — | — | 許容{0, 1}; 条件: %DateStyle=0 |
| `%BasisYear` | R/W | `int` | `int32` | — | — | >= 1; <= 9999; 条件: %BasisYearStyle=1 |
| `%DateFieldFirstChar` | R/W | `str` | `string` | — | — | 最大文字数=1 |
| `%YearField` | R/W | `str` | `string` | — | — | 条件: %DateStyle=1; 最大文字数=4; ASCII英数字とハイフンのみ |
| `%MonthField` | R/W | `str` | `string` | — | — | 条件: %DateStyle=1; 最大文字数=4; ASCII英数字とハイフンのみ |
| `%DayField` | R/W | `str` | `string` | — | — | 条件: %DateStyle=1; 最大文字数=4; ASCII英数字とハイフンのみ |
| `%DateFormat` | R/W | `str` | `string` | — | — | 許容{dd.mmm.yy, dd.mmm.yyyy, yy.m.d, yy.mm.dd}; 条件: %DateStyle=0 |
| `%DateOrder` | R/W | `int` | `int32` | — | — | 許容{0, 1}; 条件: %DateStyle=1 |

### 5.1.8 MARKER — 4項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%BorderColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%BorderWidth` | R/W | `int` | `int32` | pt | — | 追加なし |
| `%BorderTransparent` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%Points` | Rのみ | `points` | `point_array` | 絶対mm → 先頭絶対＋後続相対、1/100 mm | — | 追加なし |

### 5.1.9 POLYGON — 10項目

| 属性名 | アクセス | 自然型 | raw格納 | 自然単位 → raw単位 | Unicode保存 | 制約（raw基準） |
| --- | --- | --- | --- | --- | --- | --- |
| `%BorderStyle` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%BorderWidth` | R/W | `int` | `int32` | pt | — | 追加なし |
| `%BorderColor` | R/W | `color` | `int32` | — | — | 標準色16色 |
| `%Close` | R/W | `bool` | `int32` | — | — | 許容{0, 1} |
| `%FillStyle` | R/W | `bool` | `int32` | — | — | 許容{0, 1}; 条件: %Close=1 |
| `%FillColor` | R/W | `color` | `int32` | — | — | 標準色16色; 条件: %Close=1 |
| `%FillTransparent` | R/W | `bool` | `int32` | — | — | 許容{0, 1}; 条件: %Close=1 |
| `%ArrowheadType` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2, 3} |
| `%ArrowheadStyle` | R/W | `int` | `int32` | — | — | 許容{0, 1, 2} |
| `%Points` | Rのみ | `points` | `point_array` | 絶対mm → 先頭絶対＋後続相対、1/100 mm | — | 追加なし |

### 5.2 Custom

| `CustomAttributeKind` | setter入力 | getterの`value` | 実装上の扱い |
| --- | --- | --- | --- |
| `INT` | `int`、bool不可 | `int` | 符号付き32-bit格納 |
| `STRING` | `str` | `str` | UTF-16。Windows ACPに依存しない |
| `DATE` | `int`、bool不可 | `int` | raw signed 32-bit。`datetime.date`変換なし |
| `BOOL` | `bool` | `bool` | CustomのBOOL種別。StandardのINT格納boolとは別 |
| `OTHER` | `None` | `None` | 非NULLポインターで「値なし属性」を設定 |

Custom名は`str`をUTF-16へ変換します。`delete_custom_attribute()`はNULLポインターで削除を指定し、OTHERの設定と区別します。`custom_attributes()`はDLL順序の1始まり列挙からtupleを作ります。

既存実装の`get_custom_attribute(name)`はDLLが必要サイズ0を返すと、kindにかかわらず`CustomAttribute(..., value=None)`を返します。空文字を必ず`""`で返す等、DLLの0-byte応答に対して表以上の一律な保証を置かないでください。想定外のkindまたは不正な戻り値サイズは`ValueError`になり得ます。

### 5.3 User

Userは名前付き任意binaryです。公開注釈は`bytes`ですが、実装は`bytes`、`bytearray`、`memoryview`を受理してbytesへコピーします。名前は選択したmultibyte codepageで符号化し、255 bytes以内です。getterはbytesを返し、列挙APIはありません。

`set_user_attribute(name, b"")`は非NULLポインター＋size 0、`delete_user_attribute(name)`はNULLポインター＋size 0です。ctypes呼出しとしては区別しています。しかし添付記録と今回のXDWAPI 10.1.1実機試験では、0-byte値のsetter成功後のGETが設定直後・save／close／reopen後とも`XDW_E_UNEXPECTED`でした。ゼロ長値の取得と永続化は保証対象に含めません。必要ならアプリケーション側で非空の表現を設計してください。

### 5.4 エンコーディング

`MultibyteEncodingPolicy.create(None)`はWindowsの`GetACP()`を使います。明示codepageは正の整数へ変換し、Pythonの`cp{codepage}` codecが存在することを確認します。`open_xdw(codepage=...)`は`XdwApi.load(multibyte_codepage=...)`へ渡されます。

Unicode対応Standard属性のsetterはUTF-16入力と`XDW_TEXT_UNICODE_IFNECESSARY`を使い、選択codepageも渡します。非対応Standard文字列は選択したmultibyte codecで符号化します。Unicode対応のGETはW getterで取得したUTF-16を復号し、GETのcodepage引数にはACPまたは明示値を渡します。UTF-16バッファであることだけを理由に1200を渡しません。

Registryのbytes制限は、選択codepageで表現できればそのbytes数、できずUnicode対応ならUTF-16LEのbytes数で判定します。文字数制限とは異なります。Unicode非対応文字列の表現不能文字は`UnicodeEncodeError`です。Custom STRINGはこのACP選択と別にUTF-16です。

## 6. DLL探索・検査・ロード

### 6.1 候補の生成

明示`dll_path`がある場合は、絶対パス、名前が`xdwapi.dll`、実在ファイルという条件を検査し、そのdirectoryだけを候補にします。失敗時にSystem32へfallbackしません。

明示指定がない場合は次を候補化し、正規化したメインDLLパスのcase-insensitive identityで重複を除きます。

1. `%WINDIR%\System32`（source=`installed`）
2. `search_paths`の各要素（source=`search_path`）
3. 環境変数`DOCUWORKS_XDWAPI_PATHS`の各要素（Windowsではセミコロン区切り、source=`environment`）

`search_paths`と環境変数はdirectory、または末尾が`xdwapi.dll`のパスを受け取ります。Downloads全体や任意directoryの再帰検索、通常のPATH全体の検索は行いません。DocuWorksの版情報は`HKLM\SOFTWARE\FUJIFILM\MPM3\SystemInfo`のMajorVersion／MinorVersion／PatchVersionを読み、取得できなければ不明として扱います。

### 6.2 bundle検査と子process probe

必須ファイルは同一directoryの`xdwapi.dll`、`xdwapia.dll`、`xdwapib.dll`です。`xdwxml.dll`があればモデルに記録しますが、必須3ファイルの検査とは別です。

- 必須3ファイルをPEとして検査し、AMD64か、FileVersion／ProductVersionとSHA-256を取得できるかを確認します。
- 取得できた非ゼロProductVersion majorが複数異なる場合は不適格です。companionのpatch差だけでは拒否しません。
- メインDLLに`FUNCTION_SPECS`の全141 exportがあることを確認します。使うCore機能が少なくても不足exportを黙認しません。
- 静的に適格な候補を、同じPython実行ファイルの子processでloadし、`XDW_GetInformationW`を呼びます。`verification_document`がある場合はread-only／NO_DIALOGでopen→ページ数取得→closeも実行します。タイムアウト既定は候補ごとに15秒です。
- 情報取得に成功し、文書probeを要求した場合は文書openにも成功した候補だけを選択対象にします。タイムアウト、process異常終了、不正JSON、DLLエラーは`ProbeResult`／拒否理由へ記録します。

### 6.3 選択順位と呼出し側processへのload

適格候補は、(1) installed DocuWorksのmajorとの一致、(2) sourceがinstalledであること、(3) メインDLLのFileVersionの順で辞書式比較し、最大を選びます。同じscoreなら候補列挙で先に出たものです。「常に最大のSDK版を選ぶ」という動作ではありません。

候補がなければ`RuntimeResolutionError`で、`report`に診断を保持します。`inspect_runtimes()`は候補なしでも`selected=None`のreportを返します。存在しないverification documentや不正な明示パスなど、候補評価前のエラーはその場で例外となります。

呼出し側processへloadする際には、3 DLLの名前が別directoryから既にloadされていないかを確認し、競合時に`RuntimeBundleConflictError`を送出します。`os.add_dll_directory`と一時的なDLL directory設定を用いて`ctypes.WinDLL`を呼びます。directory設定の復元はfinallyで行います。内部lockはこのload処理を直列化しますが、文書の並行操作やXDWAPI全体のスレッド安全性を保証するものではありません。

`XdwApi.load()`は呼出し側でも版を再取得し、最低版を検査します。文書を検証せずにloadだけ成功した場合と、文書open／保存まで成功した場合を区別してください。bundleを切り替える比較試験は別processで実行します。公開APIにDLLを明示unloadする操作はありません。

### 6.4 診断モデル

`RuntimeInfo`はXDW報告版、Python bit数、選択DLLのパス・FileVersion・ProductVersion・SHA-256、必須bundleファイル情報、installed DocuWorks情報、`ResolutionReport`を別々に保持します。これらの版番号は同じ意味ではありません。

`ResolutionReport.to_dict()`はdataclassを展開し、Pathを文字列、tupleをlistにしてJSON用に変換します。`selected_report`は選択候補または`None`、`ProbeResult.eligible`は情報取得・要求された文書openの成否から適格性を返します。

## 7. 公開型・値・安定性境界

### 7.1 トップレベルの全49公開名

以下は`docuworks_ctypes.__all__`と固定snapshotが記録する全名称です。`__version__`は`1.0.1`として参照できますが、49個の`__all__`には含まれません。

| 公開名 | 役割 |
| --- | --- |
| `Annotation` | Coreのアノテーションwrapper |
| `ANNOTATION_CAPABILITIES` | 種類別resize仕様dict |
| `AnnotationCapabilitySpec` | resize仕様のfrozen dataclass |
| `AnnotationRefreshError` | 追加後の公式情報取得失敗 |
| `AnnotationType` | enum（全値は下表） |
| `ArrowheadStyle` | enum（全値は下表） |
| `AttributeCondition` | 標準raw属性の条件 |
| `ArrowheadType` | enum（全値は下表） |
| `AttributeType` | enum（全値は下表） |
| `AuthMode` | enum（全値は下表） |
| `BitnessMismatchError` | 例外（第8節） |
| `BorderType` | enum（全値は下表） |
| `ClosedHandleError` | 例外（第8節） |
| `Color` | enum（全値は下表） |
| `CandidateReport` | DLL候補単位の診断 |
| `CustomAttribute` | Custom名・kind・値 |
| `CustomAttributeKind` | enum（全値は下表） |
| `DllNotFoundError` | 例外（第8節） |
| `DllBundle` | 同じdirectoryのDLL bundle |
| `DllFileInfo` | 単一DLLの版・hash・PE machine |
| `Document` | 文書ハンドル所有者 |
| `DocuWorksError` | ライブラリ例外の基底 |
| `MINIMUM_VERSION` | (9, 1, 7) |
| `InstalledDocuWorksInfo` | レジストリから得る製品版情報 |
| `LinkPageFrom` | enum（全値は下表） |
| `LinkType` | enum（全値は下表） |
| `MultibyteEncodingPolicy` | ACPまたは明示codepageの符号化方針 |
| `OpenMode` | enum（全値は下表） |
| `Page` | 文書の1ページ |
| `PlatformNotSupportedError` | 例外（第8節） |
| `PointMM` | mm座標 |
| `RawPoint` | raw 1/100 mm座標値 |
| `ProbeResult` | 子process検査結果 |
| `ReadOnlyDocumentError` | 例外（第8節） |
| `RectMM` | mm矩形 |
| `RuntimeInfo` | 選択runtimeの診断情報 |
| `RuntimeBundleConflictError` | 例外（第8節） |
| `RuntimeResolutionError` | 例外（第8節） |
| `ResolutionReport` | 全候補と選択結果 |
| `STANDARD_ATTRIBUTE_REGISTRY` | 種類と属性名をキーとする89組のRegistry |
| `SizeMM` | mmサイズ |
| `StandardAttributeSpec` | 1組のStandard属性仕様 |
| `StaticValidation` | bundleの静的検査結果 |
| `UnsupportedVersionError` | 例外（第8節） |
| `XdwApi` | load・診断・文書openの入口 |
| `XdwError` | 例外（第8節） |
| `standard_attribute_spec` | (annotation_type, name)からStandardAttributeSpecを取得 |
| `annotation_capability` | 種類別AnnotationCapabilitySpecを取得 |
| `system_ansi_codepage` | Windows GetACPの値をintで取得 |

### 7.2 enumの全メンバーと整数値

以下の11種類は固定snapshotに収録されます。値は配布実装から抽出しています。色はCOLORREFの整数表現で、通常の`0xRRGGBB`表記とは順序が異なります。色の構築や任意RGBからの変換を行うSimple APIはありません。

#### AnnotationType

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `OLE` | 32783 | `0x0000800F` |
| `TEXT` | 32785 | `0x00008011` |
| `STICKY` | 32794 | `0x0000801A` |
| `MARKER` | 32795 | `0x0000801B` |
| `DATE_STAMP` | 32819 | `0x00008033` |
| `STRAIGHT_LINE` | 32828 | `0x0000803C` |
| `RECTANGLE` | 32829 | `0x0000803D` |
| `ELLIPSE` | 32830 | `0x0000803E` |
| `BITMAP` | 32831 | `0x0000803F` |
| `POLYGON` | 32834 | `0x00008042` |
| `CUSTOM` | 32837 | `0x00008045` |
| `TITLE` | 32838 | `0x00008046` |
| `GROUP` | 32839 | `0x00008047` |
| `LINK` | 49199 | `0x0000C02F` |
| `PAGE_FORM` | 32814 | `0x0000802E` |

#### ArrowheadStyle

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `WIDE_POLYLINE` | 0 | `0x00000000` |
| `POLYLINE` | 1 | `0x00000001` |
| `POLYGON` | 2 | `0x00000002` |

#### ArrowheadType

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `NONE` | 0 | `0x00000000` |
| `BEGINNING` | 1 | `0x00000001` |
| `ENDING` | 2 | `0x00000002` |
| `BOTH` | 3 | `0x00000003` |

#### AttributeType

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `INT` | 0 | `0x00000000` |
| `STRING` | 1 | `0x00000001` |
| `DATE` | 2 | `0x00000002` |
| `BOOL` | 3 | `0x00000003` |
| `OCTETS` | 4 | `0x00000004` |
| `OTHER` | 999 | `0x000003E7` |

#### AuthMode

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `NONE` | 0 | `0x00000000` |
| `NO_DIALOG` | 1 | `0x00000001` |
| `CONDITIONAL_DIALOG` | 2 | `0x00000002` |

#### BorderType

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `SOLID` | 0 | `0x00000000` |
| `DOT` | 1 | `0x00000001` |
| `DASH` | 2 | `0x00000002` |
| `DASH_DOT` | 3 | `0x00000003` |
| `DOUBLE` | 4 | `0x00000004` |

#### Color

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `NONE` | 65793 | `0x00010101` |
| `BLACK` | 0 | `0x00000000` |
| `RED` | 255 | `0x000000FF` |
| `GREEN` | 32768 | `0x00008000` |
| `BLUE` | 16711680 | `0x00FF0000` |
| `YELLOW` | 65535 | `0x0000FFFF` |
| `WHITE` | 16777215 | `0x00FFFFFF` |
| `GRAY` | 8421504 | `0x00808080` |
| `MAROON` | 128 | `0x00000080` |
| `OLIVE` | 32896 | `0x00008080` |
| `NAVY` | 8388608 | `0x00800000` |
| `PURPLE` | 8388736 | `0x00800080` |
| `TEAL` | 8421376 | `0x00808000` |
| `SILVER` | 12632256 | `0x00C0C0C0` |
| `LIME` | 65280 | `0x0000FF00` |
| `FUCHIA` | 16711935 | `0x00FF00FF` |
| `AQUA` | 16776960 | `0x00FFFF00` |
| `STICKY_RED` | 16761599 | `0x00FFC2FF` |
| `STICKY_BLUE` | 16760733 | `0x00FFBF9D` |
| `STICKY_YELLOW` | 6619135 | `0x0064FFFF` |
| `STICKY_LIME` | 12779421 | `0x00C2FF9D` |

#### CustomAttributeKind

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `INT` | 0 | `0x00000000` |
| `STRING` | 1 | `0x00000001` |
| `DATE` | 2 | `0x00000002` |
| `BOOL` | 3 | `0x00000003` |
| `OTHER` | 999 | `0x000003E7` |

#### LinkPageFrom

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `XDW` | 0 | `0x00000000` |
| `BINDER` | 1 | `0x00000001` |
| `XDW_IN_BINDER` | 2 | `0x00000002` |

#### LinkType

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `THIS_DOCUMENT` | 0 | `0x00000000` |
| `XDW` | 1 | `0x00000001` |
| `URL` | 2 | `0x00000002` |
| `OTHER_FILE` | 3 | `0x00000003` |
| `MAIL_ADDRESS` | 4 | `0x00000004` |

#### OpenMode

| メンバー | 整数値 | 16進値 |
| --- | --- | --- |
| `READONLY` | 0 | `0x00000000` |
| `UPDATE` | 1 | `0x00000001` |

### 7.3 公開dataclassと補助API

以下の型はfrozen dataclassです。フィールド、必須／既定値、公開補助methodを示します。`StorageKind`は`"int32" | "string" | "point_array"`、`PythonKind`は`"int" | "float" | "str" | "bool" | "color" | "points"`、`HeightBehavior`は`"independent" | "equal_width"`という型エイリアスです。型エイリアス自体を49公開名へ追加するものではありません。

```python
class PointMM:
    x: float
    y: float

class RawPoint:
    x: int
    y: int

    def to_mm(self) -> PointMM:
        ...

class SizeMM:
    width: float
    height: float

class RectMM:
    x: float
    y: float
    width: float
    height: float
```

```python
class AttributeCondition:
    attribute_name: str
    equals: int

class StandardAttributeSpec:
    name: str
    annotation_type: int
    storage_kind: StorageKind
    python_kind: PythonKind
    readable: bool = True
    writable: bool = True
    unit: str | None = None
    python_unit: str | None = None
    raw_per_python_unit: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    allowed_values: frozenset[int | str] | None = None
    unicode_allowed: bool = False
    conditions: tuple[AttributeCondition, ...] = ()
    max_bytes: int | None = None
    max_chars: int | None = None
    max_lines: int | None = None
    max_bytes_per_line: int | None = None
    allowed_characters: frozenset[str] | None = None

class CustomAttribute:
    name: str
    kind: CustomAttributeKind
    value: int | str | bool | None
```

```python
class AnnotationCapabilitySpec:
    annotation_type: int
    resizable: bool
    minimum_width_mm: float | None = None
    maximum_width_mm: float | None = None
    minimum_height_mm: float | None = None
    maximum_height_mm: float | None = None
    height_behavior: HeightBehavior = 'independent'
    resize_conditions: tuple[AttributeCondition, ...] = ()
```

```python
class MultibyteEncodingPolicy:
    codepage: int
    codec: str

    @classmethod
    def create(cls, codepage: int | None=None) -> 'MultibyteEncodingPolicy':
        ...

    def encode(self, value: str) -> bytes:
        ...

    def encoded_length(self, value: str, *, unicode_allowed: bool) -> int:
        ...
```

```python
class RuntimeInfo:
    version_text: str
    version: tuple[int, ...]
    dll_path: Path | None
    python_bits: int
    dll_file_version: tuple[int, ...] = ()
    dll_product_version: tuple[int, ...] = ()
    dll_sha256: str | None = None
    bundle_files: tuple[DllFileInfo, ...] = ()
    runtime_source: str | None = None
    installed_docuworks: InstalledDocuWorksInfo | None = None
    resolution_report: ResolutionReport | None = None
```

```python
class InstalledDocuWorksInfo:
    version: tuple[int, ...]
    trial: bool | None = None

class DllBundle:
    directory: Path
    xdwapi: Path
    xdwapia: Path
    xdwapib: Path
    xdwxml: Path | None
    source: str

    @classmethod
    def from_directory(cls, directory: Path, source: str) -> 'DllBundle':
        ...

    @property
    def identity(self) -> str:
        ...

class DllFileInfo:
    path: Path
    machine: int
    file_version: tuple[int, ...]
    product_version: tuple[int, ...]
    sha256: str

class StaticValidation:
    valid: bool
    errors: tuple[str, ...]
    files: tuple[DllFileInfo, ...] = ()
    missing_exports: tuple[str, ...] = ()

    @property
    def main_file(self) -> DllFileInfo | None:
        ...

class ProbeResult:
    attempted: bool
    get_information_ok: bool = False
    reported_version: str | None = None
    document_probe_requested: bool = False
    document_open_ok: bool | None = None
    document_page_count: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    xdw_error_code: int | None = None
    timed_out: bool = False
    crashed: bool = False
    duration_seconds: float = 0.0

    @property
    def eligible(self) -> bool:
        ...

class CandidateReport:
    bundle: DllBundle
    static: StaticValidation
    probe: ProbeResult
    score: tuple[int, ...] = ()
    selected: bool = False
    rejection_reason: str | None = None

    def mark_selected(self) -> 'CandidateReport':
        ...

class ResolutionReport:
    candidates: tuple[CandidateReport, ...]
    selected: DllBundle | None
    installed_docuworks: InstalledDocuWorksInfo | None
    verification_document: Path | None
    explicit: bool

    @property
    def selected_report(self) -> CandidateReport | None:
        ...

    def to_dict(self) -> dict[str, Any]:
        ...
```

```python
def standard_attribute_spec(annotation_type: int, name: str) -> StandardAttributeSpec:
    ...

def annotation_capability(annotation_type: int) -> AnnotationCapabilitySpec:
    ...

def system_ansi_codepage() -> int:
    ...
```

`RawPoint.to_mm()`はそのx/yを個別に100で割るだけです。raw Points列全体を第1点基準の絶対座標へ変換する操作はStandard自然getter側にあります。raw列の全点へ単純に`to_mm()`を適用するだけでは、2点目以降は相対値のままです。

### 7.4 安定性の宣言と機械検証の違い

1.x安定性方針は、既存の公開名、Simple署名、enum名・値、自然単位、1始まりページ番号、明示保存、列挙・寿命・例外、Standard／Custom／User分離、文書化されたCore raw契約を維持するとしています。削除・改名・単位変更・保存や寿命の変更・enum契約や例外変更は2.0と移行資料が必要という方針です。

一方、`PUBLIC_API_1.0.json`の機械可読範囲は、49公開名、Simple4公開名、23署名、11enumです。Coreメソッドの署名、dataclassフィールド、Raw141署名、SimpleDocument／SimplePageの`core`インスタンス属性、context methodはすべてがsnapshotに入るわけではありません。snapshot一致だけで公開契約全体の不変を証明できません。

23署名はSimpleAnnotationの初期化＋4 property＋3操作の8件、SimpleDocumentの初期化＋page／save／closeの4件、SimplePageの初期化＋annotations＋8作成の10件、`open_xdw`の1件です。source同梱`generate_public_api.py`が抽出対象を定義します。既存テストはJSONをloadしてオブジェクト同士を比較します。元方針の「byte-for-byte」記述とは異なり、空白・改行等の完全一致を確認するテストではありません。

## 8. 例外と障害時の診断

| 例外 | 代表的な発生条件／追加情報 |
| --- | --- |
| `DocuWorksError` | 以下のライブラリ独自例外の基底 |
| `PlatformNotSupportedError` | Windows以外のruntime探索／load。パッケージ全体の非Windows import成功までは保証しない |
| `BitnessMismatchError` | runtime探索時のPythonが64-bitではない |
| `DllNotFoundError` | 明示dll_pathが相対、名前違い、または不存在 |
| `RuntimeResolutionError` | 適格bundleなし。`report`に`ResolutionReport`を保持 |
| `RuntimeBundleConflictError` | 別directoryの同名DLLが呼出し側processでload済み |
| `UnsupportedVersionError` | XDW報告版を解析できない、または最低9.1.7未満 |
| `ReadOnlyDocumentError` | read-onlyの文書へ保存・変更を試みた |
| `ClosedHandleError` | 文書close済み、または操作対象wrapperが削除済み |
| `AnnotationRefreshError` | 追加DLL成功後に返されたハンドルを公式列挙情報から見つけられない |
| `XdwError` | DLLの負のsigned 32-bit戻り値。下記4属性を保持 |
| `TypeError` | Simpleのenum違い、属性型違い、Points要素型違い等 |
| `ValueError` | 属性未登録、値域・条件違反、サイズ不正、Points読取り専用、戻り値サイズ不正等 |
| `IndexError` | 文書のページ番号が1未満またはページ数を超える |
| `FileNotFoundError` | 文書・verification document・ANNパスがファイルではない |
| `UnicodeEncodeError`等 | 選択codepageで表現できない非Unicode文字列、復号上の問題等 |
| `OSError`等 | WinDLL load、Windows DLL directory操作、OS／ファイル操作等 |

`XdwError`には`result`（signed int32）、`unsigned_result`（unsigned int32）、`operation`（呼出し箇所の文字列）、`symbol`（既知エラー名または`None`）があります。メッセージには16進コードを含みます。非負の戻り値は成功として扱うため、戻り値が正のサイズ・件数である関数を0のみ成功として扱いません。

`Document.__exit__`は本体例外がないclose失敗を送出し、本体例外がある場合は元例外を維持します。3.11以降は可能ならclose失敗を注記し、3.10では注記を省略します。注記の失敗でも元例外は置き換えません。1.0.0にあった無条件add_noteの問題は1.0.1で修正しました。

独自例外へすべてを統一する層はなく、引数誤りと生存状態違反が重なる場合の優先順位も全API共通ではありません。たとえばSimpleのenum検査はCoreのread-only検査より先に実行されます。

## 9. Raw ABI

今回、公式SDK 9.1.7ヘッダーの141関数とbind定義を照合し、全件一致しました。MSVC x64の実測でSYSTEMTIMEを含む63構造体・342フィールドのサイズ、整列、オフセットもctypesと一致しました。System32 DLLには必要141 exportが存在します。const修飾や書込みバッファ安全性、全関数の実機動作をこの検査だけで保証するものではありません。

`docuworks_ctypes._raw.api.RawApi`はloadしたWinDLLへ、`FUNCTION_SPECS`から`restype`／`argtypes`を遅延設定します。`has_function(name)`は登録とDLL側の存在を確認し、未登録名はFalseです。未知の属性アクセスは`AttributeError`です。

`_raw.__all__`は`constants`、`types`、`FUNCTION_COUNT`、`FUNCTION_SPECS`です。`RawApi`はトップレベル49公開名にもSimple公開名にもありません。先頭underscoreの内部パッケージを使うコードは、Simpleの固定署名や自動的な安全検査と同じ安定性を期待せず、必要なABIを固定して保守してください。

生成型では`XDW_WCHAR = ctypes.c_uint16`、`BOOL = ctypes.c_int32`、各XDW handleは`ctypes.c_void_p`、構造体の`_pack_ = 8`です。W文字列はUTF-16LEのcode unitとして扱います。Python `str`やplatform依存の`c_wchar`を無条件に置換して渡す設計ではありません。

RawはDLL呼出しの戻り値をそのまま返します。Coreの`check_result`による`XdwError`化、Standard属性Registry、mm変換、生存状態、read-only状態、明示save方針を自動適用しません。呼出し側がバッファ容量・型・ポインター・文字コード・nSize・reserved値・ハンドル所有と解放の整合を管理します。Rawを使って変更した後はCoreキャッシュを再利用せず必要な情報を再取得してください。

### 9.1 登録される全141関数とctypes署名

以下は配布コードの`FUNCTION_SPECS`から抽出した登録内容です。左が関数名、右が`(戻り値型, 引数型tuple)`です。`ctypes`を`C`、生成型moduleを`T`と略記します。これはwrapperのbind定義であり、SDK原文の引数意味・前提条件・権利を置き換えるものではありません。各関数が今回の実機試験で実行されたことも意味しません。

```text
XDW_GetInformation: (C.c_int32, (C.c_int32, C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetInformationW: (C.c_int32, (C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_void_p))
XDW_AddSystemFolder: (C.c_int32, (C.c_int32, C.c_void_p))
XDW_MergeXdwFiles: (C.c_int32, (C.POINTER(C.c_char_p), C.c_int32, C.c_char_p, C.c_void_p))
XDW_MergeXdwFilesW: (C.c_int32, (C.POINTER(C.POINTER(T.XDW_WCHAR)), C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_OpenDocumentHandle: (C.c_int32, (C.c_char_p, C.POINTER(T.XDW_DOCUMENT_HANDLE), C.POINTER(T.XDW_OPEN_MODE)))
XDW_OpenDocumentHandleW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_DOCUMENT_HANDLE), C.POINTER(T.XDW_OPEN_MODE)))
XDW_CloseDocumentHandle: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_void_p))
XDW_GetDocumentInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.POINTER(T.XDW_DOCUMENT_INFO)))
XDW_GetPageInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_PAGE_INFO)))
XDW_GetPageImage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetPageImageW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_GetPageText: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_ConvertPageToImageFile: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.POINTER(T.XDW_IMAGE_OPTION)))
XDW_ConvertPageToImageFileW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_IMAGE_OPTION)))
XDW_GetPage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetPageW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_DeletePage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_RotatePage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_int32, C.c_void_p))
XDW_SaveDocument: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_void_p))
XDW_CreateXdwFromImageFile: (C.c_int32, (C.c_char_p, C.c_char_p, C.POINTER(T.XDW_CREATE_OPTION)))
XDW_CreateXdwFromImageFileW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_CREATE_OPTION)))
XDW_GetOriginalDataInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_ORGDATA_INFO), C.c_void_p))
XDW_GetOriginalData: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetOriginalDataW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_InsertOriginalData: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_DeleteOriginalData: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_BeginCreationFromAppFile: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_int32, C.POINTER(T.XDW_CREATE_HANDLE), C.c_void_p))
XDW_BeginCreationFromAppFileW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_int32, C.POINTER(T.XDW_CREATE_HANDLE), C.c_void_p))
XDW_EndCreationFromAppFile: (C.c_int32, (T.XDW_CREATE_HANDLE, C.c_void_p))
XDW_GetStatusCreationFromAppFile: (C.c_int32, (T.XDW_CREATE_HANDLE, C.POINTER(T.XDW_CREATE_STATUS)))
XDW_CancelCreationFromAppFile: (C.c_int32, (T.XDW_CREATE_HANDLE, C.c_void_p))
XDW_GetUserAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetUserAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetAnnotationInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.POINTER(T.XDW_ANNOTATION_INFO), C.c_void_p))
XDW_GetAnnotationAttribute: (C.c_int32, (T.XDW_ANNOTATION_HANDLE, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_AddAnnotation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_int32, C.c_int32, C.c_int32, C.POINTER(T.XDW_AA_INITIAL_DATA), C.POINTER(T.XDW_ANNOTATION_HANDLE), C.c_void_p))
XDW_RemoveAnnotation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_void_p))
XDW_SetAnnotationAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_char_p, C.c_int32, C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetAnnotationSize: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.c_int32, C.c_void_p))
XDW_SetAnnotationPosition: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.c_int32, C.c_void_p))
XDW_CreateSfxDocument: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_void_p))
XDW_CreateSfxDocumentW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_ExtractFromSfxDocument: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_void_p))
XDW_ExtractFromSfxDocumentW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_ConvertPageToImageHandle: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(C.c_void_p), C.POINTER(T.XDW_IMAGE_OPTION)))
XDW_GetThumbnailImageHandle: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(C.c_void_p), C.c_void_p))
XDW_GetPageTextToMemory: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetFullText: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.c_void_p))
XDW_GetPageUserAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetPageUserAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_ReducePageNoise: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_int32, C.c_void_p))
XDW_ShowOrHideAnnotations: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_GetCompressedPageImage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetCompressedPageImageW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_InsertDocument: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_InsertDocumentW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_ApplyOcr: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_int32, C.c_void_p, C.c_void_p))
XDW_RotatePageAuto: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_CreateBinder: (C.c_int32, (C.c_char_p, C.POINTER(T.XDW_BINDER_INITIAL_DATA), C.c_void_p))
XDW_CreateBinderW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_BINDER_INITIAL_DATA), C.c_void_p))
XDW_InsertDocumentToBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetDocumentFromBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetDocumentFromBinderW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_DeleteDocumentInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_GetDocumentNameInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetDocumentNameInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetDocumentInformationInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_DOCUMENT_INFO), C.c_void_p))
XDW_Finalize: (C.c_int32, (C.c_void_p,))
XDW_GetPageColorInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_PAGE_COLOR_INFO), C.c_void_p))
XDW_OptimizeDocument: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_void_p))
XDW_OptimizeDocumentW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_ProtectDocument: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p, C.c_void_p))
XDW_ProtectDocumentW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_void_p, C.c_void_p))
XDW_CreateXdwFromImageFileAndInsertDocument: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.POINTER(T.XDW_CREATE_OPTION), C.c_void_p))
XDW_CreateXdwFromImageFileAndInsertDocumentW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_CREATE_OPTION), C.c_void_p))
XDW_GetDocumentAttributeNumber: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_void_p))
XDW_GetDocumentAttributeByName: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.POINTER(C.c_int32), C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetDocumentAttributeByOrder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.POINTER(C.c_int32), C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetDocumentAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.c_int32, C.c_char_p, C.c_void_p))
XDW_SucceedAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.c_int32, C.c_int32, C.c_void_p))
XDW_SucceedAttributeW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_int32, C.c_void_p))
XDW_GetPageFormAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetPageFormAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_int32, C.c_char_p, C.c_int32, C.c_void_p))
XDW_UpdatePageForm: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_RemovePageForm: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_GetLinkRootFolderInformation: (C.c_int32, (C.c_int32, C.POINTER(T.XDW_LINKROOTFOLDER_INFO), C.c_void_p))
XDW_GetLinkRootFolderInformationW: (C.c_int32, (C.c_int32, C.POINTER(T.XDW_LINKROOTFOLDER_INFOW), C.c_void_p))
XDW_GetLinkRootFolderNumber: (C.c_int32, (C.c_void_p,))
XDW_GetLinkRootFolderNumberW: (C.c_int32, (C.c_void_p,))
XDW_GetPageTextInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p, C.c_void_p))
XDW_GetDocumentSignatureNumber: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_void_p))
XDW_AddAnnotationOnParentAnnotation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.c_int32, C.c_int32, C.POINTER(T.XDW_AA_INITIAL_DATA), C.POINTER(T.XDW_ANNOTATION_HANDLE), C.c_void_p))
XDW_SignDocument: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p))
XDW_SignDocumentW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p))
XDW_GetSignatureInformation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p))
XDW_UpdateSignatureStatus: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p))
XDW_GetOcrImage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.c_void_p, C.c_void_p))
XDW_GetOcrImageW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p, C.c_void_p))
XDW_SetOcrData: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_OCR_TEXTINFO), C.c_void_p))
XDW_GetDocumentAttributeNumberInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_void_p))
XDW_GetDocumentAttributeByNameInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.POINTER(C.c_int32), C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetDocumentAttributeByOrderInBinder: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_int32, C.c_char_p, C.POINTER(C.c_int32), C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetTMInfo: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_void_p, C.c_int32, C.c_void_p))
XDW_SetTMInfo: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_void_p, C.c_int32, C.c_void_p))
XDW_CreateXdwFromImagePdfFile: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_void_p))
XDW_FindTextInPage: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_char_p, C.POINTER(T.XDW_FIND_TEXT_OPTION), C.POINTER(T.XDW_FOUND_HANDLE), C.c_void_p))
XDW_FindNext: (C.c_int32, (C.POINTER(T.XDW_FOUND_HANDLE), C.c_void_p))
XDW_GetNumberOfRectsInFoundObject: (C.c_int32, (T.XDW_FOUND_HANDLE, C.c_void_p))
XDW_GetRectInFoundObject: (C.c_int32, (T.XDW_FOUND_HANDLE, C.c_int32, C.POINTER(T.XDW_RECT), C.POINTER(C.c_int32), C.c_void_p))
XDW_CloseFoundHandle: (C.c_int32, (T.XDW_FOUND_HANDLE,))
XDW_GetAnnotationUserAttribute: (C.c_int32, (T.XDW_ANNOTATION_HANDLE, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_SetAnnotationUserAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_char_p, C.c_char_p, C.c_int32, C.c_void_p))
XDW_StarchAnnotation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.c_void_p))
XDW_ReleaseProtectionOfDocument: (C.c_int32, (C.c_char_p, C.c_char_p, C.c_void_p))
XDW_ReleaseProtectionOfDocumentW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_GetProtectionInformation: (C.c_int32, (C.c_char_p, C.POINTER(T.XDW_PROTECTION_INFO), C.c_void_p))
XDW_GetProtectionInformationW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_PROTECTION_INFO), C.c_void_p))
XDW_GetAnnotationCustomAttributeByName: (C.c_int32, (T.XDW_ANNOTATION_HANDLE, C.POINTER(T.XDW_WCHAR), C.POINTER(C.c_int32), C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetAnnotationCustomAttributeByOrder: (C.c_int32, (T.XDW_ANNOTATION_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.POINTER(C.c_int32), C.c_char_p, C.c_int32, C.c_void_p))
XDW_GetAnnotationCustomAttributeNumber: (C.c_int32, (T.XDW_ANNOTATION_HANDLE, C.c_void_p))
XDW_SetAnnotationCustomAttribute: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_char_p, C.c_void_p))
XDW_GetPageTextToMemoryW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_void_p))
XDW_GetFullTextW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.POINTER(T.XDW_WCHAR), C.c_void_p))
XDW_GetAnnotationAttributeW: (C.c_int32, (T.XDW_ANNOTATION_HANDLE, C.c_char_p, C.c_void_p, C.c_int32, C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_SetAnnotationAttributeW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_char_p, C.c_int32, C.c_void_p, C.c_int32, C.c_uint32, C.c_int32, C.c_void_p))
XDW_GetDocumentAttributeByNameW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.POINTER(T.XDW_WCHAR), C.POINTER(C.c_int32), C.c_void_p, C.c_int32, C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_GetDocumentAttributeByOrderW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.POINTER(C.c_int32), C.c_void_p, C.c_int32, C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_GetDocumentAttributeByNameInBinderW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.POINTER(C.c_int32), C.c_void_p, C.c_int32, C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_GetDocumentAttributeByOrderInBinderW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.c_int32, C.POINTER(T.XDW_WCHAR), C.POINTER(C.c_int32), C.c_void_p, C.c_int32, C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_SetDocumentAttributeW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_void_p, C.c_int32, C.c_uint32, C.c_void_p))
XDW_GetDocumentNameInBinderW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_int32, C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_SetDocumentNameInBinderW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_uint32, C.c_void_p))
XDW_GetOriginalDataInformationW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_ORGDATA_INFOW), C.POINTER(C.c_int32), C.c_uint32, C.c_void_p))
XDW_AddAnnotationFromAnnFile: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_char_p, C.c_int32, C.c_int32, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.c_int32, C.POINTER(T.XDW_ANNOTATION_HANDLE), C.c_void_p))
XDW_AddAnnotationFromAnnFileW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.POINTER(T.XDW_WCHAR), C.c_int32, C.c_int32, T.XDW_ANNOTATION_HANDLE, C.c_int32, C.c_int32, C.POINTER(T.XDW_ANNOTATION_HANDLE), C.c_void_p))
XDW_GroupAnnotations: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, T.XDW_ANNOTATION_HANDLE, C.POINTER(C.c_int32), C.c_int32, C.POINTER(T.XDW_ANNOTATION_HANDLE), C.c_void_p))
XDW_UnGroupAnnotation: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, T.XDW_ANNOTATION_HANDLE, C.c_void_p))
XDW_OpenDocumentHandleEx: (C.c_int32, (C.c_char_p, C.POINTER(T.XDW_DOCUMENT_HANDLE), C.POINTER(T.XDW_OPEN_MODE)))
XDW_OpenDocumentHandleExW: (C.c_int32, (C.POINTER(T.XDW_WCHAR), C.POINTER(T.XDW_DOCUMENT_HANDLE), C.POINTER(T.XDW_OPEN_MODE)))
XDW_InsertOriginalDataW: (C.c_int32, (T.XDW_DOCUMENT_HANDLE, C.c_int32, C.POINTER(T.XDW_WCHAR), C.c_void_p))
```

## 10. 既知の制約と検証対応

### 10.1 実装・運用上の制約

- User 0-byte値は呼出しの非NULL表現を確認していても、XDWAPI 10.1.1でGET／永続取得は保証されません。
- Custom DATEはraw int32であり、日付への意味変換はありません。Simpleに日付印新規作成はなく、既存日付印の列挙・対応属性操作と区別します。
- StandardのPointsは3種類とも読取り専用です。Pointsのraw表現は先頭絶対＋後続相対で、自然getterは第1点基準で復号した絶対mm値です。
- 操作失敗時のrollback、wrapper間のキャッシュ同期、削除の全wrapper横断通知、persistent ID、スレッド間の文書操作保証はありません。
- Python 3.10の本体例外＋close失敗時に`add_note`の不具合があります。従来の通常経路の契約テスト合格から、この異常経路まで対応済みと判断できません。
- 従来の10.1.1記録ではDateFormatの`yy.mm.dd`が永続化し、`yy.MM.dd`が拒否されました。本実装は小文字形式の許容リストを維持します。TopFieldについて実機がRegistryより長い入力を受理した観察があっても、wrapperの制限を緩める根拠にはしていません。
- 9.1.7は最低版定数とABIの基点であり、現在の製品とのopen互換性を無条件に保証しません。今回もSDK 9.1.7のopenで`XDW_E_NOT_INSTALLED`を確認しました。SDK 10.0はsmoke、installed 10.1.1は117件の実機試験の対象です。

### 10.2 テストとの対応

| 確認対象 | 主な同梱テスト | 検証の意味 |
| --- | --- | --- |
| 89組のRegistry・種類別属性 | `test_registry.py` | 種類、属性名、Unicode対象、readonly、仕様データの契約 |
| Standard／Custom／User分離 | `test_attribute_contracts.py` | fake rawで格納型・NULLと非NULL・旧API除去を検査 |
| codepage・自然単位・Points | `test_encoding_and_units.py`、`test_new_core_and_simple.py` | バッファと引数、丸め、rawと自然値、条件検査 |
| resize条件と範囲 | `test_capabilities.py` | 種類別制約、境界、Text条件、日付印高さ正規化 |
| 追加後の公式情報取得 | `test_annotation_refresh.py` | handle照合と不一致時エラー。推測した情報へのfallbackをしない |
| Simple作成・列挙・寿命 | `test_new_core_and_simple.py` | facade委譲、enum拒否、snapshot、削除／close、有効性、暗黙saveなし |
| DLL選択・probe診断 | `test_runtime_resolver.py` | 選択順位、明示指定失敗、timeout／不正JSON、companion patch差 |
| サンプルと配布 | `test_simple_examples.py`、`test_release_candidate.py` | コピー保護、help実行、資料存在、API snapshot、配布比較 |
| 証跡検証 | `test_integration_support.py` | hash、証跡manifest、改変検出の補助処理 |
| 実文書属性・永続化 | `tests/integration/test_roundtrip.py` | 設定直後GETとsave／close／reopen後GET、89組の実文書値、既知観察項目 |
| 実文書Simple workflow | `tests/integration/test_simple_workflows.py` | 8種類作成、移動・resize、再帰順、削除後再列挙、明示保存 |

DLL不要のfake rawテストはPython側の契約確認であり、実DLLとの統合成功ではありません。`--help`の起動テストはexampleの実文書ワークフロー実行と別です。Standard 89組のうち3組はPointsの読取りであり、「89組すべてを書き込んだ」という解釈は誤りです。

今回の再検証では、Python 3.10.11／3.11.9／3.12.10／3.13.15のwheel・source計8環境で各103件の契約試験が成功し、各wheel環境のSimple保存smokeも成功しました。Windows x64／Python 3.11.9／System32 XDWAPI 10.1.1では実機117件が失敗・skipなしで成功し、Standard 89組を確認しました。SDK 10.0は代表smoke、SDK 9.1.7は静的検査成功・文書open失敗という範囲です。元READMEの102件表記は、添付JUnit・今回の実測103件と不一致でした。別枠の追加例外試験ではPython 3.10に1件の失敗があり、通常試験の成功に含めて隠しません。Viewer 9/9は旧版からの継承記録で、今回の目視確認は未実施です。詳細・一時フォルダー権限による初回失敗と再試行条件は検証報告書に記載します。

### 10.3 保守時の確認基準

公開契約変更の検知はSimple snapshotに加え、本書のCore署名・dataclass・単位・例外・寿命・属性表を確認します。Core修正には通常の契約試験、実文書の設定直後と再open後、86書込み可能組と3読取り組の区別、fixture原本の不変、wheel／source実装一致、証跡hash検証が必要です。

DLL版とPython版を増やす場合は、ABI検査、read-only open、Simple保存smoke、全integration、Viewerを段階別に記録します。missing interpreter、skip、手順書にコマンドがあるだけの状態を成功に数えません。入力fixtureはコピーだけを更新し、記録には原本の前後SHA-256と実際に使用したDLL bundle・Python版を含めます。

## 11. 本書の根拠

署名と振る舞いは配布sourceの`api.py`、`document.py`、`simple/facade.py`、`attributes.py`、`capabilities.py`、`encoding.py`、`runtime`、`_raw`、および対応テストを読み取り確認したものです。公開名・Simple署名・enumは`PUBLIC_API_1.0.json`も照合対象にしています。配布物間の同一性・今回の実行試験と不一致の確定結果は検証報告書にまとめます。

元資料に含まれる指示や宣言は検証対象の説明として扱い、利用者からの依頼や本書の保証に自動的に昇格させていません。本書の89属性表・141 bind表は配布wrapperのデータから作成し、SDKの仕様書本文やDLLを転載・同梱していません。公式SDKに対する追加の適合性を、本書の作成だけで認定するものではありません。
