"""runtime-check の修復ヒント表示テスト。"""

from __future__ import annotations

import socket
import sys
import types


def test_database_port_warning_includes_startup_hint(monkeypatch):
    import pipeline_v2.runtime_check as runtime_check

    def raise_refused(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", raise_refused)

    results = runtime_check.check_database()
    postgres = next(result for result in results if result.name == "external:postgres-port")

    assert postgres.status == "WARN"
    assert "python3 tools/local_postgres.py start" in postgres.detail
    assert "run_all.py --runtime-check" in postgres.detail


def test_playwright_browser_warning_includes_install_hint(tmp_path, monkeypatch):
    import pipeline_v2.runtime_check as runtime_check

    browser_root = tmp_path / ".cache" / "ms-playwright"
    monkeypatch.setattr(runtime_check.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(runtime_check, "_playwright_browser_root", lambda: browser_root)

    results = runtime_check.check_external()
    browsers = next(result for result in results if result.name == "external:playwright-browsers")

    assert browsers.status == "WARN"
    assert "python3 -m playwright install chromium" in browsers.detail


def test_playwright_launch_warning_includes_dependency_hint(tmp_path, monkeypatch):
    import pipeline_v2.runtime_check as runtime_check

    browser_root = tmp_path / ".cache" / "ms-playwright"
    (browser_root / "chromium-1").mkdir(parents=True)

    class FakeChromium:
        def launch(self, **_kwargs):
            raise RuntimeError("error while loading shared libraries: libnspr4.so")

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(runtime_check.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(sync_playwright=lambda: FakeSyncPlaywright()),
    )
    monkeypatch.setattr(runtime_check, "_playwright_browser_root", lambda: browser_root)

    results = runtime_check.check_external()
    browsers = next(result for result in results if result.name == "external:playwright-browsers")

    assert browsers.status == "WARN"
    assert "libnspr4.so" in browsers.detail
    assert "python3 -m playwright install-deps chromium" in browsers.detail
