from __future__ import annotations

from types import SimpleNamespace

import pytest

import docuworks_integrations.opencv as adapter


class _Image:
    shape = (240, 320, 3)
    ndim = 3


def test_read_image_size_hides_array(monkeypatch, tmp_path):
    fake = SimpleNamespace(IMREAD_UNCHANGED=-1, imread=lambda path, mode: _Image())
    monkeypatch.setattr(adapter, "_cv2", lambda: fake)
    assert adapter.read_image_size(tmp_path / "page.png") == (320, 240)


def test_bounding_rects_return_public_pixel_rect(monkeypatch):
    fake = SimpleNamespace(boundingRect=lambda contour: contour)
    monkeypatch.setattr(adapter, "_cv2", lambda: fake)
    assert adapter.bounding_rects([(1, 2, 3, 4)])[0].right == 4


def test_decode_failure_is_clear(monkeypatch, tmp_path):
    fake = SimpleNamespace(IMREAD_UNCHANGED=-1, imread=lambda path, mode: None)
    monkeypatch.setattr(adapter, "_cv2", lambda: fake)
    with pytest.raises(ValueError, match="could not decode"):
        adapter.read_image_size(tmp_path / "bad.png")
