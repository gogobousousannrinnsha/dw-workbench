"""Optional GPU OCR adapter. Importing this module does not load Paddle."""
from __future__ import annotations

from pathlib import Path
from math import isfinite
import logging

from .models import OcrRegion, PixelPoint, PixelRect


def parse_paddle_result(payload: dict, width: int, height: int) -> tuple[OcrRegion, ...]:
    data = payload.get("res", payload)
    texts, scores, polygons = (data[key] for key in ("rec_texts", "rec_scores", "rec_polys"))
    if not (len(texts) == len(scores) == len(polygons)):
        raise ValueError("OCR texts/scores/polygons have different lengths")
    regions = []
    skipped = 0
    for text, score, polygon in zip(texts, scores, polygons):
        if not isinstance(text, str):
            raise ValueError("OCR text must be a non-empty string")
        if len(polygon) != 4 or any(len(p) != 2 for p in polygon):
            raise ValueError("OCR polygon must contain four xy points")
        points = tuple(PixelPoint(*p) for p in polygon)
        if any(p.x < 0 or p.y < 0 or p.x > width or p.y > height for p in points):
            raise ValueError("OCR polygon is outside the original image")
        area2 = sum(points[i].x * points[(i+1) % 4].y - points[(i+1) % 4].x * points[i].y for i in range(4))
        if not isfinite(area2) or abs(area2) < 1e-9:
            raise ValueError("OCR polygon has zero area")
        x, y = min(p.x for p in points), min(p.y for p in points)
        bbox = PixelRect(x, y, max(p.x for p in points) - x, max(p.y for p in points) - y)
        confidence = float(score)
        if not isfinite(confidence):
            raise ValueError("confidence must be finite")
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        # Validate even discarded rows: blank recognition is allowed, malformed
        # engine output is not. Keep the canonical OcrRegion contract strict.
        if not text.strip():
            skipped += 1
            continue
        regions.append(OcrRegion(text, bbox, confidence, points))
    if skipped:
        logging.getLogger(__name__).warning("Skipped %d blank OCR text region(s)", skipped)
    return tuple(regions)


class PaddleOcrEngine:
    def __init__(self, model_root: str | Path):
        self.model_root = Path(model_root).expanduser().resolve()
        self._engine = None
        self.last_raw = None

    def recognize(self, image_path: Path) -> tuple[OcrRegion, ...]:
        import os
        cache = Path(os.environ.get("DW_OCR_CACHE", str(self.model_root.parent / "ocr-cache")))
        profile = cache / "profile"
        profile.mkdir(parents=True, exist_ok=True)
        # Paddle 3.2.2 also uses expanduser('~/.cache') during import.
        # Redirect only this process for the synchronous OCR call, then restore.
        values = {"USERPROFILE": str(profile), "PADDLE_PDX_CACHE_HOME": str(cache / "paddlex"),
                  "PADDLE_HOME": str(cache / "paddle"), "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"}
        previous = {key: os.environ.get(key) for key in values}
        try:
            os.environ.update(values)
            return self._recognize(image_path)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def _recognize(self, image_path: Path) -> tuple[OcrRegion, ...]:
        import os
        from PIL import Image
        import numpy as np

        for name in ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"):
            if not (self.model_root / name / "inference.yml").is_file():
                raise FileNotFoundError(self.model_root / name / "inference.yml")
        # Keep all caches adjacent to the explicitly selected model directory.
        cache = Path(os.environ.get("DW_OCR_CACHE", str(self.model_root.parent / "ocr-cache")))
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache / "paddlex"))
        os.environ.setdefault("PADDLE_HOME", str(cache / "paddle"))
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        if self._engine is None:
            import paddle
            if not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1:
                raise RuntimeError("CUDA GPU is required; CPU fallback is disabled")
            paddle.set_device("gpu:0")
            from paddleocr import PaddleOCR
            from .model_loading import local_model_paths
            with local_model_paths(paddle.inference, self.model_root):
                self._engine = PaddleOCR(
                    text_detection_model_name="PP-OCRv6_medium_det",
                    text_recognition_model_name="PP-OCRv6_medium_rec",
                    text_detection_model_dir=str(self.model_root / "PP-OCRv6_medium_det"),
                    text_recognition_model_dir=str(self.model_root / "PP-OCRv6_medium_rec"),
                    device="gpu:0", use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False,
                    text_rec_score_thresh=0.0, text_recognition_batch_size=1,
                    enable_mkldnn=False,
                )
        self.last_raw = None
        with Image.open(image_path) as image:
            width, height = image.size
            # BGR array bypasses OpenCV's Windows Unicode path limitations.
            pixels = np.array(image.convert("RGB"))[:, :, ::-1].copy()
        results = list(self._engine.predict(pixels))
        if len(results) != 1:
            raise ValueError("Expected one OCR page result")
        self.last_raw = results[0].json
        return parse_paddle_result(self.last_raw, width, height)
