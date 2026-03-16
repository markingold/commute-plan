from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
PORT = 18099
BASE_URL = f"http://{HOST}:{PORT}"


def _http_json(path: str, request_id: str | None = None):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    if request_id:
        req.add_header("X-Request-Id", request_id)
    with urllib.request.urlopen(req, timeout=2) as resp:
        body = resp.read().decode("utf-8")
        payload = json.loads(body)
        headers = {k.lower(): v for (k, v) in resp.headers.items()}
        return resp.status, headers, payload


@pytest.fixture(scope="module")
def api_server():
    env = os.environ.copy()
    env.setdefault("LOG_FORMAT", "json")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.src.comfort_api_server",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            status, _, _ = _http_json("/health")
            if status == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        output = ""
        if proc.stdout is not None:
            try:
                output = proc.stdout.read()
            except Exception:
                output = ""
        proc.terminate()
        raise RuntimeError(f"comfort_api_server did not start in time. Output:\n{output}")

    yield proc

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGKILL)


def test_health_contract(api_server):
    status, headers, payload = _http_json("/health", request_id="test-health-req")

    assert status == 200
    assert headers.get("x-request-id") == "test-health-req"

    assert payload.get("ok") is True
    assert payload.get("service") == "comfort_api"
    assert isinstance(payload.get("version"), str)
    assert isinstance(payload.get("time"), str)
    assert isinstance(payload.get("uptime_s"), (float, int))


def test_version_contract(api_server):
    status, headers, payload = _http_json("/version")

    assert status == 200
    assert "x-request-id" in headers
    assert payload.get("ok") is True
    assert isinstance(payload.get("version"), str)
