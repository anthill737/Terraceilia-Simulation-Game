"""The map fits the screen: it fills its box with its own ground, weather stays inside it, labels never overlap, pan and zoom
keep tokens readable, and the day line is a bar along the top edge inside the map. These read the frontend sources.
Run from the repo root:  python -m pytest tests -q"""
from __future__ import annotations
import re, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "frontend" / "map.js").read_text(encoding="utf-8")
APP = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


class MapFit(unittest.TestCase):
    def test_the_map_fills_its_box_and_the_leftover_is_map_ground(self) -> None:
        self.assertIn('viewBox="0 0 1000 780" preserveAspectRatio="xMidYMid meet"', HTML, "the aspect ratio is kept and the map is scaled to fit")
        self.assertIn("#map{flex:1;min-height:0;overflow:hidden", CSS); self.assertIn("#map svg{width:100%;height:100%", CSS)
        self.assertIn("svg.parentNode.style.background=deep", JS, "the space around the art is the map's own deep ground, set from its palette")
        self.assertNotIn("background:var(--bg)}#map.on", CSS, "not the page background")
        phone = CSS[CSS.index("@media (max-width:820px),(max-height:520px){"):]
        self.assertIn("#center{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}", phone, "on the phone the map sits between the header and the tabs")
        self.assertIn("(max-width:820px),(max-height:520px)", APP); self.assertIn("(max-width:820px),(max-height:520px)", JS, "a phone on its side is still a phone")

    def test_weather_is_drawn_inside_the_map_only(self) -> None:
        self.assertIn("el('clipPath',{id:'mapClip'},d);el('rect',{x:0,y:0,width:W,height:H},cp)", JS)
        self.assertIn("el('g',{id:'viewport','clip-path':'url(#mapClip)'},svg)", JS, "everything that pans and zooms is clipped to the art")
        self.assertIn("el('g',{id:'weather','clip-path':'url(#mapClip)'},vw)", JS, "rain, snow and fog fall inside the map and nowhere else")
        self.assertNotIn("el('g',{id:'weather'},svg)", JS)

    def test_labels_avoid_each_other_and_activity_is_one_line(self) -> None:
        self.assertIn("function layoutLabels()", JS); self.assertIn("const cands=[[0,0],[0,20],[36,-10],[-36,-10]", JS, "below, then beside, with offsets")
        self.assertIn("el('line',{class:'lead'", JS); self.assertIn("ld.style.display=on?'':'none'", JS, "a short leader line when a label moved")
        self.assertIn("const trunc=t=>{t=String(t||'').replace(/\\s+/g,' ').trim();return t.length>24?t.slice(0,23).replace(/[\\s,;:]+$/,'')+'.':t}", JS, "one line, cut with a full stop")
        self.assertIn("t.querySelector('.lbl').style.display='';t.querySelector('.act').style.display=(!mobile()||hover===c.name)?'':'none';", JS, "names always; the activity on the phone only for the person tapped")
        self.assertIn("if(mobile()){hover=hover===name?null:name;render(S_)}", JS, "a tap shows it")
        self.assertIn("if(busy){layoutLabels();raf=requestAnimationFrame(tick)}", JS, "laid out again after every move")

    def test_pan_and_zoom_keep_tokens_readable_and_reset_comes_back(self) -> None:
        self.assertIn("svg.addEventListener('wheel'", JS); self.assertIn("zoomAt(p.x,p.y,e.deltaY<0?1.15:1/1.15)", JS)
        self.assertIn("pinch={d:Math.hypot(a.x-b.x,a.y-b.y),k:view.k}", JS, "two fingers pinch"); self.assertIn("view.tx=pan.tx+dx;view.ty=pan.ty+dy;applyView()", JS, "one finger or the mouse drags")
        self.assertIn("const KMIN=1,KMAX=5", JS); self.assertIn("function clampView()", JS, "the map never leaves its box")
        self.assertIn("const tokScale=()=>Math.min(2.4,0.85/(view.k*U))", JS, "tokens are counter scaled against the zoom and the screen")
        self.assertIn("scale(${tokScale().toFixed(4)})", JS); self.assertIn(".node .nmw", JS, "place names too")
        self.assertIn('id="mapReset"', HTML); self.assertIn("function resetView(){view={k:1,tx:0,ty:0};applyView()}", JS)
        self.assertIn("function viewPoint(svg,evt)", JS); self.assertIn("const p=viewPoint(svg,e);t._x=p.x;t._y=p.y", JS, "dragging a person goes through the view")
        self.assertIn("touch-action:none", CSS)

    def test_the_day_line_is_a_bar_along_the_top_edge_inside_the_map(self) -> None:
        self.assertIn('<div id="dayBar"><span id="dayTitle"></span><span id="dayText"></span></div>', HTML)
        self.assertIn("#dayBar{position:absolute;left:0;top:0;height:26px", CSS)
        self.assertIn("function layoutBar()", JS); self.assertIn("const left=(r.width-W*U)/2+6*U,top=(r.height-H*U)/2+6*U", JS, "on the art's top edge whatever the letterbox")
        self.assertNotIn("id:'dayText'", JS, "no text floating over the art"); self.assertNotIn("class:'title',filter:'url(#halo)'},fr)", JS)
        self.assertIn("`Day ${s.day}${(s.day_report||{}).season?', '+s.day_report.season:''}${s.weather?', '+s.weather:''}, grain", JS)

    def test_the_map_still_parses(self) -> None:
        r = subprocess.run(["node", "--check", str(ROOT / "frontend" / "map.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
