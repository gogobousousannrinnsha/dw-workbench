from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from .models import OcrRegion, PixelRect, PixelPoint


@runtime_checkable
class OcrEngine(Protocol):
    def recognize(self, image_path: Path) -> Sequence[OcrRegion]: ...


class JsonOcrEngine:
    """Deterministic OCR-result adapter used for reproducible integrations."""

    def __init__(self, regions_path: str | Path):
        self.regions_path = Path(regions_path).expanduser().resolve()

    def recognize(self, image_path: Path) -> tuple[OcrRegion, ...]:
        del image_path
        payload = json.loads(self.regions_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            if "regions" not in payload:
                raise ValueError("OCR JSON object must contain a regions list")
            rows = payload["regions"]
        else:
            rows = payload
        if not isinstance(rows, list):
            raise ValueError("OCR JSON must be a list or an object with a regions list")
        result = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("bbox"), dict):
                raise ValueError("each OCR region must contain text and bbox")
            bbox = row["bbox"]
            result.append(
                OcrRegion(
                    text=row.get("text"),
                    bbox=PixelRect(bbox.get("x"), bbox.get("y"), bbox.get("width"), bbox.get("height")),
                    confidence=row.get("confidence"),
                    polygon=tuple(PixelPoint(p["x"], p["y"]) for p in row["polygon"]) if row.get("polygon") is not None else None,
                )
            )
        return tuple(result)
