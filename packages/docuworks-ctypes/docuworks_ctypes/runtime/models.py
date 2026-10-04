from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InstalledDocuWorksInfo:
    version: tuple[int, ...]
    trial: bool | None = None


@dataclass(frozen=True)
class DllBundle:
    directory: Path
    xdwapi: Path
    xdwapia: Path
    xdwapib: Path
    xdwxml: Path | None
    source: str

    @classmethod
    def from_directory(cls, directory: Path, source: str) -> "DllBundle":
        resolved = directory.expanduser().resolve()
        xml = resolved / "xdwxml.dll"
        return cls(
            directory=resolved,
            xdwapi=resolved / "xdwapi.dll",
            xdwapia=resolved / "xdwapia.dll",
            xdwapib=resolved / "xdwapib.dll",
            xdwxml=xml if xml.is_file() else None,
            source=source,
        )

    @property
    def identity(self) -> str:
        return str(self.xdwapi).casefold()


@dataclass(frozen=True)
class DllFileInfo:
    path: Path
    machine: int
    file_version: tuple[int, ...]
    product_version: tuple[int, ...]
    sha256: str


@dataclass(frozen=True)
class StaticValidation:
    valid: bool
    errors: tuple[str, ...]
    files: tuple[DllFileInfo, ...] = ()
    missing_exports: tuple[str, ...] = ()

    @property
    def main_file(self) -> DllFileInfo | None:
        return self.files[0] if self.files else None


@dataclass(frozen=True)
class ProbeResult:
    attempted: bool
    get_information_ok: bool = False
    reported_version: str | None = None
    document_probe_requested: bool = False
    document_open_ok: bool | None = None
    document_page_count: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    xdw_error_code: int | None = None
    timed_out: bool = False
    crashed: bool = False
    duration_seconds: float = 0.0

    @property
    def eligible(self) -> bool:
        if not self.attempted or not self.get_information_ok:
            return False
        return not self.document_probe_requested or self.document_open_ok is True


@dataclass(frozen=True)
class CandidateReport:
    bundle: DllBundle
    static: StaticValidation
    probe: ProbeResult
    score: tuple[int, ...] = ()
    selected: bool = False
    rejection_reason: str | None = None

    def mark_selected(self) -> "CandidateReport":
        return replace(self, selected=True)


@dataclass(frozen=True)
class ResolutionReport:
    candidates: tuple[CandidateReport, ...]
    selected: DllBundle | None
    installed_docuworks: InstalledDocuWorksInfo | None
    verification_document: Path | None
    explicit: bool

    @property
    def selected_report(self) -> CandidateReport | None:
        return next((item for item in self.candidates if item.selected), None)

    def to_dict(self) -> dict[str, Any]:
        def convert(value):
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {str(key): convert(item) for key, item in value.items()}
            return value

        return convert(asdict(self))
