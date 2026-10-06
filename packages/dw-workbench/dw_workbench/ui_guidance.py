"""Workflow presentation and action guards; no changes to stored contracts."""
from collections import defaultdict
import json
import tkinter as tk
from tkinter import ttk
from .domain import Status, field_complete, state_from


class WorkflowUI:
    def build_workflow(self):
        self.flow_controls = defaultdict(list)
        self.flow_reasons = {}
        self.flow_cache = None
        self.save_failed = False
        self.caps = None
        self.scroll_views = []
        header = ttk.Frame(self.root, padding=(8, 5))
        header.pack(fill="x")
        self.action_button(header, "new", "新しい案件を作る", self.new_project).pack(side="left", padx=2)
        self.action_button(header, "open", "保存した案件を開く", self.choose_project).pack(side="left", padx=2)
        self.project_label = ttk.Label(header, text="案件を作成または開いてください")
        self.project_label.pack(side="left", padx=12, fill="x", expand=True)
        self.management = ttk.Menubutton(header, text="管理・復旧")
        menu = tk.Menu(self.management, tearoff=False)
        for label, key, command in (("保存に失敗した内容を再保存", "retry", self.retry_saves),
                                   ("中断・失敗した処理を再開", "resume", self.resume_jobs),
                                   ("実行中の処理を中断", "cancel", self.stop_owned_work),
                                   ("案件のバックアップを作る", "backup", self.backup)):
            menu.add_command(label=label, command=lambda k=key,c=command: self.safe(lambda: self.guarded_action(k,c)))
        menu.add_separator()
        menu.add_command(label="共通テンプレートを管理", command=lambda: self.safe(lambda: self.tabs.select(self.library_tab)))
        self.management.configure(menu=menu)
        self.management.pack(side="right")
        self.cap_label = ttk.Label(self.root, text="原本表示・文字読取の利用環境を確認しています…", padding=(8, 0))
        self.cap_label.pack(fill="x")
        guide = ttk.LabelFrame(self.root, text="作業の流れ — いつでも戻って続けられます", padding=(7, 4))
        guide.pack(fill="x", padx=8, pady=5)
        steps = ttk.Frame(guide)
        steps.pack(fill="x")
        self.step_buttons = []
        for index, label in enumerate(("1 文書登録", "2 読取設定", "3 OCR", "4 確認・訂正", "5 Excel出力", "6 台帳・注釈"),1):
            button = ttk.Button(steps, text=label, command=lambda i=index: self.safe(lambda: self.select_step(i)))
            button.grid(row=0,column=index-1,sticky="ew",padx=2)
            steps.columnconfigure(index-1,weight=1)
            self.step_buttons.append(button)
        row = ttk.Frame(guide)
        row.pack(fill="x",pady=(5,0))
        self.flow_position = tk.StringVar()
        self.flow_hint = tk.StringVar()
        self.flow_count = tk.StringVar()
        labels = ttk.Frame(row)
        labels.pack(side="left",fill="x",expand=True)
        ttk.Label(labels,textvariable=self.flow_position).pack(anchor="w")
        self.flow_hint_label = ttk.Label(labels,textvariable=self.flow_hint,wraplength=800)
        self.flow_hint_label.pack(fill="x")
        self.flow_next = ttk.Button(row,command=lambda: self.safe(self.perform_next))
        self.flow_next.pack(side="right",padx=(8,0))
        self.action_button(row,"skip_details","寸法不一致の一覧",self.show_workflow_skips).pack(side="right",padx=(8,0))
        ttk.Label(guide,textvariable=self.flow_count).pack(anchor="w",pady=(3,0))
        labels.bind("<Configure>",lambda e: self.flow_hint_label.configure(wraplength=max(220,e.width)))
        self.root.bind("<Control-Return>",lambda e: self.keyboard_action("accept",self.accept_and_next),add=True)
        self.root.bind("<Control-s>",lambda e: self.keyboard_action("retry",self.retry_saves),add=True)
        for index in range(1,7):
            self.root.bind(f"<Alt-Key-{index}>",lambda e,i=index: self.keyboard_step(i),add=True)
        self.root.bind("<MouseWheel>",self.scroll_panel,add=True)
        self.root.bind("<FocusIn>",self.reveal_focus,add=True)
        self.root.bind("<Prior>",lambda e:self.scroll_pages(e,-1),add=True)
        self.root.bind("<Next>",lambda e:self.scroll_pages(e,1),add=True)

    def action_button(self, parent, key, text, command):
        button=ttk.Button(parent,text=text,command=lambda: self.safe(lambda: self.guarded_action(key,command)))
        self.flow_controls[key].append(button)
        button.bind("<Enter>",lambda e:self.flow_hint.set("利用できない理由："+self.flow_reasons[key] if self.flow_reasons.get(key) else "操作："+text))
        button.bind("<Leave>",lambda e:self.refresh_workflow())
        return button

    def guarded_action(self,key,command):
        self.refresh_workflow()
        reason=self.flow_reasons.get(key,"")
        if reason:
            self.status.set(reason)
            return False
        return command()

    def keyboard_action(self,key,command):
        self.safe(lambda: self.guarded_action(key,command))
        return "break"

    def keyboard_step(self,index):
        self.safe(lambda: self.select_step(index))
        return "break"

    def select_step(self,index):
        if index!=1 and not self.app:
            self.status.set("先に新しい案件を作るか、保存した案件を開いてください")
            return
        if not self.save_field():
            return
        frame={1:self.list_tab,2:self.list_tab,3:self.list_tab,4:self.review_tab,5:self.output_tab,6:self.output_tab}[index]
        self.tabs.select(frame)
        self.refresh_workflow()
        target={1:self.document_list,2:self.profile_choice,3:self.selected_ocr_button,4:self.review_list,
                5:self.finalize_button,6:self.ledger_entry_button}[index]
        target.focus_set()
        self.reveal_focus(type("Event",(),{"widget":target})())
        self.status.set({1:"文書を追加し、一覧から作業する文書を選びます",2:"対象ページと読み取りテンプレートを選び、適用します",
            3:"OCRは候補を作ります。採用・確認は次の工程で行います。手入力でも続けられます",
            4:"原文と入力を照合して、項目を確認済みにします",5:"確認済み結果を確定してExcel／CSVへ出します",
            6:"保存した確定結果を台帳と照合し、プレビュー後に原本コピーへ注釈を出します"}[index])

    def stop_owned_work(self):
        if self.ledger_dialog and not self.ledger_dialog.closed and self.ledger_dialog.busy:
            self.ledger_dialog.cancel_operation()
        else:
            self.cancel_jobs()

    def workflow_counts(self):
        # Structural refresh invalidates this cache. Field edits update only the
        # displayed active record, preserving the existing partial-update path.
        if self.flow_cache and self.flow_cache[0]==id(self.app):
            result,records=self.flow_cache[1:]
            for row in self.app.store.db.execute("SELECT rowid,data FROM datasets WHERE rowid>? ORDER BY rowid",(self.flow_dataset_rowid,)):
                result["datasets"]+=int(json.loads(row[1]).get("format_version")==2)
                self.flow_dataset_rowid=row[0]
            if self.record and self.profile and not self.frozen:
                states=[field_complete(f,state_from(self.record["data"]["fields"][f.id])) for f in self.profile.fields]
                eligible=self.record["id"] not in result["skipped_record_ids"]
                current=(sum(not state for state in states) if eligible else 0,all(states))
                old=records.get(self.record["id"],current)
                result["unconfirmed"]+=current[0]-old[0]
                result["complete_records"]+=int(current[1])-int(old[1])
                records[self.record["id"]]=current
            return result
        targets=self.app.review_targets(include_skipped=True)
        grouped=defaultdict(list)
        for item in targets:
            if item["record_id"]:
                grouped[item["record_id"]].append(item["complete"])
        skipped_ids={t["record_id"] for t in targets if t.get("skipped")}
        result=dict(unconfirmed=sum(bool(t["field_id"] and not t["complete"] and not t.get("skipped")) for t in targets),
            unassigned=sum(t["field_id"] is None and not t.get("job_id") for t in targets),
            imports=sum(bool(t.get("job_id")) for t in targets),
            complete_records=sum(all(items) for items in grouped.values()),
            skipped=len(skipped_ids),skipped_record_ids=skipped_ids,
            sources=len(self.app.store.rows("sources")),
            datasets=sum(json.loads(r["data"]).get("format_version")==2 for r in self.app.store.rows("datasets")))
        self.flow_cache=(id(self.app),result,{key:(sum(not state for state in values) if key not in skipped_ids else 0,all(values)) for key,values in grouped.items()})
        self.flow_dataset_rowid=self.app.store.db.execute("SELECT COALESCE(MAX(rowid),0) FROM datasets").fetchone()[0]
        return result

    def refresh_workflow(self):
        if not hasattr(self,"flow_next") or self.closing:
            return
        busy=bool(self.background or self.validation_busy or self.active_job or self.tasks)
        base="処理中です。完了を待ってください。OCRの中断は管理・復旧から行えます" if busy else ""
        if self.app and not self.project_verified and not busy:
            base="原本の検証が未完了です。管理・復旧から再保存・再検査してください"
        reasons={key:base for key in ("add","apply","bulk","new_template","ocr","accept","finalize","ledger","backup","next_unfinished","history_view","history_export","skip_details")}
        reasons.update(new="処理中は案件を切り替えられません" if busy else "",open="処理中は案件を切り替えられません" if busy else "",
            retry="処理の終了を待ってから再保存してください" if busy else "",
            resume=base,cancel="" if self.active_job or self.tasks or self.ledger_dialog and self.ledger_dialog.busy else "中断できる処理はありません")
        label,command,hint="新しい案件を作る",self.new_project,"初めての場合は案件を作り、XDW文書を追加します。途中からなら保存した案件を開けます"
        position="現在：開始前"
        count="入力は自動保存 → 原文と照合して確認済み → 結果を確定 → ファイル出力"
        if not self.app:
            for key in reasons:
                if key not in ("new","open"):
                    reasons[key]="先に案件を作成または開いてください"
        else:
            counts=self.workflow_counts()
            context={str(self.list_tab):"文書登録・読取設定",str(self.setup_tab):"読み取り範囲の作成",
                str(self.review_tab):"原文の確認・訂正",str(self.output_tab):"結果の確定・出力",
                str(self.history_tab):"過去の確定結果",str(self.library_tab):"共通テンプレートの管理"}
            position="現在："+context[self.tabs.select()]
            if self.source:
                position+=f" / p{self.page}"
            if self.frozen:
                position+=" / 過去の結果（閲覧専用）"
            count=f"案件全体：未確認 {counts['unconfirmed']}項目 / 読取設定なし {counts['unassigned']}対象 / 寸法不一致スキップ {counts['skipped']}対象 / 登録待ち {counts['imports']}文書 / 確定結果 {counts['datasets']}件"
            if not counts["skipped"]: reasons["skip_details"]="寸法不一致のスキップ対象はありません"
            selected_error=""
            try: targets=self.chosen_targets()
            except Exception as exc: targets=[]; selected_error=str(exc)
            if not self.source:
                reasons.update(apply="文書と対象ページを選択してください",new_template="代表の文書とページを選択してください",ocr="文字を読み取る文書とページを選択してください")
            else:
                if selected_error: reasons["apply"]=reasons["ocr"]=selected_error
                elif self.profile_choice.current()<0: reasons["apply"]="読み取りテンプレートを選択してください。未作成なら「読み取り範囲を作る」へ進みます"
                assignments=[a for a in self.app.assignments(self.source.id) if a.page in targets]
                usable=any(a.current_record_id and not self.app.workflow_skip(a.current_record_id) for a in assignments)
                if not usable: reasons["ocr"]="選択対象にOCRできる読み取り設定がありません。寸法不一致はスキップし、適合テンプレートを選び直せます"
            if not self.caps or not self.caps.get("models"):
                reasons["ocr"]="OCRモデルが利用できません。原文を見ながら値を手入力して確認できます"
            if self.draft_dirty:
                reasons["new_template"]="作成途中の読み取り範囲があります。範囲タブで続きを編集・登録できます"
            if not self.record or not self.field_id: reasons["accept"]="確認する項目を選んでください"
            elif self.frozen: reasons["accept"]="過去の結果は閲覧専用です。文書タブへ戻ると現在の作業を編集できます"
            elif self.record["data"]["fields"][self.field_id]["status"]==Status.ACCEPTED and not self.dirty:
                reasons["accept"]="この項目は確認済みです。次の未完了項目か、出力へ進めます"
            elif not self.vars["value"].get().strip() or not self.anchor:
                reasons["accept"]="原文を見て値を入力し、確認する範囲を指定してください"
            if not counts["complete_records"]: reasons["finalize"]="確認が完了した記録がありません。確認タブで未完了項目を確認してください"
            if not counts["datasets"]: reasons["ledger"]="先に確認済み結果を確定してください。台帳照合は保存した確定結果を使います"
            if not (counts["unconfirmed"] or counts["unassigned"] or counts["imports"]):
                reasons["next_unfinished"]=(f"通常対象の未完了はありません。寸法不一致 {counts['skipped']}対象はスキップ中です" if counts["skipped"] else "案件全体の確認は完了しています。出力へ進めます")
            if not self.history_list.selection(): reasons["history_view"]=reasons["history_export"]="履歴の一覧で確定結果を選んでください"
            if self.save_failed or self.pending_results or self.pending_exports:
                label,command,hint="未保存の内容を再保存する",self.retry_saves,"保存に失敗した入力・処理結果を保持しています。先に保存を再試行してください"
                for key in ("apply","bulk","ocr","accept","finalize","ledger"):
                    reasons[key]="未保存の内容があります。管理・復旧から保存を再試行してください"
            elif self.frozen:
                label,command,hint="現在の作業へ戻る",lambda:self.select_step(1),"過去の結果は変更できません。現在の作業へ戻って訂正できます"
            elif self.draft_dirty:
                label,command,hint="作成中の読取範囲を続ける",lambda:self.tabs.select(self.setup_tab),"範囲タブで編集・登録するか、草案を破棄して元の作業へ戻れます"
            elif counts["imports"] and not self.source:
                label,command,hint="登録待ちの処理を再開する",self.resume_jobs,"中断・失敗した原本登録を再開します。既に完了した結果は保持します"
            elif not counts["sources"]:
                label,command,hint="XDW文書を追加する",self.add_sources,"原本の固定コピーを案件内へ登録します。元の文書には書き込みません"
            elif not self.source:
                label,command,hint="未完了の作業を開く",self.next_unfinished,"文書一覧から選ぶか、未完了の文書・ページ・項目へ移動できます"
                if reasons["next_unfinished"]:
                    if counts["complete_records"]: label,command,hint="出力へ進む",lambda:self.select_step(5),"完了した記録を出力できます。不一致の未完了は除外一覧に記録します"
                    elif counts["skipped"]: label,command,hint="適合テンプレートを選び直す",lambda:self.select_step(2),reasons["next_unfinished"]
            elif not self.record:
                if self.available_profiles:
                    label,command,hint="読取設定を適用する",self.apply_profile,reasons["apply"] or "対象ページと読み取りテンプレートを確認して適用します"
                    if reasons["apply"]: command=None
                else:
                    label,command,hint="読み取り範囲を作る",self.new_profile,"この文書の配置に合わせた範囲を作るか、管理・復旧から共通テンプレートを取り込めます"
            elif self.app.workflow_skip(self.record["id"]):
                notice=self.workflow_skip_notice()
                if counts["unconfirmed"] or counts["unassigned"] or counts["imports"]:
                    label,command,hint="寸法不一致をスキップして次へ",lambda:self.next_unfinished(notice=notice),notice
                elif counts["complete_records"]:
                    label,command,hint="完了分の出力へ進む",lambda:self.select_step(5),notice+"。人手で確認済みの値は保持し、未完了の除外は出力前に確認します"
                else:
                    label,command,hint="適合テンプレートを選び直す",lambda:self.select_step(2),notice+"。OCR対象はありません。読み取り設定を選び直してください"
            elif self.tabs.select()!=str(self.review_tab) and counts["unconfirmed"]:
                label,command,hint="原文の確認・訂正へ進む",lambda:self.select_step(4),"OCRで候補を作るか、手入力で確認できます。OCRだけでは確認済みになりません"
            elif self.dirty:
                label,command,hint="入力を保存する（確認はまだ）",self.save_field,"変更した値を保存します。保存後に原文と照合して、もう一度確認済みにしてください"
            elif self.field_id and not field_complete(next(f for f in self.profile.fields if f.id==self.field_id),state_from(self.record["data"]["fields"][self.field_id])):
                if not self.vars["value"].get().strip() and self.candidate_values:
                    label,command,hint="選んだOCR候補を入力欄に使う",self.adopt,"OCR候補を選んで入力へ取り込みます。その後、原文と比べて確認済みにしてください"
                elif not self.vars["value"].get().strip() and not reasons["ocr"]:
                    label,command,hint="OCRで文字の候補を作る",self.run_ocr,"この対象の読み取り範囲をOCRします。処理後に候補を選び、原文と比べて確認します"
                elif not self.vars["value"].get().strip():
                    label,command,hint="値を手入力する",lambda:self.entries[0].focus_set(),"原本を見て、出力する値を入力してください。入力は自動保存され、確認は別操作です"
                else:
                    label,command,hint="確認して次へ",self.accept_and_next,reasons["accept"] or "原文と照合し、確認済みにして次の未完了項目へ進みます。OCR自動入力はまだ未確認です。Ctrl+Enterでも実行できます"
                    if reasons["accept"]: command=None
            elif counts["unconfirmed"] or counts["unassigned"] or counts["imports"]:
                label,command,hint="次の未完了項目へ",self.next_unfinished,"現在の入力を保存して、案件全体の次の未完了へ移動します"
            else:
                label,command,hint="出力へ進む",lambda:self.select_step(5),"確認は完了しています。結果を確定すると、その時点の値と根拠が保存されます"
                if self.tabs.select()==str(self.output_tab):
                    label,command,hint="結果を確定してExcel／CSV出力",self.finalize,"確定後の訂正は過去の結果を変えません。台帳照合もこの確定結果を使います"
            if base:
                command=None; hint=base
                label="処理中 — 完了を待つ" if busy else "原本の再検査が必要"
            reasons["resume"]=base
        self.flow_reasons=reasons
        self.next_command=command
        self.flow_next.configure(text=label,state="normal" if command else "disabled")
        self.flow_position.set(position)
        self.flow_hint.set(hint)
        self.flow_count.set(count)
        for key,buttons in self.flow_controls.items():
            for button in buttons:
                button.configure(state="disabled" if reasons.get(key) else "normal")
        for index,button in enumerate(self.step_buttons,1):
            button.configure(state="normal" if self.app or index==1 else "disabled")
        if hasattr(self,"output_reason"):
            detail="未完了が残る場合は、完了した記録だけを明示して出力できます"
            if self.app and counts["skipped"]:
                detail+=f"。寸法不一致 {counts['skipped']}対象の未完了は除外一覧に理由を残します。確認済み手入力は従来どおり出力対象です"
            self.output_reason.set(reasons.get("finalize","") or detail)
            self.ledger_reason.set(reasons.get("ledger","") or "台帳照合は保存済みの確定結果を使用します。訂正後は新しく確定してください")

    def perform_next(self):
        self.refresh_workflow()
        if self.next_command:
            self.next_command()

    def make_scroll_panel(self,frame):
        viewport=tk.Canvas(frame,highlightthickness=0,takefocus=False)
        scroll=ttk.Scrollbar(frame,orient="vertical",command=viewport.yview)
        viewport.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y")
        viewport.pack(side="left",fill="both",expand=True)
        content=ttk.Frame(viewport)
        item=viewport.create_window(0,0,window=content,anchor="nw")
        content.bind("<Configure>",lambda e:viewport.configure(scrollregion=viewport.bbox("all")))
        def resized(event):
            viewport.itemconfigure(item,width=event.width)
            def wrap(widget):
                if isinstance(widget,ttk.Label) and int(widget.cget("wraplength") or 0)>0:
                    widget.configure(wraplength=max(200,event.width-20))
                for child in widget.winfo_children(): wrap(child)
            wrap(content)
        viewport.bind("<Configure>",resized)
        self.scroll_views=[pair for pair in self.scroll_views if pair[0].winfo_exists()]
        self.scroll_views.append((viewport,content))
        return content

    def make_table(self,parent,**kwargs):
        host=ttk.Frame(parent)
        host.pack(fill="both",expand=True,pady=4)
        table=ttk.Treeview(host,**kwargs)
        table.grid(row=0,column=0,sticky="nsew")
        vertical=ttk.Scrollbar(host,orient="vertical",command=table.yview)
        vertical.grid(row=0,column=1,sticky="ns")
        horizontal=ttk.Scrollbar(host,orient="horizontal",command=table.xview)
        horizontal.grid(row=1,column=0,sticky="ew")
        table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        return table

    def panel_for(self,widget):
        for viewport,content in self.scroll_views:
            if not viewport.winfo_exists(): continue
            current=widget
            while current:
                if current in (viewport,content): return viewport,content
                current=getattr(current,"master",None)
        return None

    def scroll_panel(self,event):
        if event.widget.winfo_class() in ("Treeview","TCombobox","Text"): return
        panel=self.panel_for(event.widget)
        if panel:
            panel[0].yview_scroll(-int(event.delta/120),"units")
            return "break"

    def scroll_pages(self,event,direction):
        if event.widget.winfo_class() in ("Treeview","TCombobox","Text"): return
        panel=self.panel_for(event.widget)
        if panel:
            panel[0].yview_scroll(direction,"pages")
            return "break"

    def reveal_focus(self,event):
        panel=self.panel_for(event.widget)
        if not panel or not event.widget.winfo_ismapped(): return
        viewport,content=panel
        top=viewport.canvasy(0)
        position=event.widget.winfo_rooty()-content.winfo_rooty()
        if position<top or position+event.widget.winfo_height()>top+viewport.winfo_height():
            viewport.yview_moveto(max(0,position-8)/max(1,content.winfo_height()))
