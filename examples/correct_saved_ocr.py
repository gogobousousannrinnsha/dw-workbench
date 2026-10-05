"""Example of the Python correction API; writes only new derived files."""
from pathlib import Path
import sys

from docuworks_integrations import (
    TextCorrection, load_ocr_result, get_region, save_corrections,
    load_corrections, apply_corrections, export_effective_jsonl,
)


def correct_one(run_dir, region_id, before_text, after_text, output_dir):
    """Correct one explicitly selected region; output_dir must already exist."""
    result = load_ocr_result(run_dir)
    region = get_region(result, region_id)
    message = f'{region.id}: {region.text!r} -> {after_text!r}'
    # A redirected Windows console can use a Western encoding. Escape only the
    # display text in that case; correction data stays unchanged UTF-8.
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    print(message.encode(encoding, errors='backslashreplace').decode(encoding))
    output_dir = Path(output_dir)
    # Never overwrite an earlier set or result. Choose another directory to revise.
    if (output_dir / 'effective.jsonl').exists():
        raise FileExistsError(output_dir / 'effective.jsonl')
    corrections = save_corrections(
        result.root, [TextCorrection(region.id, before_text, after_text)],
        output_dir / 'corrections.json',
    )
    reloaded = load_corrections(corrections.path)
    effective = apply_corrections(result.root, reloaded)
    return export_effective_jsonl(effective, output_dir / 'effective.jsonl')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    parser.add_argument('region_id')
    parser.add_argument('before_text')
    parser.add_argument('after_text')
    parser.add_argument('output_dir')
    args = parser.parse_args()
    print(correct_one(**vars(args)))
