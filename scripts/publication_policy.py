"""Text-only distribution policy; never print matched content or credentials."""
import json
import re
from pathlib import PurePosixPath

MAX_FILE_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 20_000_000
TEXT_SUFFIXES = {'.py', '.pyi', '.md', '.rst', '.toml', '.txt', '.json', '.xml',
                 '.ps1', '.cmd', '.bat', '.ini', '.lock', '.yml', '.yaml', '.cfg', '.ini', '.typed'}
METADATA_NAMES = {'METADATA', 'WHEEL', 'RECORD', 'PKG-INFO', 'LICENSE', 'COPYING',
                  'NOTICE', '.gitignore', '.gitattributes', 'MANIFEST.in'}
PRIVATE_DIRS = {'sdk', 'models', 'local-data', 'ocr-cache', '.git', '.ssh', '.aws', 'template-drafts', 'sample-reviewed'}
SECRET_FIELDS = {'password', 'passwd', 'api_key', 'apikey', 'client_secret',
                 'access_token', 'refresh_token', 'secret_access_key'}
SECRET_PATTERNS = [
    re.compile(r'[A-Z]:[\\/]+Users[\\/]+[^\s\\/"\']+', re.I),
    re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+/'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'AKIA[A-Z0-9]{16}'),
    re.compile(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----'),
]


def path_error(name):
    path = PurePosixPath(name)
    if '\\' in name or path.is_absolute() or '..' in path.parts or ':' in name:
        return 'unsafe archive path'
    lower = path.name.lower()
    if any(part.lower() in PRIVATE_DIRS for part in path.parts):
        return 'private asset directory'
    if (lower == '.env' or lower.startswith(('.env.', 'credentials', 'secrets'))
            or lower in {'inference.json', 'inference.yml', 'inference.yaml'}):
        return 'private configuration or model file'
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in METADATA_NAMES:
        return 'non-allowlisted file type (document, model, SDK or binary)'
    return None


def content_error(data):
    if len(data) > MAX_FILE_BYTES:
        return 'file exceeds size limit'
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        return 'non UTF-8 content'
    if '\0' in text:
        return 'binary content'
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return 'private path or credential pattern'
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return None
    pending = [payload]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if any(str(key).lower() in SECRET_FIELDS and isinstance(value, str) and value.strip()
                   for key, value in item.items()):
                return 'credential field in JSON'
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    if isinstance(payload, dict):
        if payload.get('schema') in ('docuworks-ocr-result', 'docuworks-ocr-batch', 'dw-ocr-job',
                                     'docuworks-ocr-corrections', 'docuworks-ocr-effective-region',
                                     'docuworks-ocr-review', 'docuworks-ocr-review-identity',
                                     'docuworks-review-session', 'docuworks-review-session-identity',
                                     'docuworks-reviewed-result', 'docuworks-reviewed-text',
                                     'docuworks-template-draft', 'docuworks-template-authoring'):
            return 'OCR run manifest'
        raw = payload.get('res', payload)
        if isinstance(raw, dict) and {'rec_texts', 'rec_polys'} <= raw.keys():
            return 'raw OCR output'
    return None
