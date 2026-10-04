# 第三者コンポーネント

このリポジトリに含むのは独自のPython実装、ビルド設定、テスト、文書と合成サンプルです。外部のPythonランタイム・ライブラリ・GPUランタイム・OCRモデルのバイナリは含みません。ソースから依存をインストールする場合は、それぞれの配布物のライセンスとNOTICEを保持してください。

| 使用する資産 | 用途・条件の参照 |
|---|---|
| Python / Tk | 実行環境・画面。[Pythonのライセンス](https://docs.python.org/3/license.html)と各配布物の条件 |
| Pillow | 画像処理。[Pillow LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| XlsxWriter 3.2.9 | Excel生成。BSD-2-Clause。[XlsxWriter LICENSE](https://github.com/jmcnamara/XlsxWriter/blob/main/LICENSE.txt) |
| PaddleOCR / PaddleX / PaddlePaddle | 任意のGPU OCR。各配布物のLICENSE・NOTICE |
| PP-OCRv6 medium detection / recognition | ローカルOCRモデル。公式モデルカード・配布物のApache-2.0条件 |
| NVIDIA CUDA / cuDNN | PortableのGPU実行環境。該当配布物のNVIDIA条件 |
| DocuWorks / XDWAPI | 利用者が用意する外部製品。製品・SDKの条件 |

[Release](https://github.com/gogobousousannrinnsha/dw-workbench/releases)のPortableには第三者資産を含みます。Portable内の `licenses/`、元のLICENSE・NOTICE、配布対象一覧、LGPL部分の対応ソースの取得案内を併せて確認してください。本リポジトリのMITはNVIDIA等の第三者バイナリの独立再配布や転用を許可するものではありません。第三者ライセンスによる権利を制限しません。

説明書の再生成には追加ライブラリが必要です。[再生成資料](docs/manual-build/README.md)のrequirementsと各ライブラリの条件を参照してください。図版・帳票サンプルは合成データです。Windowsフォントは同梱しません。
