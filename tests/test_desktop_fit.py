"""Desktop map fit, checked in a real headless Chrome: at 1366x768, 1920x1080 and 2560x1440 every place label and every token
is inside the map's box, the box sits between the tabs and the fate box with the hint line below it, and the page does not
scroll. The check also closes the left rail to see the fit recomputed. Skipped where Chrome or node is not installed.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import json, os, random, shutil, subprocess, sys, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import connect, engine, game, server  # noqa: E402

CHROME = Path(os.environ.get("TERRA_CHROME") or r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SIZES = ["1366x768", "1920x1080", "2560x1440"]
JS = (ROOT / "frontend" / "map.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def valley() -> engine.World:
    """Four people, one of them at the southernmost place, so the lowest token is the one that matters."""
    w = engine.World(); rng = random.Random(3); places = list(w.map); lowest = max(w.map, key=lambda p: w.map[p]["y"])
    for i in range(4):
        nm = ["Aldous", "Bett", "Cuthbert", "Dimity"][i]; c = engine.roll_character(nm, i + 1, rng, places); c["trade"] = "villager"
        c["location"] = c["home"] = lowest if i < 2 else places[i]; c["voice"] = engine.roll_voice(c, rng); w.characters[nm] = c
    w.ledger = engine.starting_ledger(4, len(w.map)); w.seed_places(); w.created = True; w.day = 2; w.seed_duties(rng); w.assign_day(rng)
    return w


class DesktopFit(unittest.TestCase):
    def test_the_hint_is_a_line_below_the_box_and_the_box_is_what_is_left(self) -> None:
        self.assertIn('<div id="mapHint">Drag a person to move them.', HTML); self.assertNotIn('<span class="note">Drag a person', HTML, "not an overlay on the art")
        self.assertIn("#map.on+#mapHint{display:block}", CSS); self.assertIn("#mapHint,#map.on+#mapHint{display:none}", CSS[CSS.index("@media (max-width:820px)"):], "hidden on the phone")
        self.assertIn("#mapHint{display:none;flex:0 0 auto;", CSS, "one line in the column, so the map's box is what is left above it")
        self.assertIn("const contentBottom=m=>Math.max(AH,Math.max(0,...Object.values(m||{}).map(d=>+d.y||0))+200);", JS, "the box runs on below the lowest place for the people standing there")
        self.assertIn("H=contentBottom(m);svg.setAttribute('viewBox',`0 0 ${W} ${H}`);", JS)
        self.assertIn("new ResizeObserver(()=>{if(view.user)applyView();else resetView()})", JS, "the fit is recomputed whenever the box changes size")

    def test_in_headless_chrome_at_three_sizes_everything_is_inside_the_box_and_the_page_does_not_scroll(self) -> None:
        if not CHROME.exists() or not shutil.which("node"): self.skipTest("Chrome or node is not installed here")
        tmp = Path(tempfile.mkdtemp(prefix="terra-fit-")); engine.GAMES = tmp; game.GAMES = tmp; server.GAMES = tmp
        st, rv = connect.start, server.refresh_versions; connect.start = lambda: None; server.refresh_versions = lambda: None
        try:
            app = server.App(); g = app.run.g; g.draft = False; g.dir = tmp / g.id; g.world = valley(); w = g.world; g.title = "Fit check"
            g.seats = [{"name": "World", "provider": "Claude Code", "model": "x", "color": "#d0a92c"}] + [{"name": n, "provider": "Claude Code", "model": "x", "color": "#7f9a5c"} for n in w.characters]
            app.run._sync_terms(); g.save()
            srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, "fit")); port = srv.server_address[1]
            th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
            try:
                r = subprocess.run(["node", str(ROOT / "tests" / "map_fit_check.js"), f"http://127.0.0.1:{port}/?token=fit", str(CHROME)] + SIZES, capture_output=True, text=True, timeout=240)
            finally:
                srv.shutdown(); srv.server_close()
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(ln) for ln in r.stdout.splitlines() if ln.startswith("{")]
            self.assertEqual([x["size"] for x in rows], SIZES)
            lowest = max(w.map, key=lambda p: w.map[p]["y"])
            for row in rows:
                for state in ("open", "railClosed"):
                    x = row[state]; tag = f"{row['size']} {state}"
                    self.assertEqual(x["badLabels"], [], f"{tag}: place labels outside the box"); self.assertEqual(x["badToks"], [], f"{tag}: tokens outside the box")
                    self.assertIn(lowest, [l["n"] for l in x["labels"]]); self.assertEqual(len(x["toks"]), 4, tag)
                    self.assertAlmostEqual(x["box"][0], x["tabsBottom"], delta=1.5, msg=f"{tag}: the box starts under the tabs")
                    self.assertAlmostEqual(x["box"][1], x["hint"][0], delta=1.5, msg=f"{tag}: the hint line starts where the box ends")
                    self.assertAlmostEqual(x["hint"][1], x["fateTop"], delta=1.5, msg=f"{tag}: the fate box starts under the hint line")
                    self.assertEqual(x["hint"][3], "block", tag); self.assertGreater(x["hint"][2], 10, tag); self.assertLess(x["hint"][2], 40, f"{tag}: one small line")
                    sw, cw, sh, ch, sx, sy = x["scroll"]; self.assertLessEqual(sw, cw + 1, f"{tag}: the page scrolls sideways"); self.assertLessEqual(sh, ch + 1, f"{tag}: the page scrolls"); self.assertEqual((sx, sy), (0, 0))
                    self.assertAlmostEqual(x["view"], 1, delta=0.001, msg=f"{tag}: the desktop keeps the fit")
                self.assertGreater(row["railClosed"]["box"][3] - row["railClosed"]["box"][2], row["open"]["box"][3] - row["open"]["box"][2], f"{row['size']}: closing the rail widened the box")
        finally:
            connect.start, server.refresh_versions = st, rv; shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
