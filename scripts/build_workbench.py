"""Build a separate local Portable from a hash-pinned v0.7.0 vendor archive."""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

BASELINE_SHA = "976b4c692d475a53151c37805cd73623eedb51a2f40cdc0828fa62a892cc7a1a"


def application_version(source):
    tree = ast.parse((source/"packages/dw-workbench/dw_workbench/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Application version missing")


def source_provenance(source):
    """Describe the checkout used for the wheel; copied source needs no Git."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source,
            capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=source,
            capture_output=True, text=True, check=True).stdout.strip()
        return {"source_commit": commit, "source_dirty": bool(status)}
    except (OSError, subprocess.CalledProcessError):
        return {"source_commit": None, "source_dirty": None}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def copy_development_source(source, output):
    target = output/"source"
    shutil.copytree(source/"packages/dw-workbench", target/"packages/dw-workbench", dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__", ".pytest_cache", "pytest-cache-files-*"))
    (target/"docs").mkdir(parents=True, exist_ok=True)
    for path in (source/"docs").glob("WORKBENCH*.md"):
        shutil.copy2(path, target/"docs"/path.name)
    shutil.copy2(source/"README.md", target/"README.md")
    (target/"scripts").mkdir(parents=True, exist_ok=True)
    for path in (source/"scripts").glob("*workbench*.py"):
        shutil.copy2(path, target/"scripts"/path.name)
    (target/"portable/workbench").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source/"portable/workbench/launch.bat", target/"portable/workbench/launch.bat")


def build(source, baseline, output):
    if output.exists():
        raise FileExistsError(output)
    if sha(baseline) != BASELINE_SHA:
        raise ValueError("Pinned baseline hash does not match")
    output.mkdir(parents=True)
    vendor = []
    with zipfile.ZipFile(baseline) as archive:
        members = [n for n in archive.namelist() if n.split("/")[0] in ("runtime", "models", "reference", "wheelhouse") or n in ("LICENSE", "LICENSE_NOTICE.md", "THIRD_PARTY_NOTICES.md")]
        for i, name in enumerate(members):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
                raise ValueError("Unsafe archive member")
            target = output/name
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(name) as src, target.open("xb") as dst:
                while data := src.read(1024*1024):
                    dst.write(data)
                    digest.update(data)
            # ZipExtFile verifies CRC; independent digest verifies the extracted bytes.
            if sha(target) != digest.hexdigest():
                raise ValueError("Extracted vendor file mismatch: "+name)
            vendor.append({"path": name, "sha256": digest.hexdigest(), "bytes": target.stat().st_size})
            if i % 1500 == 0:
                print(f"vendor extraction {i}/{len(members)}", flush=True)
    return finish_build(source, output, vendor)


def build_from_portable(source, baseline, output):
    """Copy only hash-pinned vendor files, never old application/project state."""
    if output.exists():
        raise FileExistsError(output)
    provenance = json.loads((baseline/"BUILD.json").read_text(encoding="utf-8"))
    if provenance["baseline_sha256"] != BASELINE_SHA:
        raise ValueError("Pinned Portable provenance does not match")
    vendor = json.loads((baseline/"licenses/vendor-manifest.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    for i, item in enumerate(vendor):
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or ":" in item["path"] or "\\" in item["path"]:
            raise ValueError("Unsafe vendor member")
        source_file, target = baseline/item["path"], output/item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
        if sha(target) != item["sha256"]:
            raise ValueError("Pinned vendor mismatch: "+item["path"])
        if i % 1500 == 0:
            print(f"vendor copy {i}/{len(vendor)}", flush=True)
    return finish_build(source, output, vendor)


def finish_build(source, output, vendor):
    version = application_version(source)
    for folder in ("settings", "projects", "licenses"):
        (output/folder).mkdir(exist_ok=True)
    for name in ("LICENSE", "LICENSE_NOTICE.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(output/name, output/"licenses"/name)
    (output/"起動.bat").write_bytes((source/"portable/workbench/launch.bat").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    appsource = source/"packages/dw-workbench"
    wheel_dir = source/"workbench-dist"
    wheel_dir.mkdir(exist_ok=True)
    env = __import__("os").environ.copy()
    env.update({"TEMP": str(output/"settings"), "TMP": str(output/"settings"), "PYTHONDONTWRITEBYTECODE": "1"})
    subprocess.run([str(output/"runtime/python.exe"), "-I", "-B", "-X", "utf8", "-c",
        "from setuptools import setup;setup()", "bdist_wheel", "--dist-dir", str(wheel_dir)], cwd=appsource, env=env, check=True)
    wheel = wheel_dir/f"dw_workbench-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if ".data/" in name or ".." in PurePosixPath(name).parts or not name.startswith(("dw_workbench/", f"dw_workbench-{version}.dist-info/")):
                raise ValueError("Unexpected wheel member")
            target = output/"runtime/Lib/site-packages"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    shutil.copy2(wheel, output/"wheelhouse"/wheel.name)
    shutil.copy2(source/"docs/WORKBENCH_JA.md", output/"はじめに.md")
    copy_development_source(source, output)
    provenance = {"application": "DW-Workbench", "version": version, "status": "local-validation-candidate",
        "base_commit": "bb069cf3fb290df868da53fe947c9a7844f0e098", "baseline_sha256": BASELINE_SHA,
        "wheel_sha256": sha(wheel), "vendor_files": len(vendor), "vendor_bytes": sum(v["bytes"] for v in vendor),
        **source_provenance(source)}
    (output/"licenses/vendor-manifest.json").write_text(json.dumps(vendor, indent=2), encoding="utf-8")
    (output/"BUILD.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    baseline_options = parser.add_mutually_exclusive_group(required=True)
    baseline_options.add_argument("--baseline", type=Path)
    baseline_options.add_argument("--baseline-portable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    operation = build if args.baseline else build_from_portable
    operation(Path(__file__).resolve().parents[1], (args.baseline or args.baseline_portable).resolve(), args.output.resolve())
