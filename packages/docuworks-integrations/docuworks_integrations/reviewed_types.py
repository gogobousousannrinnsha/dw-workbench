"""Payload types for independent reviewed snapshots (all lengths are millimetres)."""
from typing import Literal, TypedDict


class ReviewOrigin(TypedDict):
    status: Literal['matched', 'missing', 'duplicate', 'invalid', 'foreign']
    annotation_id: str | None
    region_id: str | None
    raw_base64: str | None


class ReviewedItem(TypedDict):
    item_id: str
    order: int
    text: str
    x: float
    y: float
    width: float
    height: float
    rotation: int
    direction: Literal[0, 1]
    origin: ReviewOrigin
    diagnostics: list[str]


class ReviewedPage(TypedDict):
    page: int
    page_id: str
    width_mm: float
    height_mm: float
    rotation: Literal[0]
    items: list[ReviewedItem]


class ReviewedData(TypedDict):
    schema: Literal['docuworks-reviewed-result']
    schema_version: Literal['1.0']
    result_id: str
    review_id: str
    created_at: str
    source_xdw_sha256: str
    session_sha256: str
    coordinate_system: Literal['top-left-x-right-y-down']
    unit: Literal['mm']
    pages: list[ReviewedPage]


class ReviewedOriginReference(TypedDict):
    run_id: str
    canonical_manifest_sha256: str
    region_id: str


class OriginIssue(TypedDict):
    index: int | None
    reason: Literal['invalid', 'foreign']


class OriginEvidence(TypedDict):
    status: Literal['none', 'matched', 'invalid', 'foreign', 'partial']
    raw_base64: str | None
    issues: list[OriginIssue]


class ReviewedItemV2(TypedDict):
    item_id: str
    order: int
    text: str
    x: float
    y: float
    width: float
    height: float
    rotation: int
    direction: Literal[0, 1]
    origins: list[ReviewedOriginReference]
    origin_evidence: OriginEvidence
    diagnostics: list[str]


class ReviewedValidation(TypedDict):
    mode: Literal['identity']
    identity_checked: Literal[True]
    page_structure_checked: Literal[False]


class ReviewedPageV2(TypedDict):
    page: int
    page_id: str
    width_mm: float
    height_mm: float
    rotation: int
    items: list[ReviewedItemV2]


class ReviewedDataV2(TypedDict):
    schema: Literal['docuworks-reviewed-result']
    schema_version: Literal['2.0']
    result_id: str
    review_id: str
    created_at: str
    source_xdw_sha256: str
    session_sha256: str
    coordinate_system: Literal['top-left-x-right-y-down']
    unit: Literal['mm']
    validation: ReviewedValidation
    excluded_sticky_count: int
    pages: list[ReviewedPageV2]


class OriginAssignment(TypedDict):
    page: int
    order: int
    region_ids: list[str]
