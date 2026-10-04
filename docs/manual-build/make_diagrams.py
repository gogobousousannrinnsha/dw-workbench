"""Create source-derived UI diagrams, without opening or operating the application.

Run with a Python environment containing Pillow. All operational labels and IDs
are read from controls.json and dialogs.json beside this file. Example values are
illustrative; these images are explicitly not application screenshots.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "diagrams"
CONTROL_DATA = json.loads((ROOT / "controls.json").read_text(encoding="utf-8-sig"))
CONTROLS = {c["id"]: c for c in CONTROL_DATA["controls"]}
DIALOGS = {d["id"]: d for d in json.loads((ROOT / "dialogs.json").read_text(encoding="utf-8-sig"))["dialogs"]}
PREFIX = {"common": "共通", "viewer": "原本", "worklist": "一覧", "setup": "設定",
          "review": "確認", "history": "履歴", "library": "共通登録"}
FONT_PATH = Path(os.environ.get("WINDIR", "Windows")) / "Fonts" / "meiryo.ttc"
W, MAX_H = 900, 2400
BG, BLUE, PALE, LINE, INK = "#ffffff", "#cce5f6", "#eef7fc", "#678497", "#172530"
FONTS = {size: ImageFont.truetype(str(FONT_PATH), size=size) for size in (18, 19, 20, 22, 24, 28)}


def control(cid: str) -> dict:
    return CONTROLS[cid]


def label(cid: str) -> str:
    return control(cid)["label"]


def number(cid: str) -> str:
    section, n = cid.rsplit("_", 1)
    return PREFIX[section] + n


def wrap(text: str, width: int, size: int = 22) -> list[str]:
    """Measure every character, including Japanese, before placing a line."""
    font = FONTS[size]
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for char in paragraph:
            if font.getlength(line + char) > width and line:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return lines


class Diagram:
    def __init__(self, name: str, title: str, section: str, note: str):
        self.name, self.title, self.section = name, title, section
        self.im = Image.new("RGB", (W, MAX_H), BG)
        self.draw = ImageDraw.Draw(self.im)
        self.y = 0
        self.marks: list[dict] = []
        self.bounds: list[tuple] = []
        self.box((0, 0, W - 1, 66), BLUE, None)
        self.text("UI構成図（ソースから作成・配置の目安）", 28, 15, W - 56, 24)
        self.y = 82
        self.y += self.text(title, 30, self.y, W - 60, 28) + 12
        self.y += self.text(note, 30, self.y, W - 60, 20) + 20

    def box(self, rect, fill=BG, outline=LINE, width=2):
        x0, y0, x1, y1 = rect
        assert 0 <= x0 < x1 < W and 0 <= y0 < y1 < MAX_H, (self.name, rect)
        self.draw.rectangle(rect, fill=fill, outline=outline, width=width)
        self.bounds.append(rect)

    def text(self, text, x, y, width, size=22, fill=INK) -> int:
        lines = wrap(text, width, size)
        height = len(lines) * (size + 10)
        assert x >= 0 and x + width <= W and y >= 0 and y + height < MAX_H
        for index, line in enumerate(lines):
            at = (x, y + index * (size + 10))
            bbox = self.draw.textbbox(at, line, font=FONTS[size])
            assert bbox[0] >= 0 and bbox[2] <= W and bbox[3] < MAX_H, (self.name, line, bbox)
            assert FONTS[size].getlength(line) <= width + 0.01, (self.name, line, width)
            self.draw.text(at, line, font=FONTS[size], fill=fill)
            self.bounds.append(bbox)
        return height

    def tag(self, cid, x, y, target=None, caption=None):
        value = number(cid)
        tw = int(FONTS[19].getlength(value)) + 18
        self.box((x, y, x + tw, y + 34), BLUE, None)
        self.text(value, x + 9, y + 1, tw - 17, 19)
        rect = target or (x, y, x + tw, y + 34)
        self.marks.append({"control_id": cid, "sourceID": cid, "display_id": value,
                           "label": caption or control(cid).get("annotation_label") or label(cid),
                           "source_line": control(cid)["source_line"],
                           "x": rect[0], "y": rect[1], "width": rect[2] - rect[0],
                           "height": rect[3] - rect[1], "badge_x": x, "badge_y": y})
        return tw

    def row(self, cid, value="", dropdown=False):
        y = self.y
        self.tag(cid, 32, y)
        h = self.text(label(cid), 130, y + 1, 730, 22)
        top = y + max(40, h + 8)
        self.box((130, top, 860, top + 50), PALE)
        self.text(value, 144, top + 7, 670 if dropdown else 700, 22)
        if dropdown:
            self.text("▼", 827, top + 7, 26, 22)
        self.marks[-1].update(x=130, y=top, width=730, height=50)
        self.y = top + 67

    def buttons(self, ids, widths=None):
        """Place exact button labels and their catalogue IDs; wrap rather than shrink."""
        widths = widths or [W - 64] * len(ids)
        x, y, rowh = 32, self.y, 0
        for cid, width in zip(ids, widths):
            tw = int(FONTS[19].getlength(number(cid))) + 18
            lines = wrap(label(cid), width - tw - 32, 22)
            height = max(58, len(lines) * 32 + 20)
            if x + width > W - 32:
                x, y, rowh = 32, y + rowh + 12, 0
            self.box((x, y, x + width, y + height), PALE)
            self.tag(cid, x + 8, y + 12, (x, y, x + width, y + height))
            self.text(label(cid), x + tw + 18, y + 11, width - tw - 30, 22)
            rowh = max(rowh, height)
            x += width + 12
        self.y = y + rowh + 18

    def info(self, text, cid=None):
        y = self.y
        x = 130 if cid else 46
        if cid:
            self.tag(cid, 32, y + 8)
        height = self.text(text, x, y + 10, 730 if cid else 798, 20) + 20
        self.y += max(54, height) + 12

    def table(self, cid, rows, widths=None):
        columns = control(cid)["columns"]
        widths = widths or [int(800 / len(columns))] * len(columns)
        assert len(widths) == len(columns) and sum(widths) == 800
        self.tag(cid, 32, self.y)
        self.text("一覧（値は例）", 130, self.y + 1, 700, 22)
        y = self.y + 44
        tabletop = y
        for ri, row in enumerate([columns] + rows):
            assert len(row) == len(columns)
            h = max(len(wrap(value, width - 20, 22)) * 32 + 18 for value, width in zip(row, widths))
            x = 40
            for value, width in zip(row, widths):
                self.box((x, y, x + width, y + h), BLUE if ri == 0 else PALE if ri == 1 else BG)
                self.text(value, x + 10, y + 8, width - 20, 22)
                x += width
            y += h
        self.marks[-1].update(x=40, y=tabletop, width=800, height=y - tabletop)
        self.y = y + 18

    def confirm_text(self, cid, scroll_id, lines):
        y = self.y
        self.tag(cid, 32, y)
        self.text("対象一覧（読み取り専用・内容は例）", 130, y + 1, 700, 22)
        self.tag(scroll_id, 746, y + 44)
        top = y + 90
        h = sum(len(wrap(t, 738, 22)) * 32 + 20 for t in lines) + 22
        self.box((40, top, 860, top + h), BG)
        at = top + 12
        for t in lines:
            at += self.text(t, 54, at, 738, 22) + 20
        self.box((819, top + 5, 851, top + h - 5), PALE)
        self.box((824, top + 20, 846, top + min(100, h - 15)), BLUE)
        self.marks[-2].update(x=40, y=top, width=770, height=h)
        self.marks[-1].update(x=819, y=top + 5, width=32, height=h - 10)
        self.y = top + h + 18

    def heading(self, title):
        self.box((32, self.y, 868, self.y + 48), BLUE, None)
        self.text(title, 46, self.y + 5, 808, 24)
        self.y += 62

    def ordinary_buttons(self, dialog_id):
        """OS/Tk standard controls have no extra catalogue IDs; don't invent IDs."""
        button_labels = [c["label"] for c in DIALOGS[dialog_id]["controls"] if c["kind"] == "ボタン"]
        x, width = 380, 210
        height = max(max(52, len(wrap(text, width - 24, 22)) * 32 + 18) for text in button_labels)
        for text in button_labels:
            self.box((x, self.y, x + width, self.y + height), PALE)
            self.text(text, x + 12, self.y + 9, width - 24, 22)
            x += width + 20
        self.y += height + 14

    def finish(self, notes):
        self.y += 6
        self.box((32, self.y, 868, self.y + 3), LINE, None)
        self.y += 16
        for note in notes:
            self.y += self.text("・" + note, 36, self.y, 828, 20) + 8
        self.y += 8
        self.y += self.text("番号は操作説明のIDと対応。枠・寸法・配置は模式化しています。", 36, self.y, 828, 18)
        height = self.y + 24
        assert all(0 <= r[0] <= r[2] < W and 0 <= r[1] <= r[3] < height for r in self.bounds)
        OUT.mkdir(parents=True, exist_ok=True)
        file = f"assets/diagrams/{self.name}.png"
        self.im.crop((0, 0, W, height)).save(ROOT / file)
        return {"name": self.name, "label": self.title, "file": file, "width": W, "height": height,
                "kind": "source-diagram", "section": self.section, "marks": self.marks}


def make_all():
    manifest = []
    d = Diagram("10-setup-upper", "テンプレート作成：上部の入力と項目一覧", "setup",
                "実画面の撮影ではありません。文字と選択肢はソースから作成し、入力値は例です。")
    d.row("setup_02", "例：測定票 A 配置")
    d.row("setup_03", " / ".join(control("setup_03")["options"]), True)
    d.info(label("setup_04"), "setup_04")
    d.row("setup_05", "例：測定結果 版1 [定義ID]", True)
    d.row("setup_06", "例：測定結果")
    d.buttons(["setup_07", "setup_08"], [420, 404])
    d.table("setup_09", [["部品番号", "文字列 必須", "未指定"], ["測定温度", "数値 必須", "未指定"]], [260, 230, 310])
    manifest.append(d.finish(["ページ用は代表ページの範囲を、適用先の各ページへ対応させます。",
                              "定義を選んだ後、設定07で反映します。同じ定義ID・版は同じ結果シートになります。",
                              "テンプレートを作り始めると、設定04は草案の原本・代表ページ・登録予定版を表示します。"] ))

    d = Diagram("11-setup-lower", "テンプレート作成：項目操作と登録", "setup",
                "上部から続く構成図です。項目の順序と読み取り範囲を整えてから登録します。")
    d.table("setup_09", [["部品番号", "文字列 必須", "このページ [mm座標]"], ["測定温度", "数値 必須", "このページ [mm座標]"]], [250, 220, 330])
    d.buttons(["setup_10", "setup_11", "setup_12"], [270, 270, 272])
    d.buttons(["setup_13", "setup_14", "setup_15"], [190, 190, 432])
    d.info(label("setup_16"), "setup_16")
    d.buttons(["setup_17", "setup_18"])
    manifest.append(d.finish(["追加・編集の保存は草案への反映です。設定17で案件内の登録版を作ります。",
                              "登録済み版は上書きしません。設定15で改訂草案を作り、新しい版を登録します。",
                              "設定18は未登録草案を破棄します。登録済み版・確認結果は削除しません。"] ))

    d = Diagram("12-field-dialog", "項目を追加／項目を編集：入力ダイアログ", "dialogs",
                "追加・編集は同じ入力構成です。以下の入力値は例で、実画面ではありません。")
    d.heading(DIALOGS["field_add"]["title"] + " ／ " + DIALOGS["field_edit"]["title"])
    d.row("setup_20", "例：測定温度")
    d.row("setup_21", " / ".join(control("setup_21")["options"]), True)
    d.info(label("setup_22"), "setup_22")
    d.tag("setup_23", 32, d.y)
    d.box((130, d.y + 4, 154, d.y + 28), BG)
    d.text("✓", 131, d.y - 1, 25, 22)
    d.text(label("setup_23"), 170, d.y + 1, 670, 22)
    d.y += 56
    d.row("setup_24", "例：℃")
    d.buttons(["setup_25", "setup_26"], [420, 404])
    manifest.append(d.finish(["設定25は草案の項目を保存します。テンプレートの正式登録は別の操作です。",
                              "追加時は文字列・必須が初期値です。編集時は選択項目の内容を表示します。",
                              "設定26は今回の項目追加・編集を取り消します。"] ))

    d = Diagram("13-assignment-confirm", "適用前確認：対象と旧版→新版", "dialogs",
                "変更対象の確認方法を示す構成図です。文書名・対象・版の表示例を用いています。")
    d.heading(DIALOGS["assignment_preview"]["title"])
    d.info("例：測定票.xdw / 2記録")
    d.confirm_text("worklist_15", "worklist_16", ["2ページ: A配置 版1 → A配置 版2",
                    "3ページ: 未選択 → A配置 版2 （寸法不一致・自動OCRなし）"])
    d.info("切替前の結果は履歴へ保存します。新しい記録の値・確認状態は引き継ぎません。")
    d.buttons(["worklist_18", "worklist_17"], [260, 564])
    manifest.append(d.finish(["一覧17で実行、一覧18で実行せず戻ります。適用だけではOCR・確認は完了しません。",
                              "同じテンプレートID・版への適用は「同じ版・変更なし」です。",
                              "寸法不一致は項目を残して自動OCRを停止します。手入力・根拠指定を使えます。"] ))

    d = Diagram("14-incomplete-export", "未完了一覧：完了した記録だけを出力", "dialogs",
                "案件出力時の判断を示す構成図です。未完了対象・項目の表示例を用いています。")
    d.heading(DIALOGS["incomplete_export_confirmation"]["title"])
    d.info("未完了2記録を除外して、完了した記録だけを出力します。")
    d.confirm_text("history_08", "history_09", ["例：測定票.xdw / 3ページ / 部品番号、測定温度",
                    "例：別の測定票.xdw / 文書全体 / 測定温度"])
    d.buttons(["history_11", "history_10"], [260, 564])
    manifest.append(d.finish(["履歴10は未完了分を除外した部分出力です。履歴11で戻り、残る確認作業を続けられます。",
                              "完了記録がゼロの場合は出力できません。除外対象は出力情報へ記録します。",
                              "理由付き対象外ページは未完了一覧とは別に、出力情報へ理由を記録します。"] ))

    d = Diagram("15-assignment-history", "変更前の結果：閲覧する記録を選ぶ", "dialogs",
                "テンプレート切替時の履歴です。確定時点を保存する「出力履歴」とは別の一覧です。")
    d.buttons(["worklist_11"])
    d.heading(DIALOGS["assignment_history"]["title"])
    d.table("worklist_20", [["A配置 版2", "現在", "例：7c9f2a103bde"],
                            ["A配置 版1", "変更前・編集不可", "例：2b014ae0316f"]], [280, 270, 250])
    d.buttons(["worklist_21"])
    manifest.append(d.finish(["一ページだけを選んで開きます。文書全体方式では一文書の記録が対象です。",
                              "一覧21で選択結果を編集不可で表示します。「現在」の行も、この経路では編集不可です。",
                              "編集へ戻るには作業一覧で文書・ページを選び直します。閉じる操作はウィンドウの×です。"] ))

    d = Diagram("16-standard-inputs", "標準入力・フォルダー選択：共通操作の模式図", "dialogs",
                "下の三つは独立した操作です。一枚の実画面ではなく、標準ダイアログの内容を整理しています。")
    d.buttons(["common_02"])
    d.heading(DIALOGS["new_project"]["title"])
    d.row("common_13", "例：今月の測定結果")
    d.ordinary_buttons("new_project")
    d.info("空欄またはCancelは作成しません。OKでPortable内に新しい案件を作成します。")
    d.buttons(["common_03"])
    d.heading(DIALOGS["choose_project"]["title"])
    d.info("OS標準のフォルダー一覧／選択欄で、project.sqliteを直接含む案件フォルダーを選びます。")
    d.ordinary_buttons("choose_project")
    d.buttons(["common_07"])
    d.heading(DIALOGS["backup_destination"]["title"])
    d.info("OS標準のフォルダー一覧／選択欄で、現在の案件の外にある親フォルダーを選びます。")
    d.ordinary_buttons("backup_destination")
    manifest.append(d.finish(["共通02・03・07は呼び出すボタン、共通13は案件名入力です。標準ボタンには独自の操作番号はありません。",
                              "OS標準選択画面の配置・ボタン表記はWindowsの言語・環境で変わります。図は配置を保証しません。",
                              "バックアップは未保存内容を保存し、実行中処理を終えてから作成します。完了表示を待ってください。"] ))

    (ROOT / "diagram_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = {"generator": "make_diagrams.py", "font": FONT_PATH.name,
                "controls_sha256": hashlib.sha256((ROOT / "controls.json").read_bytes()).hexdigest(),
                "dialogs_sha256": hashlib.sha256((ROOT / "dialogs.json").read_bytes()).hexdigest(),
                "source_file": CONTROL_DATA["source_file"], "source_sha256": CONTROL_DATA["source_sha256"],
                "diagram_count": len(manifest), "bounds_validation": "passed",
                "scope": "Source-derived diagrams only; no app launch, UI operation, or screenshot capture.",
                "images": [{"file": x["file"], "sha256": hashlib.sha256((ROOT / x["file"]).read_bytes()).hexdigest(),
                            "width": x["width"], "height": x["height"], "mark_count": len(x["marks"])} for x in manifest]}
    (OUT / "generation-verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"diagrams": len(manifest), "manifest": str(ROOT / "diagram_manifest.json"),
                      "bounds_validation": "passed", "sizes": [(d["name"], d["width"], d["height"]) for d in manifest]}, ensure_ascii=False))


if __name__ == "__main__":
    make_all()
