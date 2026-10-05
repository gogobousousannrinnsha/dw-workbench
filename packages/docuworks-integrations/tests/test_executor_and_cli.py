from __future__ import annotations

import json
from pathlib import Path

import pytest

import docuworks_integrations.cli as cli
import docuworks_integrations.executor as executor
from docuworks_integrations import JsonOcrEngine, PageTransform, build_ocr_plan, execute_plan


def _plan(tmp_path: Path):
    image = tmp_path / "page.png"
    image.write_bytes(b"image")
    regions = tmp_path / "regions.json"
    regions.write_text(
        json.dumps([{"text": "A", "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}, "confidence": 1}]),
        encoding="utf-8",
    )
    return build_ocr_plan(image, JsonOcrEngine(regions), PageTransform(10, 10, 100, 100))


def test_dry_run_never_loads_dll_or_writes_output(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    source = tmp_path / "source.xdw"
    source.write_bytes(b"xdw")
    output = tmp_path / "output.xdw"
    monkeypatch.setattr(executor, "open_xdw", lambda *args, **kwargs: pytest.fail("DLL accessed"))
    report = execute_plan(plan, source, output, dry_run=True)
    assert report.status == "DRY_RUN"
    assert report.executed_operations == 0
    assert report.verified is True
    assert not output.exists()
    assert report.input_sha256_before == report.input_sha256_after


def test_output_guards_precede_dll_access(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    source = tmp_path / "source.xdw"
    source.write_bytes(b"xdw")
    monkeypatch.setattr(executor, "open_xdw", lambda *args, **kwargs: pytest.fail("DLL accessed"))
    with pytest.raises(ValueError):
        execute_plan(plan, source, source)
    output = tmp_path / "output.xdw"
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        execute_plan(plan, source, output)


def test_failure_removes_only_generated_temporary_copy(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    source = tmp_path / "source.xdw"
    source.write_bytes(b"original")
    output = tmp_path / "output.xdw"
    monkeypatch.setattr(executor, "open_xdw", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        execute_plan(plan, source, output)
    assert source.read_bytes() == b"original"
    assert not output.exists()
    assert not list(tmp_path.glob(".docuworks-integrations-*"))


def test_cli_dry_run_prints_plan_and_disallows_report(monkeypatch, tmp_path, capsys):
    image = tmp_path / "page.png"
    image.write_bytes(b"image")
    regions = tmp_path / "regions.json"
    regions.write_text(json.dumps([{"text": "A", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}]), encoding="utf-8")
    source = tmp_path / "source.xdw"
    source.write_bytes(b"xdw")
    output = tmp_path / "output.xdw"
    monkeypatch.setattr(cli, "read_image_size", lambda path: (100, 100))
    assert cli.main(["annotate-image", "--image", str(image), "--regions-json", str(regions), "--page-width-mm", "210", "--page-height-mm", "297", "--input-xdw", str(source), "--output-xdw", str(output), "--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["status"] == "DRY_RUN"
    assert payload["plan"]["operations"][0]["kind"] == "rectangle"
    with pytest.raises(ValueError, match="--report"):
        cli.main(["annotate-image", "--image", str(image), "--regions-json", str(regions), "--page-width-mm", "210", "--page-height-mm", "297", "--input-xdw", str(source), "--output-xdw", str(output), "--dry-run", "--report", str(tmp_path / "report.json")])
