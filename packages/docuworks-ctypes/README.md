# docuworks-ctypes 1.0.1

1.0.1の安全性修正と互換性は[変更記録](CHANGELOG_1.0.1.md)を参照してください。以下の1.0.0の検証記述は履歴です。

Windows版DocuWorks XDWAPIのctypesラッパー、検証済みCore API、およびその上に
構築したSimple APIです。1.0.0は検証済み0.9.0の製品挙動と公開契約を変更せず、
Python 3.10～3.13、fresh install、runtime互換性、配布内容、利用者向け文書を
固定する最初の安定版です。

Core検証の範囲、証跡、変更時の回帰条件は`CORE_VERIFICATION_COMPLETE.md`、
Simple APIの規範仕様は`SIMPLE_API_SPEC_0.7.0.md`、API一覧は
`SIMPLE_API_REFERENCE_1.0.md`、安全な操作手順は
`SIMPLE_WORKFLOW_GUIDE_0.8.0.md`、対応範囲は`COMPATIBILITY_1.0.md`を
参照してください。

## Installation

対応環境はWindows x64およびCPython 3.10～3.13です。DocuWorksと対応XDWAPIは
利用者側で用意し、wheelには含まれません。

```powershell
py -m pip install .\docuworks_ctypes-1.0.1-py3-none-any.whl
py -c "import docuworks_ctypes; print(docuworks_ctypes.__version__)"
```

出力が`1.0.1`であることを確認してください。

## Runtime Resolver

`XdwApi.load()`は、64-bitの`xdwapi.dll`、`xdwapia.dll`、`xdwapib.dll`を
同一ディレクトリのbundleとして扱います。通常はinstalled runtimeを自動選択します。

```python
api = XdwApi.load()
```

任意SDK候補を追加する場合はディレクトリを明示します。Downloads等を勝手に再帰検索
することはありません。

```python
api = XdwApi.load(search_paths=[r"C:\SDK\dwsdk10\XDWAPI\dllx64"])
```

実機試験ではread-only openまで別processで確認できます。

```python
api = XdwApi.load(verification_document=r"C:\test\blank_1page.xdw")
```

`dll_path=`は厳格な強制指定です。そのbundleが不整合またはprobe失敗ならinstalled
runtimeへfallbackしません。候補だけ確認する場合は`XdwApi.inspect_runtimes()`を使います。

`RuntimeInfo`はDLL FileVersion、ProductVersion、SHA-256、XDW報告version、companions、
installed DocuWorks version、全candidate probe結果を別々に保持します。

## 0.3.0 Breaking changes

- `Annotation.set/get_standard_attribute()`はXDW raw値ではなくPython自然単位を扱います。
- raw値が必要な場合は`set/get_standard_attribute_raw()`を使用します。
- `XdwApi.load()`と`from_raw()`に`multibyte_codepage=`を追加しました。
- 0.2.0で分離したStandard / Custom / User APIはそのまま維持します。

```python
annotation.set_standard_attribute("%FontSize", 12.0)       # 12 pt
annotation.get_standard_attribute("%FontSize")             # 12.0
annotation.set_standard_attribute_raw("%FontSize", 120)    # XDW raw
annotation.get_standard_attribute_raw("%FontSize")         # 120
```

## 0.4.0 Breaking change

Standard raw APIのint32属性は常にPython `int`で扱います。bool意味の属性も
raw getterは`0`/`1`を返し、raw setterは`True`/`False`を拒否して`0`/`1`のみ
受理します。自然単位APIは従来どおりboolです。

```python
annotation.get_standard_attribute("%FillTransparent")      # False
annotation.get_standard_attribute_raw("%FillTransparent")  # 0
annotation.set_standard_attribute("%FillTransparent", True)
annotation.set_standard_attribute_raw("%FillTransparent", 1)
```

自然単位は次のとおりです。

| Standard属性 | Python | XDW raw |
|---|---:|---:|
| FontSize / TextSpacing | pt | 1/10 pt |
| LineSpace | line | 1/100 line |
| Text margins | mm | 1/100 mm |
| TextOrientation | degree | 1 degree |
| Points | 絶対座標の`PointMM` | 先頭絶対座標＋相対移動量の`RawPoint`、1/100 mm |

変換時はDecimalのROUND_HALF_UPを使用します。

0.6.2ではPointsのraw契約をbreaking changeしました。自然getterは
`tuple[PointMM, ...]`の絶対座標、raw getterはXDW格納表現そのままの
`tuple[RawPoint, ...]`を返します。先頭点は親左上からの絶対座標、2点目以降は
第1点からの相対移動量です。Pointsは引き続き読取専用です。

## Core annotation creation

`Page`はText、Rectangle、Sticky、Straight Line、Ellipse、Polygon、Marker、Linkを
作成できます。Polygon／Markerへの入力は絶対座標の`Sequence[PointMM]`で、Coreが
公式の先頭絶対＋後続相対形式へ変換します。Linkは`LinkType`とtargetの組合せを
DLL呼出し前に検証します。

## Simple API

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
    page = document.page()
    page.text("確認", x=20, y=30, font_size=12)
    page.rectangle(x=20, y=50, width=80, height=40)
    document.save()
```

Simple APIはCoreだけを呼ぶ薄いFacadeです。単位はmm／ptで、追加メソッドはCore
`Annotation`を内包する`SimpleAnnotation`を返します。context終了時の暗黙saveは
行いません。Text、Rectangle、Sticky、Ellipse、Line、Polygon、Marker、Linkの
8種類を作成できます。日付印の新規作成はSimple 1.0の対象外です。

```python
annotations = page.annotations()                 # top-level snapshot tuple
all_annotations = page.annotations(recursive=True)

annotation = annotations[0]
print(annotation.type, annotation.position, annotation.size)
annotation.move_to(x=25, y=30)
annotation.resize(width=80, height=40)
annotation.delete()
document.save()
```

Simpleの色・線種・矢印・リンク種別は`Color`、`BorderType`、
`ArrowheadType`、`ArrowheadStyle`、`LinkType`を使用します。raw整数は受理しません。
任意COLORREFやStandard／Custom／User属性の汎用操作は`annotation.core`からCoreを
利用してください。

`examples/`には8種類の作成、read-only列挙、移動・resize、削除、再帰列挙、
Core escape hatchの6例があります。変更系exampleは入力原本と別の未存在出力
パスを要求し、コピーだけを更新します。

```powershell
py .\examples\01_add_annotations.py `
  "C:\path\blank.xdw" "C:\path\simple-created.xdw"
py .\examples\02_list_annotations.py "C:\path\simple-created.xdw"
```

## Multibyte encoding

既定codepageはWin32 `GetACP()`から取得します。現在のWindows ANSI codepageと異なる
文書を扱う必要がある場合だけ上書きしてください。

```python
api = XdwApi.load(multibyte_codepage=932)
```

- W getterのcodepageにはACPまたは指定値を渡します。UTF-16の1200は渡しません。
- Unicode対応Standard属性は`XDW_TEXT_UNICODE_IFNECESSARY`で保存します。
- ACPで表現可能ならmultibyte、表現不能ならUnicode保存になります。
- Standard非Unicode文字列とUser属性名は同じencoding policyを使用します。
- Custom STRINGはXDWAPI仕様どおりUTF-16固定です。

## Attribute systems

### Standard

`STANDARD_ATTRIBUTE_REGISTRY`はXDWAPI 3.1の9種類・89組を収録し、
`(annotation_type, attribute_name)`をキーとします。仕様書に明記された制約だけを
strict validationします。`Points`は読取専用です。

### Custom

INT / STRING / raw DATE / BOOL / OTHERに対応します。OTHERは値を持たず、削除とは
別操作です。DATEの`datetime.date`変換は実機検証後まで追加しません。

### User

任意bytesを格納します。`b""`はctypes呼出し上は非NULLポインタの
0-byte値として送られ、NULLポインタを送る削除と区別されます。
ただし、DocuWorks 10.1.1実機ではsetter成功後、NULL/size 0、
dummy/size 0、buffer/size 1の3方式のgetterが設定直後と再open後の
いずれも`XDW_E_UNEXPECTED`を返しました。0-byte値の取得・永続化は
成功扱いにしません。
XDWAPIに列挙関数がないため、User属性の列挙APIはありません。

## Annotation capabilities

`ANNOTATION_CAPABILITIES`でXDW_SetAnnotationSizeの種類別契約を管理します。

- 矩形・楕円: 3～2400 mm
- テキスト・ビットマップ・リンク: 5～2400 mm
- 付箋: 5～500 mm
- 日付印: 幅10～500 mm、高さは幅と同値
- テキスト: WordWrap=1かつTextOrientation=0の場合だけresize可能
- リンク: AutoResize=0の場合だけresize可能

追加APIはXDW_AddAnnotationが返したhandleを公式列挙情報から探し、
`XDW_ANNOTATION_INFO`を再取得します。handleが見つからない場合は合成情報へ
フォールバックせず`AnnotationRefreshError`を送出します。

## Tests

DLL不要テスト:

```powershell
py -m pytest -q -m "not integration"
```

実機テストは空白用と日付印用の2つの専用fixtureを使い、日時別artifact
ディレクトリへコピーしてから変更します。

```powershell
powershell -ExecutionPolicy Bypass -File .\run_integration.ps1 `
  -BlankFixture "C:\path\to\blank_1page.xdw" `
  -DateStampFixture "C:\path\to\date_stamp.xdw" `
  -DllPath "C:\path\to\xdwapi.dll"
```

Call、設定直後GET、save/close/reopen後GET、自然単位とraw値、text typeを記録し、
fixture原本のSHA-256不変も検証します。fixture未指定またはskip発生時は実機成功扱いに
しません。詳細は`INTEGRATION_TEST_GUIDE.md`を参照してください。

実機runはRegistry駆動の`standard-coverage.json`も生成します。89組すべてが
設定直後・再open後まで揃った場合だけ、XDWAPI 10.1.1限定の
`FULL PERSISTENCE VERIFIED`を設定します。0.6.2の最終runではViewer代表9種類も
確認済みで、`FULL VIEWER VERIFIED`まで成立しています。

同じ条件で繰り返す場合は`integration-test.config.json`へfixture等を一度設定し、
以後は`.\repeat_integration.cmd`だけを実行します。runごとに別の証拠フォルダーが
作成されます。

## API layer selection

- Simple: 通常の作成、列挙、移動、resize、削除
- Core: Standard／Custom／User属性、raw単位、高度なアノテーション操作
- Raw: XDWAPI ABIを直接扱う必要がある場合だけ使用

通常利用は`docuworks_ctypes.simple`から開始してください。

## Verification status

Core verification baselineはWindows x64、Python 3.11、System32 XDWAPI 10.1.1です。

- DLL不要contract: 102 passed
- 実機integration: 117 passed、0 failed、0 skipped
- Standard Registry/Persistence: 89/89
- Viewer代表確認: 9/9
- `FULL PERSISTENCE VERIFIED`
- `FULL VIEWER VERIFIED`

この判定は他のXDWAPI/Python環境へ自動的には一般化しません。User 0-byte GETは
既知runtime limitationとしてFull Persistence判定から分離しています。

1.0.0ではCore／Raw／Simple facadeを0.9.0から変更していません。Python
3.10～3.13のfresh wheel／source install、各102 contract、wheelのSimple
persistence smoke、およびXDWAPI 10.0代表smokeを検証済みです。詳細なpatch versionと証跡は
`COMPATIBILITY_1.0.md`およびrelease evidenceを参照してください。


> 集約版の運用入口: [README](../../README.md)。試験件数・既知不具合・Viewer確認範囲は[検証記録](../../docs/VERIFICATION.md)を正としてください。
