> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# Windows / Python 3.13 セットアップ

リポジトリルートからPowerShellで実行します。Pythonはx64 3.13、DocuWorksはライセンスを持つ製品環境を別途用意します。過去の実測はPython 3.13.15です。Coreの互換性試験範囲3.10～3.13と、OCRの実測基準3.13を区別してください。

## 1. 保存結果の利用だけ

```powershell
py -3.13 --version
py -3.13 -c "import struct; assert struct.calcsize('P') == 8"
py -3.13 -m venv .venv-results
.\.venv-results\Scripts\python.exe -m pip install -r requirements/results.txt
.\.venv-results\Scripts\python.exe -m pip check
.\.venv-results\Scripts\python.exe -m docuworks_integrations --help
```

venvの有効化は不要です。読込み・移行・JSONLにはPaddle/Pillow/OpenCVもDLLも不要です。マーカー実保存時のみCoreとDLLを使用します。

## 2. GPU OCR環境

CUDA対応NVIDIA GPUと対応ドライバーを用意し、`nvidia-smi` で認識を確認します。必要VRAM量や他GPUの互換性は未測定です。

```powershell
nvidia-smi
py -3.13 -m venv .venv-ocr
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements/ocr-python313-win-cu129.lock
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements/results.txt
.\.venv-ocr\Scripts\python.exe -m pip check
.\.venv-ocr\Scripts\python.exe -c "import paddle; assert paddle.is_compiled_with_cuda(); assert paddle.device.cuda.device_count() > 0; paddle.utils.run_check()"
```

固定構成はPaddlePaddle GPU 3.2.2 / CUDA 12.9系 / cuDNN 9.9.0.52 / PaddleOCR 3.7.0 / PaddleX 3.7.2 / Pillow 12.3.0です。CPUへの自動切替は実装されていません。cuDNNだけを別版に変更せず、lockの組合せで確認します。OCR lockは全配布物hash固定ではないため[依存一覧の範囲](../../requirements/README.md)も参照してください。

公式情報の入口: [PaddlePaddle](https://www.paddlepaddle.org.cn/)、[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)、[PaddleX](https://github.com/PaddlePaddle/PaddleX)。本書の版はローカル成果物に記録された検証基準であり、最新推奨版の調査結果ではありません。

## 3. PP-OCRv6 mediumモデル

新規の空の `models/` を使います。ダウンローダーはtarをハッシュ計算にも使うため、展開先だけを残してtarを削除すると再実行に失敗します。

```powershell
.\.venv-ocr\Scripts\python.exe packages/docuworks-integrations/download_models.py --model-root models
.\.venv-ocr\Scripts\python.exe scripts/verify_models.py --model-root models
```

`models/PP-OCRv6_medium_det` と `models/PP-OCRv6_medium_rec` が必要です。照合失敗時はOCRを開始せず、期待ハッシュを安易に更新しないでください。標準ダウンローダーは取得したハッシュを記録するだけなので、別の照合コマンドが必要です。

## 4. DocuWorks DLL

製品に付属するx64 `xdwapi.dll` の絶対パスを利用者が確認して指定します。関連DLLも同じ互換bundleに揃えます。SDKを取得しただけでは文書openが成功するとは限りません。過去のSDK 9.1.7 DLLでは `XDW_E_NOT_INSTALLED` が発生しています。DLL/SDKは本リポジトリにコピーしません。

```powershell
$dll = (Resolve-Path 'C:\Windows\System32\xdwapi.dll').Path # 実際の製品DLLの場所に合わせる
.\.venv-ocr\Scripts\python.exe -c "from docuworks_ctypes import XdwApi; import sys; XdwApi.load(dll_path=sys.argv[1]); print('DLL loaded')" $dll
```

DLLロード成功は文書操作成功ではありません。[操作手順](../WORKFLOWS.md)で自分の試験用文書を使い、生成コピーの再オープンとViewer確認まで行います。

## 一時フォルダ権限エラーが出る環境

通常手順が `PermissionError` / `WinError 5` で失敗した場合のみ、書込み可能な作業TEMPを指定します。Python 3.13自体の問題と断定しません。

```powershell
New-Item -ItemType Directory -Force work/pip-temp | Out-Null
$env:TEMP = (Resolve-Path work/pip-temp).Path
$env:TMP = $env:TEMP
# 失敗したvenvと別名を使う。以下は動作済みPython 3.11のpipがある場合。
py -3.13 -m venv --without-pip .venv-results-retry
py -3.11 -m pip --python .venv-results-retry/Scripts/python.exe install --no-cache-dir -r requirements/results.txt
```

GPU環境で同じ回避を使う場合は対象venvを分け、同じ `--python` 指定でOCR lock→本体の順に導入します。環境変数はこのPowerShellを閉じると解除されます。
