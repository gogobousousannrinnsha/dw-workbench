"""Source-owned Portable entries and documentation templates, validated before build."""
import json
from pathlib import Path, PurePosixPath


def load_layout(portable):
    portable = Path(portable)
    layout = json.loads((portable / 'layout.json').read_text(encoding='utf-8'))
    if layout.get('schema') != 'dw-ocr-portable-layout' or layout.get('schema_version') != '1.0':
        raise ValueError('unsupported Portable layout')
    files = layout['files']
    templates = layout['templates']
    if not isinstance(files, list) or not files or len(files) != len(set(files)):
        raise ValueError('Portable entries must be nonempty and unique')
    if set(templates) != {'public_readme', 'portable_readme'}:
        raise ValueError('Portable README templates are required')
    for name in [*files, *templates.values()]:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
            raise ValueError('unsafe Portable entry')
        source = portable / name
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(portable.resolve()):
            raise ValueError('missing or unsafe Portable source: ' + name)
    actual = {p.relative_to(portable).as_posix() for p in portable.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.bat', '.py', '.ini')}
    if actual != set(files):
        raise ValueError('Portable source inventory does not match layout')
    return layout


def render_readme(portable, kind, versions, release_version):
    layout = load_layout(portable)
    text = (Path(portable) / layout['templates'][kind]).read_text(encoding='utf-8')
    for key, value in {'RELEASE_VERSION': release_version, 'CORE_VERSION': versions['docuworks-ctypes'],
                       'INTEGRATIONS_VERSION': versions['docuworks-integrations']}.items():
        text = text.replace('@' + key + '@', value)
    if '@RELEASE_VERSION@' in text or '@CORE_VERSION@' in text or '@INTEGRATIONS_VERSION@' in text:
        raise ValueError('unresolved README version')
    return text
