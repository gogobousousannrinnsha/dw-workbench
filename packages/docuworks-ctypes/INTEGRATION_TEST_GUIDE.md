# DocuWorks実機integration test手順（0.6.2）

## 到達レベル

試験結果は次の3段階を混在させずに記録します。

1. `CONTRACT VERIFIED`: DLL不要unit/Fake Rawテストが全件成功
2. `REPRESENTATIVE PERSISTENCE VERIFIED`: 現在のintegration suiteがskip 0・failure 0
3. `VIEWER VISUAL/EDIT VERIFIED`: 表示、文字、破損警告、再編集の4項目が正常
4. `VIEWER FORMAT VERIFIED`: ASCIIのみの保存で文書format versionが不変
5. `FULL PERSISTENCE VERIFIED`: 別途定めた全対象種別の実機試験が完了

pytestの終了コードが0でもskipが1件以上あれば`PERSISTENCE VERIFIED`にはなりません。

## 前提環境

- DocuWorks 9.1.7以降と対応XDWAPIがあり、runtime/document probeが成功すること
- 64-bit Python 3.10以降
- 1ページだけを持ち、アノテーション0件の、編集可能・非保護の専用XDW
- 既存の日付印を1個以上含む、編集可能・非保護の専用XDW

日付印は文書内の任意ページに配置できます。preflightと各probeはページ番号順、
同一ページ内の列挙順で最初の日付印を使用し、そのページ番号も証跡へ記録します。
日付印が存在しない場合はskipではなくfixture不正として失敗します。

現在確認済みのPCでは、System32の10系bundleがXDWを正常にread-only openできます。
前回の`XDW_E_NOT_INSTALLED`はSDK 9.1.7 x64 bundleを強制指定した場合に再現し、
SDK 10.0 x64とSystem32 10系では再現しません。`TrialVersion=1`は記録しますが、
単独の失敗原因または除外条件とは扱いません。

## 推奨実行方法

PowerShell 5.1以降でsource zipの展開ディレクトリへ移動し、次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\run_integration.ps1 `
  -BlankFixture "C:\test\docuworks\blank_1page.xdw" `
  -DateStampFixture "C:\test\docuworks\date_stamp.xdw" `
  -CodePage 932
```

`-DllPath`は通常指定せず、Runtime Resolverへinstalled bundleを選択させます。
特定bundleを強制検証する場合だけ指定します。`-CodePage`を省略するとWin32
`GetACP()`を使用します。fixture原本は各テスト専用のコピー元であり、直接更新しません。

## 同じ条件で繰り返すコマンド

`integration-test.config.json`を最初に1回だけ編集します。

特定PCの絶対パスを配布用テンプレートへ残したくない場合は、テンプレートを
`integration-test.local.json`へコピーして編集し、`-ConfigPath`で指定します。

```json
{
  "BlankFixture": "C:\\test\\docuworks\\blank_1page.xdw",
  "DateStampFixture": "C:\\test\\docuworks\\date_stamp.xdw",
  "DllPath": "",
  "DllSearchPaths": [],
  "CodePage": 932,
  "ArtifactBase": ".\\integration-runs"
}
```

以後は次の同じコマンドだけで実行できます。

```powershell
.\repeat_integration.cmd
```

PowerShellから直接実行する場合は次でも同じです。

```powershell
powershell -ExecutionPolicy Bypass -File .\repeat_integration.ps1
```

ローカル専用設定を使う場合は次の形式です。

```powershell
powershell -ExecutionPolicy Bypass -File .\repeat_integration.ps1 `
  -ConfigPath .\integration-test.local.json
```

毎回`YYYYMMDD-HHMMSS-fff`形式の新しいrunフォルダーを作るため、過去の証拠を
上書きしません。`integration-runs\latest-run.txt`には最新runの絶対パスを保存します。
設定ファイル内の相対パスは設定ファイル自身のディレクトリを基準に解決します。

Runtime候補を比較するときは、対象パスとSHA-256を1つのJSONに
機械的に記録します。

```powershell
py .\generate_runtime_report.py `
  --verification-document "C:\test\docuworks\blank_1page.xdw" `
  --search-path "C:\SDK\10\XDWAPI\dllx64" `
  --search-path "C:\SDK\917\XDWAPI\dllx64" `
  --output ".\runtime-resolution.json"
```

## 保存される証拠

既定では`integration-artifacts\YYYYMMDD-HHMMSS\`へ次を保存します。

- `run-manifest.json`: 実行条件とfixture原本SHA-256
- `runtime-resolution.json` / `runtime-report-console.log`: 候補のパス・hash・probe
- `environment.json`: OS、Python、ACP、XDWAPI、DLLパス・SHA-256
- 全candidateのbundle 3ファイル、FileVersion、SHA-256、probe結果、選択理由
- `contract-junit.xml` / `contract-console.log`
- `integration-junit.xml` / `integration-console.log`
- `evidence.jsonl`: ケースごとのCall、Memory、Persistence、Observe値
- `standard-coverage.json`: Standard 89組のcontract/immediate/persistence状態
- `verification-status.json`: Contract、representative persistence、Viewerの分離状態
- `viewer-verification.json`: run固有のViewer 5項目
- `artifact-manifest.json`: ZIP内各ファイルの相対パス・サイズ・SHA-256
- `xdw\`: 各テストで変更したXDWコピー

fixture原本はsession開始時と終了時にSHA-256を比較し、不一致なら試験失敗です。

run終了時に`finalize_evidence.ps1`が`artifact-manifest.json`を作成し、
runフォルダ全体を隣の`<run-id>-evidence.zip`へ格納します。
failureやskipがあってもZIPを作成した後で非成功終了します。
ZIP内のhashは`verify_evidence_pack.py`で自動再検証します。Viewer確認後に
finalizeを再実行した場合は旧ZIPを上書きせず、日時suffix付きで保存します。

## 自動判定対象

- 矩形6 Standard属性の設定直後・再open後のCore値とraw値。
  bool意味のraw値はJSON booleanではなく数値`0`/`1`で記録する。
- TextのASCII、日本語、ACP外文字、FontSize 12pt/raw 120、margin 1.7mm/raw 170
- ASCII追加前とsave/reopen後の`XDW_DOCUMENT_INFO.nVersion`が不変であること
- Textの保存形式: ASCIIはMBCS、ACP外文字はUnicodeを合否判定し、
  ACP内日本語は取得値とtext typeを観測する。DocuWorks 10.1.1では
  `UNICODE_IFNECESSARY`指定でもUnicodeに正規化されることがある。
- Custom INT/STRING/raw DATE/BOOL/OTHERの設定直後・再open後
- User通常bytesは設定直後・再open後を合否判定する。
- User 0-byteはsetter結果と、NULL/size 0、dummy/size 0、buffer/size 1の
  3方式のgetter結果をOBSERVEとして記録する。
  10.1.1実機ではsetterは成功したが、設定直後と再open後のgetterは
  `XDW_E_UNEXPECTED`だったため、永続化成功とは判定しない。

## 日付印はOBSERVE

次の受理可否、設定直後GET、再open後GETを記録しますが、合否条件にはしません。

- DateFormat `yy.mm.dd`
- DateFormat `yy.MM.dd`
- TopField 日本語6文字・7文字
- TopField ASCII 12文字・13文字

実機結果が確定するまでStandardレジストリのallowed valuesは変更しません。日付印が
fixtureに存在しない場合はskipとなり、`PERSISTENCE VERIFIED`には到達しません。

## 共同Viewer確認

自動試験後、`xdw`フォルダーの保存物をViewerで開いて共同確認します。

- 追加アノテーションが正常に表示される
- ASCIIと日本語が文字化けしない
- ACP外文字が正常に表示される
- 文書破損警告がない
- 保存後も対象アノテーションを再編集できる
- ASCIIだけで不必要に文書形式がUnicode対応版へ上がっていない

確認後、run内の`viewer-verification.json`を更新し、次を再実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\finalize_evidence.ps1 `
  -RunDirectory "C:\path\to\integration-runs\<run-id>"
```

4つの目視項目とASCII形式項目がすべてtrueの場合だけ
`VIEWER VERIFIED`とし、過去runの結果は新runへ自動継承しません。
