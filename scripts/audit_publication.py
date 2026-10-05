"""Audit distributable source files. Runtime directories are excluded explicitly."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', 'work', 'local-data', 'models', 'dist', 'build', 'ocr-cache',
            '__pycache__', '.pytest_cache', 'integration-artifacts', 'template-drafts'}
ALLOWED = {'.py', '.md', '.toml', '.txt', '.json', '.xml', '.ps1', '.cmd', '.bat', '.ini', '.lock', '.yml', '.yaml'}
SPECIAL = {'.gitignore', '.gitattributes', 'LICENSE', 'MANIFEST.in'}
PATTERNS = [
    re.compile(r'[A-Z]:[\\/]+Users[\\/]+[^\s\\/"\']+', re.I),
    re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+/'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'AKIA[A-Z0-9]{16}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def source_files():
    # If this is the actual repository, inspect tracked files even when ignored.
    probe = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT,
                           capture_output=True, text=True)
    tracked = set()
    if probe.returncode == 0 and Path(probe.stdout.strip()).resolve() == ROOT:
        proc = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
        tracked = {ROOT / p.decode('utf-8') for p in proc.stdout.split(b'\0') if p}
    files = set(tracked)
    for p in ROOT.rglob('*'):
        rel = p.relative_to(ROOT)
        if rel.parts[0] == 'templates': continue  # runtime data, not portable/templates README sources
        if any(part in EXCLUDED or part.startswith(('.venv', 'venv')) or part.endswith('.egg-info') for part in rel.parts):
            continue
        if p.is_file():
            files.add(p)
    return sorted(files)


def main():
    errors = []
    files = source_files()
    total = 0
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        if p.is_symlink():
            errors.append(rel + ': symbolic link'); continue
        if not p.is_file():
            errors.append(rel + ': tracked file missing'); continue
        size = p.stat().st_size; total += size
        if p.suffix.lower() not in ALLOWED and p.name not in SPECIAL:
            errors.append(rel + ': excluded file type'); continue
        if size > 1_000_000:
            errors.append(rel + ': exceeds 1 MB'); continue
        try:
            content = p.read_text(encoding='utf-8-sig')
        except UnicodeError:
            errors.append(rel + ': non UTF-8'); continue
        if any(pattern.search(content) for pattern in PATTERNS):
            errors.append(rel + ': private path or credential pattern')
        if p.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', content):
                if target.startswith(('http://', 'https://', '#', 'mailto:')):
                    continue
                target = target.split('#')[0]
                if target and not (p.parent / target).exists():
                    errors.append(rel + ': broken link ' + target)
    print(json.dumps({'files': len(files), 'bytes': total, 'errors': errors}, indent=2))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
