from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import backend.launcher as launcher


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _FakeProcess:
    pid: int
    exit_code: int | None = None
    signals: list[int] = field(default_factory=list)

    def poll(self) -> int | None:
        return self.exit_code

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.exit_code is None:
            self.exit_code = 0
        return self.exit_code


def test_build_service_commands_starts_api_and_persistent_workers() -> None:
    commands = launcher.build_service_commands(
        python_executable="/venv/bin/python",
        host="127.0.0.1",
        port=8123,
        reload_enabled=True,
    )

    assert commands == (
        launcher.ServiceCommand(
            name="api",
            argv=(
                "/venv/bin/python",
                "-m",
                "uvicorn",
                "backend.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8123",
                "--reload",
            ),
        ),
        launcher.ServiceCommand(
            name="indexing-worker",
            argv=(
                "/venv/bin/python",
                "-m",
                "backend.workers.indexing",
            ),
        ),
        launcher.ServiceCommand(
            name="rag-evaluation-worker",
            argv=(
                "/venv/bin/python",
                "-m",
                "backend.workers.evaluation",
            ),
        ),
    )


def test_supervisor_stops_sibling_when_one_service_exits(monkeypatch) -> None:
    api = _FakeProcess(pid=101, exit_code=7)
    worker = _FakeProcess(pid=102)
    spawned = iter((api, worker))

    def process_factory(*_args, **_kwargs):
        return next(spawned)

    def send_signal(process: _FakeProcess, signum: int) -> None:
        process.signals.append(signum)
        process.exit_code = 0

    monkeypatch.setattr(launcher, "_send_process_signal", send_signal)

    exit_code = launcher.supervise_services(
        (
            launcher.ServiceCommand(name="api", argv=("api",)),
            launcher.ServiceCommand(name="indexing-worker", argv=("worker",)),
        ),
        process_factory=process_factory,
        poll_seconds=0,
        shutdown_timeout_seconds=0,
        install_signal_handlers=False,
    )

    assert exit_code == 7
    assert api.signals == []
    assert worker.signals == [signal.SIGTERM]


@pytest.mark.skipif(os.name == "nt", reason="Bash wrapper requires POSIX")
def test_repository_start_script_exposes_the_unified_launcher() -> None:
    completed = subprocess.run(
        [ROOT / "scripts" / "start.sh", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert "同时启动问溪 API、索引 worker 与 RAG 评估 worker" in completed.stdout


def test_python_module_exposes_the_unified_launcher() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "backend.launcher", "--help"],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
        capture_output=True,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert "同时启动问溪 API、索引 worker 与 RAG 评估 worker" in completed.stdout
