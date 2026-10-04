"""Build the offline illustrated manual from the reviewed JSON catalogs.

No application, project, source repository, or original PNG is modified.
Run with the bundled dependency Python. All outputs stay beside this script.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import math
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, KeepTogether, LongTable, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parent
PDF_NAME = "DW-Workbench_v0.2.0_図解操作マニュアル.pdf"
TITLE = "DW-Workbench v0.2.0 図解操作マニュアル"
SECTION_NAMES = {
    "common": "共通操作", "viewer": "原本表示", "worklist": "作業一覧",
    "setup": "テンプレート作成", "review": "確認・訂正",
    "history": "出力履歴", "library": "共通テンプレート",
}
PREFIXES = {
    "common": "共通", "viewer": "原本", "worklist": "一覧", "setup": "設定",
    "review": "確認", "history": "履歴", "library": "共通登録",
}
FIELDS = (("purpose", "役割"), ("when", "使う場面"), ("prerequisites", "前提"),
          ("steps", "操作"), ("result", "操作後"), ("notes", "注意"))
KIND_NAMES = {
    "button": "ボタン", "tab": "タブ", "entry": "入力欄", "dropdown": "選択欄",
    "list": "一覧", "status": "状態表示", "canvas": "表示領域",
    "scrollbar": "スクロールバー", "scroll": "スクロール操作",
    "splitter": "表示幅の調整", "window_close": "終了", "window_title": "タイトル",
    "guidance": "案内", "text": "確認一覧", "checkbox": "チェック欄",
    "confirmation": "確認画面", "tab_container": "タブ切替",
}
DEV_NOTE = re.compile(
    r"__version__|expected_revision|\bWindow\b|\bSQLite\b|trace_add|StringVar|"
    r"BooleanVar|ttk\.|tk\.|Treeview|treeview\.tcl|utils\.tcl|worker_request|"
    r"after_cancel|subfontIndex|<MouseWheel>|<Prior>|<Next>", re.I)
SOURCE_DIAGRAM_LABEL = "UI構成図（ソースから作成・配置の目安）"
REAL_SCREEN_LABEL = "実画面（合成サンプルで撮影）"
NOTICE = (
    "操作の説明はDW-Workbench v0.2.0の実ソースと呼び出し先の処理を確認して作成しています。"
    "実画面は説明用の合成サンプルです。UI構成図はソースから作った配置の目安で、撮影した実画面とは区別しています。"
    "この説明書は実帳票の認識精度や現地での操作確認を保証するものではありません。"
)


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def plain(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " / ".join(map(plain, value))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def esc(value):
    return html.escape(plain(value), quote=True)


def public_notes(record):
    notes = [plain(n) for n in as_list(record.get("notes")) if not DEV_NOTE.search(plain(n))]
    if record.get("id") == "first_complete_workflow":
        notes.append("出力履歴で開く確定時の結果は編集不可です。現在の編集へ戻るには、作業一覧で文書・ページを選び直します。")
    return notes


def annotation_id(control_id):
    match = re.fullmatch(r"([a-z]+)_(\d+)", str(control_id))
    if match and match[1] in PREFIXES:
        return PREFIXES[match[1]] + match[2].zfill(2)
    return str(control_id)


def control_title(control):
    return plain(control.get("annotation_label") or control.get("label") or control["id"])


def load_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def own_output(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("出力先は説明書フォルダー内にしてください")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Figure:
    number: int
    section: str
    title: str
    shot: str
    path: Path | None
    relative: str
    width: int
    height: int
    crop: tuple[float, float, float, float]
    marks: list[dict]
    kind: str
    error: str = ""
    max_width_mm: float = 174

    @property
    def evidence_label(self):
        return {"source-diagram": SOURCE_DIAGRAM_LABEL,
                "data-derived-workbook-view": "実XLSXのセル値から作成した表示図（Excelの撮影画像ではありません）",
                "source-document-view": "入門用の合成原本（DocuWorksで描画）"}.get(self.kind, REAL_SCREEN_LABEL)


def normalize_shots(manifest):
    if isinstance(manifest, dict):
        for key in ("screenshots", "shots", "images", "diagrams"):
            if key in manifest:
                return normalize_shots(manifest[key])
        result = []
        for name, value in manifest.items():
            item = {"file": value} if isinstance(value, str) else dict(value)
            item.setdefault("name", name)
            result.append(item)
        return result
    return [dict(item) for item in (manifest or [])]


def load_model():
    catalog = load_json(ROOT / "controls.json")
    dialogs_data = load_json(ROOT / "dialogs.json")
    if not catalog or not dialogs_data:
        raise ValueError("controls.json と dialogs.json が必要です")
    controls = catalog["controls"] if isinstance(catalog, dict) else catalog
    dialogs = dialogs_data.get("dialogs", [])
    workflows = dialogs_data.get("workflows", [])
    glossary = dialogs_data.get("glossary", [])
    ids = [c["id"] for c in controls]
    if len(set(ids)) != len(ids):
        raise ValueError("操作IDが重複しています")
    for control in controls:
        for field in ("id", "section", "label", "kind", "purpose", "when", "prerequisites",
                      "steps", "result", "notes", "command", "source_line"):
            if field not in control:
                raise ValueError(f"{control['id']}: {field} がありません")
    actual = (len(controls), len(dialogs), len(workflows), len(glossary))
    if actual != (116, 25, 7, 29):
        raise ValueError(f"収録件数が予定と異なります: controls/dialogs/workflows/glossary={actual}")
    warnings = []
    shots = {}
    for filename in ("screenshots.json", "diagram_manifest.json", "beginner_figure_manifest.json", "workbook_view_manifest.json"):
        for shot in normalize_shots(load_json(ROOT / filename, [])):
            name = shot.get("name") or shot.get("id") or shot.get("shot")
            if name:
                shots[name] = dict(shots.get(name, {}), **shot)
                for alias in as_list(shot.get("aliases")):
                    shots[alias] = shots[name]
    spec = load_json(ROOT / "figures.json", {})
    for filename in ("beginner_figures.json", "workbook_figures.json"):
        spec.update(load_json(ROOT / filename, {}))
    if "figures" in spec and isinstance(spec["figures"], dict):
        spec = spec["figures"]
    figures = []
    for section, entries in (spec or {}).items():
        for entry in as_list(entries):
            name = plain(entry.get("shot", ""))
            shot = shots.get(name, {})
            file = shot.get("file") or shot.get("rawfile") or shot.get("raw_file") or shot.get("path")
            file = file or entry.get("file") or entry.get("rawfile")
            path = (ROOT / file).resolve() if file else None
            relative, size, error = "", (0, 0), ""
            if path and path.is_relative_to(ROOT) and path.is_file():
                relative = path.relative_to(ROOT).as_posix()
                try:
                    size = ImageReader(str(path)).getSize()
                except Exception as exc:
                    error = "画像を読み込めません: " + str(exc)
            else:
                error = "対応する画像がまだ登録されていません。"
                path = None
            w, h = size
            crop = entry.get("crop") or [0, 0, w, h]
            if isinstance(crop, dict):
                crop = [crop[k] for k in ("x", "y", "w", "h")]
            try:
                x, y, cw, ch = map(float, crop)
                if not all(math.isfinite(v) for v in (x, y, cw, ch)):
                    raise ValueError("finite crop required")
                x, y = max(0, x), max(0, y)
                cw, ch = min(cw, w-x), min(ch, h-y)
                if cw <= 0 or ch <= 0:
                    raise ValueError("empty crop")
            except (TypeError, ValueError):
                x, y, cw, ch = 0., 0., float(w or 1), float(h or 1)
                if path:
                    warnings.append(f"{name}: 切り出し範囲が不正なため全体を使用")
            kind = entry.get("kind") or shot.get("kind") or "actual-application-screenshot"
            raw_marks = entry.get("marks") or shot.get("marks") or []
            marks = []
            for mark in raw_marks:
                control_id = mark.get("id") or mark.get("control_id") or mark.get("sourceID")
                if not control_id:
                    continue
                mx, my = mark.get("x", 0), mark.get("y", 0)
                if "badge_x" in mark:
                    mx, my = float(mark["badge_x"])+40, float(mark["badge_y"])+17
                mx, my = float(mx), float(my)
                if not x <= mx <= x+cw or not y <= my <= y+ch:
                    if kind != "source-diagram":
                        warnings.append(f"{name}: {control_id} の番号位置は切り出し範囲外")
                    continue
                if control_id not in ids:
                    warnings.append(f"{name}: カタログにない注釈ID {control_id}")
                marks.append({"id": control_id, "label": annotation_id(control_id), "x": mx, "y": my, "compact": bool(mark.get("compact"))})
            figure = Figure(len(figures)+1, section, plain(entry.get("title") or shot.get("label") or name),
                            name, path, relative, int(w), int(h), (x, y, cw, ch), marks, kind, error,
                            float(entry.get("max_width_mm", 174)))
            if error:
                warnings.append(name + ": " + error)
            figures.append(figure)
    sections = []
    for key in SECTION_NAMES:
        group = sorted([c for c in controls if c["section"] == key], key=lambda c: int(c["id"].split("_")[-1]))
        sections.append((key, SECTION_NAMES[key], group))
    return {"catalog": catalog, "controls": controls, "dialogs": dialogs, "workflows": workflows, "shots": shots,
            "glossary": glossary, "figures": figures, "sections": sections, "warnings": warnings,
            "beginner": load_json(ROOT / "beginner_content.json", {}),
            "demo": load_json(ROOT / "beginner_demo.json", {})}


def image_inventory(model):
    """Count distinct manifest source files separately from displayed crop figures."""
    actual, diagrams, workbook, documents = set(), set(), set(), set()
    for shot in model.get("shots", {}).values():
        filename = shot.get("file") or shot.get("rawfile") or shot.get("raw_file") or shot.get("path")
        if not filename:
            continue
        key = str((ROOT / filename).resolve())
        kind = shot.get("kind", "actual-application-screenshot")
        {"source-diagram": diagrams, "data-derived-workbook-view": workbook,
         "source-document-view": documents}.get(kind, actual).add(key)
    return {
        "actual_screenshots": len(actual),
        "source_diagrams": len(diagrams),
        "workbook_views": len(workbook), "source_document_views": len(documents),
        "actual_screenshot_figures": sum(f.kind == "actual-application-screenshot" for f in model["figures"]),
        "source_diagram_figures": sum(f.kind == "source-diagram" for f in model["figures"]),
    }


def image_inventory_text(model):
    counts = image_inventory(model)
    return (f"画像資料：撮影済みの実画面{counts['actual_screenshots']}枚、UI構成図{counts['source_diagrams']}枚。"
            "同じ元画像から異なる範囲を切り出して掲載する場合があり、掲載図の件数とは異なります。")


TROUBLESHOOTING = [
    ("GPUが利用できない・候補がない", "採用値・単位・原文を手入力し、原本上の根拠を指定して確認済みにします。OCRゼロ件でも必要項目は残ります。", ["review_04", "review_08", "review_11"]),
    ("寸法・向きがテンプレートと違う", "自動OCRは止めたまま、必要項目を手入力して当該文書の根拠を指定できます。代表帳票に合う新しいテンプレートを作る方法もあります。", ["worklist_09", "viewer_06"]),
    ("保存済みなのに出力できない", "保存と確認済みは別です。必須項目を確認済みにし、任意項目も確認済みか理由付き対象外にします。全件出力では未割当ページも適用または理由付き対象外に整理します。完了分だけ出す場合は、少なくとも1件の完了記録が必要です。除外対象を確認して「完了分だけ出力」を押します。", ["review_09", "review_11", "history_10", "worklist_10"]),
    ("別配置の帳票が別のシートに分かれる", "同じ名前だけでは共通の項目定義になりません。別配置のテンプレート作成時に、同じ定義・版を選び「選択した項目定義を使用」を押します。", ["setup_05", "setup_07"]),
    ("再OCRしたのに採用値が変わらない", "再OCRは候補を追加します。変更する場合は候補を採用欄へ取り込み、訂正と原本照合を行って確認済みにします。", ["review_16", "review_17"]),
    ("入力や処理結果の保存に失敗した", "画面内の未保存分を保持しています。原因を解消して保存再試行を行い、保存成功を確認します。保存に成功するまで強制終了しません。", ["review_10", "common_12"]),
    ("テンプレート草案の保存に失敗した", "確認・訂正タブの「保存再試行」は草案を保存しません。終了時の草案保存エラーはOKで画面に戻り、保存先の原因を解消してから右上の×で再び終了を試み、草案保存が成功したことを確認します。作成途中の入力を残したまま対処します。", ["setup_04", "common_12", "review_10"]),
    ("表の生成・出力履歴の保存に失敗した", "確定結果は保存済みです。生成の失敗は履歴から再出力、履歴だけの保存失敗は「出力履歴の保存を再試行」で保存します。", ["history_05", "history_06"]),
    ("中断・失敗したOCRを続けたい", "原因を解消して未完了ジョブ再開を押します。完了済み分は保持されます。表示中の記録だけ新たに読みたい場合は、この記録の範囲OCRを使います。", ["common_05", "review_17"]),
    ("テンプレートを切り替えた後の旧値を見たい", "作業一覧で対象を一つにし、変更前の結果から旧記録を編集不可で表示します。別版への切替で旧採用値は新記録へ引き継ぎません。", ["worklist_11", "worklist_09"]),
    ("旧案件・バックアップを開けない", "project.sqlite のある案件フォルダーを選びます。INCOMPLETE.txt のあるコピーは未完成です。元案件を保持し、原因を解消して移行・バックアップを再試行します。", ["common_03", "common_07", "common_14"]),
    ("CSVをExcelで開くと先頭ゼロが消える", "型を保持する用途ではXLSXを使います。CSVは交換用で、Excel側の読込時の型推測により表記が変わる場合があります。", ["worklist_14", "setup_21"]),
]


CSS = r"""
:root{--ink:#182b3c;--muted:#496272;--blue:#0955a1;--line:#cddae5;--pale:#edf5fb;--amber:#89540b}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:#f5f8fb;font:16px/1.8 'Meiryo','Yu Gothic',sans-serif}
a{color:var(--blue)}header{padding:2.3rem 3rem;background:#173a58;color:white}header p{max-width:65rem}.layout{display:grid;grid-template-columns:270px minmax(0,960px);gap:30px;max-width:1320px;margin:auto;padding:28px}
aside{position:sticky;top:12px;align-self:start;max-height:96vh;overflow:auto;background:white;border:1px solid var(--line);border-radius:10px;padding:18px}aside nav a{display:block;padding:5px 0;text-decoration:none}.search-label{display:block;font-weight:bold}input[type=search]{width:100%;padding:10px;border:1px solid #809aaf;border-radius:5px;font:inherit}#search-status{font-size:13px;color:var(--muted)}
main{min-width:0}section.chapter{margin-bottom:34px;padding:24px;background:white;border:1px solid var(--line);border-radius:12px}h1,h2,h3{line-height:1.45}h2{border-bottom:2px solid var(--blue);padding-bottom:10px}h3{font-size:19px;margin:5px 0 16px}.notice{background:var(--pale);border-left:4px solid var(--blue);padding:14px 18px}.note{background:#fff5df;border-left:4px solid #b78025;padding:12px 18px}
.control,.dialog-card,.flow-card,.trouble-card,.gloss-card{scroll-margin-top:15px;border-top:1px solid var(--line);padding:20px 0}.badge{display:inline-block;white-space:nowrap;background:var(--blue);color:white;border-radius:5px;padding:2px 8px;margin-right:8px;font-size:14px}.kind,.surface{color:var(--muted);font-size:13px}.field{margin:8px 0}.field>strong{display:inline-block;min-width:5em;color:var(--blue)}.field p{display:inline}.field ol,.field ul{margin:6px 0 6px 1.2em;padding-left:1.3em}.index-links{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.index-links a{border:1px solid var(--line);border-radius:5px;padding:3px 9px;font-size:14px}
figure{margin:22px 0}figure svg{width:100%;max-height:780px;display:block;background:#eff3f7;border:1px solid #b8c8d7;border-radius:6px}.figure-caption{margin:6px 0;font-size:14px}.evidence{display:block;font-weight:bold;color:var(--blue)}.diagram .evidence{color:var(--amber)}.figure-tools{display:flex;gap:10px;margin:8px 0}.zoom-button{padding:7px 13px;border:1px solid #809aaf;border-radius:5px;background:white;color:var(--blue);cursor:pointer;font:inherit;font-size:14px}.legend{font-size:14px;display:flex;flex-wrap:wrap;gap:8px}.figure-missing{border:1px dashed #9baab8;padding:25px;color:var(--muted)}
dialog{max-width:96vw;max-height:96vh;width:1450px;border:1px solid #526d84;border-radius:8px;padding:16px}dialog::backdrop{background:#14283fbb}.zoom-content{max-height:80vh;overflow:auto}.zoom-content svg{width:100%;min-width:700px;background:#f3f6fa}.close-zoom{float:right}.offline{font-size:14px;color:#52697c}.source-table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}.source-table td,.source-table th{border:1px solid var(--line);padding:7px;word-break:break-all;vertical-align:top}.source-table th:nth-child(1){width:15%}.source-table th:nth-child(2){width:8%}.source-table th:nth-child(3){width:77%}.hidden,[hidden]{display:none!important}
@media(max-width:950px){.layout{grid-template-columns:1fr;padding:12px;gap:12px}aside{position:static;max-height:none}aside nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 12px}header{padding:22px}section.chapter{padding:18px}}
@media print{@page{size:A4 portrait;margin:15mm}body{background:white;font-size:10pt;color:black}.layout{display:block;padding:0;max-width:none}header{background:white;color:black;padding:0}aside,.zoom-button,dialog,.figure-tools,#search-status{display:none!important}section.chapter{border:0;border-radius:0;padding:0;page-break-before:always}.control,.dialog-card,.flow-card,.trouble-card,.gloss-card{break-inside:avoid}.hidden,[hidden]{display:block!important}a{color:inherit;text-decoration:none}.badge{background:white;color:black;border:1px solid #555}figure{break-inside:avoid}figure svg{max-height:180mm}.notice,.note{border:1px solid #777;background:white}.source-table{font-size:8pt}}
"""


JS = r"""
const search=document.getElementById('manual-search');const status=document.getElementById('search-status');
function filter(){const q=search.value.normalize('NFKC').toLowerCase().trim();let n=0;document.querySelectorAll('.search-item').forEach(e=>{const hit=!q||e.textContent.normalize('NFKC').toLowerCase().includes(q);e.hidden=!hit;if(hit)n++});document.querySelectorAll('section.chapter').forEach(s=>{const cards=s.querySelectorAll('.search-item');s.hidden=!!q&&cards.length>0&&!Array.from(cards).some(c=>!c.hidden)});status.textContent=q?`${n} 件が見つかりました`:'操作名・番号・用語で検索できます'}
search.addEventListener('input',filter);document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',()=>{const target=document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));if(target&&(target.hidden||target.closest('[hidden]'))){search.value='';filter()}}));
const zoom=document.getElementById('image-zoom');document.querySelectorAll('.zoom-button[data-figure]').forEach(b=>b.addEventListener('click',()=>{const fig=document.getElementById(b.dataset.figure);const svg=fig.querySelector('svg');if(!svg)return;zoom.querySelector('.zoom-title').textContent=fig.querySelector('.figure-caption').textContent;zoom.querySelector('.zoom-content').replaceChildren(svg.cloneNode(true));if(zoom.showModal)zoom.showModal();else window.open(fig.dataset.raw,'_blank')}));document.querySelector('.close-zoom').addEventListener('click',()=>zoom.close());zoom.addEventListener('click',e=>{if(e.target===zoom)zoom.close()});zoom.querySelector('.zoom-content').addEventListener('click',e=>{if(e.target.closest('a[href^="#"]')){zoom.close();search.value='';filter()}});filter();
"""


def html_field(label, value, ordered=False):
    values = as_list(value)
    if not values:
        value_html = "なし。"
    elif isinstance(value, list):
        tag = "ol" if ordered else "ul"
        value_html = f"<{tag}>" + "".join(f"<li>{esc(v)}</li>" for v in values) + f"</{tag}>"
    else:
        value_html = "<p>" + esc(value) + "</p>"
    return f'<div class="field"><strong>{label}</strong>{value_html}</div>'


def html_figure(figure, control_map):
    caption = f"図{figure.number} {figure.title}"
    if not figure.path:
        return f'<figure><figcaption class="figure-caption">{esc(caption)}</figcaption><p class="figure-missing">{esc(figure.error)}</p></figure>'
    x, y, w, h = figure.crop
    image_url = quote(figure.relative, safe="/")
    parts = [f'<figure id="figure-{figure.number}" class="{ "diagram" if figure.kind == "source-diagram" else "screen"}" data-raw="{esc(image_url)}">',
             f'<figcaption class="figure-caption"><span class="evidence">{esc(figure.evidence_label)}</span>{esc(caption)}</figcaption>',
             f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(caption)}" style="max-width:{figure.max_width_mm:g}mm" viewBox="{x:g} {y:g} {w:g} {h:g}">',
             f'<image href="{esc(image_url)}" x="0" y="0" width="{figure.width}" height="{figure.height}"/>']
    base_font_size = max(12., min(18., w/55))
    for mark in figure.marks:
        label = mark["label"]
        if figure.kind == "source-diagram":
            parts.append(f'<a href="#{esc(mark["id"])}"><title>{esc(label)}</title><rect x="{mark["x"]-40:g}" y="{mark["y"]-17:g}" width="80" height="34" fill="transparent"/></a>')
            continue
        font_size = 10 if mark.get("compact") else base_font_size
        bw, bh = len(label)*font_size*.87+14, (14 if mark.get("compact") else font_size+10)
        cx = min(max(mark["x"], x+bw/2), x+w-bw/2)
        cy = min(max(mark["y"], y+bh/2), y+h-bh/2)
        parts.append(f'<a href="#{esc(mark["id"])}"><rect x="{cx-bw/2:g}" y="{cy-bh/2:g}" width="{bw:g}" height="{bh:g}" rx="4" fill="#0955a1" stroke="white" stroke-width="1.5"/><text x="{cx:g}" y="{cy:g}" dominant-baseline="central" text-anchor="middle" fill="white" font-family="Meiryo,Yu Gothic,sans-serif" font-size="{font_size:g}">{esc(label)}</text></a>')
    parts += ['</svg>', f'<div class="figure-tools"><button type="button" class="zoom-button" data-figure="figure-{figure.number}">画像を拡大</button><a href="{esc(image_url)}" target="_blank" rel="noopener">元画像を開く</a></div>']
    if figure.marks:
        parts.append('<div class="legend">' + "".join(
            f'<a href="#{esc(m["id"])}">{esc(m["label"])} {esc(control_title(control_map[m["id"]]) if m["id"] in control_map else "")}</a>' for m in figure.marks) + '</div>')
    parts.append('</figure>')
    return "".join(parts)


def build_html(model, target):
    controls = {c["id"]: c for c in model["controls"]}
    nav = [("quickstart", "最初の使い方")] + [(k, v) for k, v in SECTION_NAMES.items()] + [
        ("dialogs", "確認ダイアログ等"), ("workflows", "6つの操作の流れ"),
        ("troubleshooting", "困ったとき"), ("glossary", "用語"), ("version", "版情報と根拠")]
    parts = ['<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             f'<title>{esc(TITLE)}</title><style>{CSS}</style></head><body>',
             f'<header><h1>{esc(TITLE)}</h1><p>ページ別テンプレートから、原本確認・案件の表出力まで</p><p>116操作・25ダイアログ・6つの流れ・29用語</p><p>{esc(image_inventory_text(model))}</p></header>',
             '<div class="layout"><aside><label class="search-label" for="manual-search">説明書内を検索</label><input id="manual-search" type="search" placeholder="例：確認02、再OCR、対象外"><p id="search-status"></p><nav aria-label="目次">',
             ''.join(f'<a href="#{key}">{esc(title)}</a>' for key, title in nav),
             '</nav><p class="offline">外部接続は不要です。index.html と assets を同じ説明書フォルダー内に保ってください。</p></aside><main>']
    def figures(section):
        matches = [f for f in model["figures"] if f.section == section]
        return ''.join(html_figure(f, controls) for f in matches)
    first = model["workflows"][0]
    parts += [f'<section id="quickstart" class="chapter"><h2>最初の使い方</h2><p class="notice">{esc(NOTICE)}</p>',
              '<p>まず、案件作成から出力まで一通り進めます。後の章で各部品の説明を確認できます。</p>',
              figures("overview") + figures("quickstart"), html_field("操作", first["steps"], True),
              html_field("操作後", first["result"]), html_field("注意", public_notes(first)),
              '<p class="note">図の「共通02」などの番号は、本文の同じ番号の操作説明に対応します。画像内の番号を押すと説明へ移動できます。</p></section>']
    for key, title, group in model["sections"]:
        parts += [f'<section id="{key}" class="chapter"><h2>{esc(title)}</h2>', figures(key),
                  '<div class="index-links">' + ''.join(f'<a href="#{c["id"]}">{esc(annotation_id(c["id"]))}</a>' for c in group) + '</div>']
        for c in group:
            parts.append(f'<article id="{esc(c["id"])}" class="control search-item"><h3><span class="badge">{esc(annotation_id(c["id"]))}</span>{esc(control_title(c))}</h3><p class="kind">{esc(KIND_NAMES.get(c["kind"], c["kind"]))} / {"ダイアログ内" if c.get("surface") == "dialog" else "画面内"}</p>')
            for field, label in FIELDS:
                parts.append(html_field(label, public_notes(c) if field == "notes" else c.get(field), field == "steps"))
            parts.append('</article>')
        parts.append('</section>')
    parts += ['<section id="dialogs" class="chapter"><h2>確認ダイアログ等</h2>', figures("dialogs")]
    for i, dialog in enumerate(model["dialogs"], 1):
        parts.append(f'<article id="dialog-{esc(dialog["id"])}" class="dialog-card search-item"><h3>対話{i:02d} {esc(dialog["title"])}</h3>')
        parts.append(html_field("役割", dialog.get("purpose")))
        if dialog.get("when"):
            parts.append(html_field("使う場面", dialog["when"]))
        for d in dialog.get("controls", []):
            parts.append(f'<p><strong>{esc(d.get("label"))}</strong>：{esc(d.get("purpose"))}</p>')
        parts += [html_field("操作", dialog.get("steps", []), True), html_field("操作後", dialog.get("result")),
                  html_field("注意", public_notes(dialog)), '</article>']
    parts += ['</section><section id="workflows" class="chapter"><h2>6つの操作の流れ</h2>', figures("workflows")]
    for i, flow in enumerate(model["workflows"], 1):
        parts += [f'<article id="flow-{esc(flow["id"])}" class="flow-card search-item"><h3>手順{i:02d} {esc(flow["title"])}</h3>',
                  html_field("操作", flow["steps"], True), html_field("操作後", flow["result"]),
                  html_field("注意", public_notes(flow)), '</article>']
    parts += ['</section><section id="troubleshooting" class="chapter"><h2>困ったとき</h2>']
    for i, (title, text, refs) in enumerate(TROUBLESHOOTING, 1):
        parts += [f'<article id="trouble-{i}" class="trouble-card search-item"><h3>{esc(title)}</h3><p>{esc(text)}</p><p>参照：',
                  ' / '.join(f'<a href="#{r}">{esc(annotation_id(r))}</a>' for r in refs), '</p></article>']
    parts += ['</section><section id="glossary" class="chapter"><h2>用語</h2>']
    for i, term in enumerate(model["glossary"], 1):
        parts.append(f'<article id="term-{i}" class="gloss-card search-item"><h3>{esc(term["term"])}</h3><p>{esc(term["definition"])}</p></article>')
    parts += ['</section><section id="version" class="chapter"><h2>版情報と根拠</h2>', html_version(model), '</section></main></div>',
              '<dialog id="image-zoom"><button class="zoom-button close-zoom" type="button">閉じる</button><p class="zoom-title"></p><div class="zoom-content"></div></dialog>',
              f'<script>{JS}</script></body></html>']
    target.write_text(''.join(parts), encoding="utf-8")


def version_lines(model):
    cat = model["catalog"]
    return ["対象版：DW-Workbench v0.2.0 ローカル検証候補。",
            "収録：116操作、25ダイアログ、6つの操作の流れ、29用語。",
            "図の出典：実画面は合成サンプルで撮影。UI構成図はソースから作成し、配置の目安として表示。",
            image_inventory_text(model),
            "原本となるコード：" + plain(cat.get("source_file")),
            "コード SHA256：" + plain(cat.get("source_sha256")),
            "カタログ作成方法：" + plain(cat.get("method"))]


def html_version(model):
    out = ['<p>' + '</p><p>'.join(map(esc, version_lines(model))) + '</p>',
           '<details><summary>操作とソースの対応（開発・検証用）</summary><table class="source-table"><thead><tr><th>操作番号</th><th>行</th><th>呼び出す処理</th></tr></thead><tbody>']
    for c in model["controls"]:
        dev_notes = [n for n in c["notes"] if DEV_NOTE.search(plain(n))]
        out.append(f'<tr><td>{esc(annotation_id(c["id"]))}</td><td>{c["source_line"]}</td><td>{esc(c["command"])}' +
                   (('<br>' + '<br>'.join(map(esc, dev_notes))) if dev_notes else '') + '</td></tr>')
    out.append('</tbody></table></details><h3>入力ファイルの照合情報</h3>')
    for name in ("controls.json", "dialogs.json", "screenshots.json", "diagram_manifest.json", "figures.json"):
        path = ROOT / name
        if path.is_file():
            out.append(f'<p class="offline">{esc(name)}：SHA256 {sha256(path)}</p>')
    return ''.join(out)


def japanese_font(requested=None):
    candidates = [Path(requested)] if requested else [Path(os.environ.get("WINDIR", "Windows")) / "Fonts" / "meiryo.ttc", Path(os.environ.get("WINDIR", "Windows")) / "Fonts" / "msgothic.ttc"]
    errors = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("ManualJapanese", str(path), subfontIndex=0))
            pdfmetrics.registerFontFamily("ManualJapanese", normal="ManualJapanese", bold="ManualJapanese", italic="ManualJapanese", boldItalic="ManualJapanese")
            return "ManualJapanese", str(path)
        except Exception as exc:
            errors.append(str(path) + ": " + str(exc))
    raise RuntimeError("日本語TTFontを登録できません。msgothic.ttc または meiryo.ttc を指定してください。 " + '; '.join(errors))


class CroppedFigure(Flowable):
    """Paint the unmodified full PNG behind a clipped crop, with vector badges."""
    def __init__(self, figure, font):
        super().__init__()
        self.figure, self.font = figure, font
        self.scale = 1.

    def wrap(self, available_width, available_height):
        _, _, width, height = self.figure.crop
        if self.figure.section == "overview":
            available_width *= .82
        available_width = min(available_width, self.figure.max_width_mm*mm)
        self.scale = min(available_width/width, 165*mm/height)
        self.width, self.height = width*self.scale, height*self.scale
        return self.width, self.height

    def draw(self):
        figure, canvas = self.figure, self.canv
        x, y, width, height = figure.crop
        s = self.scale
        canvas.saveState()
        path = canvas.beginPath()
        path.rect(0, 0, self.width, self.height)
        canvas.clipPath(path, stroke=0, fill=0)
        canvas.drawImage(str(figure.path), -x*s, self.height-(figure.height-y)*s,
                         width=figure.width*s, height=figure.height*s, mask="auto")
        for mark in ([] if figure.kind == "source-diagram" else figure.marks):
            label = mark["label"]
            font_size = 6.5 if mark.get("compact") else 7.5
            badge_width = pdfmetrics.stringWidth(label, self.font, font_size)+8
            badge_height = 10 if mark.get("compact") else 13.
            mx, my = (mark["x"]-x)*s, self.height-(mark["y"]-y)*s
            mx = min(max(mx, badge_width/2), self.width-badge_width/2)
            my = min(max(my, badge_height/2), self.height-badge_height/2)
            canvas.setFillColor(colors.HexColor("#0955a1"))
            canvas.setStrokeColor(colors.white)
            canvas.setLineWidth(.6)
            canvas.roundRect(mx-badge_width/2, my-badge_height/2, badge_width, badge_height, 2, stroke=1, fill=1)
            canvas.setFillColor(colors.white)
            canvas.setFont(self.font, font_size)
            canvas.drawCentredString(mx, my-font_size*.35, label)
        canvas.restoreState()
        canvas.setStrokeColor(colors.HexColor("#b8c8d7"))
        canvas.rect(0, 0, self.width, self.height, stroke=1, fill=0)


class ManualDoc(BaseDocTemplate):
    def __init__(self, target, font):
        super().__init__(str(target), pagesize=A4, leftMargin=17*mm, rightMargin=17*mm,
                         topMargin=18*mm, bottomMargin=18*mm, title=TITLE,
                         author="DW-Workbench 操作説明", allowSplitting=1)
        self.jp_font = font
        self.running_chapter = ""
        self.page_map = {}
        self.previous_page_map = {}
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="manual", frames=[frame], onPageEnd=self.decorate))

    def beforeDocument(self):
        # multiBuild starts another pass; the cover has no previous chapter.
        self.running_chapter = ""
        self.previous_page_map = self.page_map.copy()
        self.page_map = {}

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFont(self.jp_font, 8)
        canvas.setFillColor(colors.HexColor("#496272"))
        canvas.drawString(self.leftMargin, A4[1]-11*mm, "DW-Workbench v0.2.0")
        canvas.drawRightString(A4[0]-self.rightMargin, A4[1]-11*mm, self.running_chapter[:35])
        canvas.drawCentredString(A4[0]/2, 9*mm, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        bookmark = getattr(flowable, "bookmark", None)
        if bookmark:
            self.canv.bookmarkPage(bookmark)
            self.page_map[bookmark] = self.page
            if getattr(flowable, "operation_outline", False):
                self.canv.addOutlineEntry(flowable.getPlainText(), bookmark, level=1, closed=True)
        if getattr(flowable, "chapter_name", None):
            self.running_chapter = flowable.chapter_name
        level = getattr(flowable, "toc_level", None)
        if level is not None:
            text = flowable.getPlainText()
            if level == 0:
                self.running_chapter = text
            self.notify("TOCEntry", (level, text, self.page, bookmark))
            if bookmark:
                self.canv.addOutlineEntry(text, bookmark, level=level, closed=True)


def pdf_styles(font):
    base = dict(fontName=font, wordWrap="CJK", allowWidows=0, allowOrphans=0)
    return {
        "body": ParagraphStyle("BodyJP", fontSize=10, leading=15, spaceAfter=6, **base),
        "fieldlabel": ParagraphStyle("FieldLabelJP", fontSize=10, leading=15, spaceAfter=3, keepWithNext=1, **base),
        "kind": ParagraphStyle("KindJP", fontSize=8.3, leading=12, spaceAfter=4, keepWithNext=1, **base),
        "small": ParagraphStyle("SmallJP", fontSize=8.3, leading=12, spaceAfter=4, **base),
        "title": ParagraphStyle("TitleJP", fontSize=24, leading=35, spaceAfter=16, **base),
        "h1": ParagraphStyle("ChapterJP", fontSize=18, leading=26, textColor=colors.HexColor("#0955a1"), spaceAfter=14, keepWithNext=1, **base),
        "h2": ParagraphStyle("ItemJP", fontSize=12, leading=18, textColor=colors.HexColor("#0955a1"), spaceBefore=9, spaceAfter=7, keepWithNext=1, **base),
        "term": ParagraphStyle("TermJP", fontSize=11, leading=16, textColor=colors.HexColor("#0955a1"), spaceBefore=5, spaceAfter=4, keepWithNext=1, **base),
        "caption": ParagraphStyle("CaptionJP", fontSize=9, leading=14, spaceBefore=8, spaceAfter=6, keepWithNext=1, **base),
        "toc": ParagraphStyle("TOCJP", fontSize=10, leading=17, leftIndent=4, firstLineIndent=-4, rightIndent=24, spaceBefore=4, **base),
        "table": ParagraphStyle("TableJP", fontSize=8, leading=11.5, spaceAfter=2, **base),
    }


def build_pdf(model, target, requested_font=None):
    font, font_path = japanese_font(requested_font)
    styles = pdf_styles(font)
    doc = ManualDoc(target, font)
    story = []
    control_map = {c["id"]: c for c in model["controls"]}
    def paragraph(text, style="body"):
        text = esc(text).replace("\n", "<br/>")
        for dash in ("\u2011", "\u2013", "\u2014"):
            text = text.replace(dash, "-")
        return Paragraph(text, styles[style])
    def chapter(key, title):
        story.append(PageBreak())
        heading = paragraph(title, "h1")
        heading.bookmark, heading.chapter_name = key, title
        if key != "contents":
            heading.toc_level = 0
        story.append(heading)
    def item_heading(text, bookmark=None, style="h2"):
        heading = paragraph(text, style)
        if bookmark:
            heading.bookmark = bookmark
        story.append(heading)
    def field(label, value, ordered=False):
        values = as_list(value)
        if label == "注意" and not values:
            return
        if not values:
            values = ["なし。"]
        if isinstance(value, list):
            story.append(Paragraph(f'<font color="#0955a1">{label}</font>', styles["fieldlabel"]))
            for i, text in enumerate(values, 1):
                prefix = f"{i}. " if ordered else "・"
                story.append(paragraph(prefix + plain(text)))
        else:
            story.append(Paragraph(f'<font color="#0955a1">{label}</font>　{esc(value or "なし。")}', styles["body"]))
    def figures(section):
        for figure in model["figures"]:
            if figure.section != section:
                continue
            caption = paragraph(f"図{figure.number} {figure.title}\n{figure.evidence_label}", "caption")
            if figure.path:
                cropped = CroppedFigure(figure, font)
                figure_block = [caption, cropped]
                if figure.marks and figure.kind != "source-diagram":
                    labels = [m["label"] + " " + (control_title(control_map[m["id"]]) if m["id"] in control_map else "") for m in figure.marks]
                    figure_block.append(paragraph("図の番号：" + " / ".join(labels), "small"))
                figure_block.append(Spacer(1, 5*mm))
                story.append(KeepTogether(figure_block))
            else:
                story.extend([caption, paragraph(figure.error, "small")])
    story += [Spacer(1, 28*mm), paragraph(TITLE, "title"),
              paragraph("ページ別テンプレートから、原本確認・案件の表出力まで"),
              paragraph("116操作・25ダイアログ・6つの流れ・29用語"),
              paragraph(image_inventory_text(model)), Spacer(1, 10*mm), paragraph(NOTICE)]
    chapter("contents", "目次")
    toc = TableOfContents()
    toc.levelStyles = [styles["toc"]]
    story.append(toc)
    chapter("quickstart", "最初の使い方")
    story.append(paragraph("最初に一通り作業します。図の番号は後の各操作説明に対応します。"))
    figures("overview")
    figures("quickstart")
    first = model["workflows"][0]
    field("操作", first["steps"], True)
    field("操作後", first["result"])
    field("注意", public_notes(first))
    for key, title, group in model["sections"]:
        chapter(key, title)
        figures(key)
        for c in group:
            card_start = len(story)
            item_heading(annotation_id(c["id"]) + "　" + control_title(c), c["id"])
            story.append(paragraph(KIND_NAMES.get(c["kind"], c["kind"]) + " / " + ("ダイアログ内" if c.get("surface") == "dialog" else "画面内"), "kind"))
            for key_field, label in FIELDS:
                field(label, public_notes(c) if key_field == "notes" else c.get(key_field), key_field == "steps")
            story.append(Spacer(1, 4*mm))
            if c is group[-1]:
                final_card = story[card_start:]
                story[card_start:] = [KeepTogether(final_card)]
    chapter("dialogs", "確認ダイアログ等")
    figures("dialogs")
    for i, dialog in enumerate(model["dialogs"], 1):
        item_heading(f"対話{i:02d}　{dialog['title']}", "dialog-" + dialog["id"])
        field("役割", dialog.get("purpose"))
        if dialog.get("when"):
            field("使う場面", dialog["when"])
        for d in dialog.get("controls", []):
            story.append(paragraph(plain(d.get("label")) + "：" + plain(d.get("purpose"))))
        field("操作", dialog.get("steps", []), True)
        field("操作後", dialog.get("result"))
        field("注意", public_notes(dialog))
    chapter("workflows", "6つの操作の流れ")
    figures("workflows")
    for i, flow in enumerate(model["workflows"], 1):
        item_heading(f"手順{i:02d}　{flow['title']}", "flow-" + flow["id"])
        field("操作", flow["steps"], True)
        field("操作後", flow["result"])
        field("注意", public_notes(flow))
    chapter("troubleshooting", "困ったとき")
    for i, (title, text, refs) in enumerate(TROUBLESHOOTING, 1):
        item_heading(title, f"trouble-{i}")
        story.append(paragraph(text))
        story.append(paragraph("参照：" + " / ".join(annotation_id(r) for r in refs), "small"))
    chapter("glossary", "用語")
    for i, term in enumerate(model["glossary"], 1):
        item_heading(term["term"], f"term-{i}", "term")
        story.append(paragraph(term["definition"]))
    chapter("version", "版情報と根拠")
    story.extend(paragraph(line, "small") for line in version_lines(model))
    story.append(paragraph("以下は開発・検証用の参照です。操作する順序を示すものではありません。", "small"))
    rows = [[paragraph("操作番号", "table"), paragraph("行", "table"), paragraph("呼び出す処理", "table")]]
    for c in model["controls"]:
        dev_notes = [n for n in c["notes"] if DEV_NOTE.search(plain(n))]
        text = plain(c["command"]) + ("\n" + "\n".join(map(plain, dev_notes)) if dev_notes else "")
        rows.append([paragraph(annotation_id(c["id"]), "table"), paragraph(c["source_line"], "table"), paragraph(text, "table")])
    table = LongTable(rows, colWidths=[30*mm, 11*mm, doc.width-41*mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf5fb")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cddae5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    item_heading("入力ファイルの照合情報")
    for name in ("controls.json", "dialogs.json", "screenshots.json", "diagram_manifest.json", "figures.json"):
        path = ROOT / name
        if path.is_file():
            story.append(paragraph(name + "：SHA256 " + sha256(path), "small"))
    doc.multiBuild(story)
    return font_path


def main():
    from manual_revision import build_html, build_pdf, order_figures
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html-only", action="store_true", help="HTMLのみ生成する")
    parser.add_argument("--pdf-only", action="store_true", help="PDFのみ生成する")
    parser.add_argument("--font", help="日本語TTF/TTC。TTCはsubfontIndex=0を使う")
    args = parser.parse_args()
    if args.html_only and args.pdf_only:
        parser.error("--html-only と --pdf-only は同時に指定できません")
    model = order_figures(load_model())
    outputs = []
    font_path = None
    if not args.pdf_only:
        path = own_output(ROOT / "index.html")
        build_html(model, path)
        outputs.append({"path": path.name, "sha256": sha256(path)})
    if not args.html_only:
        path = own_output(ROOT / PDF_NAME)
        font_path = build_pdf(model, path, args.font)
        outputs.append({"path": path.name, "sha256": sha256(path)})
    report = {
        "controls": len(model["controls"]), "dialogs": len(model["dialogs"]),
        "workflows": len(model["workflows"]), "glossary": len(model["glossary"]),
        "figures": len(model["figures"]), **image_inventory(model),
        "image_count_meaning": "actual_screenshots/source_diagrams はmanifestの元画像枚数、*_figures は掲載する切り出し図の件数。",
        "warnings": model["warnings"], "japanese_font": Path(font_path).name if font_path else None, "outputs": outputs,
        "images_modified": False, "visual_qa": "生成担当が全ページを描画して最終確認する必要があります。",
    }
    own_output(ROOT / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
