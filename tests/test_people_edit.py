"""Editing a person from the character screen. Skills are the new part; the rest guards what was already there.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import random, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import connect, engine, game, server  # noqa: E402


class PeopleEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-people-"))
        engine.GAMES = self.tmp; game.GAMES = self.tmp; server.GAMES = self.tmp
        self._start, self._vers = connect.start, server.refresh_versions
        connect.start = lambda: None            # no CLI probing and no npm lookups inside a test
        server.refresh_versions = lambda: None
        self.app = server.App()
        g = self.app.run.g; w = g.world; rng = random.Random(7)
        for i, n in enumerate(("Bett", "Osgar")):
            w.characters[n] = engine.roll_character(n, i + 1, rng, list(w.map))
        g.seats = [{"name": "World", "provider": "Claude Code", "model": "claude-fable-5-1", "color": "#FFFFFF"},
                   {"name": "Bett", "provider": "Claude Code", "model": "claude-haiku-4-5", "color": "#22D3EE"},
                   {"name": "Osgar", "provider": "Claude Code", "model": "claude-haiku-4-5", "color": "#F59E0B"}]
        self.app.run._reset_terms() if hasattr(self.app.run, "_reset_terms") else self.app.run._sync_terms()
        g.save()

    def tearDown(self) -> None:
        connect.start, server.refresh_versions = self._start, self._vers
        shutil.rmtree(self.tmp, ignore_errors=True)

    def me(self) -> dict:
        return self.app.run.g.world.characters["Bett"]

    def test_skills_are_set_cleaned_and_clamped(self) -> None:
        note = self.app.edit_character({"name": "Bett", "skills": {"  Axe  ": 3, "READING": "2", "smithing": 40, "": 5, "bad": "x"}})
        self.assertEqual(self.me()["skills"], {"axe": 3, "reading": 2, "smithing": 9},
                         "names are tidied and lowered, levels are clamped, and nonsense is dropped")
        self.assertIn("skills", note)

    def test_a_skill_set_to_zero_is_taken_away(self) -> None:
        self.app.edit_character({"name": "Bett", "skills": {"axe": 3, "reading": 2}})
        self.app.edit_character({"name": "Bett", "skills": {"axe": 0, "reading": 2}})
        self.assertEqual(self.me()["skills"], {"reading": 2})

    def test_skills_are_recorded_as_fate_and_left_alone_when_unchanged(self) -> None:
        self.app.edit_character({"name": "Bett", "skills": {"axe": 1}})
        fate = [e for e in self.app.run.g.transcript if e["kind"] == "fate"]
        self.assertTrue(fate and "skills" in fate[-1]["text"], "a skill change is fate the World must narrate")
        before = len(self.app.run.g.transcript)
        self.assertEqual(self.app.edit_character({"name": "Bett", "skills": {"axe": 1}}), "no change")
        self.assertEqual(len(self.app.run.g.transcript), before, "saving the same skills again changes nothing")

    def test_the_rest_of_the_screen_still_saves(self) -> None:
        self.app.edit_character({"name": "Bett", "trade": "eel catcher", "home": "The mill", "str": 8, "gold": 12,
                                 "standing": "feared", "traits": {"drink": 5}, "want": "a dry roof"})
        c = self.me()
        self.assertEqual((c["trade"], c["home"], c["str"], c["gold"], c["standing"]), ("eel catcher", "The mill", 8, 12, "feared"))
        self.assertEqual(c["traits"]["drink"], 5)
        self.assertEqual(c["want"], "a dry roof")
        self.assertTrue(c.get("changed"), "a changed life makes them play the new self")

    def test_a_tie_can_be_set_both_ways(self) -> None:
        self.app.edit_relation({"a": "Bett", "b": "Osgar", "type": "rival", "feeling": -4, "trust": -2, "mutual": True})
        w = self.app.run.g.world
        self.assertEqual((w.rel("Bett", "Osgar")["type"], w.rel("Bett", "Osgar")["feeling"]), ("rival", -4))
        self.assertEqual((w.rel("Osgar", "Bett")["type"], w.rel("Osgar", "Bett")["trust"]), ("rival", -2))


if __name__ == "__main__":
    unittest.main()
