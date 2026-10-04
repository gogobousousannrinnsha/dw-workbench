"""Lightweight public API; optional backends are loaded only on use."""
from importlib import import_module

__version__ = "0.13.0"
_EXPORTS = {
    **dict.fromkeys(("TemplateDraft", "create_template_draft", "load_template_draft", "refresh_template_draft",
                    "update_template_draft", "preview_template_draft", "publish_template_draft",
                    "load_authoring_context", "list_template_versions"), "template_authoring"),
    "export_structured_csv": "structured_csv",
    "export_reviewed_xlsx": "reviewed_xlsx",
    **dict.fromkeys(("StructuredResult", "apply_rectangle_template", "load_structured_result"), "structured"),
    **dict.fromkeys(("RectangleTemplate", "register_rectangle_template", "load_rectangle_template"), "templates"),
    **dict.fromkeys(("ReviewSession", "ReviewedResult", "create_review_session", "load_review_session", "import_reviewed_result", "load_reviewed_result", "export_reviewed_jsonl", "get_reviewed_origins", "set_review_origins"), "reviewed"),
    **dict.fromkeys(("create_review_xdw", "read_review_edit"), "review_xdw"),
    **dict.fromkeys(("create_review_xdw_regions", "read_review_edits", "ReviewEditsCandidate"), "review_xdw"),
    **dict.fromkeys(("TextCorrection", "CorrectionSet", "EffectiveOcrRegion", "EffectiveOcrPage", "EffectiveOcrResult", "save_corrections", "load_corrections", "apply_corrections", "export_effective_jsonl"), "corrections"),
    **dict.fromkeys(("annotate_rectangles", "render_text_maps"), "derivatives"),
    "process_documents": "jobs",
    **dict.fromkeys(("ocr_folder", "OcrBatchResult", "BatchDocumentResult"), "batch"),
    **dict.fromkeys(("AddRectangle", "AddMarker", "AddText", "AnnotationPlan", "ExecutionReport", "OcrRegion", "PixelPoint", "PixelRect"), "models"),
    **dict.fromkeys(("OcrEngine", "JsonOcrEngine"), "ocr"),
    **dict.fromkeys(("bounding_rects", "find_contour_rects", "read_image_size"), "opencv"),
    **dict.fromkeys(("build_ocr_plan", "build_marker_plan"), "planning"),
    **dict.fromkeys(("OcrDocumentResult", "OcrPageResult", "CanonicalOcrRegion", "load_ocr_result", "save_ocr_result", "get_region", "export_jsonl"), "results"),
    "execute_plan": "executor", "PaddleOcrEngine": "paddle", "PageTransform": "transforms",
}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module("." + _EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
