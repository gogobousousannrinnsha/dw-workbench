# 第三者資産と対応ソース

v0.7.0の全文Excel出力にはXlsxWriter 3.2.9（BSD-2-Clause）を追加しています。原文ライセンスはPortableの`reference/XlsxWriter-LICENSE.txt`とruntimeのdist-info内に保持します。固定版wheelのSHA-256は`reference/dependency-wheels.json`、実際のパッケージ一覧は`reference/installed-packages.json`に記録します。下記の公開済みパッケージ一覧とは版を区別してください。

Python、Paddle、PaddleX、PaddleOCR、モデル、GPUランタイムその他の第三者資産は各ライセンスで提供します。元のLICENSE・NOTICEは削除していません。配布ZIPの`runtime/LICENSE.txt`、`runtime/Lib/site-packages/*dist-info/`等を参照してください。

PP-OCRv6 mediumの[検出モデル](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det)と[認識モデル](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec)は公式カードでApache-2.0と表示されています。モデルの出所・ファイルhashを保持し、Apache本文とNOTICEを追加しました。

NVIDIA cuDNN 9.9の[公式条件](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.9.0/reference/eula.html)はランタイムDLLの再配布条件を定めています。配布済みwheelの古いLicense.txtも保存し、現行版の確認先を本書に追記しています。公開版ではcuDNNの開発用includeを除きました。CUDA関連資産については同梱条件と[NVIDIA公式条件](https://docs.nvidia.com/cuda/eula/index.html)に従ってください。

LGPL関連のcrc32c 2.9、python-bidi 0.6.11、GEOS 3.13.1およびShapely 2.1.2の公式ソースを`third-party-sources-v0.1.0.zip`に添付します。取得元・版・SHA-256は同ZIPのSOURCES.jsonに記録しています。Pythonソースで同梱するライブラリ・vendoredソースは元のライセンスを保持します。

画像OCRに不要なOpenCVのFFmpeg動画プラグインは公開版に含めません。動画ファイル入出力はこの配布版の対象外です。画像処理のcv2本体は保持します。

第三者の正当な著作権表示、上流のビルドパス、公開テスト用証明書・鍵は個人の秘密情報とは区別し保持します。ライセンスを一括してMITへ書き換えていません。

正確な同梱パッケージ一覧は[パッケージ一覧](docs/INSTALLED_PACKAGES.md)を参照してください。
