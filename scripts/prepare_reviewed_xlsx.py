"""Overlay a fresh A/B Portable copy with the tested Excel candidate and freeze it."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from distribution_layout import load_layout, render_readme

VOLATILE = {'INPUT', 'OUTPUT', 'runs', 'logs', 'cache', 'ocr-cache', 'templates', 'template-drafts'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise ValueError('ambiguous wheel')
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    return metadata['Name'].lower().replace('_', '-'), metadata['Version']


def repair_launcher(data, version):
    data = re.sub(rb'docuworks-ctypes==[^\s"]+', b'docuworks-ctypes==1.0.1', data)
    data = re.sub(rb'docuworks-integrations==[^\s"]+', ('docuworks-integrations==' + version).encode(), data)
    # The project install uses --no-deps. Include the optional exporter explicitly.
    text = data.decode('utf-8-sig').replace('\r\n', '\n')
    text = re.sub(r'(docuworks-integrations==[^\s"]+)(?: XlsxWriter==[^\s]+)?', r'\1 XlsxWriter==3.2.9', text)
    return text.replace('\n', '\r\n').encode('utf-8')


def installed_member_matches(root, member, expected):
    if '.data/scripts/' in member:
        # pip relocates script payloads and substitutes the interpreter shebang.
        name = member.split('.data/scripts/', 1)[1]
        actual = (root / 'runtime/Scripts' / name).read_bytes()
        if expected.startswith(b'#!python\n'):
            first, separator, rest = actual.partition(b'\n')
            return bool(separator and first.startswith(b'#!') and rest == expected.partition(b'\n')[2])
        return actual == expected
    if '.data/' in member:
        raise ValueError('unsupported wheel relocation: ' + member)
    return (root / 'runtime/Lib/site-packages' / member).read_bytes() == expected


def prepare(repo, baseline, root, wheel, dependency):
    repo, baseline, root, wheel, dependency = map(lambda p: Path(p).resolve(), (repo, baseline, root, wheel, dependency))
    if root == baseline or root.is_relative_to(baseline) or baseline.is_relative_to(root):
        raise ValueError('candidate must be independent of baseline')
    package, version = wheel_metadata(wheel)
    if package != 'docuworks-integrations' or version != '0.12.0+reviewxlsx.1':
        raise ValueError('unexpected candidate wheel')
    if wheel_metadata(dependency) != ('xlsxwriter', '3.2.9'):
        raise ValueError('unexpected exporter dependency')
    project = (repo / 'packages/docuworks-integrations/pyproject.toml').read_text(encoding='utf-8')
    if f'version = "{version}"' not in project:
        raise ValueError('source/wheel version mismatch')
    inventory = 'reference/distribution-files.json'
    if not root.exists():
        shutil.copytree(baseline, root, ignore=lambda folder, names:
                        [n for n in names if n == '__pycache__' or n == '.authoring.lock'
                         or (Path(folder) == baseline and n in VOLATILE)])
    # Also supports an independently copied baseline (e.g. robocopy); never update a used kit.
    if sha(root / inventory) != sha(baseline / inventory):
        raise ValueError('candidate must still have the baseline inventory')
    if (root / 'reference/reviewed-xlsx-build.json').exists():
        raise FileExistsError('already prepared')
    for name in VOLATILE:
        folder = root / name
        if folder.exists() and any(folder.iterdir()):
            raise ValueError('candidate contains user data: ' + name)
        folder.mkdir(exist_ok=True)
    layout = load_layout(repo / 'portable')
    files = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0')
    for name in files:
        if not name or not (repo / name).is_file():
            continue
        if name.startswith(('docs/', 'examples/', 'packages/', 'requirements/', 'scripts/')) or name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / name, target)
    for name in [*layout['files'], 'README_AB.md']:
        source = repo / 'portable' / name
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        if name.endswith('.bat'):
            data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        target.write_bytes(data)
    for name in (wheel, dependency):
        shutil.copyfile(name, root / 'wheelhouse' / name.name)
    subprocess.run([str(root / 'runtime/python.exe'), '-I', '-B', '-m', 'pip', 'install', '--no-index',
                    '--no-deps', '--force-reinstall', str(root / 'wheelhouse' / wheel.name),
                    str(root / 'wheelhouse' / dependency.name)], check=True)
    (root / 'repair_project_wheels.bat').write_bytes(repair_launcher(
        (repo / 'portable/repair_project_wheels.bat').read_bytes(), version))
    versions = {'docuworks-ctypes': '1.0.1', 'docuworks-integrations': version}
    (root / 'README.txt').write_text('DW-OCR 全文Excel出力・一括/分割 検証候補（未公開）\n\n' +
        render_readme(repo / 'portable', 'portable_readme', versions, 'v0.6.1ベースの検証候補'), encoding='utf-8-sig')
    (root / 'README.md').write_text(render_readme(repo / 'portable', 'public_readme', versions,
                                               'v0.6.1ベースの検証候補（未公開）'), encoding='utf-8')
    wheel_record = json.loads((root / 'reference/project-wheels.json').read_text(encoding='utf-8'))
    wheel_record = {n: h for n, h in wheel_record.items() if not n.startswith('docuworks_integrations-')}
    wheel_record[wheel.name] = sha(wheel)
    (root / 'reference/project-wheels.json').write_text(json.dumps(wheel_record, indent=2) + '\n', encoding='utf-8')
    description = dict(kind='local-reviewed-xlsx-verification', published=False, core='1.0.1', integrations=version,
                       baseline_inventory_sha256=sha(baseline / inventory),
                       wheels={wheel.name: sha(wheel), dependency.name: sha(dependency)})
    (root / 'reference/reviewed-xlsx-build.json').write_text(json.dumps(description, indent=2) + '\n', encoding='utf-8')
    (root / 'reference/dependency-wheels.json').write_text(json.dumps({dependency.name: sha(dependency)}, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(dependency) as archive:
        licenses = [n for n in archive.namelist() if n.endswith('/LICENSE.txt') or n.endswith('/LICENSE')]
        if len(licenses) != 1:
            raise ValueError('missing exporter license')
        target = root / 'reference/XlsxWriter-LICENSE.txt'
        target.write_bytes(archive.read(licenses[0]))
    # Historical A/B evidence stays marked as such; this is the authoritative new build record.
    (root / 'PROVENANCE.txt').write_text('Local Reviewed Excel candidate; not published.\n' +
        json.dumps(description, indent=2) + '\n', encoding='utf-8')
    return description


def freeze(root, baseline, output):
    root, baseline, output = map(lambda p: Path(p).resolve(), (root, baseline, output))
    record = json.loads((root / 'reference/reviewed-xlsx-build.json').read_text(encoding='utf-8'))
    members = 0
    for name, digest in record['wheels'].items():
        wheel = root / 'wheelhouse' / name
        assert sha(wheel) == digest
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                if member.endswith('/') or '.dist-info/' in member:
                    continue
                assert installed_member_matches(root, member, archive.read(member)), member
                members += 1
    old = json.loads((baseline / 'reference/distribution-files.json').read_text(encoding='utf-8'))
    prior = {item['path']: item['sha256'] for item in old['files']}
    rows = []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if not path.is_file() or rel.parts[0] in VOLATILE or '__pycache__' in rel.parts or rel.name == '.authoring.lock':
            continue
        name = rel.as_posix()
        if name == 'reference/distribution-files.json':
            continue
        digest = sha(path)
        rows.append(dict(path=name, bytes=path.stat().st_size, sha256=digest,
                         origin='baseline' if prior.get(name) == digest else 'excel-candidate'))
    inventory = dict(schema='dw-ocr-distribution-files', schema_version='1.0', candidate=True,
                     purpose='local-reviewed-xlsx-verification', files=rows,
                     excluded_self='reference/distribution-files.json', excluded_mutable_roots=sorted(VOLATILE),
                     excluded_generated=['__pycache__', '.authoring.lock'])
    target = root / 'reference/distribution-files.json'
    target.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    completed = dict(static_inventory_files=len(rows), inventory_sha256=sha(target),
                     hashing='all static files read once after final changes; wheel bytes compared with pip script relocation/shebang accounted for',
                     installed_wheel_members=members, installed_wheel_matches=True,
                     mutable_roots_empty=all(not any((root / n).iterdir()) for n in VOLATILE),
                     published=False)
    output.write_text(json.dumps(completed, indent=2) + '\n', encoding='utf-8')
    return completed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--portable', type=Path, required=True)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--dependency', type=Path)
    parser.add_argument('--freeze-report', type=Path)
    args = parser.parse_args()
    result = freeze(args.portable, args.baseline, args.freeze_report) if args.freeze_report else prepare(
        args.repo, args.baseline, args.portable, args.wheel, args.dependency)
    print(json.dumps(result, ensure_ascii=False), flush=True)
