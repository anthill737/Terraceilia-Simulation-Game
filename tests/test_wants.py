"""Excelling: wants the engine can measure, reached wants that raise standing and roll a new one, recognition by the valley's
best skill, and nobody starting as anything but nobody. Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, sys, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402
from engine import DUTIES  # noqa: E402


def valley(n: int = 4) -> engine.World:
    w = engine.World(); rng = random.Random(5); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard"][i % 4]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1; w.seed_duties(rng); w.seed_wants(rng)
    return w


class WantTests(unittest.TestCase):
    def test_every_want_is_one_of_the_measured_kinds_and_has_text(self) -> None:
        w = valley(20 if False else 4)
        for _ in range(60):
            for c in w.living():
                g = w.roll_want(c["name"], random.Random(_))
                self.assertIn(g["kind"], ("gold", "skill", "best", "feeling", "trust", "lover", "place")); self.assertTrue(g["text"].startswith("to "))
        for c in w.living(): self.assertTrue(c.get("goal"))

    def test_progress_is_told_and_reaching_it_raises_standing_and_rolls_a_new_want(self) -> None:
        w = valley(); c = w.characters["P0"]; c["goal"] = {"kind": "gold", "target": 10, "text": "to have 10 gold put by"}; c["gold"] = 4
        pct, how = w.want_progress("P0"); self.assertEqual(pct, 40); self.assertIn("4 of 10 gold", how); self.assertIn("40%", w.want_text("P0")); self.assertIn("10 gold", w.sheet("P0"))
        self.assertEqual(w.check_wants(random.Random(1)), [])
        c["gold"] = 10; s0 = c["standing_score"]
        got = w.check_wants(random.Random(1))
        self.assertEqual(len(got), 1); self.assertIn("P0 got what they wanted: to have 10 gold put by", got[0]["text"])
        self.assertGreater(c["standing_score"], s0); self.assertNotEqual(c["goal"]["text"], "to have 10 gold put by"); self.assertEqual(c["want"], c["goal"]["text"])
        self.assertEqual(c["wants_reached"][0]["text"], "to have 10 gold put by"); self.assertTrue(w.reached, "the World is given it to announce")
        self.assertTrue(any("got what you wanted" in x["text"] for x in c["log"]))

    def test_skill_tie_and_place_wants_are_measured(self) -> None:
        w = valley(); a, b = w.characters["P0"], w.characters["P1"]
        a["goal"] = {"kind": "skill", "target": "milling", "level": 4, "text": "to reach milling 4"}; a["skills"]["milling"] = 2
        self.assertEqual(w.want_progress("P0")[0], 50)
        a["goal"] = {"kind": "best", "target": "milling", "text": "to be the best at milling"}; b["skills"]["milling"] = 5
        self.assertLess(w.want_progress("P0")[0], 100); a["skills"]["milling"] = 6; self.assertEqual(w.want_progress("P0")[0], 100)
        a["goal"] = {"kind": "trust", "target": "P1", "level": 3, "text": "to have P1's trust"}; w.set_rel("P1", "P0", trust=-1)
        self.assertLess(w.want_progress("P0")[0], 100); w.set_rel("P1", "P0", trust=3); self.assertEqual(w.want_progress("P0")[0], 100)
        a["goal"] = {"kind": "lover", "target": "P1", "text": "to be P1's lover"}; w.set_rel("P1", "P0", typ="lover"); self.assertEqual(w.want_progress("P0")[0], 100)
        far = max(w.map, key=lambda p: w.distance(a["location"], p)); a["goal"] = {"kind": "place", "target": far, "text": f"to spend an evening at {far}"}
        self.assertLess(w.want_progress("P0")[0], 100); a["location"] = far; w.phase = "afternoon"; self.assertFalse(w.want_reached("P0"), "an evening, not a visit")
        w.phase = "evening"; self.assertTrue(w.want_reached("P0"))

    def test_recognition_goes_to_the_one_best_and_reaches_the_prompts(self) -> None:
        w = valley(); a, b = w.characters["P0"], w.characters["P1"]
        for c in w.living(): c["skills"] = {}       # people are rolled with their trade's skill; this is about earning a name, not starting with one
        self.assertEqual(w.titles(), {}, "nobody is called anything yet")
        a["skills"]["milling"] = 3; self.assertEqual(w.titles().get("P0"), ["the miller"])
        b["skills"]["milling"] = 3; self.assertNotIn("P0", w.titles(), "a tie is no title")
        b["skills"]["milling"] = 5; self.assertEqual(w.titles().get("P1"), ["the miller"]); self.assertEqual(w.titled("P1"), "P1 (the miller)")
        self.assertIn("People call you the miller", w.sheet("P1")); self.assertNotIn("People call you", w.sheet("P0"))
        for d in DUTIES.values(): self.assertTrue(d.get("title"), f"{d['key']} has no title")

    def test_nobody_starts_as_unknown(self) -> None:
        w = valley()
        for c in w.living(): self.assertEqual(c["standing"], "nobody")
        self.assertNotIn("unknown", engine.STANDING_WORDS); self.assertEqual(engine.standing_word(0), "nobody")
        old = engine.World({"characters": {"Old": {"name": "Old", "seat": 1, "alive": True, "gone": False, "standing": "unknown", "hp": 5, "hp_max": 9, "gold": 1, "skills": {}, "location": "The inn", "str": 3, "spd": 3, "trade": "", "home": "", "personality": "", "secret": "", "fear": "", "want": "", "cause_of_death": ""}}})
        self.assertEqual(old.characters["Old"]["standing"], "nobody")
        src = "\n".join(f.read_text(encoding="utf-8") for f in [ROOT / "frontend" / "app.js", ROOT / "backend" / "prompts.py"])
        self.assertNotIn("'unknown'", src.replace("cause_of_death||'unknown'", ""))


if __name__ == "__main__":
    unittest.main()
