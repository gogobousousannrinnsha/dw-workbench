"""Draw the two-field beginner diagrams without launching or operating the app.

The original synthetic PNG is read only, scaled and clipped while placing it on
the diagram canvas. It is never overwritten. These are explicitly source-based
diagrams, not screenshots or proof of manual GUI operation.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "beginner-diagrams"
FONT = Path(os.environ.get("WINDIR", "Windows")) / "Fonts" / "meiryo.ttc"
CONTROLS_DATA = json.loads((ROOT / "controls.json").read_text(encoding="utf-8-sig"))
CONTROLS = {c["id"]: c for c in CONTROLS_DATA["controls"]}
DEMO = json.loads((ROOT / "beginner_demo.json").read_text(encoding="utf-8-sig"))
SOURCE = ROOT / DEMO["source_png"]
SOURCE_HASH = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FONTS = {n: ImageFont.truetype(str(FONT), n) for n in (18, 20, 22, 24, 26, 28, 30)}
PREFIX = {"common": "共通", "viewer": "原本", "worklist": "一覧", "setup": "設定",
          "review": "確認", "history": "履歴", "library": "共通登録"}
W, MAX_H = 900, 1800
INK, MUTED, BLUE, GREEN, AMBER = "#172d3e", "#526977", "#205e84", "#147465", "#9a5c12"
PALE, TEAL_PALE, AMBER_PALE, LINE = "#edf5fb", "#ebf7f2", "#fff6e5", "#aac0cd"
NOTICE = "UI構成図（ソースから作成・配置の目安）"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrapped(text, width, size):
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for char in paragraph:
            if line and FONTS[size].getlength(line + char) > width:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return lines


class Diagram:
    def __init__(self, name, title, section, subtitle):
        self.name, self.title, self.section = name, title, section
        self.image = Image.new("RGB", (W, MAX_H), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.marks, self.bounds = [], []
        self.rect(0, 0, W - 1, 56, fill=PALE, outline=None)
        self.text(NOTICE, 28, 12, 840, 24, BLUE)
        y = 78
        y += self.text(title, 32, y, 836, 28) + 10
        y += self.text(subtitle, 32, y, 836, 20, MUTED) + 20
        self.y = y

    def rect(self, x, y, w, h, fill="white", outline=LINE, radius=8, width=2):
        assert 0 <= x and 0 <= y and x + w < W and y + h < MAX_H, (self.name, x, y, w, h)
        self.draw.rounded_rectangle((x, y, x + w, y + h), radius=radius,
                                    fill=fill, outline=outline, width=width)
        self.bounds.append((x, y, x + w, y + h))

    def text(self, value, x, y, width, size=22, fill=INK):
        lines = wrapped(value, width, size)
        height = len(lines) * (size + 10)
        assert 0 <= x and x + width <= W and 0 <= y and y + height < MAX_H
        for i, line in enumerate(lines):
            bbox = self.draw.textbbox((x, y + i * (size + 10)), line, font=FONTS[size])
            assert 0 <= bbox[0] and bbox[2] <= W and 0 <= bbox[1] and bbox[3] < MAX_H, (self.name, line, bbox)
            assert FONTS[size].getlength(line) <= width + 0.01, (self.name, line)
            self.draw.text((x, y + i * (size + 10)), line, font=FONTS[size], fill=fill)
            self.bounds.append(bbox)
        return height

    def tag(self, cid, x, y, rect=None):
        section, n = cid.rsplit("_", 1)
        name = PREFIX[section] + n
        width = int(FONTS[18].getlength(name)) + 16
        self.rect(x, y, width, 32, fill=BLUE, outline=None, radius=5)
        self.text(name, x + 8, y + 2, width - 16, 18, "white")
        target = rect or (x, y, width, 32)
        self.marks.append({"control_id": cid, "display_id": name,
                           "label": CONTROLS[cid]["label"], "source_line": CONTROLS[cid]["source_line"],
                           "x": target[0], "y": target[1], "width": target[2], "height": target[3],
                           "badge_x": x, "badge_y": y})
        return width

    def arrow(self, x1, y1, x2, y2, color=BLUE, width=4):
        self.draw.line((x1, y1, x2, y2), fill=color, width=width)
        if y1 == y2:
            s = 1 if x2 > x1 else -1
            self.draw.polygon([(x2, y2), (x2 - s * 11, y2 - 7), (x2 - s * 11, y2 + 7)], fill=color)
        else:
            s = 1 if y2 > y1 else -1
            self.draw.polygon([(x2, y2), (x2 - 7, y2 - s * 11), (x2 + 7, y2 - s * 11)], fill=color)

    def note(self, value, y=None, fill=AMBER_PALE):
        y = self.y if y is None else y
        lines = wrapped(value, 804, 20)
        h = len(lines) * 30 + 24
        self.rect(32, y, 836, h, fill=fill, outline=None)
        self.text(value, 48, y + 10, 804, 20, AMBER if fill == AMBER_PALE else GREEN)
        self.y = y + h + 16

    def button(self, cid, x, y, width, fill=PALE):
        tag_w = int(FONTS[18].getlength(PREFIX[cid.rsplit("_", 1)[0]] + cid.rsplit("_", 1)[1])) + 16
        lines = wrapped(CONTROLS[cid]["label"], width - tag_w - 30, 22)
        height = max(56, len(lines) * 32 + 20)
        self.rect(x, y, width, height, fill=fill)
        self.tag(cid, x + 10, y + 12, (x, y, width, height))
        self.text(CONTROLS[cid]["label"], x + tag_w + 20, y + 11, width - tag_w - 30, 22)
        return height

    def field(self, cid, value, x, y, width, value_fill="white"):
        tw = self.tag(cid, x, y)
        self.text(CONTROLS[cid]["label"], x + tw + 10, y + 1, width - tw - 10, 22)
        self.rect(x, y + 41, width, 52, fill=value_fill)
        self.text(value, x + 12, y + 49, width - 24, 24)
        self.marks[-1].update(x=x, y=y + 41, width=width, height=52)
        return 108

    def sample_window(self, x, y, width, height, value_y=56):
        """Canvas-only clipping of the read-only source image; no PNG modification."""
        self.rect(x, y, width, height, radius=0)
        source = Image.open(SOURCE).convert("RGB")
        # Scale the complete source to the viewport width, then shift it so the
        # first evidence range begins near value_y. The canvas clips the rest.
        shown = source.resize((width, round(source.height * width / source.width)), Image.Resampling.LANCZOS)
        page_h = shown.height
        offset_y = round(value_y - 75 / 297 * page_h)
        viewport = Image.new("RGB", (width, height), "white")
        viewport.paste(shown, (0, offset_y))
        self.image.paste(viewport, (x, y))
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rectangle((x, y, x + width, y + height), outline=LINE, width=2)
        self.bounds.append((x, y, x + width, y + height))
        def position(rect):
            rx, ry, rw, rh = rect
            return (x + rx / 210 * width, y + offset_y + ry / 297 * page_h,
                    rw / 210 * width, rh / 297 * page_h)
        return position

    def evidence_rect(self, rectangle, color=GREEN):
        x, y, w, h = rectangle
        self.draw.rectangle((x, y, x + w, y + h), outline=color, width=4)
        self.bounds.append((x, y, x + w, y + h))

    def finish(self, footnotes=()):
        if footnotes:
            for note in footnotes:
                self.note(note)
        height = int(max(self.y + 12, max(b[3] for b in self.bounds) + 28))
        assert height < MAX_H
        OUT.mkdir(parents=True, exist_ok=True)
        file = OUT / (self.name + ".png")
        self.image.crop((0, 0, W, height)).save(file)
        return {"name": self.name, "label": self.title, "file": file.relative_to(ROOT).as_posix(),
                "width": W, "height": height, "kind": "source-diagram", "section": self.section,
                "marks": self.marks, "caption": NOTICE, "synthetic": True,
                "actual_application_screenshot": False}


def result_row(d, x, y, width, title="一行の結果", unit=True):
    d.text(title, x, y, width, 22, BLUE)
    y += 38
    columns = [("部品番号", "000125", "文字列"), ("測定温度", "179.8", "数値")]
    if unit:
        columns.append(("測定温度 単位", "℃", "文字列"))
    cell = width / len(columns)
    for i, (label, value, kind) in enumerate(columns):
        cx = x + i * cell
        d.rect(cx, y, cell, 103, fill=TEAL_PALE, radius=0)
        d.text(label, cx + 10, y + 7, cell - 20, 20)
        d.text(value, cx + 10, y + 39, cell - 20, 26, GREEN)
        d.text(kind, cx + 10, y + 74, cell - 20, 18, MUTED)
    return y + 120


def mode_figure():
    d = Diagram("b01-record-unit", "一行を何の結果にするか、適用前に選ぶ", "beginner-decisions",
                "入門サンプルは一ページ・二項目なので、最初はページごとを使います。")
    y = d.y
    d.tag("worklist_03", 32, y)
    d.text("処理単位", 136, y, 720, 24)
    y += 48
    for x, title, rule, note in [
        (32, "ページごと（一ページ一行）", "一ページ → 一つの結果記録", "各ページへページ用テンプレートを選ぶ"),
        (460, "文書全体（一文書一行）", "一つのXDW → 一つの結果記録", "文書全体用テンプレートを選ぶ"),
    ]:
        d.rect(x, y, 408, 329, fill=PALE)
        d.text(title, x + 18, y + 15, 372, 22, BLUE)
        d.text("入門サンプル.xdw（1ページ）", x + 18, y + 65, 372, 20)
        d.text("部品番号 000125\n測定温度 179.8℃", x + 18, y + 106, 372, 24)
        d.arrow(x + 204, y + 184, x + 204, y + 218)
        d.text(rule, x + 18, y + 232, 372, 22, GREEN)
        d.text(note, x + 18, y + 271, 372, 20, MUTED)
    d.y = y + 348
    d.note("一ページのこの例では、どちらも一行です。複数ページでは、ページごとは各ページが別の行、文書全体は指定した各ページの項目を合わせて一行になります。")
    d.note("処理単位を選ぶ → テンプレート適用または対象外指定 → そのXDWの処理単位が固定されます。表紙だけ先に対象外にする場合も、先に方式を決めます。")
    return d.finish(["一つの案件に両方式をまとめられます。一つのXDWの途中で両方式を混ぜる機能や、ページを任意の組へ束ねる機能はありません。"])


def definition_figure():
    d = Diagram("b02-schema-layout", "項目定義を共通にして、範囲だけ配置A/Bで変える", "beginner-decisions",
                "配置Bは説明用です。最初の一行を出すときは、配置Aの入門ページだけを作ります。")
    y = d.y
    d.rect(32, y, 836, 138, fill=TEAL_PALE)
    d.text("共通の項目定義：測定記録（入門用） 版1", 50, y + 12, 800, 24, GREEN)
    d.text("部品番号＝文字列・必須・単位なし\n測定温度＝数値・必須・標準単位℃", 50, y + 55, 800, 22)
    y += 163
    d.arrow(232, y - 14, 232, y + 16)
    d.arrow(664, y - 14, 664, y + 16)
    y += 30
    for x, title, first, second in [
        (32, "配置A：入門ページ", "部品番号 000125", "測定温度 179.8℃"),
        (460, "配置B：入門ページ 配置B", "測定温度 179.8℃", "部品番号 000125"),
    ]:
        d.rect(x, y, 408, 183, fill=PALE)
        d.text(title, x + 16, y + 12, 376, 22, BLUE)
        d.rect(x + 16, y + 67, 376, 45, fill="white", outline=GREEN)
        d.text(first, x + 27, y + 72, 354, 22)
        d.rect(x + 16, y + 124, 376, 45, fill="white", outline=GREEN)
        d.text(second, x + 27, y + 129, 354, 22)
    y += 203
    d.tag("setup_07", 32, y)
    d.text("配置Bでは「選択した項目定義を使用」", 137, y, 725, 22)
    y += 42
    d.text("同じ定義・版を選び、配置Bの範囲だけを指定します。", 32, y, 836, 22)
    y += 47
    d.arrow(450, y, 450, y + 32)
    y += 45
    d.y = result_row(d, 32, y, 836, "同じ定義・版の結果 → 同じ結果シート（最初の例は一行）")
    return d.finish(["項目名が同じだけでは同じ結果シートになりません。既存の項目定義・版を明示して使用します。",
                     "範囲やテンプレート名だけの変更は同じ項目定義版を使えます。項目定義名・項目の内容や順序を変える場合は、新しい定義版になります。"])


def drag_figure():
    d = Diagram("b03-drag-evidence", "項目を選ぶ → 原本の値をドラッグで囲む", "beginner-beginner_06",
                "二回の範囲指定を一枚にまとめた図です。実画面の枠は、選択項目のものです。")
    y = d.y
    d.tag("setup_09", 32, y)
    d.text("① 部品番号を選ぶ　② 囲む　③ 測定温度でも同じ操作", 137, y, 720, 22)
    y += 53
    d.text("原本のラベルと値の周辺（合成原本PNGを配置）", 32, y, 836, 20, MUTED)
    y += 36
    position = d.sample_window(32, y, 836, 310, value_y=44)
    part = position(DEMO["profile"]["regions"]["part"]["rect"])
    measured = position(DEMO["profile"]["regions"]["measured"]["rect"])
    d.evidence_rect(part, BLUE)
    d.evidence_rect(measured, GREEN)
    d.tag("viewer_06", 48, y + 13, (32, y, 836, 310))
    for rect, word, color in [(part, "部品番号の値", BLUE), (measured, "測定温度の値", GREEN)]:
        rx, ry, rw, rh = rect
        d.draw.ellipse((rx - 6, ry - 6, rx + 6, ry + 6), fill=color)
        d.draw.ellipse((rx + rw - 6, ry + rh - 6, rx + rw + 6, ry + rh + 6), fill=color)
        # Keep the direction arrow below the printed value so all digits remain
        # legible. The corner circles identify mouse-down and mouse-up positions.
        d.arrow(rx + 10, ry + rh - 12, rx + rw - 12, ry + rh - 12, color)
        d.text(word, 55, ry + rh + 5, 300, 20, color)
    d.y = y + 329
    d.note("マウスを押す → 値の右下まで動かす → 離す。項目ごとに別の範囲を指定します。ラベルや別行を含めて、値の取り違えがないか周辺表示でも確認します。", fill=TEAL_PALE)
    h = d.button("setup_17", 32, d.y, 836)
    d.y += h + 18
    return d.finish(["測定温度の枠は数値179.8を含みます。原本の周辺にある単位℃も照合します。倍率やスクロールを変えても、保存した根拠はページ上の位置です。"])


def apply_figure():
    d = Diagram("b04-apply-empty", "テンプレートを適用しても、OCRは始まらない", "beginner-beginner_07",
                "適用は二項目の記録と範囲を用意する操作です。この例は手入力で値を入れます。")
    y = d.y
    y += d.field("worklist_06", "選択ページ → 1ページ", 32, y, 836)
    y += d.field("worklist_08", "入門ページ / 版1 / ページ用", 32, y, 836)
    y += d.button("worklist_09", 32, y, 836) + 16
    d.text("プレビューで対象1ページを確認し、「適用する」", 32, y, 836, 22)
    y += 49
    y += d.button("worklist_17", 32, y, 836) + 12
    d.arrow(450, y, 450, y + 30)
    y += 46
    d.tag("review_02", 32, y)
    d.text("確認・訂正：適用直後の二項目", 137, y, 720, 22)
    y += 43
    widths = [300, 260, 276]
    for row_i, row in enumerate([("項目", "採用値", "状態"), ("部品番号", "（空欄）", "未取得"), ("測定温度", "（空欄）", "未取得")]):
        x = 32
        for width, text in zip(widths, row):
            d.rect(x, y, width, 53, fill=PALE if row_i == 0 else "white", radius=0)
            d.text(text, x + 12, y + 10, width - 24, 22)
            x += width
        y += 53
    d.y = y + 18
    return d.finish(["単位の標準値は項目定義から入り、範囲はテンプレートから準備されます。採用値はまだ空欄です。",
                     "OCRを使う場合は、利用可能なGPU・モデルなどを確認し、別のOCRボタンで実行します。適用だけで000125や179.8が読み取られるわけではありません。"])


def review_figure():
    d = Diagram("b05-manual-accept", "手入力の保存と、原本確認は別の操作", "beginner-beginner_09",
                "最初の例はOCRなし。部品番号も測定温度も、原本と照合して一つずつ確認済みにします。")
    y = d.y
    d.text("原本周辺：ラベル、行、値、単位を照合", 32, y, 836, 22, BLUE)
    y += 41
    position = d.sample_window(32, y, 836, 291, value_y=39)
    d.evidence_rect(position(DEMO["profile"]["regions"]["measured"]["rect"]))
    y += 310
    d.tag("review_02", 32, y)
    d.text("項目ごとに選んで入力（ここでは両方の入力を併記）", 137, y, 720, 22)
    y += 45
    for x, title, value, unit, raw in [
        (32, "部品番号", "000125", "（空欄）", "000125"),
        (460, "測定温度", "179.8", "℃", "179.8℃"),
    ]:
        d.rect(x, y, 408, 400, fill=PALE)
        d.text(title, x + 16, y + 12, 376, 24, BLUE)
        yy = y + 54
        yy += d.field("review_04", value, x + 16, yy, 376)
        yy += d.field("review_05", unit, x + 16, yy, 376)
        yy += d.field("review_06", raw, x + 16, yy, 376)
    y += 418
    d.tag("review_09", 32, y)
    d.text("保存済み ≠ 確認済み。保存成功は入力を残せたという表示です。", 137, y, 720, 22, AMBER)
    y += 75
    y += d.button("review_11", 32, y, 836, TEAL_PALE) + 18
    d.y = y
    return d.finish(["値・原文・根拠を照合して押します。二項目とも確認済みになれば、この一ページは2/2項目完了です。",
                     "確認・訂正でドラッグした根拠の訂正は現在の記録に保存します。登録済みテンプレートの読み取り範囲を変更する操作ではありません。"])


def state_figure():
    d = Diagram("b06-save-accept-freeze", "候補・採用・保存・確認・確定・生成を分ける", "beginner-beginner_10",
                "000125 と 179.8℃ が同じ一行になるまで。機械候補を使わず、手入力でも同じ流れです。")
    y = d.y
    for x, heading, explanation, fill in [
        (32, "手入力（この入門例）", "採用値へ 000125 / 179.8\n単位へ ℃、原文も保存", TEAL_PALE),
        (460, "OCR候補（使う場合だけ）", "候補を選んで採用欄へ取り込む\n候補だけでは確認済みにならない", PALE),
    ]:
        d.rect(x, y, 408, 143, fill=fill)
        d.text(heading, x + 16, y + 12, 376, 22, BLUE)
        d.text(explanation, x + 16, y + 54, 376, 20)
    y += 161
    d.arrow(232, y, 232, y + 24)
    d.arrow(664, y, 664, y + 24)
    y += 37
    for index, (heading, message, fill) in enumerate([
        ("採用値を保存", "000125 / 179.8 / ℃ が案件に残る。まだ未確認。", PALE),
        ("原本と照合 → 確認済み", "二項目の値・原文・根拠を照合。2/2項目完了。", TEAL_PALE),
        ("確認済み記録の確定結果を保存", "この時点の値・根拠・対象を固定。過去の結果は編集不可。", PALE),
        ("Excel／CSVを生成・検証", "案件結果.xlsx と 結果01.csv。出力履歴で各ファイルの成否を確認。", TEAL_PALE),
    ]):
        d.rect(32, y, 836, 101, fill=fill)
        d.text(heading, 50, y + 10, 800, 24, BLUE if fill == PALE else GREEN)
        d.text(message, 50, y + 52, 800, 20)
        y += 113
        if index < 3:
            d.arrow(450, y - 5, 450, y + 19)
            y += 31
    d.y = y + 7
    d.note("保存後でも、値・原文・単位・根拠を訂正すると再確認が必要です。確定結果の保存と、表の生成・履歴保存はそれぞれ成否を確認します。")
    return d.finish(["一件以上の記録が完了したら案件を出力できます。未完了があれば一覧を確認し、完了分だけを対象にする出力も選べます。この入門例は全一件が完了です。",
                     "表の生成に失敗しても確認結果・確定結果は残ります。出力履歴で未生成・失敗した形式だけ再出力します。"])


def main():
    assert DEMO["synthetic"] and DEMO["ocr_calls"] == 0
    assert DEMO["fields"]["part"]["value"] == "000125"
    assert DEMO["fields"]["measured"]["value"] == "179.8"
    manifest = [mode_figure(), definition_figure(), drag_figure(), apply_figure(), review_figure(), state_figure()]
    figures = {}
    for entry in manifest:
        # Keep the same PNG assets, but split the two tall ones for legible A4
        # display. The manual clips the image canvas; no original PNG is edited.
        split = {
            "b05-manual-accept": [
                ("原本周辺でラベル・値・単位を照合", [0, 0, 900, 520]),
                ("採用値・単位・原文の入力と、保存・確認", [0, 520, 900, entry["height"] - 520]),
            ],
            "b06-save-accept-freeze": [
                ("候補・採用・保存・確認・確定・生成の流れ", [0, 0, 900, 917]),
                ("訂正・未完了・出力失敗時に確認すること", [0, 917, 900, entry["height"] - 917]),
            ],
        }
        for title, crop in split.get(entry["name"], [(entry["label"], [0, 0, entry["width"], entry["height"]])]):
            x, y, w, h = crop
            marks = [m for m in entry["marks"] if x <= m["badge_x"] + 40 <= x + w
                     and y <= m["badge_y"] + 17 <= y + h]
            figures.setdefault(entry["section"], []).append({
                "shot": entry["name"], "title": title, "kind": "source-diagram",
                "crop": crop, "marks": marks, "max_width_mm": 174,
            })
    assert digest(SOURCE) == SOURCE_HASH, "Original sample PNG must remain unchanged"
    report = {
        "generator": "make_beginner_diagrams.py", "generator_sha256": digest(Path(__file__)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "font": FONT.name, "diagram_count": len(manifest),
        "displayed_figures": sum(map(len, figures.values())),
        "scope": "Source-based diagrams only; no app startup, foreground operation or screenshot capture.",
        "original_png": SOURCE.relative_to(ROOT).as_posix(), "original_png_sha256_before": SOURCE_HASH,
        "original_png_sha256_after": digest(SOURCE), "original_png_unchanged": True,
        "original_png_kind": "Pillow-generated synthetic fixture, not an SDK-rendered document view",
        "controls_sha256": digest(ROOT / "controls.json"), "ui_source_sha256": CONTROLS_DATA["source_sha256"],
        "beginner_demo_sha256": digest(ROOT / "beginner_demo.json"), "bounds_validation": "passed",
        "images": [{"file": e["file"], "width": e["width"], "height": e["height"],
                    "sha256": digest(ROOT / e["file"]), "mark_count": len(e["marks"])} for e in manifest],
    }
    for name, content in [("beginner_figure_manifest.json", manifest), ("beginner_figures.json", figures),
                          ("beginner_diagrams_report.json", report)]:
        (ROOT / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"count": len(manifest), "files": [e["file"] for e in manifest],
                      "original_png_unchanged": True, "bounds_validation": "passed"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
