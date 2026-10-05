"""Compare downloaded model archives and files with the recorded baseline."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-root', required=True, type=Path)
    args = parser.parse_args()
    root = args.model_root.resolve()
    baseline = Path(__file__).resolve().parents[1] / 'requirements/models-ppocrv6-medium.json'
    for model in json.loads(baseline.read_text(encoding='utf-8')):
        expected = {model['name'] + '_infer.tar': model['archive_sha256'], **model['files']}
        for relative, sha in expected.items():
            path = (root / relative.replace('\\', '/')).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Baseline path leaves model root')
            if not path.is_file() or digest(path) != sha:
                raise SystemExit('Model verification failed: ' + relative)
        print(model['name'] + ': hashes match baseline')


if __name__ == '__main__':
    main()
