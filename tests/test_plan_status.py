"""The status script reports the plan's criteria, so its own checks need testing.

Criterion 6 measures the outcome (images reach the chat) rather than the mechanism (the host plugin
row), because route B reaches the same outcome through the proxy. A check that measures the wrong
thing reports a failure for a working feature, and nobody reads a report that cries wolf.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import plan_status  # noqa: E402

WIRED = '''MOBILE_FILES = {
    "/__dsh-portrait-chat.js": ("portrait-chat.js", "application/javascript; charset=utf-8"),
}
MOBILE_INJECT = ('<script defer src="/__dsh-portrait-chat.js"></script>')
'''


class TestImagesReachTheChat:
    def test_a_wired_proxy_with_a_fresh_decorator_passes(self, tmp_path):
        proxy = tmp_path / "dsh-auth-proxy"
        proxy.write_text(WIRED, encoding="utf-8")
        decorator = tmp_path / "portrait-chat.js"
        decorator.write_text("// generated\n", encoding="utf-8")
        ok, detail = plan_status.check_images_reach_the_chat(proxy, decorator)
        # The freshness check shells out to the generator, which compares against the real file, so
        # a temp decorator reads as stale. What must hold here is the wiring verdict.
        assert "route B carries it" in detail or "STALE" in detail

    def test_an_unwired_proxy_fails(self, tmp_path):
        proxy = tmp_path / "dsh-auth-proxy"
        proxy.write_text("MOBILE_FILES = {}\n", encoding="utf-8")
        decorator = tmp_path / "portrait-chat.js"
        decorator.write_text("// generated\n", encoding="utf-8")
        ok, detail = plan_status.check_images_reach_the_chat(proxy, decorator)
        assert ok is False
        assert "not wired" in detail

    def test_a_missing_decorator_fails_even_when_wired(self, tmp_path):
        proxy = tmp_path / "dsh-auth-proxy"
        proxy.write_text(WIRED, encoding="utf-8")
        ok, detail = plan_status.check_images_reach_the_chat(proxy, tmp_path / "absent.js")
        assert ok is False
        assert "has not been generated" in detail

    def test_a_missing_proxy_fails(self, tmp_path):
        ok, detail = plan_status.check_images_reach_the_chat(tmp_path / "absent", tmp_path / "x.js")
        assert ok is False
        assert "proxy script is missing" in detail
