# 履歴・検証の案内

[今回の構造整理の検証](../maintainer/VERIFICATION.md)は、以下の公開済み基準とは別に記録しています。

## 公開済み基準

Core 1.0.0 / Integrations 0.7.0 / Portable v0.3.0 Pre-releaseは公開済みです。開発main 26ebf04、公開main 621d0dc。開発の検証点f41ff3eとmainのtree、公開候補384787cと公開mainのtreeは一致した状態で統合されました。

[公開Releaseの確定記録](https://github.com/gogobousousannrinnsha/dw-ocr/releases/tag/v0.3.0)には、23ファイルの取得後ハッシュ照合とPortable実行結果を記載しています。添付物の「承認待ち」「公開未実施」は承認前に凍結した記録で、現在の公開状態ではありません。凍結物は更新しません。

開発CIは試験・ビルド・監査成功、artifact uploadだけ容量制限で失敗し、利用者の例外承認で検証済みローカル成果物を採用しました。公開PRのCIは全体成功です。これらを一括して「CI成功」としません。

## Viewerとコード検証

1領域ではViewer編集・移動・未変更・コピー・削除・空白の6ケース、複数領域では同一文字2領域の片方だけを編集する正常1ケースが対象です。Viewerの操作・再表示は利用者報告、保存済みファイルの照合・訂正JSONL・不変性はコード検証です。SDK検証とViewer検証は別です。複数領域のViewer異常操作、白紙型は未確認です。

- [訂正基盤の記録](CORRECTIONS_VERIFICATION.md)
- [1領域の記録](REVIEW_XDW_VERIFICATION.md)
- [複数領域の記録](REVIEW_XDW_REGIONS_VERIFICATION.md)
- [0.7.0公開準備時の試験範囲](RELEASE_0.7.0.md)
- [sdist再現性の過去記録](SDIST_REPRODUCIBILITY_0.7.0.md)
- [既知制約の由来](LIMITATIONS.md)
- [旧ロードマップ](ROADMAP.md)

このフォルダーの版別資料は整理前の説明を履歴として保存したものです。相対リンクは移動先に合わせています。機械検証の証跡は元のdocs/evidenceで保持しています。[現行仕様](../README.md)を優先してください。今回の整理候補の試験は公開済み版の試験とは別に記録します。
