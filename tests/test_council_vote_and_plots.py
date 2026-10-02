"""Votes, promotions and the plot machinery: the last five council functions.

Two of these carry a defect worth stating in a test rather than only in prose. `promote_seat` computes a
promoted seat and writes nothing, so a caller that trusts the name has announced a promotion that never
happened; the CLI persists it and says so. And `calculate_vote` counts only seats at tier three or above,
so a vote held by junior ministers does not count at all.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import council  # noqa: E402


class TestTheVote:
    def test_a_vote_with_no_active_seats_says_so(self):
        out = council.calculate_vote([], [{"position": "aye"}])
        assert out["passed"] is False
        assert "No active seats" in out["reason"], out

    def test_the_tally_counts_the_positions(self):
        seats = [{"active": True, "tier": 1}, {"active": True, "tier": 2}]
        out = council.calculate_vote(seats, [{"position": "aye"}, {"position": "nay"},
                                            {"position": "abstain"}])
        assert out["tally"] == {"aye": 1, "nay": 1, "abstain": 1}, out

    def test_a_seat_below_tier_three_is_not_counted(self):
        """The rule as written: only tier three and above are active for a vote."""
        seats = [{"active": True, "tier": 4}, {"active": True, "tier": 5}]
        out = council.calculate_vote(seats, [{"position": "aye"}])
        assert out["reason"] == "No active seats", out


class TestThePromotion:
    def test_promote_seat_computes_and_does_not_write(self):
        """The assertion is on the contract: this function returns a new seat and touches no database."""
        seat = {"id": 1, "title": "Commander", "holder": "old", "tier": 1, "active": True}
        promoted = council.promote_seat(seat, "new", {"tier": 0})
        assert promoted["holder"] == "new" and promoted["tier"] == 0
        assert seat["holder"] == "old", "the input seat was mutated as well as copied"


class TestThePlots:
    def test_an_unknown_plot_type_is_refused_by_name(self):
        out = council.generate_plot("no such plot", {}, [])
        assert "Unknown plot type" in out.get("error", ""), out

    def test_running_past_the_last_phase_reports_completion(self):
        out = council.execute_phase({"phases": [], "difficulty": 5}, 0)
        assert out.get("complete") is True, out

    def test_exposure_risk_zero_never_exposes(self):
        out = council.check_exposure({"exposure_risk": 0})
        assert out["exposed"] is False, out
