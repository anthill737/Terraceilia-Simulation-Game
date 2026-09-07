"""The prompts are what make people sound like people, so the rules that keep them plain are tested.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

import prompts  # noqa: E402

# the words that kept leaking into the valley, and the plain word each one stands in for
BANNED = ["folk", "skinful", "bedding", "aye", "nay", "thee", "thou", "prithee", "verily",
          "forsooth", "hark", "alas", "'tis", "mayhap", "methinks", "morrow"]


class SpeechRuleTests(unittest.TestCase):
    def test_villagers_are_told_to_talk_plainly(self) -> None:
        t = prompts.PLAYER_RULES.lower()
        self.assertIn("plain, everyday words", t)
        self.assertIn("short sentences", t)
        self.assertIn("contractions", t)

    def test_villagers_are_given_a_length(self) -> None:
        self.assertIn("ONE TO THREE SENTENCES", prompts.PLAYER_RULES)
        self.assertIn("one to three sentences, then stop", prompts.PLAYER_RULES.lower())

    def test_the_world_is_given_a_length(self) -> None:
        t = prompts.WORLD_RULES.lower()
        self.assertIn("at most two sentences per entry", t)
        self.assertIn("state what happened and stop", t)
        self.assertIn("no flourish", t)

    def test_both_prompts_ban_the_same_words(self) -> None:
        for word in BANNED:
            for name, text in (("PLAYER_RULES", prompts.PLAYER_RULES), ("WORLD_RULES", prompts.WORLD_RULES)):
                self.assertIn(word, text.lower(), f"{name} must name {word!r} as banned")

    def test_both_prompts_say_to_use_the_plain_word(self) -> None:
        for name, text in (("PLAYER_RULES", prompts.PLAYER_RULES), ("WORLD_RULES", prompts.WORLD_RULES)):
            t = text.lower()
            self.assertIn("not folk", t, f"{name} must say people rather than folk")
            self.assertIn("not a skinful", t, f"{name} must say a drink rather than a skinful")

    def test_neither_prompt_asks_for_flourish_any_more(self) -> None:
        """The old rules asked the World for two to five paragraphs and for vivid writing."""
        self.assertNotIn("two to five short paragraphs", prompts.WORLD_RULES)
        self.assertNotIn("be vivid", prompts.WORLD_RULES)
        import game
        self.assertNotIn("two to five short paragraphs", Path(game.__file__).read_text(encoding="utf-8"),
                         "the day's instruction still asks for paragraphs")

    def test_the_villager_rules_still_carry_the_action_line(self) -> None:
        """Shortening the speech must not lose the one line the engine parses."""
        self.assertIn("ACTION:", prompts.PLAYER_RULES)
        self.assertIn("WHISPER @Name:", prompts.PLAYER_RULES)

    def test_the_map_prompt_still_asks_for_the_world_described(self) -> None:
        self.assertIn("must read as the world described", prompts.MAP_RULES)
        self.assertTrue(re.search(r"palette", prompts.MAP_RULES))


if __name__ == "__main__":
    unittest.main()
