"""Social actions instead of chatter: the catalog, the roll that mostly comes up empty, the pick by dials and feeling, the
weight that gathers and steps feeling at ten, the optional line, the way of speaking, and the drama dial that touches events only.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, re, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine, game  # noqa: E402
from engine import SOCIAL  # noqa: E402


def valley(n: int = 4, place: str | None = None, seed: int = 3) -> engine.World:
    w = engine.World(); rng = random.Random(seed); places = list(w.map); place = place or places[0]
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["location"] = c["home"] = place; c["trade"] = "villager"
        c["traits"] = {t: 3 for t in engine.TRAITS}; c["needs"]["spirit"] = 6; c["voice"] = engine.roll_voice(c, rng); w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1
    w.seed_duties(rng); w.seed_pastimes(rng)
    for c in w.characters.values(): c["goal"] = {"kind": "gold", "target": 20, "text": "to have 20 gold put by"}   # a want that turns on nobody
    return w


def run_for(w: engine.World, tmp: Path) -> game.Run:
    engine.GAMES = tmp; game.GAMES = tmp
    g = game.Game(engine.now_id()); g.world = w
    g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
    r = game.Run(g); r.rng = random.Random(7); return r


class Catalog(unittest.TestCase):
    def test_about_twenty_acts_each_fully_described(self) -> None:
        first = [a for a in SOCIAL.values() if not a.get("reaction")]
        self.assertGreaterEqual(len(first), 20); self.assertGreaterEqual(len(SOCIAL) - len(first), 5, "the reactions are in the same catalog")
        for a in SOCIAL.values():
            for k in ("key", "label", "feeling", "trust", "self_feeling", "self_trust", "base", "targets", "dials", "needs", "sentence", "line", "ask", "reactions"): self.assertIn(k, a, a["key"])
            self.assertIn(a["targets"], ("anyone", "liked", "disliked", "owes", "wronged")); self.assertIn("{a}", a["sentence"])
            for rk in a["reactions"]: self.assertIn(rk, SOCIAL, f"{a['key']} reacts with {rk}")
            self.assertTrue(all(d in engine.TRAITS for d in a["dials"]), a["key"])
            if a["line"]: self.assertIn("{b}", a["ask"] + "{b}")
        self.assertEqual((SOCIAL["small_talk"]["feeling"], SOCIAL["compliment"]["feeling"], SOCIAL["share_food"]["feeling"], SOCIAL["gift"]["feeling"]), (1, 2, 3, 4))
        self.assertEqual((SOCIAL["insult"]["feeling"], SOCIAL["threaten"]["feeling"], SOCIAL["shove"]["feeling"]), (-4, -6, -8))
        for k in ("insult", "threaten", "shove"): self.assertTrue(SOCIAL[k]["escalation"]); self.assertLessEqual(SOCIAL[k]["base"], 1); self.assertGreaterEqual(SOCIAL[k]["needs"]["temper_min"], 4); self.assertLessEqual(SOCIAL[k]["needs"]["feeling_max"], -2)
        self.assertFalse(SOCIAL["share_food"]["line"]); self.assertFalse(SOCIAL["shove"]["line"]); self.assertTrue(SOCIAL["insult"]["line"])
        self.assertTrue((ROOT / "data" / "social.json").exists(), "an editable file")


class Beats(unittest.TestCase):
    def test_most_beats_produce_no_social_act(self) -> None:
        w = valley(); rng = random.Random(1); knot = ["P0", "P1", "P2", "P3"]; acts = 0; beats = 400
        for _ in range(beats): acts += len([e for e in w.social_beat(w.characters["P0"]["location"], knot, rng) if e["reaction_to"] is None])
        rate = acts / (beats * 4)
        self.assertLess(rate, 0.12, f"ordinary people act on {rate:.0%} of beats; most beats should be empty")
        self.assertGreater(acts, 0, "but not never")
        w2 = valley(); rng = random.Random(2); one = [e for e in w2.social_beat(w2.characters["P0"]["location"], knot, rng)]
        self.assertLessEqual(len([e for e in one if e["reaction_to"] is None]), 4)

    def test_the_action_chosen_matches_dials_and_feeling(self) -> None:
        w = valley(); rng = random.Random(3); knot = ["P0", "P1"]
        w.characters["P0"]["traits"].update(warmth=5, tongue=5, temper=1); w.set_rel("P0", "P1", feeling=4, trust=3)
        picks = [w.pick_action("P0", "P1", rng, knot)["key"] for _ in range(300)]
        self.assertGreaterEqual(len([k for k in picks if SOCIAL[k]["feeling"] >= 0]), 285, f"a warm friend picks kind acts almost always: {set(picks)}")
        self.assertIn("compliment", picks); self.assertNotIn("insult", picks); self.assertNotIn("shove", picks)
        w.characters["P0"]["traits"].update(warmth=1, tongue=3, temper=5, drink=5); w.set_rel("P0", "P1", feeling=-4, trust=-3)
        picks = [w.pick_action("P0", "P1", rng, knot)["key"] for _ in range(300)]
        self.assertGreaterEqual(len([k for k in picks if SOCIAL[k]["feeling"] <= 0]), 270, f"a hot enemy picks hard acts almost always: {set(picks)}")
        self.assertTrue({"insult", "threaten", "shove"} & set(picks), set(picks)); self.assertNotIn("compliment", picks); self.assertNotIn("gift", picks)
        hard = len([k for k in picks if k in ("insult", "threaten", "shove")]); self.assertLess(hard, 200, "escalation is weighted low even for a hot enemy")
        w.characters["P0"]["traits"].update(temper=3); w.set_rel("P0", "P1", feeling=-4)
        picks = [w.pick_action("P0", "P1", rng, knot)["key"] for _ in range(200)]
        self.assertFalse({"insult", "threaten", "shove"} & set(picks), "no escalation without a hot temper")
        self.assertIsNone(w.pick_action("P0", "P1", rng, knot, pool=["gift"]), "a gift needs liking")

    def test_an_act_with_no_line_still_applies_weight_and_reaches_the_chronicle(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-noline-"))
        try:
            w = valley(2); r = run_for(w, tmp); g = r.g
            w.characters["P0"]["traits"].update(warmth=5); w.set_rel("P0", "P1", feeling=2); w.ledger["meals"] = 3
            asked: list = []
            r.ask = lambda i, prompt, label, provider=None, model=None: (asked.append((i, prompt)), None)[1]
            w.social_beat = lambda place, knot, rng, touched=None: [w.do_social("P0", "P1", SOCIAL["share_food"], rng, knot), w.do_social("P0", "P1", SOCIAL["compliment"], rng, knot)]
            ran = r._talk_round("evening")
            self.assertEqual(ran[0]["acts"], ["share_food", "compliment"])
            self.assertEqual(w.ledger["meals"], 2, "the bread came out of the stores")
            self.assertEqual(w.social_pair("P1", "P0")["fw"], 5, "3 for the bread and 2 for the compliment"); self.assertEqual(w.rel("P1", "P0")["feeling"], 0, "no step yet")
            entries = [e for e in g.transcript if e["kind"] == "social"]
            self.assertEqual([e["text"] for e in entries], ["P0 shared bread with P1.", "P0 paid P1 a compliment."], "the compliment's line came back empty and the act still stands")
            self.assertEqual(entries[0]["heard"], ["P1"]); self.assertEqual(entries[0]["place"], w.characters["P0"]["location"])
            self.assertEqual(len(asked), 1, "only the compliment asked for a line"); self.assertIn("Pay P1 a compliment", asked[0][1]); self.assertIn("One sentence.", asked[0][1])
            self.assertEqual(w.social_log[-1]["line"], "")
        finally: shutil.rmtree(tmp, ignore_errors=True)

    def test_a_usable_line_goes_under_the_sentence_and_a_bad_one_is_dropped(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-line-"))
        try:
            w = valley(2); r = run_for(w, tmp); g = r.g
            answers = iter(['P0: "You mend a roof better than the carpenter ever did, and everyone knows it."\nACTION: I nod.', "PASS", "```json\n{}\n```"])
            r.ask = lambda i, prompt, label, provider=None, model=None: next(answers)
            w.social_beat = lambda place, knot, rng, touched=None: [w.do_social("P0", "P1", SOCIAL["compliment"], rng, knot), w.do_social("P1", "P0", SOCIAL["thank"], rng, knot, reaction_to=0), w.do_social("P0", "P1", SOCIAL["joke"], rng, knot)]
            r._talk_round("after work")
            entries = [e for e in g.transcript if e["kind"] == "social"]
            self.assertEqual(entries[0]["text"], 'P0 paid P1 a compliment.\n"You mend a roof better than the carpenter ever did, and everyone knows it."')
            self.assertEqual(entries[1]["text"], "P1 thanked P0."); self.assertEqual(entries[2]["text"], "P0 told P1 a joke.")
            self.assertEqual(game.clean_line("Well now. That is a fine roof."), "Well now."); self.assertIsNone(game.clean_line("")); self.assertIsNone(game.clean_line("ACTION: I go."))
        finally: shutil.rmtree(tmp, ignore_errors=True)


class Weight(unittest.TestCase):
    def test_feeling_moves_only_when_the_total_crosses_ten_and_at_most_one_step_a_day(self) -> None:
        w = valley(2); rng = random.Random(1); knot = ["P0", "P1"]; w.set_rel("P0", "P1", feeling=0, trust=0); w.set_rel("P1", "P0", feeling=0, trust=0)
        for n in range(4):
            w.do_social("P0", "P1", SOCIAL["compliment"], rng, knot)
            self.assertEqual(w.rel("P1", "P0")["feeling"], 0, f"after {n + 1} compliments")
        self.assertEqual(w.social_pair("P1", "P0")["fw"], 8)
        w.do_social("P0", "P1", SOCIAL["compliment"], rng, knot)
        self.assertEqual(w.rel("P1", "P0")["feeling"], 1, "five compliments move feeling one step"); self.assertEqual(w.social_pair("P1", "P0")["fw"], 0, "and the total resets")
        for _ in range(6): w.do_social("P0", "P1", SOCIAL["compliment"], rng, knot)
        self.assertEqual(w.rel("P1", "P0")["feeling"], 1, "at most one step a day per pair, whatever the total")
        w.day += 1; w.do_social("P0", "P1", SOCIAL["small_talk"], rng, knot)
        self.assertEqual(w.rel("P1", "P0")["feeling"], 2, "the next day the gathered weight steps once more")
        w2 = valley(2); w2.characters["P0"]["traits"].update(temper=5); w2.set_rel("P0", "P1", feeling=-3); w2.set_rel("P1", "P0", feeling=3, trust=2)
        w2.do_social("P0", "P1", SOCIAL["insult"], rng, knot); self.assertEqual(w2.rel("P1", "P0")["feeling"], 3, "one insult is 4 of 10")
        w2.do_social("P0", "P1", SOCIAL["shove"], random.Random(5), knot); self.assertEqual(w2.rel("P1", "P0")["feeling"], 2, "an insult and a shove move it one step the other way")
        self.assertEqual(w2.rel("P1", "P0")["trust"], 2, "trust keeps its own total: 1 and 3 is 4 of 10")
        w3 = valley(2); w3.set_rel("P1", "P0", feeling=-4); w3.set_rel("P0", "P1", feeling=4); w3.characters["P0"]["gold"] = 40; w3.characters["P0"]["traits"].update(warmth=5)
        days = 0
        while w3.rel("P1", "P0")["feeling"] < 1 and days < 40:
            w3.day += 1; days += 1; w3.do_social("P0", "P1", SOCIAL["gift"], rng, knot); w3.do_social("P0", "P1", SOCIAL["gift"], rng, knot)
        self.assertGreaterEqual(days, 5, "despise to warm cannot happen in under five days of daily kind acts, and takes two weeks at a gift a day")

    def test_talk_alone_never_moves_feeling(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-talk-"))
        try:
            w = valley(2); r = run_for(w, tmp); before = {(a, b): (w.rel(a, b)["feeling"], w.rel(a, b)["trust"], w.social_pair(a, b)["fw"]) for a in ("P0", "P1") for b in ("P0", "P1") if a != b}
            r._say(1, "P1, you are a thief and a liar and I love you anyway.\nACTION: I wait.")
            r._record("P1", "And you a fool.", "speech")
            pv = w.parse_verb("P0", "I talk to P1 about the roof"); self.assertEqual(pv["verb"], "talk"); w.resolve_verb("P0", pv, random.Random(1))
            after = {(a, b): (w.rel(a, b)["feeling"], w.rel(a, b)["trust"], w.social_pair(a, b)["fw"]) for a in ("P0", "P1") for b in ("P0", "P1") if a != b}
            self.assertEqual(before, after, "words are words; only acts carry weight")
        finally: shutil.rmtree(tmp, ignore_errors=True)


class Escalation(unittest.TestCase):
    def test_escalation_costs_standing_with_witnesses_unless_the_target_had_it_coming(self) -> None:
        w = valley(3); rng = random.Random(1); knot = ["P0", "P1", "P2"]; w.characters["P0"]["traits"].update(temper=5); w.set_rel("P0", "P1", feeling=-4)
        s0 = w.characters["P0"]["standing_score"]
        e = w.do_social("P0", "P1", SOCIAL["insult"], rng, knot)
        self.assertEqual(w.characters["P0"]["standing_score"], s0 - 1); self.assertIn("standing fell", e["cost"]); self.assertEqual(w.social_pair("P2", "P0")["fw"], -2, "the witness thinks less of them")
        w2 = valley(3); w2.characters["P1"]["traits"].update(temper=5); w2.set_rel("P1", "P0", feeling=-4); w2.characters["P0"]["traits"].update(temper=5); w2.set_rel("P0", "P1", feeling=-4)
        w2.do_social("P1", "P0", SOCIAL["slight"], rng, knot); s0 = w2.characters["P0"]["standing_score"]
        e = w2.do_social("P0", "P1", SOCIAL["insult"], rng, knot)
        self.assertEqual(w2.characters["P0"]["standing_score"], s0, "P1 had it coming"); self.assertEqual(e["cost"], "")

    def test_a_shove_can_start_a_fight_settled_by_dice_and_health(self) -> None:
        w = valley(2); knot = ["P0", "P1"]; w.characters["P0"]["traits"].update(temper=5); w.characters["P1"]["traits"].update(temper=5); w.set_rel("P0", "P1", feeling=-4)
        fights = [w.do_social("P0", "P1", SOCIAL["shove"], random.Random(seed), knot)["fight"] for seed in range(30)]
        self.assertTrue(any(fights), "sometimes it comes to blows"); self.assertFalse(all(fights), "not always")
        hp = sorted((w.characters["P0"]["hp"], w.characters["P1"]["hp"])); self.assertLess(hp[0], max(w.characters["P0"]["hp_max"], w.characters["P1"]["hp_max"]), "somebody got hurt")
        self.assertGreaterEqual(min(w.characters["P0"]["hp"], w.characters["P1"]["hp"]), 1, "a brawl does not kill")
        self.assertTrue(any("came to blows" in f for f in fights if f))


class Voice(unittest.TestCase):
    def test_every_person_gets_a_fixed_way_of_speaking_and_it_is_in_every_line_prompt(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-voice-"))
        try:
            w = valley(2); c = w.characters["P0"]; v = c["voice"]
            self.assertIn(v["length"], engine.VOICE_LENGTHS); self.assertTrue(v["habit"]); self.assertEqual(len(v["examples"]), 3); self.assertTrue(v["never"])
            r = run_for(w, tmp); e = w.do_social("P0", "P1", SOCIAL["compliment"], random.Random(1), ["P0", "P1"])
            lp = r._line_prompt("P0", e)
            for bit in ("HOW YOU TALK", v["habit"], v["examples"][0], v["never"], "Pay P1 a compliment", "One sentence", "How you feel: you"): self.assertIn(bit, lp)
            self.assertIn(v["habit"], r._player_prompt(1, "speak"), "and in every ordinary prompt")
            good = engine.clean_voice({"length": "Clipped", "habit": "says aye", "examples": ["Aye.", "No.", "Later."], "never": "the lord"}, c, random.Random(1))
            self.assertEqual(good, {"length": "clipped", "habit": "says aye", "examples": ["Aye.", "No.", "Later."], "never": "the lord"})
            bad = engine.clean_voice({"length": "long", "examples": ["one"]}, c, random.Random(1)); self.assertIn(bad["length"], engine.VOICE_LENGTHS); self.assertEqual(len(bad["examples"]), 3)
            self.assertIn('"voice":{"length":"clipped or plain or rambling"', (ROOT / "backend" / "game.py").read_text(encoding="utf-8"), "the World is asked for it at creation")
        finally: shutil.rmtree(tmp, ignore_errors=True)

    def test_fate_edits_the_voice_under_bio_and_an_old_save_is_given_one(self) -> None:
        import connect, server
        tmp = Path(tempfile.mkdtemp(prefix="terra-vedit-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; g.world = valley(2); w = g.world; del w.characters["P0"]["voice"]
            self.assertIn("ways of speaking", w.needs_seeding()); w.seed_missing(random.Random(1)); self.assertTrue(w.characters["P0"]["voice"])
            note = app.edit_character({"name": "P0", "voice": {"length": "rambling", "habit": "counts on their fingers", "examples": ["One.", "Two, and then.", "Three, I said."], "never": "the ford"}})
            self.assertIn("way of talking changed", note); self.assertEqual(w.characters["P0"]["voice"]["habit"], "counts on their fingers")
            self.assertEqual(app.snapshot()["characters"][0]["voice"]["length"], "rambling")
            js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"); self.assertIn("How they talk", js); self.assertIn("b_vhabit", js); self.assertIn("voice:{length:$('b_vlen').value", js)
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)


class Drama(unittest.TestCase):
    def test_the_drama_dial_changes_event_counts_and_nothing_else(self) -> None:
        def count(drama: int) -> int:
            n = 0
            for seed in range(120):
                w = valley(6, seed=seed); w.threads = []; n += len(w.draw_events(drama, random.Random(seed), []))
            return n
        zero, low, high = count(0), count(3), count(10)
        self.assertEqual(zero, 0); self.assertGreater(low, 0); self.assertGreater(high, low * 1.5)
        src = (ROOT / "backend" / "engine.py").read_text(encoding="utf-8")
        chunks = re.split(r"\n    def |\ndef ", src)
        users = [c.split("(")[0] for c in chunks if "drama" in c]
        self.assertEqual(users, ["draw_events"], f"only draw_events reads the dial in the engine: {users}")
        gsrc = (ROOT / "backend" / "game.py").read_text(encoding="utf-8")
        for ln in gsrc.split("\n"):
            if "drama" in ln: self.assertTrue(re.search(r"self\.drama|g\.drama|\"drama\"|Drama:", ln) and ("draw_events" in ln or "d.get" in ln or "to_dict" in ln or "self.drama" in ln or "Drama:" in ln), ln)
        self.assertNotIn("drama", " ".join(re.findall(r"def social_\w+\(.*?\)", src)) + " ".join(re.findall(r"def pick_action\(.*?\)", src)))
        w = valley(4); a = [e["key"] for e in w.social_beat(w.characters["P0"]["location"], ["P0", "P1", "P2", "P3"], random.Random(9))]
        self.assertEqual(a, [e["key"] for e in valley(4).social_beat(w.characters["P0"]["location"], ["P0", "P1", "P2", "P3"], random.Random(9))], "social beats take no dial at all")


if __name__ == "__main__":
    unittest.main()
