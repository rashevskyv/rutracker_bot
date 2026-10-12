"""The real Linux launchers must serialize their entire shared-state cycles."""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name == "nt" or not shutil.which("flock"), reason="Linux server launchers require flock")
def test_launchers_hold_one_lock_across_download_process_upload(tmp_path):
    root = Path(__file__).parent
    config = tmp_path / "config"
    config.mkdir()
    main = config / "run_checker.sh"
    custom = tmp_path / "run_custom_collector.sh"
    main.write_text((root / "config/run_checker.sh.example").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    custom.write_text((root / "run_custom_collector.sh").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    binary = tmp_path / "bin"
    binary.mkdir()
    fake = binary / "python"
    fake.write_text('''#!/bin/bash
if flock -n "$PWD/data/.runner.lock" true; then
    echo "Runner did not hold the shared state lock" >&2
    exit 1
fi
echo "$TASK_LABEL start" >> "$RUNNER_TRACE"
sleep 0.1
echo "$TASK_LABEL end" >> "$RUNNER_TRACE"
''', encoding="utf-8")
    fake.chmod(0o755)
    shutil.copyfile(fake, binary / "python3")
    (binary / "python3").chmod(0o755)
    trace = tmp_path / "trace"
    env = dict(os.environ, PATH=f"{binary}:{os.environ['PATH']}", GITHUB_TOKEN="test-placeholder", RUNNER_TRACE=str(trace))
    first = subprocess.Popen(["bash", str(main), "hb-digest"], cwd=tmp_path,
                             env=dict(env, TASK_LABEL="digest"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    second = None
    try:
        deadline = time.monotonic() + 10
        while not trace.exists() and first.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert trace.exists(), "Main runner never reached the locked processing cycle"
        second = subprocess.Popen(["bash", str(custom)], cwd=tmp_path,
                                  env=dict(env, TASK_LABEL="custom"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for process in (first, second):
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, (stdout + stderr).decode()
        assert trace.read_text().splitlines() == ["digest start", "digest end"] * 3 + ["custom start", "custom end"]
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
