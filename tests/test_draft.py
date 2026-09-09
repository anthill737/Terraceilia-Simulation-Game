"""Choose your people before the game starts: Generate makes a draft with no game folder, edits and rerolls change the draft,
Start freezes it and the people in the game match the draft exactly, and a draft survives a server restart.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import copy, json, os, shutil, sys, tempfile, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import agents, connect, engine, game, server  # noqa: E402

STUB = ROOT / "tests" / "stub_agent.py"
CMD = f'"{sys.executable}" "{STUB}" "{{ask}}" --model {{model}}'


def wait_for(cond, seconds: float = 60, what: str = "") -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cond(): return
        time.sleep(0.1)
    raise AssertionError("timed out waiting for " + what)


class DraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-draft-")); engine.GAMES = self.tmp; game.GAMES = self.tmp; server.GAMES = self.tmp
        self.saved = agents.PROVIDERS.get("Stub")
        agents.PROVIDERS["Stub"] = {"exe": sys.executable, "speech": "stdout", "resume": "", "models": ["stub"], "cmd": CMD, "ro_cmd": CMD}
        self._start, self._vers, self._status = connect.start, server.refresh_versions, connect.status_of
        connect.start = lambda: None; server.refresh_versions = lambda: None; connect.status_of = lambda n: "signed_in"
        with connect._probe_lock: connect._probes.clear()
        self.old_trust = game.ensure_codex_trust; game.ensure_codex_trust = lambda folder: None
        self.app = server.App()

    def tearDown(self) -> None:
        for r in list(self.app.runs.values()): r.stop()
        connect.start, server.refresh_versions, connect.status_of = self._start, self._vers, self._status
        game.ensure_codex_trust = self.old_trust
        if self.saved is None: agents.PROVIDERS.pop("Stub", None)
        else: agents.PROVIDERS["Stub"] = self.saved
        with connect._probe_lock: connect._probes.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub_models(self) -> None:
        self.app.configure({"title": "Fen draft", "players": 3, "max_days": 1, "drama": 0, "world_model": {"provider": "Stub", "model": "stub"},
                            "model_a": {"provider": "Stub", "model": "stub"}, "model_b": {"provider": "Stub", "model": "stub"}, "repo": str(self.tmp)})

    def generate(self, what: str = "all") -> None:
        r = self.app.run; note = self.app.generate(what); self.assertIn("rolling", note, note)
        wait_for(lambda: not r.generating, 90, "the draft to be rolled")

    def test_a_new_valley_is_a_draft_with_no_game_folder(self) -> None:
        g = self.app.run.g
        self.assertTrue(g.draft); self.assertEqual(g.status, "idle"); self.assertFalse(g.world.created)
        self.assertFalse((self.tmp / g.id).exists(), "a draft has no game folder"); self.assertTrue((self.tmp / "drafts" / g.id / "draft.json").exists())
        self.assertEqual(game.list_games(), [], "a draft is not a game"); self.assertEqual([d["id"] for d in game.list_drafts()], [g.id])
        snap = self.app.snapshot(); self.assertTrue(snap["draft"]); self.assertFalse(snap["draft_ready"]); self.assertEqual(snap["games"][0]["status"], "draft")

    def test_generate_rolls_the_map_and_the_people_and_it_is_still_not_a_game(self) -> None:
        self.stub_models(); g = self.app.run.g; w = g.world
        self.generate()
        self.assertEqual(len(w.characters), 3); self.assertEqual(len(g.seats), 4, "the World and three people")
        for c in w.characters.values():
            self.assertEqual(c["trade"], "eel catcher", "the World wrote the lives"); self.assertTrue(c["duties"]); self.assertTrue(c["pastime"]); self.assertTrue(c["goal"])
            self.assertIn(c["voice"]["length"], engine.VOICE_LENGTHS); self.assertEqual(len(c["voice"]["examples"]), 3)
        a, b = list(w.characters)[:2]; self.assertEqual(w.rel(a, b)["type"], "rival", "the relationships came with the lives")
        self.assertTrue(g.draft_narration.startswith("The fen wakes"))
        self.assertFalse(w.created); self.assertEqual(w.day, 0); self.assertEqual(g.transcript, [], "nothing is a game yet")
        self.assertFalse((self.tmp / g.id).exists(), "still no game folder"); self.assertEqual(game.list_games(), [])
        self.assertTrue(self.app.snapshot()["characters"], "the People sheet has people to show")

    def test_edits_and_rerolls_change_the_draft(self) -> None:
        self.stub_models(); r = self.app.run; g = r.g; w = g.world; self.generate()
        first = list(w.characters)[0]
        self.assertIn("trade changed", self.app.edit_character({"name": first, "trade": "smith", "personality": "hard as her anvil"}))
        self.assertEqual(w.characters[first]["trade"], "smith"); self.assertEqual(g.transcript, [], "no fate line while drafting")
        self.app.edit_relation({"a": first, "b": list(w.characters)[1], "type": "friend", "feeling": 4, "trust": 3}); self.assertEqual(w.rel(first, list(w.characters)[1])["feeling"], 4)
        seat = next(x for x in g.seats if x["name"] == first); seat["model"] = "stub"; color = seat["color"]; stats = (w.characters[first]["str"], w.characters[first]["spd"], list(w.characters[first]["duties"])); old = set(w.characters)
        note = r.reroll_person(first); self.assertIn("rerolling", note); wait_for(lambda: not r.generating, 60, "the reroll")
        self.assertNotIn(first, w.characters, "a new name"); new = next(n for n in w.characters if n not in old)
        self.assertEqual(next(x for x in g.seats if x["name"] == new)["color"], color, "the same seat")
        self.assertEqual(next(x for x in g.seats if x["name"] == new)["model"], "stub", "seat and model kept")
        self.assertEqual((w.characters[new]["str"], w.characters[new]["spd"], w.characters[new]["duties"]), stats, "stats and jobs kept")
        self.assertEqual(w.characters[new]["trade"], "eel catcher", "a new life from the World"); self.assertTrue(w.characters[new]["voice"])
        self.assertIn(new, w.relations); self.assertNotIn(first, w.relations)
        r.remove_person(new); self.assertNotIn(new, w.characters); self.assertEqual(len(g.seats), 3); self.assertFalse(any(new in rs for rs in w.relations.values()))
        self.assertIn("adding", r.add_person()); wait_for(lambda: not r.generating, 60, "the add")
        self.assertEqual(len(w.characters), 3); added = list(w.characters)[-1]; self.assertEqual(w.characters[added]["trade"], "eel catcher"); self.assertTrue(w.characters[added]["duties"])
        self.assertEqual(len(g.seats), 4)
        names = set(w.characters); self.generate("people"); self.assertEqual(len(w.characters), 3); self.assertNotEqual(set(w.characters), names, "Reroll all rerolls everyone")
        saved = json.loads((self.tmp / "drafts" / g.id / "draft.json").read_text(encoding="utf-8")); self.assertEqual(set(saved["world"]["characters"]), set(w.characters), "the draft is saved as it changes")
        self.assertFalse((self.tmp / g.id).exists())

    def test_regenerate_map_keeps_the_people(self) -> None:
        self.stub_models(); r = self.app.run; g = r.g; w = g.world; self.app.configure({"map_source": "generated"}); self.generate()
        self.assertTrue(w.map_generated); names = list(w.characters); lives = {n: w.characters[n]["personality"] for n in names}
        self.assertIn("rolling", r.regenerate_map()); wait_for(lambda: not r.generating and not r.map_generating, 60, "the map")
        self.assertEqual(list(w.characters), names, "the people stay"); self.assertEqual({n: w.characters[n]["personality"] for n in names}, lives)
        for c in w.characters.values(): self.assertIn(c["home"], w.map); self.assertIn(c["location"], w.map)

    def test_start_needs_people_and_tested_seats_then_freezes_the_draft(self) -> None:
        self.stub_models(); r = self.app.run; g = r.g; w = g.world
        self.app.start_game(); self.assertIn("Generate the valley first", self.app.start_error); self.assertTrue(g.draft)
        self.generate()
        with connect._probe_lock: connect._probes.clear()          # the World answered at Generate; pretend nothing has been tested yet
        self.assertFalse(r.draft_ready()); self.app.start_game(); self.assertIn("tested model", self.app.start_error); self.assertTrue(g.draft); self.assertFalse(w.created)
        self.assertIn("testing", r.test_seats()); wait_for(lambda: not r.testing, 60, "the seat tests")
        self.assertTrue(r.draft_ready()); self.assertTrue(all(self.app.snapshot()["seat_tests"].values()))
        before = copy.deepcopy(w.characters); rels = copy.deepcopy(w.relations); seats = copy.deepcopy(g.seats); narration = g.draft_narration
        self.app.start_game(); self.assertEqual(self.app.start_error, "")
        try:
            self.assertFalse(g.draft); self.assertTrue(w.created); self.assertGreaterEqual(w.day, 1)
            self.assertTrue((self.tmp / g.id / "game.json").exists(), "now it is a game"); self.assertFalse((self.tmp / "drafts" / g.id).exists(), "and no longer a draft")
            self.assertEqual([m["id"] for m in game.list_games()], [g.id]); self.assertEqual(game.list_drafts(), [])
            first = next(e for e in g.transcript if e["kind"] == "world"); self.assertTrue(first["text"].startswith(narration), "the World's opening line is the first of the chronicle")
            self.assertEqual(g.seats, seats, "the seats are the draft's")
            fixed = ("name", "trade", "home", "personality", "secret", "fear", "want", "voice", "traits", "str", "spd", "hp_max", "gold", "duties", "pastime", "goal", "skills")
            for n, c in before.items():
                self.assertIn(n, w.characters, n)
                for k in fixed: self.assertEqual(w.characters[n].get(k), c.get(k), f"{n}.{k} changed at Start")
            for a in rels:
                for b in rels[a]: self.assertEqual((w.rel(a, b)["type"], w.rel(a, b)["feeling"], w.rel(a, b)["trust"]), (rels[a][b]["type"], rels[a][b]["feeling"], rels[a][b]["trust"]), f"{a} to {b}")
            wait_for(lambda: g.status in ("done", "stopped"), 240, "the one day year")
            self.assertEqual(g.status, "done"); self.assertTrue(any(e["kind"] == "morning" for e in g.transcript))
        finally: r.stop()
        self.assertEqual(r.reroll_person(list(w.characters)[0]), "this is a game, not a draft"); self.assertEqual(r.add_person(), "this is a game, not a draft")

    def test_a_draft_survives_a_server_restart_and_delete_discards_it(self) -> None:
        self.stub_models(); g = self.app.run.g; w = g.world; self.generate(); gid = g.id
        first = list(w.characters)[0]; self.app.edit_character({"name": first, "fear": "the dark of the mere"})
        people = copy.deepcopy(w.characters)
        again = server.App()
        try:
            self.assertEqual(again.run.g.id, gid, "the draft is what comes back"); self.assertTrue(again.run.g.draft)
            self.assertEqual(again.run.g.world.characters, people, "where it was, edits included"); self.assertEqual(again.run.g.draft_narration, g.draft_narration)
            self.assertEqual(len(again.run.g.seats), 4)
            again.delete_game(gid)
            self.assertEqual(again.run.g.world.characters, {}, "the people are gone with it"); self.assertTrue(again.run.g.draft, "with nothing left, a fresh draft"); self.assertEqual(game.list_games(), [])
        finally:
            for r in list(again.runs.values()): r.stop()

    def test_the_old_way_still_works_for_a_game_without_a_draft(self) -> None:
        """A game.json saved by an older version is a game, not a draft, and Start still rolls it inside the run."""
        g = game.Game(engine.now_id()); g.players = 2; g.max_days = 1; g.drama = 0
        g.world_model = {"provider": "Stub", "model": "stub"}; g.model_a = {"provider": "Stub", "model": "stub"}; g.model_b = {"provider": "Stub", "model": "stub"}; g.repo = str(self.tmp); g.save()
        self.assertFalse(g.draft); self.assertTrue((self.tmp / g.id / "game.json").exists())
        self.app.open_game(g.id); r = self.app.run; self.assertIs(r.g.id, g.id) if False else self.assertEqual(r.g.id, g.id)
        connect.record_probe("Stub", "stub", True); self.app.start_game(); self.assertEqual(self.app.start_error, "")
        try:
            wait_for(lambda: r.g.world.created, 90, "the world"); self.assertEqual(len(r.g.world.characters), 2)
            wait_for(lambda: r.g.status in ("done", "stopped"), 240, "the year")
        finally: r.stop()


if __name__ == "__main__":
    unittest.main()
