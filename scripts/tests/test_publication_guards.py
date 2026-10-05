"""Negative tests use synthetic data only; no documents, models or credentials."""
import io
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import textwrap
import zipfile

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from audit_distributions import audit


def distributions(tmp_path, kind='wheel', name='package/module.py', data=b'pass\n', link=False, conftest=True):
    dist = tmp_path / 'dist'
    dist.mkdir()
    for package in ('docuworks_ctypes', 'docuworks_integrations'):
        with zipfile.ZipFile(dist / f'{package}-1.0.0-py3-none-any.whl', 'w') as z:
            z.writestr(package + '/__init__.py', b'pass\n')
            if package == 'docuworks_ctypes' and kind == 'wheel':
                member = zipfile.ZipInfo(name)
                if link:
                    member.create_system = 3
                    member.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(member, data)
        with tarfile.open(dist / f'{package}-1.0.0.tar.gz', 'w:gz') as tar:
            entries = [(package + '/PKG-INFO', b'Metadata-Version: 2.4\n')]
            if package == 'docuworks_integrations' and conftest:
                entries.append((package + '-1.0.0/tests/conftest.py', b'# fixture\n'))
            if package == 'docuworks_ctypes' and kind == 'sdist':
                entries.append((name, data))
            for path, body in entries:
                item = tarfile.TarInfo(path)
                item.size = len(body)
                if link and path == name:
                    item.type = tarfile.SYMTYPE
                    item.linkname = 'target.py'
                    item.size = 0
                tar.addfile(item, io.BytesIO(body))
    return dist


def test_clean_distributions_pass(tmp_path):
    audit(distributions(tmp_path))


@pytest.mark.parametrize('schema', ['docuworks-template-draft', 'docuworks-template-authoring'])
def test_authoring_data_is_not_publishable(tmp_path, schema):
    import json
    with pytest.raises(SystemExit):
        audit(distributions(tmp_path, data=json.dumps({'schema':schema}).encode()))


def test_integrations_sdist_requires_conftest(tmp_path):
    with pytest.raises(SystemExit, match='missing tests/conftest.py'):
        audit(distributions(tmp_path, conftest=False))


def test_manifest_in_is_allowed(tmp_path):
    audit(distributions(tmp_path, kind='sdist', name='package/MANIFEST.in',
                        data=b'include tests/conftest.py\n'))


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
@pytest.mark.parametrize('name', [
    'package/fixture.xdw', 'package/image.png', 'package/inference.pdiparams',
    'package/xdwapi.dll', 'package/xdwapi.h', 'package/manual.pdf',
    'package/.env', 'package/credentials.json', 'package/inference.yml',
    'package/models/model.json', '../outside.py', '/absolute.py',
], ids=['document', 'image', 'model', 'dll', 'header', 'manual', 'env', 'credentials',
        'model-config', 'model-directory', 'traversal', 'absolute'])
def test_forbidden_assets_rejected(tmp_path, kind, name):
    with pytest.raises(SystemExit, match='distribution audit failed'):
        audit(distributions(tmp_path, kind, name))


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
@pytest.mark.parametrize('data', [
    ('gh' + 'p_' + 'a' * 36).encode(),
    ('-----BEGIN ' + 'PRIVATE KEY-----').encode(),
    ('C:' + '/' + 'Users/' + 'synthetic/file').encode(),
    b'{"schema":"docuworks-ocr-result"}',
    b'{"schema":"docuworks-ocr-corrections"}',
    b'{"schema":"docuworks-ocr-effective-region"}',
    b'{"schema":"docuworks-ocr-review"}',
    b'{"schema":"docuworks-ocr-review-identity"}',
    b'{"schema":"docuworks-ocr-batch"}',
    b'{"res":{"rec_texts":[],"rec_polys":[]}}',
    b'{"auth":{"api_key":"synthetic-test-value"}}',
    b'\x00binary', b'\xff', b'a' * 1_000_001,
], ids=['token', 'private-key', 'user-path', 'ocr-manifest', 'corrections', 'effective-region', 'review', 'review-identity', 'batch-manifest', 'raw-ocr', 'credential-json', 'null-byte', 'invalid-utf8', 'oversized'])
def test_hidden_content_rejected_without_echo(tmp_path, kind, data, capsys):
    with pytest.raises(SystemExit) as exc:
        audit(distributions(tmp_path, kind, 'package/config.json', data))
    assert data.decode(errors='replace') not in str(exc.value) + capsys.readouterr().out


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_links_rejected(tmp_path, kind):
    with pytest.raises(SystemExit, match='link or special member'):
        audit(distributions(tmp_path, kind, link=True))


def test_unexpected_upload_file_rejected(tmp_path):
    dist = distributions(tmp_path)
    (dist / 'extra.txt').write_text('not an audited distribution')
    with pytest.raises(SystemExit, match='unexpected distribution'):
        audit(dist)


@pytest.mark.parametrize('failure', ['none', 'install', 'check', 'import', 'help'])
def test_actual_workflow_smoke_stops_on_failure(tmp_path, failure):
    shell = shutil.which('powershell') or shutil.which('pwsh')
    if shell is None:
        pytest.skip('PowerShell required')
    workflow = (SCRIPTS.parent / '.github/workflows/ci.yml').read_text()
    step = workflow.split('      - name: Smoke-test built wheels from outside repository\n', 1)[1]
    block = textwrap.dedent(step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
    # Exercise the real workflow block, substituting native commands with harmless exit codes.
    # Keep all guards, try/finally, locations and ordering exactly as authored.
    lines = []
    for line in block.splitlines():
        indent = line[:len(line) - len(line.lstrip())]
        stripped = line.strip()
        if stripped.startswith('$smokePython ='):
            line = "$smokePython = '" + sys.executable.replace("'", "''") + "'"
        elif stripped.startswith(('python ', '& $smokePython ')):
            category = ('check' if '-m pip check' in line else 'import' if 'import docuworks_' in line
                        else 'help' if '--help' in line else 'install' if '--no-index' in line else 'setup')
            code = 7 if category == failure else 0
            executable = "'" + sys.executable.replace("'", "''") + "'"
            line = indent + f'& {executable} -c "import sys; sys.exit({code})"'
        lines.append(line)
    script = tmp_path / 'smoke.ps1'
    script.write_text("$ErrorActionPreference = 'Stop'\n$env:RUNNER_TEMP = '" + str(tmp_path).replace("'", "''")
                      + "'\n" + '\n'.join(lines)
                      + "\nWrite-Output 'REACHED_END'\nexit $LASTEXITCODE\n", encoding='utf-8-sig')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                            capture_output=True, text=True)
    assert result.returncode == (0 if failure == 'none' else 7), result.stderr
    assert ('REACHED_END' in result.stdout) == (failure == 'none')
