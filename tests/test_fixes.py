"""Four fixes: old saves seeded once with a chronicle line, one palette in the stylesheet, thin scrollbars, and situations that
are never rolled twice, expire by themselves, are capped at six, and can be settled by a duty.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import json, os, random, re, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests"))
import engine, game  # noqa: E402
from engine import DUTIES, EVENTS  # noqa: E402
from test_no_court import OLD_KEY  # noqa: E402


def old_save() -> dict:
    """A game.json as the game wrote it before duties, pastimes, wants, needs or the new ledger existed."""
    w = engine.World(); rng = random.Random(1); places = list(w.map); chars = {}
    for i, n in enumerate(("Bett", "Osgar", "Maud")):
        chars[n] = {"name": n, "seat": i + 1, "str": 5, "spd": 5, "hp": 10, "hp_max": 10, "gold": 3, "skills": {}, "location": places[i], "standing": "unknown",
                    "alive": True, OLD_KEY: False, "trade": ["miller", "hunter", "cook"][i], "home": places[i], "personality": "x", "secret": "x", "fear": "x", "want": "a dry roof",
                    "cause_of_death": "", "traits": engine.roll_traits(rng)}
    return {"title": "Old", "created": "2026-08-01T10:00", "world_text": "x", "players": 3, "max_days": 12, "seats": [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#d0a92c"}] +
            [{"name": n, "provider": "Claude Code", "model": "x", "color": "#7f9a5c"} for n in chars], "transcript": [], "turn": 0, "status": "paused",
            "world": {"characters": chars, "day": 4, "ledger": {"grain_weeks": 9, "grain_needed": 16, "roofs_broken": 3, "road_safe": False, "sick": 0, "built": []}, "created": True, "court_every": 6}}


class OldSaves(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-old-")); engine.GAMES = self.tmp; game.GAMES = self.tmp
        d = self.tmp / "oldgame"; d.mkdir(); (d / "game.json").write_text(json.dumps(old_save()), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_loaded_game_is_seeded_once_as_a_new_game_would_be_with_a_chronicle_line(self) -> None:
        g = game.Game.load("oldgame"); r = game.Run(g); w = g.world
        for c in w.living():
            self.assertTrue(1 <= len(c["duties"]) <= engine.MAX_DUTIES, c["name"]); self.assertIn(c["pastime"], engine.PASTIMES); self.assertTrue(c["goal"])
            self.assertIn("spirit", c["needs"]); self.assertEqual(c["standing"], "nobody")
        for k in engine.STORES: self.assertIn(k, w.ledger)
        self.assertTrue(all(p in w.upkeep for p in w.map))
        self.assertGreaterEqual(sum(len(c["duties"]) for c in w.living()), 3 * 1)   # three people cannot hold fifteen duties; each holds their share
        notes = [e for e in g.transcript if e["kind"] == "system" and "saved before the colony rules changed" in e["text"]]
        self.assertEqual(len(notes), 1); self.assertIn("jobs", notes[0]["text"]); self.assertNotIn("duties", notes[0]["text"]); self.assertIn("the ledger", notes[0]["text"])
        # loading it again seeds nothing and says nothing
        g2 = game.Game.load("oldgame"); game.Run(g2)
        self.assertEqual(len([e for e in g2.transcript if "saved before the colony rules changed" in e["text"]]), 1)
        self.assertEqual({c["name"]: c["duties"] for c in g2.world.living()}, {c["name"]: c["duties"] for c in w.living()})
        del r

    def test_a_new_game_is_not_touched(self) -> None:
        g = game.Game(engine.now_id()); game.Run(g); self.assertEqual(g.transcript, [])


class Palette(unittest.TestCase):
    CSS = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")

    def test_the_stylesheet_uses_seven_colours_and_nothing_else(self) -> None:
        root = re.search(r":root\{(.*?)--r-ctl", self.CSS, re.S).group(1)
        base = {m.group(1).lower() for m in re.finditer(r"--(?:bg|panel|ink|muted|accent|moss|rust):(#[0-9a-fA-F]{6})", root)}
        self.assertEqual(len(base), 7)
        used = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", self.CSS)}
        self.assertEqual(used - base, set(), "stray colours in the stylesheet")
        self.assertNotIn("rgb(", self.CSS); self.assertNotIn("rgba(", self.CSS); self.assertNotIn("hsl(", self.CSS)
        for word in ("blue", "cyan", "navy", "teal"): self.assertNotIn(word, self.CSS.lower())

    def test_the_page_and_the_app_carry_no_colours_of_their_own(self) -> None:
        for f in ("index.html", "app.js"):
            t = (ROOT / "frontend" / f).read_text(encoding="utf-8")
            hexes = [h for h in re.findall(r"#[0-9a-fA-F]{6}\b", t) if h.lower() not in ("#1c1915", "#7f9a5c", "#d0a92c")]   # the favicon is drawn in the palette
            self.assertEqual(hexes, [], f"{f} carries colours of its own")
            self.assertNotIn("rgba(", t)

    def test_chronicle_cards_share_one_border_and_engine_notes_are_muted_text(self) -> None:
        self.assertRegex(self.CSS, r"\.msg\{margin:[^;]+;padding:[^;]+;border-radius:var\(--r-card\);background:var\(--panel\);border:1px solid var\(--line\)\}")
        self.assertNotIn(".msg.world{", self.CSS); self.assertNotIn(".msg.fate{", self.CSS)
        self.assertIn(".msg .who:before{content:\"\";width:8px;height:8px;border-radius:50%;background:var(--c,var(--faint))", self.CSS)
        self.assertIn(".msg.system{background:transparent;border:0", self.CSS); self.assertIn(".msg.system .body{color:var(--muted)", self.CSS)

    def test_scrollbars_are_thin_and_the_strip_hides_its_own(self) -> None:
        self.assertIn("scrollbar-width:thin;scrollbar-color:var(--edge) transparent", self.CSS)
        self.assertRegex(self.CSS, r"#peoStrip\{display:flex;gap:[^;]+;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:none")
        self.assertIn("#peoStrip::-webkit-scrollbar{display:none}", self.CSS); self.assertIn(".peoWrap:hover .stripbar{opacity:1}", self.CSS)
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8"); self.assertIn('<div class="peoWrap"><div id="peoStrip"></div><div class="stripbar"><i></i></div></div>', html)
        js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"); self.assertIn("strip.addEventListener('pointerdown'", js); self.assertIn("strip.addEventListener('scroll',paint)", js)

    def test_the_colony_sheet_uses_moss_for_held_and_rust_for_unfilled(self) -> None:
        self.assertIn(".colduty .cdw{color:var(--moss)}", self.CSS); self.assertIn(".colduty.un .cdw,.colduty .cdw .poor{color:var(--rust)", self.CSS)

    def test_seat_colours_are_warm(self) -> None:
        for h in game.PALETTE:
            r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16); self.assertLess(b, max(r, g) + 1, f"{h} leans blue")


def valley(n: int = 6) -> engine.World:
    w = engine.World(); rng = random.Random(9); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard", "healer", "smith"][i % 6]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1; w.seed_duties(rng)
    return w


class Situations(unittest.TestCase):
    def test_every_situation_event_has_days_and_fixers(self) -> None:
        for e in EVENTS:
            if e.get("thread"): self.assertGreaterEqual(int(e["days"]), 1, e["t"]); self.assertIsInstance(e["fixed_by"], list, e["t"])
        bell = next(e for e in EVENTS if "bell cracks" in e["t"]); self.assertIn("trade", bell["fixed_by"])

    def test_an_open_event_is_never_rolled_again(self) -> None:
        w = valley(); old = engine.EVENTS; engine.EVENTS = [{"t": "The chapel bell cracks in the cold and will not ring again without a smith.", "tier": 1, "thread": True, "days": 5, "fixed_by": ["trade"]}]
        try:
            for i in range(30): w.draw_events(10, random.Random(i), [])
        finally: engine.EVENTS = old
        self.assertEqual(len(w.open_threads()), 1, "the same event was opened more than once while open")

    def test_open_situations_are_capped_at_six(self) -> None:
        w = valley(); old = engine.EVENTS
        engine.EVENTS = [{"t": f"Trouble number {i} at {{place}}.", "tier": 1, "thread": True, "days": 9, "fixed_by": []} for i in range(20)]
        try:
            log: list[str] = []
            for i in range(60): w.draw_events(10, random.Random(i), log)
        finally: engine.EVENTS = old
        self.assertEqual(len(w.open_threads()), 6); self.assertTrue(any("six situations" in x for x in log))

    def test_situations_expire_by_themselves_with_a_line(self) -> None:
        w = valley(); t = w.open_thread("A comet hangs over the castle.", None, [], days=2, key="comet")
        self.assertEqual(t["expires"], 3)
        w.day = 2; self.assertEqual(w.expire_threads(), []); w.day = 3; lines = w.expire_threads()
        self.assertEqual(len(lines), 1); self.assertIn(f"Situation #{t['id']} ended by itself", lines[0]); self.assertEqual(t["status"], "resolved"); self.assertEqual(t["note"], "it passed on its own")
        w2 = valley(); w2.open_thread("Rats in the loft.", None, [], days=1, key="rats"); w2.day = 2; w2.dawn(random.Random(1))
        self.assertTrue(any("ended by itself" in ln for ln in w2.day_report["lines"]), "the dawn lines carry the expiry")

    def test_a_duty_settles_the_situation_it_can_fix(self) -> None:
        w = valley(); chapel = next(p for p, d in w.map.items() if d.get("kind") == "chapel")
        t = w.open_thread("The chapel bell cracks in the cold and will not ring again without a smith.", chapel, [], days=9, key="bell", fixed_by=["trade", "roofs"])
        c = w.characters["P5"]; c["skills"]["haggling"] = 9; c["location"] = chapel; w.ledger["grain"] = 9
        r = w.do_duty("P5", "trade", random.Random(2))
        self.assertEqual(t["status"], "resolved"); self.assertIn("P5 saw to it", t["note"]); self.assertIn(f"settled situation #{t['id']}", r["text"])
        t2 = w.open_thread("Rats in the loft.", None, [], days=9, key="rats", fixed_by=["stores"]); c["skills"]["keeping"] = 9
        w.do_duty("P5", "stores", random.Random(3)); self.assertEqual(t2["status"], "resolved", "a situation with no place is settled from anywhere")
        t3 = w.open_thread("Wolves.", None, [], days=9, key="wolves", fixed_by=["hunt"]); w.do_duty("P5", "stores", random.Random(3)); self.assertEqual(t3["status"], "open", "the wrong duty settles nothing")

    def test_fires_are_settled_by_putting_them_out_not_by_the_calendar(self) -> None:
        w = valley(); p = list(w.map)[0]; w.ignite(p); t = w.open_threads()[-1]; self.assertEqual(t["fixed_by"], ["fire"])
        w.extinguish(p); self.assertEqual(t["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
