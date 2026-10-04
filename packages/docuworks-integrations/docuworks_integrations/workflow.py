from __future__ import annotations

import ctypes
import hashlib
import json
import platform
import shutil
import time
from dataclasses import asdict
from pathlib import Path

from .executor import execute_plan
from .ocr import JsonOcrEngine
from .planning import build_marker_plan
from .transforms import PageTransform


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def write_json(path: Path, payload) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def render_page(source: Path, run_dir: Path, page: int, dpi: int, dll_path=None) -> dict:
    from docuworks_ctypes import XdwApi
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    from PIL import Image
    if dpi not in (300, 600):
        raise ValueError("dpi must be 300 or 600")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive one-based integer")
    before = sha256(source)
    copy = run_dir / "source.xdw"
    with source.open("rb") as src, copy.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    if sha256(copy) != before or sha256(source) != before:
        raise RuntimeError("source changed during copy")
    bmp = run_dir / "page.bmp"
    png = run_dir / "page.png"
    if len(str(bmp).encode("utf-16-le")) // 2 > 255:
        raise ValueError("SDK output path exceeds 255 UTF-16 code units")
    api = XdwApi.load(dll_path=dll_path)
    with api.open_document(copy) as doc:
        if page > doc.page_count:
            raise ValueError("page outside document")
        page_count = doc.page_count
        info = T.XDW_PAGE_INFO()
        info.nSize = ctypes.sizeof(info)
        check_result(doc.raw.XDW_GetPageInformation(doc.handle, page, ctypes.byref(info)), "XDW_GetPageInformation")
        options = T.XDW_IMAGE_OPTION()
        options.nSize = ctypes.sizeof(options)
        options.nDpi, options.nColor = dpi, C.XDW_IMAGE_COLOR
        check_result(doc.raw.XDW_ConvertPageToImageFileW(doc.handle, page, wchar_buffer(str(bmp)), ctypes.byref(options)), "XDW_ConvertPageToImageFileW")
    with Image.open(bmp) as image:
        width, height = image.size
        image.convert("RGB").save(png)
    if sha256(source) != before or sha256(copy) != before:
        raise RuntimeError("source changed during rendering")
    return {"source_path": str(source), "source_sha256": before, "page": page, "page_count": page_count,
            "page_width_mm": info.nWidth / 100, "page_height_mm": info.nHeight / 100,
            "render_dpi": dpi, "pixel_width": width, "pixel_height": height,
            "existing_annotations": info.nAnnotations, "runtime_version": api.runtime_info.version_text,
            "dll_path": str(api.runtime_info.dll_path), "image_sha256": sha256(png)}


def create_preview(image_path: Path, regions, run_dir: Path) -> None:
    """Compatibility entry; shared rendering lives outside the legacy workflow."""
    from ._preview import create_preview as implementation
    return implementation(image_path, regions, run_dir)


def ocr_xdw(input_xdw, run_dir, model_root, *, page=1, dpi=300, dll_path=None, engine=None) -> dict:
    from .paddle import PaddleOcrEngine
    source = Path(input_xdw).expanduser().resolve()
    root = Path(run_dir).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    engine = engine if engine is not None else PaddleOcrEngine(model_root)
    try:
        metadata = render_page(source, root, page, dpi, dll_path)
        write_json(root / "page-info.json", metadata)
        regions = tuple(engine.recognize(root / "page.png"))
        if getattr(engine, "last_raw", None) is not None:
            write_json(root / "ocr-raw.json", engine.last_raw)
        if not regions:
            raise ValueError("OCR found no text; no annotation was created")
        transform = PageTransform(metadata["pixel_width"], metadata["pixel_height"], metadata["page_width_mm"], metadata["page_height_mm"])
        for region in regions:
            transform.validate_rect(region.bbox)
        write_json(root / "regions.json", {"regions": [dict(region_id=i, **asdict(r)) for i, r in enumerate(regions, 1)]})
        create_preview(root / "page.png", regions, root)
        if sha256(source) != metadata["source_sha256"]:
            raise RuntimeError("source changed while OCR was running")
        files = {p.name: sha256(p) for p in root.iterdir() if p.is_file()}
        manifest = {"schema_version": 1, "status": "READY_FOR_SELECTION", "files": files,
                    "source_path": str(source), "source_sha256": metadata["source_sha256"],
                    "regions_count": len(regions), "elapsed_seconds": time.perf_counter() - started,
                    "python": platform.python_version(), "device": "gpu:0"}
        write_json(root / "run.json", manifest)
        write_json(root / "viewer-verification.json", {"status": "PENDING_MANUAL_REVIEW", "region_id": None,
                   "recognition_correct": None, "marker_overlaps_selected_text": None, "text_readable": None,
                   "no_repair_warning": None, "marker_editable": None})
        return manifest
    except Exception as exc:
        if getattr(engine, "last_raw", None) is not None and not (root / "ocr-raw.json").exists():
            write_json(root / "ocr-raw.json", engine.last_raw)
        write_json(root / "error.json", {"status": "FAILED", "type": type(exc).__name__, "message": str(exc)})
        raise


def verify_run(run_dir: Path) -> tuple[dict, dict]:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("status") != "READY_FOR_SELECTION":
        raise ValueError("run is not ready for selection")
    required = {"source.xdw", "page.png", "page-info.json", "regions.json", "preview.png", "regions.md"}
    if not required.issubset(manifest["files"]):
        raise ValueError("incomplete run manifest")
    for name, expected in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("invalid manifest file path")
        if sha256(run_dir / name) != expected:
            raise RuntimeError(f"preview input changed: {name}")
    if sha256(Path(manifest["source_path"])) != manifest["source_sha256"]:
        raise RuntimeError("original XDW changed since preview")
    metadata = json.loads((run_dir / "page-info.json").read_text(encoding="utf-8"))
    if metadata["source_sha256"] != manifest["source_sha256"] or manifest["files"]["source.xdw"] != manifest["source_sha256"]:
        raise ValueError("source identity mismatch")
    return manifest, metadata


def mark_region(run_dir, region_id, output_xdw, *, dry_run=False, dll_path=None) -> dict:
    root = Path(run_dir).expanduser().resolve()
    manifest, meta = verify_run(root)
    if isinstance(region_id, bool) or not isinstance(region_id, int) or region_id < 1:
        raise ValueError("region_id must be a positive integer")
    regions = JsonOcrEngine(root / "regions.json").recognize(root / "page.png")
    if region_id > len(regions):
        raise ValueError("region_id is outside the preview list")
    plan = build_marker_plan(root / "page.png", regions[region_id - 1],
             PageTransform(meta["pixel_width"], meta["pixel_height"], meta["page_width_mm"], meta["page_height_mm"]), page=meta["page"])
    output = Path(output_xdw).expanduser().resolve()
    report_path = output.with_suffix(".report.json")
    if report_path.exists() and not dry_run:
        raise FileExistsError(report_path)
    manifest_hash = sha256(root / "run.json")
    def recheck():
        if sha256(root / "run.json") != manifest_hash:
            raise RuntimeError("run manifest changed during marking")
        verify_run(root)
    report = execute_plan(plan, root / "source.xdw", output, dry_run=dry_run,
                          dll_path=dll_path or meta["dll_path"], precommit_check=recheck)
    payload = {"region_id": region_id, "text": regions[region_id - 1].text,
               "original_xdw": manifest["source_path"], "original_sha256": manifest["source_sha256"],
               "run_manifest_sha256": manifest_hash, "viewer_status": "PENDING_MANUAL_REVIEW",
               "plan": plan.to_dict(), "execution": report.to_dict()}
    if not dry_run:
        write_json(report_path, payload)
    return payload
