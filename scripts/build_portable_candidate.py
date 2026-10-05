"""Stream a fresh Portable from a pinned baseline ZIP and tested public wheels.

No live environment is modified. Unchanged compressed members are copied verbatim.
Python 3.13 zipfile internals used by the copier are covered by full CRC verification.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import zipfile
from email.parser import BytesParser
from distribution_layout import load_layout, render_readme


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def build(baseline, expected_hash, wheels, portable, output, *, release_version='v0.3.0', source=None, dependency_wheels=(), baseline_prefix=None):
    baseline, wheels, portable, output=map(Path,(baseline,wheels,portable,output))
    if digest(baseline)!=expected_hash: raise ValueError('baseline SHA-256 mismatch')
    if output.exists(): raise FileExistsError(output)
    if not re.fullmatch(r'v\d+\.\d+\.\d+',release_version): raise ValueError('invalid release version')
    layout = load_layout(portable)
    if source is None:
        raise ValueError('complete public source is required for managed documentation')
    changes={name:(portable/name).read_bytes() for name in layout['files']}
    origins={name:'source' for name in changes}
    for name in tuple(changes):
        if name.endswith('.bat'):
            # ASCII BAT syntax and a Japanese filename; CRLF for cmd.exe.
            changes[name]=changes[name].replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    wheel_paths=sorted(wheels.glob('*.whl'))
    if len(wheel_paths) not in (2, 3): raise ValueError('Core and Integrations, with optional Workbench wheels required')
    versions={}
    for wheel in wheel_paths:
        changes['wheelhouse/'+wheel.name]=wheel.read_bytes()
        origins['wheelhouse/'+wheel.name]='wheel'
        with zipfile.ZipFile(wheel) as archive:
            metadata_names=[n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            if len(metadata_names)!=1: raise ValueError('ambiguous wheel metadata')
            metadata=BytesParser().parsebytes(archive.read(metadata_names[0]))
            package=metadata['Name'].replace('_','-')
            if package in versions: raise ValueError('duplicate package')
            versions[package]=metadata['Version']
            for name in archive.namelist():
                if '.data/' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name:
                    raise ValueError('unexpected wheel data layout')
                changes['runtime/Lib/site-packages/'+name]=archive.read(name)
                origins['runtime/Lib/site-packages/'+name]='wheel'
    if set(versions) not in ({'docuworks-ctypes','docuworks-integrations'}, {'docuworks-ctypes','docuworks-integrations','dw-workbench'}):
        raise ValueError('unexpected wheel packages')
    dependency_paths = list(map(Path, dependency_wheels))
    dependencies = {}
    for wheel in dependency_paths:
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            if len(metadata_names) != 1: raise ValueError('ambiguous dependency metadata')
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
            package = metadata['Name'].lower().replace('_', '-')
            if package != 'xlsxwriter' or metadata['Version'] != '3.2.9' or package in dependencies:
                raise ValueError('unexpected dependency wheel')
            dependencies[package] = metadata['Version']
            changes['wheelhouse/' + wheel.name] = wheel.read_bytes()
            origins['wheelhouse/' + wheel.name] = 'dependency-wheel'
            for name in archive.namelist():
                if name.endswith('/'): continue
                if '\\' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name:
                    raise ValueError('unsafe dependency wheel path')
                if '.data/scripts/' in name:
                    destination = 'runtime/Scripts/' + name.split('.data/scripts/', 1)[1]
                elif '.data/' in name:
                    raise ValueError('unsupported dependency data layout')
                else:
                    destination = 'runtime/Lib/site-packages/' + name
                if destination in changes: raise ValueError('dependency overwrites project content')
                changes[destination] = archive.read(name)
                origins[destination] = 'dependency-wheel'
            licenses = [n for n in archive.namelist() if n.endswith(('/LICENSE.txt', '/LICENSE'))]
            if len(licenses) != 1: raise ValueError('missing dependency license')
            changes['reference/XlsxWriter-LICENSE.txt'] = archive.read(licenses[0])
    if 'runtime/Lib/site-packages/docuworks_integrations/reviewed_xlsx.py' in changes and not dependencies:
        raise ValueError('Excel exporter requires its pinned dependency wheel')
    version=versions['docuworks-integrations']
    if not re.fullmatch(r'1\.\d+\.\d+',versions['docuworks-ctypes']) or not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('expected stable Core 1.x and Integrations')
    init=changes['runtime/Lib/site-packages/docuworks_integrations/__init__.py'].decode('utf-8')
    if f'__version__ = "{version}"' not in init: raise ValueError('wheel/runtime version mismatch')
    if source is not None:
        source=Path(source)
        project=(source/'packages/docuworks-integrations/pyproject.toml').read_text(encoding='utf-8')
        if f'version = "{version}"' not in project: raise ValueError('source/wheel version mismatch')
        for package, expected in versions.items():
            project_metadata=(source/'packages'/package/'pyproject.toml').read_text(encoding='utf-8')
            module=package.replace('-','_')
            source_init=(source/'packages'/package/module/'__init__.py').read_text(encoding='utf-8')
            if ((package != 'dw-workbench' and f'version = "{expected}"' not in project_metadata)
                    or f'__version__ = "{expected}"' not in source_init
                    or f'__version__ = "{expected}"' not in changes[f'runtime/Lib/site-packages/{module}/__init__.py'].decode('utf-8')):
                raise ValueError('source/wheel/runtime version mismatch: '+package)
        if 'dw-workbench' in versions:
            workbench_project=(source/'packages/dw-workbench/pyproject.toml').read_text(encoding='utf-8')
            if f'docuworks-integrations=={version}' not in workbench_project:
                raise ValueError('Workbench companion version mismatch')
        for name in ('LICENSE', 'LICENSE_NOTICE.md', 'THIRD_PARTY_NOTICES.md'):
            if (source/name).is_file():
                changes[name] = (source/name).read_bytes()
                origins[name] = 'source'
        for folder in ('docs','examples','packages','requirements','scripts'):
            for path in (source/folder).rglob('*'):
                if path.is_file() and not any(part in ('__pycache__','build','dist','.pytest_cache','integration-artifacts') or part.endswith('.egg-info') for part in path.relative_to(source).parts):
                    name=path.relative_to(source).as_posix()
                    # Runtime scripts from portable are authoritative if names overlap.
                    if name not in changes:
                        changes[name]=path.read_bytes()
                        origins[name]='source'
    if (portable/'README_AB.md').is_file():
        changes['README_AB.md'] = (portable/'README_AB.md').read_bytes()
    changes['README.txt']=render_readme(portable, 'portable_readme', versions, release_version).encode('utf-8-sig')
    # Package/Core documentation links to the source root README as well.
    changes['README.md']=render_readme(portable, 'public_readme', versions, release_version).replace('(portable/README_AB.md)', '(README_AB.md)').encode('utf-8')
    repair='repair_project_wheels.bat'
    if repair in changes:
        text=changes[repair].decode('utf-8-sig')
        for package, selected_version in versions.items():
            text=re.sub(re.escape(package)+r'==[^\s"]+',package+'=='+selected_version,text)
        if dependencies and 'XlsxWriter==3.2.9' not in text:
            text=text.replace('docuworks-integrations=='+version,'docuworks-integrations=='+version+' XlsxWriter==3.2.9')
        if 'dw-workbench' in versions:
            text=text.replace('docuworks-integrations=='+version,'docuworks-integrations=='+version+' dw-workbench=='+versions['dw-workbench'])
        changes[repair]=text.encode('utf-8')
    if 'dw-workbench' in versions:
        workbench_wheel=next(w for w in wheel_paths if w.name.startswith('dw_workbench-'))
        changes['BUILD.json']=json.dumps(dict(application='DW-Workbench / DW-OCR',version=versions['dw-workbench'],
            release_version=release_version,status='local-validation-candidate',baseline_sha256=expected_hash,
            wheel_sha256=digest(workbench_wheel),components=versions,
            source_manifest_sha256=digest(Path(source)/'source-manifest.json') if (Path(source)/'source-manifest.json').is_file() else None,
            initial_projects_empty=True,initial_settings_empty=True,published=False),indent=2).encode()
    changes['PROVENANCE.txt']=(f'DW-OCR {release_version} Pre-release\nBaseline archive SHA256: '+expected_hash+
        f"\nCore {versions['docuworks-ctypes']}; Integrations {version}; Python 3.13.15\n"+
        (f"DW-Workbench {versions['dw-workbench']}\n" if 'dw-workbench' in versions else '')+
        '\n'.join(w.name+' SHA256 '+digest(w) for w in [*wheel_paths,*dependency_paths])+'\n').encode()
    changes['reference/project-wheels.json']=json.dumps({w.name:digest(w) for w in wheel_paths},indent=2).encode()
    if dependency_paths:
        changes['reference/dependency-wheels.json']=json.dumps({w.name:digest(w) for w in dependency_paths},indent=2).encode()
    for folder in ('INPUT','OUTPUT','runs','cache','templates','template-drafts','logs','projects','settings'): changes[folder+'/']=b''
    origins.update({name:'generated' for name in changes if name not in origins})
    inventory_name='reference/distribution-files.json'
    removed=[]
    with zipfile.ZipFile(baseline) as original:
        prefix = baseline_prefix.rstrip('/')+'/' if baseline_prefix else ''
        if prefix and (PurePosixPath(prefix).is_absolute() or '..' in PurePosixPath(prefix).parts or ':' in prefix or '\\' in prefix):
            raise ValueError('unsafe baseline prefix')
        infos = []
        for info in original.infolist():
            if prefix and not info.filename.startswith(prefix):
                raise ValueError('baseline member outside fixed prefix')
            normalized = copy.copy(info)
            normalized.filename = info.filename[len(prefix):]
            if normalized.filename:
                infos.append(normalized)
        if len(infos) != len(set(i.filename for i in infos)):
            raise ValueError('duplicate normalized ZIP member')
        for name in [i.filename for i in infos]:
            if name.endswith('.bat') and '/' not in name and name not in layout['files']:
                if not prefix:
                    raise ValueError('unmanaged baseline launcher: '+name)
                # A prefixed public Workbench baseline contributes vendor assets only.
                removed.append(name)
        # Keep all third-party binary/model/license content, replace only own package/entrypoints.
        for name in [i.filename for i in infos]:
            lower=name.lower()
            if ((prefix and (not lower.startswith(('runtime/','models/','licenses/')) or lower=='licenses/vendor-manifest.json'))
                or '__pycache__' in lower or lower.endswith('.pyc') or
                lower.startswith(('templates/','template-drafts/')) or
                lower.startswith(('wheelhouse/','runtime/lib/site-packages/docuworks_integrations',
                                  'runtime/lib/site-packages/docuworks_ctypes','runtime/lib/site-packages/dw_workbench')) or
                lower.startswith(('docs/','examples/','packages/','requirements/','scripts/')) or
                lower in (inventory_name, 'reference/installed-packages.json') or
                lower in ('sha256sums.txt','tools_sha256sums.txt','tools_provenance.json','installed_packages.txt',
                          'pip_check.txt','readme_tools_ja.txt','public_packaging_changes.txt')):
                removed.append(name)
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,allowZip64=True) as out, baseline.open('rb') as raw:
            if len(original.infolist())!=len(set(i.filename for i in original.infolist())): raise ValueError('duplicate ZIP member')
            for index,info in enumerate(infos):
                name=info.filename
                if name in changes:
                    out.writestr(name,changes.pop(name)); continue
                if name in removed: continue
                origins[name]='baseline'
                if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name:
                    raise ValueError('unsafe ZIP path')
                if info.flag_bits&1: raise ValueError('encrypted baseline member')
                new=copy.copy(info); new.header_offset=out.fp.tell()
                out._writecheck(new); out._didModify=True
                raw.seek(info.header_offset)
                header=raw.read(30)
                if len(header)!=30 or header[:4]!=b'PK\x03\x04': raise ValueError('invalid baseline local header')
                name_length, extra_length=struct.unpack_from('<HH',header,26)
                raw.seek(name_length+extra_length,1)
                # Known CRC/sizes remove the need for a trailing data descriptor.
                # Rewrite the local filename when stripping the fixed public root.
                new.flag_bits &= ~8
                new.extra=b''
                out.fp.write(new.FileHeader(new.file_size>=zipfile.ZIP64_LIMIT or new.compress_size>=zipfile.ZIP64_LIMIT))
                remaining=info.compress_size
                while remaining:
                    chunk=raw.read(min(8*1024*1024,remaining))
                    if not chunk: raise EOFError('truncated baseline')
                    out.fp.write(chunk); remaining-=len(chunk)
                out.filelist.append(new); out.NameToInfo[name]=new; out.start_dir=out.fp.tell()
            for name,data in sorted(changes.items()): out.writestr(name,data)
    installed = []
    with zipfile.ZipFile(output) as archive:
        for name in archive.namelist():
            if name.startswith('runtime/Lib/site-packages/') and name.endswith('.dist-info/METADATA'):
                metadata = BytesParser().parsebytes(archive.read(name))
                installed.append(dict(name=metadata['Name'], version=metadata['Version']))
    installed_name = 'reference/installed-packages.json'
    with zipfile.ZipFile(output, 'a', zipfile.ZIP_DEFLATED) as archive:
        if installed_name in archive.namelist(): raise ValueError('stale installed package inventory')
        archive.writestr(installed_name, json.dumps(sorted(installed, key=lambda p: p['name'].lower()), indent=2).encode())
    origins[installed_name] = 'generated'
    if prefix:
        # The inherited inventory describes an older application. Replace it with
        # hashes of the vendor bytes actually retained in this new Portable.
        vendor_name='licenses/vendor-manifest.json'
        vendor=[]
        with zipfile.ZipFile(output) as archive:
            for info in archive.infolist():
                if not info.is_dir() and info.filename != vendor_name and origins[info.filename]=='baseline':
                    with archive.open(info) as stream:
                        vendor.append(dict(path=info.filename,bytes=info.file_size,sha256=hashlib.file_digest(stream,'sha256').hexdigest()))
        with zipfile.ZipFile(output,'a',zipfile.ZIP_DEFLATED) as archive:
            if vendor_name in archive.namelist(): raise ValueError('stale vendor inventory')
            archive.writestr(vendor_name,json.dumps(vendor,indent=2).encode())
        origins[vendor_name]='generated'
    entries=[]
    with zipfile.ZipFile(output) as archive:
        for info in archive.infolist():
            if not info.is_dir():
                with archive.open(info) as stream:
                    value=hashlib.file_digest(stream,'sha256').hexdigest()
                entries.append(dict(path=info.filename, bytes=info.file_size, sha256=value,
                                    origin=origins[info.filename]))
    with zipfile.ZipFile(output,'a',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inventory_name,json.dumps(dict(schema='dw-ocr-distribution-files',
            schema_version='1.0',candidate=True,baseline_sha256=expected_hash,
            excluded_self=inventory_name,files=entries),ensure_ascii=False,indent=2).encode('utf-8'))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None: raise ValueError('Portable CRC failed')
        names=archive.namelist()
        dist_infos={n.split('/')[3] for n in names if n.startswith('runtime/Lib/site-packages/docuworks_integrations-')}
        if dist_infos!={f'docuworks_integrations-{version}.dist-info'}: raise ValueError('old package remains')
    return dict(sha256=digest(output),bytes=output.stat().st_size,removed=removed)


def split(archive, destination, helper_baseline):
    archive,destination,helper_baseline=map(Path,(archive,destination,helper_baseline))
    destination.mkdir()  # fresh only
    size=archive.stat().st_size; whole=digest(archive)
    chunk_size=400*1024*1024-4096
    parts=[]
    with archive.open('rb') as stream:
        index=0
        while data:=stream.read(chunk_size):
            index+=1; name=f'dw_ocr_with_code.zip.{index:03d}'
            target=destination/f'ocr_part_{index:03d}_transport.zip'
            with zipfile.ZipFile(target,'x',zipfile.ZIP_STORED) as wrapper: wrapper.writestr(name,data)
            if target.stat().st_size>400*1024*1024: raise ValueError('transport exceeds 400 MiB')
            parts.append(dict(index=index,file=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    manifest=dict(schema='docuworks-portable-split',schema_version=1,output_file='dw_ocr_with_code.zip',
                  bytes=size,sha256=whole,chunk_size_bytes=chunk_size,parts=parts)
    helpers={name:(helper_baseline/name).read_bytes() for name in ('join_parts.ps1','join_parts.bat','verify_parts.bat','LICENSE')}
    script=helpers['join_parts.ps1'].decode('utf-8-sig')
    script=re.sub(r"\$ExpectedHash = '[a-f0-9]+'",f"$ExpectedHash = '{whole}'",script)
    script=re.sub(r'\$ExpectedBytes = \[long\]\d+',f'$ExpectedBytes = [long]{size}',script)
    script=script.replace('$parts.Count -ne 8',f'$parts.Count -ne {len(parts)}').replace('$i -lt 8',f'$i -lt {len(parts)}')
    script=script.replace('Exactly 8',f'Exactly {len(parts)}').replace('all 8',f'all {len(parts)}').replace('All 8',f'All {len(parts)}')
    helpers['join_parts.ps1']=script.encode('utf-8-sig')
    helpers['split_manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    helpers['README_JOIN_JA.txt']=(f'全{len(parts)}個のtransport ZIPと結合ツールを同じフォルダへ置き、join_parts.batを実行します。\n'
        '結合後のZIPを新しい場所へ展開してください。別版の部品と混用できません。\n').encode('utf-8-sig')
    with zipfile.ZipFile(destination/'ocr_join_tools.zip','x',zipfile.ZIP_DEFLATED) as helperzip:
        for name,data in helpers.items():
            (destination/name).write_bytes(data); helperzip.writestr(name,data)
    (destination/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(destination.iterdir()) if p.is_file()),encoding='ascii')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--baseline-sha256',required=True)
    p.add_argument('--wheels',type=Path,required=True)
    p.add_argument('--portable',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--split-dir',type=Path)
    p.add_argument('--helper-baseline',type=Path)
    p.add_argument('--release-version',default='v0.3.0')
    p.add_argument('--source',type=Path)
    p.add_argument('--baseline-prefix',help='Fixed root folder of a public Workbench vendor ZIP')
    p.add_argument('--dependency-wheel', action='append', type=Path, default=[])
    a=p.parse_args()
    print(json.dumps(build(a.baseline,a.baseline_sha256,a.wheels,a.portable,a.output,release_version=a.release_version,source=a.source,dependency_wheels=a.dependency_wheel,baseline_prefix=a.baseline_prefix)),flush=True)
    if a.split_dir: print(json.dumps(split(a.output,a.split_dir,a.helper_baseline)),flush=True)
