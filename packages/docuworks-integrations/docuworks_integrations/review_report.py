"""Read-only review priorities derived from an immutable Canonical OCR bundle."""
from pathlib import Path
import json
import math
import os
from .results import load_ocr_result
from ._storage import owned_directory, publish_new


def build_review_report(result, *, threshold=0.8):
    """Flag confidence below threshold, unknown confidence and pages with no text.

    Confidence is an engine score, not a correctness/confirmation decision.
    IDs and coordinates refer to the original Canonical record, never a viewport.
    """
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold) or not 0 <= threshold <= 1):
        raise ValueError('threshold must be a finite number between 0 and 1')
    if result.root is None:
        raise ValueError('review report requires a saved result')
    current = load_ocr_result(result.root)
    if current.manifest_sha256 != result.manifest_sha256:
        raise RuntimeError('result changed since loading')
    flagged, pages = [], []
    low = unknown = total = 0
    for page in sorted(current.pages, key=lambda p: p.page):
        count = 0
        for region in page.regions:
            total += 1
            reason = 'confidence_unknown' if region.confidence is None else (
                'low_confidence' if region.confidence < threshold else None)
            if reason is None:
                continue
            low += reason == 'low_confidence'
            unknown += reason == 'confidence_unknown'
            count += 1
            flagged.append({'page': page.page, 'region_id': region.id, 'text': region.text,
                'confidence': region.confidence, 'reason': reason,
                'bbox_mm': dict(region.bbox_mm), 'polygon_mm': region.polygon_mm,
                'coordinate_system': page.coordinate_system, 'image': page.image})
        pages.append({'page': page.page, 'region_count': len(page.regions),
            'flagged_count': count, 'no_text_detected': not page.regions})
    processed = {p.page for p in current.pages}
    page_count = current.source.get('page_count')
    return {'schema': 'dw-ocr-review-report', 'schema_version': '1.0',
        'run_id': current.run_id, 'manifest_sha256': current.manifest_sha256,
        'source_sha256': current.source['sha256'], 'threshold': threshold,
        'summary': {'processed_pages': len(pages), 'regions': total, 'flagged_regions': len(flagged),
            'low_confidence': low, 'confidence_unknown': unknown,
            'no_text_pages': [p['page'] for p in pages if p['no_text_detected']],
            'unprocessed_pages': None if page_count is None else sorted(set(range(1, page_count+1))-processed)},
        'pages': pages, 'regions': flagged}


def export_review_report(result, output, *, threshold=0.8):
    """Atomically save a new report outside the input bundle; never overwrite."""
    report = build_review_report(result, threshold=threshold)
    if os.path.lexists(output):
        raise FileExistsError(output)
    output = Path(output).resolve()
    if output.is_relative_to(Path(result.root).resolve()):
        raise ValueError('review report must be outside immutable bundle')
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    with owned_directory(output.parent, '.review-report-') as staging:
        path = staging / 'report.json'
        data = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        with path.open('x', encoding='utf-8') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if json.loads(path.read_text(encoding='utf-8')) != json.loads(data):
            raise RuntimeError('report verification failed')
        current = load_ocr_result(result.root)
        if current.manifest_sha256 != report['manifest_sha256']:
            raise RuntimeError('result changed during report export')
        publish_new(path, output)
    return output
