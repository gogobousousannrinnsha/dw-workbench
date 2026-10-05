"""Download only the two official PP-OCRv6 medium models."""
from pathlib import Path
import argparse
import hashlib
import json
import tarfile
import requests
import os
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.model_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"):
        target = root / name
        archive = root / f"{name}_infer.tar"
        url = f"https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/{name}_infer.tar"
        if not target.exists():
            if not archive.exists():
                partial = archive.with_suffix(".part")
                if os.name == "nt":
                    # Use Windows certificate trust, also used by the host's corporate proxy.
                    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                    "-File", str(Path(__file__).with_name("download_file.ps1")),
                                    "-Uri", url, "-Destination", str(partial)], check=True)
                else:
                    with requests.get(url, stream=True, timeout=120) as response:
                        response.raise_for_status()
                        with partial.open("wb") as stream:
                            for chunk in response.iter_content(1024 * 1024):
                                stream.write(chunk)
                partial.rename(archive)
            with tarfile.open(archive) as tar:
                # Official tar has one top-level model directory. Do not permit links or traversal.
                members = tar.getmembers()
                top = {Path(m.name).parts[0] for m in members}
                if len(top) != 1:
                    raise ValueError("unexpected model archive structure")
                for member in members:
                    resolved = (root / member.name).resolve()
                    if not resolved.is_relative_to(root) or member.issym() or member.islnk():
                        raise ValueError("unsafe model archive member")
                tar.extractall(root, filter="data")
                extracted = root / next(iter(top))
                if extracted != target:
                    extracted.rename(target)
        if not (target / "inference.yml").is_file():
            raise ValueError(f"model missing inference.yml: {name}")
        entries.append({"name": name, "source": url, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                        "files": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(target.rglob("*")) if p.is_file()}})
        print(name, "ready", flush=True)
    (root / "model-manifest.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
