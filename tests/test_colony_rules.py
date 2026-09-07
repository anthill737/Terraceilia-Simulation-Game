"""The rules of the colony, checked together: needs come before work, the ledger decays by season, unfilled duties reach the
World by name, refusing costs, and the words of the old order are gone. The finer points live in the other test files; this
one reads across them. Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, re, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "tests"))
import engine, game  # noqa: E402
from engine import DUTIES, STORES, strip_dashes  # noqa: E402
from test_no_court import OLD_WORDS  # noqa: E402

EM, EN, HB = chr(0x2014), chr(0x2013), chr(0x2015)      # by code point: the dashes themselves are banned from the repo


def valley(n: int = 6, day: int = 1, seed: int = 11) -> engine.World:
    w = engine.World(); rng = random.Random(seed); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard", "healer", "farmer"][i % 6]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = day; w.seed_duties(rng); w.seed_wants(rng); w.assign_day(rng)
    return w


class NeedsPreemption(unittest.TestCase):
    def test_a_starving_person_eats_first_and_keeps_their_duty(self) -> None:
        w = valley(); c = w.characters["P0"]; held = list(c["duties"]); c["needs"]["food"] = 0; w.ledger["meals"] = 3; s0 = c["standing_score"]
        out = w.resolve_morning("P0", "WORK", random.Random(1))
        self.assertEqual(out[0]["kind"], "needs"); self.assertIn("too hungry to work", out[0]["text"]); self.assertIn("ate a meal", out[0]["text"])
        self.assertEqual(w.ledger["meals"], 2); self.assertGreater(c["needs"]["food"], 0)
        self.assertEqual(c["duties"], held, "the duty waits; it is not lost"); self.assertEqual(c["standing_score"], s0, "no shame in eating")
        self.assertEqual(w.activities["P0"]["state"], "needs")

    def test_a_freezing_person_goes_home_to_the_fire(self) -> None:
        w = valley(); c = w.characters["P1"]; c["needs"]["warmth"] = 0; away = [p for p in w.map if p != c["home"]][0]; c["location"] = away; w.ledger["wood"] = 4
        warm0 = w.upkeep[c["home"]]["warmth"]
        out = w.resolve_morning("P1", "WORK", random.Random(1))
        self.assertEqual(out[0]["kind"], "needs"); self.assertIn("too cold to work", out[0]["text"]); self.assertEqual(c["location"], c["home"])
        self.assertEqual(w.ledger["wood"], 3); self.assertGreater(w.upkeep[c["home"]]["warmth"], warm0); self.assertGreater(c["needs"]["warmth"], 0)

    def test_with_nothing_to_eat_the_morning_is_still_lost(self) -> None:
        w = valley(); c = w.characters["P2"]; c["needs"]["food"] = 0
        for k in ("meals", "grain", "fish", "meat"): w.ledger[k] = 0
        out = w.resolve_morning("P2", "WORK", random.Random(1)); self.assertIn("found nothing to eat", out[0]["text"]); self.assertEqual(c["needs"]["food"], 0)

    def test_a_fed_and_warm_person_works(self) -> None:
        w = valley(); c = w.characters["P0"]; c["needs"] = {"food": 5, "warmth": 5, "rest": 5}
        out = w.resolve_morning("P0", "WORK", random.Random(1)); self.assertTrue(all(r["kind"] == "work" for r in out))


class LedgerBySeason(unittest.TestCase):
    def run_day(self, day: int, weather: str, seed: int = 4) -> engine.World:
        w = valley(n=6, day=day, seed=seed); old = engine.roll_weather; engine.roll_weather = lambda d, r: weather
        try: w.dawn(random.Random(seed))
        finally: engine.roll_weather = old
        return w

    def test_winter_burns_more_wood_than_autumn_and_rain_rots_roofs(self) -> None:
        autumn = self.run_day(2, "clear"); winter = self.run_day(20, "bitter cold"); wet = self.run_day(2, "storm")
        self.assertLess(winter.ledger["wood"], autumn.ledger["wood"])
        roofs = lambda w: sum(u["roof"] for p, u in w.upkeep.items() if w.roofed(p))
        self.assertLess(roofs(wet), roofs(autumn))
        self.assertTrue(engine.growing(2, "clear")); self.assertFalse(engine.growing(20, "clear"))

    def test_nothing_in_the_ledger_grows_without_work(self) -> None:
        w = valley(n=6); before = dict(w.ledger)
        for d in range(1, 6): w.day = d; w.dawn(random.Random(d))
        for k in STORES: self.assertLessEqual(w.ledger[k], before[k], f"{k} rose with nobody working")
        w.characters["P0"]["skills"]["woodcutting"] = 9; wood0 = w.ledger["wood"]
        w.do_duty("P0", "wood", random.Random(2)); self.assertGreater(w.ledger["wood"], wood0, "work is the only way up")

    def test_the_season_and_weather_line_opens_every_day(self) -> None:
        w = valley(day=9); w.dawn(random.Random(1))
        self.assertRegex(w.dawn_text().split("\n")[0], r"^Day 9, early winter, (clear|rain|snow|storm)\.$")


class UnfilledDutiesReachTheWorld(unittest.TestCase):
    def test_the_world_prompt_names_what_went_undone_and_who_complained(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-rules-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = valley(n=4); w = g.world
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g)
            w.end_morning({"mill"}, random.Random(1)); w.day = 2; w.assign_day(random.Random(2)); w.end_morning({"mill"}, random.Random(2))
            prompt = r._world_prompt([], {}, [], [])
            self.assertIn("UNDONE TODAY, by name", prompt)
            for k in ("hunt", "fish", "wood"): self.assertIn(DUTIES[k]["label"].capitalize() + " went undone", prompt)
            self.assertIn("days running", prompt); self.assertRegex(prompt, r"P\d complains that the .+ has gone undone 2 days running")
            self.assertIn("THE DUTIES, who holds each", prompt)
            self.assertNotIn("The mill went undone", prompt, "a duty that was done is not reported undone")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RefusalConsequences(unittest.TestCase):
    def test_refusing_and_skipping_both_cost_standing_and_the_duty(self) -> None:
        for act in ("REFUSE", "I walk to the inn instead"):
            w = valley(); c = w.characters["P0"]; held = list(c["duties"]); s0 = c["standing_score"]
            w.resolve_morning("P0", act, random.Random(1))
            self.assertEqual(c["duties"], []); self.assertLess(c["standing_score"], s0)
            for k in held: self.assertFalse(w.holders(k) and "P0" in w.holders(k)); self.assertTrue(w.duty_state(k)["unclaimed_day"] is not None or w.holders(k))
            self.assertTrue(any(("refused" if act == "REFUSE" else "skipped") in x["text"] for x in c["log"]))


class EmDashes(unittest.TestCase):
    def test_no_model_line_keeps_a_dash(self) -> None:
        for line in (f"a {EM} b", f"a{EM}b", f"{EM} a", f"a {EM}", f"a {EN} b", f"a {HB} b"):
            self.assertNotIn(EM, strip_dashes(line)); self.assertNotIn(EN, strip_dashes(line)); self.assertNotIn(HB, strip_dashes(line))

    def test_no_dash_in_the_repo_itself(self) -> None:
        bad = []
        for root in (ROOT / "backend", ROOT / "frontend", ROOT / "data", ROOT / "tests", ROOT / "README.md"):
            files = [root] if root.is_file() else [f for f in root.rglob("*") if f.suffix in {".py", ".js", ".html", ".css", ".json", ".md"} and "__pycache__" not in f.parts]
            for f in files:
                t = f.read_text(encoding="utf-8")
                if EM in t or EN in t: bad.append(str(f.relative_to(ROOT)))
        self.assertEqual(bad, [], "dashes in: " + ", ".join(bad))


class WantsAndCourt(unittest.TestCase):
    def test_want_progress_and_completion(self) -> None:
        w = valley(); c = w.characters["P0"]; c["goal"] = {"kind": "skill", "target": "milling", "level": 3, "text": "to reach milling 3"}; c["skills"]["milling"] = 1
        self.assertEqual(w.want_progress("P0")[0], 33); c["skills"]["milling"] = 3
        got = w.check_wants(random.Random(1)); self.assertEqual(len(got), 1); self.assertNotEqual(c["goal"]["text"], "to reach milling 3"); self.assertEqual(c["standing"], engine.standing_word(c["standing_score"]))

    def test_no_court_anywhere(self) -> None:
        rx = OLD_WORDS; hits = []
        for root in (ROOT / "backend", ROOT / "frontend", ROOT / "data", ROOT / "README.md"):
            files = [root] if root.is_file() else [f for f in root.rglob("*") if f.suffix in {".py", ".js", ".html", ".css", ".json", ".md"} and "__pycache__" not in f.parts]
            for f in files:
                for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    if rx.search(ln): hits.append(f"{f.name}:{i}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
