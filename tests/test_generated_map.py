"""Generated maps: validation, generation through the CLI path, fallback, event gating, a full stub game, and the built-in path.
Run from the repo root:  python -m pytest tests -q     or     python -m unittest tests.test_generated_map -v"""
from __future__ import annotations
import json, math, os, random, shutil, sys, tempfile, threading, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "tests"))
import agents, engine, game  # noqa: E402
from stub_agent import FIXED_MAP  # noqa: E402

STUB = ROOT / "tests" / "stub_agent.py"
STUB_MODEL = {"provider": "Stub", "model": "stub"}


def fixed() -> dict:
    return json.loads(json.dumps(FIXED_MAP))


def by_name(m: dict) -> dict:
    return {p["name"]: p for p in m["places"]}


def connected(places: dict) -> bool:
    start = next(iter(places)); seen = {start}; stack = [start]
    while stack:
        for a in places[stack.pop()]["adj"]:
            if a not in seen: seen.add(a); stack.append(a)
    return seen == set(places)


class MapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-test-"))
        engine.GAMES = self.tmp; game.GAMES = self.tmp
        cmd = f'"{sys.executable}" "{STUB}" "{{ask}}" --model {{model}}'
        agents.PROVIDERS["Stub"] = {"exe": sys.executable, "speech": "stdout", "resume": "", "models": ["stub"], "cmd": cmd, "ro_cmd": cmd}
        os.environ.pop("TERRA_STUB_MAP", None)

    def tearDown(self) -> None:
        os.environ.pop("TERRA_STUB_MAP", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # (a) one-sided adjacency and a cut-off place become a symmetric, connected graph
    def test_a_asymmetric_and_disconnected_graph_is_repaired(self) -> None:
        m = fixed(); P = by_name(m)
        for p in m["places"]: p["adj"] = [a for a in p["adj"] if a != "Blackwater Cave"]
        P["Blackwater Cave"]["adj"] = []                       # nobody reaches the cave and it reaches nobody
        P["Saltmarket"]["adj"].append("The Mere")              # one-sided: The Mere does not list Saltmarket
        name, places, names = engine.validate_map(m)
        for n, d in places.items():
            self.assertNotIn(n, d["adj"], f"{n} lists itself")
            for a in d["adj"]:
                self.assertIn(a, places, f"{n} lists a place that does not exist: {a}")
                self.assertIn(n, places[a]["adj"], f"{n} -> {a} is one-sided")
        self.assertIn("Saltmarket", places["The Mere"]["adj"])
        self.assertTrue(places["Blackwater Cave"]["adj"], "the cave is still cut off")
        self.assertTrue(connected(places))

    # (b) two places 20 apart end up at least 110 apart; coordinates off the canvas are clamped
    def test_b_places_are_nudged_apart_and_clamped(self) -> None:
        m = fixed(); P = by_name(m)
        P["Harrow Keep"]["x"], P["Harrow Keep"]["y"] = 400, 400
        P["Saltmarket"]["x"], P["Saltmarket"]["y"] = 420, 400
        P["Blackwater Cave"]["x"], P["Blackwater Cave"]["y"] = 5000, -300
        name, places, names = engine.validate_map(m)
        a, b = places["Harrow Keep"], places["Saltmarket"]
        self.assertGreaterEqual(math.hypot(a["x"] - b["x"], a["y"] - b["y"]), 110)
        for n, d in places.items():
            self.assertTrue(0 <= d["x"] <= 1000 and 0 <= d["y"] <= 780, f"{n} is off the canvas at {d['x']},{d['y']}")
        keys = list(places)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                p, q = places[keys[i]], places[keys[j]]
                self.assertGreaterEqual(math.hypot(p["x"] - q["x"], p["y"] - q["y"]), 110, f"{keys[i]} and {keys[j]} are too close")

    # (c) an unknown kind becomes "other"; a place with no fixtures gets "the ground"
    def test_c_bad_kind_and_missing_fixtures(self) -> None:
        m = fixed(); P = by_name(m)
        P["Reedmoor"]["kind"] = "swamp"; P["Reedmoor"]["fixtures"] = []
        P["The Mere"]["fixtures"] = ["", "  "]
        name, places, names = engine.validate_map(m)
        self.assertEqual(places["Reedmoor"]["kind"], "other")
        self.assertEqual(places["Reedmoor"]["fixtures"], ["the ground"])
        self.assertEqual(places["The Mere"]["fixtures"], ["the ground"])
        self.assertEqual(places["Fenchapel"]["kind"], "chapel")

    # (d) garbage twice: the built-in map is used and the chronicle says so
    def test_d_garbage_twice_falls_back_to_builtin(self) -> None:
        os.environ["TERRA_STUB_MAP"] = "garbage"
        g = game.Game(engine.now_id()); g.map_source = "generated"; g.world_model = dict(STUB_MODEL); g.map_model = None; g.save()
        r = game.Run(g); r.prepare_map()
        w = g.world
        self.assertFalse(w.map_generated)
        self.assertEqual(json.dumps(w.map, sort_keys=True), json.dumps(engine.BASE_MAP, sort_keys=True))
        notes = [e for e in g.transcript if e["speaker"] == "Engine" and "built-in" in e["text"]]
        self.assertEqual(len(notes), 1, "no Engine note about the fallback")
        self.assertEqual(len(list((g.dir / "seat0").glob("prompt_*"))), 2, "expected exactly one retry")

    # (e) an event naming Ashford does not fire on a map without Ashford; a {place} event does
    def test_e_events_naming_builtin_places_are_gated(self) -> None:
        ashford = next(e for e in engine.EVENTS if "at Ashford" in e["t"])
        generic = next(e for e in engine.EVENTS if e["t"].startswith("Bandits from the woods raid {place}"))
        def fresh(generated: bool) -> engine.World:
            w = engine.World()
            if generated: w.install_map(*engine.validate_map(fixed()))
            w.characters = {"Bett": engine.roll_character("Bett", 1, random.Random(1), list(w.map))}
            return w
        self.assertFalse(fresh(True).event_fits(ashford)); self.assertTrue(fresh(True).event_fits(generic))
        self.assertTrue(fresh(False).event_fits(ashford)); self.assertTrue(fresh(False).event_fits(generic))
        old = engine.EVENTS; engine.EVENTS = [ashford, generic]
        try:
            seen = []
            for i in range(80): seen += fresh(True).draw_events(10, random.Random(i), [])
        finally: engine.EVENTS = old
        self.assertTrue(any(t.startswith("Bandits") for t in seen), "the {place} event never fired")
        self.assertFalse(any("Ashford" in t for t in seen), "an Ashford event fired on a map without Ashford")

    # (f) a whole stub game on a generated map: three days, travel, a fire, a destroyed fixture, no exceptions
    def test_f_full_stub_game_on_generated_map(self) -> None:
        g = game.Game(engine.now_id()); g.map_source = "generated"; g.players = 3; g.max_days = 3; g.drama = 0
        g.world_model = dict(STUB_MODEL); g.model_a = dict(STUB_MODEL); g.model_b = dict(STUB_MODEL); g.save()
        r = game.Run(g); errs: list = []
        old_hook = threading.excepthook; threading.excepthook = lambda a: errs.append(a)
        try:
            r.start(); deadline = time.time() + 240
            while not g.world.created and g.status == "running" and time.time() < deadline: time.sleep(0.2)
            w = g.world
            self.assertTrue(w.created, f"the world was never created (status {g.status}, errors {errs})")
            with r.lock:
                self.assertTrue(w.map_generated); self.assertEqual(w.map_name, "Harrowmere")
                self.assertTrue(set(w.characters) <= set(FIXED_MAP["names"]), "people were not named from the generated map")
                for c in w.characters.values(): c["hp"] = c["hp_max"] = 40
                homes = {n: c["location"] for n, c in w.characters.items()}
                self.assertEqual(w.ignite("Saltmarket"), "Saltmarket is burning")
                self.assertEqual(w.destroy("Fenchapel", "the bell"), "the bell destroyed")
            while g.status == "running" and time.time() < deadline: time.sleep(0.3)
        finally: threading.excepthook = old_hook; r.stop()
        self.assertEqual(g.status, "done"); self.assertGreater(w.day, 3)
        self.assertEqual(errs, [], f"a thread raised: {errs}")
        for t in r.terms: self.assertNotIn("[engine error", "\n".join(t["lines"]))
        self.assertTrue(any(c["location"] != homes[n] for n, c in w.characters.items()), "nobody travelled")
        self.assertIn("the bell", w.map["Fenchapel"].get("destroyed", []))
        self.assertTrue(any(t["text"].startswith("Fire at Saltmarket") for t in w.threads), "no fire situation was opened")
        self.assertTrue(w.map["Saltmarket"].get("destroyed"), "the fire ruined nothing")
        self.assertNotIn("Saltmarket", w.fires, "the fire never burned out")
        self.assertTrue(any(e["kind"] == "world" for e in g.transcript))

    # (g) the built-in path leaves world.map byte for byte equal to data/map.json
    def test_g_builtin_map_is_unchanged(self) -> None:
        g = game.Game(engine.now_id()); g.map_source = "builtin"; g.world_model = dict(STUB_MODEL); g.save()
        r = game.Run(g); r.prepare_map()
        disk = json.loads((ROOT / "data" / "map.json").read_text(encoding="utf-8"))["places"]
        self.assertEqual(json.dumps(g.world.map, sort_keys=True, ensure_ascii=False), json.dumps(disk, sort_keys=True, ensure_ascii=False))
        self.assertEqual(g.world.map_name, "Terraceilia"); self.assertFalse(g.world.map_generated)
        self.assertEqual(list((g.dir / "seat0").glob("prompt_*")), [], "the built-in path must not call any CLI")


if __name__ == "__main__":
    unittest.main()
