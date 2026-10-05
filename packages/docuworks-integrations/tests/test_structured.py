import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from docuworks_integrations import structured as s, templates as t, reviewed as r
from docuworks_integrations.cli import main
from test_reviewed import setup, read, write, hashes
from test_reviewed_v2 import modern
from test_templates import setup_template, rectangle, attr


def inputs(tmp_path, monkeypatch, version='2.0'):
    run, session, _ = (modern if version == '2.0' else setup)(tmp_path, monkeypatch)
    raw = read(session.review_xdw)
    for page in raw['pages']:
        page['items'] = page['items'][:1]
    raw['pages'][0]['items'][0].update(text='80℃', x=1, y=1, width=2, height=2, identity=None)
    write(session.review_xdw, raw)
    reviewed = r.import_reviewed_result(session.root, session.review_xdw, tmp_path/'reviewed',
                                        validation_mode='identity' if version == '2.0' else 'strict')
    snapshot = dict(pages=[dict(page=p['page'],width_mm=p['width_mm'],height_mm=p['height_mm'],rotation=0,
                               rectangles=[dict(rectangle(), x=0, y=0, width=8, height=4)] if p['page']==1 else []) for p in reviewed.pages])
    template = setup_template(tmp_path, monkeypatch, snapshot)
    return template, reviewed, run, session


@pytest.mark.parametrize('version', ['1.0','2.0'])
def test_independent_roundtrip_repeated_apply_and_schema(tmp_path, monkeypatch, version):
    template, reviewed, run, session = inputs(tmp_path, monkeypatch, version)
    roots = (template.root, reviewed.root, run.root, session.root)
    before = [hashes(root) for root in roots]
    result = s.apply_rectangle_template(template.root, reviewed.root, tmp_path/'structured')
    data = result.data
    assert data['fields'][0]['value'] == '80℃' and data['status'] == 'ok'
    assert data['reviewed']['validation']['page_structure_checked'] is (version == '1.0')
    assert data['fields'][0]['sources'][0]['item'] == reviewed.pages[0]['items'][0]
    assert data['fields'][0]['sources'][0]['result_id'] == reviewed.result_id
    assert [hashes(root) for root in roots] == before
    again = s.apply_rectangle_template(template.root, reviewed.root, tmp_path/'again')
    assert again.result_id != result.result_id
    assert again.data['fields'] == data['fields']
    assert len((result.root/'structured.jsonl').read_text(encoding='utf-8').splitlines()) == 1
    import jsonschema
    for file, schema in [('structured.json','structured-result-1.0'),('manifest.json','structured-result-manifest-1.0')]:
        jsonschema.Draft202012Validator(read(Path(s.__file__).parent/(schema+'.schema.json')),
                                       format_checker=jsonschema.FormatChecker()).validate(read(result.root/file))
    for root in roots: shutil.move(root, root.with_name('offline-'+root.name))
    assert s.load_structured_result(result.root) == result
    data['fields'].clear(); assert result.data['fields']
    code = 'import sys; from docuworks_integrations import load_structured_result; load_structured_result(sys.argv[1]); assert "docuworks_ctypes" not in sys.modules and "PIL" not in sys.modules'
    subprocess.run([sys.executable,'-c',code,str(result.root)],check=True)


@pytest.mark.parametrize('filename', sorted(s.FILES | {'manifest.json'}))
def test_file_corruption_rejected(tmp_path, monkeypatch, filename):
    template, reviewed, *_ = inputs(tmp_path, monkeypatch)
    result = s.apply_rectangle_template(template.root, reviewed.root, tmp_path/'structured')
    (result.root/filename).write_bytes(b'broken')
    with pytest.raises((ValueError, RuntimeError)): s.load_structured_result(result.root)


@pytest.mark.parametrize('mode', ['value','source','omission','status','type','validation','jsonl','template-ref','reviewed-ref','reviewed-source'])
def test_rehash_does_not_hide_semantic_corruption(tmp_path, monkeypatch, mode):
    template, reviewed, *_ = inputs(tmp_path, monkeypatch)
    result = s.apply_rectangle_template(template.root, reviewed.root, tmp_path/'structured')
    data = result.data
    if mode == 'value': data['fields'][0]['value'] = '100℃'
    if mode == 'source': data['fields'][0]['sources'][0]['item']['text'] = '100℃'
    if mode == 'omission': data['fields'][0]['sources'].clear()
    if mode == 'status': data['status'] = 'needs_review'
    if mode == 'type': data['applicable'] = 1
    if mode == 'validation': data['reviewed']['validation']['page_structure_checked'] = True
    if mode == 'template-ref': data['template']['manifest_sha256'] = '0'*64
    if mode == 'reviewed-ref': data['reviewed']['manifest_sha256'] = '0'*64
    write(result.root/'structured.json',data)
    (result.root/'structured.jsonl').write_bytes(b'{}\n' if mode == 'jsonl' else s._jsonl(data))
    if mode == 'reviewed-source':
        changed = read(result.root/'reviewed.json'); changed['pages'][0]['items'][0]['text'] = '100℃'
        write(result.root/'reviewed.json',changed)
    r._write_manifest(result.root,s.SCHEMA,s.FILES)
    with pytest.raises(ValueError): s.load_structured_result(result.root)


@pytest.mark.parametrize('failure', ['input-race','write','publish','validation'])
def test_atomic_failure_keeps_inputs_and_no_published_directory(tmp_path, monkeypatch, failure):
    template, reviewed, run, session = inputs(tmp_path, monkeypatch)
    before = hashes(template.root), hashes(reviewed.root)
    original = s._inputs
    def changed(root):
        output = original(root)
        if failure == 'input-race': (reviewed.root/'source-review.xdw').write_bytes(b'concurrent change')
        return output
    if failure == 'input-race': monkeypatch.setattr(s,'_inputs',changed)
    def fail(*args, **kwargs): raise RuntimeError('injected failure')
    if failure == 'write': monkeypatch.setattr(r,'_write_manifest',fail)
    if failure == 'publish': monkeypatch.setattr(r,'publish_new',fail)
    if failure == 'validation': monkeypatch.setattr(s,'evaluate',fail)
    with pytest.raises(RuntimeError): s.apply_rectangle_template(template.root,reviewed.root,tmp_path/'structured')
    assert not (tmp_path/'structured').exists()
    assert not list(tmp_path.glob('.structured-result-*'))
    assert hashes(template.root) == before[0]
    if failure != 'input-race': assert hashes(reviewed.root) == before[1]


def test_refuses_overwrite_nested_input_and_private_staging(tmp_path, monkeypatch):
    template, reviewed, run, session = inputs(tmp_path, monkeypatch)
    result = s.apply_rectangle_template(template.root,reviewed.root,tmp_path/'structured')
    for root in (template.root, reviewed.root, run.root, session.root, result.root):
        with pytest.raises(ValueError): s.apply_rectangle_template(template.root,reviewed.root,root/'nested')
    with pytest.raises(FileExistsError): s.apply_rectangle_template(template.root,reviewed.root,result.root)
    shutil.move(result.root,tmp_path/'.structured-result-hidden')
    with pytest.raises(ValueError): s.load_structured_result(tmp_path/'.structured-result-hidden')


@pytest.mark.parametrize('mode', ['ok','missing','empty','unsupported','not-applicable'])
def test_cli_check_and_apply_outcomes(tmp_path, monkeypatch, capsys, mode):
    template, reviewed, *_ = inputs(tmp_path, monkeypatch)
    data = template.data
    if mode == 'missing': data['pages'][0]['rectangles'][0]['y'] = 6
    if mode == 'empty' or mode == 'unsupported':
        # Regenerate a valid Reviewed through its importer, not by changing a signed result.
        session = r.load_review_session(tmp_path/'session'); raw = read(session.review_xdw)
        raw['pages'][0]['items'][0].update(text='' if mode == 'empty' else '80℃', rotation=30 if mode=='unsupported' else 0)
        write(session.review_xdw,raw)
        reviewed = r.import_reviewed_result(session.root,session.review_xdw,tmp_path/'changed-reviewed',validation_mode='identity')
    if mode == 'not-applicable': data['pages'][0]['width_mm'] += 1
    write(template.root/'template.json',data); r._write_manifest(template.root,t.SCHEMA,t.FILES)
    before = set(tmp_path.iterdir())
    args = ['--template-dir',str(template.root),'--reviewed-dir',str(reviewed.root)]
    expected = 0 if mode == 'ok' else 2
    assert main(['check-template',*args]) == expected
    assert set(tmp_path.iterdir()) == before
    assert main(['apply-template',*args,'--output-dir',str(tmp_path/'structured')]) == expected
    result = s.load_structured_result(tmp_path/'structured')
    assert result.data['status'] == ('ok' if mode=='ok' else 'not_applicable' if mode=='not-applicable' else 'needs_review')
    assert ('適用不可' if mode=='not-applicable' else '取得完了' if mode=='ok' else '要確認') in capsys.readouterr().out


def test_cli_registration_validation_and_failure_message(tmp_path, monkeypatch, capsys):
    template, *_ = inputs(tmp_path,monkeypatch)
    assert main(['register-template','--template-xdw',str(tmp_path/'帳簿A.xdw'),'--output-dir',str(tmp_path/'registered')]) == 0
    assert 'テンプレートを登録しました' in capsys.readouterr().out
    assert main(['check-template','--template-dir',str(template.root)]) == 0
    assert '温度' in capsys.readouterr().out
    assert main(['apply-template','--template-dir',str(template.root),'--reviewed-dir',str(tmp_path/'absent'),'--output-dir',str(tmp_path/'out')]) == 1
    assert '処理できませんでした' in capsys.readouterr().err
    class NativeFailure(Exception): pass
    def fail(_): raise NativeFailure('SDK unavailable')
    monkeypatch.setattr(t, '_sdk', fail)
    assert main(['register-template','--template-xdw',str(tmp_path/'帳簿A.xdw'),
                 '--output-dir',str(tmp_path/'failed')]) == 1
    assert not (tmp_path/'failed').exists()
    assert 'SDK unavailable' in capsys.readouterr().err


@pytest.mark.parametrize('command', ['--help','check-template','apply-template','register-template'])
def test_cli_japanese_output_on_non_japanese_windows_locale(tmp_path, monkeypatch, command):
    template, reviewed, *_ = inputs(tmp_path,monkeypatch)
    args = [command]
    if command in ('check-template','apply-template'):
        args += ['--template-dir',str(template.root),'--reviewed-dir',str(reviewed.root)]
        if command == 'apply-template': args += ['--output-dir',str(tmp_path/'structured')]
    if command == 'register-template':
        args += ['--template-xdw',str(tmp_path/'存在しない.xdw'),'--output-dir',str(tmp_path/'absent')]
    result = subprocess.run([sys.executable,'-m','docuworks_integrations',*args],
        env=dict(os.environ,PYTHONIOENCODING='cp1252'),capture_output=True)
    assert result.returncode == (1 if command == 'register-template' else 0)
    text = (result.stdout+result.stderr).decode('utf-8')
    assert ('処理できませんでした' if command == 'register-template' else '矩形' if command == '--help' else '温度') in text
