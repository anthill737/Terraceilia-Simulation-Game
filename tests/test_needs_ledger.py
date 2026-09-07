"""Needs and the ledger. People have food, warmth, rest and health that fall every day; the valley's stores and its places
decay; nothing comes back without work; the dead lie unburied and the filth breeds sickness; the season and the weather
change how fast it all goes. Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, sys, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402
from engine import STORES, NEEDS, season_of, roll_weather, growing, starting_ledger  # noqa: E402


def valley(n: int = 6, day: int = 1, seed: int = 1) -> engine.World:
    w = engine.World(); rng = random.Random(seed); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; w.characters[nm] = engine.roll_character(nm, i + 1, rng, places); w.characters[nm]["location"] = places[i % 3]
    w.ledger = starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = day
    return w


class SeasonTests(unittest.TestCase):
    def test_the_year_turns(self) -> None:
        self.assertEqual(season_of(1), "autumn"); self.assertEqual(season_of(7), "early winter"); self.assertEqual(season_of(20), "deep winter"); self.assertEqual(season_of(30), "thaw")

    def test_weather_comes_from_the_season(self) -> None:
        autumn = {roll_weather(2, random.Random(i)) for i in range(200)}; winter = {roll_weather(20, random.Random(i)) for i in range(200)}
        self.assertNotIn("snow", autumn); self.assertIn("snow", winter); self.assertIn("rain", autumn)

    def test_winter_stops_growing(self) -> None:
        self.assertTrue(growing(2, "clear")); self.assertFalse(growing(20, "clear")); self.assertFalse(growing(2, "snow"))


class DawnTests(unittest.TestCase):
    def test_needs_fall_daily_and_the_report_says_the_season_and_weather(self) -> None:
        w = valley(); w.ledger["meals"] = 0; w.ledger["grain"] = 0; w.ledger["fish"] = 0; w.ledger["meat"] = 0
        before = {n: dict(c["needs"]) for n, c in w.characters.items()}
        rep = w.dawn(random.Random(2))
        for n, c in w.characters.items(): self.assertLess(c["needs"]["food"], before[n]["food"], f"{n} did not get hungrier with nothing to eat")
        self.assertEqual(rep["season"], "autumn"); self.assertIn(rep["weather"], [x for x, _ in engine.WEATHER["autumn"]])
        self.assertTrue(rep["lines"][0].startswith("Day 1, autumn, "), rep["lines"][0])
        self.assertIs(w.day_report, rep)

    def test_a_need_at_zero_takes_health_and_then_life(self) -> None:
        w = valley(n=1); c = w.characters["P0"]; c["hp"] = 2; c["needs"] = {"food": 0, "warmth": 0, "rest": 5}
        for k in ("meals", "grain", "fish", "meat", "wood"): w.ledger[k] = 0
        w.dawn(random.Random(3))
        self.assertLessEqual(c["hp"], 0); self.assertFalse(c["alive"]); self.assertIn(c["cause_of_death"], ("starved", "froze"))
        self.assertIn("P0", w.bodies, "the dead lie where they fell until buried")
        self.assertTrue(any("Dead by morning" in ln for ln in w.day_report["lines"]))

    def test_stores_and_places_decay_and_nothing_comes_back(self) -> None:
        w = valley(n=6); L = w.ledger; before = dict(L); ub = {p: dict(u) for p, u in w.upkeep.items()}
        for _ in range(4): w.day += 1; w.dawn(random.Random(w.day))
        for k in STORES: self.assertLessEqual(L[k], before[k], f"{k} grew without work")
        self.assertLess(L["meals"], before["meals"]); self.assertLess(L["wood"], before["wood"])
        self.assertTrue(any(w.upkeep[p]["roof"] < ub[p]["roof"] for p in w.map if w.roofed(p)), "no roof wore at all in four days")
        lived = [p for p in w.map if w.at(p)]
        self.assertTrue(all(w.upkeep[p]["filth"] > ub[p]["filth"] for p in lived), "filth did not build where people live")
        self.assertEqual(w.map, engine.World().map, "the map itself is untouched; wear lives beside it")

    def test_cold_burns_wood_faster_and_rain_rots_roofs(self) -> None:
        # the same valley, the same dice, one day of deep winter against one day of autumn
        def run(day: int, force: str) -> tuple[int, int]:
            w = valley(n=6, day=day, seed=7); old = engine.roll_weather
            engine.roll_weather = lambda d, r: force
            try: w.dawn(random.Random(11))
            finally: engine.roll_weather = old
            return w.ledger["wood"], sum(w.upkeep[p]["roof"] for p in w.map)
        wood_clear, roof_clear = run(2, "clear"); wood_cold, _ = run(20, "bitter cold"); _, roof_wet = run(2, "storm")
        self.assertLess(wood_cold, wood_clear, "cold must burn more wood"); self.assertLess(roof_wet, roof_clear, "rain must rot roofs faster")

    def test_filth_and_the_unburied_raise_sickness(self) -> None:
        def sick_after(filth: int, bodies: int, seed: int) -> int:
            w = valley(n=6, seed=seed); p = w.characters["P0"]["location"]
            w.upkeep[p]["filth"] = filth
            for i in range(bodies): w.bodies[f"dead{i}"] = p
            w.dawn(random.Random(seed)); return sum(1 for c in w.living() if c["sick"])
        clean = sum(sick_after(0, 0, i) for i in range(60)); foul = sum(sick_after(9, 3, i) for i in range(60))
        self.assertGreater(foul, clean * 2, f"filth and bodies must breed sickness (clean {clean}, foul {foul})")

    def test_the_sick_cannot_shake_it_alone_and_get_worse(self) -> None:
        w = valley(n=1, seed=5); c = w.characters["P0"]; c["sick"] = True; c["hp"] = 6; c["needs"] = {"food": 2, "warmth": 2, "rest": 8}
        w.ledger["meals"] = 0; w.ledger["grain"] = 0; w.ledger["fish"] = 0; w.ledger["meat"] = 0
        w.dawn(random.Random(5)); self.assertLess(c["hp"], 6); self.assertTrue(c["sick"]); self.assertIn("P0", w.day_report["sick"])

    def test_the_prompts_carry_needs_and_the_morning(self) -> None:
        w = valley(); w.dawn(random.Random(1))
        self.assertIn("HOW YOU ARE:", w.sheet("P0")); self.assertIn("food", w.sheet("P0"))
        self.assertIn("Day 1, autumn,", w.dawn_text()); self.assertIn("grain", w.ledger_text()); self.assertIn("roof", w.places_text())
        self.assertIn("PROSPERITY, day 1, autumn,", w.standings_table())

    def test_events_land_on_the_new_stores(self) -> None:
        w = valley(n=4); log: list[str] = []; old = engine.EVENTS
        engine.EVENTS = [{"t": "Rats.", "tier": 1, "effect": {"grain": -2}}, {"t": "{who} coughs.", "tier": 1, "effect": {"sick": 2}}, {"t": "{who}'s roof falls.", "tier": 1, "effect": {"roofs": 1}}]
        try:
            g0 = w.ledger["grain"]; roofs0 = sum(u["roof"] for u in w.upkeep.values())
            for i in range(12): w.draw_events(10, random.Random(i), log)
        finally: engine.EVENTS = old
        self.assertLess(w.ledger["grain"], g0); self.assertTrue(any(c["sick"] for c in w.living())); self.assertLess(sum(u["roof"] for u in w.upkeep.values()), roofs0)

    def test_an_old_save_gets_the_new_ledger(self) -> None:
        w = engine.World({"ledger": {"grain_weeks": 9, "grain_needed": 16, "roofs_broken": 3, "road_safe": True, "sick": 1, "built": ["a granary"]}})
        for k in STORES: self.assertIn(k, w.ledger)
        self.assertEqual(w.ledger["grain"], 18); self.assertTrue(w.ledger["road_safe"]); self.assertEqual(w.ledger["built"], ["a granary"])
        self.assertNotIn("grain_weeks", w.ledger); self.assertTrue(w.upkeep)


if __name__ == "__main__":
    unittest.main()
