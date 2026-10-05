"""Ledger -> decisions -> source crop preview -> owned XDW output dialog."""
from copy import deepcopy
from pathlib import Path
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from .domain import Anchor, PageInfo, RuleError, crop_box
from .ledger import Cell, LedgerBook
from .ledger_marking import (build_preview, save_session, load_session, save_decisions,
    verify_session, resolved_items, summary, drawing_spec, original_ledger_path)
from .storage import digest, relative_path
from .annotation_writer import export_annotations

STATUS = {"target": "対象", "non_target": "対象外", "review": "要確認", "excluded": "明示除外"}


class LedgerDialog:
    def __init__(self, owner):
        self.owner, self.app = owner, owner.app
        self.root = tk.Toplevel(owner.root)
        self.root.title("台帳照合 → 原文プレビュー → 注釈付きXDW")
        self.root.geometry("1100x800")
        self.root.minsize(900,650)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.busy = False
        self.closed = False
        self.session = self.folder = self.book = None
        self.changed = True
        self.rendering = False
        self.cancel = threading.Event()
        self.datasets = [json.loads(r["data"]) for r in self.app.store.rows("datasets") if json.loads(r["data"]).get("format_version") == 2]
        self.datasets.reverse()
        self.vars = {k: tk.StringVar() for k in ("path", "sheet", "header", "condition", "key_kind", "condition_kind", "color")}
        self.vars["header"].set("1")
        self.vars["key_kind"].set("文字列")
        self.vars["condition_kind"].set("文字列")
        self.vars["color"].set("赤")
        self.status = tk.StringVar(value="確定結果と台帳を選び、見出しを読み込んでください。文字列は空白・先頭ゼロも完全一致です。数式は使用しません。")
        footer = ttk.Frame(self.root,padding=(10,5))
        footer.pack(side="bottom",fill="x")
        self.output_button = ttk.Button(footer,text="3 原本コピーへ注釈付きXDWを出力",command=lambda:self.safe(self.output))
        self.output_button.pack(fill="x")
        self.output_help=tk.StringVar()
        self.output_help_label=ttk.Label(footer,textvariable=self.output_help,wraplength=1000)
        self.output_help_label.pack(fill="x",pady=3)
        buttons=ttk.Frame(footer)
        buttons.pack(fill="x",pady=3)
        ttk.Button(buttons,text="処理をキャンセル",command=self.cancel_operation).pack(side="left")
        ttk.Button(buttons,text="閉じる（保存した照合は保持）",command=self.close).pack(side="right")
        self.status_label=ttk.Label(footer,textvariable=self.status,wraplength=1000)
        self.status_label.pack(fill="x")
        self.panels=ttk.Notebook(self.root)
        self.panels.pack(fill="both",expand=True,padx=10,pady=5)
        self.settings_tab=ttk.Frame(self.panels,padding=5)
        self.preview_tab=ttk.Frame(self.panels,padding=5)
        self.panels.add(self.settings_tab,text="1 台帳と照合条件")
        self.panels.add(self.preview_tab,text="2 原文と判定を確認")
        frame=self.owner.make_scroll_panel(self.settings_tab)
        self.root.bind("<MouseWheel>",self.owner.scroll_panel,add=True)
        self.root.bind("<FocusIn>",self.owner.reveal_focus,add=True)
        self.root.bind("<Prior>",lambda e:self.owner.scroll_pages(e,-1),add=True)
        self.root.bind("<Next>",lambda e:self.owner.scroll_pages(e,1),add=True)
        def resize_help(event):
            if event.widget==self.root:
                self.status_label.configure(wraplength=max(400,event.width-40))
                self.output_help_label.configure(wraplength=max(400,event.width-40))
        self.root.bind("<Configure>",resize_help,add=True)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="使う確定結果").pack(side="left")
        self.dataset_choice = ttk.Combobox(row, state="readonly", width=45,
            values=[d["created"]+" / "+str(sum(len(g['records']) for g in d['groups']))+"記録 / "+d["id"][:8] for d in self.datasets])
        self.dataset_choice.pack(side="left", padx=5,fill="x",expand=True)
        self.dataset_choice.bind("<<ComboboxSelected>>", lambda e: self.safe(self.change_dataset))
        ttk.Button(row, text="保存した照合を再開", command=lambda: self.safe(self.resume)).pack(side="left")
        row=ttk.Frame(frame)
        row.pack(fill="x",pady=4)
        ttk.Label(row,text="照合する項目定義").pack(side="left")
        self.schema_choice = ttk.Combobox(row, state="readonly", width=35)
        self.schema_choice.pack(side="left", padx=5,fill="x",expand=True)
        self.schema_choice.bind("<<ComboboxSelected>>", lambda e: self.safe(self.change_schema))
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="台帳.xlsx").pack(side="left")
        ttk.Entry(row, textvariable=self.vars["path"], width=45).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="選択", command=lambda: self.safe(self.choose_file)).pack(side="left")
        self.read_button = ttk.Button(row, text="シート読込", command=lambda: self.safe(self.read_book))
        self.read_button.pack(side="left", padx=5)
        row=ttk.Frame(frame)
        row.pack(fill="x",pady=4)
        ttk.Label(row,text="対象シート").pack(side="left")
        self.sheet_choice = ttk.Combobox(row, textvariable=self.vars["sheet"], state="readonly", width=20)
        self.sheet_choice.pack(side="left")
        ttk.Label(row, text="見出し行").pack(side="left", padx=5)
        ttk.Entry(row, textvariable=self.vars["header"], width=6).pack(side="left")
        ttk.Button(row, text="見出し読込", command=lambda: self.safe(self.read_headers)).pack(side="left", padx=5)
        grid = ttk.Frame(frame)
        grid.pack(fill="x", pady=5)
        self.key_field = self.combo(grid, "結果の照合項目", 0, 0)
        self.key_column = self.combo(grid, "台帳の照合列", 0, 2)
        self.draw_field = self.combo(grid, "枠を付ける項目", 1, 0)
        self.condition_column = self.combo(grid, "台帳の条件列", 1, 2)
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        for key, label, values in (("key_kind", "照合する値の型", ("文字列", "数値")),
                                  ("condition_kind", "条件値の型", ("文字列", "数値")),
                                  ("color", "枠の色", ("赤", "青", "緑", "黄"))):
            ttk.Label(row, text=label).pack(side="left", padx=5)
            ttk.Combobox(row, textvariable=self.vars[key], values=values, state="readonly", width=10).pack(side="left")
        row=ttk.Frame(frame)
        row.pack(fill="x",pady=5)
        ttk.Label(row, text="条件列がこの値と完全一致したら枠を付ける").pack(side="left", padx=5)
        ttk.Entry(row, textvariable=self.vars["condition"], width=20).pack(side="left",fill="x",expand=True)
        ttk.Label(frame, text="照合キーと枠を付ける項目は別に選べます。文字列の先頭ゼロは保持します。数式・重複・空欄を自動採用しません。採用値は変更しません。", wraplength=900).pack(fill="x", pady=8)
        self.preview_button = ttk.Button(frame,text="この条件で照合してプレビューを保存",command=lambda:self.safe(self.preview))
        self.preview_button.pack(fill="x",pady=5)
        ttk.Label(frame,text="保存した後は「原文と判定を確認」へ進みます。条件を変えた場合は再プレビューが必要です。",wraplength=900).pack(fill="x")
        frame=self.preview_tab
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=5)
        self.exclude_button = ttk.Button(actions, text="選択を理由付きで明示除外", command=lambda: self.safe(self.exclude))
        self.exclude_button.pack(side="left", padx=5)
        self.undo_button = ttk.Button(actions, text="選択の除外を戻す", command=lambda: self.safe(lambda: self.exclude(True)))
        self.undo_button.pack(side="left")
        ttk.Button(actions,text="照合条件へ戻る",command=lambda:self.panels.select(self.settings_tab)).pack(side="right")
        self.counts = tk.StringVar()
        ttk.Label(frame, textvariable=self.counts).pack(anchor="w", pady=4)
        tableframe = ttk.Frame(frame)
        tableframe.pack(fill="both", expand=True)
        self.table = ttk.Treeview(tableframe, columns=("status", "source", "key", "ledger", "value", "reason"),
            show="headings", selectmode="extended", height=12)
        for key, label, width in (("status", "判定", 85), ("source", "原本／台帳行", 175), ("key", "抽出キー", 110),
                                  ("ledger", "台帳キー／条件値", 200), ("value", "枠を付ける項目の値", 150), ("reason", "理由", 400)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width)
        self.table.grid(row=0,column=0,sticky="nsew")
        scrollbar = ttk.Scrollbar(tableframe, orient="vertical", command=self.table.yview)
        scrollbar.grid(row=0,column=1,sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)
        horizontal=ttk.Scrollbar(tableframe,orient="horizontal",command=self.table.xview)
        horizontal.grid(row=1,column=0,sticky="ew")
        self.table.configure(xscrollcommand=horizontal.set)
        tableframe.columnconfigure(0,weight=1)
        tableframe.rowconfigure(0,weight=1)
        self.table.bind("<<TreeviewSelect>>", lambda e: self.safe(self.show_item))
        bottom = ttk.Frame(frame)
        bottom.pack(side="bottom", fill="x", pady=6, before=tableframe)
        self.image_label = ttk.Label(bottom, text="対象を選ぶと原文切り抜きを表示します。")
        self.image_label.pack(side="left")
        self.detail = tk.StringVar()
        details=ttk.Label(bottom, textvariable=self.detail, wraplength=500)
        details.pack(side="left", padx=15, fill="x", expand=True)
        bottom.bind("<Configure>",lambda e:details.configure(wraplength=max(300,e.width-480)))
        for var in self.vars.values():
            var.trace_add("write", lambda *a: self.invalidate())
        for combo in (self.key_field, self.draw_field, self.key_column, self.condition_column):
            combo.bind("<<ComboboxSelected>>", lambda e: self.invalidate())
        if self.datasets:
            self.dataset_choice.current(0)
            self.change_dataset()
        self.refresh_buttons()

    def combo(self, parent, label, row, col):
        ttk.Label(parent, text=label).grid(row=row, column=col, padx=5, sticky="w")
        combo = ttk.Combobox(parent, state="readonly", width=35)
        combo.grid(row=row, column=col+1, padx=5, pady=3, sticky="ew")
        return combo

    def safe(self, operation):
        try:
            operation()
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror("台帳照合", str(exc), parent=self.root)

    def invalidate(self):
        self.changed = True
        if self.session:
            self.status.set("条件が変わりました。再プレビューが必要です。保存した照合は保持しています。")
        self.refresh_buttons()

    def dataset(self):
        i = self.dataset_choice.current()
        if i < 0:
            raise RuleError("保存済みの確定結果を選択してください")
        return self.app.dataset(self.datasets[i]["id"])

    def change_dataset(self):
        dataset = self.dataset()
        self.groups = dataset["groups"]
        self.schema_choice.configure(values=[str(i)+": "+g["schema"]["name"]+" / 版"+str(g["schema"]["version"]) for i,g in enumerate(self.groups,1)])
        self.schema_choice.current(0)
        self.change_schema()

    def change_schema(self):
        self.fields = self.groups[self.schema_choice.current()]["schema"]["fields"]
        for combo in (self.key_field, self.draw_field):
            combo.configure(values=[str(i)+": "+f["name"]+"（"+("数値" if f["kind"]=="decimal" else "文字列")+"）" for i,f in enumerate(self.fields,1)])
            combo.set("")
        self.invalidate()

    def choose_file(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Excel台帳", "*.xlsx")])
        if path:
            self.vars["path"].set(path)
            self.read_book()

    def read_book(self):
        if self.busy:
            return
        self.book = LedgerBook(self.vars["path"].get())
        self.sheet_choice.configure(values=list(self.book.sheets))
        self.sheet_choice.current(0)
        self.read_headers()

    def read_headers(self):
        if self.busy:
            return
        if self.book is None or self.book.path != Path(self.vars["path"].get()).resolve():
            raise RuleError("先にシートを読み込んでください")
        sheet = self.book.sheet(self.vars["sheet"].get(), int(self.vars["header"].get()))
        self.columns = list(sheet.columns)
        self.header_binding = (str(self.book.path), sheet.name, sheet.header_row)
        self.loaded_headers = sheet.columns
        for combo in (self.key_column, self.condition_column):
            combo.configure(values=[str(c)+": "+sheet.columns[c] for c in self.columns])
            combo.set("")
        self.invalidate()

    def config(self):
        choices = (self.key_field, self.draw_field, self.key_column, self.condition_column, self.schema_choice)
        if any(c.current()<0 for c in choices):
            raise RuleError("項目・列・項目定義をすべて選択してください")
        schema = self.groups[self.schema_choice.current()]["schema"]
        return dict(schema_id=schema["id"], schema_version=schema["version"],
            key_field=self.fields[self.key_field.current()]["id"], draw_field=self.fields[self.draw_field.current()]["id"],
            sheet=self.vars["sheet"].get(), header_row=int(self.vars["header"].get()),
            key_column=self.columns[self.key_column.current()], condition_column=self.columns[self.condition_column.current()],
            key_kind="text" if self.vars["key_kind"].get()=="文字列" else "number",
            condition_kind="text" if self.vars["condition_kind"].get()=="文字列" else "number",
            condition_value=self.vars["condition"].get(), color={"赤":"red", "青":"blue", "緑":"green", "黄":"yellow"}[self.vars["color"].get()])

    def preview(self):
        if self.busy:
            return
        config = self.config()
        book = LedgerBook(self.vars["path"].get())
        if getattr(self, "header_binding", None) != (str(book.path), config["sheet"], config["header_row"]) or book.sheet(config["sheet"], config["header_row"]).columns != self.loaded_headers:
            raise RuleError("ファイル・シート・見出しが変わりました。見出しを再読込して列を選択してください")
        dataset = self.dataset()
        folder, session = save_session(self.app.store.root, dataset, book, config)
        self.folder, self.session, self.book = folder, session, book
        self.changed = False
        self.show_preview()
        self.status.set("プレビューを保存しました: "+str(folder)+"。要確認は解消または理由付き除外が必要です。")

    def show_preview(self):
        self.items = {item["id"]:item for item in resolved_items(self.session)}
        self.table.delete(*self.table.get_children())
        for id,item in self.items.items():
            ledger = " / ".join(Cell(**item[k]).display() for k in ("ledger_key", "ledger_condition") if item.get(k))
            source = item["source"]["name"] if item["scope"]=="record" else "台帳行 "+str(item["ledger_row"])
            self.table.insert("", "end", iid=id, values=(STATUS[item["status"]], source, item.get("extracted_key", ""),
                ledger, item.get("extracted_value", ""), item.get("exclusion_reason", item["reason"])))
        counts = summary(self.session)
        self.counts.set("記録: "+" / ".join(label+str(counts["record"].get(key,0))+"件" for key,label in STATUS.items())
                       +"　台帳診断: 要確認"+str(counts["ledger"].get("review",0))+"件 / 明示除外"+str(counts["ledger"].get("excluded",0))+"件")
        self.refresh_buttons()
        self.panels.select(self.preview_tab)

    def exclude(self, undo=False):
        if self.busy or not self.session or self.changed:
            return
        selected = self.table.selection()
        if not selected:
            raise RuleError("対象を選択してください（複数選択可）")
        reason = None if undo else simpledialog.askstring("明示除外", "選択した"+str(len(selected))+"件を除外する理由", parent=self.root)
        if not undo and reason is None:
            return
        if not undo and not reason.strip():
            raise RuleError("除外理由を入力してください")
        session = deepcopy(self.session)
        for id in selected:
            if undo:
                session["exclusions"].pop(id, None)
            else:
                session["exclusions"][id] = reason
        save_decisions(self.folder, session)
        self.session = session
        self.show_preview()

    def resume(self):
        if self.busy:
            return
        base = self.app.store.root/"exports/ledger-markups"
        path = filedialog.askdirectory(parent=self.root, initialdir=base, title="session.jsonのある照合保存フォルダー")
        if not path:
            return
        folder = Path(path).resolve()
        if not folder.is_relative_to(base.resolve()):
            raise RuleError("現在の案件内の照合保存先を選択してください")
        raw = json.loads((folder/"session.json").read_text(encoding="utf-8"))
        dataset = self.app.dataset(raw["preview"]["dataset_id"])
        session = load_session(folder, dataset)
        self.dataset_choice.current(next(i for i,d in enumerate(self.datasets) if d["id"]==dataset["id"]))
        self.change_dataset()
        cfg = session["preview"]["config"]
        self.schema_choice.current(next(i for i,g in enumerate(self.groups) if (g["schema"]["id"],g["schema"]["version"])==(cfg["schema_id"],cfg["schema_version"])))
        self.change_schema()
        self.vars["path"].set(str(original_ledger_path(folder, session)))
        self.read_book()
        self.vars["sheet"].set(cfg["sheet"])
        self.vars["header"].set(str(cfg["header_row"]))
        self.read_headers()
        self.key_column.current(self.columns.index(cfg["key_column"]))
        self.condition_column.current(self.columns.index(cfg["condition_column"]))
        self.key_field.current(next(i for i,f in enumerate(self.fields) if f["id"]==cfg["key_field"]))
        self.draw_field.current(next(i for i,f in enumerate(self.fields) if f["id"]==cfg["draw_field"]))
        self.vars["condition"].set(cfg["condition_value"])
        self.vars["key_kind"].set("文字列" if cfg["key_kind"]=="text" else "数値")
        self.vars["condition_kind"].set("文字列" if cfg["condition_kind"]=="text" else "数値")
        self.vars["color"].set({"red":"赤","blue":"青","green":"緑","yellow":"黄"}[cfg["color"]])
        self.folder, self.session, self.changed = folder, session, False
        self.show_preview()
        self.status.set("保存した照合・除外理由を再開しました。台帳・確定結果の一致を検証済みです。")

    def show_item(self):
        selected = self.table.selection()
        if not selected:
            return
        item = self.items[selected[0]]
        # Clear the previous row's crop before any render/validation can fail.
        self.image_label.configure(image="", text="選択した行の原文範囲を準備しています…")
        anchor=item.get("anchor")
        location=("第"+str(anchor["page"])+"ページ / 左・上・幅・高さ "
                  +", ".join(str(round(v,3)) for v in anchor["rect"])+" mm") if anchor else "なし"
        ledger=" / ".join(Cell(**item[key]).display() for key in ("ledger_key","ledger_condition") if item.get(key))
        self.detail.set("原文表記: "+item.get("raw", "")+"\n出力する値（採用値）: "+item.get("extracted_value", "")
            +"\n台帳キー・条件値: "+ledger+"\n原本範囲: "+location
            +"\n判定理由: "+item.get("exclusion_reason", item["reason"]))
        if item["scope"] != "record" or not item.get("anchor"):
            self.image_label.configure(image="", text="この行に原文範囲はありません")
            return
        if self.rendering or self.busy:
            return
        anchor = item["anchor"]
        source = item["source"]
        path = self.app.store.path(f"cache/{source['id']}/page-{anchor['page']}-150.png")
        job_id = self.app.render_job(source["id"], anchor["page"], 150)
        job = self.app.job(job_id)
        if job["status"] == "complete" and path.is_file():
            self.show_crop(item, path)
            return
        self.rendering = True
        self.refresh_buttons()
        self.image_label.configure(image="", text="固定原本から原文画像を準備しています…")
        request = self.app.worker_request(job, self.owner.portable)
        from .workers import WorkerClient
        def render():
            client = WorkerClient("native", self.owner.portable, self.app.store.root/"logs/ledger-preview.log")
            try:
                return client.call(request)
            finally:
                client.close()
        def done(result):
            self.rendering = False
            self.app.finish_job(job_id, result)
            self.refresh_buttons()
            if not self.closed:
                self.show_item()
        def failed(exc):
            self.rendering = False
            self.refresh_buttons()
            self.status.set("原文画像を準備できません: "+str(exc))
        self.owner.async_call(render, done, failed)

    def show_crop(self, item, path):
        from PIL import Image, ImageTk
        original = relative_path(self.app.store.root, item["source"]["path"])
        if digest(original) != item["source"]["sha256"]:
            raise RuleError("原文が変わっています。画像は表示しません")
        anchor = Anchor(**(item["anchor"]|{"rect":tuple(item["anchor"]["rect"])}))
        info = PageInfo(**item["source"]["pages"][anchor.page-1])
        with Image.open(path) as image:
            crop = image.crop(crop_box(anchor, info, *image.size)).convert("RGB")
        crop.thumbnail((450, 180))
        self.photo = ImageTk.PhotoImage(crop, master=self.root)
        self.image_label.configure(image=self.photo, text="")

    def output(self):
        if self.busy or self.rendering:
            return
        if not self.session or self.changed:
            raise RuleError("現在の条件で再プレビューしてください")
        verify_session(self.folder, self.session, self.app.dataset(self.session["preview"]["dataset_id"]))
        spec = drawing_spec(self.app.store.root, self.session)
        if not messagebox.askyesno("注釈付きXDWの出力", str(len(spec))+"原本のコピーへ塗りなし矩形を出力します。\n原本と採用値は保持します。続けますか？", parent=self.root):
            return
        self.busy = True
        self.cancel = threading.Event()
        session = deepcopy(self.session)
        self.refresh_buttons()
        self.status.set("原本のコピーへ枠を付けています。保存後に位置と既存注釈を検証します…")
        def done(result):
            self.busy = False
            output, report = result
            self.session["outputs"].append(dict(path=output.relative_to(self.folder).as_posix(), created=report["created"]))
            try:
                save_decisions(self.folder, self.session)
            except Exception as exc:
                self.changed = True
                self.status.set("XDWとreport.jsonは出力済み。照合画面の履歴保存に失敗: "+str(exc)+" / "+str(output))
            else:
                self.status.set("出力完了: "+str(output)+"。SDK保存再読込は成功、Viewer目視は未確認です。")
            self.refresh_buttons()
        def failed(exc):
            self.busy = False
            self.status.set("出力できませんでした。保存したプレビューから再試行できます: "+str(exc))
            self.refresh_buttons()
        self.owner.async_call(lambda: export_annotations(self.app.store.root, self.folder, session, cancel=self.cancel), done, failed)

    def refresh_buttons(self):
        if not hasattr(self, "output_button"):
            return
        idle = not self.busy and not self.rendering
        for button in (self.preview_button, self.read_button):
            button.configure(state="normal" if idle else "disabled")
        ready = idle and self.session is not None and not self.changed
        for button in (self.exclude_button, self.undo_button):
            button.configure(state="normal" if ready else "disabled")
        no_review = ready and not any(i["status"]=="review" for i in resolved_items(self.session))
        targets = ready and any(i["status"]=="target" for i in resolved_items(self.session))
        self.output_button.configure(state="normal" if no_review and targets else "disabled")
        self.output_help.set("処理中です。完了を待つかキャンセルしてください" if not idle else
            "先に照合条件を指定し、プレビューを保存してください" if self.session is None else
            "条件が変わっています。照合条件の画面でプレビューを保存し直してください" if self.changed else
            "要確認を解消するか、理由付きで明示除外すると出力できます" if not no_review else
            "枠を付ける対象がありません。条件・対象外・除外内容を確認してください" if not targets else
            "原文と判定を確認したら、原本コピーへ塗りなしの枠を付けて出力できます")

    def cancel_operation(self):
        if self.busy:
            self.cancel.set()
            self.status.set("キャンセルを受け付けました。SDK処理後に一時コピーを破棄します。")

    def close(self):
        if self.busy or self.rendering:
            self.cancel_operation()
            self.status.set("処理の終了を待っています。終了後に閉じてください。")
            return False
        self.closed = True
        self.root.destroy()
        return True
