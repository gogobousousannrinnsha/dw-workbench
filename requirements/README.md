# 依存関係

`results.txt` はリポジトリルートで実行するローカルソース導入リストです。順序と版は各pyprojectで固定されるCore 1.0.1 / Integrations 0.8.1に対応します。

`ocr-python313-win-cu129.lock` は過去に動作したWindows x64 / CPython 3.13 / CUDA 12.9環境の固定依存一覧です。上流の配信継続や別GPUでの動作は保証せず、今回ネットワークからの全再取得は行っていません。Paddle wheelのみURLとSHA-256を固定し、他の配布物は版固定のみです。完全なhash lockやオフライン配布セットではありません。

`models-ppocrv6-medium.json` は検証時の公式モデルURL、tarと展開ファイルのSHA-256です。取得後に `scripts/verify_models.py` で照合します。モデル本体は同梱しません。

`dev.txt` は今回の再検証用ツールの固定版です。runtimeには不要です。
