"""The day: dawn, a morning of work the engine settles, an afternoon of free actions, the World, an evening of talk, and the
end of the day. WORK and REFUSE are read off the ACTION line; a free action in the morning is a skip; skipping costs standing
and the duty; what nobody did reaches the World by name; after two days a neighbour complains by name.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import json, os, random, shutil, sys, tempfile, threading, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "tests"))
import agents, engine, game  # noqa: E402
from engine import DUTIES  # noqa: E402

STUB = ROOT / "tests" / "stub_agent.py"
STUB_MODEL = {"provider": "Stub", "model": "stub"}


def valley(n: int = 4) -> engine.World:
    w = engine.World(); rng = random.Random(3); places = list(w.map)
    for i in range(n):
        nm = f"P{i}"; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = ["miller", "hunter", "cook", "guard"][i % 4]
        c["location"] = c["home"] = places[i % len(places)]; w.characters[nm] = c
    w.ledger = engine.starting_ledger(n, len(w.map)); w.seed_places(); w.created = True; w.day = 1; w.seed_duties(rng); w.assign_day(rng)
    return w


class MorningTests(unittest.TestCase):
    def test_work_and_refuse_are_read_off_the_action_line(self) -> None:
        w = valley()
        self.assertEqual(w.morning_intent("P0", "WORK"), ("work", None)); self.assertEqual(w.morning_intent("P0", "Work: the mill"), ("work", "mill"))
        self.assertEqual(w.morning_intent("P0", "REFUSE"), ("refuse", None)); self.assertEqual(w.morning_intent("P0", "refuse the hunt"), ("refuse", "hunt"))
        self.assertEqual(w.morning_intent("P0", "I walk to the inn"), ("skip", None)); self.assertEqual(w.morning_intent("P0", ""), ("skip", None))

    def test_every_form_of_work_and_refuse_is_read_anywhere_in_the_reply(self) -> None:
        w = valley(); mi = lambda t: w.morning_intent("P0", t)  # noqa: E731
        for t in ("WORK", "WORK.", "work", "Work.", "ACTION: WORK", "ACTION: WORK.", "action: work", "I am tired, but I will.\nACTION: WORK", "I suppose I will go. WORK.", "Fine.\nwork\n"):
            self.assertEqual(mi(t), ("work", None), t)
        for t in ("WORK the mill", "WORK mill.", "work: the mill", "ACTION: WORK the mill", "ACTION: Work the mill.", "I will see to the mill first.\nWORK the mill, then the rest."):
            self.assertEqual(mi(t), ("work", "mill"), t)
        for t in ("REFUSE", "REFUSE.", "refuse", "ACTION: REFUSE", "action: refuse.", "No. I will not.\nACTION: REFUSE"):
            self.assertEqual(mi(t), ("refuse", None), t)
        for t in ("REFUSE the hunt", "refuse hunt.", "ACTION: REFUSE the hunt", "Not the hunt, never again. REFUSE the hunt."):
            self.assertEqual(mi(t), ("refuse", "hunt"), t)
        self.assertEqual(mi("ACTION: WORK\nrefuse everything"), ("work", None), "the ACTION line wins over the rest of the reply")
        self.assertEqual(mi("I walk to the inn"), ("skip", None)); self.assertEqual(mi(""), ("skip", None)); self.assertEqual(mi("ACTION: I go drinking"), ("skip", None))

    def test_work_with_a_duty_does_that_one_first_then_the_rest(self) -> None:
        w = valley(); c = w.characters["P0"]; c["duties"] = ["mill", "wood"]; c["dumped"] = []
        for k in c["duties"]: c["skills"][DUTIES[k]["skill"]] = 9
        w.ledger["grain"] = 9; out = w.resolve_morning("P0", "WORK the wood", random.Random(1))
        self.assertEqual([r["duty"] for r in out if r.get("kind") == "work"], ["wood", "mill"]); self.assertEqual(c["duties"], ["mill", "wood"], "nothing is skipped or lost")

    def test_work_with_an_unclaimed_duty_takes_it_up(self) -> None:
        w = valley(); c = w.characters["P0"]; c["duties"] = []; c["dumped"] = []
        for x in w.living(): x["duties"] = [k for k in x.get("duties", []) if k != "wood"]; x["dumped"] = [k for k in x.get("dumped", []) if k != "wood"]
        out = w.resolve_morning("P0", "WORK the wood", random.Random(1))
        self.assertEqual(out[0]["kind"], "claim"); self.assertIn("took up", out[0]["text"]); self.assertIn("wood", c["duties"]); self.assertTrue(any(r.get("kind") == "work" and r["duty"] == "wood" for r in out))

    def test_work_is_resolved_by_the_engine(self) -> None:
        w = valley(); c = w.characters["P0"]; before = dict(w.ledger); n = len([k for k in c["duties"] if not w.nothing_today(k)])
        for k in c["duties"]: c["skills"][DUTIES[k]["skill"]] = 9
        w.ledger["grain"] = 9
        out = w.resolve_morning("P0", "WORK", random.Random(1))
        self.assertEqual([r["kind"] for r in out], ["work"] * n); self.assertNotEqual(w.ledger, before, "work must move the ledger")
        self.assertEqual(c["duties"], c["duties"], "working keeps your duties"); self.assertTrue(all(r["text"] for r in out))

    def test_a_free_action_in_the_morning_skips_the_day_and_two_running_lose_the_duty(self) -> None:
        w = valley(); c = w.characters["P1"]; held = list(c["duties"]); s0 = c["standing_score"]
        out = w.resolve_morning("P1", "I go to the inn and drink", random.Random(1))
        self.assertEqual(out[-1]["kind"], "skip"); self.assertFalse(out[-1]["lost"]); self.assertEqual(c["duties"], held, "one skip keeps the duty"); self.assertLess(c["standing_score"], s0)
        self.assertTrue(any("skipped" in x["text"] for x in c["log"]))
        w.day += 1; out = w.resolve_morning("P1", "I go to the inn again", random.Random(2))
        self.assertTrue(out[-1]["lost"]); self.assertEqual(c["duties"], [])
        for k in held: self.assertEqual(w.duty_state(k)["unclaimed_day"], w.day, f"{k} should be unclaimed")

    def test_refuse_one_keeps_the_rest(self) -> None:
        w = valley(); c = w.characters["P0"]; c["duties"] = ["mill", "hunt"]
        out = w.resolve_morning("P0", "REFUSE the hunt", random.Random(1))
        self.assertEqual(c["duties"], ["mill"]); self.assertEqual(out[-1]["duties"], ["hunt"]); self.assertEqual(out[-1]["kind"], "refuse")

    def test_the_sick_do_no_work_and_lose_nothing(self) -> None:
        w = valley(); c = w.characters["P0"]; c["sick"] = True; held = list(c["duties"])
        out = w.resolve_morning("P0", "WORK", random.Random(1)); self.assertEqual(out[0]["kind"], "sick"); self.assertEqual(c["duties"], held)

    def test_an_emergency_comes_first(self) -> None:
        w = valley(); p = w.characters["P0"]["location"]; w.fires[p] = 0
        for c in w.living(): c["hp"] = c["hp_max"] = 30
        w.assign_day(random.Random(1)); pulled = [c["name"] for c in w.living() if c.get("emergency")]
        self.assertTrue(pulled)
        out = w.resolve_morning(pulled[0], "WORK", random.Random(2))
        self.assertEqual(out[0]["kind"], "fire"); self.assertIn("fire at", out[0]["text"])

    def test_what_nobody_did_costs_and_after_two_days_a_neighbour_complains_by_name(self) -> None:
        w = valley(); w.ledger["road_safe"] = True
        m1 = w.end_morning(set(), random.Random(1)); self.assertEqual(len(m1["undone"]), len([k for k in DUTIES if not w.nothing_today(k)]), "a duty with nothing to do today is not undone"); self.assertFalse(w.ledger["road_safe"]); self.assertEqual(m1["complaints"], [])
        w.day = 2; m2 = w.end_morning({"mill"}, random.Random(1))
        self.assertTrue(m2["complaints"], "two days undone and nobody complained")
        line = m2["complaints"][0]; who = line.split(" complains")[0]; self.assertIn(who, w.characters); self.assertIn("2 days running", line)
        self.assertNotIn("the mill has gone undone", " ".join(m2["complaints"]))
        self.assertIn("UNDONE", w.undone_text().upper() or "UNDONE"); self.assertIn("days running", w.undone_text())

    def test_a_duty_that_cannot_yield_today_is_nothing_to_do_not_a_skip(self) -> None:
        w = valley(); c = w.characters["P0"]
        for x in w.living(): x["duties"] = [k for k in x.get("duties", []) if k not in ("fields", "wood")]; x["dumped"] = []
        c["duties"] = ["fields", "wood"]; c["skills"] = {"farming": 9, "woodcutting": 9}
        w.day = 20; w.weather = "clear"; w.assign_day(random.Random(1))       # deep winter: the fields are dormant
        self.assertTrue(w.nothing_today("fields")); self.assertFalse(w.nothing_today("wood"))
        self.assertEqual([ln for ln in w.nothing_lines if ln.startswith("the fields")], ["the fields are dormant; P0 is free this morning."])
        self.assertIn("nothing to do today, the fields are dormant", w.duty_brief("P0"))
        s0 = c["standing_score"]; out = w.resolve_morning("P0", "WORK", random.Random(1))
        worked = [r["duty"] for r in out if r.get("kind") == "work"]; self.assertIn("wood", worked); self.assertNotIn("fields", worked, "the dormant fields are not worked and not skipped")
        self.assertEqual(c["standing_score"], s0); self.assertEqual(c["skip_streak"], 0); self.assertEqual(c["duties"], ["fields", "wood"])
        m = w.end_morning({"wood"}, random.Random(1)); self.assertNotIn("fields", [u["duty"] for u in m["undone"]], "nothing to do is not undone")
        # the other reasons
        w2 = valley(); w2.ledger.update(grain=0, meat=0, fish=0); w2.bodies = {}
        for x in w2.living(): x["sick"] = False
        w2.assign_day(random.Random(1))
        for k, why in (("kitchen", "there is nothing to cook"), ("burial", "there is nobody to bury"), ("healing", "nobody is sick")):
            if any(k in x.get("duties", []) or k in x.get("dumped", []) for x in w2.living()): self.assertEqual(w2.duty_state(k).get("nothing_why"), why, k)
        teacher = next((x for x in w2.living() if "teaching" in x.get("duties", []) or "teaching" in x.get("dumped", [])), None)
        if teacher:
            place = w2.duty_place("teaching")
            for x in w2.living():
                if x["name"] != teacher["name"]: x["location"] = next(pl for pl in w2.map if pl != place)
            w2.mark_nothing_to_do(); self.assertEqual(w2.duty_state("teaching").get("nothing_why"), f"nobody is at {place} to teach")
        # REFUSE still gives up a duty that had nothing to do
        w3 = valley(); c3 = w3.characters["P0"]; c3["duties"] = ["fields"]; c3["dumped"] = []; w3.day = 20; w3.assign_day(random.Random(1))
        w3.resolve_morning("P0", "REFUSE", random.Random(1)); self.assertEqual(c3["duties"], [])

    def test_a_complaint_names_the_holder_even_when_the_duty_was_dumped(self) -> None:
        w = valley(); w.day = 3
        for x in w.living(): x["duties"] = []; x["dumped"] = []
        w.characters["P0"]["duties"] = ["mill"]; w.duty_state("watch")["undone_days"] = 1; w.duty_state("mill")["undone_days"] = 1
        w.assign_day(random.Random(1)); dumped_on = w.roster["duties"]["watch"]["dumped_on"]; self.assertTrue(dumped_on, "the watch is dumped on somebody")
        m = w.end_morning(set(), random.Random(1)); lines = " ".join(m["complaints"])
        self.assertNotIn("nobody has taken", lines)
        watch = [c for c in m["complaints"] if "the watch" in c]; mill = [c for c in m["complaints"] if "the mill" in c]
        self.assertTrue(watch and f"that {dumped_on} holds it" in watch[0], watch); self.assertTrue(mill and "that P0 holds it" in mill[0], mill)

    def test_evening_sends_people_home_or_to_the_inn(self) -> None:
        w = valley(); inn = next(p for p, d in w.map.items() if d.get("kind") == "inn")
        for c in w.living(): c["location"] = list(w.map)[0]; c["traits"]["drink"] = 1; c["traits"]["tongue"] = 1; c["traits"]["desire"] = 1
        w.characters["P0"]["traits"]["drink"] = 5
        w.evening_places(random.Random(1))
        self.assertEqual(w.characters["P0"]["location"], inn); self.assertEqual(w.characters["P0"]["activity"], "at the inn")
        self.assertEqual(w.characters["P1"]["location"], w.characters["P1"]["home"]); self.assertEqual(w.characters["P1"]["activity"], "at home")

    def test_the_day_ends_only_when_told(self) -> None:
        w = valley(); w.characters["P0"]["dumped"] = ["mill"]; w.end_day(); self.assertEqual(w.day, 2); self.assertEqual(w.phase, "morning"); self.assertEqual(w.characters["P0"]["dumped"], [])


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-day-")); engine.GAMES = self.tmp; game.GAMES = self.tmp
        cmd = f'"{sys.executable}" "{STUB}" "{{ask}}" --model {{model}}'
        agents.PROVIDERS["Stub"] = {"exe": sys.executable, "speech": "stdout", "resume": "", "models": ["stub"], "cmd": cmd, "ro_cmd": cmd}

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_stub_day_runs_dawn_morning_afternoon_world_evening(self) -> None:
        g = game.Game(engine.now_id()); g.players = 3; g.max_days = 2; g.drama = 0
        g.world_model = dict(STUB_MODEL); g.model_a = dict(STUB_MODEL); g.model_b = dict(STUB_MODEL); g.save()
        r = game.Run(g); w = g.world; r.prepare_map(); r._build_people(); r._create_world()
        self.assertTrue(all(c["duties"] for c in w.living()), "everyone is seeded with work at creation")
        errs: list = []; old_hook = threading.excepthook; threading.excepthook = lambda a: errs.append(a)
        try:
            r.start(); deadline = time.time() + 240
            while g.status == "running" and time.time() < deadline: time.sleep(0.2)
        finally: threading.excepthook = old_hook; r.stop()
        self.assertEqual(errs, []); self.assertEqual(g.status, "done"); self.assertGreater(w.day, 2)
        kinds = [e["kind"] for e in g.transcript if e.get("day") == 1]
        for k in ("dawn", "morning", "world", "evening"): self.assertIn(k, kinds, f"day 1 has no {k} entry: {kinds}")
        kinds = kinds[kinds.index("dawn"):]     # the creation narration comes before the first dawn
        self.assertLess(kinds.index("dawn"), kinds.index("morning")); self.assertLess(kinds.index("morning"), kinds.index("world")); self.assertLess(kinds.index("world"), kinds.index("evening"))
        morning = next(e for e in g.transcript if e["kind"] == "morning")
        self.assertTrue(any(c["name"] in morning["text"] for c in w.characters.values()), "the morning names who worked")
        self.assertTrue(all(e.get("phase") in ("morning", "afternoon", "evening") for e in g.transcript if e.get("day", 0) >= 1), "every entry carries its phase")
        prompts = " ".join(f.read_text(encoding="utf-8") for f in (g.dir / "seat0").glob("prompt_*"))
        self.assertIn("outcomes, settled by the engine", prompts, "the World is given the outcomes")
        for t in r.terms: self.assertNotIn("[engine error", "\n".join(t["lines"]))


if __name__ == "__main__":
    unittest.main()
