"""CSV contracts against real, validated Structured bundles and fake SDK input."""
import codecs
import copy
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

from docuworks_integrations import structured_csv as c, structured as s, reviewed as r, templates as t
from docuworks_integrations.cli import main
from test_structured import inputs
from test_reviewed import read, write, hashes


def fixture(tmp_path, monkeypatch, version='2.0', *, names=('温度', '部品番号')):
    template, reviewed, run, session = inputs(tmp_path, monkeypatch, version)
    data = template.data
    temperature = data['pages'][0]['rectangles'][0]
    temperature.update(name=names[0], output_order=2)
    part = dict(temperature, name=names[1], output_order=1, annotation_order=2,
                rectangle_id='p0001-a000002', y=5)
    data['pages'][0]['rectangles'].append(part)
    condition = dict(temperature, name='帳簿名', output_order=None, annotation_order=1,
                     rectangle_id='p0002-a000001', x=0, y=0, width=18, height=18,
                     purpose='condition', expected='帳簿A')
    data['pages'][1]['rectangles'] = [condition]
    write(template.root/'template.json', data); r._write_manifest(template.root,t.SCHEMA,t.FILES)
    template = t.load_rectangle_template(template.root)
    raw = read(session.review_xdw)
    seed = raw['pages'][0]['items'][0]
    raw['pages'][0]['items'] = [dict(seed,text='80℃'), dict(seed,text='001234',y=6)]
    raw['pages'][1]['items'] = [dict(seed,text='帳簿A')]
    counter = 0
    def take(mode='ok', *, value=None, template_override=None):
        nonlocal counter
        counter += 1
        source = copy.deepcopy(raw)
        if mode == 'missing': source['pages'][0]['items'].pop(1)
        if mode == 'empty': source['pages'][0]['items'][1]['text'] = ''
        if mode == 'whitespace': source['pages'][0]['items'][1]['text'] = ' \r\n\t'
        if mode == 'vertical': source['pages'][0]['items'][1]['direction'] = 1
        if mode == 'rotated': source['pages'][0]['items'][1]['rotation'] = 30
        if mode == 'foreign-origin': source['pages'][0]['items'][1]['identity'] = {'invalid':'data'}
        if mode == 'condition': source['pages'][1]['items'][0]['text'] = '別帳簿'
        if mode == 'page-size': source['pages'][0]['width_mm'] += 1
        if value is not None: source['pages'][0]['items'][1]['text'] = value
        write(session.review_xdw,source)
        reviewed = r.import_reviewed_result(session.root,session.review_xdw,tmp_path/f'reviewed-{counter}',
                                            validation_mode='identity' if version=='2.0' else 'strict')
        return s.apply_rectangle_template(template_override or template.root,reviewed.root,tmp_path/f'result-{counter}')
    return take, template, run, session


def export(results, output, names=None):
    return c.export_structured_csv(results,output,document_names=names or {
        result.result_id: f'帳簿{index:03}.xdw' for index,result in enumerate(results,1)})


def records(path):
    # newline='' is essential: do not normalize embedded CR/LF from the original text.
    with path.open(encoding='utf-8-sig',newline='') as stream: return list(csv.reader(stream))


@pytest.mark.parametrize('version', ['1.0','2.0'])
def test_fixed_columns_statuses_and_immutable_inputs(tmp_path, monkeypatch, version):
    take, template, run, session = fixture(tmp_path,monkeypatch,version)
    results = [take(),take('missing'),take('condition')]
    roots = [run.root,session.root,template.root,*[result.root for result in results]]
    before = [hashes(root) for root in roots]
    output = export(results,tmp_path/'帳簿A.csv')
    data = records(output)
    assert data[0] == ['文書名','処理結果','部品番号','温度','確認事項','結果ID']
    assert [row[:4] for row in data[1:]] == [['帳簿001.xdw','正常','001234','80℃'],
        ['帳簿002.xdw','要確認','','80℃'],['帳簿003.xdw','適用不可','','']]
    assert data[1][4] == '' and '候補なし' in data[2][4]
    assert '帳簿名' in data[3][4] and '別帳簿' in data[3][4]
    assert [row[-1] for row in data[1:]] == [result.result_id for result in results]
    assert [hashes(root) for root in roots] == before
    expected = io.StringIO(newline='')
    csv.writer(expected,quoting=csv.QUOTE_ALL,lineterminator='\r\n').writerows(data)
    assert output.read_bytes() == codecs.BOM_UTF8 + expected.getvalue().encode('utf-8')


@pytest.mark.parametrize('value', ['001234','1E10','1-2','80℃','部品,"番号"\n続き\r\n次\r末',' =SUM(1,2)','𠮷😀'])
def test_preserves_values_without_type_conversion_or_formula_wrapping(tmp_path, monkeypatch, value):
    take, *_ = fixture(tmp_path,monkeypatch)
    result = take(value=value)
    label = '帳簿,"A".xdw'
    output = export([result],tmp_path/'result.csv',{result.result_id:label})
    row = records(output)[1]
    assert row[0] == label and row[2] == value
    assert result.data['fields'][0]['value'] == value


@pytest.mark.parametrize('mode,reason', [('missing','候補なし'),('empty','空文字'),('whitespace','空文字'),
    ('vertical','縦書き'),('rotated','回転文字'),('foreign-origin','由来情報が不正'),('page-size','ページ寸法')])
def test_reasons_distinguish_empty_missing_and_unsupported(tmp_path, monkeypatch, mode, reason):
    take, *_ = fixture(tmp_path,monkeypatch)
    result = take(mode)
    row = records(export([result],tmp_path/'result.csv'))[1]
    assert reason in row[4]
    if mode == 'whitespace': assert row[2] == ' \r\n\t'
    elif mode == 'foreign-origin': assert row[2] == '001234' and row[1] == '正常'
    else: assert row[2] == ''


def test_only_inapplicable_results_still_have_all_template_columns(tmp_path, monkeypatch):
    take, *_ = fixture(tmp_path,monkeypatch)
    results = [take('page-size'), take('condition')]
    data = records(export(results,tmp_path/'result.csv'))
    assert data[0][2:4] == ['部品番号','温度']
    assert len(data) == 3 and all(row[2:4] == ['',''] for row in data[1:])


def test_header_collisions_do_not_rename_unrelated_fields(tmp_path, monkeypatch):
    take, *_ = fixture(tmp_path,monkeypatch,names=('文書名','項目:文書名'))
    result = take()
    data = records(export([result],tmp_path/'result.csv'))
    assert data[0] == ['文書名','処理結果','項目:文書名','項目:項目:文書名','確認事項','結果ID']
    assert data[1][2:4] == ['001234','80℃']


@pytest.mark.parametrize('mode', ['new-id','same-id-different-definition'])
def test_rejects_mixed_templates_and_revisions(tmp_path, monkeypatch, mode):
    take, template, *_ = fixture(tmp_path,monkeypatch)
    first = take()
    other = tmp_path/'other-template'; shutil.copytree(template.root,other)
    data = read(other/'template.json')
    if mode == 'new-id': data['template_id'] = str(uuid.uuid4())
    else: data['pages'][0]['rectangles'][0]['join'] = '空白'
    write(other/'template.json',data); r._write_manifest(other,t.SCHEMA,t.FILES)
    second = take(template_override=other)
    with pytest.raises(ValueError,match='異なるテンプレート'):
        export([first,second],tmp_path/'result.csv')
    assert not (tmp_path/'result.csv').exists()


@pytest.mark.parametrize('mode', ['empty','duplicate','missing-name','extra-name','blank-name','wrong-type','corrupt','stale'])
def test_invalid_inputs_never_publish_csv(tmp_path, monkeypatch, mode):
    take, *_ = fixture(tmp_path,monkeypatch)
    result = take(); results = [result]; names = {result.result_id:'帳簿.xdw'}
    if mode == 'empty': results = []
    if mode == 'duplicate': results.append(result)
    if mode == 'missing-name': names.clear()
    if mode == 'extra-name': names[str(uuid.uuid4())] = 'extra'
    if mode == 'blank-name': names[result.result_id] = ' \n'
    if mode == 'wrong-type': results = [result.root]
    if mode == 'corrupt': (result.root/'reviewed.json').write_bytes(b'broken')
    if mode == 'stale':
        data = result.data; data['result_id'] = str(uuid.uuid4())
        write(result.root/'structured.json',data); (result.root/'structured.jsonl').write_bytes(s._jsonl(data))
        r._write_manifest(result.root,s.SCHEMA,s.FILES)
    with pytest.raises((ValueError,RuntimeError,TypeError)):
        c.export_structured_csv(results,tmp_path/'result.csv',document_names=names)
    assert not (tmp_path/'result.csv').exists()


@pytest.mark.parametrize('mode', ['partial-write','input-change','publish','race-destination'])
def test_failure_cleanup_and_atomic_publication(tmp_path, monkeypatch, mode):
    take, *_ = fixture(tmp_path,monkeypatch); result = take(); before = hashes(result.root)
    original_write, original_publish = c._write_csv, r.publish_new
    def write_csv(path, rows):
        if mode == 'partial-write':
            path.write_bytes(b'partial'); raise OSError('write failure')
        original_write(path,rows)
        if mode == 'input-change': (result.root/'reviewed.json').write_bytes(b'concurrent change')
    def publish(source, destination):
        if mode == 'publish': raise OSError('publish failure')
        if mode == 'race-destination': destination.write_bytes(b'existing user data')
        return original_publish(source,destination)
    monkeypatch.setattr(c,'_write_csv',write_csv); monkeypatch.setattr(r,'publish_new',publish)
    output = tmp_path/'result.csv'
    with pytest.raises((OSError,RuntimeError)): export([result],output)
    if mode == 'race-destination': assert output.read_bytes() == b'existing user data'
    else: assert not output.exists()
    assert not list(tmp_path.glob('.structured-csv-*'))
    if mode != 'input-change': assert hashes(result.root) == before


def test_destination_protection_and_repeatability(tmp_path, monkeypatch):
    take, template, run, session = fixture(tmp_path,monkeypatch)
    result = take()
    for root in (result.root,template.root,run.root,session.root):
        with pytest.raises(ValueError): export([result],root/'result.csv')
    with pytest.raises(ValueError): export([result],tmp_path/'result.txt')
    with pytest.raises(ValueError): export([result],tmp_path/'.structured-csv-private.csv')
    output = export([result],tmp_path/'result.csv')
    with pytest.raises(FileExistsError): export([result],output)
    assert export([result],tmp_path/'again.csv').read_bytes() == output.read_bytes()


def test_offline_export_is_native_dependency_free(tmp_path, monkeypatch):
    take, template, run, session = fixture(tmp_path,monkeypatch); result = take()
    for root in (template.root,run.root,session.root,tmp_path/'reviewed-1'):
        shutil.move(root,root.with_name('offline-'+root.name))
    code = ('import sys; from docuworks_integrations import load_structured_result, export_structured_csv; '
            'r=load_structured_result(sys.argv[1]); '
            'export_structured_csv([r],sys.argv[2],document_names={r.result_id:"source.xdw"}); '
            'assert all(m not in sys.modules for m in ("docuworks_ctypes","PIL","openpyxl","pandas"))')
    subprocess.run([sys.executable,'-c',code,str(result.root),str(tmp_path/'offline.csv')],check=True)
    assert records(tmp_path/'offline.csv')[1][2:4] == ['001234','80℃']


@pytest.mark.parametrize('mode,exit_code', [('ok',0),('missing',2),('condition',2)])
def test_cli_japanese_output_and_status(tmp_path, monkeypatch, capsys, mode, exit_code):
    take, *_ = fixture(tmp_path,monkeypatch)
    results = [take(),take(mode)]
    args = ['export-structured-csv','--output',str(tmp_path/'結果.csv')]
    for n,result in enumerate(results): args += ['--entry',str(result.root),f'帳簿{n}.xdw']
    result = subprocess.run([sys.executable,'-m','docuworks_integrations',*args],
        env=dict(os.environ,PYTHONIOENCODING='cp1252'),capture_output=True)
    assert result.returncode == exit_code, result.stderr.decode('utf-8')
    assert 'CSVを出力しました：2件' in result.stdout.decode('utf-8')
    assert len(records(tmp_path/'結果.csv')) == 3
    assert main(args) == 1
    assert 'CSVを出力できませんでした' in capsys.readouterr().err
