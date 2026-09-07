"""Nothing in the valley is decided by a body. A person drives someone out, refuses them, takes their work, or leaves,
and the engine settles it. These tests hold that line, and make sure the old words never come back.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, re, sys, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine  # noqa: E402

# the words that meant a body decided something; none of them may appear anywhere the game reads or shows
OLD_WORDS = re.compile(r"\b(court|courts|vote|votes|voting|tally|tallies|council|councils|banish\w*)\b", re.I)
SCAN = [ROOT / "backend", ROOT / "frontend", ROOT / "data", ROOT / "tests", ROOT / "README.md"]
SUFFIXES = {".py", ".js", ".html", ".css", ".json", ".md"}


OLD_KEY = "bani" + "shed"      # what old saves called it; this file scans for the word, so it is never written whole here


def source_files():
    for root in SCAN:
        if root.is_file(): yield root; continue
        for f in root.rglob("*"):
            if f.suffix in SUFFIXES and "__pycache__" not in f.parts and f.name != Path(__file__).name: yield f


class World3(unittest.TestCase):
    """Three people in one place, with feelings that make the sides predictable."""

    def setUp(self) -> None:
        self.w = engine.World(); rng = random.Random(3); places = list(self.w.map); here = places[0]
        for i, n in enumerate(("Aldous", "Bett", "Cuthbert", "Dimity")):
            self.w.characters[n] = engine.roll_character(n, i + 1, rng, places); self.w.characters[n]["location"] = here
        self.w.characters["Dimity"]["location"] = places[1]        # one path away, not in the room
        self.w.created = True; self.w.day = 4
        for n in self.w.characters:
            for m in self.w.characters:
                if n != m: self.w.rel(n, m)

    def test_the_old_words_are_gone(self) -> None:
        hits = []
        for f in source_files():
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if OLD_WORDS.search(line): hits.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:80]}")
        self.assertEqual(hits, [], "the old words are back:\n" + "\n".join(hits))

    def test_the_world_has_no_court_day(self) -> None:
        self.assertFalse(hasattr(self.w, "court_every"))
        self.assertNotIn("court_every", self.w.to_dict())

    def test_a_result_block_cannot_send_anyone_away(self) -> None:
        log: list[str] = []
        self.w.apply({OLD_KEY: ["Bett"], "sent_away": ["Bett"], "gone": ["Bett"], "results": []}, log)
        self.assertFalse(self.w.characters["Bett"]["gone"], "the World's block must not be able to send anyone away")
        self.assertIn("Bett", self.w.living()[1]["name"] if len(self.w.living()) > 1 else "", "Bett must still be living")

    def test_villagers_and_world_are_not_told_to_decide_together(self) -> None:
        import prompts
        for text in (prompts.PLAYER_RULES, prompts.WORLD_RULES, prompts.DEFAULT_WORLD):
            self.assertIsNone(OLD_WORDS.search(text), "a prompt names a deciding body")
        self.assertIn("drive them out yourself", prompts.PLAYER_RULES)
        self.assertIn("refuse to share with someone", prompts.PLAYER_RULES)
        self.assertIn("leave the valley for good", prompts.PLAYER_RULES)
        self.assertIn("never reverse it", prompts.WORLD_RULES)

    def test_intents_are_read_from_action_lines(self) -> None:
        w = self.w
        self.assertEqual(w.social_intent("Aldous", "I drive @Bett out of the valley for good"), ("drive_out", "Bett"))
        self.assertEqual(w.social_intent("Aldous", "Run Bett off. She goes today."), ("drive_out", "Bett"))
        self.assertEqual(w.social_intent("Aldous", "I refuse to share my bread with Bett"), ("refuse", "Bett"))
        self.assertEqual(w.social_intent("Aldous", "I won't give Cuthbert any more grain"), ("refuse", "Cuthbert"))
        self.assertEqual(w.social_intent("Aldous", "I take over Bett's work at the mill; she is not fit for it"), ("take_duty", "Bett"))
        self.assertEqual(w.social_intent("Aldous", "I pack my things and leave the valley"), ("leave", None))
        self.assertEqual(w.social_intent("Aldous", "I'm leaving for good."), ("leave", None))
        self.assertIsNone(w.social_intent("Aldous", "I mend my nets and listen"))
        self.assertIsNone(w.social_intent("Aldous", "I ask Bett to share her fire"))
        self.assertIsNone(w.social_intent("Aldous", "I walk to the mill and ask about work"))

    def test_driving_out_is_settled_by_standing_sides_and_dice(self) -> None:
        w = self.w; a, t = w.characters["Aldous"], w.characters["Bett"]
        a["standing_score"] = 8; t["standing_score"] = -8; t["traits"]["courage"] = 1; t["traits"]["temper"] = 1
        w.set_rel("Cuthbert", "Aldous", feeling=5); w.set_rel("Cuthbert", "Bett", feeling=-5)     # Cuthbert stands with Aldous
        r = w.resolve_social("Aldous", "drive_out", "Bett", random.Random(1))
        self.assertTrue(r["ok"], r); self.assertEqual(r["with_actor"], ["Cuthbert"]); self.assertEqual(r["with_target"], [])
        self.assertTrue(t["gone"]); self.assertIn("driven out by Aldous", t["gone_reason"])
        self.assertNotIn(t, w.living()); self.assertTrue(any("drove you out" in x["text"] for x in t["log"]))
        self.assertIn("Dimity", [c["name"] for c in w.living()], "someone one path away is neither a side nor a victim")

    def test_driving_out_can_fail_and_costs_the_one_who_tried(self) -> None:
        w = self.w; a, t = w.characters["Aldous"], w.characters["Bett"]
        a["standing_score"] = -8; t["standing_score"] = 8; t["traits"]["courage"] = 5; t["traits"]["temper"] = 5
        w.set_rel("Cuthbert", "Bett", feeling=5); w.set_rel("Cuthbert", "Aldous", feeling=-5)
        before = a["standing_score"]
        r = w.resolve_social("Aldous", "drive_out", "Bett", random.Random(2), resisting=True)
        self.assertFalse(r["ok"], r); self.assertEqual(r["with_target"], ["Cuthbert"])
        self.assertFalse(t["gone"]); self.assertLess(a["standing_score"], before)
        self.assertTrue(any("tried to drive you out and failed" in x["text"] for x in t["log"]))
        self.assertLess(w.rel("Bett", "Aldous")["feeling"], 0)

    def test_leaving_benches_the_leaver_with_the_reason(self) -> None:
        w = self.w; a = w.characters["Aldous"]
        r = w.resolve_social("Aldous", "leave", None, random.Random(0))
        self.assertTrue(r["ok"]); self.assertTrue(a["gone"]); self.assertIn("left the valley on day 4", a["gone_reason"])
        self.assertNotIn(a, w.living()); self.assertTrue(any("left the valley" in x["text"] for x in a["log"]))

    def test_refusing_and_taking_work_move_standing_and_ties(self) -> None:
        w = self.w; a, t = w.characters["Aldous"], w.characters["Bett"]
        a["standing_score"] = 6; t["standing_score"] = 0
        r = w.resolve_social("Aldous", "refuse", "Bett", random.Random(5))
        self.assertIn(r["kind"], ("refuse",)); self.assertLess(w.rel("Bett", "Aldous")["feeling"], 0)
        self.assertFalse(t["gone"], "refusing to share never sends anyone away")
        r2 = w.resolve_social("Cuthbert", "take_duty", "Bett", random.Random(6))
        self.assertEqual(r2["kind"], "take_duty"); self.assertTrue(r2["text"])
        self.assertTrue(w.characters["Cuthbert"]["log"] or t["log"], "somebody's log records it")

    def test_the_day_pulls_social_acts_out_before_the_world_sees_them(self) -> None:
        w = self.w; log: list[str] = []
        acts = [{"who": "Aldous", "text": "I drive Bett out of the valley", "turn": 1},
                {"who": "Bett", "text": "I stay. @Aldous can try; I am not going anywhere", "turn": 2},
                {"who": "Cuthbert", "text": "I mend the fence", "turn": 3}]
        settled = w.resolve_social_actions(acts, random.Random(9), log)
        self.assertEqual([a["who"] for a in acts], ["Bett", "Cuthbert"], "the settled act leaves the list; the rest stay for the World")
        self.assertEqual(len(settled), 1); self.assertEqual(settled[0]["kind"], "drive_out"); self.assertTrue(settled[0]["text"])
        self.assertTrue(log and log[0].startswith("drive_out"))

    def test_standing_is_a_number_with_a_word(self) -> None:
        c = self.w.characters["Aldous"]
        self.assertEqual(c["standing"], engine.standing_word(0))
        engine.bump_standing(c, 9); self.assertEqual(c["standing"], "loved"); self.assertEqual(c["standing_score"], 9)
        engine.bump_standing(c, -30); self.assertEqual(c["standing"], "hated"); self.assertEqual(c["standing_score"], -9)
        for word in engine.STANDING_WORDS: self.assertEqual(engine.standing_word(engine.standing_score_for(word)), word)

    def test_old_saves_are_carried_over(self) -> None:
        old = {"characters": {"Osgar": {"name": "Osgar", "seat": 1, "alive": True, OLD_KEY: True, "standing": "feared", "hp": 5, "hp_max": 9, "gold": 1,
                                        "skills": {}, "location": "The inn", "str": 3, "spd": 3, "trade": "", "home": "", "personality": "", "secret": "", "fear": "", "want": "", "cause_of_death": ""}},
               "court_every": 6}
        w = engine.World(old); c = w.characters["Osgar"]
        self.assertTrue(c["gone"]); self.assertNotIn(OLD_KEY, c); self.assertTrue(c["gone_reason"])
        self.assertIn(c["standing"], engine.STANDING_WORDS); self.assertNotIn("court_every", w.to_dict())


if __name__ == "__main__":
    unittest.main()
