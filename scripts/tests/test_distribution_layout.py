"""Distribution ownership must not silently fall back to an older archive."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from distribution_layout import load_layout
from build_portable_candidate import build, digest
from export_public_source import export
from test_release_070 import setup_case


@pytest.mark.parametrize('name',['OCR開始.bat','verify_environment.py','ocr_rectangles.bat'])
def test_missing_source_rejected_even_when_baseline_has_file(tmp_path,name):
    repo,public,wheels,baseline,_=setup_case(tmp_path)
    (repo/'portable'/name).unlink()
    with zipfile.ZipFile(baseline,'a') as z:
        if name not in z.namelist(): z.writestr(name,b'old')
    target=tmp_path/'output.zip'
    with pytest.raises(ValueError,match='missing'):
        build(baseline,digest(baseline),wheels,repo/'portable',target,source=repo)
    assert not target.exists()
    with pytest.raises(ValueError,match='missing'):
        export(repo,public,tmp_path/'export')
    assert not (tmp_path/'export').exists()


def test_unknown_source_and_baseline_launchers_rejected(tmp_path):
    repo,_,wheels,baseline,_=setup_case(tmp_path)
    (repo/'portable/forgotten.bat').write_bytes(b'old')
    with pytest.raises(ValueError,match='inventory'): load_layout(repo/'portable')
    (repo/'portable/forgotten.bat').unlink()
    with zipfile.ZipFile(baseline,'a') as z: z.writestr('forgotten.bat',b'old')
    with pytest.raises(ValueError,match='unmanaged'):
        build(baseline,digest(baseline),wheels,repo/'portable',tmp_path/'out.zip',source=repo)
    assert not (tmp_path/'out.zip').exists()


def test_inventory_proves_source_wheel_and_inherited_bytes(tmp_path):
    repo,_,wheels,baseline,_=setup_case(tmp_path)
    with zipfile.ZipFile(baseline,'a') as z:
        z.writestr('docs/obsolete.md',b'obsolete')
        z.writestr('scripts/old_helper.py',b'obsolete')
    output=tmp_path/'out.zip'
    build(baseline,digest(baseline),wheels,repo/'portable',output,source=repo)
    with zipfile.ZipFile(output) as z:
        name='reference/distribution-files.json'
        report=json.loads(z.read(name))
        rows={r['path']:r for r in report['files']}
        assert set(rows)=={i.filename for i in z.infolist() if not i.is_dir()}-{name}
        for path,row in rows.items():
            data=z.read(path)
            assert row['bytes']==len(data)
            assert row['sha256']==hashlib.sha256(data).hexdigest()
        assert rows['models/model.bin']['origin']=='baseline'
        assert rows['scripts/start_ocr.py']['origin']=='source'
        assert rows['runtime/Lib/site-packages/docuworks_integrations/__init__.py']['origin']=='wheel'
        assert rows['README.txt']['origin']=='generated'
        assert rows['README.md']['origin']=='generated'
        assert b'docs/user/README.md' in z.read('README.md')
        assert 'docs/obsolete.md' not in z.namelist()
        assert 'scripts/old_helper.py' not in z.namelist()


def test_export_uses_managed_launchers_not_public_baseline(tmp_path):
    repo,public,_,_,bat=setup_case(tmp_path)
    (public/'portable/ocr_rectangles.bat').write_bytes(b'outdated')
    export(repo,public,tmp_path/'export')
    assert (tmp_path/'export/portable/ocr_rectangles.bat').read_bytes()==bat


def test_portable_does_not_inherit_user_templates_or_drafts(tmp_path):
    repo,_,wheels,baseline,_ = setup_case(tmp_path)
    with zipfile.ZipFile(baseline,'a') as z:
        z.writestr('templates/private/v001/authoring/sample-reviewed/reviewed.json', b'private sample')
        z.writestr('template-drafts/private/draft.json', b'private draft')
    output = tmp_path/'fresh.zip'
    build(baseline,digest(baseline),wheels,repo/'portable',output,source=repo)
    with zipfile.ZipFile(output) as z:
        assert {name for name in z.namelist() if name.startswith(('templates/','template-drafts/'))} == {
            'templates/','template-drafts/'}
        assert 'テンプレート作成.bat' in z.namelist()


def test_public_links_and_machine_evidence(tmp_path):
    repo,public,_,_,_=setup_case(tmp_path)
    package=repo/'packages/docuworks-integrations'
    (package/'README.md').write_text('[API](https://github.com/example/docuworks-ocr/blob/main/docs/api.md)',encoding='utf-8')
    (repo/'docs/evidence.json').write_text(json.dumps({'import_path':str(tmp_path/'private-env'),'sha256':'a'*64}),encoding='utf-8')
    export(repo,public,tmp_path/'export',release_version='v0.4.0')
    assert '/dw-ocr/blob/v0.4.0/docs/api.md' in (tmp_path/'export/packages/docuworks-integrations/README.md').read_text()
    evidence=json.loads((tmp_path/'export/docs/evidence.json').read_text())
    if str(tmp_path)[1:3] in (':\\',':/'):
        assert evidence['import_path']=='REDACTED_LOCAL_PATH'
    assert evidence['sha256']=='a'*64
