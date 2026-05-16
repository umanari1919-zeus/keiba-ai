"""runtime-check の修復ヒント表示テスト。"""

from __future__ import annotations

import socket


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

    monkeypatch.setattr(runtime_check.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(runtime_check.pathlib.Path, "home", lambda: tmp_path)

    results = runtime_check.check_external()
    browsers = next(result for result in results if result.name == "external:playwright-browsers")

    assert browsers.status == "WARN"
    assert "python3 -m playwright install chromium" in browsers.detail
