"""The UI pass. Season rules per source and the plain sentence; the region the World sheet shows; the map locked once a game has
started; the Situations sheet gone; one type scale and one spacing unit in the stylesheet, no dotted leaders.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, re, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402

CSS = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")


class Seasons(unittest.TestCase):
    def test_rules_per_source(self) -> None:
        r = engine.season_rules(22, "clear")
        self.assertEqual(r["fields"], ("dormant", 0.0)); self.assertEqual(r["fish"][0], "reduced"); self.assertEqual(r["game"][0], "reduced"); self.assertEqual(r["forage"][0], "low"); self.assertEqual(r["wood"], ("normal", 1.0))
        self.assertEqual(engine.season_rules(3, "clear")["fields"], ("yield", 1.0)); self.assertEqual(engine.season_rules(3, "snow")["fields"][0], "dormant", "snow stops the fields in any season")
        self.assertEqual(engine.season_rules(30, "clear")["fields"][0], "sowing")

    def test_the_sentence(self) -> None:
        self.assertEqual(engine.season_sentence(22, "clear"), "Day 22. Deep winter, clear. Fields are dormant until spring; hunting and fishing are reduced; forage is low; wood still yields.")
        self.assertEqual(engine.season_sentence(3, "clear"), "Day 3. Autumn, clear. Fields yield; hunting, fishing, foraging and wood still yield.")
        self.assertNotIn("nothing grows", engine.season_sentence(22, "snow"))

    def test_the_rules_reach_the_work(self) -> None:
        w = engine.World(); rng = random.Random(1); places = list(w.map)
        for i in range(2): w.characters[f"P{i}"] = engine.roll_character(f"P{i}", i + 1, rng, places)
        w.ledger = engine.starting_ledger(2, len(w.map)); w.seed_places(); w.created = True
        c = w.characters["P0"]; c["skills"] = {"hunting": 9, "fishing": 9, "woodcutting": 9}
        def made(day: int, key: str, store: str) -> int:
            w.day = day; w.weather = "clear"; total = 0
            for i in range(20): w.ledger["tools"] = 9; c["needs"] = {"food": 8, "warmth": 8, "rest": 8, "spirit": 6}; total += w.do_duty("P0", key, random.Random(i))["made"].get(store, 0)
            return total
        self.assertLess(made(22, "hunt", "meat"), made(3, "hunt", "meat")); self.assertLess(made(22, "fish", "fish"), made(3, "fish", "fish"))
        self.assertEqual(made(22, "wood", "wood"), made(3, "wood", "wood"))
        w.day = 22; c["skills"]["farming"] = 9; self.assertIn("dormant", w.do_duty("P0", "fields", random.Random(1))["text"])

    def test_tomorrow_and_the_region(self) -> None:
        ch = engine.weather_chances(23); self.assertEqual(sum(p for _, p in ch), 100); self.assertIn(("snow", 40), ch)
        self.assertEqual([a["name"] for a in engine.REGION], ["The lord's lands", "The next valley", "The forest road", "The market town"])
        for a in engine.REGION: self.assertTrue(a["offers"] and a["threatens"])


class Sheets(unittest.TestCase):
    def test_the_situations_sheet_and_button_are_gone(self) -> None:
        self.assertNotIn('data-sheet="situations"', HTML); self.assertNotIn('id="sheet-situations"', HTML); self.assertNotIn("renderSituations", JS); self.assertNotIn("['situations','Situations']", JS)

    def test_people_has_six_tabs_and_a_body_tab(self) -> None:
        tabs = re.findall(r'<div class="ptabs">(.*?)</div>', HTML)[0]
        self.assertEqual(re.findall(r'data-p="(\w+)"', tabs), ["bio", "body", "disp", "ties", "duties", "log"])
        self.assertIn("function paneBody", JS); self.assertNotIn("function paneHealth", JS); self.assertNotIn("function paneStats", JS)
        self.assertIn('class="needbars"', JS); self.assertNotIn("Where they stand", JS)

    def test_the_bio_is_one_form_with_four_textareas(self) -> None:
        bio = JS[JS.index("function paneBio"):JS.index("// ---- Body")]
        self.assertEqual(bio.count("<textarea"), 4); self.assertEqual(bio.count('rows="3"'), 4); self.assertIn('id="b_pastime"', bio); self.assertIn('<div class="row end">', bio)
        self.assertLess(bio.index("<textarea"), bio.index('id="b_save"'))

    def test_the_world_sheet_is_the_region_and_the_map_is_locked_once_started(self) -> None:
        self.assertIn('id="g_region"', HTML); self.assertIn("function renderRegion", JS); self.assertIn("The season calendar", JS); self.assertIn("The lands around", JS); self.assertIn("Tomorrow:", JS)
        self.assertIn("$('g_mapBlock').style.display=started?'none':''", JS)
        import connect, game, server
        tmp = Path(tempfile.mkdtemp(prefix="terra-ui-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; g.seats = [{"name": "World", "provider": "Claude Code", "model": "", "color": "#d0a92c"}, {"name": "Bett", "provider": "Claude Code", "model": "", "color": "#7f9a5c"}]
            app.edit_game({"map_source": "generated"}); self.assertEqual(g.map_source, "builtin", "a started game keeps its map")
            snap = app.snapshot()
            for k in ("region", "calendar", "season_days", "tomorrow", "sentence"): self.assertIn(k, snap)
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)

    def test_the_colony_header_is_the_sentence(self) -> None:
        self.assertIn('class="colsent"', JS); self.assertNotIn("nothing grows", JS); self.assertNotIn('class="colseason"', JS)


class Stylesheet(unittest.TestCase):
    def test_three_type_sizes_and_the_serif(self) -> None:
        sizes = set(re.findall(r"font-size:\s*([^;}]+)", CSS)); self.assertEqual(sizes, {"var(--fs-h)", "var(--fs-b)", "var(--fs-s)"})
        self.assertEqual(re.findall(r"font:[^;{}]*?(\d+(?:\.\d+)?)px", CSS), [], "a font shorthand carries a pixel size")
        self.assertIn("Georgia", CSS)

    def test_one_spacing_unit(self) -> None:
        stray = re.findall(r"(?:margin|padding|gap)(?:-\w+)?:[^;{}]*?(?<![\w.])([2-9]|[1-9]\d)px", CSS)
        self.assertEqual(stray, [], f"spacing not on the unit: {stray}")
        self.assertIn("--u:8px", CSS)

    def test_no_dotted_leaders_and_one_sheet_width(self) -> None:
        self.assertNotIn("dotted", CSS); self.assertNotIn(".dots", CSS); self.assertNotIn('class="dots"', JS)
        self.assertIn(".sheetwrap .panel{width:min(900px,100%)", CSS); self.assertIn(".panel.wide{width:min(900px,100%)}", CSS)
        self.assertNotIn(".fatecard", CSS); self.assertNotIn('class="fatecard"', HTML)

    def test_accent_only_where_selected(self) -> None:
        self.assertIn(".dial.sel{outline:1px solid var(--accent)", CSS); self.assertIn(".tie.sel{outline:1px solid var(--accent)", CSS)
        self.assertIn(".tie .seg button.on{background:var(--moss)", CSS); self.assertIn(".tie .seg button.on.neg{background:var(--rust)", CSS)
        self.assertNotIn(".seg button.on{background:var(--accent)", CSS)


if __name__ == "__main__":
    unittest.main()
