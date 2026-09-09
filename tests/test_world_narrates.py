"""The World invents nothing. Every free action is read into one of fourteen verbs and settled by the engine; the World is given
the outcomes and nothing else, tells them, and any name, number, item or place it adds is dropped and logged.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import copy, json, os, random, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine, game, prompts  # noqa: E402


def valley(n: int = 5, seed: int = 21) -> engine.World:
    w = engine.World(); rng = random.Random(seed); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard", "healer"][i % 5]
        c["location"] = c["home"] = places[0]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 2; w.phase = "afternoon"; w.seed_duties(rng); w.seed_wants(rng); w.seed_pastimes(rng)
    for a in w.characters:
        for b in w.characters:
            if a != b: w.rel(a, b)
    return w


def snapshot(w: engine.World) -> str:
    d = w.to_dict(); d.pop("activities", None)
    return json.dumps(d, sort_keys=True)


class ParseTests(unittest.TestCase):
    def test_every_verb_is_read_from_plain_words(self) -> None:
        w = valley(); inn = next(p for p, d in w.map.items() if d.get("kind") == "inn")
        cases = {"I walk to the inn": ("travel", None, inn), "I go home": ("travel", None, w.characters["P0"]["home"]), "I give P1 two gold": ("give", "P1", None),
                 "I take some grain from the stores": ("take", None, None), "I steal from P2 while he sleeps": ("steal", "P2", None), "I hit P3 in the mouth": ("hit", "P3", None),
                 "I drive P1 out of the valley": ("drive out", "P1", None), "I help P4 with the nets": ("help", "P4", None), "I tend P2's fever": ("tend", "P2", None),
                 "I kiss P1 behind the mill": ("court", "P1", None), "I pray for the harvest": ("pray", None, None), "I sell my spoon at the market": ("trade", None, None),
                 "I search the grain loft for coin": ("search", None, None), "I wait and see": ("wait", None, None), "I tell P1 what I think of her": ("talk", "P1", None),
                 "I sing to the goats": ("talk", None, None)}
        for text, (verb, target, place) in cases.items():
            pv = w.parse_verb("P0", text)
            self.assertEqual(pv["verb"], verb, f"{text!r} read as {pv['verb']}"); self.assertEqual(pv["target"], target, text)
            if place: self.assertEqual(pv["place"], place, text)
        self.assertEqual(w.parse_verb("P0", "I give P1 two gold")["n"], 2); self.assertEqual(w.parse_verb("P0", "I take some grain")["item"], "grain")
        self.assertEqual(set(engine.World.VERBS), {"travel", "talk", "give", "take", "steal", "hit", "drive out", "help", "tend", "court", "pray", "trade", "search", "wait"})


class ResolveTests(unittest.TestCase):
    def test_an_unparsed_action_is_talk_and_changes_nothing(self) -> None:
        w = valley(); before = snapshot(w); log: list[str] = []
        out = w.resolve_afternoon([{"who": "P0", "text": "I sing to the goats about the old days", "turn": 1}, {"who": "P1", "text": "I tell P2 what I think of him", "turn": 2}], random.Random(1), log)
        self.assertEqual([o["kind"] for o in out], ["talk", "talk"]); self.assertTrue(all(not o["changed"] for o in out))
        self.assertEqual(snapshot(w), before, "talk moved state")

    def test_travel_moves_one_path_and_no_further(self) -> None:
        w = valley(); c = w.characters["P0"]; here = c["location"]; far = max(w.map, key=lambda p: w.distance(here, p)); near = w.map[here]["adj"][0]
        r = w.resolve_verb("P0", w.parse_verb("P0", f"I walk to {near}"), random.Random(1)); self.assertTrue(r["ok"]); self.assertEqual(c["location"], near)
        c["location"] = here; r = w.resolve_verb("P0", w.parse_verb("P0", f"I go to {far}"), random.Random(1)); self.assertIn("more than a day's walk", r["text"]); self.assertEqual(c["location"], w._path(here, far)[1])

    def test_give_take_steal_and_hit_are_settled_by_stats_ties_and_dice(self) -> None:
        w = valley(); a, b = w.characters["P0"], w.characters["P1"]; a["gold"] = 5; b["gold"] = 2
        r = w.resolve_verb("P0", w.parse_verb("P0", "I give P1 three gold"), random.Random(1)); self.assertTrue(r["ok"]); self.assertEqual((a["gold"], b["gold"]), (2, 5)); self.assertGreater(w.rel("P1", "P0")["feeling"], 0)
        g0 = w.ledger["grain"]; r = w.resolve_verb("P0", w.parse_verb("P0", "I take a sack of grain from the stores"), random.Random(1)); self.assertEqual(w.ledger["grain"], g0 - 1); self.assertIn("saw it", r["text"])
        a["traits"]["cunning"] = 5; b["traits"]["cunning"] = 1; a["gold"] = 0; b["gold"] = 4
        wins = sum(1 for i in range(20) if w.resolve_verb("P0", w.parse_verb("P0", "I steal from P1"), random.Random(i))["ok"] for _ in [b.__setitem__("gold", 4)]); self.assertGreater(wins, 10)
        a["traits"]["cunning"] = 1; b["traits"]["cunning"] = 5; s0 = a["standing_score"]
        losses = sum(1 for i in range(20) if not w.resolve_verb("P0", w.parse_verb("P0", "I steal from P1"), random.Random(i))["ok"]); self.assertGreater(losses, 10); self.assertLess(a["standing_score"], s0)
        a["str"] = 9; b["str"] = 2; b["hp"] = b["hp_max"] = 20
        r = w.resolve_verb("P0", w.parse_verb("P0", "I hit P1"), random.Random(3)); self.assertTrue(r["changed"]); self.assertLess(b["hp"], 20); self.assertLess(w.rel("P1", "P0")["feeling"], 0)
        b["hp"] = 1; r = w.resolve_verb("P0", w.parse_verb("P0", "I hit P1 again"), random.Random(3)); self.assertFalse(b["alive"]); self.assertIn("P1", w.bodies); self.assertIn("dead", r["text"])

    def test_help_tend_court_pray_trade_search_wait(self) -> None:
        w = valley(); rng = random.Random(4); a, b = w.characters["P0"], w.characters["P1"]
        b["needs"]["rest"] = 1; w.resolve_verb("P0", w.parse_verb("P0", "I help P1 carry water"), rng); self.assertEqual(b["needs"]["rest"], 3); self.assertGreater(w.rel("P1", "P0")["feeling"], 0)
        b["sick"] = True; w.ledger["herbs"] = 2; r = w.resolve_verb("P0", w.parse_verb("P0", "I tend P1"), rng); self.assertEqual(b["tended_day"], w.day); self.assertEqual(w.ledger["herbs"], 1); self.assertIn("used herbs", r["text"])
        a["traits"]["desire"] = 5; a["traits"]["tongue"] = 5; b["traits"]["desire"] = 5; w.set_rel("P1", "P0", feeling=2)
        r = w.resolve_verb("P0", w.parse_verb("P0", "I court P1"), random.Random(1)); self.assertTrue(r["changed"]); self.assertIn("court", r["text"])
        sp = a["needs"]["spirit"]; w.resolve_verb("P0", w.parse_verb("P0", "I pray"), rng); self.assertGreater(a["needs"]["spirit"], sp)
        a["location"] = next(p for p, d in w.map.items() if d.get("kind") in ("market", "town")); a["gold"] = 1; m0 = w.ledger["meals"]
        r = w.resolve_verb("P0", w.parse_verb("P0", "I buy bread"), rng); self.assertEqual((a["gold"], w.ledger["meals"]), (0, m0 + 2))
        found = [w.resolve_verb("P0", w.parse_verb("P0", "I search the loft"), random.Random(i))["ok"] for i in range(30)]; self.assertIn(True, found); self.assertIn(False, found)
        a["needs"]["rest"] = 4; w.resolve_verb("P0", w.parse_verb("P0", "I wait"), rng); self.assertEqual(a["needs"]["rest"], 5)

    def test_a_target_elsewhere_or_dead_changes_nothing(self) -> None:
        w = valley(); b = w.characters["P1"]; b["location"] = [p for p in w.map if p != w.characters["P0"]["location"]][0]; before = snapshot(w)
        r = w.resolve_verb("P0", w.parse_verb("P0", "I hit P1"), random.Random(1)); self.assertFalse(r["changed"]); self.assertIn("was at", r["text"]); self.assertEqual(snapshot(w), before)


class WorldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-world-")); engine.GAMES = self.tmp; game.GAMES = self.tmp
        g = game.Game(engine.now_id()); g.world = valley(); self.w = g.world
        g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in self.w.characters]
        self.r = game.Run(g)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_prompt_carries_outcomes_and_no_state(self) -> None:
        w = self.w; a = w.characters["P0"]; a["gold"] = 7; a["skills"]["milling"] = 4
        outs = [{"kind": "give", "who": "P0", "text": "P0 gave P1 2 gold."}]
        p = self.r._world_prompt(outs)
        self.assertIn("P0 gave P1 2 gold.", p); self.assertIn("You decide nothing", p)
        for bad in ("STR ", "HP ", "Paths lead to", "The stores:", "THE DUTIES", "->", "What was said", "```", "STANDINGS", "roof ", "filth", "skills", "gold 7", "milling", "wants "):
            self.assertNotIn(bad, p, f"state leaked into the World's prompt: {bad!r}")
        self.assertNotIn(prompts.MAP_RULES[:40], p)

    def test_invented_names_numbers_items_and_places_are_dropped_and_logged(self) -> None:
        w = self.w; outs = [{"kind": "give", "who": "P0", "text": "P0 gave P1 2 gold."}, {"kind": "travel", "who": "P2", "text": f"P2 walked to {list(w.map)[1]}."}]
        text = ("P0: He handed P1 2 gold and said nothing.\n"
                "P2: She walked to " + list(w.map)[1] + " in the rain.\n"
                "P3: He watched from the door.\n"
                "P0: He also slipped P1 5 gold under the table.\n"
                "P1: She spent it on herbs at " + list(w.map)[3] + ".\n"
                "A stranger named Ozymandias rode in.")
        kept, dropped = w.check_narration(text, outs)
        self.assertIn("handed P1 2 gold", kept); self.assertIn("in the rain", kept)
        for gone in ("P3", "5 gold", "herbs", "Ozymandias", list(w.map)[3]): self.assertNotIn(gone, kept, gone)
        self.assertEqual(len(dropped), 4); self.assertTrue(all("not in any outcome" in d for d in dropped))

    def test_the_world_phase_writes_state_only_through_the_engine(self) -> None:
        w = self.w; r = self.r; g = r.g; a, b = w.characters["P0"], w.characters["P1"]; a["gold"] = 5; b["gold"] = 0; g.drama = 0
        w.pending = [{"who": "P0", "text": "I give P1 one gold", "turn": 1}, {"who": "P2", "text": "I hum a tune nobody knows", "turn": 2}]
        r._invoke = lambda i, prompt, label, **k: "P0: He gave P1 1 gold.\nP2: He hummed.\nP4: Meanwhile P4 found 30 gold in the river."   # the World tries to invent
        before_p4 = w.characters["P4"]["gold"]
        r._world_phase()
        self.assertEqual((a["gold"], b["gold"]), (4, 1)); self.assertEqual(w.characters["P4"]["gold"], before_p4, "the World's invention moved nothing")
        world = next(e for e in g.transcript if e["kind"] == "world"); self.assertIn("gave P1 1 gold", world["text"]); self.assertNotIn("30 gold", world["text"])
        eng = next(e for e in g.transcript if e["kind"] == "system" and e["text"].startswith("Adjustments")); self.assertIn("dropped", eng["text"]); self.assertIn("P4", eng["text"])

    def test_with_no_narration_the_engine_lines_stand(self) -> None:
        w = self.w; r = self.r; g = r.g; g.drama = 0; w.pending = [{"who": "P0", "text": "I pray", "turn": 1}]
        r._invoke = lambda i, prompt, label, **k: None
        r._world_phase(); world = next(e for e in g.transcript if e["kind"] == "world"); self.assertIn("P0 prayed", world["text"])


if __name__ == "__main__":
    unittest.main()
