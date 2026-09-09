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
        self.assertIn("svg.parentNode.style.background=''", JS, "a letterbox, when there is one, shows the page behind it"); self.assertNotIn("style.background=deep", JS)
        self.assertIn("background:var(--bg)}#map.on", CSS, "the page background, not the map's ground")
        phone = CSS[CSS.index("@media (max-width:820px),(max-height:520px){"):]
        self.assertIn("#center{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}", phone, "on the phone the map sits between the header and the tabs")
        self.assertIn("(max-width:820px),(max-height:520px)", APP); self.assertIn("(max-width:820px),(max-height:520px)", JS, "a phone on its side is still a phone")

    def test_weather_is_drawn_inside_the_map_only(self) -> None:
        self.assertIn("el('clipPath',{id:'mapClip'},d);el('rect',{x:0,y:0,width:W,height:H},cp)", JS)
        self.assertIn("el('g',{id:'viewport','clip-path':'url(#boxClip)'},svg)", JS, "everything that pans and zooms is clipped to the visible box")
        self.assertIn("el('clipPath',{id:'boxClip'},d);el('rect',{id:'boxRect'", JS); self.assertIn("br.setAttribute('x',b.x0.toFixed(1))", JS, "the box clip follows the box's shape")
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
        self.assertIn("pinch={d:Math.hypot(a.x-b.x,a.y-b.y),k:view.k}", JS, "two fingers pinch"); self.assertIn("view.tx=pan.tx+dx;view.ty=pan.ty+dy;view.user=true;applyView()", JS, "one finger or the mouse drags")
        self.assertIn("const KMIN=1;let home={k:1,tx:0,ty:0};", JS); self.assertIn("const kmax=()=>5*home.k;", JS, "pinch runs from the resting level out to fit and in to five times it")
        self.assertIn("function clampView()", JS, "the map never leaves its box"); self.assertIn("view.tx=aw>=b.w-0.5?Math.max(b.x0+b.w-aw,Math.min(b.x0,view.tx)):b.x0+(b.w-aw)/2;", JS, "clamped against the visible box, not the art")
        self.assertIn("const tokScale=()=>Math.min(2.4,0.85/(view.k*U))", JS, "tokens are counter scaled against the zoom and the screen")
        self.assertIn("scale(${tokScale().toFixed(4)})", JS); self.assertIn(".node .nmw", JS, "place names too")
        self.assertIn('id="mapReset"', HTML); self.assertIn("function resetView(){U=unit();const hv=homeView();view={k:hv.k,tx:hv.tx,ty:hv.ty,user:false", JS, "Reset returns to the resting view")
        self.assertIn("rb.style.display=atHome()?'none':''", JS)
        self.assertIn("function viewPoint(svg,evt)", JS); self.assertIn("const p=viewPoint(svg,e);t._x=p.x;t._y=p.y", JS, "dragging a person goes through the view")
        self.assertIn("touch-action:none", CSS)

    def test_the_day_line_is_a_bar_along_the_top_edge_inside_the_map(self) -> None:
        self.assertIn('<div id="dayBar"><span id="dayTitle"></span><span id="dayText"></span></div>', HTML)
        self.assertIn("#dayBar{position:absolute;left:0;right:0;top:0;height:26px", CSS, "pinned to the top of the box"); self.assertNotIn("function layoutBar()", JS)
        self.assertNotIn("id:'dayText'", JS, "no text floating over the art"); self.assertNotIn("class:'title',filter:'url(#halo)'},fr)", JS)
        self.assertIn("`Day ${s.day}${(s.day_report||{}).season?', '+s.day_report.season:''}${s.weather?', '+s.weather:''}, grain", JS)

    def test_a_phone_in_portrait_covers_the_box_centered_on_the_people(self) -> None:
        self.assertIn("const portraitPhone=()=>{const b=boxUnits();return mobile()&&b.h>b.w};", JS)
        self.assertIn("const coverK=()=>{const b=boxUnits();return Math.max(b.w/W,b.h/H)};", JS, "the art covers the whole box")
        self.assertIn("function homeView(){if(!portraitPhone())return {k:1,tx:0,ty:0};const b=boxUnits(),k=coverK(),c=centroid();return {k,tx:b.x0+b.w/2-c.x*k,ty:b.y0+b.h/2-c.y*k}}", JS, "centered on the middle of the people; a phone on its side and the desktop keep the fit")
        self.assertIn("function centroid(){const ts=Object.values(tokens)", JS)
        self.assertIn("function dblTap(px,py){if(atHome())zoomAt(px,py,2);else resetView()}", JS, "double tap toggles the resting view and 2x on the spot")
        self.assertIn("if(lastTap&&now-lastTap.t<350&&Math.hypot(e.clientX-lastTap.x,e.clientY-lastTap.y)<30){lastTap=null;dblTap(p.x,p.y)}", JS)
        self.assertIn("new ResizeObserver(()=>{if(view.user)applyView();else resetView()})", JS, "turning the phone re-rests the view unless the player has moved it")
        self.assertIn("fr.style.opacity=view.k>1.001?'0':''", JS, "the art's frame is a frame of the whole map only")

    def test_the_map_still_parses(self) -> None:
        r = subprocess.run(["node", "--check", str(ROOT / "frontend" / "map.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
