"""Business contracts. No GUI, SDK, OCR engine or persistence dependencies."""
from dataclasses import dataclass, asdict, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import math
import unicodedata
import uuid
from datetime import datetime, timezone


def identifier():
    return uuid.uuid4().hex


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class RuleError(ValueError):
    pass


class StaleRevision(RuleError):
    pass


class DimensionMismatch(RuleError):
    """An assigned template cannot OCR this target's saved page geometry."""


class Status(StrEnum):
    MISSING = "missing"
    PENDING = "pending"
    ACCEPTED = "accepted"
    DEFERRED = "deferred"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class PageInfo:
    width_mm: float
    height_mm: float
    rotation: int = 0

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in (self.width_mm, self.height_mm)):
            raise RuleError("ページ寸法が不正です")
        if self.rotation not in (0, 90, 180, 270):
            raise RuleError("ページの向きが不正です")


@dataclass(frozen=True)
class SourceSnapshot:
    id: str
    name: str
    sha256: str
    path: str
    pages: tuple[PageInfo, ...]


@dataclass(frozen=True)
class Anchor:
    source_id: str
    source_hash: str
    page: int
    rect: tuple[float, float, float, float]  # x, y, width, height in page mm

    def validate(self, source):
        if self.source_id != source.id or self.source_hash != source.sha256:
            raise RuleError("根拠と原本の内容が一致しません")
        if not 1 <= self.page <= len(source.pages):
            raise RuleError("根拠ページが不正です")
        x, y, w, h = self.rect
        p = source.pages[self.page - 1]
        if not all(math.isfinite(v) for v in self.rect) or min(x, y) < 0 or min(w, h) <= 0:
            raise RuleError("根拠範囲が不正です")
        if x + w > p.width_mm + .001 or y + h > p.height_mm + .001:
            raise RuleError("根拠範囲がページ外です")


@dataclass(frozen=True)
class FieldSchema:
    id: str
    name: str
    kind: str = "text"
    required: bool = True
    unit: str = ""

    def __post_init__(self):
        if not self.id or not self.name.strip() or self.kind not in ("text", "decimal"):
            raise RuleError("項目名・型が不正です")

    def canonical(self, value):
        if not isinstance(value, str) or not value.strip():
            raise RuleError("採用値を入力してください")
        if self.kind == "text":
            return value  # IDs and fullwidth spelling are intentionally retained.
        try:
            result = Decimal(unicodedata.normalize("NFKC", value).strip())
        except InvalidOperation as exc:
            raise RuleError("数値は小数点付きの十進表記で入力してください（単位は別欄）") from exc
        if not result.is_finite() or abs(result.adjusted()) > 1000:
            raise RuleError("数値が不正、または大きすぎます")
        return format(result, "f")


@dataclass(frozen=True)
class ResultSchema:
    id: str
    version: int
    name: str
    fields: tuple[FieldSchema, ...]

    def validate(self):
        if not self.id or not isinstance(self.version, int) or self.version < 1 or not self.name.strip() or not self.fields:
            raise RuleError("項目定義のID・版・名前・項目が必要です")
        if len({f.id for f in self.fields}) != len(self.fields):
            raise RuleError("項目IDが重複しています")
        for item in self.fields:
            if not isinstance(item, FieldSchema):
                raise RuleError("項目定義が不正です")


@dataclass(frozen=True)
class ExtractionProfile:
    id: str
    version: int
    name: str
    pages: tuple[PageInfo, ...]
    fields: tuple[FieldSchema, ...]
    regions: dict  # field ID -> {page, rect}; immutable after registration
    scope: str = "document"
    schema_id: str = ""
    schema_version: int = 1

    def validate(self):
        if not self.id or not self.name.strip() or not self.pages or not self.fields or self.version < 1:
            raise RuleError("設定名・ページ・項目が必要です")
        if self.scope not in ("document", "page") or self.schema_version < 1:
            raise RuleError("設定の処理単位・項目定義版が不正です")
        if self.scope == "page" and (len(self.pages) != 1 or any(r.get("page") != 1 for r in self.regions.values())):
            raise RuleError("ページ用設定は一ページの範囲として登録してください")
        if len({f.id for f in self.fields}) != len(self.fields):
            raise RuleError("項目IDが重複しています")
        probe = SourceSnapshot("profile", "", "profile", "", self.pages)
        if set(self.regions) != {f.id for f in self.fields}:
            raise RuleError("すべての項目の読み取り範囲を指定してください")
        for r in self.regions.values():
            Anchor("profile", "profile", r["page"], tuple(r["rect"])).validate(probe)

    def matches(self, source, target_page=None):
        if self.scope == "page":
            if not isinstance(target_page, int) or not 1 <= target_page <= len(source.pages):
                return False
            pages = (source.pages[target_page - 1],)
        else:
            pages = source.pages
        return len(self.pages) == len(pages) and all(
            abs(a.width_mm-b.width_mm) < .01 and abs(a.height_mm-b.height_mm) < .01 and a.rotation == b.rotation
            for a, b in zip(self.pages, pages))

    def resolve_region(self, field_id, target_page=None):
        try:
            region = self.regions[field_id]
        except KeyError as exc:
            raise RuleError("設定に項目の読み取り範囲がありません") from exc
        if self.scope == "page":
            if not isinstance(target_page, int) or target_page < 1:
                raise RuleError("適用先のページを指定してください")
            page = target_page
        else:
            page = region["page"]
        return {"page": page, "rect": list(region["rect"])}


@dataclass(frozen=True)
class PageAssignment:
    source_id: str
    page: int
    revision: int
    state: str
    current_record_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class TemplateRecordRevision:
    id: str
    revision: int
    active: bool
    source_id: str
    page: int | None
    assignment_revision: int
    profile_id: str
    profile_version: int


@dataclass(frozen=True)
class TemplateSourceState:
    source: SourceSnapshot
    mode: str | None
    mode_revision: int
    assignments: tuple[PageAssignment, ...]
    records: tuple[TemplateRecordRevision, ...]


@dataclass(frozen=True)
class TemplateApplicationEntry:
    source_id: str
    source_name: str
    page: int | None  # 0 is the document target; None is an invalid/empty request.
    action: str  # apply, same, skip
    reason: str
    geometry_matches: bool | None
    current_state: str
    current_record_id: str | None = None
    assignment_revision: int | None = None
    record_revision: int | None = None
    previous_profile_id: str | None = None
    previous_profile_version: int | None = None


@dataclass(frozen=True)
class TemplateModeChange:
    source_id: str
    source_name: str
    old_mode: str | None
    new_mode: str
    expected_revision: int


@dataclass(frozen=True)
class TemplateApplicationPlan:
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    unassigned_only: bool
    entries: tuple[TemplateApplicationEntry, ...]
    mode_changes: tuple[TemplateModeChange, ...]
    captured_sources: tuple[TemplateSourceState, ...]
    targets: tuple[tuple[str, tuple[int | None, ...]], ...]


@dataclass(frozen=True)
class TemplateApplicationResult:
    applied: int
    same: int
    skipped: int
    record_ids: tuple[str, ...]
    mode_changes: int


@dataclass(frozen=True)
class Observation:
    id: str
    source_id: str
    source_hash: str
    field_id: str
    anchor: Anchor
    text: str
    confidence: float
    engine: dict
    polygon_mm: tuple = ()


@dataclass(frozen=True)
class Candidate:
    id: str
    field_id: str
    text: str
    anchor: Anchor
    observation_ids: tuple[str, ...]


@dataclass
class FieldState:
    value: str = ""
    unit: str = ""
    raw: str = ""
    anchor: Anchor | None = None
    status: str = Status.MISSING
    reason: str = ""
    accepted_revision: int | None = None
    candidate_id: str | None = None

    def edit(self, schema, *, value, unit, raw, anchor, source, candidate_id=None, reason=None):
        if anchor is not None:
            anchor.validate(source)
        changed = (value, unit, raw, anchor, candidate_id) != (self.value, self.unit, self.raw, self.anchor, self.candidate_id)
        self.value, self.unit, self.raw, self.anchor, self.candidate_id = value, unit, raw, anchor, candidate_id
        if changed:
            self.status = Status.PENDING if value or anchor else Status.MISSING
            self.reason, self.accepted_revision = "", None
        if reason is not None:
            self.reason = reason
            if self.status in (Status.DEFERRED, Status.NOT_APPLICABLE) and not reason.strip():
                self.status = Status.PENDING if value or anchor else Status.MISSING
                self.accepted_revision = None

    def accept(self, schema, source, revision):
        value = schema.canonical(self.value)
        if self.anchor is None:
            raise RuleError("確認済みには原本の範囲指定が必要です")
        self.anchor.validate(source)
        self.value = value
        self.status, self.reason, self.accepted_revision = Status.ACCEPTED, "", revision

    def mark(self, schema, status, reason):
        if status not in (Status.DEFERRED, Status.NOT_APPLICABLE) or not reason.strip():
            raise RuleError("保留・対象外には理由が必要です")
        if schema.required and status == Status.NOT_APPLICABLE:
            raise RuleError("必須項目は対象外にできません")
        self.status, self.reason, self.accepted_revision = status, reason, None


@dataclass(frozen=True)
class FinalizedDataset:
    id: str
    created: str
    groups: tuple
    excluded: tuple
    format_version: int = 1


def field_complete(field, state):
    return state.status == Status.ACCEPTED or bool(
        not field.required and state.status == Status.NOT_APPLICABLE and state.reason.strip())


def unfinished(profile, states):
    return [f.name for f in profile.fields if not field_complete(f, states[f.id])]


def profile_from(data):
    return ExtractionProfile(data["id"], data["version"], data["name"],
        tuple(PageInfo(**p) for p in data["pages"]), tuple(FieldSchema(**f) for f in data["fields"]), data["regions"],
        data.get("scope", "document"), data.get("schema_id", ""), data.get("schema_version", 1))


def schema_from(data):
    return ResultSchema(data["id"], data["version"], data["name"], tuple(FieldSchema(**f) for f in data["fields"]))


def source_from(data):
    return SourceSnapshot(data["id"], data["name"], data["sha256"], data["path"], tuple(PageInfo(**p) for p in data["pages"]))


def state_from(data):
    d = dict(data)
    a = d.get("anchor")
    d["anchor"] = Anchor(a["source_id"], a["source_hash"], a["page"], tuple(a["rect"])) if a else None
    return FieldState(**d)


def crop_box(anchor, page, width, height):
    x, y, w, h = anchor.rect
    return (max(0, math.floor(x/page.width_mm*width)), max(0, math.floor(y/page.height_mm*height)),
        min(width, math.ceil((x+w)/page.width_mm*width)), min(height, math.ceil((y+h)/page.height_mm*height)))


def pixel_to_mm(x, y, page, width, height, offset=(0, 0)):
    return ((x+offset[0])/width*page.width_mm, (y+offset[1])/height*page.height_mm)
