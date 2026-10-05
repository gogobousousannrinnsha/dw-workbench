"""Export buildable MIT project source, retaining the established public notices."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re
import xml.etree.ElementTree as ET
from distribution_layout import load_layout, render_readme


def export(repo, baseline_public, output, *, release_version='v0.3.0'):
    repo, baseline_public, output=map(Path,(repo,baseline_public,output))
    if not re.fullmatch(r'v\d+\.\d+\.\d+', release_version):
        raise ValueError('invalid Portable release version')
    metadata=(repo/'packages/docuworks-integrations/pyproject.toml').read_text(encoding='utf-8')
    version=re.search(r'^version = "([^"]+)"$',metadata,re.M).group(1)
    runtime=(repo/'packages/docuworks-integrations/docuworks_integrations/__init__.py').read_text(encoding='utf-8')
    if f'__version__ = "{version}"' not in runtime or not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('stable package and runtime versions must match')
    core_metadata=(repo/'packages/docuworks-ctypes/pyproject.toml').read_text(encoding='utf-8')
    core_version=re.search(r'^version = "([^"]+)"$',core_metadata,re.M).group(1)
    core_runtime=(repo/'packages/docuworks-ctypes/docuworks_ctypes/__init__.py').read_text(encoding='utf-8')
    if not re.fullmatch(r'1\.\d+\.\d+',core_version) or f'__version__ = "{core_version}"' not in core_runtime:
        raise ValueError('stable Core 1.x package and runtime versions must match')
    load_layout(repo/"portable")
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True)
    for name in ('LICENSE','LICENSE_NOTICE.md','THIRD_PARTY_NOTICES.md'):
        shutil.copyfile(baseline_public/name,output/name)
    package_names = ['docuworks-ctypes', 'docuworks-integrations']
    if (repo/'packages/dw-workbench').is_dir():
        package_names.append('dw-workbench')
    for name in package_names:
        source=repo/'packages'/name
        destination=output/'packages'/name
        shutil.copytree(source,destination,ignore=shutil.ignore_patterns(
            '__pycache__','*.pyc','*.egg-info','build','dist','.pytest_cache','integration-artifacts',
            'template-drafts','sample-reviewed','pytest-cache-files-*'))
        metadata=destination/'pyproject.toml'
        text=metadata.read_text(encoding='utf-8').replace('license = {text = "Proprietary"}',
                                                        'license = {text = "MIT"}')
        metadata.write_text(text,encoding='utf-8')
        shutil.copyfile(baseline_public/'LICENSE',destination/'LICENSE')
    for folder in ('portable','requirements','docs','examples','scripts'):
        shutil.copytree(repo/folder,output/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns(
            '__pycache__','*.pyc','template-drafts','sample-reviewed','pytest-cache-files-*'))
    if (repo/'.github').is_dir():
        shutil.copytree(repo/'.github',output/'.github')
    for name in ('.gitattributes','.gitignore'):
        if (repo/name).is_file():
            shutil.copyfile(repo/name,output/name)
    # Historical development records stay recognizable as redacted records;
    # operational clone instructions point to the public repository instead.
    for path in [*(output/'docs').rglob('*'), *(output/'packages').rglob('*.md')]:
        if path.is_file() and path.suffix=='.xml':
            tree=ET.parse(path)
            for element in tree.iter():
                for key in ('hostname','file'): element.attrib.pop(key,None)
            tree.write(path,encoding='utf-8',xml_declaration=True)
        if not path.is_file() or path.suffix not in ('.md','.json'): continue
        text=path.read_text(encoding='utf-8')
        if path.name=='INSTALLED_PACKAGES.md':
            text=re.sub(r'\| docuworks-integrations \| [^|]+ \|',f'| docuworks-integrations | {version} |',text)
        pattern=r'https://github\.com/[A-Za-z0-9_-]+/docuworks-ocr(?:\.git)?'
        public='https://github.com/gogobousousannrinnsha/dw-ocr'
        text=re.sub(pattern+r'/blob/main/',public+'/blob/'+release_version+'/',text)
        text=re.sub(pattern,public,text)
        text=text.replace('cd docuworks-ocr', 'cd dw-ocr')
        text=re.sub(r'`[A-Za-z0-9_-]+/docuworks-ocr`','`gogobousousannrinnsha/dw-ocr`',text)
        if path.suffix == '.md':
            # Historical acceptance notes can name the author's local install.
            # Keep the notes, but remove that location from distributable copies.
            text=re.sub(r'(?i)[A-Z]:[\\/]+(?:Users|ai)[\\/]+[^`"\r\n]*', 'REDACTED_LOCAL_PATH', text)
        if path.suffix=='.json':
            def portable_evidence(value):
                if isinstance(value,dict): return {k:portable_evidence(v) for k,v in value.items()}
                if isinstance(value,list): return [portable_evidence(v) for v in value]
                if isinstance(value,str) and re.match(r'^[A-Za-z]:[\\/]',value):
                    return 'REDACTED_LOCAL_PATH'
                if isinstance(value,str) and re.search(pattern,value):
                    return 'REDACTED_PRIVATE_REPOSITORY'
                return value
            text=json.dumps(portable_evidence(json.loads(path.read_text(encoding='utf-8'))),ensure_ascii=False,indent=2)+'\n'
        path.write_text(text,encoding='utf-8')
    (output/'README.md').write_text(render_readme(repo/'portable', 'public_readme',
        {'docuworks-ctypes': core_version, 'docuworks-integrations': version}, release_version), encoding='utf-8')
    # Public requirements must refer to this export's local packages, never a private URL.
    files=[]
    for path in sorted(output.rglob('*')):
        if path.is_file():
            data=path.read_bytes()
            files.append(dict(path=path.relative_to(output).as_posix(),bytes=len(data),
                              sha256=hashlib.sha256(data).hexdigest()))
    (output/'source-manifest.json').write_text(json.dumps(dict(files=files),indent=2)+'\n',encoding='utf-8')
    return files


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--baseline-public',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--release-version',default='v0.3.0')
    a=p.parse_args(); print(len(export(a.repo,a.baseline_public,a.output,release_version=a.release_version)))
