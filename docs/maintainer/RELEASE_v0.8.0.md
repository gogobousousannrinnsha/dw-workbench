# v0.8.0 Portableのローカル配布候補

公開済みOCR v0.7.0、Workbench v0.2.0の第三者資産を基準に、Core 1.0.1、Integrations 0.14.0、Workbench 0.4.0を固定します。v0.3.0ローカル候補の複数文書へのテンプレート一括適用を保持し、次の未完了項目への移動、台帳照合と別XDWへの注釈、操作導線を加えます。OCRの確認一覧は領域ID・原本座標・元結果を保持し、低信頼度・空欄などの確認理由を出力します。

Portable起動には開発checkout・Codex・PC固有パスを使いません。`Workbench開始.bat`と従来のOCR BATが同じruntimeとモデルを使います。公開ソースは既存の変換器で自作部分をMITに変換し、第三者のLICENSE・NOTICEを保持します。配布対象一覧は厳密に照合し、Workbench起動BATの一覧漏れを修正しています。

ビルド入力は既存公開Workbench ZIPの固定SHA256と、公開変換後の3パッケージのwheelです。原本・実台帳・利用者DB・設定・ログ・認証情報を入力にしません。vendorファイル、モデル、同梱ライセンスを保持・照合します。LGPL関連の既存対応ソースZIPを配布資料に含めます。DocuWorks本体・SDK・XDWAPI・GPUドライバーを含めません。

検証は合成データを使います。実SDK・GPU OCR・確認と保存・Excel・台帳照合・注釈・実UI・フォルダー移動の結果をローカル引き渡し記録へ保存し、公開前に添付報告へ反映します。別の物理PC・DocuWorks 9.1・Viewer手操作・実帳票は未確認です。公開承認が来るまでpush・PR・merge・Release・アップロードは行いません。
