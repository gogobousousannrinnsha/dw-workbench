"""Tk desktop. Source coordinates are independent of canvas zoom and scrolling."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import copy
import json
import queue
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from .application import Workbench
from . import __version__
from .domain import (Anchor, ExtractionProfile, FieldSchema, ResultSchema, RuleError, StaleRevision, Status, identifier,
    profile_from, source_from, state_from, schema_from)
from .library import TemplateLibrary
from .workers import WorkerClient, capabilities
from .ui_guidance import WorkflowUI

LABELS = {Status.MISSING: "未取得", Status.PENDING: "未確認", Status.ACCEPTED: "確認済み", Status.DEFERRED: "保留", Status.NOT_APPLICABLE: "対象外"}
KINDS = {"text": "文字列", "decimal": "数値"}
MODES = {"page": "ページごと（一ページ一行）", "document": "文書全体（一文書一行）"}


def target_pages(choice, selected, page_count, expression=""):
    """Resolve the visible bulk selector; reject typos rather than silently skipping pages."""
    if choice == "選択ページ":
        result = sorted(set(int(p) for p in selected))
    elif choice == "全ページ":
        result = list(range(1, page_count + 1))
    elif choice == "奇数ページ":
        result = list(range(1, page_count + 1, 2))
    elif choice == "偶数ページ":
        result = list(range(2, page_count + 1, 2))
    elif choice == "ページ範囲":
        import re
        result = set()
        for part in expression.replace("、", ",").split(","):
            match = re.fullmatch(r"\s*(\d+)\s*(?:[-〜～]\s*(\d+)\s*)?", part)
            if not match:
                raise RuleError("ページ範囲は 2-10 または 1,3,5-8 のように入力してください")
            start, end = int(match[1]), int(match[2] or match[1])
            if start > end:
                raise RuleError("ページ範囲の開始は終了以下にしてください")
            if start < 1 or end > page_count:
                raise RuleError(f"ページは1〜{page_count}の範囲で指定してください")
            result.update(range(start, end + 1))
        result = sorted(result)
    else:
        raise RuleError("適用対象を選択してください")
    if not result or min(result) < 1 or max(result) > page_count:
        raise RuleError("対象ページを選択してください")
    return result


class Window(WorkflowUI):
    def __init__(self, root, portable, project=None):
        self.root, self.portable = root, Path(portable).resolve()
        self.app = None
        self.library = TemplateLibrary(self.portable)
        self.source = self.record = self.profile = self.frozen = None
        self.field_id = None
        self.page = 1
        self.scale = 1
        self.image = self.photo = None
        self.anchor = None
        self.draft_fields, self.draft_regions = [], {}
        self.draft_id, self.draft_version = identifier(), 1
        self.draft_source = None
        self.draft_page = 1
        self.draft_schema = None
        self.draft_dirty = False
        self.draft_scope_value = "ページ用"
        self.draft_timer = None
        self.refreshing = False
        self.loading = False
        self.dirty = False
        self.save_timer = None
        self.tasks = []
        self.active_job = None
        self.callback_queue = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.clients = {}
        self.closing = False
        self.background = 0
        self.pending_results = {}
        self.pending_exports = {}
        self.exporting_ids = set()
        self.ledger_dialog = None
        self.batch_dialog = None
        self.project_verified = True
        self.validation_busy = False
        self.root.title(f"DW-Workbench v{__version__} — ローカル検証候補")
        self.root.geometry("1380x900")
        self.root.minsize(1000, 650)
        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(75, self.poll)
        self.async_call(lambda: capabilities(self.portable), self.show_capabilities)
        if project:
            self.open_project(project)

    def build(self):
        self.build_workflow()
        split = ttk.Panedwindow(self.root, orient="horizontal")
        split.pack(fill="both", expand=True, padx=5)
        left, right = ttk.Frame(split), ttk.Frame(split)
        split.add(left, weight=3)
        split.add(right, weight=2)
        nav = ttk.Frame(left)
        nav.pack(fill="x")
        ttk.Button(nav, text="前ページ", command=lambda: self.safe(lambda: self.navigate(-1))).pack(side="left")
        ttk.Button(nav, text="次ページ", command=lambda: self.safe(lambda: self.navigate(1))).pack(side="left")
        self.zoom = tk.StringVar(value="ページに合わせる")
        combo = ttk.Combobox(nav, textvariable=self.zoom, values=("ページに合わせる", "50%", "100%", "150%", "200%"), state="readonly", width=18)
        combo.pack(side="left", padx=5)
        combo.bind("<<ComboboxSelected>>", lambda e: self.show_image())
        pagebar = ttk.Frame(left)
        pagebar.pack(fill="x")
        ttk.Button(pagebar, text="選択範囲を拡大", command=self.focus_anchor).pack(side="right")
        self.page_label = ttk.Label(pagebar, text="原本未選択", wraplength=400)
        self.page_label.pack(side="left", padx=5, fill="x", expand=True)
        pagebar.bind("<Configure>", lambda e: self.page_label.configure(wraplength=max(150,e.width-130)))
        canvas_frame = ttk.Frame(left)
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg="#404449", highlightthickness=0)
        vscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        hscroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta/120), "units"))
        self.canvas.bind("<Configure>", lambda e: self.show_image() if self.image is not None and self.zoom.get() == "ページに合わせる" else None)
        ttk.Label(left, text="左の原本画像をドラッグして、読み取り範囲を指定します。", padding=4).pack(fill="x")
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        self.list_tab, self.setup_tab, self.review_tab, self.output_tab, self.history_tab, self.library_tab = (ttk.Frame(self.tabs, padding=8) for _ in range(6))
        for frame, label in ((self.list_tab, "文書"), (self.setup_tab, "範囲"), (self.review_tab, "確認"), (self.output_tab, "出力"), (self.history_tab, "履歴"), (self.library_tab, "共通")):
            self.tabs.add(frame, text=label)
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.safe(self.tab_changed))
        list_content = self.scrollable_content(self.list_tab)
        ttk.Label(list_content, text="1 文書を登録・選択", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w")
        self.action_button(list_content, "add", "XDW文書を追加する", self.add_sources).pack(fill="x", pady=4)
        self.document_list = self.make_table(list_content, columns=("name", "status"), show="headings", height=4, selectmode="browse")
        self.document_list.heading("name", text="文書")
        self.document_list.heading("status", text="確認状態")
        self.document_list.column("name", width=240)
        self.document_list.column("status", width=145)
        self.document_list.bind("<<TreeviewSelect>>", lambda e: self.safe(self.select_source))
        ttk.Label(list_content, text="2 ページと読み取りテンプレートを選ぶ", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w", pady=(8,0))
        self.action_button(list_content, "bulk", "複数文書へ一括適用", self.open_bulk_templates).pack(fill="x", pady=4)
        modebar = ttk.Frame(list_content)
        modebar.pack(fill="x", pady=5)
        ttk.Label(modebar, text="結果をまとめる単位").pack(side="left")
        self.mode_choice = ttk.Combobox(modebar, values=list(MODES.values()), state="readonly", width=29)
        self.mode_choice.pack(side="left", padx=5)
        self.mode_choice.bind("<<ComboboxSelected>>", lambda e: self.safe(self.change_mode))
        self.mode_hint = ttk.Label(list_content, text="文書を選択してください", wraplength=400)
        self.mode_hint.pack(anchor="w")
        self.page_list = self.make_table(list_content, columns=("page", "template", "status"), show="headings", height=5, selectmode="extended")
        for name, title, width in (("page", "ページ", 55), ("template", "読取設定", 180), ("status", "状態", 145)):
            self.page_list.heading(name, text=title)
            self.page_list.column(name, width=width)
        self.page_list.bind("<<TreeviewSelect>>", lambda e: self.safe(self.select_page))
        self.page_list.bind("<Double-1>", lambda e: self.tabs.select(self.review_tab))
        targets = ttk.Frame(list_content)
        targets.pack(fill="x", pady=3)
        ttk.Label(targets, text="対象").pack(side="left")
        self.target_choice = ttk.Combobox(targets, values=("選択ページ", "全ページ", "ページ範囲", "奇数ページ", "偶数ページ"), state="readonly", width=15)
        self.target_choice.set("選択ページ")
        self.target_choice.pack(side="left", padx=4)
        self.target_expression = ttk.Entry(targets, width=12)
        self.target_expression.pack(side="left")
        ttk.Label(targets, text="例: 2-10,12").pack(side="left", padx=4)
        ttk.Label(list_content, text="使う読み取りテンプレート").pack(anchor="w", pady=(5, 0))
        self.profile_choice = ttk.Combobox(list_content, state="readonly")
        self.profile_choice.pack(fill="x")
        self.profile_choice.bind("<<ComboboxSelected>>", lambda e: self.refresh_workflow())
        self.target_choice.bind("<<ComboboxSelected>>", lambda e: self.refresh_workflow())
        self.target_expression.bind("<KeyRelease>", lambda e: self.refresh_workflow())
        self.action_button(list_content, "apply", "選んだページへ読取設定を適用", self.apply_profile).pack(fill="x", pady=4)
        self.action_button(list_content, "new_template", "読み取り範囲を新しく作る", self.new_profile).pack(fill="x")
        ttk.Button(list_content, text="共通テンプレートから取り込む", command=lambda: self.tabs.select(self.library_tab)).pack(fill="x", pady=3)
        extras = ttk.Frame(list_content)
        extras.pack(fill="x", pady=4)
        ttk.Button(extras, text="ページを理由付きで対象外に", command=lambda: self.safe(self.exclude_pages)).pack(side="left", padx=2)
        ttk.Button(extras, text="設定変更前の結果を見る", command=lambda: self.safe(self.open_assignment_history)).pack(side="left", padx=2)
        ttk.Label(list_content, text="3 OCRで文字の候補を作る", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w", pady=(8,0))
        self.selected_ocr_button = self.action_button(list_content, "ocr", "選択したページの文字を読み取る", self.run_selected_ocr)
        self.selected_ocr_button.pack(fill="x", pady=4)
        ttk.Label(list_content, text="OCRは候補を追加します。値の採用と確認は別操作です。手入力でも続けられます。", wraplength=400).pack(anchor="w")
        ttk.Button(list_content, text="4 原文の確認・訂正へ進む", command=lambda: self.safe(lambda: self.select_step(4))).pack(fill="x", pady=5)
        setup_content = self.scrollable_content(self.setup_tab)
        self.setup_name = tk.StringVar()
        self.setup_name.trace_add("write", lambda *a: self.draft_changed())
        ttk.Label(setup_content, text="テンプレート名").pack(anchor="w")
        ttk.Entry(setup_content, textvariable=self.setup_name).pack(fill="x")
        setupbar = ttk.Frame(setup_content)
        setupbar.pack(fill="x", pady=5)
        ttk.Label(setupbar, text="読み取り単位").pack(side="left")
        self.setup_scope = ttk.Combobox(setupbar, values=("ページ用", "文書全体用"), state="readonly", width=14)
        self.setup_scope.set("ページ用")
        self.setup_scope.pack(side="left", padx=5)
        self.setup_scope.bind("<<ComboboxSelected>>", lambda e: self.safe(self.change_draft_scope))
        self.draft_label = ttk.Label(setup_content, text="「文書」画面で代表文書・ページを選択してください", wraplength=480)
        self.draft_label.pack(anchor="w")
        ttk.Label(setup_content, text="出力する項目のまとまり（項目定義）").pack(anchor="w", pady=(6, 0))
        self.schema_choice = ttk.Combobox(setup_content, state="readonly")
        self.schema_choice.pack(fill="x")
        self.schema_name = tk.StringVar()
        self.schema_name.trace_add("write", lambda *a: self.draft_changed())
        ttk.Label(setup_content, text="項目定義の名前").pack(anchor="w")
        ttk.Entry(setup_content, textvariable=self.schema_name).pack(fill="x")
        schemabar = ttk.Frame(setup_content)
        schemabar.pack(fill="x", pady=3)
        ttk.Button(schemabar, text="選択した項目定義を使用", command=lambda: self.safe(self.use_schema)).pack(side="left")
        ttk.Button(schemabar, text="新しい項目定義にする", command=lambda: self.safe(self.fork_schema)).pack(side="left", padx=4)
        self.setup_list = self.make_table(setup_content, columns=("name", "type", "region"), show="headings", height=9)
        for name, title in (("name", "項目"), ("type", "型・必須"), ("region", "ページ・範囲")):
            self.setup_list.heading(name, text=title)
            self.setup_list.column(name, width=160)
        self.setup_list.bind("<<TreeviewSelect>>", self.select_draft_field)
        buttons = ttk.Frame(setup_content)
        buttons.pack(fill="x")
        for label, command in (("追加", self.add_draft_field), ("編集", self.edit_draft_field), ("削除", self.delete_draft_field), ("↑", lambda: self.move_draft_field(-1)), ("↓", lambda: self.move_draft_field(1)), ("登録版を改訂", self.revise_profile)):
            ttk.Button(buttons, text=label, command=lambda c=command: self.safe(c)).pack(side="left", padx=2)
        ttk.Label(setup_content, text="項目を選び、原本上で値の範囲をドラッグします。上から順に出力します。\n項目の変更は新しい定義版になります。範囲だけの変更は同じ定義を使います。", wraplength=480).pack(anchor="w", pady=8)
        ttk.Button(setup_content, text="テンプレートを案件へ登録", command=lambda: self.safe(self.save_profile)).pack(fill="x")
        ttk.Button(setup_content, text="この草案を破棄", command=lambda: self.safe(self.discard_draft)).pack(fill="x", pady=4)
        review_footer = ttk.Frame(self.review_tab)
        review_footer.pack(side="bottom", fill="x", pady=(5,0))
        self.edit_buttons = []
        self.accept_button = self.action_button(review_footer, "accept", "この項目を確認済みにする  Ctrl+Enter", self.accept)
        self.accept_button.pack(fill="x")
        self.edit_buttons.append(self.accept_button)
        self.action_button(review_footer, "next_unfinished", "次の未完了項目へ（案件全体）", self.next_unfinished).pack(fill="x", pady=3)
        ttk.Button(review_footer, text="出力へ進む（結果の確定は次の画面）", command=lambda: self.safe(lambda: self.select_step(5))).pack(fill="x")
        review_content = self.scrollable_content(self.review_tab)
        ttk.Label(review_content, text="4 原文を見て、値と範囲を確認", font=("Yu Gothic UI",10,"bold")).pack(anchor="w")
        self.review_list = self.make_table(review_content, columns=("name", "value", "status"), show="headings", height=5)
        for name, title in (("name", "項目"), ("value", "採用値"), ("status", "状態")):
            self.review_list.heading(name, text=title)
            self.review_list.column(name, width=130)
        self.review_list.bind("<<TreeviewSelect>>", lambda e: self.safe(self.select_field))
        self.field_label = ttk.Label(review_content, text="項目を選択してください",wraplength=400)
        self.field_label.pack(anchor="w", pady=5)
        self.vars = {k: tk.StringVar() for k in ("value", "unit", "raw", "reason")}
        self.entries = []
        for key, label in (("value", "出力する値（採用値）"), ("unit", "単位"), ("raw", "原文の文字表記"), ("reason", "保留・対象外にする理由")):
            ttk.Label(review_content, text=label).pack(anchor="w")
            entry = ttk.Entry(review_content, textvariable=self.vars[key])
            entry.pack(fill="x")
            self.entries.append(entry)
            self.vars[key].trace_add("write", self.changed)
        self.anchor_label = ttk.Label(review_content, text="根拠未指定", wraplength=480)
        self.anchor_label.pack(anchor="w", pady=5)
        self.save_label = ttk.Label(review_content, text="")
        self.save_label.pack(anchor="w")
        review_buttons = ttk.Frame(review_content)
        review_buttons.pack(fill="x", pady=5)
        for label, command in (("入力の保存を再試行", self.retry_saves), ("理由を付けて保留", lambda: self.mark(Status.DEFERRED)), ("この項目を対象外に", lambda: self.mark(Status.NOT_APPLICABLE))):
            b = ttk.Button(review_buttons, text=label, command=lambda c=command: self.safe(c))
            b.pack(side="left", padx=2)
            self.edit_buttons.append(b)
        self.candidate_list = ttk.Combobox(review_content, state="readonly")
        self.candidate_list.pack(fill="x", pady=4)
        self.candidate_count_label = ttk.Label(review_content, text="候補0件")
        self.candidate_count_label.pack(anchor="w")
        b = ttk.Button(review_content, text="OCR候補を入力欄に使う（確認はまだ）", command=lambda: self.safe(self.adopt))
        b.pack(fill="x")
        self.edit_buttons.append(b)
        b = self.action_button(review_content, "ocr", "この記録の文字を読み直す（候補を追加）", self.run_ocr)
        b.pack(fill="x", pady=5)
        self.edit_buttons.append(b)
        ttk.Label(review_content, text="入力は自動保存されます。保存しただけでは確認済みになりません。変更した項目は再確認が必要です。", wraplength=400).pack(anchor="w", pady=6)
        output_content = self.scrollable_content(self.output_tab)
        ttk.Label(output_content, text="5 確認済み結果を確定してExcelへ", font=("Yu Gothic UI",10,"bold")).pack(anchor="w",pady=4)
        ttk.Label(output_content, text="確定すると、その時点の値と原本の範囲を保存します。後で訂正しても過去の確定結果は変わりません。ExcelとCSVを新しいファイルへ出力します。", wraplength=400).pack(fill="x")
        self.finalize_button = self.action_button(output_content, "finalize", "結果を確定してExcel／CSV出力", self.finalize)
        self.finalize_button.pack(fill="x", pady=7)
        self.output_reason = tk.StringVar()
        ttk.Label(output_content, textvariable=self.output_reason,wraplength=400).pack(fill="x")
        ttk.Button(output_content, text="未完了を確認して作業へ戻る",command=lambda:self.safe(self.next_unfinished)).pack(fill="x",pady=5)
        ttk.Separator(output_content).pack(fill="x",pady=12)
        ttk.Label(output_content,text="6 台帳と照合して原文へ注釈",font=("Yu Gothic UI",10,"bold")).pack(anchor="w")
        ttk.Label(output_content,text="台帳の条件で対象を選び、原文プレビューを確認します。最後に、原本のコピーへ塗りなしの枠を追加したXDWを出力します。",wraplength=400).pack(fill="x",pady=4)
        self.ledger_entry_button = self.action_button(output_content,"ledger","台帳を選び、照合プレビューへ進む",self.open_ledger)
        self.ledger_entry_button.pack(fill="x",pady=7)
        self.ledger_reason = tk.StringVar()
        ttk.Label(output_content,textvariable=self.ledger_reason,wraplength=400).pack(fill="x")
        ttk.Button(output_content,text="確定結果・出力履歴を見る",command=lambda:self.tabs.select(self.history_tab)).pack(fill="x",pady=9)
        ttk.Button(output_content,text="案件の出力フォルダーを開く",command=lambda:self.safe(self.open_exports)).pack(fill="x")
        history_content = self.scrollable_content(self.history_tab)
        self.history_list = self.make_table(history_content, columns=("date", "count", "status"), show="headings", height=8)
        for name, title in (("date", "確定日時 UTC"), ("count", "対象件数"), ("status", "出力状況")):
            self.history_list.heading(name, text=title)
            self.history_list.column(name, width=160)
        self.action_button(history_content,"history_view","選んだ確定結果の原文を見る",self.open_history).pack(fill="x", pady=4)
        self.history_record = ttk.Combobox(history_content, state="readonly")
        self.history_record.pack(fill="x", pady=4)
        self.history_record.bind("<<ComboboxSelected>>", lambda e: self.safe(self.select_history_record))
        self.history_list.bind("<<TreeviewSelect>>",lambda e:self.refresh_workflow())
        self.action_button(history_content,"history_export","失敗・未生成のExcel／CSVを再出力",self.retry_export).pack(fill="x", pady=4)
        self.action_button(history_content,"ledger","この案件の確定結果を台帳と照合",self.open_ledger).pack(fill="x", pady=4)
        ttk.Button(history_content, text="出力履歴の保存を再試行", command=lambda: self.safe(self.retry_saves)).pack(fill="x", pady=4)
        ttk.Button(history_content, text="出力フォルダーを開く", command=lambda: self.safe(self.open_exports)).pack(fill="x", pady=4)
        ttk.Label(self.library_tab, text="Portable内の共通登録から、別案件へ同じテンプレートを取り込めます。\n取り込んだ版は案件内に保存され、共通登録の改訂では変わりません。", wraplength=480).pack(anchor="w", pady=5)
        self.library_list = ttk.Treeview(self.library_tab, columns=("name", "scope", "schema"), show="headings", height=15, selectmode="browse")
        for key, title in (("name", "テンプレート・版"), ("scope", "単位"), ("schema", "項目定義・版")):
            self.library_list.heading(key, text=title)
            self.library_list.column(key, width=155)
        self.library_list.pack(fill="both", expand=True)
        ttk.Button(self.library_tab, text="選択版を現在の案件へ取り込む", command=lambda: self.safe(self.import_library)).pack(fill="x", pady=5)
        ttk.Label(self.library_tab, text="共通へ登録する案件内テンプレート").pack(anchor="w")
        self.publish_choice = ttk.Combobox(self.library_tab, state="readonly")
        self.publish_choice.pack(fill="x")
        ttk.Button(self.library_tab, text="選択版を共通へ登録", command=lambda: self.safe(self.publish_library)).pack(fill="x", pady=5)
        self.refresh_library()
        self.status = tk.StringVar(value="準備完了")
        status_label = ttk.Label(self.root, textvariable=self.status, padding=6,wraplength=1250)
        status_label.pack(fill="x")
        self.root.bind("<Configure>",lambda e:status_label.configure(wraplength=max(400,e.width-30)) if e.widget==self.root else None,add=True)
        self.refresh_workflow()

    def scrollable_content(self, frame):
        return self.make_scroll_panel(frame)

    def safe(self, operation):
        try:
            return operation()
        except Exception as exc:
            self.status.set("処理失敗: "+str(exc))
            messagebox.showerror("DW-Workbench", str(exc), parent=self.root)
            return False
        finally:
            self.refresh_workflow()

    def async_call(self, operation, callback, error=None):
        self.background += 1
        self.refresh_workflow()
        future = self.pool.submit(operation)
        def done(f):
            try:
                self.callback_queue.put((callback, f.result(), None))
            except Exception as exc:
                self.callback_queue.put((error, None, exc))
        future.add_done_callback(done)

    def poll(self):
        if self.closing:
            return
        for _ in range(15):
            try:
                callback, result, error = self.callback_queue.get_nowait()
            except queue.Empty:
                break
            if callback:
                self.background -= 1
                self.safe(lambda: callback(error if error else result))
            elif error:
                self.background -= 1
                self.status.set("処理失敗: "+str(error))
                self.refresh_workflow()
            else:
                self.background -= 1
                self.refresh_workflow()
        self.root.after(75, self.poll)

    def show_capabilities(self, caps):
        self.caps = caps
        self.cap_label.configure(text=f"原本表示: DocuWorks {caps['docuworks']}  /  文字読取: {'利用可能' if caps['models'] else 'モデルなし・手入力で確認可'}")

    def require_project(self):
        if not self.app:
            raise RuleError("案件を開いてください")
        if not self.project_verified or self.validation_busy:
            raise RuleError("原本の検証が完了してから操作してください")

    def new_project(self):
        name = simpledialog.askstring("案件作成", "案件名", parent=self.root)
        if name:
            target = self.portable/"projects"/(identifier()+" "+self.safe_name(name))
            self.open_project(target)

    @staticmethod
    def safe_name(name):
        return "".join(c if c not in '<>:"/\\|?*' and ord(c) >= 32 else "_" for c in name).strip(" .")[:60] or "案件"

    def choose_project(self):
        folder = filedialog.askdirectory(title="project.sqliteのある案件フォルダー", initialdir=self.portable/"projects", parent=self.root)
        if folder:
            if not (Path(folder)/"project.sqlite").is_file():
                raise RuleError("project.sqliteがありません")
            self.open_project(folder)

    def open_project(self, folder):
        if self.ledger_dialog and not self.ledger_dialog.closed:
            if not self.ledger_dialog.close():
                raise RuleError("台帳照合の処理を終了してから案件を切り替えてください")
        if self.app and self.background:
            raise RuleError("処理が終了してから案件を切り替えてください")
        if (self.pending_results or self.pending_exports) and not self.retry_saves():
            raise RuleError("処理結果・出力履歴の未保存分を保持しています。管理・復旧から保存を再試行してください")
        if self.dirty and not self.save_field():
            return
        if self.draft_dirty:
            self.checkpoint_draft()
        self.cancel_jobs()
        from .storage import MigrationRequired, migrate_project_copy
        try:
            candidate = Workbench(folder)
        except MigrationRequired:
            if not messagebox.askyesno("旧案件をコピーして更新", "この案件はv0.1.0形式です。別フォルダーにコピーしてv0.2.0用へ更新します。\n元の案件はそのまま残ります。コピーを作成しますか？", parent=self.root):
                return
            self.validation_busy = True
            self.refresh_review()
            self.status.set("旧案件をコピーして更新しています。原本と保存結果を検証します…")
            def complete(path):
                self.validation_busy = False
                self.open_project(path)
                messagebox.showinfo("案件の更新完了", "更新したコピーを開きました。\n元の案件はv0.1.0で引き続き開けます。\n\n"+str(path), parent=self.root)
            def failure(exc):
                self.validation_busy = False
                self.refresh_review()
                self.status.set("案件のコピー更新に失敗しました。元の案件は保持しています: "+str(exc))
                messagebox.showerror("案件の更新失敗", str(exc), parent=self.root)
            self.async_call(lambda: migrate_project_copy(folder, self.portable/"projects"), complete, failure)
            return
        try:
            candidate.store.verify_database()
        except BaseException:
            candidate.close()
            raise
        if self.app:
            self.app.close()
        self.app = candidate
        self.source = self.record = self.profile = self.frozen = None
        self.field_id = None
        self.anchor = None
        self.draft_source = None
        self.draft_schema = None
        self.draft_fields, self.draft_regions = [], {}
        self.draft_dirty = False
        self.refresh_draft()
        folder_name=Path(folder).name
        first,space,rest=folder_name.partition(" ")
        visible_name=rest if space and len(first)==32 and all(c in "0123456789abcdef" for c in first) else folder_name
        self.project_label.configure(text=visible_name)
        self.refresh_lists()
        self.canvas.delete("all")
        self.image = None
        self.status.set("案件を開きました。未完了の処理は管理・復旧の再開操作で再開できます")
        self.project_verified = False
        self.validate_project()
        self.restore_draft()

    def validate_project(self):
        from .storage import validate_sources
        project = self.app
        snapshots = project.store.verify_database()
        if not snapshots:
            self.project_verified = True
            return
        self.validation_busy = True
        self.refresh_review()
        self.status.set("固定原本を検証しています。画面は読み取り専用です…")
        def finish(proof):
            if self.app is not project:
                return
            try:
                project.store.verify(proof)
                self.project_verified = True
                self.status.set("原本の検証が完了しました")
            finally:
                self.validation_busy = False
                self.refresh_review()
            if self.source and self.project_verified:
                mode = project.mode(self.source.id)
                if mode["mode"] is None:
                    project.set_mode(self.source.id, "page", mode["revision"])
                self.refresh_lists()
        def failure(exc):
            self.validation_busy = False
            self.project_verified = False
            self.refresh_review()
            self.status.set("原本検証に失敗しました。復旧後に管理・復旧の再保存から再検査できます: "+str(exc))
        self.async_call(lambda: validate_sources(project.store.root, snapshots), finish, failure)

    def add_sources(self):
        self.require_project()
        files = filedialog.askopenfilenames(title="固定コピーとして登録するXDW", filetypes=[("DocuWorks", "*.xdw")], parent=self.root)
        if not files:
            return
        from .application import copy_snapshot
        project = self.app
        def finished(data):
            project.queue_source(data)
            self.resume_jobs()
        for filename in files:
            self.async_call(lambda f=filename: copy_snapshot(f, project.store.root), finished)
        self.status.set("固定原本を案件内へコピーしています…")

    def refresh_lists(self):
        if not self.app:
            return
        self.flow_cache = None
        self.refreshing = True
        selection = self.document_list.selection()
        self.document_list.delete(*self.document_list.get_children())
        for row in self.app.store.rows("sources"):
            source = self.app.source(row["id"])
            assignments = self.app.assignments(source.id)
            done = sum(self.assignment_status(a)[1] for a in assignments)
            status = f"{done}/{len(assignments)} 記録 完了" if assignments else "処理単位を選択"
            self.document_list.insert("", "end", iid=source.id, values=(source.name, status))
        for job in self.app.store.rows("jobs"):
            if job["kind"] == "inspect" and job["status"] != "complete":
                name = json.loads(job["data"])["name"]
                self.document_list.insert("", "end", iid="job-"+job["id"], values=(name, "原本登録 "+job["status"]))
        if selection and self.document_list.exists(selection[0]):
            self.document_list.selection_set(selection)
        self.all_profiles = self.app.profiles()
        previous_profile = self.profile_choice.get()
        mode = self.app.mode(self.source.id)["mode"] if self.source else None
        self.available_profiles = [p for p in self.all_profiles if not mode or p.scope == mode]
        self.profile_choice.configure(values=[self.profile_text(p) for p in self.available_profiles])
        if previous_profile in self.profile_choice["values"]:
            self.profile_choice.set(previous_profile)
        elif self.available_profiles:
            self.profile_choice.current(len(self.available_profiles)-1)
        else:
            self.profile_choice.set("")
        self.publish_choice.configure(values=[self.profile_text(p) for p in self.all_profiles])
        if self.all_profiles and self.publish_choice.current() < 0:
            self.publish_choice.current(len(self.all_profiles)-1)
        self.available_schemas = self.app.schemas()
        self.schema_choice.configure(values=[f"{s.name} / 版{s.version} / {s.id[:8]}" for s in self.available_schemas])
        if self.draft_schema:
            for index, schema in enumerate(self.available_schemas):
                if (schema.id, schema.version) == (self.draft_schema.id, self.draft_schema.version):
                    self.schema_choice.current(index)
                    break
        self.history_list.delete(*self.history_list.get_children())
        for r in self.app.store.rows("datasets"):
            d = json.loads(r["data"])
            artifacts = [a for a in self.app.store.rows("artifacts") if a["dataset_id"] == d["id"]]
            count = sum(len(g["records"]) for g in d["groups"])
            expected = len(d["groups"])+1 if d.get("format_version", 1) >= 2 else len(d["groups"])*2
            state = f"{sum(a['status']=='complete' for a in artifacts)}/{expected} ファイル完了"
            self.history_list.insert("", 0, iid=d["id"], values=(d["created"][:19], count, state))
        self.refresh_pages()
        self.refreshing = False
        self.refresh_workflow()

    @staticmethod
    def profile_text(profile):
        return f"{profile.name} / 版{profile.version} / {'ページ用' if profile.scope == 'page' else '文書用'} / {profile.id[:8]}"

    def assignment_status(self, assignment):
        if assignment.state == "excluded":
            return "対象外: "+assignment.reason, True
        if not assignment.current_record_id:
            return "テンプレート未選択", False
        record, _, profile = self.app.context(assignment.current_record_id)
        states = record["data"]["fields"]
        ready = sum(states[f.id]["status"] == Status.ACCEPTED or
            not f.required and states[f.id]["status"] == Status.NOT_APPLICABLE and bool(states[f.id]["reason"].strip())
            for f in profile.fields)
        warning = " / 寸法不一致・手入力" if not record["data"].get("geometry_matches", True) else ""
        return f"{ready}/{len(profile.fields)} 項目 完了"+warning, ready == len(profile.fields)

    def refresh_pages(self):
        selected = self.page_list.selection()
        focused = self.page_list.focus()
        self.page_list.delete(*self.page_list.get_children())
        if not self.source:
            self.mode_choice.set("")
            self.mode_choice.configure(state="disabled")
            self.mode_hint.configure(text="文書を選択してください")
            return
        mode = self.app.mode(self.source.id)["mode"]
        self.mode_choice.set(MODES.get(mode, MODES["page"]))
        assignments = self.app.assignments(self.source.id)
        locked = any(a.state != "unassigned" for a in assignments)
        self.mode_choice.configure(state="disabled" if locked else "readonly")
        self.mode_hint.configure(text="適用・対象外指定後は処理単位を保持します" if locked else "初期選択はページごと。適用前なら変更できます")
        self.target_choice.configure(state="disabled" if mode == "document" else "readonly")
        for assignment in assignments:
            template = "—"
            if assignment.current_record_id:
                _, _, p = self.app.context(assignment.current_record_id)
                template = f"{p.name} / 版{p.version}"
            self.page_list.insert("", "end", iid=str(assignment.page), values=("文書全体" if assignment.page == 0 else assignment.page, template, self.assignment_status(assignment)[0]))
        kept = [p for p in selected if self.page_list.exists(p)]
        if kept:
            self.page_list.selection_set(kept)
            if focused and self.page_list.exists(focused):
                self.page_list.focus(focused)
        elif assignments:
            target = "0" if mode == "document" else str(self.page)
            if self.page_list.exists(target):
                self.page_list.selection_set(target)
                self.page_list.focus(target)

    def refresh_source_progress(self, source_id):
        """Field edits change one source's progress; templates and frozen history stay fixed."""
        if not self.app:
            return
        if not self.document_list.exists(source_id):
            self.refresh_lists()
            return
        source = self.app.source(source_id)
        assignments = self.app.assignments(source_id)
        done = sum(self.assignment_status(a)[1] for a in assignments)
        status = f"{done}/{len(assignments)} 記録 完了" if assignments else "処理単位を選択"
        self.document_list.item(source_id, values=(source.name, status))
        if self.source and self.source.id == source_id:
            self.refresh_pages()

    def refresh_job_view(self, job):
        """OCR adds immutable candidates; it never changes adoption or completion counts."""
        if job["kind"] == "inspect":
            if self.app.job(job["id"])["status"] == "complete":
                source_id = job["data"]["id"]
                mode = self.app.mode(source_id)
                if mode["mode"] is None:
                    self.app.set_mode(source_id, "page", mode["revision"])
            self.refresh_lists()
        elif job["kind"] == "ocr" and self.record and not self.frozen and self.field_id and (
            self.record["id"], self.field_id) == (job["data"]["record_id"], job["data"]["field_id"]):
            self.refresh_candidate_choices()

    def select_source(self):
        selection = self.document_list.selection()
        if self.refreshing or not selection or not self.app or self.source and selection[0] == self.source.id and not self.frozen:
            return
        if selection[0].startswith("job-"):
            if self.dirty and not self.save_field():
                return
            job = self.app.job(selection[0][4:])
            self.source = self.record = self.profile = self.frozen = None
            self.field_id = self.anchor = None
            self.image = None
            self.canvas.delete("all")
            self.page_label.configure(text=job["data"]["name"]+" / 原本登録未完了")
            self.refresh_review()
            self.status.set("原本登録未完了: "+str(job["error"] or job["status"])+" / 管理・復旧の再開操作で再試行できます")
            return
        if self.dirty and not self.save_field():
            if self.source and self.document_list.exists(self.source.id):
                self.document_list.selection_set(self.source.id)
            return
        self.frozen = None
        self.source = self.app.source(selection[0])
        mode = self.app.mode(self.source.id)
        if mode["mode"] is None and self.project_verified and not self.validation_busy:
            self.app.set_mode(self.source.id, "page", mode["revision"])
        self.record, self.profile = None, None
        self.field_id, self.anchor = None, None
        self.page = 1
        self.refresh_lists()
        self.load_assignment(0 if self.app.mode(self.source.id)["mode"] == "document" else 1)
        self.refresh_review()
        self.load_page()

    def apply_profile(self):
        self.require_project()
        if not self.source:
            raise RuleError("文書を選んでください")
        if not self.save_field():
            return
        index = self.profile_choice.current()
        if index < 0:
            raise RuleError("適用するテンプレートを選んでください。共通テンプレートから取り込むこともできます")
        p = self.available_profiles[index]
        pages = self.chosen_targets()
        revisions = {a.page: a.revision for a in self.app.assignments(self.source.id) if a.page in pages}
        if not self.preview_assignment(pages, p):
            return
        self.app.assign_pages(self.source.id, pages, p.id, p.version, revisions)
        target = self.page if self.page in pages else pages[0]
        self.load_assignment(target)
        self.refresh_lists()
        self.refresh_review()
        self.tabs.select(self.review_tab)
        if not self.record["data"]["geometry_matches"]:
            self.status.set("寸法・向きが不一致です。項目は保持しました。手入力と原本上の範囲指定をご利用ください")
        else:
            self.status.set(f"{len(pages)}記録に適用しました。同じ版の再適用では値を変更しません")

    def open_bulk_templates(self):
        self.require_project()
        if self.background or self.validation_busy or self.pending_results or self.pending_exports:
            raise RuleError("実行中・未保存の処理を終了してから一括適用を開いてください")
        if not self.save_field():
            return
        if self.batch_dialog and self.batch_dialog.dialog.winfo_exists():
            self.batch_dialog.dialog.lift()
            return self.batch_dialog
        profiles = self.app.profiles()
        sources = [self.app.source(row["id"]) for row in self.app.store.rows("sources")]
        if not profiles:
            raise RuleError("案件にテンプレートを登録してください。共通テンプレートから取り込むこともできます")
        if not sources:
            raise RuleError("登録が完了した文書を追加してください")
        self.batch_dialog = BulkTemplateDialog(self, profiles, sources)
        return self.batch_dialog

    def refresh_bulk_application(self, plan):
        """Refresh affected sources without changing the main document selection or old-result view."""
        changed = {entry.source_id for entry in plan.entries if entry.action == "apply"}
        if self.source and any(change.source_id == self.source.id for change in plan.mode_changes):
            previous = self.profile_choice.get()
            mode = self.app.mode(self.source.id)["mode"]
            self.available_profiles = [p for p in self.all_profiles if p.scope == mode]
            values = [self.profile_text(p) for p in self.available_profiles]
            self.profile_choice.configure(values=values)
            self.profile_choice.set(previous if previous in values else values[-1] if values else "")
        if self.source and self.source.id in changed and not self.frozen:
            target = 0 if self.app.mode(self.source.id)["mode"] == "document" else self.page
            assignment = next((a for a in self.app.assignments(self.source.id) if a.page == target), None)
            current_id = assignment.current_record_id if assignment else None
            if current_id != (self.record["id"] if self.record else None):
                self.load_assignment(target)
                self.select_field()
                self.load_page()
        for source_id in changed:
            self.refresh_source_progress(source_id)
        self.flow_cache = None
        self.refresh_workflow()

    def change_mode(self):
        self.require_project()
        if not self.source or not self.save_field():
            return
        mode = next(k for k, label in MODES.items() if label == self.mode_choice.get())
        current = self.app.mode(self.source.id)
        self.app.set_mode(self.source.id, mode, current["revision"])
        self.record = self.profile = self.frozen = self.field_id = self.anchor = None
        self.refresh_lists()
        self.refresh_review()

    def chosen_targets(self):
        if not self.source:
            raise RuleError("文書を選択してください")
        if self.app.mode(self.source.id)["mode"] == "document":
            return [0]
        return target_pages(self.target_choice.get(), self.page_list.selection(), len(self.source.pages), self.target_expression.get())

    def preview_assignment(self, pages, profile=None, reason=""):
        assignments = {a.page: a for a in self.app.assignments(self.source.id)}
        lines = []
        changed = False
        for page in pages:
            a = assignments[page]
            old = "未選択"
            same = False
            if a.current_record_id:
                _, _, previous = self.app.context(a.current_record_id)
                old = f"{previous.name} 版{previous.version}"
                same = bool(profile and (previous.id, previous.version) == (profile.id, profile.version))
                changed = changed or not same
            elif a.state == "excluded":
                old = "対象外: "+a.reason
            new = f"{profile.name} 版{profile.version}" if profile else "対象外: "+reason
            warning = "（同じ版・変更なし）" if same else ""
            if profile and not profile.matches(self.source, page if page else None):
                warning += "（寸法不一致・自動OCRなし）"
            lines.append(f"{'文書全体' if page == 0 else str(page)+'ページ'}: {old} → {new} {warning}")
        return self.confirm_list("適用内容を確認", self.source.name+f" / {len(pages)}記録", lines, "適用する",
            "切替前の結果は履歴へ保存します。新しい記録の値・確認状態は引き継ぎません。" if changed else "")

    def confirm_list(self, title, heading, lines, action, footer=""):
        """Keep large target/exclusion lists reviewable without truncating them in a dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("700x470")
        dialog.transient(self.root)
        ttk.Label(dialog, text=heading, padding=10, wraplength=670).pack(fill="x")
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10)
        text = tk.Text(body, height=17, wrap="word")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        if footer:
            ttk.Label(dialog, text=footer, padding=10, wraplength=670).pack(fill="x")
        answer = [False]
        def finish(value):
            answer[0] = value
            dialog.destroy()
        buttons = ttk.Frame(dialog, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=action, command=lambda: finish(True)).pack(side="right")
        ttk.Button(buttons, text="戻る", command=lambda: finish(False)).pack(side="right", padx=8)
        dialog.grab_set()
        self.root.wait_window(dialog)
        return answer[0]

    def exclude_pages(self):
        self.require_project()
        if not self.save_field():
            return
        pages = self.chosen_targets()
        reason = simpledialog.askstring("対象外の理由", "例：表紙、説明ページ、今回の対象外", parent=self.root)
        if reason is None:
            return
        if not reason.strip():
            raise RuleError("対象外には理由を入力してください")
        if not self.preview_assignment(pages, reason=reason):
            return
        revisions = {a.page: a.revision for a in self.app.assignments(self.source.id) if a.page in pages}
        self.app.exclude_pages(self.source.id, pages, reason, revisions)
        self.load_assignment(0 if pages == [0] else self.page)
        self.refresh_lists()
        self.refresh_review()
        self.status.set("対象外として保存しました。再び対象にするにはテンプレートを適用してください")

    def load_assignment(self, page):
        assignment = next((a for a in self.app.assignments(self.source.id) if a.page == page), None)
        self.record = self.profile = self.frozen = self.field_id = self.anchor = None
        if assignment and assignment.current_record_id:
            self.record, _, self.profile = self.app.context(assignment.current_record_id)
        if page:
            self.page = page
        self.refresh_review()

    def select_page(self):
        if self.refreshing or not self.source or self.frozen:
            return
        selected = self.page_list.selection()
        if not selected:
            return
        focused = self.page_list.focus()
        page = int(focused if focused in selected else selected[0])
        record_page = self.record.get("page") if self.record else None
        if (page == self.page or page == 0) and self.record and record_page == (page or None):
            return
        if not self.save_field():
            self.page_list.selection_set(str(record_page or 0))
            return
        self.load_assignment(page)
        self.load_page()

    def open_assignment_history(self):
        self.require_project()
        if not self.save_field():
            return
        targets = self.chosen_targets()
        if len(targets) != 1:
            raise RuleError("変更前の結果を表示するページを一つ選択してください")
        records = self.app.history_records(self.source.id, targets[0])
        if not records:
            raise RuleError("この対象には保存された記録がありません")
        dialog = tk.Toplevel(self.root)
        dialog.title("テンプレート変更の履歴")
        dialog.transient(self.root)
        dialog.grab_set()
        listing = ttk.Treeview(dialog, columns=("template", "state", "id"), show="headings", height=10, selectmode="browse")
        for key, title in (("template", "テンプレート・版"), ("state", "記録"), ("id", "記録ID")):
            listing.heading(key, text=title)
            listing.column(key, width=200)
        listing.pack(fill="both", expand=True, padx=10, pady=10)
        for record in records:
            _, _, profile = self.app.context(record["id"])
            listing.insert("", "end", iid=record["id"], values=(f"{profile.name} 版{profile.version}", "現在" if record.get("active", True) else "変更前・編集不可", record["id"][:12]))
        def show():
            selection = listing.selection()
            if not selection:
                return
            self.record, self.source, self.profile = self.app.context(selection[0])
            self.frozen = "archived"
            self.field_id = self.anchor = None
            self.page = self.record.get("page") or 1
            self.refresh_review()
            self.load_page()
            self.tabs.select(self.review_tab)
            dialog.destroy()
        ttk.Button(dialog, text="選択した記録を編集不可で表示", command=lambda: self.safe(show)).pack(fill="x", padx=10, pady=10)

    def run_selected_ocr(self):
        self.require_project()
        if not self.save_field():
            return
        targets = self.chosen_targets()
        assignments = {a.page: a for a in self.app.assignments(self.source.id)}
        ids = []
        skipped = []
        for page in targets:
            assignment = assignments[page]
            if assignment.current_record_id:
                record, _, _ = self.app.context(assignment.current_record_id)
                if record["data"].get("geometry_matches", True):
                    ids.extend(self.app.ocr_jobs(assignment.current_record_id))
                else:
                    skipped.append(page)
            else:
                skipped.append(page)
        if not ids:
            raise RuleError("OCRできる対象がありません。テンプレート未選択・対象外・寸法不一致の状態をご確認ください")
        self.enqueue_ocr_jobs(ids)
        if skipped:
            self.status.set("OCRを開始しました。未選択・対象外・寸法不一致は除外: "+", ".join(map(str, skipped)))

    def new_profile(self):
        self.require_project()
        if not self.source:
            raise RuleError("代表文書・ページを選んでください")
        if not self.save_field():
            return
        if self.draft_dirty:
            raise RuleError("現在のテンプレート草案を登録するか、草案を破棄してから新規作成してください")
        self.draft_id, self.draft_version = identifier(), 1
        self.draft_fields, self.draft_regions = [], {}
        self.draft_source = self.source
        self.draft_page = self.page
        self.draft_schema = None
        scope = self.app.mode(self.source.id)["mode"] or "page"
        self.setup_scope.set("ページ用" if scope == "page" else "文書全体用")
        self.draft_scope_value = self.setup_scope.get()
        self.setup_name.set(self.source.name+f" {'p'+str(self.page)+' ' if scope == 'page' else ''}テンプレート")
        self.schema_name.set("新しい項目定義")
        self.draft_dirty = False
        self.refresh_draft()
        self.tabs.select(self.setup_tab)

    def revise_profile(self):
        self.require_project()
        if not self.source:
            raise RuleError("代表文書を選んでください")
        if self.draft_dirty:
            raise RuleError("現在の草案を登録するか破棄してから、登録版を改訂してください")
        if not self.save_field():
            return
        index = self.profile_choice.current()
        if index < 0:
            raise RuleError("「文書」画面で改訂元の設定を選んでください")
        p = self.available_profiles[index]
        self.draft_id = p.id
        self.draft_version = max(q.version for q in self.all_profiles if q.id == p.id)+1
        self.draft_source, self.draft_page = self.source, self.page
        self.setup_scope.set("ページ用" if p.scope == "page" else "文書全体用")
        self.draft_scope_value = self.setup_scope.get()
        self.draft_schema = self.app.schema(p.schema_id, p.schema_version)
        self.draft_fields = list(p.fields)
        self.draft_regions = copy.deepcopy(p.regions) if p.matches(self.source, self.page if p.scope == "page" else None) else {}
        self.setup_name.set(p.name)
        self.schema_name.set(self.draft_schema.name)
        self.draft_dirty = False
        self.refresh_draft()
        self.tabs.select(self.setup_tab)
        self.status.set(f"設定版{self.draft_version}の草案。登録済みの版は保持されます")

    def add_draft_field(self):
        self.field_dialog()

    def edit_draft_field(self):
        selected = self.setup_list.selection()
        if not selected:
            raise RuleError("編集する項目を選択してください")
        self.field_dialog(next(f for f in self.draft_fields if f.id == selected[0]))

    def field_dialog(self, field=None):
        self.require_project()
        if not self.draft_source:
            raise RuleError("「文書」画面からテンプレートを新規作成するか、登録版を改訂してください")
        dialog = tk.Toplevel(self.root)
        dialog.title("項目を編集" if field else "項目を追加")
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        name = tk.StringVar(value=field.name if field else "")
        kind = tk.StringVar(value=KINDS[field.kind] if field else "文字列")
        required = tk.BooleanVar(value=field.required if field else True)
        unit = tk.StringVar(value=field.unit if field else "")
        ttk.Label(body, text="項目名").pack(anchor="w")
        entry = ttk.Entry(body, textvariable=name, width=40)
        entry.pack(fill="x")
        ttk.Label(body, text="値の種類").pack(anchor="w", pady=(8, 0))
        ttk.Combobox(body, textvariable=kind, values=list(KINDS.values()), state="readonly").pack(fill="x")
        ttk.Label(body, text="部品番号・先頭ゼロは文字列、温度などは数値を選びます。", wraplength=340).pack(anchor="w", pady=5)
        ttk.Checkbutton(body, variable=required, text="必須項目にする").pack(anchor="w")
        ttk.Label(body, text="標準単位（不要なら空欄）").pack(anchor="w", pady=(8, 0))
        ttk.Entry(body, textvariable=unit).pack(fill="x")
        def save():
            try:
                f = FieldSchema(field.id if field else identifier(), name.get(), next(k for k, v in KINDS.items() if v == kind.get()), required.get(), unit.get())
            except RuleError as exc:
                messagebox.showerror("項目の入力", str(exc), parent=dialog)
                return
            if field:
                self.draft_fields[self.draft_fields.index(field)] = f
            else:
                self.draft_fields.append(f)
            self.draft_changed()
            self.refresh_draft()
            self.setup_list.selection_set(f.id)
            dialog.destroy()
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="保存", command=save).pack(side="right")
        ttk.Button(buttons, text="戻る", command=dialog.destroy).pack(side="right", padx=5)
        dialog.grab_set()
        entry.focus_set()
        self.root.wait_window(dialog)

    def delete_draft_field(self):
        selection = self.setup_list.selection()
        if selection:
            self.draft_fields = [f for f in self.draft_fields if f.id != selection[0]]
            self.draft_regions.pop(selection[0], None)
            self.draft_changed()
            self.refresh_draft()

    def move_draft_field(self, delta):
        selection = self.setup_list.selection()
        if not selection:
            return
        index = next(i for i, f in enumerate(self.draft_fields) if f.id == selection[0])
        target = index+delta
        if 0 <= target < len(self.draft_fields):
            self.draft_fields[index], self.draft_fields[target] = self.draft_fields[target], self.draft_fields[index]
            self.draft_changed()
            self.refresh_draft()

    def draft_changed(self):
        if self.draft_source:
            self.draft_dirty = True
            self.update_draft_label()
            if self.draft_timer:
                self.root.after_cancel(self.draft_timer)
            self.draft_timer = self.root.after(600, self.autosave_draft)

    def autosave_draft(self):
        self.draft_timer = None
        if self.app and self.draft_dirty:
            try:
                self.checkpoint_draft()
            except Exception as exc:
                self.status.set("テンプレート草案の保存失敗・画面内に保持: "+str(exc))

    def checkpoint_draft(self):
        if not self.app or not self.draft_source:
            return
        from .storage import atomic_bytes, encode
        if self.draft_timer:
            self.root.after_cancel(self.draft_timer)
            self.draft_timer = None
        payload = {"format": 1, "source_id": self.draft_source.id, "page": self.draft_page,
            "profile_id": self.draft_id, "profile_version": self.draft_version,
            "name": self.setup_name.get(), "scope": self.setup_scope.get(),
            "schema_name": self.schema_name.get(), "schema": asdict(self.draft_schema) if self.draft_schema else None,
            "fields": [asdict(f) for f in self.draft_fields], "regions": self.draft_regions}
        path = self.app.store.root/"drafts"/"template.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_bytes(path, encode(payload).encode("utf-8"))

    def restore_draft(self):
        path = self.app.store.root/"drafts"/"template.json"
        if not path.is_file():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = self.app.source(payload["source_id"])
        page = payload["page"]
        if payload.get("format") != 1 or not isinstance(page, int) or not 1 <= page <= len(source.pages) or payload["scope"] not in ("ページ用", "文書全体用"):
            raise RuleError("保存したテンプレート草案のページ・形式が不正です。草案ファイルは保持しています")
        fields = [FieldSchema(**f) for f in payload["fields"]]
        if len({f.id for f in fields}) != len(fields):
            raise RuleError("保存した草案の項目IDが重複しています")
        for id, region in payload["regions"].items():
            if id not in {f.id for f in fields}:
                raise RuleError("保存した草案の範囲と項目が一致しません")
            actual_page = page if payload["scope"] == "ページ用" else region["page"]
            Anchor(source.id, source.sha256, actual_page, tuple(region["rect"])).validate(source)
        self.draft_source, self.draft_page = source, page
        self.draft_id, self.draft_version = payload["profile_id"], payload["profile_version"]
        self.draft_schema = schema_from(payload["schema"]) if payload["schema"] else None
        self.draft_fields, self.draft_regions = fields, payload["regions"]
        self.setup_scope.set(payload["scope"])
        self.draft_scope_value = payload["scope"]
        self.setup_name.set(payload["name"])
        self.schema_name.set(payload["schema_name"])
        self.draft_dirty = True
        self.refresh_draft()
        self.status.set("未登録のテンプレート草案を復元しました。テンプレート作成タブで続けられます")

    def remove_draft_checkpoint(self):
        if self.draft_timer:
            self.root.after_cancel(self.draft_timer)
            self.draft_timer = None
        if self.app:
            (self.app.store.root/"drafts"/"template.json").unlink(missing_ok=True)

    def update_draft_label(self):
        if not self.draft_source:
            self.draft_label.configure(text="「文書」画面で代表文書・ページを選択してください")
            return
        target = f"p{self.draft_page}" if self.setup_scope.get() == "ページ用" else "文書全体"
        state = "草案・未登録" if self.draft_dirty else "草案"
        self.draft_label.configure(text=f"{state}: {self.draft_source.name} / {target} / 登録予定版{self.draft_version}")

    def change_draft_scope(self):
        if not self.draft_source:
            return
        if self.draft_regions and not messagebox.askyesno("読み取り単位を変更", "読み取り単位を変えるため、範囲を指定し直します。項目は保持します。", parent=self.root):
            self.setup_scope.set(self.draft_scope_value)
            return
        self.draft_regions = {}
        self.draft_scope_value = self.setup_scope.get()
        self.draft_changed()
        self.refresh_draft()

    def use_schema(self):
        self.require_project()
        if not self.draft_source:
            raise RuleError("テンプレートを新規作成するか、登録版を改訂してください")
        index = self.schema_choice.current()
        if index < 0:
            raise RuleError("案件内の項目定義を選択してください")
        schema = self.available_schemas[index]
        if self.draft_fields and tuple(self.draft_fields) != schema.fields:
            if not messagebox.askyesno("項目定義を変更", "草案の項目を、選択した定義の項目へ置き換えます。\n同じ項目IDの範囲は保持します。続けますか？", parent=self.root):
                return
        self.draft_schema = schema
        self.draft_fields = list(schema.fields)
        self.draft_regions = {f.id: self.draft_regions[f.id] for f in schema.fields if f.id in self.draft_regions}
        self.schema_name.set(schema.name)
        self.draft_changed()
        self.refresh_draft()

    def fork_schema(self):
        if not self.draft_source:
            raise RuleError("先にテンプレートを作成してください")
        self.draft_schema = None
        self.schema_name.set(self.schema_name.get()+"（別定義）")
        self.draft_changed()
        self.status.set("別の項目定義として登録します。名前が同じでも別の結果シートになります")

    def discard_draft(self):
        if self.draft_dirty and not messagebox.askyesno("草案を破棄", "登録していないテンプレート草案を破棄しますか？", parent=self.root):
            return
        self.remove_draft_checkpoint()
        self.draft_source = self.draft_schema = None
        self.draft_fields, self.draft_regions = [], {}
        self.draft_dirty = False
        self.refresh_draft()

    def refresh_draft(self):
        selected = self.setup_list.selection()
        self.setup_list.delete(*self.setup_list.get_children())
        for f in self.draft_fields:
            r = self.draft_regions.get(f.id)
            location = "未指定" if not r else ("このページ" if self.setup_scope.get() == "ページ用" else "p"+str(r["page"]))+" "+str([round(v, 1) for v in r["rect"]])
            self.setup_list.insert("", "end", iid=f.id, values=(f.name, KINDS[f.kind]+(" 必須" if f.required else " 任意"), location))
        if selected and self.setup_list.exists(selected[0]):
            self.setup_list.selection_set(selected)
        self.update_draft_label()

    def select_draft_field(self, event=None):
        selection = self.setup_list.selection()
        if selection and self.draft_source:
            self.source = self.draft_source
            r = self.draft_regions.get(selection[0])
            page = self.draft_page if self.setup_scope.get() == "ページ用" else (r["page"] if r else self.page)
            self.anchor = Anchor(self.source.id, self.source.sha256, page, tuple(r["rect"])) if r else None
            if self.page != page:
                self.page = page
                self.load_page()
            self.draw_anchor()

    def save_profile(self):
        self.require_project()
        if not self.draft_source:
            raise RuleError("代表文書がありません")
        fields = tuple(self.draft_fields)
        schema = self.draft_schema
        if schema is None:
            schema = ResultSchema(identifier(), 1, self.schema_name.get(), fields)
        elif schema.fields != fields or schema.name != self.schema_name.get():
            version = max(s.version for s in self.app.schemas() if s.id == schema.id)+1
            schema = ResultSchema(schema.id, version, self.schema_name.get(), fields)
        scope = "page" if self.setup_scope.get() == "ページ用" else "document"
        pages = (self.draft_source.pages[self.draft_page-1],) if scope == "page" else self.draft_source.pages
        p = ExtractionProfile(self.draft_id, self.draft_version, self.setup_name.get(), pages,
            fields, copy.deepcopy(self.draft_regions), scope, schema.id, schema.version)
        schema.validate()
        p.validate()
        self.app.register_template(p, schema)
        self.remove_draft_checkpoint()
        self.draft_schema = schema
        self.draft_version += 1
        self.draft_dirty = False
        self.refresh_lists()
        self.refresh_draft()
        self.status.set(f"テンプレートを案件へ登録しました: {p.name} 版{p.version}。共通登録すると別案件でも利用できます")

    def refresh_library(self):
        self.library_profiles = self.library.list_profiles()
        self.library_list.delete(*self.library_list.get_children())
        for p in self.library_profiles:
            schema = self.library.get_schema(p.schema_id, p.schema_version)
            self.library_list.insert("", "end", iid=f"{p.id}:{p.version}", values=(f"{p.name} 版{p.version}", "ページ用" if p.scope == "page" else "文書用", f"{schema.name} 版{schema.version}"))

    def import_library(self):
        self.require_project()
        selected = self.library_list.selection()
        if not selected:
            raise RuleError("取り込む共通テンプレートを選択してください")
        p = next(p for p in self.library_profiles if f"{p.id}:{p.version}" == selected[0])
        self.app.import_template(self.library, p.id, p.version)
        self.refresh_lists()
        self.status.set(f"案件へ取り込みました: {p.name} 版{p.version}")
        self.tabs.select(self.list_tab)

    def publish_library(self):
        self.require_project()
        index = self.publish_choice.current()
        if index < 0:
            raise RuleError("共通へ登録する案件内テンプレートを選択してください")
        p = self.all_profiles[index]
        self.app.publish_template(self.library, p.id, p.version)
        self.refresh_library()
        self.status.set(f"Portableの共通テンプレートへ登録しました: {p.name} 版{p.version}")

    def refresh_review(self):
        selected = self.field_id
        self.review_list.delete(*self.review_list.get_children())
        enabled = bool(self.record and not self.frozen and self.project_verified and not self.validation_busy)
        for widget in self.entries+self.edit_buttons:
            widget.configure(state="normal" if enabled else "disabled")
        if not self.record:
            self.loading = True
            for variable in self.vars.values():
                variable.set("")
            self.loading = False
            self.field_label.configure(text="この対象のテンプレートを「文書」画面で選択してください")
            self.anchor_label.configure(text="根拠未指定")
            self.save_label.configure(text="")
            self.refresh_candidate_choices()
        if self.profile and self.record:
            for f in self.profile.fields:
                s = self.record["data"]["fields"][f.id]
                self.review_list.insert("", "end", iid=f.id, values=(f.name, s["value"], LABELS[s["status"]]))
            if selected and self.review_list.exists(selected):
                self.review_list.selection_set(selected)
            elif self.profile.fields:
                self.review_list.selection_set(self.profile.fields[0].id)
        self.refresh_workflow()

    def select_field(self):
        selected = self.review_list.selection()
        if not selected or not self.record:
            return
        if selected[0] == self.field_id:
            return
        if self.dirty and not self.save_field():
            if self.field_id:
                self.review_list.selection_set(self.field_id)
            return
        self.field_id = selected[0]
        self.load_field()

    def load_field(self):
        s = state_from(self.record["data"]["fields"][self.field_id])
        f = next(f for f in self.profile.fields if f.id == self.field_id)
        self.loading = True
        for k, v in self.vars.items():
            v.set(getattr(s, k))
        self.loading = False
        self.dirty = False
        self.anchor = s.anchor
        target = f" / p{self.record['page']}" if self.record.get("page") else " / 文書全体"
        self.field_label.configure(text=f"{f.name} / {KINDS[f.kind]} / {'必須' if f.required else '任意'} / {LABELS[s.status]}"+target+(" / 過去の結果・編集不可" if self.frozen else ""))
        self.save_label.configure(text="変更前の保存済み内容（編集不可）" if self.frozen == "archived" else "確定時の保存済み内容" if self.frozen else "保存済み（確認状態は上に表示）")
        self.anchor_label.configure(text="根拠未指定" if not self.anchor else f"原本 p{self.anchor.page} / mm {tuple(round(x, 2) for x in self.anchor.rect)}")
        self.refresh_candidate_choices()
        if self.anchor and self.page != self.anchor.page:
            self.page = self.anchor.page
            self.load_page()
        self.draw_anchor()

    def refresh_candidate_choices(self):
        previous = getattr(self, "candidate_values", [])
        index = self.candidate_list.current()
        selected_id = previous[index]["id"] if 0 <= index < len(previous) else None
        self.candidate_values = [] if self.frozen or not self.record or not self.field_id else self.app.candidates(self.record["id"], self.field_id)
        self.candidate_list.configure(values=[c["text"] for c in self.candidate_values])
        self.candidate_count_label.configure(text=f"候補{len(self.candidate_values)}件（取り込み後に原本と照合して確認）")
        if self.candidate_values:
            selected = next((i for i, c in enumerate(self.candidate_values) if c["id"] == selected_id), 0)
            self.candidate_list.current(selected)
        else:
            self.candidate_list.set("候補なし。手入力できます")

    def changed(self, *args):
        if self.loading or not self.record or not self.field_id or self.frozen or self.validation_busy or not self.project_verified:
            return
        self.dirty = True
        self.save_label.configure(text="未保存入力 — 保存待ち")
        if self.save_timer:
            self.root.after_cancel(self.save_timer)
        self.save_timer = self.root.after(350, self.autosave)
        self.refresh_workflow()

    def autosave(self):
        self.save_timer = None
        try:
            self.save_field()
        except Exception as exc:
            self.save_label.configure(text="保存失敗・入力を保持: "+str(exc))

    def save_field(self):
        if not self.dirty:
            return True
        if self.save_timer:
            self.root.after_cancel(self.save_timer)
            self.save_timer = None
        try:
            self.app.edit(self.record["id"], self.field_id, self.record["revision"],
                value=self.vars["value"].get(), unit=self.vars["unit"].get(), raw=self.vars["raw"].get(), anchor=self.anchor, reason=self.vars["reason"].get())
            self.record, _, self.profile = self.app.context(self.record["id"])
            self.dirty = False
            self.save_failed = False
            self.save_label.configure(text="保存済み — 変更した項目は再確認が必要です")
            self.refresh_review()
            self.refresh_source_progress(self.record["source_id"])
            return True
        except Exception as exc:
            self.save_failed = True
            self.save_label.configure(text="保存失敗・未保存入力を保持: "+str(exc))
            self.status.set("保存失敗: "+str(exc))
            return False
        finally:
            self.refresh_workflow()

    def accept(self):
        self.require_project()
        if self.frozen or not self.field_id:
            return
        if not self.save_field():
            raise RuleError("未保存入力があります。管理・復旧から保存を再試行してください")
        from .storage import validate_sources
        project, record_id, field, revision = self.app, self.record["id"], self.field_id, self.record["revision"]
        source = project.context(record_id)[1]
        self.validation_busy = True
        self.refresh_review()
        self.status.set("確認前に固定原本を検証しています…")
        def finish(proof):
            try:
                project.accept(record_id, field, revision, proof)
                if self.record and self.record["id"] == record_id and not self.frozen:
                    self.after_edit()
                else:
                    self.refresh_source_progress(source.id)
            finally:
                self.validation_busy = False
                self.refresh_review()
        def failure(exc):
            self.validation_busy = False
            self.refresh_review()
            self.status.set("確認できませんでした: "+str(exc))
        self.async_call(lambda: validate_sources(project.store.root, [asdict(source)]), finish, failure)

    def mark(self, status):
        self.require_project()
        if self.frozen or not self.field_id:
            return
        if not self.save_field():
            raise RuleError("管理・復旧から再保存してください")
        self.app.mark(self.record["id"], self.field_id, self.record["revision"], status, self.vars["reason"].get())
        self.after_edit()

    def after_edit(self):
        self.record, _, self.profile = self.app.context(self.record["id"])
        self.refresh_review()
        self.load_field()
        self.refresh_source_progress(self.record["source_id"])

    def adopt(self):
        self.require_project()
        index = self.candidate_list.current()
        if not self.save_field():
            return
        if index < 0 or not self.candidate_values:
            raise RuleError("候補を選択してください")
        self.app.adopt(self.record["id"], self.candidate_values[index]["id"], self.record["revision"])
        self.after_edit()

    def navigate(self, delta):
        if not self.source:
            return
        if not self.save_field():
            return
        page = max(1, min(len(self.source.pages), self.page+delta))
        if self.tabs.select() == str(self.setup_tab) and self.draft_source and self.setup_scope.get() == "ページ用":
            self.status.set(f"ページ用テンプレートは代表p{self.draft_page}で範囲を指定します。別ページへ適用する操作は「文書」画面で行います")
            return
        if not self.frozen and self.tabs.select() != str(self.setup_tab) and self.app.mode(self.source.id)["mode"] == "page":
            self.load_assignment(page)
            if self.page_list.exists(str(page)):
                self.page_list.selection_set(str(page))
                self.page_list.focus(str(page))
                self.page_list.see(str(page))
        else:
            self.page = page
        self.load_page()

    def next_unfinished(self):
        self.require_project()
        if self.frozen:
            raise RuleError("過去の結果は閲覧専用です。「文書」画面へ戻ってください")
        if not self.save_field():
            return
        current = (self.source.id, self.record.get('page') or 0, self.field_id) if self.source and self.record else (
            (self.source.id, self.page if self.app.mode(self.source.id)['mode'] == 'page' else 0, None) if self.source else None)
        selection = self.document_list.selection()
        if not self.source and selection and selection[0].startswith('job-'):
            job = self.app.job(selection[0][4:])
            current = (job['data']['id'], 0, None)
        target = self.app.next_unfinished(current)
        if target is None:
            self.status.set("案件の全項目が完了しています")
            return
        if target.get('job_id'):
            self.document_list.selection_set('job-'+target['job_id'])
            self.select_source()
            self.tabs.select(self.list_tab)
            self.status.set("原本登録未完了です。管理・復旧の再開操作で続けてください")
            return
        self.refreshing = True
        try:
            self.source = self.app.source(target['source_id'])
            if self.app.mode(self.source.id)['mode'] is None:
                self.app.set_mode(self.source.id, 'page')
                # A newly inspected source has no assignment yet; start at p1.
                target = target | {'page': 1}
            self.document_list.selection_set(self.source.id)
            self.document_list.see(self.source.id)
            self.page = target['page'] or 1
            self.load_assignment(target['page'])
            self.refresh_lists()
            if self.page_list.exists(str(target['page'])):
                self.page_list.selection_set(str(target['page']))
                self.page_list.focus(str(target['page']))
                self.page_list.see(str(target['page']))
            if target['field_id']:
                self.field_id = target['field_id']
                self.review_list.selection_set(self.field_id)
                self.review_list.see(self.field_id)
                self.tabs.select(self.review_tab)
            else:
                self.tabs.select(self.list_tab)
            self.load_page()
        finally:
            self.refreshing = False
        # Let queued selection/tab events settle before setting the requested field.
        self.root.after_idle(lambda: self.show_review_target(target))

    def show_review_target(self, target):
        if target['field_id'] and self.record and self.record['id'] == target['record_id']:
            self.field_id = target['field_id']
            self.review_list.selection_set(self.field_id)
            self.review_list.see(self.field_id)
            self.load_field()
            self.status.set("未完了項目を表示しました。原本と照合して確認してください")
        elif not target['field_id']:
            self.status.set("テンプレート未選択です。「文書」画面で対象を設定してください")

    def tab_changed(self):
        if not self.save_field():
            if self.tabs.select() != str(self.review_tab):
                self.tabs.select(self.review_tab)
            return
        if self.tabs.select() == str(self.setup_tab) and self.draft_source:
            self.source = self.draft_source
            self.page = self.draft_page
            self.anchor = None
            self.select_draft_field()
            self.load_page()
        elif self.tabs.select() in (str(self.list_tab), str(self.review_tab)) and self.source:
            if self.frozen and self.tabs.select() == str(self.review_tab):
                return
            if self.tabs.select() == str(self.list_tab) and self.frozen:
                self.frozen = None
            self.load_assignment(0 if self.app.mode(self.source.id)["mode"] == "document" else self.page)
            self.load_page()

    def load_page(self):
        if not self.source:
            return
        self.image = None
        self.canvas.delete("all")
        self.page_label.configure(text=f"p{self.page}/{len(self.source.pages)} {self.source.name}")
        path = self.app.store.path(f"cache/{self.source.id}/page-{self.page}-150.png")
        id = self.app.render_job(self.source.id, self.page)
        if self.app.job(id)["status"] == "complete":
            self.read_image(path)
        else:
            self.enqueue([id])

    def read_image(self, path):
        from PIL import Image
        with Image.open(path) as image:
            self.image = image.convert("RGB")
        self.show_image()

    def show_image(self):
        if self.image is None:
            return
        from PIL import ImageTk, Image
        value = self.zoom.get()
        if value == "ページに合わせる":
            self.scale = max(.05, min(max(100, self.canvas.winfo_width())/self.image.width, max(100, self.canvas.winfo_height())/self.image.height))
        else:
            self.scale = float(value.rstrip("%"))/100
        width, height = round(self.image.width*self.scale), round(self.image.height*self.scale)
        self.photo = ImageTk.PhotoImage(self.image.resize((width, height), Image.Resampling.BILINEAR), master=self.root)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.draw_anchor()

    def draw_anchor(self):
        self.canvas.delete("evidence")
        if self.anchor and self.anchor.page == self.page and self.image and self.source:
            p = self.source.pages[self.page-1]
            x, y, w, h = self.anchor.rect
            self.canvas.create_rectangle(x/p.width_mm*self.image.width*self.scale, y/p.height_mm*self.image.height*self.scale,
                (x+w)/p.width_mm*self.image.width*self.scale, (y+h)/p.height_mm*self.image.height*self.scale,
                outline="#16C270", width=3, tags="evidence")

    def focus_anchor(self):
        if not self.anchor or not self.source:
            return
        if self.page != self.anchor.page:
            self.page = self.anchor.page
            self.load_page()
        self.zoom.set("150%")
        self.show_image()
        p = self.source.pages[self.page-1]
        self.canvas.xview_moveto(max(0, self.anchor.rect[0]-25)/p.width_mm)
        self.canvas.yview_moveto(max(0, self.anchor.rect[1]-25)/p.height_mm)

    def canvas_mm(self, x, y):
        p = self.source.pages[self.page-1]
        return (max(0, min(p.width_mm, self.canvas.canvasx(x)/(self.image.width*self.scale)*p.width_mm)),
            max(0, min(p.height_mm, self.canvas.canvasy(y)/(self.image.height*self.scale)*p.height_mm)))

    def drag_start(self, event):
        self.drag = None
        tab = self.tabs.select()
        if not self.source or not self.image or self.frozen or self.validation_busy or not self.project_verified or tab not in (str(self.setup_tab), str(self.review_tab)):
            return
        if tab == str(self.setup_tab) and not self.setup_list.selection() or tab == str(self.review_tab) and not self.field_id:
            return
        if tab == str(self.setup_tab):
            if not self.draft_source or self.source.id != self.draft_source.id:
                return
            if self.setup_scope.get() == "ページ用" and self.page != self.draft_page:
                self.status.set("代表ページへ戻ってから範囲を指定してください")
                return
        elif self.record.get("page") and self.page != self.record["page"]:
            self.status.set("この記録の根拠は割り当てたページで指定してください")
            return
        self.drag = self.canvas_mm(event.x, event.y)
        self.drag_previous = self.anchor

    def drag_move(self, event):
        if getattr(self, "drag", None):
            end = self.canvas_mm(event.x, event.y)
            x, y = min(self.drag[0], end[0]), min(self.drag[1], end[1])
            self.anchor = Anchor(self.source.id, self.source.sha256, self.page, (x, y, abs(end[0]-self.drag[0]), abs(end[1]-self.drag[1])))
            self.draw_anchor()

    def drag_end(self, event):
        if not getattr(self, "drag", None):
            return
        self.drag_move(event)
        self.drag = None
        if min(self.anchor.rect[2:]) < .2:
            self.anchor = self.drag_previous
            self.draw_anchor()
            return
        self.anchor.validate(self.source)
        if self.tabs.select() == str(self.setup_tab):
            relative = 1 if self.setup_scope.get() == "ページ用" else self.page
            self.draft_regions[self.setup_list.selection()[0]] = {"page": relative, "rect": list(self.anchor.rect)}
            self.draft_changed()
            self.refresh_draft()
        else:
            self.anchor_label.configure(text=f"原本 p{self.page} / mm {tuple(round(x, 2) for x in self.anchor.rect)}")
            self.changed()

    def run_ocr(self):
        self.require_project()
        if not self.record or self.frozen:
            return
        if not self.save_field():
            return
        self.enqueue_ocr_jobs(self.app.ocr_jobs(self.record["id"]))

    def enqueue_ocr_jobs(self, ids):
        render_ids = []
        for id in ids:
            data = self.app.job(id)["data"]
            render_ids.append(self.app.render_job(data["source_id"], data["page"], 300))
        self.enqueue(list(dict.fromkeys(render_ids))+ids)

    def resume_jobs(self):
        self.require_project()
        if self.pending_results and not self.retry_saves():
            return
        self.enqueue([r["id"] for r in self.app.pending_jobs()])

    def retry_saves(self):
        if not self.project_verified and not self.validation_busy:
            self.validate_project()
            return False
        if not self.save_field():
            return False
        for id, (value, error) in list(self.pending_results.items()):
            try:
                self.app.finish_job(id, error=str(value)) if error else self.app.finish_job(id, result=value)
                del self.pending_results[id]
                self.refresh_job_view(self.app.job(id))
            except Exception as exc:
                self.status.set("ワーカー結果の保存失敗・結果を保持: "+str(exc))
                return False
        for id, (dataset, results) in list(self.pending_exports.items()):
            try:
                from .exporting import record_artifacts
                record_artifacts(self.app.store, dataset, results)
            except Exception as exc:
                self.status.set("出力履歴の保存失敗・生成結果を保持。管理・復旧から保存を再試行してください: "+str(exc))
                return False
            del self.pending_exports[id]
            self.report_export_results(results)
        self.refresh_lists()
        return True

    def enqueue(self, ids):
        for id in ids:
            if id != self.active_job and id not in self.tasks:
                self.tasks.append(id)
        self.next_job()

    def next_job(self):
        if self.active_job or not self.tasks or not self.app:
            return
        for _ in range(25):
            if not self.tasks:
                return
            id = self.tasks.pop(0)
            job = self.app.start_job(id)
            if job is not None:
                break
        else:
            self.root.after(1, self.next_job)
            return
        kind = "ocr" if job["kind"] == "ocr" else "docuworks"
        if kind not in self.clients:
            self.clients[kind] = WorkerClient(kind, self.portable, self.app.store.root/"logs"/(kind+".log"))
        try:
            request = self.app.worker_request(job, self.portable)
        except Exception as exc:
            self.app.finish_job(id, error=str(exc))
            self.status.set(str(exc))
            self.root.after(1, self.next_job)
            return
        self.active_job = id
        project = self.app
        label = {"inspect": "原本登録", "render": "原本描画", "ocr": "範囲OCR"}[job["kind"]]
        self.status.set(f"実行中: {label} / p{job['data'].get('page','—')} / 残り{len(self.tasks)}件")
        def finish(value, error=False):
            if self.app is not project or self.active_job != id:
                return
            try:
                self.app.finish_job(id, error=str(value)) if error else self.app.finish_job(id, result=value)
            except RuleError as exc:
                try:
                    self.app.finish_job(id, error=str(exc))
                except Exception:
                    self.pending_results[id] = (str(exc), True)
                error = True
                self.status.set("処理結果の検証失敗: "+str(exc))
            except Exception as exc:
                self.pending_results[id] = (value, error)
                self.active_job = None
                self.tasks.clear()
                self.status.set("結果保存失敗・結果を保持。管理・復旧から保存を再試行してください: "+str(exc))
                return
            self.active_job = None
            self.refresh_job_view(job)
            if job["kind"] == "render" and self.source and job["data"]["source_id"] == self.source.id and job["data"]["page"] == self.page and job["data"]["dpi"] == 150 and not error:
                self.read_image(self.app.store.path(job["data"]["image"]))
            if not self.tasks:
                self.status.set("処理が終了しました。失敗した処理は再開操作で再試行できます")
            self.next_job()
        self.async_call(lambda: self.clients[kind].call(request), finish, lambda error: finish(error, True))

    def cancel_jobs(self):
        had_jobs = bool(self.tasks or self.active_job)
        self.tasks.clear()
        if self.active_job and self.app:
            try:
                self.app.finish_job(self.active_job, error="利用者による中断。完了済みの結果は保持しています")
            except Exception as exc:
                self.status.set("中断状態の保存失敗。次回起動では未完了として再開します: "+str(exc))
        self.active_job = None
        for client in self.clients.values():
            client.close()
        self.clients.clear()
        if hasattr(self, "status"):
            self.status.set("処理を中断しました。完了済みの結果は保持しています。管理・復旧の再開操作で続けられます" if had_jobs else "実行中の処理はありません")

    def finalize(self):
        self.require_project()
        if self.background or self.pending_results or self.pending_exports:
            raise RuleError("実行中・未保存の処理を完了させてから結果を確定してください")
        if not self.save_field():
            raise RuleError("未保存入力があります")
        excluded = self.app.incomplete()
        completed_only = False
        if excluded:
            lines = [r["name"]+(f" p{r['page']}" if r.get("page") else " / 文書全体")+": "+", ".join(r["fields"]) for r in excluded]
            completed_only = self.confirm_list("出力対象の確認", f"未完了{len(excluded)}記録を除外して、完了した記録だけを出力します。", lines,
                "完了分だけ出力", "表示した除外対象は、Excelの出力情報に記録します。全件を完了して出す場合は「戻る」を選んでください。")
            if not completed_only:
                return
        from .storage import validate_sources
        project = self.app
        snapshots = project.store.verify_database()
        self.validation_busy = True
        self.refresh_review()
        self.status.set("確定前に固定原本を検証しています…")
        def finish(proof):
            try:
                id = project.finalize(completed_only=completed_only, validation=proof)
                self.status.set("確定結果を保存しました。表を生成しています…")
                self.export(id)
            finally:
                self.validation_busy = False
                self.refresh_review()
        def failure(exc):
            self.validation_busy = False
            self.refresh_review()
            self.status.set("結果を確定できませんでした: "+str(exc))
        self.async_call(lambda: validate_sources(project.store.root, snapshots), finish, failure)

    def export(self, id):
        # SQLite remains on this thread. File generation uses a read-only frozen snapshot.
        from .exporting import generate_artifacts
        if id in self.exporting_ids:
            raise RuleError("この確定結果を出力中です。完了してから再出力してください")
        if self.pending_exports and not self.retry_saves():
            return
        dataset = self.app.dataset(id)
        project = self.app
        completed = project.store.rows("artifacts")
        def finish(results):
            self.exporting_ids.discard(id)
            if self.app is not project:
                return
            from .exporting import record_artifacts
            try:
                record_artifacts(project.store, dataset, results)
            except Exception as exc:
                self.pending_exports[id] = (dataset, results)
                self.status.set("確認結果は保存済み。出力履歴の保存失敗・生成結果を保持。管理・復旧から保存を再試行してください: "+str(exc))
                self.refresh_lists()
                self.tabs.select(self.history_tab)
                self.history_list.selection_set(id)
                return
            self.refresh_lists()
            self.tabs.select(self.history_tab)
            self.history_list.selection_set(id)
            self.report_export_results(results)
        def failure(exc):
            self.exporting_ids.discard(id)
            self.status.set("確認結果は保存済み。表の生成に失敗しました。再出力できます: "+str(exc))
        self.exporting_ids.add(id)
        self.async_call(lambda: generate_artifacts(project.store.root, dataset, ("xlsx", "csv"), completed), finish, failure)

    def report_export_results(self, results):
        failed = [r for r in results if r["status"] == "failed"]
        self.status.set("出力完了: "+str(self.app.store.root/"exports") if not failed else "確認結果・出力履歴は保存済み。出力失敗: "+"; ".join(r["error"] for r in failed))

    def open_history(self):
        selected = self.history_list.selection()
        if not selected:
            raise RuleError("確定結果を選択してください")
        if not self.save_field():
            return
        self.history_dataset = self.app.dataset(selected[0])
        self.history_records = [(r, r.get("profile", g["profile"])) for g in self.history_dataset["groups"] for r in g["records"]]
        if not self.history_records:
            raise RuleError("確定結果に表示できる記録がありません")
        self.history_record.configure(values=[r["source"]["name"]+(f" / p{r['page']}" if r.get("page") else " / 文書全体")+f" / {p['name']} 版{p['version']} / "+r["id"][:8] for r, p in self.history_records])
        self.history_record.current(0)
        self.select_history_record()

    def select_history_record(self):
        r, p = self.history_records[self.history_record.current()]
        self.frozen = self.history_dataset["id"]
        self.source, self.profile = source_from(r["source"]), profile_from(p)
        self.record = {"id": r["id"], "revision": r["revision"], "page": r.get("page"), "data": {"fields": r["fields"]}}
        self.field_id = None
        self.anchor = None
        self.page = r.get("page") or 1
        self.refresh_review()
        self.load_page()
        self.tabs.select(self.review_tab)

    def retry_export(self):
        self.require_project()
        selected = self.history_list.selection()
        if not selected:
            raise RuleError("確定結果を選択してください")
        if not self.retry_saves():
            return
        self.export(selected[0])

    def open_exports(self):
        self.require_project()
        import os
        os.startfile(self.app.store.root/"exports")

    def backup(self):
        self.require_project()
        if self.active_job or self.background:
            raise RuleError("中断ボタンで処理を終了してからバックアップしてください")
        if not self.retry_saves():
            return
        if self.draft_dirty:
            self.checkpoint_draft()
        folder = filedialog.askdirectory(title="バックアップを置く親フォルダー", parent=self.root)
        if folder:
            from datetime import datetime
            target = Path(folder)/(self.app.store.root.name+"-backup-"+datetime.now().strftime("%Y%m%d-%H%M%S"))
            from .storage import complete_backup
            destination = self.app.store.begin_backup(target)
            source = self.app.store.root
            self.status.set("案件バックアップを作成しています…")
            self.async_call(lambda: complete_backup(source, destination), lambda _: self.status.set("バックアップ完了: "+str(target)))

    def close(self):
        if self.closing:
            return
        if self.ledger_dialog and not self.ledger_dialog.closed and not self.ledger_dialog.close():
            return
        if (self.pending_results or self.pending_exports) and not self.retry_saves():
            messagebox.showerror("未保存の処理・出力結果", "処理結果・出力履歴を保持しています。保存失敗を解決してから終了してください", parent=self.root)
            return
        if self.dirty and not self.save_field():
            messagebox.showerror("未保存入力を保持しています", "保存失敗を解決してから終了してください", parent=self.root)
            return
        if self.draft_dirty:
            try:
                self.checkpoint_draft()
            except Exception as exc:
                messagebox.showerror("テンプレート草案の保存失敗", "未登録の草案を保持しています。保存失敗を解決してから終了してください。\n"+str(exc), parent=self.root)
                return
        self.cancel_jobs()
        if self.background:
            self.status.set("実行中のファイル処理を終了してから閉じます…")
            self.root.after(150, self.close)
            return
        self.closing = True
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.app:
            self.app.close()
        self.library.close()
        self.root.destroy()

    def open_ledger(self):
        self.require_project()
        if self.background or self.pending_results or self.pending_exports:
            raise RuleError("実行中・未保存の処理を終了してから台帳照合を開いてください")
        if not self.save_field():
            return
        if self.ledger_dialog and not self.ledger_dialog.closed:
            self.ledger_dialog.root.lift()
            return
        from .ledger_ui import LedgerDialog
        self.ledger_dialog = LedgerDialog(self)


class BulkTemplateDialog:
    """A separate modal selection and immutable preview; the main list stays single-select."""

    def __init__(self, window, profiles, sources):
        self.window, self.app = window, window.app
        self.profiles = list(profiles)
        self.sources = {source.id: source for source in sources}
        name_counts = Counter(source.name for source in sources)
        self.source_labels = {source.id: source.name + (f" / {source.id[:8]}" if name_counts[source.name] > 1 else "") for source in sources}
        self.plan = self.preview_signature = self.result = None
        self.preview_rows = {}
        self.dialog = tk.Toplevel(window.root)
        self.dialog.title("複数文書へ一括適用")
        width = max(960, min(1160, window.root.winfo_screenwidth()-60))
        height = max(600, min(780, window.root.winfo_screenheight()-90))
        self.dialog.geometry(f"{width}x{height}")
        self.dialog.minsize(960, 600)
        self.dialog.transient(window.root)
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        content = ttk.Frame(self.dialog, padding=10)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)
        content.rowconfigure(8, weight=2)
        wrapped_labels = []
        intro = ttk.Label(content, text="同じテンプレートを複数の文書へ適用します。プレビューは保存しません。適用してもOCRは始まりません。", wraplength=1100)
        intro.grid(row=0, column=0, sticky="w", pady=(0, 6))
        wrapped_labels.append(intro)
        ttk.Label(content, text="1. 案件に登録済みのテンプレート・版").grid(row=1, column=0, sticky="w")
        self.profile_variable = tk.StringVar(self.dialog)
        self.profile_choice = ttk.Combobox(content, textvariable=self.profile_variable, state="readonly",
            values=[window.profile_text(p) for p in self.profiles])
        self.profile_choice.grid(row=2, column=0, sticky="ew", pady=(3, 7))

        source_bar = ttk.Frame(content)
        source_bar.grid(row=3, column=0, sticky="ew")
        ttk.Label(source_bar, text="2. 登録済みの文書（Ctrl・Shiftで複数選択）").pack(side="left")
        self.source_count = ttk.Label(source_bar)
        self.source_count.pack(side="left", padx=10)
        self.select_all_button = ttk.Button(source_bar, text="全選択", command=lambda: self.select_documents(True))
        self.select_all_button.pack(side="right")
        self.clear_button = ttk.Button(source_bar, text="選択解除", command=lambda: self.select_documents(False))
        self.clear_button.pack(side="right", padx=5)
        source_body = ttk.Frame(content)
        source_body.grid(row=4, column=0, sticky="nsew", pady=(3, 7))
        self.document_list = ttk.Treeview(source_body, columns=("name", "pages", "mode"), show="headings", height=6, selectmode="extended")
        for key, title, width in (("name", "文書", 520), ("pages", "ページ数", 80), ("mode", "現在の処理単位", 250)):
            self.document_list.heading(key, text=title)
            self.document_list.column(key, width=width)
        source_scroll = ttk.Scrollbar(source_body, orient="vertical", command=self.document_list.yview)
        self.document_list.configure(yscrollcommand=source_scroll.set)
        source_scroll.pack(side="right", fill="y")
        self.document_list.pack(side="left", fill="both", expand=True)
        for source in sources:
            mode = self.app.mode(source.id)["mode"]
            self.document_list.insert("", "end", iid=source.id, values=(self.source_labels[source.id], len(source.pages), MODES.get(mode, "未選択")))

        targets = ttk.Frame(content)
        targets.grid(row=5, column=0, sticky="ew")
        ttk.Label(targets, text="3. 対象ページ").pack(side="left")
        self.target_variable = tk.StringVar(self.dialog, value="全ページ")
        self.target_choice = ttk.Combobox(targets, textvariable=self.target_variable,
            values=("全ページ", "ページ範囲", "奇数ページ", "偶数ページ"), state="readonly", width=16)
        self.target_choice.pack(side="left", padx=5)
        self.expression_variable = tk.StringVar(self.dialog)
        self.target_expression = ttk.Entry(targets, textvariable=self.expression_variable, width=22)
        self.target_expression.pack(side="left")
        self.page_hint = ttk.Label(targets, text="例: 2-10,12")
        self.page_hint.pack(side="left", padx=5)
        self.unassigned_only = tk.BooleanVar(self.dialog, value=True)
        self.unassigned_check = ttk.Checkbutton(targets, text="未割当だけに適用する", variable=self.unassigned_only)
        self.unassigned_check.pack(side="right")
        range_hint = ttk.Label(content, text="範囲は選択文書の最大ページ数まで指定できます。短い文書の存在しないページはスキップします。", wraplength=1100)
        range_hint.grid(row=6, column=0, sticky="w", pady=(3, 6))
        wrapped_labels.append(range_hint)

        preview_bar = ttk.Frame(content)
        preview_bar.grid(row=7, column=0, sticky="ew")
        self.preview_button = ttk.Button(preview_bar, text="プレビュー", command=self.preview)
        self.preview_button.pack(side="left")
        self.summary = tk.StringVar(self.dialog, value="対象を選び、プレビューで変更内容を確認してください")
        summary_label = ttk.Label(preview_bar, textvariable=self.summary, wraplength=970)
        summary_label.pack(side="left", padx=10)
        wrapped_labels.append(summary_label)
        preview_body = ttk.Frame(content)
        preview_body.grid(row=8, column=0, sticky="nsew", pady=5)
        columns = (("document", "文書", 180), ("page", "ページ", 70), ("previous", "現在のテンプレート", 230),
                   ("action", "変更", 85), ("reason", "理由", 390), ("geometry", "寸法・向き", 130), ("mode", "処理単位の変更", 280))
        self.preview_list = ttk.Treeview(preview_body, columns=[c[0] for c in columns], show="headings", height=8, selectmode="browse")
        for key, title, width in columns:
            self.preview_list.heading(key, text=title)
            self.preview_list.column(key, width=width, stretch=False)
        yscroll = ttk.Scrollbar(preview_body, orient="vertical", command=self.preview_list.yview)
        xscroll = ttk.Scrollbar(preview_body, orient="horizontal", command=self.preview_list.xview)
        self.preview_list.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.preview_list.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        preview_body.rowconfigure(0, weight=1)
        preview_body.columnconfigure(0, weight=1)
        self.details = tk.StringVar(self.dialog, value="一覧の行を選ぶと理由の全文を表示します")
        detail_body = ttk.Frame(content)
        detail_body.grid(row=9, column=0, sticky="ew", pady=(0, 5))
        self.detail_text = tk.Text(detail_body, height=3, wrap="word", font="TkDefaultFont")
        detail_scroll = ttk.Scrollbar(detail_body, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side="right", fill="y")
        self.detail_text.pack(side="left", fill="x", expand=True)
        self.detail_text.insert("1.0", self.details.get())
        self.detail_text.configure(state="disabled")
        self.details.trace_add("write", self.update_details)
        note = ttk.Label(content, text="「未割当だけ」を外すと、変更前の結果を残して新しい記録を作成します。値・確認状態は引き継ぎません。\n"
                         "同じ版は変更しません。適用済み・対象外の記録がある文書の処理単位は変更できません。", wraplength=1100)
        note.grid(row=10, column=0, sticky="ew")
        wrapped_labels.append(note)
        bottom = ttk.Frame(content)
        bottom.grid(row=11, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(bottom, text="閉じる", command=self.close).pack(side="right")
        self.apply_button = ttk.Button(bottom, text="この内容を適用", command=self.apply, state="disabled")
        self.apply_button.pack(side="right", padx=8)

        main_index = window.profile_choice.current()
        main_profile = window.available_profiles[main_index] if main_index >= 0 else None
        selected = next((i for i, p in enumerate(self.profiles) if main_profile and
                         (p.id, p.version) == (main_profile.id, main_profile.version)), len(self.profiles)-1)
        self.profile_choice.current(selected)
        if window.source and window.source.id in self.sources:
            self.document_list.selection_set(window.source.id)
            self.document_list.see(window.source.id)
        for variable in (self.profile_variable, self.target_variable, self.expression_variable, self.unassigned_only):
            variable.trace_add("write", self.inputs_changed)
        self.document_list.bind("<<TreeviewSelect>>", self.inputs_changed)
        self.preview_list.bind("<<TreeviewSelect>>", self.show_details)
        content.bind("<Configure>", lambda event: [label.configure(wraplength=max(450, event.width-120 if label is summary_label else event.width-20)) for label in wrapped_labels])
        self.inputs_changed()
        self.dialog.grab_set()

    def selected_profile(self):
        index = self.profile_choice.current()
        if index < 0:
            raise RuleError("一括適用するテンプレートを選択してください")
        return self.profiles[index]

    def signature(self):
        return (self.profile_variable.get(), tuple(sorted(self.document_list.selection())), self.target_variable.get(),
                self.expression_variable.get(), self.unassigned_only.get())

    def inputs_changed(self, *args):
        self.source_count.configure(text=f"{len(self.document_list.selection())}/{len(self.sources)} 文書 選択")
        document = self.selected_profile().scope == "document"
        self.target_choice.configure(state="disabled" if document else "readonly")
        self.target_expression.configure(state="normal" if not document and self.target_variable.get() == "ページ範囲" else "disabled")
        self.page_hint.configure(text="文書全体に適用します" if document else "例: 2-10,12")
        if self.plan is not None and self.signature() != self.preview_signature:
            self.invalidate("入力を変更しました。プレビューを作り直してください", clear=True)
        elif self.result is not None:
            self.result = None
            self.invalidate("入力を変更しました。プレビューを作り直してください", clear=True)

    def invalidate(self, text, clear=False):
        self.plan = self.preview_signature = None
        self.apply_button.configure(state="disabled")
        self.summary.set(text)
        if clear:
            self.preview_list.delete(*self.preview_list.get_children())
            self.preview_rows.clear()
            self.details.set("一覧の行を選ぶと理由の全文を表示します")

    def select_documents(self, all_documents):
        self.document_list.selection_set(tuple(self.sources) if all_documents else ())
        self.inputs_changed()

    def targets(self, profile):
        selected = self.document_list.selection()
        if not selected:
            raise RuleError("一括適用する文書を選択してください")
        if profile.scope == "document":
            return {source_id: [0] for source_id in selected}
        if self.target_variable.get() == "ページ範囲":
            pages = target_pages("ページ範囲", (), max(len(self.sources[sid].pages) for sid in selected), self.expression_variable.get())
            return {sid: pages for sid in selected}
        # An even-page selector can yield no targets for a one-page document;
        # the application keeps that document visible as a skip in the preview.
        result = {}
        for sid in selected:
            if self.target_variable.get() == "偶数ページ" and len(self.sources[sid].pages) < 2:
                result[sid] = []
            else:
                result[sid] = target_pages(self.target_variable.get(), (), len(self.sources[sid].pages))
        return result

    def require_current_project(self):
        self.window.require_project()
        if self.window.app is not self.app:
            raise RuleError("案件が変わりました。この画面を閉じ、現在の案件で開き直してください")

    def preview(self):
        try:
            self.require_current_project()
            profile = self.selected_profile()
            plan = self.app.plan_template_application(profile.id, profile.version, self.targets(profile), self.unassigned_only.get())
            self.preview_list.delete(*self.preview_list.get_children())
            self.preview_rows.clear()
            modes = {change.source_id: f"{MODES.get(change.old_mode, '未選択')} → {MODES[change.new_mode]}" for change in plan.mode_changes}
            profiles = {(p.id, p.version): p for p in self.profiles}
            for index, entry in enumerate(plan.entries):
                previous = profiles.get((entry.previous_profile_id, entry.previous_profile_version))
                old = f"{previous.name} / 版{previous.version}" if previous else ("対象外" if entry.current_state == "excluded" else "未割当")
                page = "文書全体" if entry.page == 0 else "対象なし" if entry.page is None else str(entry.page)
                geometry = "—" if entry.geometry_matches is None else "一致" if entry.geometry_matches else "不一致・手入力"
                values = (self.source_labels[entry.source_id], page, old, {"apply": "適用", "same": "変更なし", "skip": "スキップ"}[entry.action],
                          entry.reason, geometry, modes.get(entry.source_id, "変更なし"))
                self.preview_list.insert("", "end", iid=str(index), values=values)
                self.preview_rows[str(index)] = values
            self.plan, self.preview_signature = plan, self.signature()
            counts = {action: sum(entry.action == action for entry in plan.entries) for action in ("apply", "same", "skip")}
            warning = sum(entry.geometry_matches is False for entry in plan.entries)
            self.summary.set(f"適用 {counts['apply']} / 変更なし {counts['same']} / スキップ {counts['skip']} / 処理単位変更 {len(plan.mode_changes)}文書 / 寸法不一致 {warning}")
            self.apply_button.configure(state="normal" if counts["apply"] or counts["same"] else "disabled")
            if self.preview_rows:
                self.preview_list.selection_set("0")
                self.show_details()
            return plan
        except Exception as exc:
            self.invalidate("プレビューを作成できませんでした。条件を確認してください", clear=True)
            messagebox.showerror("一括適用のプレビュー", str(exc), parent=self.dialog)
            return None

    def show_details(self, event=None):
        selected = self.preview_list.selection()
        if selected and selected[0] in self.preview_rows:
            values = self.preview_rows[selected[0]]
            self.details.set(f"{values[0]} / {values[1]} / {values[2]} → {values[3]}\n{values[4]} / {values[5]} / 処理単位: {values[6]}")

    def update_details(self, *args):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", self.details.get())
        self.detail_text.configure(state="disabled")

    def apply(self):
        try:
            self.require_current_project()
            if self.plan is None or self.signature() != self.preview_signature:
                self.invalidate("条件が変わりました。プレビューを作り直してください", clear=True)
                return False
            if not self.window.save_field():
                self.summary.set("未保存入力を保持しています。保存失敗を解決してから、適用を再試行してください")
                return False
            plan = self.plan
            result = self.app.apply_template_plan(plan)
        except StaleRevision as exc:
            self.invalidate("保存内容が変わりました。プレビューを作り直して再確認してください")
            messagebox.showerror("一括適用を再確認してください", str(exc), parent=self.dialog)
            return False
        except Exception as exc:
            self.invalidate("適用できませんでした。原因を解決し、プレビューを作り直してください")
            messagebox.showerror("一括適用できませんでした", str(exc), parent=self.dialog)
            return False
        self.result = result
        self.invalidate(f"適用完了: 適用 {result.applied} / 変更なし {result.same} / スキップ {result.skipped} / 処理単位変更 {result.mode_changes}文書。OCRは別操作です")
        self.window.status.set(self.summary.get())
        self.window.refresh_bulk_application(plan)
        for source_id in self.sources:
            mode = self.app.mode(source_id)["mode"]
            self.document_list.set(source_id, "mode", MODES.get(mode, "未選択"))
        return True

    def close(self):
        self.dialog.grab_release()
        self.dialog.destroy()
        if self.window.batch_dialog is self:
            self.window.batch_dialog = None
