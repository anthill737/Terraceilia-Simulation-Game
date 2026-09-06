// Terraceilia overworld, illustrated edition. Procedural SVG: terrain, weather, living places, walking tokens.
const MapView=(()=>{
 const NS='http://www.w3.org/2000/svg';const $=id=>document.getElementById(id);
 const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
 let built=false,drag=null,selected=null,S_=null,tokens={},hover=null,weather={};
 function el(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e}
 function svgPoint(svg,evt){const pt=svg.createSVGPoint();pt.x=evt.clientX;pt.y=evt.clientY;return pt.matrixTransform(svg.getScreenCTM().inverse())}
 const rng=(seed=>()=>(seed=(seed*9301+49297)%233280)/233280);
 // kinds: a generated map carries a kind per place; the built-in valley is drawn as it always was
 const KINDS=['castle','town','village','inn','chapel','mill','forest','fields','water','ruin','market','farm','tower','cave','road','other'];
 const BUILTIN_KIND={'Market town':'town','The castle':'castle','The inn':'inn','The chapel':'chapel','The mill':'mill','Ashford':'village','Millbrook':'village','Oakstead':'village','The forest road':'forest','Open country':'fields'};
 const DANGER=new Set(['road','forest','cave','ruin']);
 const kindOf=(n,d)=>(d&&d.kind&&KINDS.includes(d.kind))?d.kind:(BUILTIN_KIND[n]||'other');
 const isGenerated=m=>Object.values(m||{}).some(d=>d&&d.kind);
 function wolfPlace(m){const es=Object.entries(m||{});const pick=k=>es.find(([n,d])=>kindOf(n,d)===k);const hit=pick('fields')||pick('farm')||pick('forest')||pick('road');return hit?hit[1]:(es.length?es.reduce((a,b)=>b[1].y>a[1].y?b:a)[1]:null)}

 // ---------- defs: gradients, filters, patterns
 function defs(svg){const d=el('defs',{},svg);
  const g1=el('radialGradient',{id:'ground',cx:'50%',cy:'45%',r:'75%'},d);el('stop',{offset:'0%','stop-color':'#2a4a33'},g1);el('stop',{offset:'55%','stop-color':'#1d3626'},g1);el('stop',{offset:'100%','stop-color':'#0f1c14'},g1);
  const vig=el('radialGradient',{id:'vig',cx:'50%',cy:'50%',r:'72%'},d);el('stop',{offset:'55%','stop-color':'#000','stop-opacity':0},vig);el('stop',{offset:'100%','stop-color':'#000','stop-opacity':.6},vig);
  const hill=el('linearGradient',{id:'hill',x1:0,y1:0,x2:0,y2:1},d);el('stop',{offset:'0%','stop-color':'#3d4658'},hill);el('stop',{offset:'100%','stop-color':'#1c222c'},hill);
  const water=el('linearGradient',{id:'water',x1:0,y1:0,x2:1,y2:0},d);el('stop',{offset:'0%','stop-color':'#2f6f8f'},water);el('stop',{offset:'50%','stop-color':'#4d9bbd'},water);el('stop',{offset:'100%','stop-color':'#2f6f8f'},water);
  const sky=el('linearGradient',{id:'sky',x1:0,y1:0,x2:0,y2:1},d);el('stop',{offset:'0%','stop-color':'#0a0f1e'},sky);el('stop',{offset:'100%','stop-color':'#0a0f1e','stop-opacity':0},sky);
  const tex=el('filter',{id:'tex',x:'0',y:'0',width:'100%',height:'100%'},d);el('feTurbulence',{type:'fractalNoise',baseFrequency:'0.9',numOctaves:3,seed:4,result:'n'},tex);el('feColorMatrix',{type:'saturate',values:0,in:'n',result:'g'},tex);const cm=el('feComponentTransfer',{in:'g',result:'a'},tex);el('feFuncA',{type:'table',tableValues:'0 0.18'},cm);el('feComposite',{in:'a',in2:'SourceGraphic',operator:'atop'},tex);
  const halo=el('filter',{id:'halo',x:'-20%',y:'-30%',width:'140%',height:'160%'},d);el('feMorphology',{in:'SourceAlpha',operator:'dilate',radius:2.2,result:'dl'},halo);el('feFlood',{'flood-color':'#0a0d0b','flood-opacity':.9,result:'c'},halo);el('feComposite',{in:'c',in2:'dl',operator:'in',result:'h'},halo);const mg=el('feMerge',{},halo);el('feMergeNode',{in:'h'},mg);el('feMergeNode',{in:'SourceGraphic'},mg);
  const sh=el('filter',{id:'shadow',x:'-40%',y:'-40%',width:'180%',height:'180%'},d);el('feDropShadow',{dx:0,dy:4,stdDeviation:3,'flood-color':'#000','flood-opacity':.7},sh);
  const glow=el('filter',{id:'glow',x:'-100%',y:'-100%',width:'300%',height:'300%'},d);el('feGaussianBlur',{stdDeviation:6,result:'b'},glow);const mg2=el('feMerge',{},glow);el('feMergeNode',{in:'b'},mg2);el('feMergeNode',{in:'SourceGraphic'},mg2);
  const fire=el('radialGradient',{id:'fire'},d);el('stop',{offset:'0%','stop-color':'#ffb347','stop-opacity':.9},fire);el('stop',{offset:'100%','stop-color':'#ff5a1f','stop-opacity':0},fire);
  const lamp=el('radialGradient',{id:'lamp'},d);el('stop',{offset:'0%','stop-color':'#ffd27a','stop-opacity':.85},lamp);el('stop',{offset:'100%','stop-color':'#ffd27a','stop-opacity':0},lamp);}

 // ---------- terrain
 function tree(g,x,y,sz,col,dark){el('ellipse',{cx:x+2,cy:y+sz*1.7,rx:sz*.9,ry:sz*.35,fill:'#000',opacity:.25},g);el('rect',{x:x-1,y:y+sz*1.1,width:2.4,height:sz*.7,fill:'#3b2a17'},g);
  el('path',{d:`M${x} ${y-sz*.4} L${x-sz} ${y+sz*1.3} L${x+sz} ${y+sz*1.3} Z`,fill:dark},g);el('path',{d:`M${x} ${y-sz} L${x-sz*.8} ${y+sz*.5} L${x+sz*.8} ${y+sz*.5} Z`,fill:col},g);el('path',{d:`M${x} ${y-sz*1.5} L${x-sz*.55} ${y-sz*.2} L${x+sz*.55} ${y-sz*.2} Z`,fill:col},g)}
 function hut(g,x,y,w,col){el('path',{d:`M${x-w} ${y+w*.8} L${x-w} ${y} L${x} ${y-w*.9} L${x+w} ${y} L${x+w} ${y+w*.8} Z`,fill:col,stroke:'#2a1d10','stroke-width':1},g);el('path',{d:`M${x-w-2} ${y+1} L${x} ${y-w} L${x+w+2} ${y+1}`,fill:'none',stroke:'#4a3520','stroke-width':2},g);el('rect',{x:x-w*.25,y:y+w*.2,width:w*.5,height:w*.6,fill:'#1a120a'},g)}
 function smoke(g,x,y){for(let i=0;i<3;i++){const c=el('circle',{cx:x,cy:y,r:2.5+i,fill:'#c9c9c9',opacity:0},g);el('animate',{attributeName:'cy',values:`${y};${y-30}`,dur:`${3+i}s`,begin:`${i}s`,repeatCount:'indefinite'},c);el('animate',{attributeName:'opacity',values:'0;.45;0',dur:`${3+i}s`,begin:`${i}s`,repeatCount:'indefinite'},c);el('animate',{attributeName:'cx',values:`${x};${x+6};${x-4}`,dur:`${3+i}s`,begin:`${i}s`,repeatCount:'indefinite'},c)}}
 function terrain(svg,m){const g=el('g',{id:'terrain'},svg);const R=rng(11);
  el('rect',{x:0,y:0,width:1000,height:780,fill:'url(#ground)'},g);el('rect',{x:0,y:0,width:1000,height:780,fill:'#000',filter:'url(#tex)',opacity:.55},g);
  // land contours
  for(let i=0;i<9;i++)el('ellipse',{cx:150+R()*700,cy:200+R()*450,rx:60+R()*160,ry:20+R()*40,fill:R()>.5?'#234a30':'#1b3b26',opacity:.35},g);
  if(isGenerated(m))terrainGenerated(g,m,R);else terrainBuiltin(g,R);
  // vignette
  el('rect',{x:0,y:0,width:1000,height:780,fill:'url(#vig)'},g)}
 function terrainBuiltin(g,R){
  // hills
  el('path',{d:'M250 170 C330 40 660 40 760 170 Z',fill:'url(#hill)',opacity:.95},g);el('path',{d:'M300 170 C370 90 620 90 690 170 Z',fill:'#2c3340',opacity:.9},g);el('path',{d:'M180 190 C230 120 330 120 380 190 Z',fill:'#262d39',opacity:.9},g);el('path',{d:'M620 190 C690 110 800 110 850 190 Z',fill:'#262d39',opacity:.8},g);
  // river with flow
  const river='M-20 555 C120 520 180 470 250 480 C330 495 360 560 470 560 C600 560 650 700 720 770';
  el('path',{d:river,stroke:'#12242f','stroke-width':30,fill:'none','stroke-linecap':'round',opacity:.9},g);el('path',{d:river,stroke:'url(#water)','stroke-width':18,fill:'none','stroke-linecap':'round',opacity:.95},g);
  const fl=el('path',{d:river,stroke:'#bfe6f5','stroke-width':3,fill:'none','stroke-linecap':'round','stroke-dasharray':'6 28',opacity:.5},g);el('animate',{attributeName:'stroke-dashoffset',values:'0;-68',dur:'2.5s',repeatCount:'indefinite'},fl);
  // fields
  for(let i=0;i<10;i++)el('line',{x1:430+i*38,y1:640,x2:462+i*38,y2:770,stroke:'#5a5330','stroke-width':7,opacity:.55},g);
  // forests
  const trees=[];for(let i=0;i<110;i++){const x=780+R()*230,y=50+R()*330;if(Math.hypot(x-880,y-190)<58)continue;trees.push([x,y,5+R()*7])}
  for(let i=0;i<26;i++){trees.push([20+R()*190,40+R()*300,4+R()*6])}for(let i=0;i<14;i++){trees.push([40+R()*140,600+R()*160,4+R()*5])}
  trees.sort((a,b)=>a[1]-b[1]).forEach(([x,y,s])=>tree(g,x,y,s,R()>.5?'#2f6b3d':'#26593a','#1c4128'));
  // pasture and sheep
  el('ellipse',{cx:770,cy:485,rx:95,ry:42,fill:'#5d7a3a',opacity:.45},g);
  for(let i=0;i<10;i++){const sx=700+R()*140,sy=455+R()*60;const s=el('ellipse',{cx:sx,cy:sy,rx:4,ry:2.6,fill:'#e8e6dc'},g);el('circle',{cx:sx+3,cy:sy,r:1.5,fill:'#3a3a3a'},g);el('animate',{attributeName:'cx',values:`${sx};${sx+6+R()*6};${sx}`,dur:`${8+R()*8}s`,repeatCount:'indefinite'},s)}
}
 function terrainGenerated(g,m,R){const ps=Object.entries(m).map(([n,d])=>({n,d,k:kindOf(n,d)}));const near=(x,y,r)=>ps.some(p=>Math.hypot(p.d.x-x,p.d.y-y)<r);
  // hills behind castles and towers
  ps.filter(p=>p.k==='castle'||p.k==='tower').forEach(p=>{const x=p.d.x,y=p.d.y+8;el('path',{d:`M${x-170} ${y} C${x-100} ${y-140} ${x+100} ${y-140} ${x+170} ${y} Z`,fill:'url(#hill)',opacity:.95},g);el('path',{d:`M${x-110} ${y} C${x-60} ${y-80} ${x+60} ${y-80} ${x+110} ${y} Z`,fill:'#2c3340',opacity:.9},g)});
  // a body of water under every water place
  ps.filter(p=>p.k==='water').forEach(p=>{const x=p.d.x,y=p.d.y+18;el('ellipse',{cx:x,cy:y,rx:135,ry:52,fill:'#12242f',opacity:.9},g);el('ellipse',{cx:x,cy:y,rx:120,ry:42,fill:'url(#water)',opacity:.95},g);const rp=el('ellipse',{cx:x,cy:y,rx:80,ry:24,fill:'none',stroke:'#bfe6f5','stroke-width':2,'stroke-dasharray':'6 28',opacity:.5},g);el('animate',{attributeName:'stroke-dashoffset',values:'0;-68',dur:'3s',repeatCount:'indefinite'},rp)});
  // furrows around fields, pasture and sheep around farms
  ps.filter(p=>p.k==='fields').forEach(p=>{for(let i=0;i<9;i++)el('line',{x1:p.d.x-88+i*22,y1:p.d.y+34,x2:p.d.x-70+i*22,y2:p.d.y+96,stroke:'#5a5330','stroke-width':7,opacity:.55},g)});
  ps.filter(p=>p.k==='farm').forEach(p=>{el('ellipse',{cx:p.d.x,cy:p.d.y+52,rx:95,ry:38,fill:'#5d7a3a',opacity:.45},g);for(let i=0;i<7;i++){const sx=p.d.x-70+R()*140,sy=p.d.y+34+R()*44;const s=el('ellipse',{cx:sx,cy:sy,rx:4,ry:2.6,fill:'#e8e6dc'},g);el('circle',{cx:sx+3,cy:sy,r:1.5,fill:'#3a3a3a'},g);el('animate',{attributeName:'cx',values:`${sx};${sx+6+R()*6};${sx}`,dur:`${8+R()*8}s`,repeatCount:'indefinite'},s)}});
  // trees clustered around forests, and a light scatter elsewhere, never on top of a place
  const trees=[];const ok=(x,y)=>x>15&&x<985&&y>70&&y<765&&!near(x,y,62);
  ps.filter(p=>p.k==='forest').forEach(p=>{for(let i=0;i<80;i++){const a=R()*Math.PI*2,r=62+R()*100;const x=p.d.x+Math.cos(a)*r,y=p.d.y+Math.sin(a)*r*.7;if(ok(x,y))trees.push([x,y,5+R()*7])}});
  for(let i=0;i<40;i++){const x=R()*1000,y=60+R()*700;if(ok(x,y)&&!ps.some(p=>(p.k==='water'||p.k==='fields'||p.k==='farm')&&Math.hypot(p.d.x-x,p.d.y-y)<150))trees.push([x,y,4+R()*5])}
  trees.sort((a,b)=>a[1]-b[1]).forEach(([x,y,s])=>tree(g,x,y,s,R()>.5?'#2f6b3d':'#26593a','#1c4128'))}

 // ---------- places, each alive
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
  'Ashford':(g)=>{hut(g,-18,2,12,'#8a7a5a');hut(g,10,-4,13,'#9a8a62');el('path',{d:'M-30 24 Q0 16 30 24',stroke:'#4f7f9f','stroke-width':4,fill:'none'},g);el('path',{d:'M-14 22 L-2 22 L-4 17 L-12 17 Z',fill:'#5a3a20'},g);smoke(g,10,-18)},
  'Millbrook':(g)=>{hut(g,-18,4,11,'#7a6a5a');hut(g,6,-2,12,'#867458');el('ellipse',{cx:-6,cy:22,rx:18,ry:5,fill:'#4a3a2a'},g);el('ellipse',{cx:-6,cy:22,rx:12,ry:3,fill:'#5c4632'},g);el('path',{d:'M14 14 L30 8',stroke:'#6a5a3a','stroke-width':3},g);smoke(g,6,-16)},
  'Oakstead':(g)=>{el('rect',{x:9,y:0,width:6,height:16,fill:'#4a3520'},g);el('circle',{cx:12,cy:-10,r:20,fill:'#3f6b3a'},g);el('circle',{cx:4,cy:-14,r:12,fill:'#4a7a44'},g);el('circle',{cx:20,cy:-14,r:11,fill:'#4a7a44'},g);hut(g,-22,6,11,'#8a7a5a');smoke(g,-22,-6)},
  forest:(g)=>{el('path',{d:'M-36 18 Q0 4 36 18',stroke:'#6b5a3e','stroke-width':6,fill:'none'},g);tree(g,-22,-10,8,'#2f6b3d','#1c4128');tree(g,0,-16,10,'#26593a','#1c4128');tree(g,22,-8,8,'#2f6b3d','#1c4128');el('rect',{x:-6,y:4,width:12,height:9,fill:'#3a2a18'},g)},
  fields:(g)=>{[-26,-12,2,16,30].forEach(x=>el('path',{d:`M${x} 16 Q${x+3} -6 ${x+6} 16`,stroke:'#c9b25a','stroke-width':3.5,fill:'none'},g));el('path',{d:'M-34 18 L34 18',stroke:'#7a6a3a','stroke-width':2},g);el('path',{d:'M20 -4 L34 -10',stroke:'#7a6a3a','stroke-width':2},g)},
  village:(g)=>{hut(g,-20,2,12,'#8a7a5a');hut(g,8,-4,13,'#9a8a62');el('path',{d:'M-34 22 L34 22 M-30 16 L-30 24 M-18 16 L-18 24 M22 16 L22 24 M32 16 L32 24',stroke:'#6a5a3a','stroke-width':2},g);smoke(g,8,-18)},
  market:(g)=>{[[-26,'#b3261e'],[0,'#2f6f8f'],[26,'#c9a227']].forEach(([x,c])=>{el('rect',{x:x-11,y:2,width:22,height:12,fill:'#7a6248',stroke:'#2a1d10'},g);el('path',{d:`M${x-14} 2 L${x} -10 L${x+14} 2 Z`,fill:c},g);el('path',{d:`M${x-14} 2 L${x+14} 2`,stroke:'#f2ebd8','stroke-width':2,'stroke-dasharray':'4 3'},g)});el('rect',{x:-2,y:-30,width:4,height:22,fill:'#9aa3b5'},g);el('rect',{x:-8,y:-26,width:16,height:4,fill:'#9aa3b5'},g)},
  water:(g)=>{el('ellipse',{cx:0,cy:8,rx:34,ry:14,fill:'#12242f'},g);el('ellipse',{cx:0,cy:8,rx:28,ry:10,fill:'url(#water)'},g);const b=el('g',{},g);el('path',{d:'M-12 6 L12 6 L8 12 L-8 12 Z',fill:'#5a3a20'},b);el('line',{x1:0,y1:6,x2:0,y2:-10,stroke:'#3b2a17','stroke-width':1.5},b);el('path',{d:'M0 -10 L9 -2 L0 -2 Z',fill:'#e8e6dc'},b);el('animateTransform',{attributeName:'transform',type:'translate',values:'0 0;3 -1;0 0',dur:'3s',repeatCount:'indefinite'},b);el('path',{d:'M-22 22 Q0 26 22 22',stroke:'#4f7f9f','stroke-width':3,fill:'none'},g)},
  ruin:(g)=>{[[-28,14],[-14,26],[4,10],[18,20]].forEach(([x,h])=>el('rect',{x,y:18-h,width:12,height:h,fill:'#5a5f6b',stroke:'#14171d'},g));el('path',{d:'M-30 18 L30 18',stroke:'#3a3f4a','stroke-width':3},g);el('rect',{x:-8,y:12,width:9,height:6,fill:'#4b5160',transform:'rotate(-20 -4 15)'},g);[-24,20].forEach(x=>el('path',{d:`M${x} 24 L${x} 16 M${x-3} 19 L${x+3} 19`,stroke:'#4a7a44','stroke-width':1.5},g))},
  farm:(g)=>{el('path',{d:'M-26 18 L-26 -4 L-8 -18 L10 -4 L10 18 Z',fill:'#7a3a2a',stroke:'#2a1d10'},g);el('path',{d:'M-29 -2 L-8 -20 L13 -2',fill:'none',stroke:'#4a3520','stroke-width':3},g);el('rect',{x:-13,y:2,width:10,height:16,fill:'#1a120a'},g);el('circle',{cx:26,cy:8,r:10,fill:'#c9a95a'},g);el('path',{d:'M14 22 L38 22 M18 16 L18 24 M30 16 L30 24',stroke:'#6a5a3a','stroke-width':2},g);smoke(g,-16,-18)},
  tower:(g)=>{el('path',{d:'M-30 22 Q0 10 30 22 Z',fill:'#3a3f4a'},g);el('rect',{x:-9,y:-30,width:18,height:48,fill:'#4b5160',stroke:'#14171d'},g);[-9,-2,5].forEach(x=>el('rect',{x,y:-34,width:4,height:5,fill:'#4b5160'},g));el('rect',{x:-3,y:-12,width:6,height:8,fill:'#ffd27a',class:'win'},g);el('line',{x1:0,y1:-34,x2:0,y2:-50,stroke:'#d9d9e0','stroke-width':1.5},g);const b=el('path',{d:'M0 -50 L14 -46 L0 -42 Z',fill:'#2f6f8f'},g);el('animate',{attributeName:'d',values:'M0 -50 L14 -46 L0 -42 Z;M0 -50 L13 -49 L0 -42 Z;M0 -50 L14 -46 L0 -42 Z',dur:'1.6s',repeatCount:'indefinite'},b)},
  cave:(g)=>{el('path',{d:'M-34 20 C-30 -14 30 -14 34 20 Z',fill:'#3a3f4a',stroke:'#14171d'},g);el('path',{d:'M-14 20 C-12 -2 12 -2 14 20 Z',fill:'#07090c'},g);el('path',{d:'M-6 2 L-4 10 M4 4 L5 12',stroke:'#2a2f3a','stroke-width':2},g);el('circle',{cx:-24,cy:18,r:3,fill:'#5a5f6b'},g);el('circle',{cx:26,cy:16,r:4,fill:'#5a5f6b'},g)},
  road:(g)=>{const d='M-38 18 C-20 2 -6 26 8 8 C16 -2 26 6 38 -4';el('path',{d,stroke:'#6b5a3e','stroke-width':6,fill:'none','stroke-linecap':'round'},g);el('path',{d,stroke:'#c9b28a','stroke-width':1.2,fill:'none','stroke-dasharray':'3 6'},g);el('rect',{x:20,y:-22,width:3,height:26,fill:'#4a3520'},g);el('path',{d:'M21 -20 L36 -20 L40 -16 L36 -12 L21 -12 Z',fill:'#c9b28a'},g);el('rect',{x:-30,y:2,width:6,height:9,fill:'#5a5f6b'},g)},
  other:(g)=>{el('path',{d:'M-6 18 L-2 -22 L4 -22 L8 18 Z',fill:'#6a6f7b',stroke:'#14171d'},g);[[-22,10],[-14,14],[18,12],[26,16]].forEach(([x,r])=>el('circle',{cx:x,cy:18-r/2,r:r/2,fill:'#5a5f6b',stroke:'#14171d'},g));el('path',{d:'M-30 24 L30 24',stroke:'#3a3f4a','stroke-width':2},g)},
 };

 // ---------- build
 function buildBase(s){const svg=$('mapSvg');svg.innerHTML='';const m=s.map;defs(svg);terrain(svg,m);
  const roads=el('g',{id:'roads'},svg);const seen=new Set();
  for(const [n,d] of Object.entries(m))for(const a of d.adj){const k=[n,a].sort().join('|');if(seen.has(k)||!m[a])continue;seen.add(k);const unsafe=DANGER.has(kindOf(n,d))||DANGER.has(kindOf(a,m[a]));
   const mx=(d.x+m[a].x)/2+(a<n?-1:1)*18,my=(d.y+m[a].y)/2+12;const dd=`M${d.x} ${d.y} Q${mx} ${my} ${m[a].x} ${m[a].y}`;
   el('path',{d:dd,class:'roadedge'},roads);el('path',{d:dd,class:'road'+(unsafe?' unsafe':''),'data-k':k},roads)}
  const gn=el('g',{id:'nodes'},svg);
  for(const [n,d] of Object.entries(m)){const node=el('g',{class:'node','data-place':n,transform:`translate(${d.x},${d.y})`},gn);
   el('circle',{r:46,class:'glow'},node);el('ellipse',{cx:0,cy:24,rx:38,ry:9,fill:'#000',opacity:.25},node);const ic=el('g',{class:'icon',filter:'url(#shadow)',transform:'scale(1.15)'},node);((d.kind?ICONS[kindOf(n,d)]:(ICONS[n]||ICONS[kindOf(n,d)]))||ICONS.other)(ic);
   el('g',{class:'fx'},node);
   el('text',{y:44,'text-anchor':'middle',class:'nm',filter:'url(#halo)'},node).textContent=n;el('text',{y:58,'text-anchor':'middle',class:'ruin',filter:'url(#halo)',id:'ru-'+n.replace(/\W/g,'_')},node);
   node.addEventListener('click',e=>{e.stopPropagation();selected=n;showPlace(S_)})}
  el('g',{id:'tokens'},svg);el('g',{id:'weather'},svg);el('rect',{id:'night',x:0,y:0,width:1000,height:780,fill:'#0a0f1e',opacity:0,'pointer-events':'none'},svg);el('g',{id:'tips'},svg);
  // frame: title and day
  const fr=el('g',{id:'frame','pointer-events':'none'},svg);el('rect',{x:6,y:6,width:988,height:768,rx:14,fill:'none',stroke:'#3a3222','stroke-width':3},fr);el('rect',{x:10,y:10,width:980,height:760,rx:12,fill:'none',stroke:'#7a6a44','stroke-width':1,opacity:.6},fr);
  el('text',{x:28,y:38,class:'title',filter:'url(#halo)'},fr).textContent=s.map_name||'Terraceilia';el('text',{x:28,y:56,class:'sub',filter:'url(#halo)',id:'dayText'},fr).textContent='';
  const cr=el('g',{transform:'translate(950,700)'},fr);el('circle',{r:22,fill:'none',stroke:'#7a6a44','stroke-width':1.5},cr);el('path',{d:'M0 -20 L5 0 L0 20 L-5 0 Z',fill:'#c9b28a'},cr);el('path',{d:'M-20 0 L0 5 L20 0 L0 -5 Z',fill:'#7a6a44'},cr);el('text',{y:-26,'text-anchor':'middle',class:'sub'},cr).textContent='N';
  svg.addEventListener('click',()=>{selected=null;showPlace(S_)});built=true;tokens={}}

 // ---------- weather from the World's words
 function narration(s){const last=[...(s.transcript||[])].reverse().find(e=>e.kind==='world');let t=last?last.text:'';const i=t.indexOf('PROSPERITY');return (i>0?t.slice(0,i):t).toLowerCase()}
 function readWeather(s){const t=narration(s);
  weather={snow:/\bsnow/.test(t),rain:/\brain|drizzle|downpour/.test(t),fog:/\bfog|mist/.test(t),wolves:/\bwol(f|ves)\b/.test(t),fire:/\bfire\b|burn|blaze/.test(t),night:/\bnight|dusk|dark/.test(t)};
  if(s.ledger&&s.ledger.grain_weeks!==undefined&&s.day>=8)weather.snow=weather.snow||s.day>=8}
 function renderWeather(){const g=$('weather');if(!g)return;const key=JSON.stringify(weather);if(g.dataset.key===key)return;g.dataset.key=key;g.innerHTML='';const R=rng(3);
  if(weather.snow){for(let i=0;i<70;i++){const x=R()*1000,y=R()*780;const f=el('circle',{cx:x,cy:y,r:1.2+R()*1.6,fill:'#fff',opacity:.7},g);el('animate',{attributeName:'cy',values:`${y};${y+780}`,dur:`${9+R()*8}s`,repeatCount:'indefinite'},f);el('animate',{attributeName:'cx',values:`${x};${x+30};${x-10};${x+20}`,dur:`${9+R()*8}s`,repeatCount:'indefinite'},f)}}
  if(weather.rain){for(let i=0;i<60;i++){const x=R()*1000,y=R()*780;const l=el('line',{x1:x,y1:y,x2:x-4,y2:y+14,stroke:'#9fc7e0','stroke-width':1.2,opacity:.5},g);el('animate',{attributeName:'y1',values:`${y};${y+780}`,dur:`${1.2+R()*.8}s`,repeatCount:'indefinite'},l);el('animate',{attributeName:'y2',values:`${y+14};${y+794}`,dur:`${1.2+R()*.8}s`,repeatCount:'indefinite'},l)}}
  if(weather.fog){for(let i=0;i<8;i++){const y=100+R()*600;const c=el('ellipse',{cx:R()*1000,cy:y,rx:180+R()*160,ry:24+R()*20,fill:'#cfd8d6',opacity:.10},g);el('animate',{attributeName:'cx',values:`${-200};${1200}`,dur:`${40+R()*30}s`,repeatCount:'indefinite'},c)}}
  if(weather.wolves){const m=wolfPlace(S_.map);if(m)for(let i=0;i<3;i++){const w=el('g',{transform:`translate(${m.x-60+i*50},${m.y+40})`},g);el('path',{d:'M-8 4 L-8 -2 L-3 -6 L6 -6 L10 -9 L12 -4 L8 -2 L8 4 Z',fill:'#5a5a62'},w);el('circle',{cx:9,cy:-6,r:1,fill:'#ff4d4d'},w);el('animateTransform',{attributeName:'transform',type:'translate',values:`${m.x-60+i*50} ${m.y+40};${m.x-40+i*50} ${m.y+46};${m.x-60+i*50} ${m.y+40}`,dur:`${3+i}s`,repeatCount:'indefinite'},w)}}}
 function renderFire(s){const fires=s.fires||{};document.querySelectorAll('.node').forEach(n=>{const fx=n.querySelector('.fx');fx.innerHTML='';const pl=n.dataset.place;
  const pres=(s.map[pl].present||[]);pres.slice(0,3).forEach((p,i)=>{const g=el('g',{transform:`translate(${-30+i*30},-46)`},fx);el('circle',{r:8,fill:'#2a2a2e',stroke:'#c9b28a','stroke-width':1.5},g);el('text',{y:4,'text-anchor':'middle',fill:'#c9b28a',style:'font:700 10px Inter,sans-serif'},g).textContent='!';const tt=el('title',{},g);tt.textContent=p});
  if(fires[pl]!==undefined){const f=el('circle',{cx:0,cy:-10,r:34,fill:'url(#fire)',filter:'url(#glow)'},fx);el('animate',{attributeName:'r',values:'30;38;30',dur:'.9s',repeatCount:'indefinite'},f)}
  const gone=(s.map[n.dataset.place].destroyed||[]);if(gone.length)el('circle',{cx:0,cy:0,r:30,fill:'none',stroke:'#f08b86','stroke-dasharray':'4 4',opacity:.6},fx)})}
 function renderDaylight(s){const nt=$('night');if(!nt)return;const t=(Date.now()/1000)%120;const cyc=(Math.cos(t/120*Math.PI*2)+1)/2;const op=weather.night?.5:.15+cyc*.35;nt.setAttribute('opacity',op.toFixed(2));document.querySelectorAll('.win,.lamp').forEach(w=>w.setAttribute('opacity',(0.3+op).toFixed(2)))}
 setInterval(()=>{if(S_)renderDaylight(S_)},2000);

 // ---------- people
 function showPlace(s){const pp=$('placePanel');if(!selected||!s){pp.classList.remove('open');document.querySelectorAll('.node').forEach(x=>x.classList.remove('sel'));return}const d=s.map[selected];if(!d)return;const gone=d.destroyed||[];
  document.querySelectorAll('.node').forEach(x=>x.classList.toggle('sel',x.dataset.place===selected));
  $('ppName').textContent=selected;$('ppDesc').textContent=d.desc;
  $('ppFx').innerHTML=d.fixtures.map(f=>`<div class="fx ${gone.includes(f)?'gone':''}"><span>${esc(f)}</span><button class="btn" data-f="${esc(f)}">${gone.includes(f)?'Restore':'Destroy'}</button></div>`).join('');
  $('ppFx').querySelectorAll('button').forEach(b=>b.onclick=async()=>{const r=await App.api('/god/destroy',{place:selected,fixture:b.dataset.f});note(r.last_god);App.render(r)});
  const burning=(s.fires||{})[selected]!==undefined;$('ppFire').textContent=burning?'Put out the fire':'Set fire';$('ppFire').className=burning?'btn':'danger solid';$('ppFire').onclick=async()=>{const r=await App.api(burning?'/god/extinguish':'/god/fire',{place:selected});note(r.last_god);App.render(r)};
  const pres=(d.present||[]);$('ppPres').innerHTML=pres.length?'Here: '+pres.map(esc).join(', '):'';
  const who=s.characters.filter(c=>c.alive&&!c.banished&&c.location===selected).map(c=>c.name);$('ppWho').textContent=who.length?'People: '+who.join(', '):'Nobody here.';pp.classList.add('open')}
 function note(t){const n=$('godNote');n.textContent=t||'';n.style.display=t?'':'none';clearTimeout(n._t);n._t=setTimeout(()=>n.style.display='none',4000)}
 function figure(t,col){el('ellipse',{cy:14,rx:8,ry:3,fill:'#000',opacity:.35},t);el('circle',{class:'ring',r:12,stroke:col},t);
  el('path',{class:'cloak',d:'M-8 12 L-6 -2 L0 -6 L6 -2 L8 12 Z',fill:col,stroke:'#0a0d0b','stroke-width':1.2},t);el('circle',{class:'head',cy:-9,r:5,fill:'#e6c8a6',stroke:'#0a0d0b','stroke-width':1.2},t);el('text',{y:6,'text-anchor':'middle',class:'ini'},t)}
 function render(s){S_=s;if(!s.map||!(s.created||s.map_generated))return;const svg=$('mapSvg');const mk=(s.map_name||'')+'|'+Object.keys(s.map).join('|');if(!built||svg.dataset.gid!==s.id||svg.dataset.mk!==mk){buildBase(s);svg.dataset.gid=s.id;svg.dataset.mk=mk}
  readWeather(s);renderWeather();renderFire(s);renderDaylight(s);const dt=$('dayText');if(dt)dt.textContent=`Day ${s.day} · grain for ${s.ledger.grain_weeks} of ${s.ledger.grain_needed} weeks`;
  document.querySelectorAll('.road.unsafe').forEach(r=>r.classList.toggle('open',!!s.ledger.road_safe));
  for(const [n,d] of Object.entries(s.map)){const gone=d.destroyed||[];const ru=$('ru-'+n.replace(/\W/g,'_'));if(ru)ru.textContent=gone.length?'ruined: '+gone.join(', '):''}
  const thinking=new Set((s.current||'').split(', ').filter(Boolean));const acted={};(s.pending||[]).forEach(a=>acted[a.who]=a.text);
  const col={};(s.seats||[]).forEach(x=>col[x.name]=x.color);
  const byPlace={};s.characters.forEach(c=>{if(!c.alive||c.banished)return;(byPlace[c.location]=byPlace[c.location]||[]).push(c)});
  const gt=$('tokens');const live=new Set();
  for(const [pl,cs] of Object.entries(byPlace)){const d=s.map[pl];if(!d)continue;const n=cs.length;
   cs.forEach((c,i)=>{live.add(c.name);const ang=Math.PI*0.12+(i/Math.max(1,n-1||1))*Math.PI*0.76;const rad=n>1?60:0;const x=d.x+(n>1?Math.cos(ang)*rad:0),y=d.y+70+(n>1?Math.sin(ang)*rad*0.4:4);
    let t=tokens[c.name];if(!t){t=el('g',{class:'tok','data-name':c.name},gt);figure(t,col[c.name]||'#888');t.querySelector('.ini').textContent=c.name[0];el('text',{y:28,'text-anchor':'middle',class:'lbl',filter:'url(#halo)'},t).textContent=c.name;tokens[c.name]=t;bind(t,c.name);t.setAttribute('transform',`translate(${x},${y})`)}
    if(!t.classList.contains('drag'))t.setAttribute('transform',`translate(${x},${y})`);
    t.classList.toggle('thinking',thinking.has(c.name));t.classList.toggle('hurt',c.hp<=c.hp_max/2);t.querySelector('.lbl').style.display=(n<=4||hover===c.name||selected===pl)?'':'none';
    t.dataset.place=pl;t.dataset.action=acted[c.name]||'';t.dataset.info=`${c.name} · ${c.trade} · ${c.hp}/${c.hp_max} hp · ${c.gold} gold · ${c.standing}`})}
  for(const n in tokens)if(!live.has(n)){tokens[n].remove();delete tokens[n]}
  if(hover&&tokens[hover])tip(tokens[hover]);else $('tips').innerHTML='';
  if(selected)showPlace(s)}
 function tip(t){const g=$('tips');g.innerHTML='';const m=/translate\(([-\d.]+),([-\d.]+)\)/.exec(t.getAttribute('transform'));if(!m)return;const x=+m[1],y=+m[2];
  const lines=[t.dataset.info].concat(t.dataset.action?['now: '+t.dataset.action]:[]);const w=Math.min(440,Math.max(...lines.map(l=>l.length))*6.4+20);
  const bx=Math.max(8,Math.min(1000-w-8,x-w/2)),by=y-44-lines.length*15;const box=el('g',{class:'tip',transform:`translate(${bx},${by})`},g);
  el('rect',{width:w,height:lines.length*15+10,rx:8},box);lines.forEach((l,i)=>el('text',{x:10,y:16+i*15},box).textContent=l.length>68?l.slice(0,67)+'…':l)}
 function bind(t,name){const svg=$('mapSvg');
  t.addEventListener('pointerenter',()=>{hover=name;render(S_)});t.addEventListener('pointerleave',()=>{if(!drag){hover=null;render(S_)}});
  t.addEventListener('pointerdown',e=>{drag={name,g:t};t.classList.add('drag');t.setPointerCapture(e.pointerId);e.preventDefault();e.stopPropagation()});
  t.addEventListener('pointermove',e=>{if(!drag||drag.g!==t)return;const p=svgPoint(svg,e);t.setAttribute('transform',`translate(${p.x},${p.y})`);highlight(nearest(S_,p))});
  t.addEventListener('pointerup',async e=>{if(!drag||drag.g!==t)return;const p=svgPoint(svg,e);const dest=nearest(S_,p);t.classList.remove('drag');drag=null;highlight(null);hover=null;
   if(dest&&dest!==t.dataset.place){const r=await App.api('/god/move',{name,place:dest});note(r.last_god);App.render(r)}else render(S_)});
  t.addEventListener('click',e=>e.stopPropagation())}
 function nearest(s,p){let best=null,bd=1e9;for(const [n,d] of Object.entries(s.map)){const dd=Math.hypot(d.x-p.x,d.y+30-p.y);if(dd<95){if(dd<bd){bd=dd;best=n}}}return best}
 function highlight(n){document.querySelectorAll('.node').forEach(x=>x.classList.toggle('hot',x.dataset.place===n))}
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){selected=null;showPlace(S_)}});
 function live(){try{const es=new EventSource('/events');es.onmessage=ev=>{const m=JSON.parse(ev.data);if(S_&&m.id!==S_.id)return;S_=Object.assign(S_||{},m);render(S_);const st=document.getElementById('statusText');if(st&&!m.current)st.textContent=`Day ${m.day} · ${({idle:'Not started',running:'Running',paused:'Paused',done:'The year is over',stopped:'Stopped'})[m.status]||m.status}`;else if(st){const who=m.current.split(', ');st.innerHTML=who.length>2?`<b>${who.length} people</b> are speaking`:`<b>${esc(m.current)}</b> ${who.length>1?'are':'is'} speaking`}};es.onerror=()=>{es.close();setTimeout(live,3000)}}catch(e){setTimeout(live,3000)}}
 live();
 return {render,close:()=>{selected=null;showPlace(S_)}}})();
