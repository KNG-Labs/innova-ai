import subprocess
from pathlib import Path

import pytest

from scripts.verify_vercel import verify_deployment


def fake_vercel(monkeypatch, *, exposed_admin=False, unhealthy=False):
    calls = []

    def run(command, **kwargs):
        path = command[2]
        calls.append(path)
        status = 200
        body = b"asset"
        headers = ""
        if path == "/health":
            body = b'{"status":"unavailable"}' if unhealthy else b'{"status":"ok"}'
            status = 503 if unhealthy else 200
        elif path == "/":
            status = 307
            headers = "HTTP/2 307\r\nlocation: /static/widget-demo.html\r\n"
        elif path == "/static/widget-demo.html":
            body = b'<script src="demo.js"></script>'
        elif not path.startswith("/static/"):
            status = 200 if exposed_admin else 404
        Path(command[command.index("--output") + 1]).write_bytes(body)
        Path(command[command.index("--dump-header") + 1]).write_text(headers)
        return subprocess.CompletedProcess(command, 0, stdout=str(status), stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_release_checks_are_read_only(monkeypatch):
    calls = fake_vercel(monkeypatch)
    verify_deployment("https://innova-demo-example.vercel.app")
    assert "/message" not in calls
    assert "/health" in calls
    assert "/leads" in calls


@pytest.mark.parametrize("failure", ["exposed_admin", "unhealthy"])
def test_release_check_blocks_unsafe_or_unhealthy_deployment(monkeypatch, failure):
    fake_vercel(monkeypatch, **{failure: True})
    with pytest.raises(AssertionError, match="Unexpected HTTP status"):
        verify_deployment("https://innova-demo-example.vercel.app")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.vercel.app",
        "https://example.com",
        "https://user@example.vercel.app",
        "https://example.vercel.app/other",
    ],
)
def test_release_check_rejects_untrusted_origin(url):
    with pytest.raises(ValueError, match="deployment origin"):
        verify_deployment(url)
