"""Public export and Portable assembly regression tests with tiny synthetic archives."""
from pathlib import Path
import sys
import zipfile
import shutil
import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_portable_candidate import build, digest
from export_public_source import export


def setup_case(root):
    repo=root/'repo'; public=root/'public'; wheels=root/'wheels'
    wheels.mkdir(); public.mkdir()
    for name in ('LICENSE','LICENSE_NOTICE.md','THIRD_PARTY_NOTICES.md'):
        (public/name).write_text('public notice',encoding='utf-8')
    bat=b'@echo off\r\nif not exist "%ROOT%runtime\\python.exe" (exit /b 2)\r\n"%ROOT%runtime\\python.exe" -I -X utf8 tool.py\r\n'
    (public/'portable').mkdir()
    for name in ('ocr_rectangles.bat','text_maps.bat'):
        (public/'portable'/name).write_bytes(bat)
    for package,version in [('docuworks-ctypes','1.0.0'),('docuworks-integrations','0.7.0')]:
        folder=repo/'packages'/package; folder.mkdir(parents=True)
        (folder/'pyproject.toml').write_text(f'version = "{version}"\nlicense = {{text = "Proprietary"}}\n',encoding='utf-8')
        module=package.replace('-','_')
        (folder/module).mkdir()
        init=f'__version__ = "{version}"\n'
        (folder/module/'__init__.py').write_text(init,encoding='utf-8')
        with zipfile.ZipFile(wheels/f'{module}-{version}-py3-none-any.whl','w') as z:
            z.writestr(f'{module}/__init__.py',init)
            z.writestr(f'{module}-{version}.dist-info/METADATA',f'Name: {package}\nVersion: {version}\n')
    for name in ('portable','requirements','docs','examples','scripts'):
        (repo/name).mkdir()
    shutil.copytree(Path(__file__).resolve().parents[2]/'portable',repo/'portable',dirs_exist_ok=True)
    (repo/'portable/ocr_rectangles.bat').write_bytes(bat)
    (repo/'portable/text_maps.bat').write_bytes(bat)
    (repo/'docs/CORRECTIONS_0.7.0.md').write_text('correction API',encoding='utf-8')
    (repo/'examples/use_review_xdw_regions.py').write_text('# multi region example',encoding='utf-8')
    baseline=root/'baseline.zip'
    with zipfile.ZipFile(baseline,'w') as z:
        z.writestr('ocr_rectangles.bat',bat)
        z.writestr('vendor/NOTICE.txt',b'UNCHANGED NOTICE')
        z.writestr('models/model.bin',b'UNCHANGED MODEL')
        z.writestr('runtime/Lib/site-packages/docuworks_integrations-0.6.0.dist-info/METADATA',b'old')
        z.writestr('runtime/Lib/site-packages/docuworks_integrations/old.py',b'old')
    return repo,public,wheels,baseline,bat


def test_portable_includes_pinned_excel_dependency_and_scripts(tmp_path):
    repo, _, wheels, baseline, _ = setup_case(tmp_path)
    dependency = tmp_path / 'xlsxwriter.whl'
    with zipfile.ZipFile(dependency, 'w') as z:
        z.writestr('xlsxwriter/__init__.py', '__version__ = "3.2.9"\n')
        z.writestr('xlsxwriter-3.2.9.dist-info/METADATA', 'Name: xlsxwriter\nVersion: 3.2.9\n')
        z.writestr('xlsxwriter-3.2.9.dist-info/licenses/LICENSE.txt', 'BSD test license')
        z.writestr('xlsxwriter-3.2.9.data/scripts/vba_extract.py', '#!python\n# helper\n')
    output = tmp_path / 'portable.zip'
    build(baseline, digest(baseline), wheels, repo/'portable', output, source=repo, dependency_wheels=[dependency])
    with zipfile.ZipFile(output) as z:
        assert z.read('runtime/Scripts/vba_extract.py') == b'#!python\n# helper\n'
        assert z.read('reference/XlsxWriter-LICENSE.txt') == b'BSD test license'
        assert 'XlsxWriter==3.2.9' in z.read('repair_project_wheels.bat').decode()
        assert 'xlsxwriter.whl' in json.loads(z.read('reference/dependency-wheels.json'))
        assert {'name': 'xlsxwriter', 'version': '3.2.9'} in json.loads(z.read('reference/installed-packages.json'))


def test_excel_feature_requires_dependency_at_build(tmp_path):
    repo, _, wheels, baseline, _ = setup_case(tmp_path)
    with zipfile.ZipFile(next(wheels.glob('docuworks_integrations-*.whl')), 'a') as z:
        z.writestr('docuworks_integrations/reviewed_xlsx.py', '# exporter\n')
    with pytest.raises(ValueError, match='requires its pinned dependency'):
        build(baseline, digest(baseline), wheels, repo/'portable', tmp_path/'bad.zip', source=repo)


def test_public_export_includes_docs_examples_and_preserves_bat(tmp_path):
    repo,public,_,_,bat=setup_case(tmp_path)
    (public/'docs').mkdir()
    (public/'docs/INSTALLED_PACKAGES.md').write_text('published inventory\n| docuworks-integrations | 0.6.0 | MIT |')
    (repo/'docs/history.json').write_text('{"repository_target":"https://github.com/private-owner/docuworks-ocr"}')
    (repo/'docs/tests.xml').write_text('<testsuite tests="1" hostname="private-host"><testcase file="private-path" /></testsuite>')
    target=tmp_path/'export'
    export(repo,public,target)
    assert (target/'docs/CORRECTIONS_0.7.0.md').read_text()=='correction API'
    assert (target/'examples/use_review_xdw_regions.py').exists()
    assert not (target/'docs/INSTALLED_PACKAGES.md').exists()
    assert 'REDACTED_PRIVATE_REPOSITORY' in (target/'docs/history.json').read_text()
    assert 'private-owner' in (repo/'docs/history.json').read_text()
    assert 'private-' not in (target/'docs/tests.xml').read_text()
    assert 'tests="1"' in (target/'docs/tests.xml').read_text()
    assert (target/'portable/ocr_rectangles.bat').read_bytes()==bat
    assert 'docs/user/README.md' in (target/'README.md').read_text(encoding='utf-8')
    assert 'MIT' in (target/'packages/docuworks-integrations/pyproject.toml').read_text()
    assert 'Proprietary' in (repo/'packages/docuworks-integrations/pyproject.toml').read_text()
    with pytest.raises(FileExistsError): export(repo,public,target)


@pytest.mark.parametrize('mode',['runtime-mismatch','dev-version','invalid-release'])
def test_export_rejects_versions_before_creating_output(tmp_path,mode):
    repo,public,*_=setup_case(tmp_path)
    if mode=='runtime-mismatch':
        (repo/'packages/docuworks-integrations/docuworks_integrations/__init__.py').write_text('__version__ = "0.6.0"')
    if mode=='dev-version':
        path=repo/'packages/docuworks-integrations/pyproject.toml'
        path.write_text(path.read_text().replace('0.7.0','0.7.0.dev3'))
    target=tmp_path/'export'
    with pytest.raises(ValueError): export(repo,public,target,release_version='bad' if mode=='invalid-release' else 'v0.3.0')
    assert not target.exists()


def test_portable_replacement_preserves_fixed_bat_and_vendor_bytes(tmp_path):
    repo,_,wheels,baseline,bat=setup_case(tmp_path)
    output=tmp_path/'new.zip'; before=digest(baseline)
    build(baseline,before,wheels,repo/'portable',output,source=repo)
    with zipfile.ZipFile(output) as z:
        assert z.read('ocr_rectangles.bat')==bat
        assert z.read('vendor/NOTICE.txt')==b'UNCHANGED NOTICE'
        assert z.read('models/model.bin')==b'UNCHANGED MODEL'
        assert '0.7.0' in z.read('PROVENANCE.txt').decode()
        assert 'v0.3.0' in z.read('README.txt').decode('utf-8-sig')
        assert z.read('docs/CORRECTIONS_0.7.0.md')==b'correction API'
        assert 'runtime/Lib/site-packages/docuworks_integrations/old.py' not in z.namelist()
        assert not any('0.6.0' in n for n in z.namelist())
    saved=output.read_bytes()
    with pytest.raises(FileExistsError): build(baseline,before,wheels,repo/'portable',output)
    assert output.read_bytes()==saved and digest(baseline)==before


@pytest.mark.parametrize('mode',['source-mismatch','bad-hash'])
def test_portable_rejects_invalid_inputs_without_output(tmp_path,mode):
    repo,_,wheels,baseline,_=setup_case(tmp_path)
    if mode=='source-mismatch':
        path=repo/'packages/docuworks-integrations/pyproject.toml'
        path.write_text(path.read_text().replace('0.7.0','0.8.0'))
    output=tmp_path/'new.zip'
    with pytest.raises(ValueError):
        build(baseline,'0'*64 if mode=='bad-hash' else digest(baseline),wheels,repo/'portable',output,source=repo)
    assert not output.exists()
