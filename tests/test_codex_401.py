"""The Codex 401 path, end to end, with a stub that can be refused on demand: a dead sign in at priming pauses the run and says
what to do; Resume after a new sign in primes again and carries on; a seat refused mid-turn is asked again after the recovery
and loses nothing; and the saved copy of the sign in is refreshed by a good prime. The real user's ~/.codex is never touched.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, shutil, sys, tempfile, threading, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "tests"))
import agents, engine, game  # noqa: E402

STUB = ROOT / "tests" / "stub_agent.py"


class Codex401Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-401-")); engine.GAMES = self.tmp; game.GAMES = self.tmp
        cmd = f'"{sys.executable}" "{STUB}" "{{ask}}" --model {{model}}'
        self.old_codex = agents.PROVIDERS["Codex"]
        agents.PROVIDERS["Codex"] = {"exe": sys.executable, "speech": "stdout", "resume": "", "models": ["stub"], "cmd": cmd, "ro_cmd": cmd}
        agents.PROVIDERS["Stub"] = {"exe": sys.executable, "speech": "stdout", "resume": "", "models": ["stub"], "cmd": cmd, "ro_cmd": cmd}
        self.auth = self.tmp / "auth.json"; self.backup = self.tmp / "auth.json.backup"; self.auth.write_text('{"tokens": "good"}', encoding="utf-8")
        self.old_paths = (game.CODEX_AUTH, game.CODEX_BACKUP); game.CODEX_AUTH, game.CODEX_BACKUP = self.auth, self.backup
        self.old_trust = game.ensure_codex_trust; game.ensure_codex_trust = lambda folder: None
        self.counter = self.tmp / "refuse.txt"; os.environ["TERRA_STUB_401"] = str(self.counter)
        self.errs: list = []; self.old_hook = threading.excepthook; threading.excepthook = lambda a: self.errs.append(a)

    def tearDown(self) -> None:
        threading.excepthook = self.old_hook; agents.PROVIDERS["Codex"] = self.old_codex; game.CODEX_AUTH, game.CODEX_BACKUP = self.old_paths; game.ensure_codex_trust = self.old_trust
        os.environ.pop("TERRA_STUB_401", None); shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self) -> tuple[game.Game, game.Run]:
        g = game.Game(engine.now_id()); g.players = 2; g.max_days = 1; g.drama = 0
        g.world_model = {"provider": "Stub", "model": "stub"}; g.model_a = {"provider": "Codex", "model": "stub"}; g.model_b = {"provider": "Codex", "model": "stub"}
        g.repo = str(self.tmp); g.save(); r = game.Run(g); r.prepare_map(); r._build_people(); r._create_world(); return g, r

    def wait(self, g: game.Game, cond, seconds: float = 120) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if cond(): return
            time.sleep(0.2)
        self.fail("timed out waiting: " + " | ".join(e["text"][:80] for e in g.transcript if e["kind"] == "system"))

    def notes(self, g: game.Game) -> list[str]:
        return [e["text"] for e in g.transcript if e["kind"] == "system"]

    def test_a_dead_sign_in_at_priming_pauses_and_resume_after_a_new_sign_in_carries_on(self) -> None:
        g, r = self.make()
        self.counter.write_text("99", encoding="utf-8")            # refused every time from here on: the refresh token is revoked
        try:
            r.start(); self.wait(g, lambda: r.blocked == "Codex signed out, sign in and press Resume")
            self.assertEqual(g.status, "paused"); self.assertTrue(r.pause_flag.is_set())
            self.assertTrue(any("refused with 401" in n for n in self.notes(g))); self.assertTrue(any("still signed out" in n for n in self.notes(g)))
            self.assertTrue(all("gave no answer" not in n for n in self.notes(g)), "nobody spoke yet, so nobody is blamed")
            self.counter.write_text("0", encoding="utf-8")         # the convener signs in again
            self.auth.write_text('{"tokens": "new"}', encoding="utf-8")
            r.start()                                                # and presses Resume
            self.assertEqual(r.blocked, "", "Resume clears the banner")
            self.wait(g, lambda: g.status in ("done", "stopped"), 180)
            self.assertEqual(g.status, "done"); self.assertEqual(self.errs, [])
            self.assertEqual(self.backup.read_text(encoding="utf-8"), '{"tokens": "new"}', "a good prime keeps the new sign in as the copy")
            prompts = " ".join(f.name for f in (g.dir / "seat0").glob("prompt_*"))
            self.assertGreaterEqual(len(list((g.dir / "seat0").glob("prompt_*"))), 3, "priming ran again after Resume: " + prompts)
            self.assertTrue(any(e["kind"] == "morning" for e in g.transcript), "the day went on after Resume")
        finally:
            r.stop()

    def test_a_seat_refused_mid_turn_is_recovered_and_asked_again(self) -> None:
        # the prime succeeds (the counter is only armed after it), one seat is refused mid-morning, the copy is restored, the re-prime succeeds, the seat is asked again
        g, r = self.make(); armed = {"done": False}
        old_prime = r.prime_codex
        def prime(label: str) -> bool:
            ok = old_prime(label)
            if ok and not armed["done"]: armed["done"] = True; self.counter.write_text("1", encoding="utf-8")
            return ok
        r.prime_codex = prime
        try:
            r.start(); self.wait(g, lambda: g.status in ("done", "stopped"), 240)
            self.assertEqual(g.status, "done"); self.assertEqual(self.errs, [])
            ns = self.notes(g)
            self.assertTrue(any("refused with 401" in n for n in ns), ns); self.assertTrue(any("Codex answered again" in n for n in ns), ns)
            self.assertFalse(any("gave no answer" in n for n in ns), "the refused seat was asked again, not written off")
            morning = next(e for e in g.transcript if e["kind"] == "morning")
            self.assertNotIn("skipped", morning["text"]); self.assertNotIn("could not face", morning["text"])
            asked_again = any("asked again after the sign in came back" in ln for t in r.terms for ln in t["lines"])
            self.assertTrue(asked_again, "the retry is written in the seat's terminal")
        finally:
            r.stop()

    def test_the_revoked_token_message_counts_as_refused(self) -> None:
        for line in ("ERROR: Your access token could not be refreshed because your refresh token was revoked.", "HTTP 401 Unauthorized", "invalid_grant", "missing bearer token"):
            self.assertTrue(game.CODEX_401.search(line), line)
        self.assertFalse(game.CODEX_401.search("I keep my own counsel and watch the water."))


if __name__ == "__main__":
    unittest.main()
