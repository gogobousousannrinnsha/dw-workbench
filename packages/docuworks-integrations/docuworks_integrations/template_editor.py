"""Local Windows authoring UI. No GUI or native imports at package import time."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


class Editor:
    def __init__(self, window, app_root):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox, simpledialog
        from . import template_authoring as a
        self.tk, self.ttk = tk, ttk
        self.files, self.messages, self.dialog = filedialog, messagebox, simpledialog
        self.api = a; self.window = window; self.app_root = a._workspace(app_root)
        self.draft = None; self.selected = None; self.page = 1; self.image = None
        self.process = None; self.save_timer = None; self.dirty = False; self.filling = False
        self.preview = None; self.examples = {}; self.snapshot = None; self.settings = {}
        self.closed = False
        window.title('DW-OCR テンプレート作成'); window.geometry('1140x820'); window.minsize(860, 650)
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.bind('<Control-s>', lambda event: self.save())
        window.bind('<Control-r>', lambda event: self.refresh())
        style = ttk.Style(window)
        if 'vista' in style.theme_names(): style.theme_use('vista')
        style.configure('Title.TLabel', font=('Yu Gothic UI', 15))
        self.status = tk.StringVar(value='作成方法を選んでください。')
        self.title = ttk.Label(window, text='テンプレート作成', style='Title.TLabel', padding=14)
        self.title.pack(fill='x')
        self.container = ttk.Frame(window, padding=(14, 0, 14, 8)); self.container.pack(fill='both', expand=True)
        self.home = ttk.Frame(self.container); self.edit = ttk.Frame(self.container); self.review = ttk.Frame(self.container)
        self.status_label = ttk.Label(window, textvariable=self.status, padding=10, wraplength=1000)
        self.status_label.pack(fill='x', side='bottom', before=self.container)
        self._home_widgets(); self._edit_widgets(); self._review_widgets()
        self.show_home()

    def _button(self, parent, text, command, **pack):
        button = self.ttk.Button(parent, text=text, command=command)
        button.pack(**pack)
        return button

    def _home_widgets(self):
        ttk = self.ttk
        actions = ttk.Frame(self.home); actions.pack(fill='x', pady=(8, 18))
        self.new_button = self._button(actions, '新規作成', self.new, side='left', padx=(0, 8))
        self._button(actions, '一覧を更新', self.show_home, side='left')
        ttk.Label(self.home, text='下書きから再開').pack(anchor='w')
        self.drafts = ttk.Treeview(self.home, columns=('name','state'), show='headings', height=6)
        self.drafts.heading('name', text='テンプレート名'); self.drafts.heading('state', text='状態')
        self.drafts.pack(fill='both', expand=True, pady=6)
        self.drafts.bind('<Double-1>', lambda event: self.resume())
        self._button(self.home, '選んだ下書きを再開', self.resume, anchor='e', pady=(0, 16))
        ttk.Label(self.home, text='登録済みから改訂').pack(anchor='w')
        self.versions = ttk.Treeview(self.home, columns=('name','version','sample'), show='headings', height=6)
        for key, label in [('name','テンプレート名'),('version','版'),('sample','作成時の見本')]:
            self.versions.heading(key, text=label)
        self.versions.pack(fill='both', expand=True, pady=6)
        self.versions.bind('<Double-1>', lambda event: self.revise())
        self._button(self.home, '選んだ版を改訂', self.revise, anchor='e')

    def _edit_widgets(self):
        tk, ttk = self.tk, self.ttk
        toolbar = ttk.Frame(self.edit); toolbar.pack(fill='x', pady=(0, 10))
        self._button(toolbar, '一覧へ戻る', self.back_home, side='left')
        self._button(toolbar, 'Viewerで開く', self.open_viewer, side='left', padx=6)
        self._button(toolbar, '保存後に再読込', self.refresh, side='left')
        self._button(toolbar, '下書きを保存', self.save, side='right')
        self.panes = ttk.Panedwindow(self.edit, orient='horizontal'); self.panes.pack(fill='both', expand=True)
        left = ttk.Frame(self.panes); right = ttk.Frame(self.panes, padding=(14, 0, 0, 0))
        self.panes.add(left, weight=3); self.panes.add(right, weight=2)
        controls = ttk.Frame(left); controls.pack(fill='x', pady=(0, 8))
        self._button(controls, '前', lambda: self.change_page(-1), side='left')
        self.page_label = ttk.Label(controls, text='1 / 1 ページ'); self.page_label.pack(side='left', padx=8)
        self._button(controls, '次', lambda: self.change_page(1), side='left')
        self.zoom = tk.StringVar(value='全体')
        self.zoom_box = ttk.Combobox(controls, textvariable=self.zoom, values=('全体','100%','150%','200%'),
                                    state='readonly', width=7)
        self.zoom_box.pack(side='right'); self.zoom_box.bind('<<ComboboxSelected>>', lambda e: self.draw())
        view = ttk.Frame(left); view.pack(fill='both', expand=True)
        view.rowconfigure(0, weight=1); view.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(view, background='#e8ebef', highlightthickness=0)
        xs = ttk.Scrollbar(view, orient='horizontal', command=self.canvas.xview)
        ys = ttk.Scrollbar(view, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0,column=0,sticky='nsew'); ys.grid(row=0,column=1,sticky='ns'); xs.grid(row=1,column=0,sticky='ew')
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<Button-1>', self.canvas_select)
        ttk.Label(left, text='矩形の追加・移動・削除はViewerで行い、保存して閉じてから再読込してください。',
                  wraplength=480, padding=(0, 8)).pack(fill='x')
        self.name = tk.StringVar(); self.field_name = tk.StringVar(); self.purpose = tk.StringVar(value='取得')
        self.expected = tk.StringVar(); self.required = tk.BooleanVar(value=True); self.join = tk.StringVar(value='連結')
        ttk.Label(right, text='テンプレート名').pack(anchor='w')
        self.name_entry = ttk.Entry(right, textvariable=self.name); self.name_entry.pack(fill='x', pady=(4, 12))
        self.fields = ttk.Treeview(right, columns=('number','name','purpose','page'), show='headings', height=7)
        for key, label, width in [('number','番号',45),('name','項目名',160),('purpose','用途',70),('page','頁',35)]:
            self.fields.heading(key, text=label); self.fields.column(key, width=width, minwidth=30, stretch=key=='name')
        self.fields.pack(fill='both', expand=True)
        self.fields.bind('<<TreeviewSelect>>', self.tree_select)
        ordering = ttk.Frame(right); ordering.pack(fill='x', pady=6)
        self._button(ordering, '出力順 ↑', lambda: self.reorder(-1), side='left')
        self._button(ordering, '出力順 ↓', lambda: self.reorder(1), side='left', padx=5)
        form_view = ttk.Frame(right); form_view.pack(fill='both', expand=True)
        self.form_canvas = tk.Canvas(form_view, highlightthickness=0, height=290, width=320)
        form_scroll = ttk.Scrollbar(form_view, orient='vertical', command=self.form_canvas.yview)
        self.form_canvas.configure(yscrollcommand=form_scroll.set)
        form_scroll.pack(side='right', fill='y'); self.form_canvas.pack(side='left', fill='both', expand=True)
        right = ttk.Frame(self.form_canvas)
        form_window = self.form_canvas.create_window(0, 0, window=right, anchor='nw')
        self.form_canvas.bind('<Configure>', lambda e: self.form_canvas.itemconfigure(form_window, width=e.width))
        right.bind('<Configure>', lambda e: self.form_canvas.configure(scrollregion=self.form_canvas.bbox('all')))
        self.field_heading = ttk.Label(right, text='矩形を選んでください。'); self.field_heading.pack(anchor='w', pady=(8, 4))
        self.example = tk.StringVar(value='')
        ttk.Label(right, textvariable=self.example, wraplength=370, padding=8, relief='groove').pack(fill='x', pady=(0, 12))
        ttk.Label(right, text='項目名').pack(anchor='w')
        self.field_entry = ttk.Entry(right, textvariable=self.field_name); self.field_entry.pack(fill='x', pady=(4, 10))
        ttk.Label(right, text='この範囲の用途').pack(anchor='w')
        self.purpose_box = ttk.Combobox(right, textvariable=self.purpose, values=('取得','適用判定'), state='readonly')
        self.purpose_box.pack(fill='x', pady=(4, 8))
        self.required_box = ttk.Checkbutton(right, text='必須項目にする', variable=self.required)
        self.required_box.pack(anchor='w', pady=6)
        self.expected_row = ttk.Frame(right)
        ttk.Label(self.expected_row, text='期待する文字（見本から候補を入力）').pack(anchor='w')
        self.expected_entry = ttk.Entry(self.expected_row, textvariable=self.expected); self.expected_entry.pack(fill='x', pady=4)
        self.details = ttk.Frame(right)
        self.details_open = tk.BooleanVar(value=False)
        self.details_toggle = ttk.Checkbutton(right, text='詳細設定', variable=self.details_open, command=self.toggle_details)
        self.details_toggle.pack(anchor='w', pady=7)
        ttk.Label(self.details, text='文字の結合').pack(side='left')
        ttk.Combobox(self.details, textvariable=self.join, values=('連結','空白','改行'), state='readonly', width=9).pack(side='right')
        actions = ttk.Frame(self.edit); actions.pack(side='bottom', fill='x', pady=(12, 0), before=self.panes)
        self.check_button = self._button(actions, '取得結果を確認 →', self.check, side='right')
        for var in (self.name,self.field_name,self.purpose,self.expected,self.required,self.join):
            var.trace_add('write', self.changed)

    def _review_widgets(self):
        ttk = self.ttk
        self.result_heading = ttk.Label(self.review, style='Title.TLabel'); self.result_heading.pack(anchor='w', pady=(5, 12))
        self.result_rows = ttk.Treeview(self.review, columns=('name','value','state'), show='headings', height=10)
        for key,label in [('name','項目名 / 条件'),('value','取得値'),('state','状態')]: self.result_rows.heading(key,text=label)
        self.result_rows.pack(fill='both',expand=True)
        self.diagnostics = self.tk.Text(self.review, height=7, wrap='word', state='disabled')
        self.diagnostics.pack(fill='x', pady=10)
        self.confirmed = self.tk.BooleanVar(value=False)
        self.confirm = ttk.Checkbutton(self.review, text='確認事項を読み、この内容で登録する', variable=self.confirmed,
                                       command=self.update_publish_button)
        self.confirm.pack(anchor='w', pady=5)
        actions = ttk.Frame(self.review); actions.pack(fill='x', pady=10)
        self._button(actions, '設定に戻る', lambda: self.show_panel(self.edit), side='left')
        self.publish_button = self._button(actions, 'この内容で登録', self.publish, side='right')

    def show_panel(self, panel):
        for current in (self.home,self.edit,self.review): current.pack_forget()
        panel.pack(fill='both', expand=True)

    def show_home(self):
        if self.process: return
        self.show_panel(self.home)
        self.drafts.delete(*self.drafts.get_children()); self.versions.delete(*self.versions.get_children())
        self.draft_paths = {}; self.version_rows = {}
        for path in sorted((self.app_root/'template-drafts').iterdir()):
            if not path.is_dir() or path.name.startswith('.'): continue
            try:
                draft = self.api.load_template_draft(path)
                if draft.data['registered']: continue
                label, status = draft.data['name'] or '名前未入力', '下書き'
            except Exception as exc:
                label, status = path.name, '読込不可: '+str(exc)
            self.draft_paths[path.name] = path
            self.drafts.insert('', 'end', iid=path.name, values=(label,status))
        for index, row in enumerate(self.api.list_template_versions(self.app_root)):
            key = str(index); self.version_rows[key] = row
            self.versions.insert('', 'end', iid=key, values=(row['name'],row['version'],
                '読込不可: '+row['error'] if row['error'] else '保存済み' if row['has_sample'] else '選択が必要'))
        self.status.set('新規作成、下書き再開、登録済みから改訂を選んでください。')

    def new(self):
        if self.process: return
        source = self.files.askdirectory(parent=self.window, title='見本のReviewed保存フォルダーを選択')
        if not source: return
        name = self.dialog.askstring('新規作成','テンプレート名',parent=self.window)
        if name is None: return
        self.run_job('create', dict(app_root=str(self.app_root), reviewed_dir=source, name=name), self.adopt_job)

    def resume(self):
        if self.process: return
        selection = self.drafts.selection()
        if selection:
            try: self.adopt(self.api.load_template_draft(self.draft_paths[selection[0]]))
            except Exception as exc: self.error(exc)

    def revise(self):
        if self.process: return
        selection = self.versions.selection()
        if not selection: return
        row = self.version_rows[selection[0]]
        if row['error']: self.error(row['error']); return
        args = dict(app_root=str(self.app_root), base_template_dir=row['path'])
        if not row['has_sample']:
            source = self.files.askdirectory(parent=self.window, title='この従来テンプレートに対応するReviewedを選択')
            if not source: return
            args['reviewed_dir'] = source
        self.run_job('create', args, self.adopt_job)

    def adopt_job(self, result):
        self.adopt(self.api.load_template_draft(result['root']))

    def adopt(self, draft):
        self.draft = draft; self.settings = copy.deepcopy(draft.data['settings']); self.dirty = False
        self.filling = True; self.name.set(draft.data['name']); self.filling = False
        self.name_entry.configure(state='readonly' if draft.data['base_template_id'] else 'normal')
        self.snapshot = self.api._snapshot(draft, fresh=False) if draft.data['generation'] else None
        try: self.examples = self.api.rectangle_examples(draft.root)
        except ValueError: self.examples = {}
        self.selected = next(iter(self.settings), None); self.page = 1
        self.fill_tree(); self.fill_form(); self.show_panel(self.edit)
        self.status.set(' / '.join(draft.data['notices']) or '矩形を選び、項目名を入力してください。')
        self.render_page()

    def ordered(self):
        return sorted(self.settings, key=lambda uid:self.settings[uid]['order'])

    def locations(self):
        if not self.snapshot: return {}
        return {rect['uid']:(page,rect) for page in self.snapshot['pages'] for rect in page['rectangles']}

    def fill_tree(self):
        self.fields.delete(*self.fields.get_children())
        locations = self.locations()
        for index, uid in enumerate(self.ordered(), 1):
            s = self.settings[uid]; page,_ = locations[uid]
            self.fields.insert('', 'end', iid=uid, values=(index,s['name'] or '未入力',s['purpose'],page['page']))
        if self.selected in self.settings: self.fields.selection_set(self.selected)

    def fill_form(self):
        self.filling = True
        setting = self.settings.get(self.selected, self.api._default())
        for var,key in [(self.field_name,'name'),(self.purpose,'purpose'),(self.expected,'expected'),
                        (self.required,'required'),(self.join,'join')]: var.set(setting[key])
        if self.selected:
            number = self.ordered().index(self.selected) + 1
            self.field_heading.configure(text=f'矩形{number}の設定')
        else: self.field_heading.configure(text='Viewerで矩形を追加して再読込してください。')
        example = self.examples.get(self.selected, {})
        self.example.set('取得例: '+str(example.get('value') if example.get('value') is not None else '候補なし'))
        self.filling = False; self.purpose_visibility(); self.draw()
        self.form_canvas.yview_moveto(0)

    def purpose_visibility(self):
        if self.purpose.get() == '適用判定':
            self.required_box.pack_forget()
            self.expected_row.pack(fill='x', before=self.details_toggle)
        else:
            self.expected_row.pack_forget()
            self.required_box.pack(anchor='w', pady=6, before=self.details_toggle)

    def toggle_details(self):
        if self.details_open.get(): self.details.pack(fill='x', pady=5)
        else: self.details.pack_forget()

    def tree_select(self, event=None):
        if self.process: return
        selection = self.fields.selection()
        if not selection or selection[0] == self.selected: return
        self.selected = selection[0]
        page = self.locations()[self.selected][0]['page']
        self.fill_form()
        if page != self.page: self.page = page; self.render_page()

    def changed(self, *args):
        if self.filling or self.draft is None: return
        if self.selected in self.settings:
            s = self.settings[self.selected]
            if self.purpose.get() == '適用判定' and s['purpose'] != '適用判定' and not self.expected.get():
                value = self.examples.get(self.selected, {}).get('value')
                self.filling = True; self.expected.set(value.strip() if isinstance(value,str) else ''); self.filling = False
            s.update(name=self.field_name.get(), purpose=self.purpose.get(), expected=self.expected.get(),
                     required=self.required.get(), join=self.join.get())
            index = self.ordered().index(self.selected)+1
            self.fields.item(self.selected, values=(index,s['name'] or '未入力',s['purpose'],self.locations()[self.selected][0]['page']))
            self.purpose_visibility(); self.draw()
        self.dirty = True; self.status.set('未保存の変更があります。')
        if self.save_timer: self.window.after_cancel(self.save_timer)
        self.save_timer = self.window.after(650, self.autosave)

    def autosave(self):
        self.save_timer = None
        if self.process:
            self.save_timer = self.window.after(650, self.autosave); return
        self.save(quiet=True)

    def save(self, quiet=False):
        if self.process: return False
        if not self.draft or not self.dirty: return True
        try:
            self.draft = self.api.update_template_draft(self.draft.root, settings=self.settings,
                name=self.name.get(), expected_revision=self.draft.revision)
            self.dirty = False; self.status.set('下書き保存済み')
            try: self.examples = self.api.rectangle_examples(self.draft.root)
            except ValueError: pass
            self.fill_form()
            return True
        except Exception as exc:
            self.status.set('未保存: '+str(exc))
            if not quiet: self.error(exc)
            return False

    def reorder(self, direction):
        if not self.selected or self.process: return
        order = self.ordered(); index = order.index(self.selected); other = index+direction
        if not 0 <= other < len(order): return
        order[index],order[other] = order[other],order[index]
        for number,uid in enumerate(order,1): self.settings[uid]['order'] = number
        self.fill_tree(); self.changed()

    def refresh(self):
        if not self.draft or self.process or not self.save(): return
        self.run_job('refresh', dict(draft_dir=str(self.draft.root), expected_revision=self.draft.revision), self.adopt_job)

    def open_viewer(self):
        if not self.draft or self.process or not self.save(): return
        try:
            os.startfile(self.draft.working_xdw)
            self.status.set('Viewerで矩形を編集し、保存して閉じてから「保存後に再読込」を押してください。')
        except OSError as exc: self.error('XDWを開けませんでした。DocuWorksの関連付けを確認してください。 '+str(exc))

    def back_home(self):
        if not self.process and self.save():
            self.draft = None; self.show_home()

    def change_page(self, delta):
        if not self.draft or self.process: return
        from .reviewed import load_reviewed_result
        count = len(load_reviewed_result(self.draft.root/'sample-reviewed').pages)
        if 1 <= self.page+delta <= count: self.page += delta; self.render_page()

    def render_page(self):
        if not self.draft or self.process: return
        self.image = None; self.canvas.delete('all')
        self.run_job('render', dict(draft_dir=str(self.draft.root), page=self.page), self.rendered)

    def rendered(self, value):
        from PIL import Image
        with Image.open(value['path']) as image: self.image = image.convert('RGB')
        self.page_mm = (value['page_width_mm'],value['page_height_mm'])
        from .reviewed import load_reviewed_result
        count = len(load_reviewed_result(self.draft.root/'sample-reviewed').pages)
        self.page_label.configure(text=f'{self.page} / {count} ページ'); self.draw()

    def draw(self):
        if self.image is None: return
        from PIL import ImageTk
        width,height = self.image.size
        fit = min(max(100,self.canvas.winfo_width()-34)/width,max(100,self.canvas.winfo_height()-34)/height)
        scale = fit if self.zoom.get()=='全体' else int(self.zoom.get().rstrip('%'))/100 * 96/150
        w,h = max(1,round(width*scale)),max(1,round(height*scale))
        self.photo = ImageTk.PhotoImage(self.image.resize((w,h)), master=self.window)
        self.canvas.delete('all'); self.canvas.create_image(16,16,image=self.photo,anchor='nw')
        self.canvas.configure(scrollregion=(0,0,w+32,h+32)); self.boxes = {}
        for uid,(page,rect) in self.locations().items():
            if page['page']!=self.page: continue
            x=16+rect['x']/self.page_mm[0]*w; y=16+rect['y']/self.page_mm[1]*h
            x2=x+rect['width']/self.page_mm[0]*w; y2=y+rect['height']/self.page_mm[1]*h
            self.boxes[uid]=(x,y,x2,y2)
            self.canvas.create_rectangle(x,y,x2,y2,outline='#1264b5',width=3 if uid==self.selected else 1,
                dash=(5,3) if self.settings[uid]['purpose']=='適用判定' else ())
            self.canvas.create_text(x+3,max(9,y-10),text=str(self.ordered().index(uid)+1),fill='#064a91',anchor='w')

    def canvas_select(self, event):
        if self.process: return
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        hits=[uid for uid,(x1,y1,x2,y2) in getattr(self,'boxes',{}).items() if x1<=x<=x2 and y1<=y<=y2]
        if hits:
            # Repeated clicks cycle overlapping rectangles; every range stays selectable.
            uid=hits[(hits.index(self.selected)+1)%len(hits)] if self.selected in hits else hits[0]
            self.fields.selection_set(uid); self.fields.see(uid)

    def check(self):
        if self.process or not self.draft or not self.save(): return
        self.run_job('preview', dict(draft_dir=str(self.draft.root)), self.checked)

    def checked(self, result):
        from ._template_messages import diagnostic_message, LABELS
        self.preview = result; self.confirmed.set(False)
        self.result_heading.configure(text=self.draft.data['name']+' の取得結果')
        self.result_rows.delete(*self.result_rows.get_children()); notes=[]
        for row in result['conditions']:
            self.result_rows.insert('', 'end', values=(row['name'],str(row['value']), '一致' if row['matched'] else '不一致'))
            if not row['matched']: notes.append(row['name']+'：期待文字 '+repr(row['expected']))
        for row in result['fields']:
            self.result_rows.insert('', 'end', values=(row['name'],row['value'] if row['value'] is not None else '',LABELS.get(row['status'],row['status'])))
        for code in result['diagnostics']: notes.append(diagnostic_message(code))
        for row in result['conditions']+result['fields']:
            notes.extend(row['name']+'：'+diagnostic_message(code) for code in row['diagnostics'])
        self.diagnostics.configure(state='normal'); self.diagnostics.delete('1.0','end')
        self.diagnostics.insert('1.0','\n'.join(notes) if notes else '確認事項はありません。'); self.diagnostics.configure(state='disabled')
        self.confirm.configure(state='normal' if result['warnings'] and result['applicable'] else 'disabled')
        self.update_publish_button(); self.show_panel(self.review)

    def update_publish_button(self):
        enabled=self.preview and self.preview['applicable'] and (not self.preview['warnings'] or self.confirmed.get())
        self.publish_button.configure(state='normal' if enabled else 'disabled')

    def publish(self):
        if self.process or not self.draft: return
        self.run_job('publish', dict(draft_dir=str(self.draft.root), app_root=str(self.app_root),
            expected_revision=self.draft.revision, confirm_warnings=self.confirmed.get()), self.published)

    def published(self, result):
        self.draft = None; self.show_home()
        self.status.set('登録完了: '+result['root'])
        if self.messages.askyesno('登録完了', '新しい版を登録しました。\n'+result['root']+'\n\n保存フォルダーを開きますか？', parent=self.window):
            os.startfile(result['root'])

    def run_job(self, operation, arguments, callback):
        if self.process: return
        requests = self.app_root/'template-drafts'/'.requests'; requests.mkdir(exist_ok=True)
        key=uuid.uuid4().hex
        request=requests/(key+'.request.json'); response=requests/(key+'.response.json')
        request.write_text(json.dumps(dict(operation=operation,arguments=arguments),ensure_ascii=False),encoding='utf-8')
        # Source checkouts and installed wheels use the same isolated child entry.
        bootstrap='import sys; sys.path.insert(0,sys.argv.pop(1)); from docuworks_integrations._template_editor_worker import main; raise SystemExit(main())'
        args=[sys.executable,'-I','-B','-X','utf8','-c',bootstrap,str(Path(__file__).resolve().parent.parent),str(request),str(response)]
        self.job_log = (requests/(key+'.log')).open('wb')
        try:
            self.process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=self.job_log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception as exc:
            self.job_log.close(); self.error(exc); return
        self.set_busy(True)
        self.status.set({'create':'見本と作業用XDWを準備しています…','refresh':'矩形を再読込しています…',
            'render':'ページ画像を準備しています…','preview':'取得結果を確認しています…','publish':'保存・再読込を検証して登録しています…'}[operation])
        self.window.configure(cursor='watch')
        def poll():
            if self.closed: return
            if self.process.poll() is None:
                self.window.after(100,poll); return
            self.process=None; self.job_log.close(); self.window.configure(cursor='')
            self.set_busy(False)
            try:
                if not response.is_file(): raise RuntimeError('処理が終了しましたが結果を取得できませんでした。下書きを再開してください。')
                result=json.loads(response.read_text(encoding='utf-8'))
                if not result['ok']: raise RuntimeError(result['error'])
                self.status.set('処理が完了しました。'); callback(result['value'])
            except Exception as exc: self.error(exc)
        self.window.after(100,poll)

    def set_busy(self, busy):
        """Freeze editable controls while a child owns the draft generation."""
        if busy:
            self.control_states = []
            def visit(parent):
                for widget in parent.winfo_children():
                    if isinstance(widget, (self.ttk.Button, self.ttk.Entry, self.ttk.Combobox,
                                           self.ttk.Checkbutton, self.ttk.Treeview)):
                        self.control_states.append((widget, widget.state()))
                        widget.state(['disabled'])
                    visit(widget)
            visit(self.container)
        else:
            for widget, state in self.control_states:
                widget.state(['!disabled', '!readonly', *state])
            self.control_states = []

    def error(self, error):
        self.status.set('処理できませんでした: '+str(error))
        self.messages.showerror('テンプレート作成',str(error),parent=self.window)

    def close(self):
        if self.process:
            if not self.messages.askyesno('終了','実行中の処理を中断して終了しますか？下書きは残ります。',parent=self.window): return
            self.process.terminate(); self.process.wait(timeout=10); self.job_log.close(); self.process=None
        if not self.save(): return
        if self.save_timer: self.window.after_cancel(self.save_timer)
        self.closed=True; self.window.destroy()


def launch(app_root):
    import tkinter as tk
    root=tk.Tk()
    try:
        Editor(root, app_root)
        root.mainloop()
    finally:
        try: root.destroy()
        except tk.TclError: pass
    return 0
