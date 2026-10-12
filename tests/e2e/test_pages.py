"""The pages in a real browser: the app started the way `make dev` starts it (offline, seeded), two
sample cases run through the API, then Chromium checks what a judge would see. Run by `make e2e`
only; `make check` deselects the e2e marker, so it never needs a browser."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
CASES = ["001", "002"]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """The app on a free port, offline, with CASES already run; yields its base URL."""
    tmp = tmp_path_factory.mktemp("e2e-server")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {
        **os.environ,
        "ANTHROPIC_API_KEY": "",
        "MODE": "local",
        "EFFECTS": "simulate",
        "DATA_PATH": str(tmp / "store.json"),
    }
    log = open(tmp / "server.log", "w")  # closed in the finally below
    cmd = [sys.executable, "-m", "uvicorn", "starter.main:app", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(base, proc, tmp / "server.log")
        token = httpx2.post(f"{base}/api/login", json={"password": "admin"}).json()["token"]
        for case in CASES:
            body = (ROOT / "cases" / "sample" / case / "index.md").read_text()
            run = httpx2.post(
                f"{base}/api/runs",
                json={"id": case, "body": body},
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            run.raise_for_status()
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()


def _wait_healthy(base: str, proc: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            if httpx2.get(f"{base}/health", timeout=1).status_code == 200:
                return
        except httpx2.TransportError:
            pass
        time.sleep(0.2)
    pytest.fail(f"the app did not come up on {base}:\n{log.read_text()[-2000:]}")


@pytest.fixture
def errors(page: Page) -> list[str]:
    """Console errors and uncaught exceptions on the page. Web fonts are stubbed so the test is
    offline and a missing network is not a console error."""
    found: list[str] = []
    page.on("console", lambda m: found.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: found.append(str(e)))
    stub = {"status": 200, "content_type": "text/css", "body": ""}
    page.route("https://fonts.googleapis.com/**", lambda route: route.fulfill(**stub))
    page.route("https://fonts.gstatic.com/**", lambda route: route.fulfill(**stub))
    return found


@pytest.fixture
def shots(tmp_path) -> Path:
    """Where screenshots go: $E2E_OUT (make e2e prints it), else this test's tmp dir."""
    out = Path(os.environ.get("E2E_OUT") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def test_runs_page_shows_every_run(page: Page, server, errors, shots):
    page.goto(server + "/")
    expect(page.get_by_role("heading", name="Runs", exact=True)).to_be_visible()
    for case in CASES:
        card = page.locator("[data-run]", has_text=f"Case {case}")
        expect(card).to_contain_text("DONE")
        expect(card).to_contain_text("acknowledged the case")
        expect(card).to_contain_text("send_message")
        expect(card).to_contain_text("SIMULATED")
    page.screenshot(path=shots / "runs.png", full_page=True)
    assert errors == []


def test_one_case_filtered_shows_only_its_run(page: Page, server, errors, shots):
    page.goto(server + "/")
    page.get_by_label("Filter runs").fill("Case 001")
    expect(page.locator("[data-run]", has_text="Case 001")).to_be_visible()
    expect(page.locator("[data-run]", has_text="Case 002")).to_be_hidden()
    expect(page.locator("[data-run]", has_text="Case 001")).to_contain_text("DONE")
    page.screenshot(path=shots / "case-001.png", full_page=True)
    assert errors == []
