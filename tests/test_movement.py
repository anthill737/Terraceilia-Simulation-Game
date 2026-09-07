"""Live movement: the engine records what each person is doing, where, and since when, so the map can walk them there.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, sys, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402


def valley(n: int = 4) -> engine.World:
    w = engine.World(); rng = random.Random(3); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard"][i % 4]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1; w.seed_duties(rng); w.assign_day(rng)
    return w


class ActivityTests(unittest.TestCase):
    def test_work_walks_them_to_each_duty_with_a_label_and_a_duration(self) -> None:
        w = valley(); c = w.characters["P0"]; c["duties"] = ["mill", "wood"]; t0 = time.time()
        for k in c["duties"]: c["skills"][engine.DUTIES[k]["skill"]] = 9
        w.resolve_morning("P0", "WORK", random.Random(1)); a = w.activities["P0"]
        self.assertEqual(a["state"], "working"); self.assertGreaterEqual(a["started"], t0 - 1); self.assertEqual(len(a["stops"]), 2)
        self.assertEqual(a["stops"][0]["place"], w.duty_place("mill")); self.assertIn("grain", a["stops"][0]["what"]); self.assertGreater(a["stops"][0]["dur"], 0)
        self.assertEqual(c["location"], a["stops"][-1]["place"], "when the work is done they are at the last thing")
        self.assertEqual(c["activity"], a["what"])

    def test_labels_name_the_thing_or_the_person(self) -> None:
        w = valley(); c = w.characters["P0"]; c["duties"] = ["healing", "roofs"]; c["skills"] = {"healing": 9, "carpentry": 9}
        w.characters["P1"]["sick"] = True; w.characters["P1"]["location"] = w.characters["P0"]["location"]; w.mark_nothing_to_do()
        w.resolve_morning("P0", "WORK", random.Random(2)); stops = w.activities["P0"]["stops"]
        self.assertEqual(stops[0]["what"], "tending P1"); self.assertTrue(stops[1]["what"].startswith("mending the roof at "))

    def test_skippers_are_idle_and_the_sick_rest_at_home(self) -> None:
        w = valley(); w.resolve_morning("P1", "I go drinking", random.Random(1)); self.assertEqual(w.activities["P1"]["state"], "idle"); self.assertEqual(w.activities["P1"]["what"], "idle")
        c = w.characters["P2"]; c["sick"] = True; w.resolve_morning("P2", "WORK", random.Random(1))
        self.assertEqual(w.activities["P2"]["state"], "resting"); self.assertEqual(w.activities["P2"]["stops"][0]["place"], c["home"])

    def test_emergencies_move_people_at_once(self) -> None:
        w = valley(); p = w.characters["P0"]["location"]; far = max(w.map, key=lambda q: w.distance(q, p))
        for c in w.living(): c["hp"] = c["hp_max"] = 30; c["location"] = far
        w.fires[p] = 0; w.assign_day(random.Random(1))
        pulled = [n for n, a in w.activities.items() if a["state"] == "emergency"]
        self.assertTrue(pulled); a = w.activities[pulled[0]]; self.assertTrue(a["immediate"]); self.assertEqual(a["stops"][0]["place"], p)

    def test_evening_and_the_end_of_the_day(self) -> None:
        w = valley(); w.phase = "evening"; w.evening_places(random.Random(1))
        for c in w.living(): self.assertIn(w.activities[c["name"]]["what"], ("at home", "at the inn")); self.assertEqual(w.activities[c["name"]]["stops"][0]["place"], c["location"])
        w.end_day()
        for c in w.living(): self.assertEqual(w.activities[c["name"]]["state"], "resting"); self.assertEqual(c["location"], c["home"])

    def test_a_travel_action_starts_the_walk_before_the_engine_resolves_it(self) -> None:
        w = valley(); c = w.characters["P0"]; here = c["location"]; far = max(w.map, key=lambda q: w.distance(q, here))
        self.assertEqual(w.start_walk("P0", f"I walk to {far}"), far); a = w.activities["P0"]
        self.assertTrue(a["provisional"]); self.assertEqual(a["from"], here); self.assertEqual(a["stops"][0]["place"], far); self.assertEqual(c["location"], here, "the engine has not moved them yet")
        self.assertIsNone(w.start_walk("P0", "I sharpen my knife")); self.assertIsNone(w.start_walk("P0", f"I stay at {here}"))
        r = w.resolve_verb("P0", w.parse_verb("P0", f"I walk to {far}"), random.Random(1)); a2 = w.activities["P0"]
        self.assertFalse(a2.get("provisional")); self.assertEqual(a2["from"], here, "the settled walk starts from where they were"); self.assertEqual(a2["stops"][0]["place"], c["location"])
        self.assertEqual(c["location"], w._path(here, far)[1]); self.assertTrue(r["ok"])

    def test_the_map_walks_every_move_and_never_jumps(self) -> None:
        import subprocess
        r = subprocess.run(["node", str(ROOT / "tests" / "walks_check.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("six position changes in one poll give six walk animations", r.stdout); self.assertIn("ALL PASS", r.stdout)
        js = (ROOT / "frontend" / "map.js").read_text(encoding="utf-8"); html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Walks.plan(s,prev,serverNow())", js); self.assertIn("posAt(tl,now-tl.base", js); self.assertNotIn("function buildTimeline", js)
        self.assertLess(html.index('src="walks.js"'), html.index('src="map.js"'))

    def test_the_map_is_told_with_a_clock(self) -> None:
        import connect, server, game, shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="terra-move-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; g.world = valley(); g.world.set_activity("P0", "acting", "walks to the inn", [{"place": list(g.world.map)[1], "what": "walks to the inn", "dur": 8}])
            m = app.map_state(); self.assertIn("activities", m); self.assertEqual(m["activities"]["P0"]["what"], "walks to the inn"); self.assertAlmostEqual(m["now"], time.time(), delta=5)
            self.assertIn("activities", app.snapshot())
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
