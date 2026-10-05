"""Explicit multi-region review, then a single correction transaction."""
from pathlib import Path

from docuworks_integrations import (
    create_review_xdw_regions, read_review_edits, load_ocr_result,
    save_corrections, apply_corrections, export_effective_jsonl,
)
from docuworks_integrations.results import sha256


def prepare(run_dir, region_ids, review_dir, *, dll_path=None):
    return create_review_xdw_regions(run_dir, region_ids, review_dir, dll_path=dll_path)


def finish(run_dir, review_dir, edited_xdw, output_dir, *, dll_path=None):
    """output_dir must exist outside the source; all edits are saved together."""
    output = Path(output_dir)
    if (output / 'effective.jsonl').exists():
        raise FileExistsError(output / 'effective.jsonl')
    candidate = read_review_edits(run_dir, review_dir, edited_xdw, dll_path=dll_path)
    original = load_ocr_result(run_dir)
    if (original.run_id, original.manifest_sha256) != (candidate.run_id, candidate.manifest_sha256):
        raise RuntimeError('source changed before saving review corrections')
    if sha256(Path(review_dir) / 'review.json') != candidate.review_manifest_sha256 or sha256(edited_xdw) != candidate.edited_xdw_sha256:
        raise RuntimeError('review input changed before saving corrections')
    saved = save_corrections(run_dir, candidate.corrections, output / 'corrections.json')
    return export_effective_jsonl(apply_corrections(run_dir, saved), output / 'effective.jsonl')
