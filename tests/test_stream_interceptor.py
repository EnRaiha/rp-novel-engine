"""Tests for core/stream_interceptor.py — narrative tag templating."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio
from core.stream_interceptor import StreamInterceptor
import pytest

CACHE = {
    "[ENV: HEAVEN_POOL]": "The pool glows.",
    "[HIT: RAILGUN_KINETIC]": "THE WET CRUNCH",
    "[SENSE: PILEDRIVER]": "Gravity does the work.",
}


class TestExpandText:
    def test_known_tag_swapped_inline(self):
        si = StreamInterceptor(cache=CACHE)
        out = si.expand_text("She fired. [HIT: RAILGUN_KINETIC] The squad advanced.")
        assert out == "She fired. THE WET CRUNCH The squad advanced."

    def test_unknown_tag_passthrough(self):
        si = StreamInterceptor(cache=CACHE)
        out = si.expand_text("Something [UNKNOWN: TAG] remains.")
        assert out == "Something [UNKNOWN: TAG] remains."

    def test_multiple_tags_one_line(self):
        si = StreamInterceptor(cache=CACHE)
        out = si.expand_text("[ENV: HEAVEN_POOL] then [SENSE: PILEDRIVER].")
        assert out == "The pool glows. then Gravity does the work.."

    def test_no_tag_untouched(self):
        si = StreamInterceptor(cache=CACHE)
        text = "Plain prose with no tags at all."
        assert si.expand_text(text) == text

    def test_cache_injection_skips_db(self):
        si = StreamInterceptor(cache=CACHE)
        assert si.cache_loaded is True  # no DB call in unit tests


class TestProcessStream:
    def test_stream_expansion(self):
        si = StreamInterceptor(cache=CACHE)

        async def gen():
            for t in ["Look. ", "[ENV: HEAVEN_POOL]\n", "Done."]:
                yield t

        async def run():
            out = ""
            async for chunk in si.process_stream(gen()):
                out += chunk
            return out

        out = asyncio.run(run())
        assert "Look. The pool glows." in out
        assert "Done." in out
        assert "[ENV:" not in out

    def test_stream_unknown_tag_passes(self):
        si = StreamInterceptor(cache=CACHE)

        async def gen():
            yield "[UNKNOWN: TAG]\n"

        async def run():
            out = ""
            async for chunk in si.process_stream(gen()):
                out += chunk
            return out

        assert asyncio.run(run()) == "[UNKNOWN: TAG]\n"
