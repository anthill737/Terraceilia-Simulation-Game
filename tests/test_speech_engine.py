"""The engine's side of plain speech: dashes stripped on the way in, villagers cut to three sentences, the World cut to
two per outcome, and a villager told only what touched them rather than the day's story.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, random, shutil, sys, tempfile, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import engine, game  # noqa: E402
from engine import strip_dashes, cap_speech, cap_outcomes, touched_text  # noqa: E402

EM, EN = "—", "–"      # by code point: the dash itself is not allowed in this repo, tests included


class DashTests(unittest.TestCase):
    def test_a_dash_between_words_becomes_a_comma(self) -> None:
        self.assertEqual(strip_dashes(f"the grain is short {EM} we all know it"), "the grain is short, we all know it")
        self.assertEqual(strip_dashes(f"ash{EM}fire{EM}smoke"), "ash, fire, smoke")
        self.assertEqual(strip_dashes(f"the grain is short {EN} we all know it"), "the grain is short, we all know it")

    def test_a_dash_before_a_capital_or_at_the_end_becomes_a_stop(self) -> None:
        self.assertEqual(strip_dashes(f"The grain is short {EM} And the wood is worse"), "The grain is short. And the wood is worse")
        self.assertEqual(strip_dashes(f"The grain is short {EM}"), "The grain is short.")
        self.assertEqual(strip_dashes(f"The grain is short {EM} I'm scared"), "The grain is short, I'm scared", "a capital I is not a new sentence")

    def test_a_dash_opening_a_line_is_dropped_and_lines_are_kept(self) -> None:
        self.assertEqual(strip_dashes(f"{EM} nobody asked you\nfine {EM} go"), "nobody asked you\nfine, go")

    def test_nothing_else_is_touched(self) -> None:
        s = "Plain text, with a hyphen-word and a colon: fine.\nACTION: I go."
        self.assertEqual(strip_dashes(s), s)
        self.assertNotIn(EM, strip_dashes(f"a {EM} b {EM} c {EM} D {EM}"))


class CapTests(unittest.TestCase):
    def test_villagers_are_cut_to_three_sentences_and_keep_their_action(self) -> None:
        out = cap_speech("One. Two! Three? Four. Five.\nACTION: I mend the roof.")
        self.assertEqual(out, "One. Two! Three?\nACTION: I mend the roof.")

    def test_a_whisper_line_keeps_its_prefix(self) -> None:
        out = cap_speech("WHISPER @Bett: six. seven. eight. nine.\nACTION: I go.")
        self.assertEqual(out, "WHISPER @Bett: six. seven. eight.\nACTION: I go.")
        self.assertIn("bett", engine.whisper_targets(out))

    def test_short_replies_are_left_alone(self) -> None:
        self.assertEqual(cap_speech("I'm fine.\nACTION: I go."), "I'm fine.\nACTION: I go.")
        self.assertEqual(cap_speech("PASS"), "PASS")

    def test_the_world_is_cut_to_two_sentences_per_outcome(self) -> None:
        out = cap_outcomes("Bett: She fell. She got up. She fell again.\nEVENT: Rain. More rain. Even more.\n\nA long day. Nothing. Really nothing.")
        self.assertEqual(out, "Bett: She fell. She got up.\nEVENT: Rain. More rain.\n\nA long day. Nothing.")


class TouchedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.w = engine.World(); rng = random.Random(4); places = list(self.w.map)
        for i, n in enumerate(("Aldous", "Bett", "Cuthbert", "Dimity")):
            self.w.characters[n] = engine.roll_character(n, i + 1, rng, places)
        c = self.w.characters; c["Aldous"]["location"] = "The mill"; c["Bett"]["location"] = "The mill"; c["Cuthbert"]["location"] = "The inn"; c["Dimity"]["location"] = "The castle"
        self.w.set_rel("Aldous", "Dimity", typ="kin", feeling=3, trust=3)

    def test_only_what_touched_them_reaches_a_villager(self) -> None:
        w = self.w; ties = w.ties_of("Aldous"); self.assertIn("Dimity", ties); self.assertNotIn("Cuthbert", ties)
        entry = {"kind": "world", "speaker": "World", "text": ("Cuthbert: He drank at The inn until he fell over. Nobody helped him.\n"
                                                                 "Bett: She mended a net at The mill and cursed Aldous for the cold.\n"
                                                                 "Dimity: She walked the castle wall alone.\n"
                                                                 "The weather turned.\n\nPROSPERITY, day 2: grain for 9 of 16 weeks needed.")}
        got = touched_text(entry, "Aldous", "The mill", ties) or ""
        self.assertIn("cursed Aldous", got, "named them")
        self.assertIn("castle wall", got, "done by someone they are tied to")
        self.assertNotIn("drank at The inn", got, "nothing to do with them")
        self.assertNotIn("weather turned", got, "no day summary")
        self.assertNotIn("PROSPERITY", got, "no tables")
        self.assertIsNone(touched_text({"kind": "system", "speaker": "Engine", "text": "Adjustments: Aldous lost 2"}, "Aldous", "The mill", ties), "engine notes never reach a person")

    def test_speech_still_follows_sight(self) -> None:
        w = self.w; ties = w.ties_of("Aldous")
        here = {"kind": "speech", "speaker": "Bett", "place": "The mill", "text": "Cold, isn't it.\nACTION: I wait."}
        away = {"kind": "speech", "speaker": "Cuthbert", "place": "The inn", "text": "Another cup.\nACTION: I drink."}
        self.assertTrue(touched_text(here, "Aldous", "The mill", ties)); self.assertIsNone(touched_text(away, "Aldous", "The mill", ties))

    def test_the_villager_prompt_carries_no_day_summary(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-speech-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g)
            r._record("World", "Cuthbert: He drank at The inn until he fell over. Nobody helped him.\nThe valley slept badly.\n\nPROSPERITY, day 1: grain.", "world")
            r._record("Bett", "Aldous, the roof is yours to fix.\nACTION: I wait.", "speech")
            p = r._player_prompt(1, "speak")
            self.assertIn("WHAT TOUCHED YOU", p); self.assertIn("the roof is yours", p)
            self.assertNotIn("drank at The inn", p, "the day's story is not repeated to a villager it did not touch")
            self.assertNotIn("slept badly", p); self.assertNotIn("What you saw and heard since your last turn", p)
            p3 = r._player_prompt(3, "speak")     # Cuthbert, at the inn: named in the World's line, so it reaches him
            self.assertIn("drank at The inn", p3); self.assertNotIn("the roof is yours", p3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
