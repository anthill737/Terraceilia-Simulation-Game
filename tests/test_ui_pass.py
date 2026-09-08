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

    def test_tomorrow(self) -> None:
        ch = engine.weather_chances(23); self.assertEqual(sum(p for _, p in ch), 100); self.assertIn(("snow", 40), ch)

    def test_the_calendar_rows_are_plain(self) -> None:
        self.assertEqual(engine.season_row("deep winter"), "Deep winter, days 15 to 24: fields dormant, hunting and fishing halved, forage low, wood normal.")
        self.assertEqual(engine.season_row("autumn"), "Autumn, days 1 to 6: fields yield, hunting and fishing normal, forage good, wood normal.")
        self.assertEqual(engine.season_row("thaw"), "Thaw, from day 25: fields sown at half, hunting and fishing normal, forage low, wood normal.")
        for _, name in engine.SEASONS: self.assertNotIn(":", engine.season_row(name).split(":", 1)[1]); self.assertNotIn("\u00b7", engine.season_row(name))

    def test_nothing_backs_the_lands_around_so_it_is_gone(self) -> None:
        self.assertFalse(hasattr(engine, "REGION")); self.assertFalse((ROOT / "data" / "region.json").exists())
        for text in (JS, HTML, CSS, (ROOT / "README.md").read_text(encoding="utf-8")): self.assertNotIn("lands around", text)
        self.assertNotIn("s.region", JS); self.assertNotIn("offers", JS); self.assertNotIn("threatens", JS)


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
        self.assertIn('id="g_region"', HTML); self.assertIn("function renderRegion", JS); self.assertIn("The season calendar", JS)
        region = JS[JS.index("function renderRegion"):JS.index("regionHtml=html")]
        self.assertIn("s.world_text", region); self.assertIn("s.sentence", region)
        for tok in ("Tomorrow", "s.tomorrow", "d.kind", "KIND", "map_style", "st.water", "st.sky", "map_generated", "elevation", "feature"): self.assertNotIn(tok, region)
        self.assertIn("s.calendar_rows", JS); self.assertNotIn("seasonRow", JS)
        self.assertIn("$('g_mapBlock').style.display=started?'none':''", JS); self.assertIn("$('g_descBlock').style.display=started?'none':''", JS); self.assertIn('id="g_descBlock"', HTML)
        save = JS[JS.index("async function saveWorld"):JS.index("function renderRegion")]
        self.assertIn("if(!started){d.world_text=$('g_world').value", save); self.assertNotIn("world_text:$('g_world')", save)
        import connect, game, server
        tmp = Path(tempfile.mkdtemp(prefix="terra-ui-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; g.seats = [{"name": "World", "provider": "Claude Code", "model": "", "color": "#d0a92c"}, {"name": "Bett", "provider": "Claude Code", "model": "", "color": "#7f9a5c"}]
            app.edit_game({"map_source": "generated"}); self.assertEqual(g.map_source, "builtin", "a started game keeps its map")
            g.world.created = True; app.edit_game({"world_text": "changed after the start"}); self.assertNotEqual(g.world_text, "changed after the start", "the description is fixed once the world is made")
            g.world.created = False; app.edit_game({"world_text": "changed before the start"}); self.assertEqual(g.world_text, "changed before the start")
            snap = app.snapshot()
            for k in ("calendar_rows", "sentence"): self.assertIn(k, snap)
            for k in ("region", "calendar", "season_days", "tomorrow"): self.assertNotIn(k, snap)
            self.assertEqual(snap["calendar_rows"][2], engine.season_row("deep winter"))
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)

    def test_the_person_header_is_one_line(self) -> None:
        head = JS[JS.index("$('peoHead').innerHTML=`"):JS.index("`;", JS.index("$('peoHead').innerHTML=`"))]
        self.assertIn('<span class="nm">', head); self.assertIn('<i class="ttl">', head); self.assertIn("showTrade", head); self.assertIn("'the '+trade", head)
        for tok in ("seat.provider", "seat.model", "class=\"note\"", "<b"): self.assertNotIn(tok, head)
        self.assertIn("wants ${esc(g.text)}, ${wp[0]}%", head, "the want shows in the header line only")
        bio = JS[JS.index("function paneBio"):JS.index("// ---- Body")]
        for tok in ("In plain terms", "wbar", "want_progress"): self.assertNotIn(tok, bio)
        self.assertIn('id="b_reroll"', bio); self.assertNotIn(".wbar", CSS)
        self.assertIn("title.replace(/^the /,'').toLowerCase()===trade.replace(/^the /,'').toLowerCase()", JS, "the trade is dropped when it equals the title")
        self.assertIn("white-space:nowrap", CSS[CSS.index("#peoHead{"):CSS.index("}", CSS.index("#peoHead{"))])
        bio = JS[JS.index("function paneBio"):JS.index("// ---- Body")]; self.assertIn('id="b_prov"', bio); self.assertIn('id="b_model"', bio)

    def test_colony_tables_have_headers_plain_status_and_no_truncation(self) -> None:
        col = JS[JS.index("function renderColony"):JS.index("document.querySelectorAll('.sheetclose')")]
        self.assertIn("thead(['Job','Where','Who','Today'])", col); self.assertIn("thead(['Good','Have','Change'])", col); self.assertIn("thead(['Place','Roof','Warmth','Filth'])", col)
        self.assertEqual(col.count('<table class="ctab">'), 3)
        for word in ("'done','good'", "['not done today','poor']", "`open for ${since} day${since>1?'s':''}`,'poor'", "`${esc(dumped)} is covering it today`,'poor'", "'nothing to do','quiet'"): self.assertIn(word, col)
        self.assertIn("' (covering)'", col, "the Who column carries the full name and (covering) after it"); self.assertNotIn("' (dumped)'", col); self.assertNotIn("undone ${", col); self.assertNotIn("dumped on ${esc(r.dumped_on)}</span>", col)
        self.assertIn("${label}: ${names.length} of ${living.length}.", col, "hungry, freezing and sick are counts"); self.assertIn("title=\"${esc(names.join(', '))}\"", col, "with the names on hover")
        self.assertNotIn("Hungry: ${R.hungry.map(esc).join(', ')}", col)
        self.assertIn("${v} ${chg(d[k])}", col, "each place number carries today's change beside it")
        tab = CSS[CSS.index(".ctab{"):CSS.index("@media (max-width:820px)", CSS.index(".ctab{"))] if CSS.index("@media (max-width:820px)", CSS.index(".ctab{")) > 0 else CSS[CSS.index(".ctab{"):]
        self.assertNotIn("ellipsis", tab); self.assertNotIn("overflow:hidden", tab); self.assertIn("white-space:nowrap", tab); self.assertIn("height:calc(var(--u) * 4)", tab)
        self.assertNotIn(".crow", CSS)
        self.assertIn(".hgrid{display:flex;flex-wrap:wrap", CSS, "the cards sit beside each other while they fit and wrap when the sheet is narrower")
        phone = CSS[CSS.rindex("@media (max-width:820px)"):]; self.assertIn(".colsent{white-space:normal}", phone); self.assertIn(".ctab td,.ctab th{white-space:normal", phone)
        self.assertIn(".colsent{font-size:var(--fs-b);color:var(--ink);margin:0 0 calc(var(--u) / 2);white-space:nowrap}", CSS)

    def test_the_new_words_everywhere_and_the_old_ones_nowhere(self) -> None:
        """Jobs, relationships, covering and open in every user-facing place; dump, unclaimed and ties in none. Data keys stay."""
        import prompts
        self.assertIn('<button data-p="ties">Relationships</button><button data-p="duties">Jobs</button>', HTML); self.assertIn("Today's Jobs", HTML)
        self.assertNotIn(">Ties<", HTML); self.assertNotIn(">Duties<", HTML); self.assertNotIn("Today's duties", HTML)
        jobs = JS[JS.index("function paneDuties"):JS.index("// ---- Log")]
        self.assertIn("Covering today:", jobs); self.assertIn("'open'+(since?` for ${since} day", jobs); self.assertIn("A job nobody holds is covered each morning", jobs)
        self.assertIn("${em.place&&!String(em.text||'').includes(em.place)?' at '+esc(em.place):''}", jobs, "the emergency prints its place once")
        for old in ("Dumped on", "dumped on", "nobody holds it", "undone '+", "Tick a duty", "kind of tie", "No duties yet"): self.assertNotIn(old, JS)
        for text in (prompts.PLAYER_RULES, prompts.WORLD_RULES):
            for old in ("dump", "unclaimed", "duty", "duties", " ties", "a tie "): self.assertNotIn(old, text.lower(), old)
        flat = " ".join(prompts.PLAYER_RULES.split()); self.assertIn("you are covering the hunt today because nobody has it", flat); self.assertIn("named jobs", flat)
        w = engine.World(); rng = random.Random(1); places = list(w.map)
        for i in range(3): w.characters[f"P{i}"] = engine.roll_character(f"P{i}", i + 1, rng, places)
        w.ledger = engine.starting_ledger(3, len(w.map)); w.seed_places(); w.created = True; w.day = 1; w.seed_duties(rng)
        for c in w.living(): c["duties"] = []
        w.characters["P0"]["duties"] = ["mill"]; w.assign_day(rng)
        covering = [c for c in w.living() if c.get("dumped")][0]
        self.assertTrue(any(x["text"].startswith("You are covering ") and x["text"].endswith("because nobody has it; you were nearest.") for x in covering["log"]))
        self.assertIn("(you are covering it today because nobody has it)", w.duty_brief(covering["name"])); self.assertNotIn("dump", w.duty_brief(covering["name"]).lower())
        self.assertIn("is covering it today", w.duties_text()); self.assertNotIn("UNCLAIMED", w.duties_text()); self.assertNotIn("dumped", w.duties_text())
        self.assertIn("; it is open", w.refuse_duty("P0", "mill")); self.assertIn("jobs are now", w.set_duties("P0", ["mill"]))
        self.assertIn("no relationships worth the name", w.relations_text("P0")); self.assertIn('"YOUR JOBS: "', (ROOT / "backend" / "game.py").read_text(encoding="utf-8"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for old in ("dumped", "unclaimed", "### duties", "duties tab", "web of ties"): self.assertNotIn(old, readme, old)

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

    def test_one_weight_for_body_text(self) -> None:
        weights = set(re.findall(r"font-weight:\s*(\d+)", CSS)) | set(re.findall(r"font:\s*(\d+) ", CSS))
        self.assertEqual(weights, {"400", "600"}, f"weights in use: {weights}")
        bold = [m for m in re.findall(r"([^{}]*)\{[^{}]*font-weight:\s*600", CSS)]
        self.assertEqual(len(bold), 1, "one rule carries the bold weight")
        self.assertEqual(set(x.strip() for x in bold[0].split(",")), {".chip .cn", ".ch", "h1", ".sheetwrap .panel h1", ".logday", ".place", ".railhdr", "header .brand"})
        self.assertIn("b,strong{font-weight:400}", CSS)

    def test_italics_only_for_the_earned_title_and_no_highlight(self) -> None:
        italic = re.findall(r"([^{}]*)\{[^{}]*font-style:\s*italic", CSS) + re.findall(r"([^{}]*)\{[^{}]*font:\s*italic", CSS)
        self.assertEqual([x.strip() for x in italic], ["#peoHead .ttl"], f"italic rules: {italic}")
        self.assertIn("i,em{font-style:normal}", CSS)
        act = CSS[CSS.index(".act{"):CSS.index("}", CSS.index(".act{"))]; self.assertNotIn("background", act)
        self.assertNotIn("<mark", JS); self.assertNotIn("<mark", HTML); self.assertNotIn("mark{", CSS)

    def test_accent_only_where_selected(self) -> None:
        self.assertIn(".dial.sel{outline:1px solid var(--accent)", CSS); self.assertIn(".tie.sel{outline:1px solid var(--accent)", CSS)
        self.assertIn(".tie .seg button.on{background:var(--moss)", CSS); self.assertIn(".tie .seg button.on.neg{background:var(--rust)", CSS)
        self.assertNotIn(".seg button.on{background:var(--accent)", CSS)


if __name__ == "__main__":
    unittest.main()
