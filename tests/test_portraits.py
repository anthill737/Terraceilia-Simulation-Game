"""Faces. Every person carries one, drawn from their own data and their own seed: the same person always has the same
face, and the face moves only when they do. backend/portrait.py settles the features and frontend/face.js draws them.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import json, os, random, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine, portrait  # noqa: E402

JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
MAPJS = (ROOT / "frontend" / "map.js").read_text(encoding="utf-8")
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def person(**over) -> dict:
    c = engine.roll_character("Bett", 1, random.Random(3))
    c.update(over); return c


class TheSameFaceEveryTime(unittest.TestCase):
    def test_a_person_has_one_face_and_keeps_it(self) -> None:
        c = person()
        face = portrait.face_of(c, "#d0a92c")
        for _ in range(20): self.assertEqual(portrait.face_of(c, "#d0a92c"), face)
        again = json.loads(json.dumps(c))                      # through a save and back
        self.assertEqual(portrait.face_of(again, "#d0a92c"), face)

    def test_two_people_do_not_share_a_face(self) -> None:
        rng = random.Random(9)
        faces = [json.dumps(portrait.face_of(engine.roll_character(f"P{i}", i, rng), "#d0a92c"), sort_keys=True) for i in range(40)]
        self.assertGreater(len(set(faces)), 30, "forty people should not keep coming out with the same face")

    def test_a_face_seed_is_all_it_takes(self) -> None:
        """Everything the seed settles is settled by the seed alone: a different name on the same seed is the same face."""
        drawn = ("shape", "skin", "hair", "eyes", "eyecol", "nose", "mouth", "brow", "ears", "beard")
        a = person(face_seed=1234); b = person(face_seed=1234, name="Osgar", seat=7)
        for k in drawn: self.assertEqual(portrait.face_of(a)[k], portrait.face_of(b)[k], k)
        seeds = [tuple(portrait.face_of(person(face_seed=n))[k] for k in drawn) for n in (1234, 99, 500001, 7)]
        self.assertEqual(len(set(seeds)), 4, "four seeds, four faces")


class WhatTheFaceCarries(unittest.TestCase):
    def test_the_hat_comes_from_the_trade(self) -> None:
        self.assertEqual(portrait.face_of(person(trade="nun"))["hat"], "veil")
        self.assertEqual(portrait.face_of(person(trade="guard"))["hat"], "helm")
        self.assertEqual(portrait.face_of(person(trade="the miller"))["hat"], "cap", "a trade with a word in front is still that trade")
        self.assertEqual(portrait.face_of(person(trade="star pilot"))["hat"], "none", "a trade nobody has heard of goes bare headed")
        self.assertEqual(portrait.face_of(person(trade=""))["hat"], "none")
        for t in engine.TRADE_NAMES: self.assertIn(portrait.hat_for(t), portrait.HATS, t)

    def test_the_clothes_are_the_seat_colour(self) -> None:
        self.assertEqual(portrait.face_of(person(), "#7f9a5c")["cloth"], "#7f9a5c")
        self.assertEqual(portrait.face_of(person())["cloth"], portrait.CLOTH, "a person with no seat still wears something")

    def test_the_years_the_wound_the_hunger_and_the_strength(self) -> None:
        self.assertEqual([portrait.face_of(person(age=a))["lines"] for a in (18, 33, 50, 70)], [0, 1, 2, 3])
        grey = lambda h: min(abs(int(h[i:i + 2], 16) - 190) for i in (1, 3, 5))
        self.assertGreater(grey(portrait.face_of(person(age=20))["haircol"]), grey(portrait.face_of(person(age=75))["haircol"]), "hair greys with the years")
        self.assertEqual([portrait.face_of(person(hp=h, hp_max=12))["pale"] for h in (12, 6, 1)], [0, 1, 2])
        self.assertEqual(portrait.face_of(person(alive=False))["dead"], True)
        self.assertEqual(portrait.face_of(person(needs={"food": 2}))["thin"], 1)
        self.assertEqual(portrait.face_of(person(needs={"food": 8}))["thin"], 0)
        self.assertEqual(portrait.face_of(person(str=9))["scar"], 1)
        self.assertEqual(portrait.face_of(person(str=4))["scar"], 0)

    def test_the_face_moves_when_health_or_age_moves_and_not_otherwise(self) -> None:
        c = person(age=30, hp=12, hp_max=12); face = portrait.face_of(c, "#d0a92c")
        c["gold"] = 99; c["standing"] = "loved"; c["duties"] = ["mill"]
        self.assertEqual(portrait.face_of(c, "#d0a92c"), face, "gold and standing are not written on a face")
        c["hp"] = 2; hurt = portrait.face_of(c, "#d0a92c")
        self.assertNotEqual(hurt, face); self.assertEqual(hurt["shape"], face["shape"], "and they are still themselves")
        c["hp"] = 12; c["age"] = 70
        self.assertNotEqual(portrait.face_of(c, "#d0a92c"), face)
        c["age"] = 30
        self.assertEqual(portrait.face_of(c, "#d0a92c"), face, "well and no older, the face comes back to what it was")

    def test_every_field_is_something_the_drawing_understands(self) -> None:
        rng = random.Random(4)
        for i in range(60):
            f = portrait.face_of(engine.roll_character(f"P{i}", i, rng), "#d0a92c")
            self.assertIn(f["shape"], portrait.SHAPES); self.assertIn(f["hair"], portrait.HAIRS); self.assertIn(f["eyes"], portrait.EYES)
            self.assertIn(f["beard"], portrait.BEARDS); self.assertIn(f["hat"], portrait.HATS); self.assertIn(f["skin"], portrait.SKINS)
            self.assertTrue(re.fullmatch(r"#[0-9a-f]{6}", f["haircol"])); self.assertIn(f["lines"], (0, 1, 2, 3))


class TheDrawing(unittest.TestCase):
    def test_face_js_is_a_pure_function_of_the_spec(self) -> None:
        if not shutil.which("node"): self.skipTest("node is not installed here")
        r = subprocess.run(["node", str(ROOT / "tests" / "face_check.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("ALL PASS", r.stdout)

    def test_the_page_draws_them_at_the_three_sizes(self) -> None:
        self.assertIn('<script src="face.js">', HTML, "the drawing half is loaded before the app")
        self.assertLess(HTML.index('src="face.js"'), HTML.index('src="app.js"'))
        self.assertIn("portrait(c.name,60)", JS, "60 across on a card in the strip")
        self.assertIn("portrait(c.name,160)", JS, "160 in Bio and in the editor")
        self.assertEqual(JS.count("portrait(c.name,160)"), 2)
        self.assertIn("transform:'translate(-10,-19) scale(0.2)'", MAPJS, "20 by 20 on a map token, where the initial used to be")
        self.assertIn("Face.markup(face,{head:true,plate:false})", MAPJS)
        self.assertNotIn(".ini", MAPJS); self.assertNotIn(".ini", (ROOT / "frontend" / "style.css").read_text(encoding="utf-8"))
        self.assertIn("t._faceKey===key", MAPJS, "a token repaints its face only when the person behind it changed")

    def test_every_face_reaches_the_page(self) -> None:
        import connect, game, server
        tmp = Path(tempfile.mkdtemp(prefix="terra-face-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); r = app.run; g = r.g; g.players = 4
            r._build_people(77); g.world.assign_homes(r.rng); g.world.created = True
            snap = app.snapshot(); state = app.map_state()
            for c in g.world.characters.values():
                colour = next(x["color"] for x in g.seats if x["name"] == c["name"])
                self.assertEqual(snap["faces"][c["name"]], portrait.face_of(c, colour))
                self.assertEqual(state["faces"][c["name"]], portrait.face_of(c, colour), "the map's own state carries them too")
            for k in ("trade_list", "tag_list", "tie_words"): self.assertTrue(snap[k], k)
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
