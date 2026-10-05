"""Refresh only this candidate's own application after tests; keep vendor bytes intact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import importlib.util

_builder_spec = importlib.util.spec_from_file_location("workbench_builder", Path(__file__).with_name("build_workbench.py"))
_builder = importlib.util.module_from_spec(_builder_spec)
_builder_spec.loader.exec_module(_builder)
copy_development_source = _builder.copy_development_source
application_version = _builder.application_version
source_provenance = _builder.source_provenance


def update(portable):
    source = Path(__file__).resolve().parents[1]
    app = source/"packages/dw-workbench"
    dist = source/"workbench-dist"
    version = application_version(source)
    old_version = json.loads((portable/"BUILD.json").read_text(encoding="utf-8"))["version"]
    if old_version != version:
        raise ValueError("Update is only for a candidate of the same version; build a separate Portable for a new version")
    env = os.environ.copy()
    env.update({"TEMP": str(portable/"settings/temp"), "TMP": str(portable/"settings/temp"), "PYTHONDONTWRITEBYTECODE": "1"})
    Path(env["TEMP"]).mkdir(parents=True, exist_ok=True)
    subprocess.run([str(portable/"runtime/python.exe"), "-I", "-B", "-X", "utf8", "-c", "from setuptools import setup;setup()",
        "bdist_wheel", "--dist-dir", str(dist)], cwd=app, env=env, check=True, stdout=subprocess.DEVNULL)
    wheel = dist/f"dw_workbench-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if not name.startswith(("dw_workbench/", f"dw_workbench-{version}.dist-info/")) or ".." in Path(name).parts:
                raise ValueError(name)
            target = portable/"runtime/Lib/site-packages"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    shutil.copy2(wheel, portable/"wheelhouse"/wheel.name)
    copy_development_source(source, portable)
    shutil.copy2(source/"docs/WORKBENCH_JA.md", portable/"はじめに.md")
    report = json.loads((portable/"BUILD.json").read_text(encoding="utf-8"))
    report["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    report.update(source_provenance(source))
    (portable/"BUILD.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["wheel_sha256"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("portable", type=Path)
    update(parser.parse_args().portable.resolve())
