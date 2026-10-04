from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from docuworks_ctypes import AnnotationType
from docuworks_ctypes.simple import open_xdw

from .models import AddRectangle, AddText, AddMarker, AnnotationPlan, ExecutionReport


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _paths(input_xdw: str | Path, output_xdw: str | Path) -> tuple[Path, Path]:
    source = Path(input_xdw).expanduser().resolve()
    output = Path(output_xdw).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == output:
        raise ValueError("input and output XDW paths must differ")
    if output.exists():
        raise FileExistsError(output)
    if not output.parent.is_dir():
        raise FileNotFoundError(output.parent)
    return source, output


def execute_plan(
    plan: AnnotationPlan,
    input_xdw: str | Path,
    output_xdw: str | Path,
    *,
    dry_run: bool = False,
    dll_path: str | Path | None = None,
    codepage: int | None = None,
    precommit_check=None,
) -> ExecutionReport:
    if not isinstance(plan, AnnotationPlan):
        raise TypeError("plan must be AnnotationPlan")
    source, output = _paths(input_xdw, output_xdw)
    before_hash = _sha256(source)
    image_hash = _sha256(plan.image_path)
    if dry_run:
        after_hash = _sha256(source)
        return ExecutionReport(
            status="DRY_RUN",
            input_xdw=str(source),
            output_xdw=str(output),
            image_path=str(plan.image_path),
            page=plan.page,
            planned_operations=len(plan.operations),
            executed_operations=0,
            annotations_before=None,
            annotations_after=None,
            input_sha256_before=before_hash,
            input_sha256_after=after_hash,
            image_sha256=image_hash,
            output_sha256=None,
            verified=before_hash == after_hash and not output.exists(),
        )

    # tempfile.TemporaryDirectory uses a special 0700 ACL on recent Windows
    # Python builds.  A restricted host can then be unable to re-open its own
    # directory.  Create one collision-resistant sibling with normal inherited
    # permissions and always remove that exact directory in the finally block.
    temporary = output.parent / f".docuworks-integrations-{uuid.uuid4().hex}"
    temporary.mkdir()
    try:
        working = temporary / "working.xdw"
        shutil.copy2(source, working)
        if _sha256(working) != before_hash or _sha256(source) != before_hash:
            raise RuntimeError("input changed while copying")
        created = []
        expected_types = tuple(
            AnnotationType.RECTANGLE if isinstance(operation, AddRectangle) else
            AnnotationType.MARKER if isinstance(operation, AddMarker) else AnnotationType.TEXT
            for operation in plan.operations
        )
        with open_xdw(working, writable=True, dll_path=dll_path, codepage=codepage) as document:
            page = document.page(plan.page)
            annotations_before = len(page.annotations())
            for operation in plan.operations:
                if isinstance(operation, AddRectangle):
                    created.append(
                        page.rectangle(
                            x=operation.rect.x,
                            y=operation.rect.y,
                            width=operation.rect.width,
                            height=operation.rect.height,
                        )
                    )
                elif isinstance(operation, AddText):
                    created.append(
                        page.text(
                            operation.text,
                            x=operation.position.x,
                            y=operation.position.y,
                            font_size=operation.font_size,
                        )
                    )
                elif isinstance(operation, AddMarker):
                    created.append(page.marker(operation.points, border_color=operation.border_color,
                                               border_width=operation.border_width,
                                               border_transparent=operation.border_transparent))
                else:
                    raise TypeError(f"unsupported operation: {type(operation).__name__}")
            if tuple(annotation.type for annotation in created) != expected_types:
                raise RuntimeError("created annotation types do not match the plan")
            document.save()
        with open_xdw(working, writable=False, dll_path=dll_path, codepage=codepage) as document:
            reopened = document.page(plan.page).annotations()
            annotations_after = len(reopened)
            if annotations_after != annotations_before + len(plan.operations):
                raise RuntimeError("save/reopen annotation count does not match the plan")
            reopened_tail = reopened[-len(plan.operations):] if plan.operations else ()
            if tuple(annotation.type for annotation in reopened_tail) != expected_types:
                raise RuntimeError("save/reopen annotation order or types do not match the plan")
            for operation, annotation in zip(plan.operations, reopened_tail):
                if isinstance(operation, AddMarker):
                    verify_marker(annotation, operation)
                    continue
                expected = operation.rect if isinstance(operation, AddRectangle) else operation.position
                position = annotation.position
                if abs(position.x - expected.x) > 0.01 or abs(position.y - expected.y) > 0.01:
                    raise RuntimeError("save/reopen annotation position does not match the plan")
                if isinstance(operation, AddText):
                    actual_text = annotation.core.get_standard_attribute("%Text")
                    if actual_text != operation.text:
                        raise RuntimeError("save/reopen text does not match the plan")
        if _sha256(source) != before_hash or _sha256(plan.image_path) != image_hash:
            raise RuntimeError("input or image changed during execution")
        if precommit_check is not None:
            precommit_check()
        if output.exists():
            raise FileExistsError(output)
        working.rename(output)
    finally:
        shutil.rmtree(temporary)

    after_hash = _sha256(source)
    if after_hash != before_hash:
        raise RuntimeError("input XDW changed during execution")
    return ExecutionReport(
        status="VERIFIED",
        input_xdw=str(source),
        output_xdw=str(output),
        image_path=str(plan.image_path),
        page=plan.page,
        planned_operations=len(plan.operations),
        executed_operations=len(plan.operations),
        annotations_before=annotations_before,
        annotations_after=annotations_after,
        input_sha256_before=before_hash,
        input_sha256_after=after_hash,
        image_sha256=image_hash,
        output_sha256=_sha256(output),
        verified=True,
    )


def verify_marker(annotation, operation: AddMarker) -> None:
    from docuworks_ctypes.geometry import mm_to_xdw
    core = annotation.core
    for name, expected in (("%BorderColor", int(operation.border_color)),
                           ("%BorderWidth", operation.border_width),
                           ("%BorderTransparent", operation.border_transparent)):
        if core.get_standard_attribute(name) != expected:
            raise RuntimeError(f"save/reopen marker {name} mismatch")
    # Core decodes the raw delta array to absolute page coordinates in mm.
    # annotation.position is the outer stroke box, not the line's first point.
    points = core.get_standard_attribute("%Points")
    if len(points) != 2:
        raise RuntimeError("save/reopen marker point count mismatch")
    for actual, expected in zip(points, operation.points):
        if abs(actual.x - mm_to_xdw(expected.x) / 100) > 0.010001 or abs(actual.y - mm_to_xdw(expected.y) / 100) > 0.010001:
            raise RuntimeError("save/reopen marker geometry mismatch")
