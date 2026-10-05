from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """Provide a Windows-safe temporary path without pytest's 0700 ACL.

    Some restricted Windows hosts cannot re-open a directory created with the
    special 0700 ACL used by recent Python/pytest combinations.  The root can
    be pinned by the compatibility runner; normal local runs use the OS temp
    directory.  Every test receives a unique child and cleanup is limited to
    that exact child.
    """

    configured = os.environ.get("DOCUWORKS_INTEGRATIONS_TEST_TMP")
    root = Path(configured) if configured else Path(tempfile.gettempdir()) / "docuworks-integrations-tests"
    root.mkdir(parents=True, exist_ok=True)
    leaf = root / f"{request.node.name[:40]}-{uuid.uuid4().hex}"
    leaf.mkdir()
    try:
        yield leaf
    finally:
        shutil.rmtree(leaf, ignore_errors=True)
