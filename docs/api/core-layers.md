# Which API should I use?

`docuworks-ctypes` には **Simple / Core / Raw** の3つの層があります。

この文書は、利用者が「自分はどのAPIから始めるべきか」を判断するための入口です。
難易度の目安として Simple = 初心者、Core = 中級者、Raw = 上級者と表現しますが、
**Pythonの経験年数ではなく、やりたい処理に必要な抽象度で選ぶ**ことを推奨します。

通常のアプリケーション開発は **Simple から開始してください**。
CoreやRawを使う必要が出たときだけ、1段ずつ下の層へ進みます。

---

## まず結論

| やりたいこと | 推奨API |
|---|---|
| 文書を開く・保存する | **Simple** |
| ページを選ぶ | **Simple** |
| Text / Rectangle / Sticky / Ellipse / Line / Polygon / Marker / Linkを作る | **Simple** |
| 既存アノテーションを列挙する | **Simple** |
| アノテーションを移動・resize・削除する | **Simple** |
| Standard属性を細かく読み書きする | **Core** |
| Custom Attribute / User Attributeを扱う | **Core** |
| XDW raw値とPython自然単位を明示的に使い分ける | **Core** |
| Simpleにない高度なアノテーション操作を行う | **Core** |
| XDWAPI関数・構造体・ポインタ・ABIを直接扱う | **Raw** |
| 新しいXDWAPI bindingを追加する | **Raw** |
| DLLやSDKの互換性・ABIを調査する | **Raw** |

迷った場合は **Simple** を選んでください。

---

## 3層の関係

```text
あなたのアプリケーション
        |
        v
+-----------------------+
| Simple                |
| 普通のDocuWorks操作   |
+-----------------------+
        |
        v
+-----------------------+
| Core                  |
| DocuWorksの意味を     |
| Pythonとして安全に扱う|
+-----------------------+
        |
        v
+-----------------------+
| Raw                   |
| ctypes / XDWAPI ABI   |
+-----------------------+
        |
        v
     XDWAPI
        |
        v
    DocuWorks
```

上の層ほど使いやすく、下の層ほどXDWAPIに近くなります。

重要なのは、**上級者だからRawを使う、という設計ではない**ことです。
XDWファイルへ通常のアノテーションを追加するだけなら、経験豊富な開発者でもSimpleが適切です。

---

# Level 1: Simple

## 対象

- Pythonの基本的な文法が分かる
- DocuWorks文書をPythonから操作したい
- XDWAPI仕様書や`ctypes`を意識せず使いたい

Simple APIは、通常の利用者が最初に使うための高水準APIです。

公開入口は次です。

```python
from docuworks_ctypes.simple import open_xdw
```

## Simpleでできること

- XDW文書を開く
- 1-basedのページ番号でページを取得する
- アノテーションを作成する
- アノテーションを列挙する
- 移動する
- resizeする
- 削除する
- 明示的に保存する

作成できるSimple 1.0のアノテーションは次の8種類です。

- Text
- Rectangle
- Sticky
- Ellipse
- Line
- Polygon
- Marker
- Link

日付印の新規作成はSimple 1.0の対象外です。

## 最小例

```python
import shutil
from pathlib import Path

from docuworks_ctypes.simple import open_xdw

source = Path("sample.xdw")
output = Path("sample-edited.xdw")

if output.exists():
    raise FileExistsError(output)

shutil.copy2(source, output)

with open_xdw(output, writable=True) as document:
    page = document.page(1)

    page.text("確認", x=20, y=30, font_size=12)
    page.rectangle(x=20, y=50, width=80, height=40)

    document.save()
```

Simpleでは、座標は基本的に **mm**、文字サイズは **pt** として扱います。
XDWAPI内部の`1/100 mm`や`1/10 pt`を利用者が直接計算する必要はありません。

## Simple利用者が最初は知らなくてよいもの

次の内容は、Simpleだけを使う間は理解しなくても構いません。

- XDWAPIの関数番号やC API
- `ctypes.Structure`
- ポインタ
- HRESULT
- XDW raw単位
- DLL export
- Standard Attributeの格納形式

SimpleはCoreを呼び出す薄いFacadeとして設計されており、これらの低水準処理を隠します。

## Coreへ進む目安

次のどれかが必要になったらCoreを検討します。

- Simpleに公開されていないStandard属性を操作したい
- Custom Attributeを使いたい
- User Attributeを使いたい
- raw値を確認したい
- 任意の属性値を詳細に検証したい

Simpleの`SimpleAnnotation`からは、必要な場合だけ`annotation.core`を通してCoreへ降りることができます。

---

# Level 2: Core

## 対象

- Simpleの基本操作を理解している
- DocuWorksのアノテーション属性を細かく扱いたい
- XDWAPIの意味は理解したいが、`ctypes`やABI管理はライブラリへ任せたい

Coreは、XDWAPIの概念をPythonで安全に扱うための層です。

Simpleが「何をしたいか」を中心にしたAPIなのに対して、Coreは
**「DocuWorksではそのデータがどの属性として表現されているか」**を扱います。

## Coreで扱う主な内容

- Standard Attribute
- Custom Attribute
- User Attribute
- 属性ごとの型・制約
- 読取り可能 / 書込み可能の区別
- Annotation Typeごとの適用条件
- `PointMM`などの幾何型
- Python自然単位とXDW raw値の変換

`STANDARD_ATTRIBUTE_REGISTRY`は、検証済みのStandard属性契約を管理します。

## 自然単位とraw値

Coreでは、通常はPython向けの自然な値を使用します。

```python
annotation.set_standard_attribute("%FontSize", 12.0)
value = annotation.get_standard_attribute("%FontSize")
# 12.0 pt
```

XDW格納値そのものを確認する必要がある場合は、raw APIを明示的に使用します。

```python
annotation.set_standard_attribute_raw("%FontSize", 120)
value = annotation.get_standard_attribute_raw("%FontSize")
# 120 = 1/10 pt
```

主な変換例は次のとおりです。

| 意味 | Core自然単位 | XDW raw |
|---|---|---|
| FontSize / TextSpacing | pt | 1/10 pt |
| LineSpace | line | 1/100 line |
| Text margins | mm | 1/100 mm |
| TextOrientation | degree | 1 degree |
| Points | `PointMM`の絶対座標 | `RawPoint`、1/100 mm |

Coreを使う場合でも、通常は自然単位APIを優先してください。
raw APIは、仕様確認・互換性調査・低水準値を意図的に扱う場合のためのものです。

## 3種類のAttributeを混同しない

Coreでは次の3系統を別物として扱います。

### Standard Attribute

DocuWorksが定義している標準属性です。
例: `%FontSize`, `%FillColor`, `%BorderWidth` など。

### Custom Attribute

型付きのユーザー定義属性です。
INT / STRING / DATE / BOOL / OTHERを扱います。

### User Attribute

任意の名前とbytesを扱う属性です。
Standard / Customとは別の仕組みです。

この3種類を分離して扱うことは、`docuworks-ctypes 1.x`の安定契約の一部です。

## Rawへ進む目安

次の場合だけRawを検討します。

- CoreにbindingされていないXDWAPI関数が必要
- C headerとABIを直接確認する必要がある
- 新しいRaw bindingを実装する
- DLLロードや構造体layoutを調査する
- Coreそのものを拡張・修正する

通常のアプリケーションコードでRawへ直接降りる必要はほとんどありません。

---

# Level 3: Raw

## 対象

- `ctypes`を理解している
- Cの構造体・ポインタ・整数幅を理解している
- Windows DLL / ABIの基礎知識がある
- XDWAPI SDK仕様を読みながら実装・検証できる

RawはXDWAPIのABIをPythonから直接扱うための最下層です。
実装は主に`docuworks_ctypes/_raw/`以下にあります。

## Rawで扱うもの

- XDWAPI関数signature
- `ctypes`の型
- C構造体
- pointer / buffer
- A/W関数
- HRESULT
- DLL export
- ABI layout
- XDW raw整数値
- XDWAPI SDKとの対応

Rawでは、SimpleやCoreが提供している安全性・型変換・単位変換の一部を自分で意識する必要があります。

## Rawを直接使う主な理由

### 1. 新しいXDWAPI関数を追加する

CoreやSimpleで未対応のSDK機能を追加するときは、まずRaw bindingが必要です。

### 2. ABIを検証する

関数signature、構造体size、field offset、DLL exportなどをSDK headerと照合する場合です。

### 3. Coreの不具合を調査する

Coreの結果がXDWAPIのどの値から来ているかを切り分ける場合です。

## Rawを通常利用に使わない理由

Rawを直接使うと、次の責任が利用者側へ近づきます。

- 正しい引数型
- pointer lifetime
- buffer size
- encoding
- raw単位
- HRESULT処理
- SDK version差

そのため、**「Rawの方が高機能だから使う」のではなく、Rawでなければ解決できない問題にだけ使用する**のが基本方針です。

---

# 同じライブラリを3つの視点で見る

例えば「文字アノテーションの文字サイズを扱う」場合を比較します。

## Simpleの視点

```python
page.text("確認", x=20, y=30, font_size=12)
```

考えること:

- どこに置くか
- 何を書くか
- 何ptにするか

## Coreの視点

```python
annotation.set_standard_attribute("%FontSize", 12.0)
```

考えること:

- `%FontSize`というStandard Attribute
- Python自然単位はpt
- この属性が対象annotationで書込み可能か

## Rawの視点

考えること:

- 対応するXDWAPI関数
- attribute名と値の格納形式
- `12 pt -> raw 120`
- ctypes引数型
- HRESULT
- encoding / buffer契約

同じ操作でも、層を下げるほどDocuWorks内部仕様へ近づきます。

---

# APIを選ぶためのフローチャート

```text
DocuWorksをPythonから操作したい
        |
        v
Simpleに目的の操作がある？
   | yes              | no
   v                  v
Simpleを使う     属性や高度な操作？
                      |
                 yes  |  no
                      v
                    Core
                      |
              Coreにも機能がない？
                 | no       | yes
                 v          v
               Core        Raw
```

原則は **Simple -> Core -> Raw** の順です。

---

# よくある選択例

## OCR結果からMarkerを追加したい

**Simple** を推奨します。

OCRや座標変換は`docuworks-integrations`側で行い、DocuWorksへの書込みはSimpleへ渡します。
外部ツールがRawを直接呼ぶ設計にはしません。

```text
PP-OCRv6
   |
   v
Canonical OCR Result
   |
   v
docuworks-integrations
   |
   v
Simple
   |
   v
Core -> Raw -> XDWAPI
```

## 特定のStandard属性を変更したい

まずSimpleに専用引数・操作があるか確認します。
なければ **Core** を使用します。

## XDWAPI SDKで見つけた新しい関数を使いたい

これは **Raw** の担当です。
Raw bindingを追加し、その上に必要ならCore APIを作り、一般利用が見込まれる場合だけSimpleへ上げます。

---

# 全レベル共通の重要ルール

API層に関係なく、次のルールは共通です。

## 1. ページ番号は1-based

```python
document.page(1)
```

が最初のページです。

## 2. 保存は明示的

```python
document.save()
```

を呼びます。
context managerを抜けても暗黙saveは行いません。

## 3. 原本を直接変更しない運用を推奨

検証・自動処理では、原本をコピーして出力ファイル側を変更する方式を推奨します。

## 4. 幾何の高水準単位はmm

SimpleおよびCoreの自然単位では、ページ上の位置・サイズをmmで扱います。

## 5. raw整数を必要以上に外へ漏らさない

アプリケーション、OCR、OpenCV、CAD、AIなどのintegration層ではSimple/CoreのPython型を利用し、XDW raw値への変換は`docuworks-ctypes`内部へ閉じ込めます。

---

# 学習順序

初めて使う場合は次の順序を推奨します。

```text
1. WHICH_API.md        <- 今ここ
        |
        v
2. Simple Guide
        |
        v
3. 実際のXDWを安全に操作
        |
        +---- 必要になったら ----> Core Guide
                                   |
                                   +---- 必要になったら ----> Raw Guide
```

Simpleをすべて覚えてからCoreへ進む必要はありません。
必要な機能がSimpleの範囲を超えた時点で、その部分だけCoreを学ぶことができます。

---

# 既存の参照資料

現在の実装・契約を詳しく確認する場合は、次を参照してください。

- [`docuworks-ctypes README`](../../packages/docuworks-ctypes/README.md)
- [`Simple API Reference 1.0`](../../packages/docuworks-ctypes/SIMPLE_API_REFERENCE_1.0.md)
- [`API Stability Policy 1.0`](../../packages/docuworks-ctypes/API_STABILITY_1.0.md)
- [`Core API 1.0.0`](../CORE_API_1.0.0.md)
- [`Core Verification Complete`](../../packages/docuworks-ctypes/CORE_VERIFICATION_COMPLETE.md)
- [`Known Runtime Behaviors`](../../packages/docuworks-ctypes/KNOWN_RUNTIME_BEHAVIORS.md)
- [`Compatibility 1.0`](../../packages/docuworks-ctypes/COMPATIBILITY_1.0.md)
- [`docuworks_ctypes/_raw`](../../packages/docuworks-ctypes/docuworks_ctypes/_raw)

---

# まとめ

- **Simple**: DocuWorksをPythonから普通に使うための入口
- **Core**: DocuWorksの属性・型・単位・制約を理解して詳細に制御する層
- **Raw**: XDWAPI ABIを直接実装・検証するための最下層

通常はSimpleから始め、必要な箇所だけCoreへ降り、Rawはライブラリ実装・ABI調査に限定するのが基本です。

```text
通常利用          -> Simple
高度な属性操作    -> Core
XDWAPI/ABI開発    -> Raw
```

この境界を守ることで、アプリケーションコードをXDWAPIの低水準仕様から分離し、将来の保守と検証を容易にできます。
