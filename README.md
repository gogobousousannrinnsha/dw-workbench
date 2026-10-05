# DW-Workbench 0.4.0

複数文書への一括テンプレート適用を保持し、未完了項目の移動、原文確認・訂正、Excel出力、台帳照合と別XDWへの注釈を追加した公開Pre-releaseです。保存形式は2のままです。

[操作の流れ](docs/WORKFLOW_UI_JA.md)、[一括適用](docs/BULK_TEMPLATE_JA.md)、[台帳と注釈](docs/LEDGER_MARKUP_JA.md)、[別PCで使う](docs/user/portable-transfer.md)、[配布案内](DISTRIBUTION.md)を参照してください。

Core 1.0.1 / Integrations 0.14.0 / Python 3.13以降を使います。PortableはDW-OCR v0.8.0候補と同じruntime・モデルを共有できます。DocuWorks本体・XDWAPI・ドライバーは利用者が移動先に導入します。自作部分はMIT、第三者条件を保持します。実文書と利用者DB・設定を含めません。9.1・別の物理PC・実帳票・Viewer手操作は未確認です。

## Portableをダウンロードして使う

[DW-OCR v0.8.0 / Workbench 0.4.0 共通Portable](https://github.com/gogobousousannrinnsha/dw-ocr/releases/tag/v0.8.0) を使います。輸送ZIP8個 `ocr_part_001_transport.zip` ～ `ocr_part_008_transport.zip` と `ocr_join_tools.zip` をダウンロードし、同じ新しいフォルダーへ展開してください。`join_parts.bat` で検査・結合し、できた `dw_ocr_with_code.zip` を別の新しいフォルダーへ展開して `Workbench開始.bat` を実行します。

Windows x64、DocuWorks本体/XDWAPI、GPU OCR用の対応NVIDIA GPU・ドライバーが必要です。Python・OCRモデルは同梱しています。すべてのZIP・部品・展開後ファイルを残す場合は空き容量16GB以上を目安にしてください。使用中のPortableは保存して終了し、新版は別フォルダーへ展開します。DocuWorks10.1.1の本PCで合成データによるSDK/GPU/Tk/保存・再読込・フォルダー移動を確認済みです。9.1、Viewer目視、別の物理PC、全DPI、CPU専用OCRは未確認です。
