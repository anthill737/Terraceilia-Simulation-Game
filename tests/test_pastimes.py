"""Free time and pastimes. A morning skip costs the day, two running cost the duty. Everyone has a pastime seeded from their
nature, a spirit that falls daily and rises on the pastime, good company, or a good meal, and a free afternoon spent on the
pastime by default, on the map, with company where places coincide. Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402
from engine import PASTIMES, DUTIES  # noqa: E402


def valley(n: int = 6, seed: int = 8) -> engine.World:
    w = engine.World(); rng = random.Random(seed); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard", "healer", "farmer"][i % 6]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1; w.seed_duties(rng); w.seed_pastimes(rng); w.assign_day(rng)
    return w


class SkipTests(unittest.TestCase):
    def test_one_skip_costs_the_day_two_cost_the_duty_and_work_resets_it(self) -> None:
        w = valley(); c = w.characters["P0"]; held = list(c["duties"])
        out = w.resolve_morning("P0", "I take a walk instead", random.Random(1)); self.assertFalse(out[-1]["lost"]); self.assertEqual(c["duties"], held); self.assertEqual(c["skip_streak"], 1)
        w.day += 1; w.resolve_morning("P0", "WORK", random.Random(2)); self.assertEqual(c["skip_streak"], 0, "a morning of work forgives the skip")
        w.day += 1; w.resolve_morning("P0", "I take a walk", random.Random(3)); w.day += 1; out = w.resolve_morning("P0", "I take another walk", random.Random(4))
        self.assertTrue(out[-1]["lost"]); self.assertEqual(c["duties"], []); self.assertIn("second day running", out[-1]["text"])

    def test_refuse_still_gives_the_duty_up_at_once(self) -> None:
        w = valley(); c = w.characters["P0"]; out = w.resolve_morning("P0", "REFUSE", random.Random(1)); self.assertTrue(out[-1]["lost"]); self.assertEqual(c["duties"], [])


class PastimeTests(unittest.TestCase):
    def test_the_list_and_the_seeding_from_disposition(self) -> None:
        for k in ("carving", "fishing", "singing", "dice", "drinking", "wandering", "gossip", "garden", "sparring", "stories", "praying", "collecting"): self.assertIn(k, PASTIMES)
        w = valley()
        for c in w.living(): self.assertIn(c["pastime"], PASTIMES)
        drunk = w.characters["P0"]; drunk["traits"] = {t: 3 for t in engine.TRAITS}; drunk["traits"]["drink"] = 5
        pious = w.characters["P1"]; pious["traits"] = {t: 3 for t in engine.TRAITS}; pious["traits"]["piety"] = 5
        picks = [w.roll_pastime("P0", random.Random(i)) for i in range(40)]; self.assertGreater(picks.count("drinking"), 15, picks)
        picks = [w.roll_pastime("P1", random.Random(i)) for i in range(40)]; self.assertGreater(picks.count("praying"), 15, picks)

    def test_fate_can_set_it(self) -> None:
        w = valley(); self.assertIn("is now carving", w.set_pastime("P0", "carving")); self.assertEqual(w.characters["P0"]["pastime"], "carving")
        self.assertEqual(w.set_pastime("P0", "carving"), "no change"); self.assertTrue(w.set_pastime("P0", "knitting").startswith("no such"))

    def test_a_free_afternoon_goes_to_the_pastime_on_the_map_with_a_label(self) -> None:
        w = valley(); c = w.characters["P0"]; c["pastime"] = "praying"; c["needs"]["spirit"] = 3
        r = w.do_pastime("P0", random.Random(1))
        self.assertEqual(r["kind"], "pastime"); self.assertEqual(c["location"], w.pastime_place("P0")); self.assertEqual(w.map[c["location"]]["kind"], "chapel")
        self.assertEqual(w.activities["P0"]["state"], "pastime"); self.assertEqual(w.activities["P0"]["what"], "praying at the chapel"); self.assertGreater(c["needs"]["spirit"], 3)
        self.assertTrue(any("spent the afternoon praying" in x["text"] for x in c["log"]))

    def test_side_effects(self) -> None:
        w = valley(); rng = random.Random(2)
        c = w.characters["P0"]; c["pastime"] = "fishing"; f0 = w.ledger["fish"]; w.do_pastime("P0", rng); self.assertEqual(w.ledger["fish"], f0 + 1)
        c = w.characters["P1"]; c["pastime"] = "carving"; w.do_pastime("P1", rng); self.assertTrue(c["items"]); self.assertIn("made", w.activities and c["log"][-1]["text"])
        c = w.characters["P2"]; c["pastime"] = "drinking"; c["needs"].update({"rest": 6, "warmth": 6}); w.do_pastime("P2", rng); self.assertEqual((c["needs"]["rest"], c["needs"]["warmth"]), (4, 5))
        c = w.characters["P3"]; c["pastime"] = "sparring"; c["str"] = 4; ups = 0
        for i in range(40): c["str"] = 4; w.do_pastime("P3", random.Random(i)); ups += c["str"] > 4
        self.assertGreater(ups, 0, "sparring never nudged strength")

    def test_the_same_place_makes_company_and_lifts_the_spirit(self) -> None:
        w = valley(); a, b = w.characters["P0"], w.characters["P1"]; a["pastime"] = b["pastime"] = "dice"; w.set_rel("P0", "P1", feeling=4)
        a["needs"]["spirit"] = 3; w.do_pastime("P1", random.Random(1)); r = w.do_pastime("P0", random.Random(1))
        self.assertEqual(a["location"], b["location"]); self.assertIn("good company: P1", r["text"]); self.assertEqual(a["needs"]["spirit"], 8)
        groups = w.pastime_groups(); self.assertEqual(set(groups[a["location"]]), {"P0", "P1"})


class SpiritTests(unittest.TestCase):
    def test_spirit_falls_daily_and_a_good_meal_lifts_it(self) -> None:
        w = valley(n=2); c = w.characters["P0"]; c["needs"]["spirit"] = 6; w.ledger["meals"] = 0; w.ledger["grain"] = 0; w.ledger["fish"] = 0; w.ledger["meat"] = 0
        w.dawn(random.Random(1)); self.assertEqual(c["needs"]["spirit"], 5)
        c["needs"]["spirit"] = 6; w.ledger["meals"] = 5; w.day += 1; w.dawn(random.Random(1)); self.assertEqual(c["needs"]["spirit"], 6, "a meal lifts what the day takes")
        self.assertIn("spirit", w.needs_text("P0")); self.assertIn("in good spirits", w.needs_text("P0") if c["needs"]["spirit"] >= 5 else "in good spirits")

    def test_low_spirit_lowers_output_and_high_raises_it(self) -> None:
        def made(spirit: int) -> int:
            w = valley(n=2); c = w.characters["P0"]; c["skills"]["woodcutting"] = 4; c["needs"]["spirit"] = spirit; total = 0
            for i in range(30): w.ledger["tools"] = 5; total += w.do_duty("P0", "wood", random.Random(i))["made"].get("wood", 0)
            return total
        low, mid, high = made(1), made(5), made(9)
        self.assertLess(low, mid); self.assertGreater(high, mid)

    def test_low_spirit_makes_refusing_likelier(self) -> None:
        w = valley(n=2); c = w.characters["P0"]; c["needs"]["spirit"] = 0
        skips = sum(1 for i in range(60) if w.resolve_morning("P0", "WORK", random.Random(i))[-1].get("kind") == "skip" for _ in [c.__setitem__("skip_streak", 0)])
        self.assertGreater(skips, 5, "a broken spirit should sometimes not face the work")
        self.assertTrue(any("spirit is low" in u for u in engine.urges(c, w, random.Random(3))), "the prompt says so")


class ServerTests(unittest.TestCase):
    def test_pastime_and_spirit_are_told_and_editable(self) -> None:
        import connect, game, server
        tmp = Path(tempfile.mkdtemp(prefix="terra-past-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; g.world = valley(n=2); w = g.world
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            app.run._sync_terms(); g.save()
            w.characters["P0"]["pastime"] = "walking"        # whatever the roll gave them, the edit has somewhere to move it to
            self.assertIn("pastime is now singing at the inn", app.edit_character({"name": "P0", "pastime": "singing"}))
            self.assertIn("in good spirits", app.edit_character({"name": "P0", "needs": {"spirit": 9}}))
            snap = app.snapshot(); self.assertIn("pastime_defs", snap); self.assertEqual(next(c for c in snap["characters"] if c["name"] == "P0")["pastime"], "singing")
            self.assertEqual(next(c for c in app.map_state()["characters"] if c["name"] == "P0")["needs"]["spirit"], 9)
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
