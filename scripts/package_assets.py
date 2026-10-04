"""Create deterministic ZIPs and split a large Portable ZIP for GitHub assets."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def archive_folder(folder: Path, target: Path, prefix: str) -> dict:
    if target.exists():
        raise FileExistsError(target)
    files = sorted(p for p in folder.rglob('*') if p.is_file() and '.git' not in p.relative_to(folder).parts
                   and '__pycache__' not in p.relative_to(folder).parts and p.suffix not in ('.pyc', '.pyo'))
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for index, path in enumerate(files):
            if path.is_symlink():
                raise ValueError(f'Symbolic link: {path}')
            info = zipfile.ZipInfo(prefix + '/' + path.relative_to(folder).as_posix(), (2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            with path.open('rb') as source, archive.open(info, 'w', force_zip64=True) as destination:
                shutil.copyfileobj(source, destination, 8 * 1024 * 1024)
            if index % 2000 == 0:
                print(f'{target.name}: {index}/{len(files)} files', flush=True)
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('ZIP CRC failure: ' + bad)
    return {'name': target.name, 'bytes': target.stat().st_size, 'sha256': digest(target), 'files': len(files), 'crc_passed': True}

def portable(root: Path) -> dict:
    assets = root / 'assets'
    folder = root / 'portable-staging' / 'DW-Workbench-v0.2.0'
    full = root / 'DW-Workbench-v0.2.0-Portable.zip'
    result = archive_folder(folder, full, folder.name)
    if result['bytes'] < 2 * 1024**3:
        shutil.move(full, assets / full.name)
        return {'mode': 'single-zip', 'zip': result}
    parts = []
    chunk_size = 1024**3
    with full.open('rb') as stream:
        index = 1
        remaining = result['bytes']
        while remaining:
            target = assets / f'{full.name}.{index:03d}'
            if target.exists():
                raise FileExistsError(target)
            part_size = min(chunk_size, remaining)
            pending = part_size
            part_hash = hashlib.sha256()
            with target.open('xb') as output:
                while pending:
                    data = stream.read(min(pending, 8 * 1024 * 1024))
                    if not data:
                        raise ValueError('Unexpected end of complete ZIP')
                    output.write(data)
                    part_hash.update(data)
                    pending -= len(data)
            parts.append({'name': target.name, 'bytes': part_size, 'sha256': part_hash.hexdigest()})
            remaining -= part_size
            print(f'Created {target.name}', flush=True)
            index += 1
    manifest = {'format': 'dw-workbench-portable-parts-v1', 'root_directory': folder.name,
                'created_utc': datetime.now(timezone.utc).isoformat(), 'zip': result, 'parts': parts}
    (assets / 'PORTABLE-MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for name in ('Restore-Portable.ps1', 'Restore-Portable.bat'):
        shutil.copy2(root / name, assets / name)
    return {'mode': 'split-zip', **manifest}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('kind', choices=('portable', 'manual', 'source'))
    args = parser.parse_args()
    if args.kind == 'portable':
        result = portable(args.root)
    else:
        folder = args.root / ('manual-public' if args.kind == 'manual' else 'public-source')
        target = args.root / 'assets' / f'DW-Workbench-v0.2.0-{args.kind}.zip'
        result = archive_folder(folder, target, f'DW-Workbench-v0.2.0-{args.kind}')
        if args.kind == 'manual':
            shutil.copy2(folder / 'DW-Workbench_v0.2.0_図解操作マニュアル.pdf',
                         args.root / 'assets' / 'DW-Workbench-v0.2.0-manual.pdf')
    (args.root / 'evidence' / f'{args.kind}-archive.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
