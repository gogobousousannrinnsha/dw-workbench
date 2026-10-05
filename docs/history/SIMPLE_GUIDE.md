> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# Simple API Beginner Guide

`docuworks-ctypes` の **Simple API** を初めて使う人向けの入門ガイドです。

対象は、Pythonの基本的な文法は分かるものの、XDWAPI、`ctypes`、Cの構造体、
DocuWorks内部のraw単位などはまだ扱いたくない利用者です。

通常のDocuWorks自動化では、まずSimple APIから始めてください。
API層の選び方は [WHICH_API.md](../WHICH_API.md) を参照してください。

---

## 1. このガイドでできるようになること

このガイドを順番に進めると、次の操作ができるようになります。

- `docuworks-ctypes` をインストールする
- XDW文書をread-onlyで開く
- ページを選ぶ
- 既存アノテーションを列挙する
- 原本を壊さないようにコピーへ書き込む
- Text / Rectangle / Sticky / Ellipse / Line / Polygon / Marker / Linkを作る
- アノテーションの位置・サイズを確認する
- 移動する
- resizeする
- 削除する
- 明示的に保存する
- 必要なときだけCoreへ進む

Simple APIでは、通常の座標は **mm**、文字サイズは **pt** で扱います。
XDWAPI内部の`1/100 mm`や`1/10 pt`を自分で計算する必要はありません。

---

# 2. 前提環境

`docuworks-ctypes 1.0.0` の対応範囲は次です。

- Windows x64
- CPython 3.10 / 3.11 / 3.12 / 3.13 の64-bit版
- 利用者側に互換性のあるDocuWorksとXDWAPI runtimeが導入済み

このリポジトリにはDocuWorks本体、XDWAPI DLL、SDK、仕様書は含まれません。

初めて試す場合は、現在の開発基準に合わせて **Python 3.13 x64** を推奨します。

Pythonを確認します。

```powershell
py -3.13 --version
```

例:

```text
Python 3.13.x
```

64-bitか確認したい場合:

```powershell
py -3.13 -c "import struct; print(struct.calcsize('P') * 8)"
```

`64` と表示されれば64-bit Pythonです。

詳しい対応範囲は
[COMPATIBILITY_1.0.md](../../packages/docuworks-ctypes/COMPATIBILITY_1.0.md) を参照してください。

---

# 3. インストール

## 3.1 リポジトリをcloneする

```powershell
git clone https://github.com/gogobousousannrinnsha/dw-ocr
cd dw-ocr
```

すでにclone済みなら、そのフォルダへ移動してください。

```powershell
cd C:\path\to\docuworks-ocr
```

---

## 3.2 Python 3.13の仮想環境を作る

```powershell
py -3.13 -m venv .venv-simple
```

PowerShellの実行ポリシーに問題がなければ、次で有効化できます。

```powershell
.\.venv-simple\Scripts\Activate.ps1
```

有効化しなくても構いません。
その場合は、このガイドの`python`を次のように読み替えられます。

```powershell
.\.venv-simple\Scripts\python.exe
```

例えば:

```powershell
.\.venv-simple\Scripts\python.exe -m pip --version
```

この方法なら、PowerShellのactivate scriptを実行しなくても仮想環境を利用できます。

---

## 3.3 pipを更新する

仮想環境を有効化した場合:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

有効化していない場合:

```powershell
.\.venv-simple\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
```

---

## 3.4 docuworks-ctypesをインストールする

リポジトリ直下から、同梱sourceをインストールできます。

```powershell
python -m pip install .\packages\docuworks-ctypes
```

仮想環境を有効化していない場合:

```powershell
.\.venv-simple\Scripts\python.exe -m pip install .\packages\docuworks-ctypes
```

配布wheelを別途持っている場合は、wheelから導入しても構いません。

```powershell
python -m pip install .\docuworks_ctypes-1.0.0-py3-none-any.whl
```

---

## 3.5 インストール確認

```powershell
python -c "import docuworks_ctypes; print(docuworks_ctypes.__version__)"
```

期待値:

```text
1.0.0
```

Simple APIの入口も確認します。

```powershell
python -c "from docuworks_ctypes.simple import open_xdw; print(open_xdw)"
```

ここまでエラーがなければPythonパッケージの導入は完了です。

---

# 4. 最初に覚える4つのルール

Simple APIを使う前に、次の4点だけ覚えてください。

## 4.1 まずread-onlyで開く

`open_xdw()`は既定でread-onlyです。

```python
from docuworks_ctypes.simple import open_xdw

with open_xdw("sample.xdw") as document:
    page = document.page(1)
```

書込みが必要なときだけ`writable=True`を指定します。

---

## 4.2 ページ番号は1から始まる

最初のページは`1`です。

```python
page1 = document.page(1)
page2 = document.page(2)
```

Pythonのlistのような0始まりではありません。

---

## 4.3 書込みは原本ではなくコピーへ行う

初心者のうちは、原本を直接編集しないことを強く推奨します。

```python
import shutil
from pathlib import Path

source = Path("sample.xdw")
output = Path("sample-edited.xdw")

if output.exists():
    raise FileExistsError(output)

shutil.copy2(source, output)
```

その後、`output`を開いて編集します。

---

## 4.4 `save()`は明示的に呼ぶ

context managerを抜けても自動保存されません。

```python
with open_xdw("sample-edited.xdw", writable=True) as document:
    document.page(1).text("確認", x=20, y=30)
    document.save()
```

`document.save()`を書かなければ、変更を保存したことにはなりません。

---

# 5. 最初の実用サンプル

まずはTextとRectangleだけ追加してみます。

`first_edit.py`:

```python
import shutil
from pathlib import Path

from docuworks_ctypes import Color
from docuworks_ctypes.simple import open_xdw

source = Path("sample.xdw")
output = Path("sample-edited.xdw")

if not source.exists():
    raise FileNotFoundError(source)

if output.exists():
    raise FileExistsError(output)

shutil.copy2(source, output)

with open_xdw(output, writable=True) as document:
    page = document.page(1)

    page.text(
        "確認",
        x=20,
        y=20,
        font_size=12,
        fore_color=Color.BLUE,
    )

    page.rectangle(
        x=20,
        y=40,
        width=60,
        height=25,
        border_color=Color.RED,
        fill_color=Color.YELLOW,
    )

    document.save()

print(f"Saved: {output}")
```

実行:

```powershell
python .\first_edit.py
```

成功したら、`sample-edited.xdw`をDocuWorks Viewerで開いて確認してください。

---

# 6. 座標とサイズ

Simple APIでは、ページ上の座標・幅・高さを基本的にmmで指定します。

```python
page.rectangle(
    x=20,
    y=30,
    width=80,
    height=40,
)
```

これは概念的に、ページ座標上の

- `x = 20 mm`
- `y = 30 mm`
- 幅 `80 mm`
- 高さ `40 mm`

を意味します。

文字サイズはptです。

```python
page.text("確認", x=20, y=30, font_size=12)
```

XDW raw値への変換はCoreが担当します。

---

# 7. 既存アノテーションを一覧表示する

書込みをしないのでread-onlyで十分です。

```python
from docuworks_ctypes.simple import open_xdw

with open_xdw("sample.xdw") as document:
    page = document.page(1)
    annotations = page.annotations()

    print(f"annotations: {len(annotations)}")

    for index, annotation in enumerate(annotations, start=1):
        print(f"[{index}]")
        print("  type:", annotation.type)
        print("  position:", annotation.position)
        print("  size:", annotation.size)
```

`page.annotations()`は、その時点のsnapshot tupleを返します。

子アノテーションも含めて列挙したい場合:

```python
annotations = page.annotations(recursive=True)
```

通常はまず`recursive=False`の既定値から始めてください。

---

# 8. 8種類のアノテーションを作る

Simple 1.0では次の8種類を作成できます。

- Text
- Rectangle
- Sticky
- Ellipse
- Line
- Polygon
- Marker
- Link

日付印の新規作成はSimple 1.0の対象外です。

以下は8種類を1ページに追加するサンプルです。

```python
import shutil
from pathlib import Path

from docuworks_ctypes import (
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
    LinkType,
    PointMM,
)
from docuworks_ctypes.simple import open_xdw

source = Path("sample.xdw")
output = Path("all-simple-annotations.xdw")

if output.exists():
    raise FileExistsError(output)

shutil.copy2(source, output)

with open_xdw(output, writable=True) as document:
    page = document.page(1)

    # 1. Text
    page.text(
        "Simple API",
        x=15,
        y=15,
        font_size=12,
        fore_color=Color.BLUE,
    )

    # 2. Rectangle
    page.rectangle(
        x=15,
        y=35,
        width=30,
        height=18,
        border_color=Color.RED,
        fill_color=Color.YELLOW,
    )

    # 3. Sticky
    page.sticky(
        x=55,
        y=35,
        width=30,
        height=25,
        fill_color=Color.STICKY_YELLOW,
        text="付箋",
    )

    # 4. Ellipse
    page.ellipse(
        x=95,
        y=35,
        width=30,
        height=18,
        border_color=Color.RED,
        fill_color=Color.YELLOW,
    )

    # 5. Line
    page.line(
        x1=15,
        y1=75,
        x2=50,
        y2=90,
        border_color=Color.BLUE,
        border_type=BorderType.DASH,
        arrowhead_type=ArrowheadType.ENDING,
        arrowhead_style=ArrowheadStyle.POLYGON,
    )

    # 6. Polygon
    page.polygon(
        (
            PointMM(60, 75),
            PointMM(90, 75),
            PointMM(80, 95),
        ),
        border_color=Color.BLUE,
        fill_color=Color.YELLOW,
    )

    # 7. Marker
    page.marker(
        (
            PointMM(105, 75),
            PointMM(125, 82),
            PointMM(140, 90),
        ),
        border_color=Color.GREEN,
    )

    # 8. Link
    page.link(
        "This document",
        x=15,
        y=110,
        link_type=LinkType.THIS_DOCUMENT,
        fore_color=Color.BLUE,
    )

    document.save()
```

この例はリポジトリ内の
[`examples/01_add_annotations.py`](../../packages/docuworks-ctypes/examples/01_add_annotations.py)
と同じSimple公開APIを使用しています。

---

# 9. 作成したアノテーションを変数に受け取る

作成メソッドは`SimpleAnnotation`を返します。

```python
annotation = page.rectangle(
    x=20,
    y=30,
    width=50,
    height=20,
)

print(annotation.type)
print(annotation.position)
print(annotation.size)
```

この変数を使って、そのまま移動・resize・削除できます。

---

# 10. アノテーションを移動する

```python
annotation.move_to(x=40, y=50)
```

完全な例:

```python
import shutil
from pathlib import Path

from docuworks_ctypes.simple import open_xdw

source = Path("sample.xdw")
output = Path("moved.xdw")
shutil.copy2(source, output)

with open_xdw(output, writable=True) as document:
    page = document.page(1)

    rectangle = page.rectangle(
        x=20,
        y=20,
        width=50,
        height=20,
    )

    rectangle.move_to(x=60, y=80)

    document.save()
```

---

# 11. アノテーションをresizeする

```python
annotation.resize(width=80, height=40)
```

例:

```python
with open_xdw("sample-edited.xdw", writable=True) as document:
    page = document.page(1)
    annotations = page.annotations()

    target = annotations[0]
    target.resize(width=80, height=40)

    document.save()
```

すべてのアノテーションが自由にresizeできるわけではありません。
種類や属性状態によってDocuWorks側の制約があります。
初心者向けの練習では、まずRectangleやEllipseのようなサイズを持つ種類で試してください。

---

# 12. アノテーションを削除する

```python
annotation.delete()
```

例:

```python
with open_xdw("sample-edited.xdw", writable=True) as document:
    page = document.page(1)
    annotations = page.annotations()

    if annotations:
        annotations[0].delete()
        document.save()
```

削除後、その`SimpleAnnotation`は有効なアノテーションとして再利用しないでください。
文書をcloseした後も、以前取得したwrapperは利用できません。

---

# 13. 安全な「既存文書を編集する」テンプレート

実際のプログラムでは、この形を出発点にすると安全です。

```python
import shutil
from pathlib import Path

from docuworks_ctypes.simple import open_xdw


def edit_copy(source_path: str, output_path: str) -> None:
    source = Path(source_path)
    output = Path(output_path)

    if not source.exists():
        raise FileNotFoundError(source)

    if output.exists():
        raise FileExistsError(output)

    shutil.copy2(source, output)

    with open_xdw(output, writable=True) as document:
        page = document.page(1)

        page.text("確認済み", x=20, y=20, font_size=12)
        page.rectangle(x=15, y=15, width=50, height=20)

        document.save()


edit_copy("sample.xdw", "sample-edited.xdw")
```

ポイントは次です。

1. 原本の存在を確認する
2. 出力がすでにあれば停止する
3. 原本をコピーする
4. コピーだけを`writable=True`で開く
5. 最後に明示的`save()`する

---

# 14. 保存後にread-onlyで再確認する

書込み後に一度閉じ、read-onlyで開き直すと確認しやすくなります。

```python
from docuworks_ctypes.simple import open_xdw

path = "sample-edited.xdw"

with open_xdw(path) as document:
    page = document.page(1)

    for index, annotation in enumerate(page.annotations(), start=1):
        print(index, annotation.type, annotation.position, annotation.size)
```

重要な処理では、Python側の確認に加えてDocuWorks Viewerでも出力を確認してください。

---

# 15. 色や線種はEnumを使う

Simpleでは、色や線種などにraw整数を直接渡さず、公開Enumを使用します。

```python
from docuworks_ctypes import Color

page.rectangle(
    x=20,
    y=30,
    width=50,
    height=20,
    border_color=Color.RED,
    fill_color=Color.YELLOW,
)
```

Lineでは例えば:

```python
from docuworks_ctypes import (
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
)

page.line(
    x1=20,
    y1=30,
    x2=80,
    y2=30,
    border_color=Color.BLUE,
    border_type=BorderType.DASH,
    arrowhead_type=ArrowheadType.ENDING,
    arrowhead_style=ArrowheadStyle.POLYGON,
)
```

Simple APIは、Enumが必要な場所でraw整数を受け付けない設計です。

---

# 16. PolygonとMarkerではPointMMを使う

PolygonとMarkerは点列を渡します。

```python
from docuworks_ctypes import PointMM

points = (
    PointMM(20, 20),
    PointMM(60, 20),
    PointMM(50, 50),
)

page.polygon(points)
```

Markerも同様です。

```python
page.marker(
    (
        PointMM(20, 70),
        PointMM(50, 70),
    )
)
```

Simple/Core側では`PointMM`はページ上の絶対座標として扱います。
XDWAPIの内部格納形式を利用者が意識する必要はありません。

---

# 17. Linkを作る

Linkでは`LinkType`を必ず指定します。

文書内リンクの最小例:

```python
from docuworks_ctypes import LinkType

page.link(
    "This document",
    x=20,
    y=100,
    link_type=LinkType.THIS_DOCUMENT,
)
```

`LinkType`と`target`の組合せには種類ごとの条件があります。
まずは既存のexampleやSimple API Referenceにある組合せを使ってください。

---

# 18. read-onlyとwritableを使い分ける

## 読むだけ

```python
with open_xdw("sample.xdw") as document:
    annotations = document.page(1).annotations()
```

## 変更する

```python
with open_xdw("sample-edited.xdw", writable=True) as document:
    document.page(1).text("追加", x=20, y=30)
    document.save()
```

「読むだけなのに`writable=True`」という使い方は避けると安全です。

---

# 19. XDWAPI runtimeが自動検出できない場合

通常は次だけで構いません。

```python
with open_xdw("sample.xdw") as document:
    ...
```

installed runtimeを自動選択できない環境では、`dll_path`を明示できます。

```python
from docuworks_ctypes.simple import open_xdw

with open_xdw(
    "sample.xdw",
    dll_path=r"C:\Windows\System32\xdwapi.dll",
) as document:
    print(document.page(1).annotations())
```

`dll_path`は強制指定です。
指定したXDWAPI bundleが不整合なら、別runtimeへ黙ってfallbackしません。

DocuWorks環境そのものが正しく導入されているか分からない場合は、
まずDocuWorks Viewerで対象XDWを正常に開けることも確認してください。

---

# 20. 日本語文字列について

通常は特別なencoding指定なしで始めてください。

```python
page.text("日本語の確認", x=20, y=30)
```

`open_xdw()`には必要な場合だけ`codepage=`を指定できます。

```python
with open_xdw("sample.xdw", codepage=932) as document:
    ...
```

これは現在のWindows ANSI codepageと異なる文書を扱う必要がある場合などの高度な設定です。
初心者は既定値のままで構いません。

---

# 21. よくある失敗

## `ModuleNotFoundError: No module named 'docuworks_ctypes'`

使用しているPythonと、インストールしたPythonが違う可能性があります。

確認:

```powershell
python -c "import sys; print(sys.executable)"
python -m pip show docuworks-ctypes
```

仮想環境を有効化していない場合:

```powershell
.\.venv-simple\Scripts\python.exe -m pip show docuworks-ctypes
```

---

## XDWを開けない

次を順番に確認してください。

1. ファイルパスが正しい
2. DocuWorks ViewerでそのXDWを開ける
3. Pythonが64-bit
4. DocuWorks/XDWAPIが利用可能
5. 必要なら`dll_path`を明示する

---

## 変更が保存されていない

`document.save()`を呼んだか確認してください。

```python
with open_xdw(path, writable=True) as document:
    document.page(1).text("確認", x=20, y=30)
    document.save()  # 必須
```

context managerを抜けるだけでは自動保存されません。

---

## `writable=False`のまま変更しようとした

書込み時は明示します。

```python
open_xdw(path, writable=True)
```

ただし、原本ではなくコピーへ書き込むことを推奨します。

---

## resizeでエラーになる

種類や現在の属性状態によってresizeできないアノテーションがあります。
最初はRectangleまたはEllipseで練習してください。

---

# 22. リポジトリにある実行例

`packages/docuworks-ctypes/examples/`には、Simple APIの実行例があります。

- [`01_add_annotations.py`](../../packages/docuworks-ctypes/examples/01_add_annotations.py) — 8種類を作成
- [`02_list_annotations.py`](../../packages/docuworks-ctypes/examples/02_list_annotations.py) — read-only列挙
- [`03_move_resize.py`](../../packages/docuworks-ctypes/examples/03_move_resize.py) — 移動とresize
- [`04_delete_annotations.py`](../../packages/docuworks-ctypes/examples/04_delete_annotations.py) — 削除
- [`05_recursive_annotations.py`](../../packages/docuworks-ctypes/examples/05_recursive_annotations.py) — 再帰列挙
- [`06_use_core_escape_hatch.py`](../../packages/docuworks-ctypes/examples/06_use_core_escape_hatch.py) — SimpleからCoreへ進む例

変更系exampleは原本と別の出力パスを使う設計です。

---

# 23. まず試すおすすめ順序

初めて使う場合は、次の順で試してください。

```text
Step 1
インストール確認

    ↓

Step 2
read-onlyで1ページ目を開く

    ↓

Step 3
annotations()で一覧表示

    ↓

Step 4
原本をコピー

    ↓

Step 5
コピーへTextを1つ追加

    ↓

Step 6
save → close → read-only reopen

    ↓

Step 7
Viewerで確認

    ↓

Step 8
Rectangle / Markerなどへ拡張
```

最初から8種類すべてを使う必要はありません。
まず **Textを1つ追加して保存できること** を最初の成功条件にすると切り分けが簡単です。

---

# 24. SimpleからCoreへ進むタイミング

Simpleで通常操作は完結します。
次のような要求が出たときだけCoreを検討してください。

- Simpleの引数にないStandard Attributeを読み書きしたい
- Custom Attributeを扱いたい
- User Attributeを扱いたい
- XDW raw値を確認したい
- Simpleで公開されていない高度な属性を操作したい

`SimpleAnnotation`には`core` escape hatchがあります。

```python
annotation = page.text("確認", x=20, y=30)
core_annotation = annotation.core
```

ただし、初心者の間は`annotation.core`を使わずSimpleだけで作ることを推奨します。

API層の違いは [WHICH_API.md](../WHICH_API.md) を参照してください。

---

# 25. Simple利用者が覚えなくてよいもの

Simpleだけを利用する間は、次を理解する必要はありません。

- `ctypes.Structure`
- XDWAPIのC関数signature
- pointer / buffer
- HRESULT
- DLL export
- `1/100 mm`などのraw単位
- Standard Attributeの格納型
- ABI layout

これらはCoreまたはRaw側の責任です。

---

# 26. 最小チートシート

```python
from docuworks_ctypes.simple import open_xdw

# read-only
with open_xdw("sample.xdw") as document:
    page = document.page(1)
    annotations = page.annotations()

# writable
with open_xdw("copy.xdw", writable=True) as document:
    page = document.page(1)
    annotation = page.text("確認", x=20, y=30, font_size=12)
    annotation.move_to(x=30, y=40)
    document.save()
```

主要オブジェクト:

```text
open_xdw()
    ↓
SimpleDocument
    ↓ page(1)
SimplePage
    ↓ text()/rectangle()/...
SimpleAnnotation
    ↓ move_to()/resize()/delete()
```

主要プロパティ:

```python
annotation.type
annotation.position
annotation.size
```

---

# 27. 次に読む文書

Simpleをもう少し詳しく調べたい場合:

- [WHICH_API.md](../WHICH_API.md)
- [Simple API Reference 1.0](../../packages/docuworks-ctypes/SIMPLE_API_REFERENCE_1.0.md)
- [Simple API Spec](../../packages/docuworks-ctypes/SIMPLE_API_SPEC_0.7.0.md)
- [Simple Workflow Guide](../../packages/docuworks-ctypes/SIMPLE_WORKFLOW_GUIDE_0.8.0.md)
- [Compatibility Matrix](../../packages/docuworks-ctypes/COMPATIBILITY_1.0.md)

Coreへ進む場合:

- [CORE_API_1.0.0.md](../CORE_API_1.0.0.md)

Rawは、Coreでも解決できないXDWAPI/ABI開発が必要になるまで読む必要はありません。

---

# まとめ

初心者がSimple APIを使うときの基本形は次です。

```text
1. Windows x64 + 64-bit Pythonを用意
2. docuworks-ctypesをインストール
3. read-onlyで開けることを確認
4. 原本をコピー
5. コピーをwritable=Trueで開く
6. page(1)を取得
7. Simple APIで操作
8. document.save()
9. 閉じる
10. read-only reopen + Viewerで確認
```

迷ったときは、RawやCoreへ降りる前にSimpleで解決できないか確認してください。
通常のDocuWorksアプリケーション開発はSimpleだけで始められます。
