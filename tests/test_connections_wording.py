"""Connections says what it is doing, in the convener's words.

The word on screen is "test", never "probe": the button is Test, a green row is Connected, an amber one is
Signed in, not tested, a red one is Not signed in or Not installed. Nothing runs out of sight: a test carries
a spinner and its live line from the moment it starts, Start counts the seats it is testing and names them as
they answer, and a sign in says it is waiting for you until the CLI reports otherwise. The code and the test
names keep "probe" for themselves.
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations
import os, re, sys, threading, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "tests"))
import connect, server  # noqa: E402
from test_runners import Base  # noqa: E402

JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")

# Where the word survives without a person meeting it: the route and the JSON field, which are API names
# and are documented as such. Everything a person reads has to say "test".
ALLOWED = ("/connect/probe", 'data-do="probe"', "d==='probe'", "p.probes")


def user_facing(text: str) -> list[str]:
    """Every line that still shows the convener the word probe, the route name aside."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line
        for a in ALLOWED: stripped = stripped.replace(a, "")
        if re.search(r"probe", stripped, re.I): out.append(f"{i}: {line.strip()[:120]}")
    return out


class TheWord(unittest.TestCase):
    def test_the_frontend_never_shows_the_word_probe(self) -> None:
        self.assertEqual(user_facing(JS), [], "app.js")
        self.assertEqual(user_facing(HTML), [], "index.html")
        self.assertEqual(user_facing(CSS), [], "style.css")

    def test_the_readme_never_shows_the_word_probe(self) -> None:
        self.assertEqual(user_facing(README), [], "README.md")

    def test_the_button_is_test(self) -> None:
        self.assertIn('data-do="probe">Test</button>', JS)
        self.assertNotIn(">Probe</button>", JS)

    def test_the_four_labels(self) -> None:
        m = re.search(r"const CONN_LABEL=\{(.*?)\};", JS)
        self.assertTrue(m, "the labels moved")
        for want in ("connected:'Connected'", "signed_in:'Signed in, not tested'",
                     "not_installed:'Not installed'", "not_signed_in:'Not signed in'"):
            self.assertIn(want, m.group(1))

    def test_a_row_that_has_answered_says_which_model_and_when(self) -> None:
        """claude-fable-5-1 answered at 11:39, to the minute, not to the second."""
        with connect._lock:
            connect._cache["Stub row"] = (time.monotonic(), {"name": "Stub row", "state": "connected", "detail": "", "installed": True, "exe": "x"})
        connect.PROVIDERS.setdefault("Stub row", {"exe": "x"})
        try:
            connect.record_probe("Stub row", "claude-fable-5-1", True)
            row = connect.state()["Stub row"]
            self.assertRegex(row["detail"], r"^claude-fable-5-1 answered at \d\d:\d\d\.")
            self.assertRegex(row["probe_time"], r"^\d\d:\d\d$")
        finally:
            connect.PROVIDERS.pop("Stub row", None)
            with connect._lock: connect._cache.pop("Stub row", None)
            with connect._probe_lock: connect._probes.pop("Stub row", None)

    def test_an_untested_row_says_so_and_names_the_button(self) -> None:
        with connect._lock:
            connect._cache["Stub row"] = (time.monotonic(), {"name": "Stub row", "state": "connected", "detail": "", "installed": True, "exe": "x"})
        connect.PROVIDERS.setdefault("Stub row", {"exe": "x"})
        try:
            row = connect.state()["Stub row"]
            self.assertEqual(row["state"], "signed_in")
            self.assertIn("No model has answered a test yet", row["detail"])
            self.assertIn("press Test", row["detail"])
            self.assertNotIn("probe", row["detail"].lower())
        finally:
            connect.PROVIDERS.pop("Stub row", None)
            with connect._lock: connect._cache.pop("Stub row", None)


class NothingRunsOutOfSight(unittest.TestCase):
    def test_a_running_row_carries_a_spinner_and_its_live_line(self) -> None:
        self.assertIn("const running=!!(job&&!job.done)", JS)
        self.assertIn('<span class="spin sm"></span>', JS)
        self.assertIn(".spin.sm{", CSS)
        self.assertIn("(job.lines||[]).slice(-1)[0]||'Testing...'", JS, "a running test shows its own last line")

    def test_the_test_button_is_gone_while_a_test_runs(self) -> None:
        self.assertIn("&&!running?`<button class=\"btn act\" data-do=\"probe\">Test</button>`", JS)

    def test_a_sign_in_says_it_is_waiting_for_you(self) -> None:
        self.assertIn("Waiting for you to sign in...", JS)
        self.assertNotIn("Waiting for the sign in to finish", JS)
        self.assertLessEqual(connect.LOGIN_POLL, 5.0, "the row has to turn green about as soon as the CLI says so")

    def test_the_start_banner_exists_and_counts(self) -> None:
        self.assertIn('id="startTest"', HTML)
        self.assertIn("#startTest{", CSS)
        self.assertIn("Testing seats: ${tst.done} of ${tst.total}", JS)


class TestsAreJobs(Base):
    """A test is a job like Install and Sign in, so a row is never quietly busy."""

    def app_for(self, r) -> server.App:
        """An App around one Run, without touching the convener's own games folder."""
        app = server.App.__new__(server.App)
        app.lock = threading.Lock(); app.last_conn = ""; app.runs = {r.g.id: r}; app.gid = r.g.id
        return app

    def test_a_test_writes_its_lines_under_the_row_and_ends(self) -> None:
        connect.clear_job("Stub")
        self.assertFalse(connect.testing("Stub"))
        connect.begin_test("Stub")
        try:
            self.assertTrue(connect.testing("Stub"))
            j = connect.job("Stub")
            self.assertEqual(j["kind"], "test"); self.assertFalse(j["done"])
            connect.test_line("Stub", "Testing stub...")
            self.assertEqual(j["lines"], ["Testing stub..."])
            connect.end_test("Stub", True)
            self.assertTrue(j["done"]); self.assertTrue(j["ok"]); self.assertFalse(connect.testing("Stub"))
        finally:
            connect.clear_job("Stub")

    def test_the_test_button_shows_a_line_for_every_model_it_tries(self) -> None:
        _, r = self.make(); app = self.app_for(r); connect.clear_job("Stub")
        try:
            self.assertEqual(app.probe("Stub", "stub"), "Testing Stub...")
            self.wait(lambda: (connect.job("Stub") or {}).get("done"), 90, "the test")
            j = connect.job("Stub")
            self.assertEqual(j["kind"], "test"); self.assertTrue(j["ok"])
            self.assertEqual(j["lines"][0], "Testing stub...")
            self.assertRegex(j["lines"][-1], r"^stub answered at \d\d:\d\d$")
            self.assertRegex(app.last_conn, r"^stub answered at \d\d:\d\d$")
        finally:
            connect.clear_job("Stub")

    def test_a_model_that_will_not_answer_says_why(self) -> None:
        _, r = self.make(); app = self.app_for(r); connect.clear_job("Stub")
        try:
            app.probe("Stub", "bad")
            self.wait(lambda: (connect.job("Stub") or {}).get("done"), 90, "the test")
            j = connect.job("Stub")
            self.assertFalse(j["ok"])
            self.assertTrue(j["lines"][-1].startswith("bad did not answer: "), j["lines"])
            self.assertTrue(app.last_conn.startswith("bad did not answer: "), app.last_conn)
        finally:
            connect.clear_job("Stub")

    def test_the_terminal_pane_calls_it_a_test_too(self) -> None:
        """The pane the convener watches gets the header of every call. A test is headed as one."""
        g, r = self.make(); g.seats = [r.world_seat()]; r._sync_terms(); g.save()
        ok, _ = r.probe_model("Stub", "stub")
        self.assertTrue(ok)
        lines = list(r.terms[0]["lines"])
        self.assertTrue(any("World: test Stub stub" in ln for ln in lines), lines)
        self.assertFalse([ln for ln in lines if "probe" in ln.lower()], lines)

    def test_a_second_test_does_not_start_on_top_of_a_running_one(self) -> None:
        connect.clear_job("Stub"); connect.begin_test("Stub")
        try:
            _, r = self.make()
            self.assertEqual(self.app_for(r).probe("Stub", "stub"), "Stub is being tested already.")
        finally:
            connect.end_test("Stub", False); connect.clear_job("Stub")


class StartCountsTheSeats(Base):
    def test_the_count_the_names_and_the_clean_finish(self) -> None:
        """Testing seats: 3 of 8, with the names as they finish. Read at every step, not sampled: once a
        model is known good the rest of the seats answer from the record and the count runs to the end at once."""
        g, r = self.make()
        g.seats = [r.world_seat()] + [{"name": n, "provider": "Stub", "model": "stub", "color": "#7f9a5c"} for n in ("Bett", "Cuthbert")]
        r._sync_terms(); g.save()
        steps: list[tuple[int, int, list[str]]] = []
        nows: list[str] = []
        orig_tested, orig_probe = r._tested, r.probe_model
        def tested(who: str) -> None:
            orig_tested(who); steps.append((r.testing["done"], r.testing["total"], list(r.testing["names"])))
        def probe_model(provider: str, model: str, i: int = 0):
            nows.append(r.testing.get("now", "")); return orig_probe(provider, model, i)
        r._tested, r.probe_model = tested, probe_model
        self.assertTrue(r.preflight())
        self.assertEqual([d for d, _, _ in steps], [1, 2, 3], "every seat is counted as it answers")
        self.assertEqual({t for _, t, _ in steps}, {3}, "three seats to test")
        self.assertEqual(steps[-1][2], ["World", "Bett", "Cuthbert"], "named in the order they finish")
        self.assertEqual(nows[0], "World", "the seat under test is named while its test runs")
        self.assertEqual(r.testing, {}, "the banner goes when Start is done")
        self.assertIsNone(r.current)

    def test_the_banner_goes_even_when_a_seat_refuses(self) -> None:
        _, r = self.make(); self.fail_with("auth", 9)
        self.assertFalse(r.preflight())
        self.assertEqual(r.testing, {}, "a refusal leaves no banner claiming a test is still running")
        self.assertIn("refused the test", r.blocked)
        self.assertNotIn("probe", r.blocked.lower())


if __name__ == "__main__":
    unittest.main()
