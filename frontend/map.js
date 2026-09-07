// Terraceilia overworld. Procedural SVG drawn from the map's own data: its palette, its water, its sky,
// and the land each place stands on. The built-in valley keeps the fixed river and hills it has always had.
const MapView=(()=>{
 const NS='http://www.w3.org/2000/svg';const $=id=>document.getElementById(id);
 const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
 let built=false,drag=null,selected=null,S_=null,tokens={},hover=null,weather={},sky='day';
 function el(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e}
 function svgPoint(svg,evt){const pt=svg.createSVGPoint();pt.x=evt.clientX;pt.y=evt.clientY;return pt.matrixTransform(svg.getScreenCTM().inverse())}
 const rng=(seed=>()=>(seed=(seed*9301+49297)%233280)/233280);

 // ---------- what a place is, and what it stands on
 const KINDS=['castle','town','village','inn','chapel','mill','forest','fields','water','ruin','market','farm','tower','cave','road','other'];
 const FEATURES=['mountain','peak','cliff','island','crater','crag','forest','marsh','plain','coast','none'];
 const DANGER=new Set(['road','forest','cave','ruin']);
 const kindOf=(n,d)=>(d&&KINDS.includes(d.kind))?d.kind:'other';
 const featOf=d=>(d&&FEATURES.includes(d.feature))?d.feature:'none';
 const elevOf=d=>Math.max(0,Math.min(3,+(d&&d.elevation)||0));
 const styleOf=s=>{const st=(s&&s.map_style)||{};return {palette:st.palette||{},water:st.water||{type:'none'},sky:st.sky||'day'}};
 function shade(hex,f){const h=/^#([0-9a-f]{6})$/i.exec(hex||'');if(!h)return '#1d3626';const n=parseInt(h[1],16);
  const r=Math.round(((n>>16)&255)*f),g=Math.round(((n>>8)&255)*f),b=Math.round((n&255)*f);
  return '#'+[r,g,b].map(x=>Math.max(0,Math.min(255,x)).toString(16).padStart(2,'0')).join('')}
 function wolfPlace(m){const es=Object.entries(m||{});const pick=k=>es.find(([n,d])=>kindOf(n,d)===k);const hit=pick('fields')||pick('farm')||pick('forest')||pick('road');return hit?hit[1]:(es.length?es.reduce((a,b)=>b[1].y>a[1].y?b:a)[1]:null)}

 // ---------- defs: gradients built from this world's own colours
 function defs(svg,st){const d=el('defs',{},svg);const pal=st.palette||{};
  const base=pal.ground||'#2a4a33',mid=pal.mid||shade(base,.72),deep=pal.deep||shade(base,.40);
  const g1=el('radialGradient',{id:'ground',cx:'50%',cy:'45%',r:'75%'},d);el('stop',{offset:'0%','stop-color':base},g1);el('stop',{offset:'55%','stop-color':mid},g1);el('stop',{offset:'100%','stop-color':deep},g1);
  const vig=el('radialGradient',{id:'vig',cx:'50%',cy:'50%',r:'72%'},d);el('stop',{offset:'55%','stop-color':'#000','stop-opacity':0},vig);el('stop',{offset:'100%','stop-color':'#000','stop-opacity':.6},vig);
  const hill=el('linearGradient',{id:'hill',x1:0,y1:0,x2:0,y2:1},d);el('stop',{offset:'0%','stop-color':'#3d4658'},hill);el('stop',{offset:'100%','stop-color':'#1c222c'},hill);
  const hg=el('linearGradient',{id:'hillgen',x1:0,y1:0,x2:0,y2:1},d);el('stop',{offset:'0%','stop-color':shade(base,2.05)},hg);el('stop',{offset:'100%','stop-color':shade(base,1.05)},hg);
  const wc=(st.water&&st.water.color)||'#4d9bbd';const lava=(st.water&&st.water.type)==='lava';
  const water=el('linearGradient',{id:'water',x1:0,y1:0,x2:1,y2:0},d);
  el('stop',{offset:'0%','stop-color':shade(wc,.62)},water);el('stop',{offset:'50%','stop-color':wc},water);el('stop',{offset:'100%','stop-color':shade(wc,.62)},water);
  const molten=el('radialGradient',{id:'molten'},d);el('stop',{offset:'0%','stop-color':'#ffd08a'},molten);el('stop',{offset:'45%','stop-color':wc},molten);el('stop',{offset:'100%','stop-color':shade(wc,.5)},molten);
  const cast=el('radialGradient',{id:'cast'},d);el('stop',{offset:'0%','stop-color':wc,'stop-opacity':lava?.55:.20},cast);el('stop',{offset:'100%','stop-color':wc,'stop-opacity':0},cast);
  const tex=el('filter',{id:'tex',x:'0',y:'0',width:'100%',height:'100%'},d);el('feTurbulence',{type:'fractalNoise',baseFrequency:'0.9',numOctaves:3,seed:4,result:'n'},tex);el('feColorMatrix',{type:'saturate',values:0,in:'n',result:'g'},tex);const cm=el('feComponentTransfer',{in:'g',result:'a'},tex);el('feFuncA',{type:'table',tableValues:'0 0.18'},cm);el('feComposite',{in:'a',in2:'SourceGraphic',operator:'atop'},tex);
  const halo=el('filter',{id:'halo',x:'-20%',y:'-30%',width:'140%',height:'160%'},d);el('feMorphology',{in:'SourceAlpha',operator:'dilate',radius:2.2,result:'dl'},halo);el('feFlood',{'flood-color':'#0a0d0b','flood-opacity':.9,result:'c'},halo);el('feComposite',{in:'c',in2:'dl',operator:'in',result:'h'},halo);const mg=el('feMerge',{},halo);el('feMergeNode',{in:'h'},mg);el('feMergeNode',{in:'SourceGraphic'},mg);
  const sh=el('filter',{id:'shadow',x:'-40%',y:'-40%',width:'180%',height:'180%'},d);el('feDropShadow',{dx:0,dy:4,stdDeviation:3,'flood-color':'#000','flood-opacity':.7},sh);
  const glow=el('filter',{id:'glow',x:'-100%',y:'-100%',width:'300%',height:'300%'},d);el('feGaussianBlur',{stdDeviation:6,result:'b'},glow);const mg2=el('feMerge',{},glow);el('feMergeNode',{in:'b'},mg2);el('feMergeNode',{in:'SourceGraphic'},mg2);
  const fire=el('radialGradient',{id:'fire'},d);el('stop',{offset:'0%','stop-color':'#ffb347','stop-opacity':.9},fire);el('stop',{offset:'100%','stop-color':'#ff5a1f','stop-opacity':0},fire);
  const lamp=el('radialGradient',{id:'lamp'},d);el('stop',{offset:'0%','stop-color':'#ffd27a','stop-opacity':.85},lamp);el('stop',{offset:'100%','stop-color':'#ffd27a','stop-opacity':0},lamp);}

 // ---------- pieces of land
 function tree(g,x,y,sz,col,dark){el('ellipse',{cx:x+2,cy:y+sz*1.7,rx:sz*.9,ry:sz*.35,fill:'#000',opacity:.25},g);el('rect',{x:x-1,y:y+sz*1.1,width:2.4,height:sz*.7,fill:'#3b2a17'},g);
  el('path',{d:`M${x} ${y-sz*.4} L${x-sz} ${y+sz*1.3} L${x+sz} ${y+sz*1.3} Z`,fill:dark},g);el('path',{d:`M${x} ${y-sz} L${x-sz*.8} ${y+sz*.5} L${x+sz*.8} ${y+sz*.5} Z`,fill:col},g);el('path',{d:`M${x} ${y-sz*1.5} L${x-sz*.55} ${y-sz*.2} L${x+sz*.55} ${y-sz*.2} Z`,fill:col},g)}
 function hut(g,x,y,w,col){el('path',{d:`M${x-w} ${y+w*.8} L${x-w} ${y} L${x} ${y-w*.9} L${x+w} ${y} L${x+w} ${y+w*.8} Z`,fill:col,stroke:'#2a1d10','stroke-width':1},g);el('path',{d:`M${x-w-2} ${y+1} L${x} ${y-w} L${x+w+2} ${y+1}`,fill:'none',stroke:'#4a3520','stroke-width':2},g);el('rect',{x:x-w*.25,y:y+w*.2,width:w*.5,height:w*.6,fill:'#1a120a'},g)}
 function smoke(g,x,y){for(let i=0;i<3;i++){const c=el('circle',{cx:x,cy:y,r:2.5+i,fill:'#c9c9c9',opacity:0},g);el('animate',{attributeName:'cy',values:`${y};${y-30}`,dur:`${3+i}s`,begin:`${i}s`,repeatCount:'indefinite'},c);el('animate',{attributeName:'opacity',values:'0;.45;0',dur:`${3+i}s`,begin:`${i}s`,repeatCount:'indefinite'},c);el('animate',{attributeName:'cx',values:`${x};${x+6};${x-4}`,dur:`${3+i}s`,begin:`${i}s`,repeatCount:'indefinite'},c)}}
 function ridge(g,x,y,w,h,rock,cap){ // a mountain shoulder behind a place, snow or ash on its top
  h=Math.max(40,Math.min(h,y-46));            // never climbs out of the frame
  el('path',{d:`M${x-w} ${y} C${x-w*.55} ${y-h} ${x+w*.55} ${y-h} ${x+w} ${y} Z`,fill:'url(#hillgen)',opacity:.95},g);
  el('path',{d:`M${x-w*.62} ${y} C${x-w*.3} ${y-h*.72} ${x+w*.3} ${y-h*.72} ${x+w*.62} ${y} Z`,fill:rock,opacity:.92},g);
  if(cap)el('path',{d:`M${x-w*.22} ${y-h*.52} L${x} ${y-h*.75} L${x+w*.22} ${y-h*.52} L${x+w*.08} ${y-h*.47} L${x} ${y-h*.6} L${x-w*.09} ${y-h*.47} Z`,fill:cap,opacity:.9},g)}
 function rocks(g,x,y,R){for(let i=0;i<7;i++){const rx=x-52+R()*104,ry=y+10+R()*44,s=5+R()*11;
  el('path',{d:`M${rx-s} ${ry} L${rx-s*.4} ${ry-s*.9} L${rx+s*.5} ${ry-s*.7} L${rx+s} ${ry} Z`,fill:'#5a5f6b',stroke:'#20242c','stroke-width':1,opacity:.9},g)}}
 function reeds(g,x,y,R,col){for(let i=0;i<16;i++){const rx=x-70+R()*140,ry=y+18+R()*40,h=8+R()*14;
  el('path',{d:`M${rx} ${ry} Q${rx+3} ${ry-h*.6} ${rx+1} ${ry-h}`,stroke:col,'stroke-width':1.6,fill:'none',opacity:.75},g)}}
 function furrows(g,x,y,col){for(let i=0;i<9;i++)el('line',{x1:x-88+i*22,y1:y+34,x2:x-70+i*22,y2:y+96,stroke:col,'stroke-width':7,opacity:.5},g)}
 function cliffEdge(g,x,y,col){el('path',{d:`M${x-92} ${y+26} L${x+92} ${y+18}`,stroke:'#20242c','stroke-width':7,fill:'none','stroke-linecap':'round'},g);
  el('path',{d:`M${x-92} ${y+26} L${x+92} ${y+18}`,stroke:col,'stroke-width':2.5,fill:'none','stroke-linecap':'round',opacity:.8},g);
  for(let i=0;i<7;i++)el('line',{x1:x-80+i*27,y1:y+27,x2:x-86+i*27,y2:y+50,stroke:'#20242c','stroke-width':3,opacity:.7},g)}
 function craterRing(g,x,y){el('ellipse',{cx:x,cy:y+16,rx:78,ry:30,fill:'none',stroke:'#5a5f6b','stroke-width':6,opacity:.85},g);
  el('ellipse',{cx:x,cy:y+16,rx:62,ry:22,fill:'#1a1512',opacity:.75},g)}

 // ---------- terrain
 function terrain(svg,m,s){const g=el('g',{id:'terrain'},svg);const R=rng(11);const st=styleOf(s);
  el('rect',{x:0,y:0,width:1000,height:780,fill:'url(#ground)'},g);el('rect',{x:0,y:0,width:1000,height:780,fill:'#000',filter:'url(#tex)',opacity:.55},g);
  const acc=(st.palette||{}).accent||'#5d7a3a';
  for(let i=0;i<9;i++)el('ellipse',{cx:150+R()*700,cy:200+R()*450,rx:60+R()*160,ry:20+R()*40,fill:R()>.5?shade(acc,.55):shade(acc,.4),opacity:.30},g);
  if(s&&s.map_generated)terrainGenerated(g,m,R,st);else terrainBuiltin(g,R);
  el('rect',{x:0,y:0,width:1000,height:780,fill:'url(#vig)'},g)}

 function terrainBuiltin(g,R){
  el('path',{d:'M250 170 C330 40 660 40 760 170 Z',fill:'url(#hill)',opacity:.95},g);el('path',{d:'M300 170 C370 90 620 90 690 170 Z',fill:'#2c3340',opacity:.9},g);el('path',{d:'M180 190 C230 120 330 120 380 190 Z',fill:'#262d39',opacity:.9},g);el('path',{d:'M620 190 C690 110 800 110 850 190 Z',fill:'#262d39',opacity:.8},g);
  const river='M-20 555 C120 520 180 470 250 480 C330 495 360 560 470 560 C600 560 650 700 720 770';
  el('path',{d:river,stroke:'#12242f','stroke-width':30,fill:'none','stroke-linecap':'round',opacity:.9},g);el('path',{d:river,stroke:'url(#water)','stroke-width':18,fill:'none','stroke-linecap':'round',opacity:.95},g);
  const fl=el('path',{d:river,stroke:'#bfe6f5','stroke-width':3,fill:'none','stroke-linecap':'round','stroke-dasharray':'6 28',opacity:.5},g);el('animate',{attributeName:'stroke-dashoffset',values:'0;-68',dur:'2.5s',repeatCount:'indefinite'},fl);
  for(let i=0;i<10;i++)el('line',{x1:430+i*38,y1:640,x2:462+i*38,y2:770,stroke:'#5a5330','stroke-width':7,opacity:.55},g);
  const trees=[];for(let i=0;i<110;i++){const x=780+R()*230,y=50+R()*330;if(Math.hypot(x-880,y-190)<58)continue;trees.push([x,y,5+R()*7])}
  for(let i=0;i<26;i++){trees.push([20+R()*190,40+R()*300,4+R()*6])}for(let i=0;i<14;i++){trees.push([40+R()*140,600+R()*160,4+R()*5])}
  trees.sort((a,b)=>a[1]-b[1]).forEach(([x,y,s])=>tree(g,x,y,s,R()>.5?'#2f6b3d':'#26593a','#1c4128'));
  el('ellipse',{cx:770,cy:485,rx:95,ry:42,fill:'#5d7a3a',opacity:.45},g);
  for(let i=0;i<10;i++){const sx=700+R()*140,sy=455+R()*60;const s=el('ellipse',{cx:sx,cy:sy,rx:4,ry:2.6,fill:'#e8e6dc'},g);el('circle',{cx:sx+3,cy:sy,r:1.5,fill:'#3a3a3a'},g);el('animate',{attributeName:'cx',values:`${sx};${sx+6+R()*6};${sx}`,dur:`${8+R()*8}s`,repeatCount:'indefinite'},s)}}

 function terrainGenerated(g,m,R,st){
  const ps=Object.entries(m).map(([n,d])=>({n,d,k:kindOf(n,d),f:featOf(d),e:elevOf(d)}));
  const acc=(st.palette||{}).accent||'#8aa35a';const wt=(st.water||{}).type||'none';const wc=(st.water||{}).color||'#4d9bbd';
  const lava=wt==='lava';const snowy=/^#([e-f][0-9a-f]|d[89a-f])/i.test(acc);
  // the water this world has
  const wet=ps.filter(p=>p.f==='island'||p.f==='coast'||p.k==='water'||p.f==='crater');
  if(wt==='lake'||wt==='sea'||wt==='lava'){
   const anchors=wet.length?wet:[ps.reduce((a,b)=>b.d.y>a.d.y?b:a)];
   anchors.forEach(p=>{const x=p.d.x,y=p.d.y+(p.f==='island'?6:26);
    el('ellipse',{cx:x,cy:y,rx:wt==='sea'?190:150,ry:wt==='sea'?78:62,fill:shade(wc,.45),opacity:.95},g);
    const body=el('ellipse',{cx:x,cy:y,rx:wt==='sea'?172:132,ry:wt==='sea'?66:50,fill:lava?'url(#molten)':'url(#water)',opacity:.95},g);
    if(lava){el('animate',{attributeName:'opacity',values:'.85;1;.85',dur:'3.4s',repeatCount:'indefinite'},body);
     el('ellipse',{cx:x,cy:y,rx:150,ry:58,fill:'url(#cast)',filter:'url(#glow)'},g)}
    else{const fl=el('ellipse',{cx:x,cy:y,rx:100,ry:32,fill:'none',stroke:'#bfe6f5','stroke-width':2.5,'stroke-dasharray':'6 26',opacity:.45},g);
     el('animate',{attributeName:'stroke-dashoffset',values:'0;-64',dur:'3s',repeatCount:'indefinite'},fl)}});
   if(lava)ps.forEach(p=>{const near=anchors.some(a=>Math.hypot(a.d.x-p.d.x,a.d.y-p.d.y)<250);
    if(near)el('circle',{cx:p.d.x,cy:p.d.y+10,r:96,fill:'url(#cast)'},g)});   // lava lights what stands near it
  }else if(wt==='river'){
   const line=(wet.length>1?wet:ps).map(p=>p.d).sort((a,b)=>a.x-b.x);
   const pts=line.length>1?line:[{x:-20,y:520},{x:1020,y:640}];
   let dpath=`M${pts[0].x-120} ${pts[0].y+40}`;
   pts.forEach((p,i)=>{const nx=p.x,ny=p.y+34;dpath+=` Q${nx-60} ${ny+30} ${nx} ${ny}`;if(i===pts.length-1)dpath+=` Q${nx+80} ${ny+20} ${nx+140} ${ny+60}`});
   el('path',{d:dpath,stroke:shade(wc,.42),'stroke-width':30,fill:'none','stroke-linecap':'round',opacity:.9},g);
   el('path',{d:dpath,stroke:'url(#water)','stroke-width':18,fill:'none','stroke-linecap':'round',opacity:.95},g);
   const fl=el('path',{d:dpath,stroke:'#bfe6f5','stroke-width':3,fill:'none','stroke-dasharray':'6 28',opacity:.5},g);
   el('animate',{attributeName:'stroke-dashoffset',values:'0;-68',dur:'2.5s',repeatCount:'indefinite'},fl)}
  // the land each place stands on, low ground first so summits sit in front
  ps.slice().sort((a,b)=>a.d.y-b.d.y).forEach(p=>{const x=p.d.x,y=p.d.y+18,e=p.e;
   if(p.f==='mountain'||p.f==='peak'){const w=110+e*38,h=70+e*46;
    ridge(g,x,y+8,w,h,lava?'#3a2b26':'#2c3340',p.f==='peak'?(lava?'#c2521a':(snowy?'#e8eef2':'#cfd8e2')):null)}
   else if(p.f==='crag'){ridge(g,x,y+10,88,52,'#343a46',null);rocks(g,x,y,R)}
   else if(p.f==='cliff')cliffEdge(g,x,y,acc);
   else if(p.f==='crater')craterRing(g,x,y);
   else if(p.f==='island'){el('ellipse',{cx:x,cy:y+16,rx:74,ry:30,fill:shade(acc,.5),opacity:.95},g);el('ellipse',{cx:x,cy:y+12,rx:58,ry:22,fill:(st.palette||{}).ground||'#2a4a33',opacity:.95},g)}
   else if(p.f==='marsh')reeds(g,x,y,R,acc);
   else if(p.f==='coast')el('path',{d:`M${x-96} ${y+34} Q${x} ${y+18} ${x+96} ${y+34}`,stroke:shade(wc,1),'stroke-width':4,fill:'none',opacity:.7},g)});
  // trees around forests, then a light scatter that never lands on a place
  const near=(x,y,r)=>ps.some(p=>Math.hypot(p.d.x-x,p.d.y-y)<r);
  const ok=(x,y)=>x>15&&x<985&&y>70&&y<765&&!near(x,y,62);
  const trees=[];const dark=shade(acc,.5),leaf=acc;
  ps.filter(p=>p.f==='forest'||p.k==='forest').forEach(p=>{for(let i=0;i<70;i++){const a=R()*Math.PI*2,r=64+R()*96;
   const x=p.d.x+Math.cos(a)*r,y=p.d.y+Math.sin(a)*r*.7;if(ok(x,y))trees.push([x,y,5+R()*7])}});
  if(wt!=='lava')for(let i=0;i<34;i++){const x=R()*1000,y=60+R()*700;if(ok(x,y)&&!ps.some(p=>(p.f==='island'||p.k==='water'||p.f==='fields')&&Math.hypot(p.d.x-x,p.d.y-y)<150))trees.push([x,y,4+R()*5])}
  trees.sort((a,b)=>a[1]-b[1]).forEach(([x,y,s])=>tree(g,x,y,s,leaf,dark));
  ps.filter(p=>p.k==='fields'||p.f==='plain'&&p.k==='farm').forEach(p=>furrows(g,p.d.x,p.d.y,shade(acc,.7)))}

 // ---------- places, drawn by what they are
 const ICONS={
  castle:(g)=>{el('path',{d:'M-34 20 L-34 -10 L34 -10 L34 20 Z',fill:'#3a3f4a',stroke:'#14171d'},g);[-34,-14,6,26].forEach(x=>{el('rect',{x,y:-26,width:9,height:18,fill:'#4b5160',stroke:'#14171d'},g);el('rect',{x:x+1,y:-30,width:3,height:4,fill:'#4b5160'},g);el('rect',{x:x+5,y:-30,width:3,height:4,fill:'#4b5160'},g)});el('rect',{x:-4,y:-16,width:10,height:14,fill:'#9aa3b5'},g);el('rect',{x:-7,y:2,width:14,height:18,fill:'#0f1115'},g);
   el('line',{x1:-2,y1:-30,x2:-2,y2:-50,stroke:'#d9d9e0','stroke-width':1.5},g);const b=el('path',{d:'M-2 -50 L14 -46 L-2 -42 Z',fill:'#b3261e'},g);el('animate',{attributeName:'d',values:'M-2 -50 L14 -46 L-2 -42 Z;M-2 -50 L13 -49 L-2 -42 Z;M-2 -50 L14 -46 L-2 -42 Z',dur:'1.6s',repeatCount:'indefinite'},b);smoke(g,20,-12)},
  town:(g)=>{hut(g,-22,0,14,'#8a6a44');hut(g,4,-6,16,'#9a7a50');hut(g,26,4,12,'#7e6040');el('circle',{cx:-30,cy:18,r:5,fill:'#3a4a55',stroke:'#1a2228'},g);el('rect',{x:-32,y:8,width:4,height:10,fill:'#5a4a30'},g);smoke(g,4,-22);smoke(g,-22,-14)},
  inn:(g)=>{el('path',{d:'M-30 18 L-30 -6 L0 -26 L30 -6 L30 18 Z',fill:'#6b4a2e',stroke:'#2a1d10'},g);el('path',{d:'M-33 -4 L0 -28 L33 -4',fill:'none',stroke:'#4a3520','stroke-width':3},g);el('rect',{x:-7,y:2,width:14,height:16,fill:'#1a120a'},g);[-20,14].forEach(x=>el('rect',{x,y:-2,width:8,height:8,fill:'#ffd27a',class:'win'},g));
   const l=el('circle',{cx:22,cy:-2,r:14,fill:'url(#lamp)',class:'lamp'},g);el('animate',{attributeName:'r',values:'12;15;12',dur:'1.3s',repeatCount:'indefinite'},l);el('circle',{cx:22,cy:-2,r:3,fill:'#ffe6a8'},g);smoke(g,-10,-27)},
  chapel:(g)=>{el('path',{d:'M-20 20 L-20 -8 L0 -22 L20 -8 L20 20 Z',fill:'#a3a3b2',stroke:'#3a3a44'},g);el('path',{d:'M-2 -40 L2 -40 L2 -22 L-2 -22 Z',fill:'#e8e8ee'},g);el('path',{d:'M-8 -34 L8 -34 L8 -30 L-8 -30 Z',fill:'#e8e8ee'},g);el('path',{d:'M-6 20 L-6 6 L0 0 L6 6 L6 20 Z',fill:'#2a2530'},g);el('rect',{x:-14,y:0,width:5,height:8,fill:'#5a6a8a'},g);el('rect',{x:9,y:0,width:5,height:8,fill:'#5a6a8a'},g);
   [-30,-24,-18].forEach(x=>el('path',{d:`M${x} 26 L${x} 16 M${x-3} 19 L${x+3} 19`,stroke:'#cfcfd8','stroke-width':1.5},g))},
  mill:(g)=>{el('rect',{x:-24,y:-8,width:30,height:26,fill:'#7a6248',stroke:'#2a1d10'},g);el('path',{d:'M-26 -6 L-9 -22 L8 -6',fill:'#4a3520'},g);const w=el('g',{transform:'translate(16,6)'},g);el('circle',{r:16,fill:'none',stroke:'#c9b28a','stroke-width':3.5},w);[0,45,90,135].forEach(a=>el('line',{x1:0,y1:0,x2:16*Math.cos(a*Math.PI/180),y2:16*Math.sin(a*Math.PI/180),stroke:'#c9b28a','stroke-width':2.5},w));[180,225,270,315].forEach(a=>el('line',{x1:0,y1:0,x2:16*Math.cos(a*Math.PI/180),y2:16*Math.sin(a*Math.PI/180),stroke:'#c9b28a','stroke-width':2.5},w));
   el('animateTransform',{attributeName:'transform',type:'rotate',from:'0',to:'360',dur:'6s',repeatCount:'indefinite',additive:'sum'},w);el('rect',{x:-16,y:4,width:8,height:12,fill:'#1a120a'},g)},
  village:(g)=>{hut(g,-20,2,12,'#8a7a5a');hut(g,8,-4,13,'#9a8a62');el('path',{d:'M-34 22 L34 22 M-30 16 L-30 24 M-18 16 L-18 24 M22 16 L22 24 M32 16 L32 24',stroke:'#6a5a3a','stroke-width':2},g);smoke(g,8,-18)},
  market:(g)=>{[[-26,'#b3261e'],[0,'#2f6f8f'],[26,'#c9a227']].forEach(([x,c])=>{el('rect',{x:x-11,y:2,width:22,height:12,fill:'#7a6248',stroke:'#2a1d10'},g);el('path',{d:`M${x-14} 2 L${x} -10 L${x+14} 2 Z`,fill:c},g);el('path',{d:`M${x-14} 2 L${x+14} 2`,stroke:'#f2ebd8','stroke-width':2,'stroke-dasharray':'4 3'},g)});el('rect',{x:-2,y:-30,width:4,height:22,fill:'#9aa3b5'},g);el('rect',{x:-8,y:-26,width:16,height:4,fill:'#9aa3b5'},g)},
  water:(g)=>{el('ellipse',{cx:0,cy:8,rx:34,ry:14,fill:'#12242f'},g);el('ellipse',{cx:0,cy:8,rx:28,ry:10,fill:'url(#water)'},g);const b=el('g',{},g);el('path',{d:'M-12 6 L12 6 L8 12 L-8 12 Z',fill:'#5a3a20'},b);el('line',{x1:0,y1:6,x2:0,y2:-10,stroke:'#3b2a17','stroke-width':1.5},b);el('path',{d:'M0 -10 L9 -2 L0 -2 Z',fill:'#e8e6dc'},b);el('animateTransform',{attributeName:'transform',type:'translate',values:'0 0;3 -1;0 0',dur:'3s',repeatCount:'indefinite'},b)},
  ruin:(g)=>{[[-28,14],[-14,26],[4,10],[18,20]].forEach(([x,h])=>el('rect',{x,y:18-h,width:12,height:h,fill:'#5a5f6b',stroke:'#14171d'},g));el('path',{d:'M-30 18 L30 18',stroke:'#3a3f4a','stroke-width':3},g);el('rect',{x:-8,y:12,width:9,height:6,fill:'#4b5160',transform:'rotate(-20 -4 15)'},g)},
  farm:(g)=>{el('path',{d:'M-26 18 L-26 -4 L-8 -18 L10 -4 L10 18 Z',fill:'#7a3a2a',stroke:'#2a1d10'},g);el('path',{d:'M-29 -2 L-8 -20 L13 -2',fill:'none',stroke:'#4a3520','stroke-width':3},g);el('rect',{x:-13,y:2,width:10,height:16,fill:'#1a120a'},g);el('circle',{cx:26,cy:8,r:10,fill:'#c9a95a'},g);smoke(g,-16,-18)},
  tower:(g)=>{el('path',{d:'M-30 22 Q0 10 30 22 Z',fill:'#3a3f4a'},g);el('rect',{x:-9,y:-30,width:18,height:48,fill:'#4b5160',stroke:'#14171d'},g);[-9,-2,5].forEach(x=>el('rect',{x,y:-34,width:4,height:5,fill:'#4b5160'},g));el('rect',{x:-3,y:-12,width:6,height:8,fill:'#ffd27a',class:'win'},g);el('line',{x1:0,y1:-34,x2:0,y2:-50,stroke:'#d9d9e0','stroke-width':1.5},g);const b=el('path',{d:'M0 -50 L14 -46 L0 -42 Z',fill:'#2f6f8f'},g);el('animate',{attributeName:'d',values:'M0 -50 L14 -46 L0 -42 Z;M0 -50 L13 -49 L0 -42 Z;M0 -50 L14 -46 L0 -42 Z',dur:'1.6s',repeatCount:'indefinite'},b)},
  cave:(g)=>{el('path',{d:'M-34 20 C-30 -14 30 -14 34 20 Z',fill:'#3a3f4a',stroke:'#14171d'},g);el('path',{d:'M-14 20 C-12 -2 12 -2 14 20 Z',fill:'#07090c'},g);el('circle',{cx:-24,cy:18,r:3,fill:'#5a5f6b'},g);el('circle',{cx:26,cy:16,r:4,fill:'#5a5f6b'},g)},
  forest:(g)=>{el('path',{d:'M-36 18 Q0 4 36 18',stroke:'#6b5a3e','stroke-width':6,fill:'none'},g);tree(g,-22,-10,8,'#2f6b3d','#1c4128');tree(g,0,-16,10,'#26593a','#1c4128');tree(g,22,-8,8,'#2f6b3d','#1c4128');el('rect',{x:-6,y:4,width:12,height:9,fill:'#3a2a18'},g)},
  fields:(g)=>{[-26,-12,2,16,30].forEach(x=>el('path',{d:`M${x} 16 Q${x+3} -6 ${x+6} 16`,stroke:'#c9b25a','stroke-width':3.5,fill:'none'},g));el('path',{d:'M-34 18 L34 18',stroke:'#7a6a3a','stroke-width':2},g);el('path',{d:'M20 -4 L34 -10',stroke:'#7a6a3a','stroke-width':2},g)},
  road:(g)=>{const d='M-38 18 C-20 2 -6 26 8 8 C16 -2 26 6 38 -4';el('path',{d,stroke:'#6b5a3e','stroke-width':6,fill:'none','stroke-linecap':'round'},g);el('path',{d,stroke:'#c9b28a','stroke-width':1.2,fill:'none','stroke-dasharray':'3 6'},g);el('rect',{x:20,y:-22,width:3,height:26,fill:'#4a3520'},g);el('path',{d:'M21 -20 L36 -20 L40 -16 L36 -12 L21 -12 Z',fill:'#c9b28a'},g)},
  other:(g)=>{el('path',{d:'M-6 18 L-2 -22 L4 -22 L8 18 Z',fill:'#6a6f7b',stroke:'#14171d'},g);[[-22,10],[-14,14],[18,12],[26,16]].forEach(([x,r])=>el('circle',{cx:x,cy:18-r/2,r:r/2,fill:'#5a5f6b',stroke:'#14171d'},g));el('path',{d:'M-30 24 L30 24',stroke:'#3a3f4a','stroke-width':2},g)},
 };
 const BUILTIN_ICON={'Ashford':(g)=>{hut(g,-18,2,12,'#8a7a5a');hut(g,10,-4,13,'#9a8a62');el('path',{d:'M-30 24 Q0 16 30 24',stroke:'#4f7f9f','stroke-width':4,fill:'none'},g);el('path',{d:'M-14 22 L-2 22 L-4 17 L-12 17 Z',fill:'#5a3a20'},g);smoke(g,10,-18)},
  'Millbrook':(g)=>{hut(g,-18,4,11,'#7a6a5a');hut(g,6,-2,12,'#867458');el('ellipse',{cx:-6,cy:22,rx:18,ry:5,fill:'#4a3a2a'},g);el('ellipse',{cx:-6,cy:22,rx:12,ry:3,fill:'#5c4632'},g);el('path',{d:'M14 14 L30 8',stroke:'#6a5a3a','stroke-width':3},g);smoke(g,6,-16)},
  'Oakstead':(g)=>{el('rect',{x:9,y:0,width:6,height:16,fill:'#4a3520'},g);el('circle',{cx:12,cy:-10,r:20,fill:'#3f6b3a'},g);el('circle',{cx:4,cy:-14,r:12,fill:'#4a7a44'},g);el('circle',{cx:20,cy:-14,r:11,fill:'#4a7a44'},g);hut(g,-22,6,11,'#8a7a5a');smoke(g,-22,-6)}};

 // ---------- build
 function buildBase(s){const svg=$('mapSvg');svg.innerHTML='';const m=s.map;const st=styleOf(s);sky=st.sky||'day';
  defs(svg,st);terrain(svg,m,s);
  const roads=el('g',{id:'roads'},svg);const seen=new Set();
  for(const [n,d] of Object.entries(m))for(const a of d.adj){const k=[n,a].sort().join('|');if(seen.has(k)||!m[a])continue;seen.add(k);
   const unsafe=DANGER.has(kindOf(n,d))||DANGER.has(kindOf(a,m[a]));
   const mx=(d.x+m[a].x)/2+(a<n?-1:1)*18,my=(d.y+m[a].y)/2+12;const dd=`M${d.x} ${d.y} Q${mx} ${my} ${m[a].x} ${m[a].y}`;
   el('path',{d:dd,class:'roadedge'},roads);el('path',{d:dd,class:'road'+(unsafe?' unsafe':''),'data-k':k},roads)}
  const gn=el('g',{id:'nodes'},svg);
  for(const [n,d] of Object.entries(m)){const node=el('g',{class:'node','data-place':n,transform:`translate(${d.x},${d.y})`},gn);
   el('circle',{r:46,class:'glow'},node);el('ellipse',{cx:0,cy:24,rx:38,ry:9,fill:'#000',opacity:.25},node);
   const ic=el('g',{class:'icon',filter:'url(#shadow)',transform:'scale(1.15)'},node);
   ((!s.map_generated&&BUILTIN_ICON[n])||ICONS[kindOf(n,d)]||ICONS.other)(ic);
   el('g',{class:'fx'},node);
   el('text',{y:44,'text-anchor':'middle',class:'nm',filter:'url(#halo)'},node).textContent=n;el('text',{y:58,'text-anchor':'middle',class:'ruin',filter:'url(#halo)',id:'ru-'+n.replace(/\W/g,'_')},node).textContent='';
   node.addEventListener('click',e=>{e.stopPropagation();selected=n;showPlace(S_)})}
  el('g',{id:'tokens'},svg);el('g',{id:'weather'},svg);
  el('rect',{id:'night',x:0,y:0,width:1000,height:780,fill:SKY[sky]?SKY[sky].tint:'#0a0f1e',opacity:0,'pointer-events':'none'},svg);
  el('g',{id:'tips'},svg);
  const fr=el('g',{id:'frame','pointer-events':'none'},svg);el('rect',{x:6,y:6,width:988,height:768,rx:14,fill:'none',stroke:'#3a3222','stroke-width':3},fr);el('rect',{x:10,y:10,width:980,height:760,rx:12,fill:'none',stroke:'#7a6a44','stroke-width':1,opacity:.6},fr);
  el('text',{x:28,y:38,class:'title',filter:'url(#halo)'},fr).textContent=s.map_name||'Terraceilia';
  el('text',{x:28,y:56,class:'sub',filter:'url(#halo)',id:'dayText'},fr).textContent='';
  const cr=el('g',{transform:'translate(950,700)'},fr);el('circle',{r:22,fill:'none',stroke:'#7a6a44','stroke-width':1.5},cr);el('path',{d:'M0 -20 L5 0 L0 20 L-5 0 Z',fill:'#c9b28a'},cr);el('path',{d:'M-20 0 L0 5 L20 0 L0 -5 Z',fill:'#7a6a44'},cr);el('text',{y:-26,'text-anchor':'middle',class:'sub'},cr).textContent='N';
  svg.addEventListener('click',()=>{selected=null;showPlace(S_)});built=true;tokens={}}

 // ---------- the light this world sits under
 const SKY={day:{tint:'#0a0f1e',base:.15,cycle:.35},dusk:{tint:'#2a1420',base:.34,cycle:.18},night:{tint:'#060a16',base:.55,cycle:.08},
            ash:{tint:'#2a2622',base:.40,cycle:.12},storm:{tint:'#10141c',base:.46,cycle:.12}};
 function narration(s){const last=[...(s.transcript||[])].reverse().find(e=>e.kind==='world');let t=last?last.text:'';const i=t.indexOf('PROSPERITY');return (i>0?t.slice(0,i):t).toLowerCase()}
 function readWeather(s){const t=narration(s);
  weather={snow:/\bsnow/.test(t),rain:/\brain|drizzle|downpour/.test(t),fog:/\bfog|mist|ash\b/.test(t),wolves:/\bwol(f|ves)\b/.test(t),fire:/\bfire\b|burn|blaze/.test(t),night:/\bnight|dusk|dark/.test(t)};
  if(sky==='ash')weather.fog=true;if(sky==='storm')weather.rain=true;
  const w=(s.weather||'');if(/snow|bitter/.test(w))weather.snow=true;if(/rain|storm/.test(w))weather.rain=true;if(w==='storm')weather.night=weather.night||false}
 function renderWeather(){const g=$('weather');if(!g)return;const key=JSON.stringify(weather)+sky;if(g.dataset.key===key)return;g.dataset.key=key;g.innerHTML='';const R=rng(3);
  if(weather.snow){for(let i=0;i<70;i++){const x=R()*1000,y=R()*780;const f=el('circle',{cx:x,cy:y,r:1.2+R()*1.6,fill:'#fff',opacity:.7},g);el('animate',{attributeName:'cy',values:`${y};${y+780}`,dur:`${9+R()*8}s`,repeatCount:'indefinite'},f);el('animate',{attributeName:'cx',values:`${x};${x+30};${x-10};${x+20}`,dur:`${9+R()*8}s`,repeatCount:'indefinite'},f)}}
  if(weather.rain){for(let i=0;i<60;i++){const x=R()*1000,y=R()*780;const l=el('line',{x1:x,y1:y,x2:x-4,y2:y+14,stroke:'#9fc7e0','stroke-width':1.2,opacity:.5},g);el('animate',{attributeName:'y1',values:`${y};${y+780}`,dur:`${1.2+R()*.8}s`,repeatCount:'indefinite'},l);el('animate',{attributeName:'y2',values:`${y+14};${y+794}`,dur:`${1.2+R()*.8}s`,repeatCount:'indefinite'},l)}}
  if(weather.fog){const col=sky==='ash'?'#c9bda8':'#cfd8d6';for(let i=0;i<8;i++){const y=100+R()*600;const c=el('ellipse',{cx:R()*1000,cy:y,rx:180+R()*160,ry:24+R()*20,fill:col,opacity:sky==='ash'?.14:.10},g);el('animate',{attributeName:'cx',values:`${-200};${1200}`,dur:`${40+R()*30}s`,repeatCount:'indefinite'},c)}}
  if(weather.wolves){const m=wolfPlace(S_.map);if(m)for(let i=0;i<3;i++){const w=el('g',{transform:`translate(${m.x-60+i*50},${m.y+40})`},g);el('path',{d:'M-8 4 L-8 -2 L-3 -6 L6 -6 L10 -9 L12 -4 L8 -2 L8 4 Z',fill:'#5a5a62'},w);el('circle',{cx:9,cy:-6,r:1,fill:'#ff4d4d'},w);el('animateTransform',{attributeName:'transform',type:'translate',values:`${m.x-60+i*50} ${m.y+40};${m.x-40+i*50} ${m.y+46};${m.x-60+i*50} ${m.y+40}`,dur:`${3+i}s`,repeatCount:'indefinite'},w)}}}
 function renderFire(s){const fires=s.fires||{};document.querySelectorAll('.node').forEach(n=>{const fx=n.querySelector('.fx');fx.innerHTML='';const pl=n.dataset.place;if(!s.map[pl])return;
  const pres=(s.map[pl].present||[]);pres.slice(0,3).forEach((p,i)=>{const g=el('g',{transform:`translate(${-30+i*30},-46)`},fx);el('circle',{r:8,fill:'#2a2a2e',stroke:'#c9b28a','stroke-width':1.5},g);el('text',{y:4,'text-anchor':'middle',fill:'#c9b28a',style:'font:700 10px Inter,sans-serif'},g).textContent='!';const tt=el('title',{},g);tt.textContent=p});
  if(fires[pl]!==undefined){const f=el('circle',{cx:0,cy:-10,r:34,fill:'url(#fire)',filter:'url(#glow)'},fx);el('animate',{attributeName:'r',values:'30;38;30',dur:'.9s',repeatCount:'indefinite'},f)}
  const gone=(s.map[pl].destroyed||[]);if(gone.length)el('circle',{cx:0,cy:0,r:30,fill:'none',stroke:'#f08b86','stroke-dasharray':'4 4',opacity:.6},fx)})}
 function renderDaylight(){const nt=$('night');if(!nt)return;const k=SKY[sky]||SKY.day;const t=(Date.now()/1000)%120;const cyc=(Math.cos(t/120*Math.PI*2)+1)/2;
  const op=weather.night?Math.max(k.base,.5):k.base+cyc*k.cycle;nt.setAttribute('opacity',op.toFixed(2));
  document.querySelectorAll('.win,.lamp').forEach(w=>w.setAttribute('opacity',(0.3+op).toFixed(2)))}
 setInterval(()=>{if(S_)renderDaylight()},2000);

 // ---------- the place panel and the people
 function showPlace(s){const pp=$('placePanel');if(!selected||!s||!s.map[selected]){pp.classList.remove('open');document.querySelectorAll('.node').forEach(x=>x.classList.remove('sel'));return}const d=s.map[selected];const gone=d.destroyed||[];
  document.querySelectorAll('.node').forEach(x=>x.classList.toggle('sel',x.dataset.place===selected));
  $('ppName').textContent=selected;$('ppDesc').textContent=d.desc;
  $('ppFx').innerHTML=d.fixtures.map(f=>`<div class="fx ${gone.includes(f)?'gone':''}"><span>${esc(f)}</span><button class="btn" data-f="${esc(f)}">${gone.includes(f)?'Restore':'Destroy'}</button></div>`).join('');
  $('ppFx').querySelectorAll('button').forEach(b=>b.onclick=async()=>{const r=await App.api('/god/destroy',{place:selected,fixture:b.dataset.f});note(r.last_god);App.render(r)});
  const burning=(s.fires||{})[selected]!==undefined;$('ppFire').textContent=burning?'Put out the fire':'Set fire';$('ppFire').className=burning?'btn':'danger solid';$('ppFire').onclick=async()=>{const r=await App.api(burning?'/god/extinguish':'/god/fire',{place:selected});note(r.last_god);App.render(r)};
  const pres=(d.present||[]);$('ppPres').innerHTML=pres.length?'Here: '+pres.map(esc).join(', '):'';
  const who=s.characters.filter(c=>c.alive&&!c.gone&&c.location===selected).map(c=>c.name);$('ppWho').textContent=who.length?'People: '+who.join(', '):'Nobody here.';pp.classList.add('open')}
 function note(t){const n=$('godNote');n.textContent=t||'';n.style.display=t?'':'none';clearTimeout(n._t);n._t=setTimeout(()=>n.style.display='none',4000)}
 function figure(t,col){el('ellipse',{cy:14,rx:8,ry:3,fill:'#000',opacity:.35},t);el('circle',{class:'ring',r:12,stroke:col},t);
  el('path',{class:'cloak',d:'M-8 12 L-6 -2 L0 -6 L6 -2 L8 12 Z',fill:col,stroke:'#0a0d0b','stroke-width':1.2},t);el('circle',{class:'head',cy:-9,r:5,fill:'#e6c8a6',stroke:'#0a0d0b','stroke-width':1.2},t);el('text',{y:6,'text-anchor':'middle',class:'ini'},t);
  el('text',{y:40,'text-anchor':'middle',class:'act',filter:'url(#halo)'},t);el('rect',{x:-20,y:44,width:40,height:3,rx:1.5,class:'pbar'},t);el('rect',{x:-20,y:44,width:0,height:3,rx:1.5,class:'pfill'},t)}

 // ---------- movement. The engine says what each person is doing, where, and since when; Walks plans it and the map plays it.
 // A timeline is a walk along the paths to each stop, then a stay there with the bar filling. It begins where the token stands,
 // so a walk under way is finished to wherever the engine says they got, and a place that changes with no walk still walks.
 let raf=null,clockOff=0;
 const posAt=Walks.posAt;
 const serverNow=()=>Date.now()/1000-clockOff;
 function tick(){raf=null;if(!S_)return;let busy=false;const now=serverNow();
  for(const name in tokens){const t=tokens[name];if(t.classList.contains('drag'))continue;const tl=t._tl;let target=null,what=t._what||'',bar=null,walking=false;
   if(tl){const pos=posAt(tl,now-tl.base,t._slotOf);if(pos){target=pos;what=pos.what;bar=pos.bar;walking=pos.walking;busy=true}else{t._rest=tl.provisional&&tl.final?t._slotOf(tl.final):null;t._tl=null}}
   if(!target)target=t._rest||{x:+t.dataset.sx,y:+t.dataset.sy};
   const cx=t._x??target.x,cy=t._y??target.y;let nx=target.x,ny=target.y;
   if(t._tl&&walking){nx=target.x;ny=target.y}else{const dx=target.x-cx,dy=target.y-cy;const d=Math.hypot(dx,dy);if(d>0.5){const step=Math.min(1,0.12);nx=cx+dx*step;ny=cy+dy*step;busy=true}}
   t._x=nx;t._y=ny;t.setAttribute('transform',`translate(${nx.toFixed(1)},${ny.toFixed(1)})`);t.classList.toggle('walking',!!walking);
   const at=t.querySelector('.act');if(at&&at.textContent!==what)at.textContent=what;
   const pb=t.querySelector('.pbar'),pf=t.querySelector('.pfill');const show=bar!==null&&bar!==undefined;pb.style.display=show?'':'none';pf.style.display=show?'':'none';if(show)pf.setAttribute('width',(40*Math.min(1,bar)).toFixed(1))}
  if(busy)raf=requestAnimationFrame(tick)}
 function kick(){if(!raf)raf=requestAnimationFrame(tick)}
 function render(s){S_=s;if(!s.map||!(s.created||s.map_generated))return;const svg=$('mapSvg');
  const mk=(s.map_name||'')+'|'+Object.keys(s.map).join('|')+'|'+JSON.stringify(s.map_style||{});
  if(!built||svg.dataset.gid!==s.id||svg.dataset.mk!==mk){buildBase(s);svg.dataset.gid=s.id;svg.dataset.mk=mk}
  readWeather(s);renderWeather();renderFire(s);renderDaylight();const dt=$('dayText');if(dt)dt.textContent=`Day ${s.day}${(s.day_report||{}).season?' · '+s.day_report.season:''}${s.weather?' · '+s.weather:''} · grain ${(s.ledger||{}).grain??0} · meals ${(s.ledger||{}).meals??0} · wood ${(s.ledger||{}).wood??0}`;
  document.querySelectorAll('.road.unsafe').forEach(r=>r.classList.toggle('open',!!s.ledger.road_safe));
  for(const [n,d] of Object.entries(s.map)){const gone=d.destroyed||[];const ru=$('ru-'+n.replace(/\W/g,'_'));if(ru)ru.textContent=gone.length?'ruined: '+gone.join(', '):''}
  const thinking=new Set((s.current||'').split(', ').filter(Boolean));const acted={};(s.pending||[]).forEach(a=>acted[a.who]=a.text);
  const col={};(s.seats||[]).forEach(x=>col[x.name]=x.color);
  if(typeof s.now==='number')clockOff=Date.now()/1000-s.now;
  const byPlace={};s.characters.forEach(c=>{if(!c.alive||c.gone)return;(byPlace[c.location]=byPlace[c.location]||[]).push(c)});
  const slotOf=(pl,name)=>{const d=s.map[pl];if(!d)return {x:500,y:400};const cs=byPlace[pl]||[];const n=Math.max(1,cs.length);let i=cs.findIndex(c=>c.name===name);if(i<0){i=n;}
   const ang=Math.PI*0.12+(i/Math.max(1,(i>=n?n:n-1)||1))*Math.PI*0.76;const rad=n>1||i>=n?60:0;return {x:d.x+(rad?Math.cos(ang)*rad:0),y:d.y+70+(rad?Math.sin(ang)*rad*0.4:4)}};
  const gt=$('tokens');const live=new Set();const acts=s.activities||{};
  const prev={};for(const n in tokens){const t=tokens[n];if(t.classList.contains('drag'))continue;prev[n]={place:t.dataset.place,key:t._key||'',x:t._x,y:t._y}}
  const planned=Walks.plan(s,prev,serverNow());
  s.characters.forEach(c=>{if(!c.alive||c.gone)return;const pl=c.location;const d=s.map[pl];if(!d)return;live.add(c.name);const sl=slotOf(pl,c.name);const n=(byPlace[pl]||[]).length;
    let t=tokens[c.name];if(!t){t=el('g',{class:'tok','data-name':c.name},gt);figure(t,col[c.name]||'#7d7462');t.querySelector('.ini').textContent=c.name[0];el('text',{y:28,'text-anchor':'middle',class:'lbl',filter:'url(#halo)'},t).textContent=c.name;tokens[c.name]=t;bind(t,c.name);t._x=sl.x;t._y=sl.y;t.setAttribute('transform',`translate(${sl.x},${sl.y})`)}
    t.dataset.sx=sl.x;t.dataset.sy=sl.y;t._slotOf=p=>slotOf(p,c.name);
    const a=acts[c.name];const pn=planned[c.name];
    if(pn){t._key=pn.key;t._act=a||null;t._tl=pn.tl&&pn.tl.end>0?pn.tl:null;t._rest=null}
    t._what=a?(a.state==='working'&&a.stops&&a.stops.length?a.stops[a.stops.length-1].what:a.what):'';
    t.classList.toggle('thinking',thinking.has(c.name));t.classList.toggle('hurt',c.hp<=c.hp_max/2);t.classList.toggle('idle',!!a&&a.state==='idle');t.classList.toggle('resting',!!a&&a.state==='resting');
    t.querySelector('.lbl').style.display=(n<=4||hover===c.name||selected===pl)?'':'none';
    t.dataset.place=pl;t.dataset.action=acted[c.name]||(a?a.what:'');t.dataset.info=`${c.name} · ${c.trade} · ${c.hp}/${c.hp_max} hp · ${c.gold} gold · ${c.standing}`});
  for(const n in tokens)if(!live.has(n)){tokens[n].remove();delete tokens[n]}
  kick();
  if(hover&&tokens[hover])tip(tokens[hover]);else $('tips').innerHTML='';
  if(selected)showPlace(s)}
 function tip(t){const g=$('tips');g.innerHTML='';const m=/translate\(([-\d.]+),([-\d.]+)\)/.exec(t.getAttribute('transform'));if(!m)return;const x=+m[1],y=+m[2];
  const lines=[t.dataset.info].concat(t.dataset.action?['now: '+t.dataset.action]:[]);const w=Math.min(440,Math.max(...lines.map(l=>l.length))*6.4+20);
  const bx=Math.max(8,Math.min(1000-w-8,x-w/2)),by=y-44-lines.length*15;const box=el('g',{class:'tip',transform:`translate(${bx},${by})`},g);
  el('rect',{width:w,height:lines.length*15+10,rx:8},box);lines.forEach((l,i)=>el('text',{x:10,y:16+i*15},box).textContent=l.length>68?l.slice(0,67)+'…':l)}
 function bind(t,name){const svg=$('mapSvg');
  t.addEventListener('pointerenter',()=>{hover=name;render(S_)});t.addEventListener('pointerleave',()=>{if(!drag){hover=null;render(S_)}});
  t.addEventListener('pointerdown',e=>{drag={name,g:t};t.classList.add('drag');t.setPointerCapture(e.pointerId);e.preventDefault();e.stopPropagation()});
  t.addEventListener('pointermove',e=>{if(!drag||drag.g!==t)return;const p=svgPoint(svg,e);t._x=p.x;t._y=p.y;t.setAttribute('transform',`translate(${p.x},${p.y})`);highlight(nearest(S_,p))});
  t.addEventListener('pointerup',async e=>{if(!drag||drag.g!==t)return;const p=svgPoint(svg,e);const dest=nearest(S_,p);t.classList.remove('drag');drag=null;highlight(null);hover=null;
   if(dest&&dest!==t.dataset.place){const r=await App.api('/god/move',{name,place:dest});note(r.last_god);App.render(r)}else render(S_)});
  t.addEventListener('click',e=>e.stopPropagation())}
 function nearest(s,p){let best=null,bd=1e9;for(const [n,d] of Object.entries(s.map)){const dd=Math.hypot(d.x-p.x,d.y+30-p.y);if(dd<95){if(dd<bd){bd=dd;best=n}}}return best}
 function highlight(n){document.querySelectorAll('.node').forEach(x=>x.classList.toggle('hot',x.dataset.place===n))}
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){selected=null;showPlace(S_)}});
 function live(){try{const es=new EventSource('/events');es.onmessage=ev=>{const m=JSON.parse(ev.data);if(S_&&m.id!==S_.id)return;S_=Object.assign(S_||{},m);render(S_);const st=document.getElementById('statusText');if(st&&!m.current)st.textContent=`Day ${m.day} · ${({idle:'Not started',running:'Running',paused:'Paused',done:'The year is over',stopped:'Stopped'})[m.status]||m.status}`;else if(st){const who=m.current.split(', ');st.innerHTML=who.length>2?`<b>${who.length} people</b> are speaking`:`<b>${esc(m.current)}</b> ${who.length>1?'are':'is'} speaking`}};es.onerror=()=>{es.close();setTimeout(live,3000)}}catch(e){setTimeout(live,3000)}}
 live();
 return {render,close:()=>{selected=null;showPlace(S_)}}})();
