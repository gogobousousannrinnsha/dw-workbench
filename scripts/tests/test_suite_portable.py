"""Fresh combined Portable uses public vendor bytes and excludes baseline user state."""
import json
import zipfile
import pytest
from test_release_070 import setup_case
from build_portable_candidate import build, digest
from export_public_source import export


def with_workbench(root):
    repo, public, wheels, _, _ = setup_case(root)
    package = repo/'packages/dw-workbench'
    (package/'dw_workbench').mkdir(parents=True)
    (package/'pyproject.toml').write_text('dynamic = ["version"]\nlicense = {text = "Proprietary"}\ndependencies = ["docuworks-integrations==0.7.0"]\n')
    init = '__version__ = "0.4.0"\n'
    (package/'dw_workbench/__init__.py').write_text(init)
    with zipfile.ZipFile(wheels/'dw_workbench-0.4.0-py3-none-any.whl','w') as archive:
        archive.writestr('dw_workbench/__init__.py',init)
        archive.writestr('dw_workbench-0.4.0.dist-info/METADATA','Name: dw-workbench\nVersion: 0.4.0\n')
    return repo, public, wheels


def test_prefixed_public_vendor_zip_rewrites_names_and_omits_user_state(tmp_path):
    repo, _, wheels = with_workbench(tmp_path)
    baseline = tmp_path/'public-vendor.zip'
    payload = b'UNCHANGED VENDOR BINARY\0' * 1000
    with zipfile.ZipFile(baseline,'w',zipfile.ZIP_DEFLATED) as archive:
        with archive.open('old-root/runtime/vendor.dll','w',force_zip64=True) as stream:
            stream.write(payload)
        archive.writestr('old-root/models/model.bin',b'MODEL')
        archive.writestr('old-root/licenses/NOTICE.txt','original upstream notice')
        archive.writestr('old-root/projects/business/project.sqlite',b'PRIVATE DB')
        archive.writestr('old-root/settings/private.json','private setting')
        archive.writestr('old-root/source/old.py','old source')
        archive.writestr('old-root/起動.bat','old launcher')
        archive.writestr('old-root/runtime/Lib/site-packages/dw_workbench/old.py','old code')
    output = tmp_path/'fresh.zip'
    build(baseline,digest(baseline),wheels,repo/'portable',output,source=repo,baseline_prefix='old-root')
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.read('runtime/vendor.dll') == payload
        assert archive.read('models/model.bin') == b'MODEL'
        assert archive.read('licenses/NOTICE.txt') == b'original upstream notice'
        assert not any(name.startswith(('old-root/','projects/business/','source/')) or name.endswith('old.py') for name in archive.namelist())
        assert 'settings/private.json' not in archive.namelist()
        assert 'Workbench開始.bat' in archive.namelist()
        assert archive.read('runtime/Lib/site-packages/dw_workbench/__init__.py') == b'__version__ = "0.4.0"\n'
        entries = json.loads(archive.read('reference/distribution-files.json'))['files']
        assert next(entry for entry in entries if entry['path']=='runtime/vendor.dll')['origin']=='baseline'


def test_workbench_companion_version_mismatch_stops_build(tmp_path):
    repo, _, wheels = with_workbench(tmp_path)
    path = repo/'packages/dw-workbench/pyproject.toml'
    path.write_text(path.read_text().replace('==0.7.0','==0.6.0'))
    baseline=tmp_path/'baseline.zip'
    with zipfile.ZipFile(baseline,'w') as archive:
        archive.writestr('vendor/NOTICE.txt','notice')
    with pytest.raises(ValueError,match='companion version'):
        build(baseline,digest(baseline),wheels,repo/'portable',tmp_path/'bad.zip',source=repo)
    assert not (tmp_path/'bad.zip').exists()


def test_public_export_includes_workbench_with_license_and_exact_source(tmp_path):
    repo, public, _ = with_workbench(tmp_path)
    slash=chr(92)
    local='C:'+slash+'ai'+slash+'private portable'
    personal='C:'+slash+'Users'+slash+'example'+slash+'workspace'
    (repo/'docs/local-verification.md').write_text(f'Verified in `{local}` and `{personal}`.\n')
    output=tmp_path/'export'
    export(repo,public,output)
    name='packages/dw-workbench/dw_workbench/__init__.py'
    assert (output/name).read_bytes() == (repo/name).read_bytes()
    assert 'license = {text = "MIT"}' in (output/'packages/dw-workbench/pyproject.toml').read_text()
    assert (output/'packages/dw-workbench/LICENSE').read_text() == 'public notice'
    assert (output/'docs/local-verification.md').read_text() == 'Verified in `REDACTED_LOCAL_PATH` and `REDACTED_LOCAL_PATH`.\n'
