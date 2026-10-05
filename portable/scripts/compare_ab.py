"""Compare explicitly selected A/B jobs; never silently select a latest run."""
import csv
import json
from pathlib import Path
import sys
import uuid


def load(path):
    path = Path(path)
    if path.is_dir(): path = path/'performance.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'dw-ocr-ab-performance':
        raise ValueError('A/B検証版のperformance.jsonを指定してください。')
    return data


def compare(a, b):
    if (a.get('variant'), b.get('variant')) != ('A', 'B'):
        raise ValueError('Aの結果、Bの結果の順で指定してください。')
    issues = []
    if a.get('status') != 'COMPLETE' or b.get('status') != 'COMPLETE':
        issues.append('未完了または失敗した実行を含みます')
    for key in ('settings', 'fingerprints', 'python'):
        if a.get(key) != b.get(key): issues.append(key+'が異なります')
    docs_a, docs_b = a.get('documents', []), b.get('documents', [])
    if not docs_a or not docs_b: issues.append('比較可能な文書がありません')
    if [d.get('source_sha256') for d in docs_a] != [d.get('source_sha256') for d in docs_b]:
        issues.append('入力文書または処理順が異なります')
    if [d.get('content_geometry_sha256') for d in docs_a] != [d.get('content_geometry_sha256') for d in docs_b]:
        issues.append('OCR結果が異なる比較です（文字数・本文・座標）')
    def seconds(data, phase):
        return sum(e['seconds'] for e in data['events'] if e['phase'] == phase)
    metrics = ['ocr', 'review', 'rectangles', 'text_maps', 'jsonl', 'review.create',
               'review.blank', 'review.text', 'review.save', 'review.merge',
               'review.save_final', 'review.inspect', 'preflight', 'postflight']
    rows = [dict(metric='total', A=a['elapsed_seconds'], B=b['elapsed_seconds'])]
    rows.extend(dict(metric=p, A=seconds(a,p), B=seconds(b,p)) for p in metrics)
    for row in rows:
        row.update(B_minus_A=row['B']-row['A'], B_over_A=row['B']/row['A'] if row['A'] else None)
    return dict(comparable=not issues, issues=issues, timings=rows,
                memory_A=a.get('memory'), memory_B=b.get('memory'),
                documents_A=docs_a, documents_B=docs_b,
                note='秒。親工程には子工程の時間を含みます。行の単純合計は全体時間になりません。')


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = [input('Aの実行フォルダー: ').strip().strip('"'), input('Bの実行フォルダー: ').strip().strip('"')]
    if len(args) not in (2, 3): raise ValueError('Aの実行フォルダー Bの実行フォルダー [出力フォルダー]')
    result = compare(load(args[0]), load(args[1]))
    output = Path(args[2]) if len(args)==3 else Path(args[0]).resolve().parent.parent/('comparison-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    (output/'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (output/'comparison.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=('metric', 'A', 'B', 'B_minus_A', 'B_over_A'))
        writer.writeheader(); writer.writerows(result['timings'])
    lines = ['A/B比較結果', '入力・設定・記録した環境情報が一致' if result['comparable'] else '比較条件に相違があります',
             *result['issues'], '', result['note'],
             '初回起動・OS/GPUキャッシュ・他プロセスの負荷は一致を保証しません。工程別に反復して比較してください。', '']
    lines += [f"{r['metric']}: A={r['A']:.3f}s / B={r['B']:.3f}s" for r in result['timings']]
    lines += ['', 'メモリは当該プロセスのWorking Set採取最大値（GPUメモリを除く）です。']
    for variant in ('A','B'):
        memory=result['memory_'+variant] or {}
        peak=memory.get('sampled_peak_bytes')
        lines.append(variant+' メモリ: '+(f'{peak/1024**2:.1f} MiB' if peak is not None else '取得不可'))
        for doc in result['documents_'+variant]:
            lines.append(f"{variant} {doc.get('source_name','')}: {doc.get('pages','?')}ページ / "
                         f"{doc.get('items','?')}項目 / XDW {doc.get('review_xdw_bytes','?')} bytes")
    (output/'comparison.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8-sig')
    print('\n'.join(lines)); print('保存先: '+str(output))
    return 0 if result['comparable'] else 2


if __name__ == '__main__':
    try: code = main()
    except (KeyboardInterrupt, EOFError): code = 130
    except Exception as exc: code = 1; print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
    raise SystemExit(code)
