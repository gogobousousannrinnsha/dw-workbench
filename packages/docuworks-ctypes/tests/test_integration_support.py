import hashlib
import json
import zipfile

import pytest

from tests.integration.support import EvidenceWriter, json_value, safe_case_name, sha256_file
from docuworks_ctypes.evidence import verify_evidence_archive


def test_sha256_file(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == (
        "BA7816BF8F01CFEA414140DE5DAE2223"
        "B00361A396177A9CB410FF61F20015AD"
    )


def test_safe_case_name():
    assert safe_case_name("test[a/b:日本語]") == "test_a_b"


def test_json_value_preserves_binary_evidence():
    assert json_value(b"\x00\xff") == {"hex": "00ff", "length": 2}


def test_evidence_writer_copies_and_records(tmp_path):
    source = tmp_path / "fixture.xdw"
    source.write_bytes(b"fixture")
    writer = EvidenceWriter(tmp_path / "artifacts")
    copied = writer.copy_fixture(source, "case[1]")
    assert copied == tmp_path / "artifacts" / "xdw" / "case_1.xdw"
    assert copied.read_bytes() == b"fixture"
    assert '"stage": "fixture_copy"' in writer.evidence_path.read_text("utf-8")


def _evidence_zip(tmp_path, payload: bytes, expected_hash: str):
    archive = tmp_path / "evidence.zip"
    manifest = {
        "missing_required_files": [],
        "files": [
            {
                "path": "xdw/sample.xdw",
                "size": len(payload),
                "sha256": expected_hash,
            }
        ],
    }
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("xdw/sample.xdw", payload)
        package.writestr("artifact-manifest.json", json.dumps(manifest))
    return archive


def test_evidence_pack_verifier_checks_manifest_hashes(tmp_path):
    payload = b"xdw-evidence"
    archive = _evidence_zip(tmp_path, payload, hashlib.sha256(payload).hexdigest())
    summary = verify_evidence_archive(archive)
    assert summary["verified_files"] == 1
    assert summary["missing_required_files"] == []


def test_evidence_pack_verifier_rejects_hash_mismatch(tmp_path):
    archive = _evidence_zip(tmp_path, b"tampered", "0" * 64)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_evidence_archive(archive)
