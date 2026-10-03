"""3-axis reputation engine — fame, moral, brutality."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

IMPACTS = {
    "torture": {"standard": {"fame": 0, "moral": -2, "brutality": 2},
                "enhanced": {"fame": -2, "moral": -5, "brutality": 5},
                "brutal": {"fame": -8, "moral": -12, "brutality": 15}},
    "execute": {"standard": {"fame": -5, "moral": -8, "brutality": 10},
                "enhanced": {"fame": -10, "moral": -15, "brutality": 20},
                "brutal": {"fame": -15, "moral": -20, "brutality": 30}},
    "mercy": {"standard": {"fame": 5, "moral": 5, "brutality": -3}},
    "victory": {"standard": {"fame": 10, "moral": 3, "brutality": 1}},
    "defeat": {"standard": {"fame": -5, "moral": -3, "brutality": 0}},
    "diplomacy": {"standard": {"fame": 3, "moral": 2, "brutality": -1}},
    "betrayal": {"standard": {"fame": -10, "moral": -8, "brutality": 5}},
    # Novel adaptation — "Ruthless but Fair" (novel bab 51):
    # hapus khianat = brutal tapi adil; lepaskan neutral = mercy bermoral tinggi
    "execute_leader": {"standard": {"fame": -3, "moral": -10, "brutality": 12},
                       "justified": {"fame": 3, "moral": -2, "brutality": 5},
                       "unjust": {"fame": -12, "moral": -18, "brutality": 20}},
    "spare_leader": {"standard": {"fame": 6, "moral": 6, "brutality": -5},
                     "risky": {"fame": 2, "moral": 3, "brutality": -2}},
    "family_spared": {"standard": {"fame": 8, "moral": 8, "brutality": -6}},
    "family_executed": {"standard": {"fame": -6, "moral": -12, "brutality": 15}},
}

#: The outer band of each map is open: fame is never clamped, so a campaign that keeps winning
#: walks past 100, and `_find` answered "Unknown" for every point beyond the last tuple. The same
#: hole sat below -999 on fame and above 999 on brutality.
_TITLE_MAP = {
    (75, float("inf")): "Legendary Hero", (25, 75): "Respected", (-24, 25): "Neutral",
    (-74, -24): "Feared", (float("-inf"), -74): "Galactic Terror"
}
_ALIGN_MAP = {
    (75, float("inf")): "Paragon", (40, 75): "Honorable", (10, 40): "Renegade",
    (float("-inf"), 10): "Monster"
}
_BRUTAL_MAP = {
    (80, float("inf")): "Unforgivable", (50, 80): "Butcher", (20, 50): "Bloodstained",
    (1, 20): "Hard Choices", (float("-inf"), 1): "Clean"
}

@dataclass
class Reputation:
    fame: int = 0
    moral: int = 50
    brutality: int = 0
    hidden_brutality: int = 0
    self_redemption: int = 0
    dark_deeds: List[Dict] = field(default_factory=list)

    def apply(self, action_type: str, severity: str = "standard",
              witnesses: Optional[List[str]] = None, secrecy: str = "public",
              context: str = "") -> Dict:
        witnesses = witnesses or []
        # `IMPACTS.get(action_type, {}).get(severity, {0, 0, 0})` answered an unknown action, and an
        # unknown severity for a known action, with a no-op that then reported the unchanged state
        # as though the deed had been recorded. Both are refused by name now: severities are
        # per-action (`mercy` has only `standard`), so a typo is the ordinary way to arrive here.
        effects = IMPACTS.get(action_type)
        if effects is None:
            raise ValueError(f"unknown reputation action {action_type!r}; known: {sorted(IMPACTS)}")
        impact = effects.get(severity)
        if impact is None:
            raise ValueError(
                f"unknown severity {severity!r} for action {action_type!r};"
                f" known severities: {sorted(effects)}")
        if secrecy == "public":
            self.fame += impact.get("fame", 0)
            self.moral += impact.get("moral", 0)
            self.brutality += impact.get("brutality", 0)
        else:
            self.hidden_brutality += impact.get("brutality", 0)
        self.moral = max(0, min(100, self.moral))
        self.brutality = max(0, self.brutality)
        if action_type in ("torture", "execute", "betrayal"):
            self.dark_deeds.append({"action": action_type, "severity": severity, "context": context})
        return {"public": self._public(), "private": self._private()}

    def _public(self) -> Dict:
        def _find(val, mapping):
            for (lo, hi), label in mapping.items():
                if lo <= val < hi:
                    return label
            return "Unknown"
        return {
            "fame": self.fame,
            "title": _find(self.fame, _TITLE_MAP),
            "moral": self.moral,
            "alignment": _find(self.moral, _ALIGN_MAP),
            "brutality": self.brutality,
            "brutality_label": _find(self.brutality, _BRUTAL_MAP),
        }

    def _private(self) -> Dict:
        return {
            "hidden_brutality": self.hidden_brutality,
            "redemption_pct": min(100, int(self.self_redemption / max(1, self.hidden_brutality) * 100)),
            "dark_deeds": len(self.dark_deeds),
        }
