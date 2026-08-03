"""Tests for core/stream_interceptor.py — narrative tag templating."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio
from core.stream_interceptor import StreamInterceptor
import pytest

def entry(text):
    return {"expanded_text": text, "readable_hint": None, "required_context": []}


CACHE = {
    "[ENV: HEAVEN_POOL]": entry("The pool glows."),
    "[HIT: RAILGUN_KINETIC]": entry("THE WET CRUNCH"),
    "[SENSE: PILEDRIVER]": entry("Gravity does the work."),
}

CACHE_INTERP = {
    "[HIT: RAILGUN_KINETIC]": entry("The rod fired by {attacker_name} hit {target_name} whose {target_armor_type} armor was paper."),
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


class TestInterpolation:
    def test_placeholders_filled_with_context(self):
        si = StreamInterceptor(cache=CACHE_INTERP, context_state={
            "attacker_name": "Legion Vanguard", "target_name": "Balor Ironhand",
            "target_armor_type": "heavy composite"})
        out = si.expand_text("[HIT: RAILGUN_KINETIC]")
        assert "Legion Vanguard" in out and "Balor Ironhand" in out
        assert "heavy composite" in out and "{attacker_name}" not in out

    def test_raw_fallback_when_context_missing(self):
        si = StreamInterceptor(cache=CACHE_INTERP)
        out = si.expand_text("[HIT: RAILGUN_KINETIC]")
        assert "{attacker_name}" in out  # raw template survives

    def test_partial_context_leaves_missing_keys(self):
        si = StreamInterceptor(cache=CACHE_INTERP, context_state={"attacker_name": "Shadow Wing"})
        out = si.expand_text("[HIT: RAILGUN_KINETIC]")
        assert "Shadow Wing" in out
        assert "{target_name}" in out


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


class TestSemanticTier:
    def test_no_vectors_fast_fail(self):
        # Injected cache without vectors -> returns None with NO DB/embed call
        si = StreamInterceptor(cache=CACHE)
        out = asyncio.run(si._semantic_swap("plasma bolt scorched the hull"))
        assert out is None

    def test_prefilter_gate(self):
        si = StreamInterceptor(cache=CACHE)
        assert si._is_hint_like("plasma bolt scorched the hull") is True
        assert si._is_hint_like("short") is False                # < 8 chars
        assert si._is_hint_like("The fleet assembled at the jump") is False  # prose opener
        assert si._is_hint_like("the crew celebrates tonight.") is False     # terminal punctuation
        long = "a " * 40
        assert si._is_hint_like(long) is False                   # > 60 chars

    def test_breaker_disables_after_two_failures(self, monkeypatch):
        import numpy as np
        si = StreamInterceptor(cache=CACHE)
        si._tag_vectors = [("[HIT: X]", np.ones(768) / np.sqrt(768))]

        async def boom(text, keep_alive="30m"):
            raise RuntimeError("ollama down")

        monkeypatch.setattr("core.memory._embed", boom)
        out = asyncio.run(si._semantic_swap("plasma bolt scorched the hull"))
        assert out is None
        out2 = asyncio.run(si._semantic_swap("plasma bolt scorched the hull"))
        assert out2 is None
        assert si._semantic_disabled is True
        assert si.stats["breaker_engaged"] is True

    def test_breaker_shortcircuits(self, monkeypatch):
        import numpy as np
        si = StreamInterceptor(cache=CACHE)
        si._tag_vectors = [("[HIT: X]", np.ones(768) / np.sqrt(768))]
        si._semantic_disabled = True  # already tripped

        async def boom(text, keep_alive="30m"):
            raise AssertionError("should not be called after breaker")

        monkeypatch.setattr("core.memory._embed", boom)
        out = asyncio.run(si._semantic_swap("plasma bolt scorched the hull"))
        assert out is None
