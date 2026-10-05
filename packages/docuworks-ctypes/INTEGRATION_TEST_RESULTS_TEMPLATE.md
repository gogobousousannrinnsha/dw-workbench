# docuworks-ctypes 0.6.2 実機試験結果

- run ID:
- 実施日時:
- 実施者:
- artifactフォルダー:
- OS:
- Windows ACP:
- Python version / bitness:
- DocuWorks / XDWAPI version:
- selected bundle / source:
- xdwapi FileVersion / ProductVersion / SHA-256:
- xdwapia FileVersion / ProductVersion / SHA-256:
- xdwapib FileVersion / ProductVersion / SHA-256:
- XDW報告version:
- candidate probe結果ファイル:
- 空白fixture path / SHA-256:
- 日付印fixture path / SHA-256:
- fixture原本の試験前後一致: 未確認

## 自動判定

| レベル | 判定 | 根拠ファイル |
|---|---|---|
| CONTRACT VERIFIED | 未確認 | `contract-junit.xml` |
| REPRESENTATIVE PERSISTENCE VERIFIED | 未確認 | `integration-junit.xml`, `evidence.jsonl` |
| VIEWER VISUAL/EDIT VERIFIED | 未確認 | `viewer-verification.json` |
| VIEWER FORMAT VERIFIED | 未確認 | ASCIIのnVersion証跡 |
| FULL PERSISTENCE VERIFIED | 未確認 | `standard-coverage.json`の89/89とRuntime scope |

- contract passed / failed / skipped:
- integration passed / failed / skipped:
- XDWエラーコード:

## Call・Memory・Persistence

| 対象 | Call | 設定直後Core/raw | 再open後Core/raw | 備考 |
|---|---|---|---|---|
| 矩形6属性 |  |  |  | bool rawは数値0/1 |
| Text ASCII / text type |  |  |  |  |
| Text ASCII / document nVersion |  |  |  | 保存前後不変を確認 |
| Text 日本語 / text type (OBSERVE) |  |  |  | 保存形式は合否条件外 |
| Text ACP外 / text type |  |  |  |  |
| FontSize 12pt / raw 120 |  |  |  |  |
| margin 1.7mm / raw 170 |  |  |  |  |
| Custom INT |  |  |  |  |
| Custom STRING |  |  |  |  |
| Custom raw DATE |  |  |  |  |
| Custom BOOL |  |  |  |  |
| Custom OTHER |  |  |  |  |
| User bytes |  |  |  |  |
| User 0-byte (OBSERVE) |  |  |  | setterと3方式getterを記録し、成功扱いにしない |
| Straight Line / Points |  |  |  | natural PointMM / raw RawPoint |
| Sticky / Ellipse |  |  |  |  |
| Polygon / Marker / Points |  |  |  |  |
| Link 4種類 |  |  |  | 条件付きtarget |

## Standard coverage

- registry count:
- immediate complete:
- persistence complete:
- runtime scope:
- missing / failed rows:

### User 0-byte Raw OBSERVE

| 時点 | NULL / size 0 | dummy / size 0 | buffer / size 1 |
|---|---|---|---|
| 設定直後 |  |  |  |
| save/reopen後 |  |  |  |

## 日付印OBSERVE

| 入力 | SET結果コード | 受理 | 設定直後GET | 再open後GET |
|---|---:|---|---|---|
| `yy.mm.dd` |  |  |  |  |
| `yy.MM.dd` |  |  |  |  |
| 日本語6文字 |  |  |  |  |
| 日本語7文字 |  |  |  |  |
| ASCII 12文字 |  |  |  |  |
| ASCII 13文字 |  |  |  |  |

- 判明した実機契約:
- registry変更要否:

## 共同Viewer確認

| 項目 | 結果 | 対象XDW・備考 |
|---|---|---|
| アノテーション表示 | 未確認 |  |
| ASCII・日本語文字化けなし | 未確認 |  |
| ACP外文字表示 | 未確認 |  |
| 文書破損警告なし | 未確認 |  |
| 保存後の再編集 | 未確認 |  |
| 不要な文書形式上昇なし | 未確認 |  |

### 9アノテーション種別

| 種別 | 代表XDW | 表示・編集結果 |
|---|---|---|
| Text |  | 未確認 |
| Link |  | 未確認 |
| Sticky |  | 未確認 |
| Straight Line |  | 未確認 |
| Rectangle |  | 未確認 |
| Ellipse |  | 未確認 |
| Date Stamp |  | 未確認 |
| Marker |  | 未確認 |
| Polygon |  | 未確認 |

## エラー・追加観測

- 再現手順:
- 期待値:
- 実測値:
- 次の対応:
