"""Capability failures must leave the manual workflow discoverable."""
import subprocess
from types import SimpleNamespace
import pytest
from dw_workbench import workers


def test_capability_sdk_probe_is_isolated_and_masked_gpu_explains_manual_mode(workdir, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "nvidia-smi":
            return SimpleNamespace(returncode=0, stdout="NVIDIA GeForce TEST\n", stderr="")
        return SimpleNamespace(returncode=0, stdout='{"docuworks":"10.1.1"}', stderr="")
    monkeypatch.setattr(workers.subprocess, "run", run)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    caps = workers.capabilities(workdir)
    assert caps["docuworks"] == "10.1.1"
    assert "手入力" in caps["gpu"] and "無効" in caps["gpu"]
    assert calls[0][0][0] == workers.sys.executable and calls[0][1]["timeout"] > 0
    assert not caps["models"]


@pytest.mark.parametrize("failure", ["timeout", "exit", "invalid_json"])
def test_failed_capability_probe_returns_actionable_manual_state(workdir, monkeypatch, failure):
    def run(args, **kwargs):
        if args[0] == "nvidia-smi":
            raise FileNotFoundError("No GPU tools")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        if failure == "exit":
            return SimpleNamespace(returncode=1, stdout="", stderr="SDK unavailable")
        return SimpleNamespace(returncode=0, stdout="Unexpected SDK output", stderr="")
    monkeypatch.setattr(workers.subprocess, "run", run)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    caps = workers.capabilities(workdir)
    assert caps["docuworks"].startswith("利用不可")
    assert "手入力" in caps["gpu"] and not caps["models"]
