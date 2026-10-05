"""Python workflow example: create a review, then import a separately saved XDW."""
from pathlib import Path

from docuworks_integrations import (
    create_review_xdw, read_review_edit, load_ocr_result,
    save_corrections, apply_corrections, export_effective_jsonl,
)
from docuworks_integrations.results import sha256


def prepare(run_dir, region_id, review_dir, *, dll_path=None):
    return create_review_xdw(run_dir, region_id, review_dir, dll_path=dll_path)


def finish(run_dir, review_dir, edited_xdw, output_dir, *, dll_path=None):
    """output_dir must exist outside the OCR bundle; existing outputs are refused."""
    output = Path(output_dir)
    if (output / 'effective.jsonl').exists():
        raise FileExistsError(output / 'effective.jsonl')
    candidate = read_review_edit(run_dir, review_dir, edited_xdw, dll_path=dll_path)
    source = load_ocr_result(run_dir)
    if (source.run_id, source.manifest_sha256) != (candidate.run_id, candidate.manifest_sha256):
        raise RuntimeError('source changed before saving the review correction')
    if sha256(Path(review_dir) / 'review.json') != candidate.review_manifest_sha256 or sha256(edited_xdw) != candidate.edited_xdw_sha256:
        raise RuntimeError('review input changed before saving the correction')
    edits = [] if candidate.correction is None else [candidate.correction]
    saved = save_corrections(run_dir, edits, output / 'corrections.json')
    effective = apply_corrections(run_dir, saved)
    return export_effective_jsonl(effective, output / 'effective.jsonl')
