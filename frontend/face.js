// Faces: the drawing half. backend/portrait.py settles what a person looks like and hands over a small spec; this
// draws that spec, and nothing here rolls anything or reads a person. Same spec in, same markup out, every time.
// One picture at three sizes: 20 on a map token, 60 on a card, 160 in the editor, all off the same 100 by 100 box.
(function(root){
 const H=(t,a,inner)=>{let s='<'+t;for(const k in a){if(a[k]===null||a[k]===undefined||a[k]==='')continue;s+=' '+k+'="'+String(a[k]).replace(/"/g,'&quot;')+'"'}return inner===undefined?s+'/>':s+'>'+inner+'</'+t+'>'};
 const hex=c=>/^#[0-9a-fA-F]{6}$/.test(c||'')?c:'#7f6a4a';
 // toward a colour, by f from 0 to 1: shade darkens, tint lifts, wash pulls the life out of it
 function mix(c,to,f){c=hex(c);const p=i=>parseInt(c.slice(i,i+2),16),q=i=>parseInt(to.slice(i,i+2),16);
  return '#'+[1,3,5].map(i=>Math.round(p(i)+(q(i)-p(i))*f).toString(16).padStart(2,'0')).join('')}
 const dark=(c,f)=>mix(c,'#000000',f), light=(c,f)=>mix(c,'#ffffff',f), grey=(c,f)=>mix(c,'#8d8880',f);

 // ---------- the head, one path per shape, all on the same centre
 const CX=50,CY=46;
 function headPath(shape,thin){
  const w=(shape==='long'?22:shape==='round'?27:shape==='square'?26:shape==='heart'?26:25)-(thin?3:0);
  const h=shape==='long'?33:shape==='round'?27:shape==='square'?29:30;
  if(shape==='square')return `M${CX-w} ${CY-h+8} q0 -8 8 -8 h${2*w-16} q8 0 8 8 v${2*h-18} q0 10 -10 10 h${-(2*w-20)} q-10 0 -10 -10 Z`;
  if(shape==='heart')return `M${CX-w} ${CY-h+10} q0 -10 ${w} -10 q${w} 0 ${w} 10 q0 ${h*0.9} -${w*0.55} ${h*1.2} q-${w*0.45} ${h*0.32} -${w*0.9} 0 q-${w*0.55} -${h*0.3} -${w*0.55} -${h*1.2} Z`;
  return `M${CX-w} ${CY} a${w} ${h} 0 1 1 ${2*w} 0 a${w} ${h} 0 1 1 ${-2*w} 0 Z`}
 const headHalfWidth=(shape,thin)=>(shape==='long'?22:shape==='round'?27:shape==='square'?26:shape==='heart'?26:25)-(thin?3:0);
 const headBottom=(shape)=>CY+(shape==='long'?33:shape==='round'?27:shape==='square'?29:30);

 // ---------- hair
 function hair(sp,skin){const c=hex(sp.haircol),w=headHalfWidth(sp.shape,sp.thin),back=[],front=[];
  if(sp.hair==='bald')return {back:'',front:H('path',{d:`M${CX-w-1} ${CY-4} q2 -12 10 -16 q-6 10 -4 17 Z`,fill:c,opacity:.75})+H('path',{d:`M${CX+w+1} ${CY-4} q-2 -12 -10 -16 q6 10 4 17 Z`,fill:c,opacity:.75})};
  const cap=`M${CX-w-1} ${CY-6} q0 -26 ${w+1} -26 q${w+1} 0 ${w+1} 26 q-4 -16 -${w+1} -16 q-${w-3} 0 -${w+1} 16 Z`;
  front.push(H('path',{d:cap,fill:c}));
  if(sp.hair==='wild')front.push(H('path',{d:`M${CX-w-3} ${CY-12} l6 -8 l2 7 l6 -11 l3 8 l6 -12 l4 9 l5 -9 l4 10 l5 -6 l2 9 Z`,fill:c}));
  if(sp.hair==='cropped')front.push(H('path',{d:`M${CX-w} ${CY-14} q${w} -8 ${2*w} 0 q-${w} -5 -${2*w} 0 Z`,fill:dark(c,.2)}));
  if(sp.hair==='long'){back.push(H('path',{d:`M${CX-w-4} ${CY-14} q-4 30 -2 46 h${2*w+12} q2 -16 -2 -46 q-6 20 -${w+2} 20 q-${w-4} 0 -${w+2} -20 Z`,fill:c}))}
  if(sp.hair==='bob'){back.push(H('path',{d:`M${CX-w-3} ${CY-14} q-3 22 0 30 h${2*w+6} q3 -8 0 -30 Z`,fill:c}))}
  if(sp.hair==='braid'){back.push(H('path',{d:`M${CX+w-2} ${CY-8} q10 6 8 22 q-2 14 -8 18 q4 -18 -2 -30 Z`,fill:c}));
   for(let i=0;i<4;i++)back.push(H('ellipse',{cx:CX+w+4,cy:CY+8+i*8,rx:4,ry:3.6,fill:dark(c,.15)}))}
  if(sp.hair==='topknot')front.push(H('circle',{cx:CX,cy:CY-30,r:8,fill:c})+H('rect',{x:CX-6,y:CY-24,width:12,height:5,rx:2,fill:dark(c,.3)}));
  return {back:back.join(''),front:front.join('')}}

 // ---------- eyes, brows, nose, mouth
 function eyes(sp,ink){const y=CY-2,dx=11,c=hex(sp.eyecol),out=[];
  for(const s of [-1,1]){const x=CX+s*dx;
   if(sp.dead){out.push(H('path',{d:`M${x-5} ${y} q5 4 10 0`,fill:'none',stroke:ink,'stroke-width':1.6,'stroke-linecap':'round'}));continue}
   const rx=sp.eyes==='narrow'?4.6:sp.eyes==='wide'?4.6:sp.eyes==='round'?3.8:4.2;
   const ry=sp.eyes==='narrow'?1.7:sp.eyes==='wide'?3.4:sp.eyes==='round'?3.8:sp.eyes==='deep'?2.4:2.2;
   out.push(H('ellipse',{cx:x,cy:y,rx:rx,ry:ry,fill:'#f7f2e8'}));
   out.push(H('circle',{cx:x,cy:y,r:Math.min(1.9,ry*0.85),fill:c}));
   out.push(H('circle',{cx:x,cy:y,r:Math.min(0.9,ry*0.45),fill:'#14100c'}));
   out.push(H('path',{d:`M${x-rx-.6} ${y} a${rx+.6} ${ry+.6} 0 0 1 ${2*(rx+.6)} 0`,fill:'none',stroke:ink,'stroke-width':1.1,'stroke-linecap':'round'}));
   if(sp.eyes==='hooded')out.push(H('path',{d:`M${x-rx-1} ${y-1.4} q${rx+1} -3 ${2*rx+2} 0`,fill:'none',stroke:ink,'stroke-width':1.2,opacity:.7}));
   if(sp.eyes==='deep')out.push(H('path',{d:`M${x-rx-1} ${y-3.4} q${rx+1} 2 ${2*rx+2} 0`,fill:'none',stroke:ink,'stroke-width':.9,opacity:.5}))}
  return out.join('')}
 function brows(sp,ink){const y=CY-9.5,dx=11,out=[];
  for(const s of [-1,1]){const x=CX+s*dx;
   const d=sp.brow===0?`M${x-6} ${y} h12`:sp.brow===1?`M${x-6} ${y+1} q6 -4 12 0`:`M${x-6*s} ${y+2} L${x+6*s} ${y-1}`;
   out.push(H('path',{d:d,fill:'none',stroke:dark(hex(sp.haircol),.25),'stroke-width':2.2,'stroke-linecap':'round'}))}
  return out.join('')}
 function nose(sp,ink){const y=CY+7;
  const d=[`M${CX} ${y-8} v9 q0 3 3 3`,
           `M${CX-1} ${y-7} q-2 8 1 10 q3 2 5 -1`,
           `M${CX} ${y-8} v10 m-4 0 q4 3 8 0`,
           `M${CX+1} ${y-8} q3 7 0 10 q-3 2 -5 0`][sp.nose%4];
  return H('path',{d:d,fill:'none',stroke:ink,'stroke-width':1.4,'stroke-linecap':'round','stroke-linejoin':'round',opacity:.8})}
 function mouth(sp,ink){const y=CY+18;
  const d=[`M${CX-8} ${y} q8 4 16 0`,`M${CX-7} ${y} h14`,`M${CX-8} ${y+1} q8 -5 16 0`,`M${CX-7} ${y} q7 6 14 0 q-7 -3 -14 0`][sp.mouth%4];
  return H('path',{d:d,fill:sp.mouth%4===3?'#8c4f4a':'none',stroke:'#7a4038','stroke-width':1.7,'stroke-linecap':'round'})}

 // ---------- what the years and the winter do
 function wear(sp,ink){const out=[];const w=headHalfWidth(sp.shape,sp.thin);
  if(sp.lines>=1)out.push(H('path',{d:`M${CX-9} ${CY-17} q9 -3 18 0`,fill:'none',stroke:ink,'stroke-width':1,opacity:.35}));
  if(sp.lines>=2){out.push(H('path',{d:`M${CX-7} ${CY+9} q-3 8 -1 12`,fill:'none',stroke:ink,'stroke-width':1,opacity:.35}));
   out.push(H('path',{d:`M${CX+7} ${CY+9} q3 8 1 12`,fill:'none',stroke:ink,'stroke-width':1,opacity:.35}))}
  if(sp.lines>=3){out.push(H('path',{d:`M${CX-9} ${CY-21} q9 -3 18 0`,fill:'none',stroke:ink,'stroke-width':1,opacity:.3}));
   for(const s of [-1,1])out.push(H('path',{d:`M${CX+s*17} ${CY-3} l${s*4} -2 m${-s*4} 4 l${s*4} 0 m${-s*4} 2 l${s*4} 2`,fill:'none',stroke:ink,'stroke-width':.9,opacity:.35}))}
  if(sp.thin){out.push(H('path',{d:`M${CX-w+3} ${CY+2} q3 8 1 13`,fill:'none',stroke:ink,'stroke-width':1.1,opacity:.4}));
   out.push(H('path',{d:`M${CX+w-3} ${CY+2} q-3 8 -1 13`,fill:'none',stroke:ink,'stroke-width':1.1,opacity:.4}))}
  if(sp.scar)out.push(H('path',{d:`M${CX+13} ${CY-16} L${CX+8} ${CY+4}`,fill:'none',stroke:'#a4564a','stroke-width':1.6,'stroke-linecap':'round',opacity:.85}));
  if(sp.sick)out.push(H('ellipse',{cx:CX,cy:CY+2,rx:w-2,ry:16,fill:'#7f9a5c',opacity:.14}));
  return out.join('')}
 function beard(sp){const c=hex(sp.haircol),w=headHalfWidth(sp.shape,sp.thin),b=headBottom(sp.shape);
  if(sp.beard==='none')return '';
  if(sp.beard==='stubble')return H('path',{d:`M${CX-w+2} ${CY+10} q${w-2} ${b-CY-2} ${2*w-4} 0 q-${w-2} 12 -${2*w-4} 0 Z`,fill:c,opacity:.22});
  if(sp.beard==='goatee')return H('path',{d:`M${CX-5} ${CY+22} q5 -3 10 0 q1 10 -5 12 q-6 -2 -5 -12 Z`,fill:c});
  if(sp.beard==='mutton')return H('path',{d:`M${CX-w} ${CY-4} q3 20 8 26 q-10 -2 -12 -14 Z`,fill:c})+H('path',{d:`M${CX+w} ${CY-4} q-3 20 -8 26 q10 -2 12 -14 Z`,fill:c});
  return H('path',{d:`M${CX-w-1} ${CY+4} q2 ${b-CY+8} ${w+1} ${b-CY+8} q${w-1} 0 ${w+1} -${b-CY+8} q-4 16 -${w+1} 16 q-${w-3} 0 -${w+1} -16 Z`,fill:c})}

 // ---------- what they wear, over everything. A hood, a coif, a wimple and a veil are one shape with the face cut out
 // of it, so the face is never buried by what is on top of it.
 function opening(w){const rx=w-1,ry=23;return `M${CX-rx} ${CY+3} a${rx} ${ry} 0 1 0 ${2*rx} 0 a${rx} ${ry} 0 1 0 ${-2*rx} 0 Z`}
 function framed(outer,w,fill,stroke,opacity){
  return H('path',{d:outer+' '+opening(w),'fill-rule':'evenodd',fill:fill,stroke:stroke,'stroke-width':stroke?1.1:null,opacity:opacity||null})}
 function hat(sp){const cl=hex(sp.cloth),w=headHalfWidth(sp.shape,sp.thin);
  switch(sp.hat){
   case 'cap':return H('path',{d:`M${CX-w-2} ${CY-14} q2 -20 ${w+2} -20 q${w} 0 ${w+2} 20 q-${w+2} -8 -${2*w+4} 0 Z`,fill:dark(cl,.25)});
   case 'hood':return framed(`M${CX-w-7} ${CY+30} q-7 -44 ${w+7} -46 q${w+7} 2 ${w+7} 46 Z`,w,cl,dark(cl,.4));
   case 'coif':return framed(`M${CX-w-4} ${CY+16} q-4 -40 ${w+4} -40 q${w+4} 0 ${w+4} 40 Z`,w,'#e7e1d2','#b9b2a1');
   case 'wimple':return framed(`M${CX-w-6} ${CY+34} q-6 -42 ${w+6} -44 q${w+6} 2 ${w+6} 44 Z`,w,'#ded7c6','#b0a897');
   case 'veil':return framed(`M${CX-w-7} ${CY+34} q-5 -46 ${w+7} -46 q${w+7} 0 ${w+7} 46 Z`,w,'#efe9dc','',.85);
   case 'straw':return H('ellipse',{cx:CX,cy:CY-16,rx:w+18,ry:6,fill:'#d9be74'})+H('path',{d:`M${CX-w-1} ${CY-16} q2 -18 ${w+1} -18 q${w-1} 0 ${w+1} 18 Z`,fill:'#c9a94f'});
   case 'helm':return H('path',{d:`M${CX-w-2} ${CY-6} q0 -28 ${w+2} -28 q${w+2} 0 ${w+2} 28 q-4 -10 -8 -12 h${-(2*w-12)} q-4 2 -8 12 Z`,fill:'#8e9299',stroke:'#5d6167','stroke-width':1.2})
     +H('rect',{x:CX-2,y:CY-14,width:4,height:20,rx:1.6,fill:'#8e9299',stroke:'#5d6167','stroke-width':1});
   case 'hat':return H('ellipse',{cx:CX,cy:CY-17,rx:w+11,ry:5,fill:dark(cl,.4)})+H('path',{d:`M${CX-w+2} ${CY-17} q0 -16 ${w-2} -16 q${w-2} 0 ${w-2} 16 Z`,fill:dark(cl,.25)});
   default:return ''}}

 // ---------- the whole picture, in one 100 by 100 box
 function markup(spec,opts){const sp=Object.assign({shape:'oval',skin:'#dcae86',hair:'short',haircol:'#3a2418',eyes:'wide',eyecol:'#3c2a1a',
   nose:0,mouth:0,brow:1,ears:0,beard:'none',hat:'none',cloth:'#7f6a4a',lines:0,scar:0,thin:0,pale:0,dead:false,gone:false,sick:false},spec||{});
  opts=opts||{};
  let skin=hex(sp.skin);
  if(sp.pale>=1)skin=light(grey(skin,sp.pale>=2?.55:.28),sp.pale>=2?.12:.06);
  if(sp.dead)skin=grey(skin,.72);
  const ink=dark(skin,.62), cl=hex(sp.cloth), hr=hair(sp,skin);
  const parts=[];
  if(opts.plate!==false&&!opts.head)parts.push(H('rect',{x:0,y:0,width:100,height:100,rx:opts.round?50:10,fill:opts.bg||'#211e19'}));
  const body=[];
  if(!opts.head){                                        // shoulders, so a card reads as a person and not a mask
   body.push(H('path',{d:`M46 ${headBottom(sp.shape)-6} h8 v14 q-4 3 -8 0 Z`,fill:dark(skin,.16)}));
   body.push(H('path',{d:'M11 100 q5 -14 25 -18 q14 -3 28 0 q20 4 25 18 Z',fill:cl,stroke:dark(cl,.4),'stroke-width':1.2}))}
  body.push(hr.back);
  if(sp.ears){for(const s of [-1,1])body.push(H('ellipse',{cx:CX+s*(headHalfWidth(sp.shape,sp.thin)+1),cy:CY+3,rx:3.4,ry:5,fill:skin,stroke:ink,'stroke-width':1}))}
  body.push(H('path',{d:headPath(sp.shape,sp.thin),fill:skin,stroke:ink,'stroke-width':1.3}));
  body.push(beard(sp));
  body.push(hr.front);
  body.push(brows(sp,ink),eyes(sp,ink),nose(sp,ink),mouth(sp,ink),wear(sp,ink));
  body.push(hat(sp));
  if(sp.gone)body.push(H('rect',{x:0,y:0,width:100,height:100,fill:'#0b0a08',opacity:.35}));
  parts.push(opts.head?H('g',{transform:'translate(50,54) scale(1.42) translate(-50,-46)'},body.join('')):body.join(''));
  return parts.join('')}

 function svg(spec,size,opts){opts=opts||{};
  return H('svg',{width:size,height:size,viewBox:'0 0 100 100',class:'face '+(opts.cls||''),'aria-hidden':'true',focusable:'false'},markup(spec,opts))}

 const Face={markup,svg,mix,dark,light,grey};
 if(typeof module!=='undefined'&&module.exports)module.exports=Face;else root.Face=Face;
})(typeof window!=='undefined'?window:globalThis);
