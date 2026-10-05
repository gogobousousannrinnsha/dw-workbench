"""A Core patch version must be carried through exports and Portable metadata."""
import zipfile
import pytest
from test_release_070 import setup_case
from build_portable_candidate import build,digest
from export_public_source import export


def patched_core(tmp_path):
    repo,public,wheels,baseline,_=setup_case(tmp_path)
    for p in (repo/'packages/docuworks-ctypes').rglob('*'):
        if p.is_file():p.write_bytes(p.read_bytes().replace(b'1.0.0',b'1.0.1'))
    original=wheels/'docuworks_ctypes-1.0.0-py3-none-any.whl'
    with zipfile.ZipFile(original) as z:
        members={n.replace('1.0.0','1.0.1'):z.read(n).replace(b'1.0.0',b'1.0.1') for n in z.namelist()}
    original.unlink()
    with zipfile.ZipFile(wheels/'docuworks_ctypes-1.0.1-py3-none-any.whl','w') as z:
        for n,v in members.items():z.writestr(n,v)
    return repo,public,wheels,baseline


def test_export_and_portable_use_core_patch_version(tmp_path):
    repo,public,wheels,baseline=patched_core(tmp_path)
    out=tmp_path/'export';export(repo,public,out,release_version='v0.4.1')
    assert 'Core 1.0.1' in (out/'README.md').read_text(encoding='utf-8')
    archive=tmp_path/'portable.zip';build(baseline,digest(baseline),wheels,repo/'portable',archive,source=repo,release_version='v0.4.1')
    with zipfile.ZipFile(archive) as z:
        assert b'Core 1.0.1' in z.read('PROVENANCE.txt')
        assert b'docuworks-ctypes==1.0.1' in z.read('repair_project_wheels.bat')


def test_core_source_wheel_mismatch_rejected(tmp_path):
    repo,public,wheels,baseline=patched_core(tmp_path)
    p=repo/'packages/docuworks-ctypes/pyproject.toml'
    p.write_bytes(p.read_bytes().replace(b'1.0.1',b'1.0.2'))
    with pytest.raises(ValueError,match='version'):
        export(repo,public,tmp_path/'export')
    with pytest.raises(ValueError,match='version'):
        build(baseline,digest(baseline),wheels,repo/'portable',tmp_path/'out.zip',source=repo)
