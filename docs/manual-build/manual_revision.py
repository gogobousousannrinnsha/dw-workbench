"""Three-layer manual layout: introduction, reference, evidence appendix."""
from pathlib import Path
import json
import html
from reportlab.platypus import Paragraph, Spacer, KeepTogether, PageBreak, LongTable, TableStyle, Flowable, IndexingFlowable
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib import colors
from reportlab.lib.units import mm
import build_manual as b

PARTS = [("preparation", "入門1　起動前の準備"), ("decisions", "入門2　最初に決めること"),
         ("quickstart", "入門3　一ページからExcelの一行へ"),
         ("states", "入門4　保存・確認・終了・再開"), ("workflows", "目的別の操作手順")]

def order_figures(model):
    order=['beginner-preparation','beginner-decisions']+['beginner-'+s['id'] for s in model['beginner']['steps']]+list(b.SECTION_NAMES)+['dialogs']
    rank={key:i for i,key in enumerate(order)}
    model['figures']=sorted([f for f in model['figures'] if f.section in rank],key=lambda f:rank[f.section])
    for number,figure in enumerate(model['figures'],1): figure.number=number
    return model

def sample_files(model):
    demo = model["demo"]
    files = [("練習する原本XDW", demo.get("input")),
             ("完成したExcel見本", demo.get("xlsx")), ("完成したCSV見本", demo.get("csv"))]
    result=[]
    for label, raw in files:
        if raw and (b.ROOT / raw).is_file():
            p=(b.ROOT / raw).resolve()
            if p.is_relative_to(b.ROOT): result.append((label,p.relative_to(b.ROOT).as_posix()))
    return result

def semantic_blocks(content):
    """Keep the same beginner text in HTML and PDF."""
    result=[]
    for p in content.get("paragraphs", []): result.append(("", p, False))
    if content.get("lead"): result.append(("", content["lead"], False))
    if content.get("comparison"):
        for c in content["comparison"]:
            result.append((c["choice"], ["使うテンプレート："+c["template"], "表の一行："+c["row"], c["example"]], False))
    if content.get("shared_definition"):
        d=content["shared_definition"]
        result.append(("共通の項目定義", d["name"]+"　版"+str(d["version"]), False))
        result.append(("表に出す項目", [f'{f["name"]}：{f["kind"]}・{f["required"]}／例 {f["example"]}{f["unit"]}' for f in d["fields"]], False))
    for c in content.get("layouts", []): result.append((c["name"], c["template_name"]+"："+c["position_example"], False))
    for label,key,ordered in [("使う場所","layout",False),("確認","checklist",False),("操作前","before",False),
                              ("操作","actions",True),("成功した状態","success",False),
                              ("配置Bを追加する際の手順","how_to_share",True),("操作後","result",False),
                              ("注意","notes",False),("困ったら","trouble",False)]:
        val=content.get(key)
        if val:
            if key=="layout": val=[r["item"]+"："+r["role"] for r in val]
            result.append((label,val,ordered))
    return result

def versions(model):
    cat=model["catalog"]
    return ["対象：DW-Workbench v0.2.0 ローカル検証候補。説明書改訂日：2026年10月3日。",
            f'収録：{len(model["controls"])}操作、{len(model["dialogs"])}のダイアログ・通知・関連操作、{len(model["workflows"])}の目的別手順、{len(model["glossary"])}用語。',
            b.image_inventory_text(model),
            "入門のUI構成図は同じ一ページ・二項目の例を示します。リファレンスの撮影済み実画面は別の三ページ・四項目の合成案件です。",
            "入門Excelは現行アプリの出力処理で生成し、別の読取ライブラリで35項目を照合しました。Excel表示図は実セル値から作成した図で、Excelアプリの撮影画像ではありません。",
            "操作カタログ作成は静的確認のみ。その後の別工程で、合成サンプルの実画面9枚を撮影しました。本改訂では前面のPC操作や再撮影を行っていません。",
            "原本となるコード："+b.plain(cat.get("source_file")), "コード SHA256："+b.plain(cat.get("source_sha256"))]

def build_html(model,target):
    intro=model["beginner"]; controls={c["id"]:c for c in model["controls"]}
    nav=PARTS+[(k,"参照　"+v) for k,v in b.SECTION_NAMES.items()]+[("dialogs","参照　ダイアログ・通知・関連操作"),("troubleshooting","参照　困ったとき"),("glossary","参照　用語"),("version","付録　版と検証範囲")]
    pieces=['<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',f'<title>{b.esc(b.TITLE)}</title><style>{b.CSS}</style></head><body>',f'<header><h1>{b.esc(b.TITLE)}</h1><p>入門 → 操作リファレンス → 検証付録</p><p>一ページの部品番号000125と測定温度179.8℃を、Excelの一行にする</p></header>', '<div class="layout"><aside><label class="search-label" for="manual-search">説明書内を検索</label><input id="manual-search" type="search" placeholder="例：確認11、草案、部分出力"><p id="search-status"></p><nav aria-label="目次">', ''.join(f'<a href="#{k}">{b.esc(v)}</a>' for k,v in nav), '</nav><p class="offline">外部接続不要。説明書フォルダー一式を保持してください。</p></aside><main>']
    def start(key,title): pieces.append(f'<section id="{key}" class="chapter"><h2>{b.esc(title)}</h2>')
    def end(): pieces.append('</section>')
    def figs(section): pieces.extend(b.html_figure(f,controls) for f in model["figures"] if f.section==section)
    def blocks(content):
        for label,val,ordered in semantic_blocks(content): pieces.append(b.html_field(label,val,ordered) if label else '<p>'+b.esc(val)+'</p>')
    def refs(ids):
        if ids: pieces.append('<p>詳しい操作：'+' / '.join(f'<a href="#{r}">{b.esc(b.annotation_id(r))} {b.esc(b.control_title(controls[r]))}</a>' for r in ids)+'</p>')
    start(*PARTS[0]); pieces.append('<p>初めて使う場合は、この入門1から順番に読みます。操作中の調べ直しは「参照」、資料の根拠確認は「付録」を使います。</p>')
    for item in intro["preparation"]:
        pieces.append(f'<article id="prep-{item["id"]}" class="flow-card search-item"><h3>{b.esc(item["title"])}</h3>');blocks(item);refs(item.get("control_refs",[]));pieces.append('</article>')
    figs("beginner-preparation");end()
    start(*PARTS[1])
    for item in intro["decisions"]:
        pieces.append(f'<article id="decision-{item["id"]}" class="flow-card search-item"><h3>{b.esc(item["title"])}</h3>');blocks(item);refs(item.get("control_refs",[]));pieces.append('</article>')
    figs("beginner-decisions");end()
    start(*PARTS[2]);pieces.extend('<p>'+b.esc(p)+'</p>' for p in intro["lead"])
    pieces.append('<p class="notice">この経路はOCRを使わずに進められます。練習用原本と、現行アプリで生成した完成見本を同梱しています。</p>')
    pieces.append('<p>'+ ' / '.join(f'<a href="{b.esc(b.quote(p,safe="/"))}">{b.esc(label)}</a>' for label,p in sample_files(model))+'</p>')
    example=intro["worked_example"]
    pieces.append(b.html_field("例の条件",["案件名："+example["project_name"],"原本："+example["source_name"]+"（一ページ）","処理単位："+example["mode"],"テンプレート："+example["template_name"],"項目定義："+example["schema_name"]]))
    for item in intro["steps"]:
        pieces.append(f'<article id="{item["id"]}" class="flow-card search-item"><h3>{b.esc(item["title"])}</h3>');blocks(item);figs("beginner-"+item["id"]);refs(item.get("control_refs",[]));pieces.append('</article>')
    pieces.append('<article id="beginner-ocr" class="flow-card search-item"><h3>'+b.esc(intro["optional_ocr"]["title"])+'</h3>');blocks(intro["optional_ocr"]);refs(intro["optional_ocr"].get("control_refs",[]));pieces.append('</article>');end()
    start(*PARTS[3])
    for state in intro["state_guide"]:
        pieces.append(f'<article class="gloss-card search-item"><h3>{b.esc(state["term"])}</h3><p>{b.esc(state["meaning"])}</p><p>次の操作：{b.esc(state["next_action"])}</p><p class="note">{b.esc(state["guarantee_boundary"])}</p></article>')
    for flow in model["workflows"]:
        if "save" in flow["id"] or "draft" in flow["id"]: pieces.append('<p>保存・終了・再開：<a href="#flow-'+b.esc(flow["id"])+'">'+b.esc(flow["title"])+'</a></p>')
    end();start(*PARTS[4])
    for i,flow in enumerate(model["workflows"],1):
        pieces.append(f'<article id="flow-{flow["id"]}" class="flow-card search-item"><h3>手順{i:02d} {b.esc(flow["title"])}</h3>');pieces.append(b.html_field("操作",flow["steps"],True));pieces.append(b.html_field("操作後",flow["result"]));pieces.append(b.html_field("注意",b.public_notes(flow)));pieces.append('</article>')
    end()
    for key,title,group in model["sections"]:
        start(key,"操作リファレンス　"+title)
        if key=="common": pieces.append('<p>ここからは調べたい操作を引く部分です。図の番号・操作番号を押すと各説明へ移動できます。実画面の三ページ案件は、前の入門用一ページ案件とは別の例です。</p>')
        figs(key);pieces.append('<div class="index-links">'+''.join(f'<a href="#{c["id"]}">{b.esc(b.annotation_id(c["id"]))}</a>' for c in group)+'</div>')
        for c in group:
            pieces.append(f'<article id="{c["id"]}" class="control search-item"><h3><span class="badge">{b.esc(b.annotation_id(c["id"]))}</span>{b.esc(b.control_title(c))}</h3><p class="kind">{b.esc(b.KIND_NAMES.get(c["kind"],c["kind"]))}</p>')
            for keyfield,label in b.FIELDS: pieces.append(b.html_field(label,b.public_notes(c) if keyfield=="notes" else c.get(keyfield),keyfield=="steps"))
            pieces.append('</article>')
        end()
    start("dialogs","ダイアログ・通知・関連操作");figs("dialogs")
    for i,d in enumerate(model["dialogs"],1):
        pieces.append(f'<article id="dialog-{d["id"]}" class="dialog-card search-item"><h3>対話{i:02d} {b.esc(d["title"])}</h3>');pieces.append(b.html_field("役割",d.get("purpose")))
        if d.get("when"): pieces.append(b.html_field("使う場面",d["when"]))
        for c in d.get("controls",[]): pieces.append('<p><strong>'+b.esc(c.get("label"))+'</strong>：'+b.esc(c.get("purpose"))+'</p>')
        pieces.extend([b.html_field("操作",d.get("steps",[]),True),b.html_field("操作後",d.get("result")),b.html_field("注意",b.public_notes(d)),'</article>'])
    end();start("troubleshooting","困ったとき")
    for i,(title,text,ids) in enumerate(b.TROUBLESHOOTING,1): pieces.append(f'<article id="trouble-{i}" class="trouble-card search-item"><h3>{b.esc(title)}</h3><p>{b.esc(text)}</p>');refs(ids);pieces.append('</article>')
    end();start("glossary","用語")
    for i,t in enumerate(model["glossary"],1): pieces.append(f'<article id="term-{i}" class="gloss-card search-item"><h3>{b.esc(t["term"])}</h3><p>{b.esc(t["definition"])}</p></article>')
    end();start("version","検証付録　版情報と根拠")
    pieces.extend('<p>'+b.esc(p)+'</p>' for p in versions(model))
    for c in intro["method_and_scope"]["classifications"]:
        pieces.append('<h3>'+b.esc(c["category"])+'</h3>');pieces.append(b.html_field("対象",c["target"]));pieces.append(b.html_field("確認状況",c["status"]));pieces.append(b.html_field("確認の限界",c["does_not_prove"]))
    pieces.append(b.html_field("初版の範囲",intro["method_and_scope"]["scope"]));pieces.append(b.html_field("含めない機能",intro["method_and_scope"]["out_of_scope"]))
    # Original source correspondence, without the ambiguous old method summary.
    source=b.html_version(model);source=source[source.index('<details>'):];pieces.append(source);end()
    pieces+=['</main></div><dialog id="image-zoom"><button class="zoom-button close-zoom" type="button">閉じる</button><p class="zoom-title"></p><div class="zoom-content"></div></dialog>',f'<script>{b.JS}</script></body></html>']
    target.write_text(''.join(pieces),encoding='utf-8')

class StablePageMap(IndexingFlowable):
    def __init__(self,doc): Flowable.__init__(self);self.doc=doc
    def isSatisfied(self): return bool(self.doc.previous_page_map) and self.doc.previous_page_map==self.doc.page_map
    def wrap(self,w,h): return 0,0
    def draw(self): pass

class References(Flowable):
    def __init__(self,ids,doc,styles,controls): Flowable.__init__(self);self.ids=ids;self.doc=doc;self.styles=styles;self.controls=controls
    def wrap(self,w,h):
        texts=[]
        for r in self.ids:
            page=self.doc.previous_page_map.get(r,self.doc.page_map.get(r))
            texts.append(f'<link href="#{r}" color="#0955a1">{b.esc(b.annotation_id(r))} {b.esc(b.control_title(self.controls[r]))}（p.{page if page else "---"}）</link>')
        self.p=Paragraph('詳しい操作：'+' / '.join(texts),self.styles['small']);self.width,self.height=self.p.wrap(w,h);return self.width,self.height
    def draw(self): self.p.drawOn(self.canv,0,0)

def build_pdf(model,target,requested_font=None):
    font,font_path=b.japanese_font(requested_font);styles=b.pdf_styles(font);doc=b.ManualDoc(target,font);story=[]
    intro=model['beginner'];controls={c['id']:c for c in model['controls']}
    def p(text,style='body'): return Paragraph(b.esc(text).replace('\n','<br/>'),styles[style])
    def heading(text,bookmark=None,style='h2'):
        q=p(text,style)
        if bookmark:
            q.bookmark=bookmark
            q.operation_outline=True
        story.append(q)
    def chapter(key,title):
        story.append(PageBreak());q=p(title,'h1');q.bookmark=key;q.chapter_name=title
        if key!='contents': q.toc_level=0
        story.append(q)
    def field(label,val,ordered=False):
        if not val: return
        if label and not isinstance(val,list):
            story.append(Paragraph('<font color="#0955a1">'+b.esc(label)+'</font>　'+b.esc(val).replace('\n','<br/>'),styles['body']))
            return
        if label: story.append(Paragraph('<font color="#0955a1">'+b.esc(label)+'</font>',styles['fieldlabel']))
        for i,text in enumerate(b.as_list(val),1): story.append(p((f'{i}. ' if ordered else '・' if isinstance(val,list) else '')+b.plain(text)))
    def blocks(c):
        for label,val,ordered in semantic_blocks(c): field(label,val,ordered)
    def refs(ids):
        if ids: story.append(References(ids,doc,styles,controls))
    def figs(section):
        for f in model['figures']:
            if f.section!=section: continue
            block=[p(f'図{f.number}　{f.title}\n{f.evidence_label}','caption')]
            if f.path: block.append(b.CroppedFigure(f,font))
            else: block.append(p(f.error,'small'))
            if f.marks and f.kind!='source-diagram': block.append(p('番号：'+' / '.join(m['label']+' '+b.control_title(controls[m['id']]) for m in f.marks),'small'))
            block.append(Spacer(1,4*mm));story.append(KeepTogether(block))
    story.extend([Spacer(1,24*mm),p(b.TITLE,'title'),p('入門 → 操作リファレンス → 検証付録'),p('一ページの部品番号000125と測定温度179.8℃を、Excelの一行にする'),Spacer(1,8*mm),p('初めて使う方は、起動前の準備から順番に読みます。操作中は操作番号と検索、開発・保守では巻末付録を使います。'),p('116操作／25のダイアログ・通知・関連操作／7の目的別手順／29用語'),p('実画面・UI構成図・Excel表示図は、それぞれ出典を図に示しています。合成サンプルの結果であり、実帳票の精度や現地受け入れを保証する資料ではありません。','small')])
    chapter('contents','目次');toc=TableOfContents();toc.levelStyles=[styles['toc']];story.append(toc)
    chapter(*PARTS[0]);story.append(p('初めて使う場合は入門1から順番に読みます。操作の調べ直しには「参照」、資料の根拠確認には「付録」を使います。'))
    for item in intro['preparation']:
        start=len(story);heading(item['title'],'prep-'+item['id']);blocks(item);refs(item.get('control_refs',[]));story.append(Spacer(1,3*mm));story[start:]=[KeepTogether(story[start:])]
    figs('beginner-preparation')
    chapter(*PARTS[1])
    for item in intro['decisions']:
        heading(item['title'],'decision-'+item['id']);blocks(item);refs(item.get('control_refs',[]))
    figs('beginner-decisions')
    chapter(*PARTS[2]);story.extend(p(s) for s in intro['lead'])
    story.append(p('練習用原本は説明書フォルダーのsample-input、現行アプリで生成した完成Excel／CSV見本はsample-outputにあります。最初は「入門練習」という別案件を作り、練習用XDWを追加します。'))
    for label,path in sample_files(model):
        story.append(Paragraph('<link href="'+b.esc(b.quote(path,safe='/'))+'" color="#0955a1">'+b.esc(label)+'</link>　'+b.esc(path),styles['small']))
    story.append(p('二項目とも必須です。部品番号は文字列000125、測定温度は数値179.8、温度の単位は℃です。'))
    for item in intro['steps']:
        start=len(story);heading(item['title'],item['id']);blocks(item);refs(item.get('control_refs',[]));story.append(Spacer(1,3*mm));story[start:]=[KeepTogether(story[start:])]
        figs('beginner-'+item['id'])
    heading(intro['optional_ocr']['title'],'beginner-ocr');blocks(intro['optional_ocr']);refs(intro['optional_ocr'].get('control_refs',[]))
    chapter(*PARTS[3])
    for state in intro['state_guide']:
        start=len(story);heading(state['term']);story.extend(p(state[k]) for k in ['meaning','next_action','guarantee_boundary']);story[start:]=[KeepTogether(story[start:])]
    story.append(p('通常の保存失敗と、テンプレート草案の保存失敗では、再試行する操作が異なります。次の目的別手順で分けて説明します。'))
    chapter(*PARTS[4])
    for i,flow in enumerate(model['workflows'],1):
        start=len(story);heading(f'手順{i:02d}　'+flow['title'],'flow-'+flow['id']);field('操作',flow['steps'],True);field('操作後',flow['result']);field('注意',b.public_notes(flow));story.append(Spacer(1,4*mm))
        # Short workflows are kept as one operation. Long ones can flow to the next page.
        if len(flow['steps'])<=6: story[start:]=[KeepTogether(story[start:])]
    for key,title,group in model['sections']:
        chapter(key,'操作リファレンス　'+title)
        if key=='common': story.append(p('ここからは操作中に参照する部分です。図の番号と各操作番号が対応します。撮影済み実画面は三ページ・四項目の別の合成案件で、入門用一ページ案件とは異なります。'))
        figs(key)
        for c in group:
            start=len(story);heading(b.annotation_id(c['id'])+'　'+b.control_title(c),c['id']);story.append(p(b.KIND_NAMES.get(c['kind'],c['kind']),'kind'))
            for keyfield,label in b.FIELDS: field(label,b.public_notes(c) if keyfield=='notes' else c.get(keyfield),keyfield=='steps')
            story.append(Spacer(1,4*mm));story[start:]=[KeepTogether(story[start:])]
    chapter('dialogs','ダイアログ・通知・関連操作');figs('dialogs')
    for i,d in enumerate(model['dialogs'],1):
        start=len(story);heading(f'対話{i:02d}　'+d['title'],'dialog-'+d['id']);field('役割',d.get('purpose'));field('使う場面',d.get('when'))
        for c in d.get('controls',[]): story.append(p(b.plain(c.get('label'))+'：'+b.plain(c.get('purpose'))))
        field('操作',d.get('steps',[]),True);field('操作後',d.get('result'));field('注意',b.public_notes(d));story.append(Spacer(1,4*mm))
        story[start:]=[KeepTogether(story[start:])]
    chapter('troubleshooting','困ったとき')
    for i,(title,text,ids) in enumerate(b.TROUBLESHOOTING,1):
        start=len(story);heading(title,f'trouble-{i}');story.append(p(text));refs(ids);story.append(Spacer(1,3*mm));story[start:]=[KeepTogether(story[start:])]
    chapter('glossary','用語')
    for i,t in enumerate(model['glossary'],1):
        start=len(story);heading(t['term'],f'term-{i}','term');story.append(p(t['definition']));story[start:]=[KeepTogether(story[start:])]
    chapter('version','検証付録　版情報と根拠');story.extend(p(line,'small') for line in versions(model))
    for c in intro['method_and_scope']['classifications']:
        heading(c['category']);field('対象',c['target']);field('確認状況',c['status']);field('確認の限界',c['does_not_prove'])
    field('初版の範囲',intro['method_and_scope']['scope']);field('含めない機能',intro['method_and_scope']['out_of_scope'])
    heading('操作とソースの対応（開発・保守用）');story.append(p('以下は記述の追跡用です。手動で全操作を実行した証拠を示す表ではありません。','small'))
    rows=[[p('操作番号','table'),p('行','table'),p('呼び出す処理','table')]]
    for c in model['controls']:
        dev=[b.plain(n) for n in c['notes'] if b.DEV_NOTE.search(b.plain(n))]
        rows.append([p(b.annotation_id(c['id']),'table'),p(c['source_line'],'table'),p(b.plain(c['command'])+('\n'+'\n'.join(dev) if dev else ''),'table')])
    table=LongTable(rows,colWidths=[30*mm,11*mm,doc.width-41*mm],repeatRows=1,hAlign='LEFT');table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf5fb')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#cddae5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story.append(table)
    heading('資料の照合情報')
    for name in ['controls.json','dialogs.json','beginner_content.json','beginner_demo.json','verification.json','screenshots.json','figures.json','beginner_figure_manifest.json','workbook_view_manifest.json']:
        path=b.ROOT/name
        if path.is_file(): story.append(p(name+'：SHA256 '+b.sha256(path),'small'))
    story.append(StablePageMap(doc));doc.multiBuild(story,maxPasses=6)
    (b.ROOT/'page-map.json').write_text(json.dumps(doc.page_map,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return font_path
