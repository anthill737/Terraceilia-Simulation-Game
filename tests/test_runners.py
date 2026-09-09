"""Runners. Every error class is read from the runner's exit code and message before anything is taken as a line: a sign in
refusal pauses the run, a model refusal moves the seat to the first model that answered the probe, a rate limit or server error
waits with backoff, a launcher bug stops the run with the command, anything else is asked once more and then benched. The
auth file is never written. Two clocks kill a hung process. Preflight probes every seat's real model before Start.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import os, re, shutil, sys, tempfile, threading, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "tests"))
import agents, connect, engine, game, runner, server  # noqa: E402

STUB = ROOT / "tests" / "stub_agent.py"
CMD = f'"{sys.executable}" "{STUB}" "{{ask}}" --model {{model}}'
CODEX_AUTH = Path.home() / ".codex" / "auth.json"


def stub_provider(models: list[str]) -> dict:
    return {"exe": sys.executable, "speech": "stdout", "resume": "", "models": list(models), "cmd": CMD, "ro_cmd": CMD}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="terra-run-")); engine.GAMES = self.tmp; game.GAMES = self.tmp
        self.saved = {k: agents.PROVIDERS.get(k) for k in ("Stub", "Codex")}
        agents.PROVIDERS["Stub"] = stub_provider(["stub", "stub2"]); agents.PROVIDERS["Codex"] = stub_provider(["stub", "stub2"])
        self.counter = self.tmp / "fail.txt"; os.environ["TERRA_STUB_401"] = str(self.counter)
        for k in ("TERRA_STUB_FAIL", "TERRA_STUB_MODE"): os.environ.pop(k, None)
        with connect._probe_lock: connect._probes.clear()
        self.old_trust = game.ensure_codex_trust; game.ensure_codex_trust = lambda folder: None
        self.old_backoff = runner.BACKOFF; runner.BACKOFF = (0.2, 0.3, 0.4)
        self.errs: list = []; self.old_hook = threading.excepthook; threading.excepthook = lambda a: self.errs.append(a)
        self.auth_before = CODEX_AUTH.stat().st_mtime if CODEX_AUTH.exists() else None

    def tearDown(self) -> None:
        threading.excepthook = self.old_hook; runner.BACKOFF = self.old_backoff; game.ensure_codex_trust = self.old_trust
        for k, v in self.saved.items():
            if v is None: agents.PROVIDERS.pop(k, None)
            else: agents.PROVIDERS[k] = v
        for k in ("TERRA_STUB_401", "TERRA_STUB_FAIL", "TERRA_STUB_MODE"): os.environ.pop(k, None)
        with connect._probe_lock: connect._probes.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.auth_before is not None: self.assertEqual(CODEX_AUTH.stat().st_mtime, self.auth_before, "the user's Codex auth file was touched")

    def make(self, provider: str = "Stub", model: str = "stub", days: int = 1) -> tuple[game.Game, game.Run]:
        g = game.Game(engine.now_id()); g.players = 2; g.max_days = days; g.drama = 0
        g.world_model = {"provider": "Stub", "model": "stub"}; g.model_a = {"provider": provider, "model": model}; g.model_b = {"provider": provider, "model": model}
        g.repo = str(self.tmp); g.save(); return g, game.Run(g)

    def created(self, r: game.Run) -> None:
        self.assertTrue(r.preflight()); r._build_people(); r.prepare_map(); r._create_world()

    def wait(self, cond, seconds: float = 90, what: str = "") -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if cond(): return
            time.sleep(0.2)
        self.fail("timed out waiting for " + what)

    def notes(self, g: game.Game) -> list[str]:
        return [e["text"] for e in g.transcript if e["kind"] == "system"]

    def fail_with(self, kind: str, times: int) -> None:
        os.environ["TERRA_STUB_FAIL"] = kind; self.counter.write_text(str(times), encoding="utf-8")

    def arm(self, r: game.Run, kind: str, times: int) -> None:
        """Start runs the preflight first; the failure is armed only once that has passed, so it lands on a real turn."""
        orig = r.preflight
        def pf() -> bool:
            ok = orig()
            if ok: self.fail_with(kind, times)
            return ok
        r.preflight = pf


class ErrorClasses(Base):
    def test_auth_pauses_the_run_and_asks_for_a_sign_in_and_resume_carries_on(self) -> None:
        g, r = self.make("Codex"); self.created(r); self.arm(r, "auth", 99)
        try:
            r.start(); self.wait(lambda: r.blocked.endswith("sign in and press Resume"), what="the pause")
            self.assertEqual(g.status, "paused"); self.assertIn("Codex signed out", r.blocked)
            self.assertTrue(any("refused a call for want of a sign in" in n for n in self.notes(g)))
            self.counter.write_text("0", encoding="utf-8"); r.start()
            self.assertEqual(r.blocked, ""); self.wait(lambda: g.status in ("done", "stopped"), 180, "the year")
            self.assertEqual(g.status, "done"); self.assertEqual(self.errs, [])
        finally: r.stop()

    def test_a_model_refusal_moves_the_seat_to_the_first_model_that_answered(self) -> None:
        g, r = self.make(); self.created(r)
        connect.record_probe("Stub", "stub2", True)
        seat = g.seats[1]; self.arm(r, "model", 1)
        try:
            r.start(); self.wait(lambda: g.status in ("done", "stopped"), 180, "the year")
            self.assertEqual(g.status, "done")
            moved = [x for x in g.seats[1:] if x["model"] == "stub2"]; self.assertEqual(len(moved), 1, [x["model"] for x in g.seats])
            self.assertTrue(any("now uses stub2, the first Stub model that answered a test" in n for n in self.notes(g)), self.notes(g))
            self.assertFalse(any("benched" in n for n in self.notes(g)))
        finally: r.stop()
        del seat

    def test_rate_limits_and_server_errors_wait_with_backoff(self) -> None:
        for kind in ("rate", "server"):
            g, r = self.make(); self.created(r); self.arm(r, kind, 2)
            try:
                r.start(); self.wait(lambda: g.status in ("done", "stopped"), 180, "the year")
                self.assertEqual(g.status, "done"); self.assertFalse(any("benched" in n for n in self.notes(g)), self.notes(g))
                waits = [ln for t in r.terms for ln in t["lines"] if "asked us to wait" in ln]
                self.assertEqual(len(waits), 2, waits)
            finally: r.stop()

    def test_a_launcher_bug_stops_the_run_with_the_command(self) -> None:
        g, r = self.make(); self.created(r); self.arm(r, "launcher", 99)
        try:
            r.start(); self.wait(lambda: g.status in ("done", "stopped"), 60, "the stop")
            self.assertEqual(g.status, "stopped"); self.assertIn("launcher bug", r.blocked); self.assertIn("stub_agent.py", r.blocked); self.assertIn("--model", r.blocked)
            self.assertTrue(any("The command that was built" in n for n in self.notes(g)))
        finally: r.stop()

    def test_any_other_failure_is_asked_again_once_then_benched_and_is_never_a_line(self) -> None:
        g, r = self.make(); self.created(r); self.arm(r, "other", 1)
        try:
            r.start(); self.wait(lambda: g.status in ("done", "stopped"), 180, "the year")
            self.assertEqual(g.status, "done"); self.assertFalse(any("benched" in n for n in self.notes(g)), "one retry saved the turn")
            self.assertTrue(any("asking again once" in ln for t in r.terms for ln in t["lines"]))
        finally: r.stop()
        g, r = self.make(); self.created(r); self.arm(r, "other", 99)
        try:
            r.start(); self.wait(lambda: g.status in ("done", "stopped"), 180, "the year")
            self.assertTrue(any("is benched for this turn" in n and "nobody has a name for" in n for n in self.notes(g)), self.notes(g))
            self.assertFalse(any(e["kind"] == "speech" and "burn the mill" in e["text"] for e in g.transcript), "an error was read as a line")
            self.assertFalse(any("burn the mill" in a["text"] for a in g.world.pending), "an error was read as an action")
            self.assertFalse(any(x["text"] and "burn" in x["text"] for c in g.world.characters.values() for x in c["log"]))
        finally: r.stop()


class Classify(unittest.TestCase):
    def test_kinds(self) -> None:
        c = runner.classify
        self.assertEqual(c(1, "ERROR: 401 Unauthorized", "", False, "", False)[0], "auth")
        self.assertEqual(c(1, "refresh token was revoked", "", False, "", False)[0], "auth")
        self.assertEqual(c(1, "404: model gpt-99 does not exist", "", False, "", False)[0], "model")
        self.assertEqual(c(1, "you do not have access to model x", "", False, "", False)[0], "model")
        self.assertEqual(c(1, "429 rate limit", "", False, "", False)[0], "rate"); self.assertEqual(c(1, "503 Service Unavailable", "", False, "", False)[0], "rate")
        self.assertEqual(c(1, "missing bearer token", "", False, "", False)[0], "launcher")
        self.assertEqual(c(1, "", "", False, "killed after 5 seconds without a line of output", False)[0], "timeout")
        self.assertEqual(c(1, "", "", False, "", False)[0], "other"); self.assertEqual(c(0, "", "fine", False, "", True), ("", ""))
        self.assertEqual(c(0, "warning: update available", "fine", False, "", True), ("", ""), "a warning beside a real answer is not an error")
        self.assertEqual(c(0, "", "", True, "", True)[0], "other", "the runner's own error flag counts before the text")


class AuthFileNeverWritten(Base):
    def test_no_code_path_touches_the_auth_file(self) -> None:
        for f in ("game.py", "runner.py", "server.py", "connect.py", "agents.py"):
            src = (ROOT / "backend" / f).read_text(encoding="utf-8")
            self.assertNotRegex(src, r"auth\.json\.\w*backup|_backup_codex|_restore_codex|CODEX_AUTH|CODEX_BACKUP|prime_codex|_codex_refused", f)
            self.assertNotRegex(src, r"copy2?\([^)]*auth\.json|auth\.json[^\n]*write", f)
        self.assertFalse(hasattr(game.Run, "prime_codex")); self.assertFalse(hasattr(game.Run, "_prime_day"))

    def test_old_backups_are_deleted_at_launch(self) -> None:
        home = self.tmp / "home"; (home / ".codex").mkdir(parents=True); b = home / ".codex" / "auth.json.terraceilia-backup"; b.write_text("old")
        real = home / ".codex" / "auth.json"; real.write_text("keep")
        old = server.Path.home
        try:
            server.Path.home = classmethod(lambda cls: home); server.App._forget_old_backups()
        finally: server.Path.home = old
        self.assertFalse(b.exists()); self.assertEqual(real.read_text(), "keep")


class Timeouts(Base):
    def test_the_quiet_clock_kills_a_silent_process(self) -> None:
        os.environ["TERRA_STUB_MODE"] = "hang"; t0 = time.time()
        r = runner.launch(CMD.format(ask=agents.ASK.format(prompt_file=str(self.tmp / "p.md")), model="stub"), str(self.tmp), "stdout", wall=60, quiet=1.0)
        self.assertEqual(r.kind, "timeout"); self.assertIn("without a line", r.message); self.assertLess(time.time() - t0, 15); self.assertIsNone(r.speech)

    def test_the_wall_clock_kills_a_chattering_process(self) -> None:
        os.environ["TERRA_STUB_MODE"] = "chatter"; t0 = time.time()
        r = runner.launch(CMD.format(ask=agents.ASK.format(prompt_file=str(self.tmp / "p.md")), model="stub"), str(self.tmp), "stdout", wall=1.5, quiet=60)
        self.assertEqual(r.kind, "timeout"); self.assertIn("wall clock", r.message); self.assertLess(time.time() - t0, 15)
        self.assertGreater(len(r.stdout), 2, "it was printing the whole time"); self.assertIsNone(r.speech, "output before the kill is not an answer")

    def test_the_defaults_are_thirty_and_five_minutes(self) -> None:
        self.assertEqual(runner.TURN_TIMEOUT, 1800); self.assertEqual(runner.NO_OUTPUT_TIMEOUT, 300)

    def test_a_timed_out_seat_is_asked_again_then_benched(self) -> None:
        g, r = self.make(); self.created(r)
        os.environ["TERRA_STUB_MODE"] = "hang"; old = (runner.TURN_TIMEOUT, runner.NO_OUTPUT_TIMEOUT); runner.TURN_TIMEOUT, runner.NO_OUTPUT_TIMEOUT = 30, 0.8
        try:
            self.assertIsNone(r.ask(0, "hello", "t")); self.assertEqual(r.last_error[0]["kind"], "timeout")
            self.assertTrue(any("benched" in n and "without a line" in n for n in self.notes(g)))
        finally: runner.TURN_TIMEOUT, runner.NO_OUTPUT_TIMEOUT = old


class Preflight(Base):
    def test_an_empty_model_takes_the_first_that_answers(self) -> None:
        agents.PROVIDERS["Stub"] = stub_provider(["bad", "stub", "stub2"])
        g, r = self.make(model=""); g.world_model = {"provider": "Stub", "model": ""}; g.save()
        self.assertTrue(r.preflight())
        self.assertEqual(g.model_a["model"], "stub"); self.assertEqual(g.world_model["model"], "stub"); self.assertEqual(g.seats[0]["model"], "stub")
        self.assertEqual(connect.first_accessible("Stub"), "stub"); self.assertFalse(connect.probes_of("Stub")["bad"]["ok"])

    def test_an_auth_failure_at_preflight_blocks_start_with_the_reason(self) -> None:
        g, r = self.make(); self.fail_with("auth", 9)
        try:
            r.start(); self.wait(lambda: g.status in ("done", "stopped"), 60, "the stop")
            self.assertEqual(g.status, "stopped"); self.assertIn("Stub refused the test for want of a sign in", r.blocked)
            self.assertFalse(g.world.created, "nothing was started")
        finally: r.stop()

    def test_a_model_failure_at_preflight_switches_the_seat_and_starts(self) -> None:
        agents.PROVIDERS["Stub"] = stub_provider(["bad", "stub", "stub2"])
        g, r = self.make(model="bad")
        self.assertTrue(r.preflight(), "a model failure does not block Start")
        self.assertEqual(g.model_a["model"], "stub"); self.assertEqual(g.model_b["model"], "stub"); self.assertEqual(g.seats[0]["model"], "stub")
        self.assertEqual(g.bad_models, ["Stub|bad"], "a 404 is remembered for the game")
        notes = self.notes(g); self.assertEqual(len(notes), 2, "one chronicle line per switched model: the first and the second villagers' model")
        for n in notes: self.assertIn("model bad was refused at Start", n); self.assertIn("now plays on stub, the first Stub model that answered", n)
        self.assertIn("The first villagers' model", notes[0]); self.assertIn("The second villagers' model", notes[1])
        saved = game.Game(g.id, __import__("json").loads((g.dir / "game.json").read_text(encoding="utf-8")))
        self.assertEqual(saved.model_a["model"], "stub"); self.assertEqual(saved.bad_models, ["Stub|bad"])

    def test_a_seat_is_probed_once_a_day_and_a_bad_model_never_again(self) -> None:
        agents.PROVIDERS["Stub"] = stub_provider(["bad", "stub", "stub2"])
        g, r = self.make(model="bad"); g.seats = [r.world_seat(), {"name": "Bett", "provider": "Stub", "model": "bad", "color": "#7f9a5c"}]; g.save(); r._sync_terms()
        probes: list[tuple[int, str]] = []; orig = r.probe_model
        def counting(provider: str, model: str, i: int = 0) -> tuple[bool, str]:
            probes.append((i, model)); return orig(provider, model, i)
        r.probe_model = counting
        self.assertTrue(r.preflight()); self.assertEqual(g.seats[1]["model"], "stub"); self.assertEqual(g.seats[0]["model"], "stub")
        first = list(probes); self.assertEqual([m for _, m in first if m == "bad"], ["bad"], "the bad model was probed once for the day, by the first seat that needed it")
        self.assertLessEqual(len([1 for i, _ in first if i == 1]), 1); probes.clear()
        self.assertTrue(r.preflight()); self.assertEqual(probes, [], "a second Start the same day probes nobody")
        g.world.day += 1; self.assertTrue(r.preflight())
        self.assertNotIn("bad", [m for _, m in probes], "a model that failed with 404 is never probed again in this game")
        self.assertEqual(sorted(i for i, _ in probes), sorted(set(i for i, _ in probes)), "one probe per seat per day")
        n = len(probes); self.assertEqual(r.find_model(1, "Stub"), "stub"); self.assertEqual(len(probes), n, "find_model probes nothing when the record already has an answer")

    def test_connected_comes_only_from_a_probe(self) -> None:
        with connect._lock: connect._cache["Stub"] = (time.monotonic(), {"name": "Stub", "state": "connected", "detail": "Signed in", "installed": True, "exe": "x", "version": "1.0"})
        connect.PROVIDERS.setdefault("Stub", {"exe": "x", "shares": "Codex"})
        try:
            self.assertEqual(connect.state()["Stub"]["state"], "signed_in")
            connect.record_probe("Stub", "stub", True)
            row = connect.state()["Stub"]; self.assertEqual(row["state"], "connected"); self.assertEqual(row["probe_model"], "stub"); self.assertRegex(row["probe_time"], r"^\d\d:\d\d$")
            self.assertEqual(row["shares"], "Codex")
        finally:
            connect.PROVIDERS.pop("Stub", None)
            with connect._lock: connect._cache.pop("Stub", None)

    def test_defaults(self) -> None:
        """Claude seats and the World take the first model that answers; Codex villagers default to gpt-5.6-luna."""
        g = game.Game(engine.now_id()); self.assertEqual((g.model_a["model"], g.model_b["model"], g.world_model["model"]), ("", "gpt-5.6-luna", ""))
        self.assertEqual(g.model_b["provider"], "Codex")


class CodexModels(unittest.TestCase):
    def test_every_codex_launch_asks_for_low_reasoning_effort(self) -> None:
        for k in ("cmd", "ro_cmd"):
            self.assertIn('exec -c model_reasoning_effort="low" ', agents.PROVIDERS["Codex"][k], k)
        self.assertNotIn("model_reasoning_effort", agents.PROVIDERS["Claude Code"]["cmd"])

    def test_a_save_on_a_retired_codex_model_moves_to_luna_with_one_line(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="terra-mig-")); engine.GAMES = tmp; game.GAMES = tmp
        try:
            g = game.Game(engine.now_id()); g.model_b = {"provider": "Codex", "model": "gpt-5.6"}
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "claude-haiku-4-5", "color": "#d0a92c"}, {"name": "Bett", "provider": "Codex", "model": "gpt-5.5", "color": "#7f9a5c"},
                       {"name": "Cuthbert", "provider": "Codex", "model": "gpt-5.4", "color": "#b4553f"}, {"name": "Dimity", "provider": "Codex", "model": "gpt-6-astra", "color": "#a79d84"}]
            g.cli_sessions = {"1": "old-session"}; g.save(); r = game.Run(g)
            self.assertEqual([x["model"] for x in g.seats], ["claude-haiku-4-5", "gpt-5.6-luna", "gpt-5.6-luna", "gpt-6-astra"]); self.assertEqual(g.model_b["model"], "gpt-5.6-luna")
            self.assertNotIn("1", g.cli_sessions, "a moved seat starts a fresh session")
            notes = [e["text"] for e in g.transcript if e["kind"] == "system"]; self.assertEqual(len(notes), 1)
            self.assertIn("gpt-5.4, gpt-5.5 are no longer offered; Bett, Cuthbert now play on gpt-5.6-luna.", notes[0])
            r2 = game.Run(game.Game(g.id, __import__("json").loads((g.dir / "game.json").read_text(encoding="utf-8"))))
            self.assertEqual(len([e for e in r2.g.transcript if e["kind"] == "system"]), 1, "the line is written once")
        finally: shutil.rmtree(tmp, ignore_errors=True)

    def test_the_codex_lists(self) -> None:
        self.assertEqual(agents.PROVIDERS["Codex"]["models"], ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.3-codex-spark"])
        self.assertNotIn("gpt-5.5", agents.PROVIDERS["Codex"]["models"]); self.assertIn(game.CODEX_DEFAULT, agents.PROVIDERS["Codex"]["models"])

    def test_there_is_one_codex_row_and_it_is_the_installed_one(self) -> None:
        """No pinned copy fetched per run: the Codex a game uses is whatever version is on PATH."""
        self.assertEqual([n for n in agents.PROVIDERS if "codex" in n.lower()], ["Codex"])
        self.assertEqual([n for n in connect.PROVIDERS if "codex" in n.lower()], ["Codex"])
        self.assertEqual(connect.PROVIDERS["Codex"]["exe"], "codex")
        for prov in list(agents.PROVIDERS.values()) + list(connect.PROVIDERS.values()):
            for v in prov.values():
                self.assertNotIn("@openai/codex@latest", str(v))


if __name__ == "__main__":
    unittest.main()
