"""Duties: the valley's work in named pieces. Seeded from trade and nature, one to three each; unclaimed ones dumped daily on the
nearest able person; emergencies pull whoever is nearest; refusing costs standing; work is resolved by the engine.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402
from engine import DUTIES, MAX_DUTIES  # noqa: E402

TRADES = ["miller", "hunter", "fisherwoman", "carpenter", "priest", "innkeeper", "guard", "farmer", "healer", "merchant",
          "servant", "woodcutter", "cook", "clerk", "shepherd", "gravedigger", "smith", "alewife", "tanner", "weaver"]


def valley(n: int = 20, seed: int = 2) -> engine.World:
    w = engine.World(); rng = random.Random(seed); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = TRADES[i % len(TRADES)]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1
    return w


class DataTests(unittest.TestCase):
    def test_about_fifteen_duties_each_fully_described(self) -> None:
        self.assertGreaterEqual(len(DUTIES), 14); self.assertLessEqual(len(DUTIES), 16)
        for k in ("mill", "fields", "hunt", "fish", "wood", "roofs", "stores", "healing", "kitchen", "watch", "burial", "cleaning", "trade", "teaching", "fire"): self.assertIn(k, DUTIES)
        for k, d in DUTIES.items():
            for f in ("label", "verb", "where", "skill", "consumes", "produces", "breaks", "aliases", "seed"): self.assertIn(f, d, f"{k} lacks {f}")
            self.assertTrue(d["produces"] or d.get("effect"), f"{k} makes nothing and changes nothing")


class SeedTests(unittest.TestCase):
    def test_everyone_holds_one_to_three_and_every_duty_is_held(self) -> None:
        w = valley(); w.seed_duties(random.Random(1))
        for c in w.living(): self.assertTrue(1 <= len(c["duties"]) <= MAX_DUTIES, f"{c['name']} holds {c['duties']}")
        for k in DUTIES: self.assertTrue(w.holders(k), f"{k} has no holder among twenty people")

    def test_trade_seeds_the_duty(self) -> None:
        w = valley(); w.seed_duties(random.Random(1))
        self.assertIn("mill", w.characters["P0"]["duties"]); self.assertIn("hunt", w.characters["P1"]["duties"]); self.assertIn("fish", w.characters["P2"]["duties"])
        self.assertIn("healing", w.characters["P8"]["duties"])

    def test_a_small_valley_still_gives_everyone_work(self) -> None:
        w = valley(n=3); w.seed_duties(random.Random(1))
        for c in w.living(): self.assertTrue(1 <= len(c["duties"]) <= MAX_DUTIES)


class AssignTests(unittest.TestCase):
    def test_an_open_job_is_covered_by_the_nearest_able_free_person_and_they_are_told(self) -> None:
        w = valley(n=3); w.seed_duties(random.Random(1))
        for c in w.living(): c["duties"] = []
        w.characters["P0"]["duties"] = ["stores"]; w.characters["P1"]["duties"] = ["stores"]; w.characters["P2"]["duties"] = ["stores"]
        mill = w.duty_place("mill"); far = max(w.map, key=lambda p: w.distance(p, mill))
        w.characters["P0"]["location"] = far; w.characters["P1"]["location"] = mill; w.characters["P2"]["location"] = far
        w.characters["P1"]["sick"] = True           # nearest, but not able
        r = w.assign_day(random.Random(1))
        self.assertTrue(r["duties"]["mill"]["unclaimed"]); self.assertIn(r["duties"]["mill"]["dumped_on"], ("P0", "P2"))
        who = w.characters[r["duties"]["mill"]["dumped_on"]]
        self.assertIn("mill", who["dumped"]); self.assertTrue(any("You are covering" in x["text"] and "because nobody has it" in x["text"] for x in who["log"]))
        self.assertIn("the mill", w.duty_brief(who["name"]).lower()); self.assertIn("you are covering it today because nobody has it", w.duty_brief(who["name"]))
        w.characters["P1"]["sick"] = False; w.characters["P0"]["location"] = far
        r2 = w.assign_day(random.Random(1)); self.assertEqual(r2["duties"]["mill"]["dumped_on"], "P1", "the nearest able person gets it")

    def test_nobody_is_dumped_past_three(self) -> None:
        w = valley(n=1); c = w.characters["P0"]; c["duties"] = ["mill", "hunt", "fish"]
        r = w.assign_day(random.Random(1)); self.assertEqual(c["dumped"], []); self.assertTrue(r["duties"]["wood"]["unclaimed"]); self.assertIsNone(r["duties"]["wood"]["dumped_on"])

    def test_an_emergency_pulls_the_nearest_regardless_of_duty(self) -> None:
        w = valley(n=4); w.seed_duties(random.Random(1)); places = list(w.map); here = places[0]; far = max(places, key=lambda p: w.distance(p, here))
        for c in w.living(): c["location"] = far
        w.characters["P0"]["location"] = here; w.characters["P1"]["location"] = w.map[here]["adj"][0]
        for c in w.living(): c["hp"] = c["hp_max"] = 30
        w.fires[here] = 0
        r = w.assign_day(random.Random(1))
        e = [x for x in r["emergencies"] if x["kind"] == "fire"][0]
        self.assertEqual(set(e["pulled"]), {"P0", "P1"}); self.assertTrue(w.characters["P0"]["emergency"]); self.assertIsNone(w.characters["P3"]["emergency"])
        self.assertIn("EMERGENCY", w.duty_brief("P0")); self.assertNotIn("EMERGENCY", w.duty_brief("P3"))
        w.fires.clear(); w.characters["P2"]["hp"] = 2; w.characters["P2"]["location"] = here
        r = w.assign_day(random.Random(1)); self.assertTrue(any(x["kind"] == "injury" and x.get("who") == "P2" for x in r["emergencies"]))
        self.assertNotIn("P2", [n for x in r["emergencies"] for n in x["pulled"]], "the hurt one is not pulled to their own rescue")


class ChangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.w = valley(n=4); self.w.seed_duties(random.Random(1))
        for c in self.w.living(): c["duties"] = []
        self.w.characters["P0"]["duties"] = ["mill", "hunt"]; self.w.characters["P1"]["duties"] = ["fish"]

    def test_refusing_drops_standing_and_leaves_it_unclaimed(self) -> None:
        w = self.w; c = w.characters["P0"]; s0 = c["standing_score"]
        self.assertIn("refused", w.refuse_duty("P0", "mill")); self.assertNotIn("mill", c["duties"]); self.assertLess(c["standing_score"], s0)
        self.assertEqual(w.duty_state("mill")["unclaimed_day"], w.day); self.assertTrue(any("refused" in x["text"] for x in c["log"]))
        self.assertIn("does not hold", w.refuse_duty("P0", "fish"))

    def test_handing_and_taking_up(self) -> None:
        w = self.w
        self.assertIn("handed", w.hand_duty("P0", "P1", "hunt")); self.assertIn("hunt", w.characters["P1"]["duties"]); self.assertNotIn("hunt", w.characters["P0"]["duties"])
        w.refuse_duty("P1", "fish")
        s0 = w.characters["P2"]["standing_score"]
        self.assertIn("took up", w.claim_duty("P2", "fish")); self.assertIn("fish", w.characters["P2"]["duties"]); self.assertGreater(w.characters["P2"]["standing_score"], s0)
        self.assertIsNone(w.duty_state("fish")["unclaimed_day"])
        self.assertIn("is held by", w.claim_duty("P3", "fish"), "a held duty cannot simply be claimed")

    def test_actions_are_read_and_settled_by_the_engine(self) -> None:
        w = self.w; log: list[str] = []
        acts = [{"who": "P0", "text": "I refuse the mill, let someone else grind", "turn": 1},
                {"who": "P1", "text": "I hand the fishing over to @P2", "turn": 2},
                {"who": "P3", "text": "Nobody does the wood, so I'll take up the wood", "turn": 3},
                {"who": "P2", "text": "I walk to the chapel", "turn": 4}]
        out = w.resolve_duty_actions(acts, log)
        self.assertEqual([o["kind"] for o in out], ["refuse_duty", "hand_duty", "claim_duty"]); self.assertTrue(all(o["ok"] for o in out))
        self.assertEqual([a["who"] for a in acts], ["P2"], "settled acts leave the list for the World")
        self.assertIn("wood", w.characters["P3"]["duties"]); self.assertIn("fish", w.characters["P2"]["duties"])

    def test_taking_work_by_contest_moves_a_duty(self) -> None:
        w = self.w; a, t = w.characters["P2"], w.characters["P0"]; a["location"] = t["location"]
        a["standing_score"] = 9; t["standing_score"] = -9; t["traits"]["courage"] = 1; t["traits"]["temper"] = 1
        r = w.resolve_social("P2", "take_duty", "P0", random.Random(3))
        self.assertTrue(r["ok"], r); self.assertIn("the mill", r["text"]); self.assertIn("mill", a["duties"]); self.assertNotIn("mill", t["duties"])

    def test_fate_sets_duties_outright(self) -> None:
        w = self.w
        self.assertIn("jobs are now", w.set_duties("P3", ["kitchen", "fire", "nonsense", "watch", "trade"]))
        self.assertEqual(w.characters["P3"]["duties"], ["kitchen", "fire", "watch"])
        self.assertEqual(w.set_duties("P3", ["kitchen", "fire", "watch"]), "no change")


class WorkTests(unittest.TestCase):
    def test_work_moves_the_ledger_and_nudges_the_skill(self) -> None:
        w = valley(n=2); c = w.characters["P0"]; c["duties"] = ["wood"]; c["skills"]["woodcutting"] = 5; L = w.ledger; w0 = L["wood"]
        made = 0; learned = 0
        for i in range(10): r = w.do_duty("P0", "wood", random.Random(i)); made += r["made"].get("wood", 0); learned += int(bool(r.get("learned")))
        self.assertGreater(made, 0); self.assertEqual(L["wood"], w0 + made); self.assertGreater(learned, 0); self.assertGreaterEqual(c["skills"]["woodcutting"], 5)
        self.assertEqual(w.duty_state("wood")["done_day"], w.day); self.assertTrue(any("cutting wood" in x["text"] for x in c["log"]))

    def test_work_consumes_and_fails_without_its_inputs(self) -> None:
        w = valley(n=2); L = w.ledger; L["grain"] = 0
        r = w.do_duty("P0", "mill", random.Random(5)); self.assertEqual(r["made"], {}); self.assertIn("nothing to work with", r["text"])
        L["grain"] = 3; c = w.characters["P0"]; c["skills"]["milling"] = 9
        r = w.do_duty("P0", "mill", random.Random(5)); self.assertEqual(r["used"], {"grain": 1}); self.assertGreater(r["made"].get("meals", 0), 0)

    def test_fields_give_nothing_in_winter(self) -> None:
        w = valley(n=2); w.day = 20; w.weather = "snow"; w.characters["P0"]["skills"]["farming"] = 9
        r = w.do_duty("P0", "fields", random.Random(1)); self.assertEqual(r["made"], {}); self.assertIn("season", r["text"])

    def test_effects_land_on_places_and_people(self) -> None:
        w = valley(n=3); rng = random.Random(4); p = w.duty_place("roofs"); w.upkeep[p]["roof"] = 1
        for c in w.living(): c["skills"] = {d["skill"]: 9 for d in DUTIES.values()}
        w.do_duty("P0", "roofs", rng); self.assertGreater(w.upkeep[p]["roof"], 1)
        f = w.duty_place("cleaning"); w.upkeep[f]["filth"] = 9; w.do_duty("P0", "cleaning", rng); self.assertLess(w.upkeep[f]["filth"], 9)
        w.characters["P1"]["sick"] = True; r = w.do_duty("P0", "healing", rng); self.assertEqual(w.characters["P1"].get("tended_day"), w.day); self.assertIn("tended", r["text"])
        w.bodies["Old Tam"] = w.duty_place("burial"); r = w.do_duty("P0", "burial", rng); self.assertNotIn("Old Tam", w.bodies); self.assertIn("buried", r["text"])
        w.ledger["road_safe"] = False; w.do_duty("P0", "watch", rng); self.assertTrue(w.ledger["road_safe"])

    def test_an_undone_duty_costs_the_valley(self) -> None:
        w = valley(n=2); w.ledger["road_safe"] = True; g0 = w.ledger["grain"]
        r = w.mark_undone("watch"); self.assertFalse(w.ledger["road_safe"]); self.assertLess(w.ledger["grain"], g0); self.assertEqual(r["days"], 1); self.assertIn("undone", r["text"])
        self.assertEqual(w.mark_undone("watch")["days"], 2)


class ServerTests(unittest.TestCase):
    def test_fate_edits_duties_through_the_character_endpoint(self) -> None:
        import connect, game, server
        tmp = Path(tempfile.mkdtemp(prefix="terra-duties-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; w = g.world; rng = random.Random(7)
            for i, n in enumerate(("Bett", "Osgar")): w.characters[n] = engine.roll_character(n, i + 1, rng, list(w.map))
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in ("Bett", "Osgar")]
            app.run._sync_terms(); g.save()
            note = app.edit_character({"name": "Bett", "duties": ["mill", "fire"]})
            self.assertIn("jobs are now the mill, the fires", note); self.assertEqual(w.characters["Bett"]["duties"], ["mill", "fire"])
            snap = app.snapshot(); self.assertIn("duty_defs", snap); self.assertIn("mill", snap["duty_defs"]); self.assertIn("roster", snap)
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
