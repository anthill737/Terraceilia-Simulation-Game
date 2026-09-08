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

EM, EN = "\u2014", "\u2013"      # by code point: the dash itself is not allowed in this repo, tests included


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

    def test_an_at_name_carries_nowhere_and_names_the_person_only(self) -> None:
        """A villager can reach nobody but the people standing with them. @Name is a name, not a message."""
        w = self.w; ties = w.ties_of("Aldous")
        e = {"kind": "speech", "speaker": "Bett", "place": "The mill", "text": "Cold, isn't it.\n@Cuthbert the roof is yours.\nACTION: I wait."}
        self.assertIsNone(touched_text(e, "Cuthbert", "The inn", ties), "the @ line does not reach him at the inn")
        self.assertEqual(touched_text(e, "Aldous", "The mill", ties), e["text"], "the people at the mill hear all of it, @ line included")
        self.assertIsNone(touched_text(e, "Dimity", "The castle", ties))
        self.assertEqual(w.heard_by("Bett", e["text"]), ["Aldous"], "only the mill hears it")
        self.assertEqual(w.heard_by("Dimity", "Anyone?"), [])
        self.assertEqual(w.not_here("Bett", "Dimity, come down from there."), ["Dimity"])
        self.assertEqual(w.not_here("Bett", "@Dimity come down."), ["Dimity"], "@ names her, and she is not here")
        self.assertEqual(w.not_here("Bett", "WHISPER @Cuthbert: bring ale."), ["Cuthbert"], "a whisper to someone elsewhere reaches nobody either")
        self.assertEqual(w.not_here("Bett", "Dimity owes me two coins."), [], "talking about someone is not addressing them")
        self.assertEqual(w.not_here("Bett", "Aldous, pass the sack."), [], "Aldous is here")

    def test_a_whisper_is_for_one_pair_of_ears_at_the_place(self) -> None:
        w = self.w; ties = w.ties_of("Aldous")
        e = {"kind": "speech", "speaker": "Bett", "place": "The mill", "text": "WHISPER @Aldous: the sack is short.\nACTION: I wait."}
        self.assertIn("the sack is short", touched_text(e, "Aldous", "The mill", ties) or "")
        self.assertIsNone(touched_text(e, "Cuthbert", "The inn", ties), "not at the mill, so none of it")
        w.characters["Cuthbert"]["location"] = "The mill"
        try:
            got = touched_text(e, "Cuthbert", "The mill", ties) or ""
            self.assertNotIn("the sack is short", got, "standing there, but the whisper was not for him")
            self.assertIn("ACTION: I wait.", got)
        finally:
            w.characters["Cuthbert"]["location"] = "The inn"

    def test_the_prompt_states_the_audience_and_the_chronicle_says_who_heard(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-aud-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g)
            self.assertIn("You are at The mill with Bett.", r._player_prompt(1, "speak"))
            self.assertIn("You are at The castle. Nobody else is here.", r._player_prompt(4, "speak"))
            for gone in ("Only they can hear you", "Nobody can hear you", "to talk to someone elsewhere, go there",
                         "To talk to someone elsewhere, go there", "is not here"):
                self.assertNotIn(gone, r._player_prompt(1, "speak")); self.assertNotIn(gone, r._player_prompt(4, "speak"))
            r._record("Bett", "Aldous, the sack is short.\nACTION: I wait.", "speech"); e = g.transcript[-1]
            self.assertEqual(e["heard"], ["Aldous"]); self.assertNotIn("is not here", e["text"], "nothing is appended any more")
            r._record("Dimity", "Nobody up here but the wind.", "speech"); self.assertEqual(g.transcript[-1]["heard"], [])
            self.assertIsNone(r._record("World", "The day ends.", "world")); self.assertIsNone(g.transcript[-1]["heard"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_prompt_with_nobody_there_offers_no_speech_at_all(self) -> None:
        """Alone: the ACTION line and an optional private THOUGHT, and not one word about talking."""
        tmp = Path(tempfile.mkdtemp(prefix="terra-alone-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g)
            self.assertTrue(w.alone("Dimity")); self.assertFalse(w.alone("Bett"))
            solo = r._speech_clause("Dimity")
            self.assertIn("Nobody else is at The castle.", solo)
            self.assertIn("say nothing aloud: give your ACTION line and nothing more", solo)
            self.assertIn("THOUGHT:", solo)
            for gone in ("Say what you say", "Only they", "elsewhere"): self.assertNotIn(gone, solo)
            together = r._speech_clause("Bett")
            self.assertIn("You are at The mill with Aldous. Say what you say to them", together)
            for gone in ("THOUGHT:", "elsewhere", "Nobody"): self.assertNotIn(gone, together)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_words_with_no_ear_are_dropped_and_only_the_log_says_so(self) -> None:
        """A line to someone who is not there, and a line said by someone standing alone, never reach the chronicle."""
        tmp = Path(tempfile.mkdtemp(prefix="terra-drop-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g); idx = {s["name"]: i for i, s in enumerate(g.seats)}
            before = len(g.transcript)
            self.assertFalse(r._say(idx["Bett"], "Dimity, come down from there.\nACTION: I wait."))
            self.assertEqual(len(g.transcript), before, "the speech is dropped, not annotated")
            log = [x["text"] for x in w.characters["Bett"]["log"]]
            self.assertTrue(any("spoke to nobody" in t and "Dimity" in t for t in log), log)
            self.assertFalse(any("is not here" in e["text"] for e in g.transcript))

            self.assertFalse(r._say(idx["Dimity"], "Anyone up here?\nACTION: I wait."), "she is alone at the castle")
            self.assertEqual(len(g.transcript), before)
            self.assertTrue(any("spoke to nobody at The castle" in x["text"] for x in w.characters["Dimity"]["log"]))

            self.assertFalse(r._say(idx["Dimity"], "ACTION: I wait.\nTHOUGHT: the wall is thinner than it looks."))
            self.assertTrue(any("You thought: the wall is thinner than it looks." == x["text"] for x in w.characters["Dimity"]["log"]))
            self.assertEqual(len(g.transcript), before, "a thought is nobody else's business")

            self.assertTrue(r._say(idx["Bett"], "Aldous, the sack is short.\nACTION: I wait."), "he is standing right there")
            self.assertEqual(g.transcript[-1]["heard"], ["Aldous"])
            self.assertEqual(g.transcript[-1]["text"], "Aldous, the sack is short.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_only_the_people_standing_there_are_woken_to_answer(self) -> None:
        """Naming someone reaches them only if they are there. @ and WHISPER wake nobody who is elsewhere."""
        tmp = Path(tempfile.mkdtemp(prefix="terra-react-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g)
            idx = {s["name"]: i for i, s in enumerate(g.seats)}
            n2i = {n.lower(): i for n, i in idx.items() if n != "World"}
            speaker = idx["Bett"]                                   # Bett is at The mill with Aldous
            self.assertEqual(r._reactors(speaker, "Aldous, pass the sack.", n2i), [idx["Aldous"]])
            self.assertEqual(r._reactors(speaker, "@Aldous pass the sack.", n2i), [idx["Aldous"]])
            for line in ("Cuthbert, get up here.", "@Cuthbert get up here.", "WHISPER @Cuthbert: get up here.",
                         "Dimity, come down.", "@Dimity come down."):
                self.assertEqual(r._reactors(speaker, line, n2i), [], line)
            self.assertEqual(r._reactors(speaker, "Nobody in particular.", n2i), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_afternoon_prompt_says_where_to_find_the_people_who_matter(self) -> None:
        """A grudge, a debt, a lover, or the person a want turns on, each with the place they are standing."""
        tmp = Path(tempfile.mkdtemp(prefix="terra-errand-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2; w.phase = "afternoon"
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
            r = game.Run(g)
            w.set_rel("Aldous", "Cuthbert", typ="debtor", why="four gold at the harvest")
            w.set_rel("Aldous", "Bett", feeling=-4, why="she took the sack")
            w.characters["Aldous"]["goal"] = {"kind": "lover", "target": "Dimity", "text": "to be Dimity's lover, or more"}
            rows = {x["name"]: x for x in w.errands("Aldous")}
            self.assertEqual(rows["Cuthbert"]["place"], "The inn"); self.assertEqual(rows["Cuthbert"]["why"], "they owe you")
            self.assertEqual(rows["Bett"]["why"], "you hold a grudge against them"); self.assertTrue(rows["Bett"]["here"], "she is at the mill with him")
            self.assertEqual(rows["Dimity"]["place"], "The castle"); self.assertIn("what you want turns on them", rows["Dimity"]["why"])
            p = r._player_prompt(1, "act")
            self.assertIn("PEOPLE YOU HAVE A REASON TO FIND", p)
            self.assertIn("- Cuthbert is at The inn: they owe you.", p)
            self.assertIn("- Bett is at The mill (here, with you): you hold a grudge against them.", p)
            self.assertIn("your ACTION can be to travel there, and you talk when you arrive", p)
            w.phase = "morning"
            self.assertNotIn("PEOPLE YOU HAVE A REASON TO FIND", r._player_prompt(1, "work"), "the morning is for work")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _run_for_talk(self, tmp: Path) -> tuple:
        engine.GAMES = tmp; game.GAMES = tmp
        g = game.Game(engine.now_id()); g.world = self.w; w = g.world; w.created = True; w.day = 2
        g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#fff"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#abc"} for n in w.characters]
        r = game.Run(g); rounds: list[tuple] = []
        def fake_round(seats, instruction, label, on_reply, reactions=True):
            rounds.append((label, tuple(sorted(g.seats[i]["name"] for i in seats)),
                           instruction(seats[0]) if callable(instruction) else instruction, reactions))
        r._round = fake_round
        return g, w, r, rounds

    def test_two_people_arriving_at_the_same_place_get_one_talk_round(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-talk-"));
        try:
            g, w, r, rounds = self._run_for_talk(tmp)
            c = w.characters
            c["Aldous"]["location"] = c["Bett"]["location"] = "The mill"
            c["Cuthbert"]["location"] = "The inn"; c["Dimity"]["location"] = "The castle"
            ran = r._talk_round("after work")
            self.assertEqual(len(ran), 1, ran); self.assertEqual(ran[0]["place"], "The mill")
            self.assertEqual(ran[0]["names"], ["Aldous", "Bett"])
            self.assertEqual(len(rounds), 1)
            label, names, instr, reactions = rounds[0]
            self.assertEqual(names, ("Aldous", "Bett")); self.assertIn("The mill", label)
            self.assertFalse(reactions, "one round per group per beat, so nothing re-wakes them")
            self.assertIn("You are at The mill with Bett.", instr); self.assertIn("No ACTION line.", instr)
            self.assertNotIn("Cuthbert", " ".join(x[1][0] for x in rounds))
            self.assertEqual(r._talk_round("after work"), [], "the same group at the same beat is not asked twice")
            self.assertEqual(len(rounds), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_nobody_standing_alone_is_ever_woken(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-solo-"))
        try:
            g, w, r, rounds = self._run_for_talk(tmp)
            for i, n in enumerate(("Aldous", "Bett", "Cuthbert", "Dimity")):
                w.characters[n]["location"] = list(w.map)[i]
            self.assertEqual(r._talk_round("evening"), []); self.assertEqual(rounds, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_three_beats_in_the_same_place_give_three_rounds_and_no_more(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-beats-"))
        try:
            g, w, r, rounds = self._run_for_talk(tmp)
            for n in ("Aldous", "Bett", "Cuthbert", "Dimity"): w.characters[n]["location"] = "The inn"
            for beat in ("after work", "after the afternoon", "evening"):
                self.assertEqual(len(r._talk_round(beat)), 1, beat)
                self.assertEqual(r._talk_round(beat), [], f"{beat} twice is still one round")
            self.assertEqual(len(rounds), 3, [x[0] for x in rounds])
            self.assertEqual([x["beat"] for x in r.talks], ["after work", "after the afternoon", "evening"])
            w.day += 1
            self.assertEqual(len(r._talk_round("after work")), 1, "tomorrow is a new day and a new round")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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
