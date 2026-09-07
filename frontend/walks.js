// Walks: how a token moves, planned as pure data so the map (in the browser) and the tests (in node) share it.
// A timeline is a list of segments in seconds from its base time: a walk along the paths, point to point, then a stay
// at a place with the bar filling. A walk's length scales with the path, never under MIN_WALK seconds. A timeline can
// begin where the token is now rather than at the activity's first place, so a walk already under way is finished to
// wherever the engine says they got, and a position that changes without any walk still walks the path, never jumps.
(function(root){
 const WALK=1.4,RUSH=0.25,MIN_WALK=2;
 function pathBetween(m,a,b){if(a===b||!m[a]||!m[b])return [a,b].filter((x,i,arr)=>m[x]&&arr.indexOf(x)===i);const prev={[a]:null};let q=[a];
  while(q.length){const nq=[];for(const p of q){for(const n of (m[p].adj||[])){if(n in prev)continue;prev[n]=p;if(n===b){const out=[b];let c=b;while(prev[c]){c=prev[c];out.unshift(c)}return out}nq.push(n)}}q=nq}
  return [a,b]}
 const nodeXY=(m,p)=>{const d=m[p];return d?{x:d.x,y:d.y+70}:null};
 const walkSeconds=(hops,immediate)=>Math.max(MIN_WALK,hops*(immediate?RUSH:WALK));
 // the point on a polyline nearest to pt: which segment, and how far along it
 function nearest(pts,pt){let best={i:0,f:0,d:Infinity};for(let i=0;i<pts.length-1;i++){const a=pts[i],b=pts[i+1];const dx=b.x-a.x,dy=b.y-a.y;const L=dx*dx+dy*dy;
   const f=L?Math.max(0,Math.min(1,((pt.x-a.x)*dx+(pt.y-a.y)*dy)/L)):0;const x=a.x+dx*f,y=a.y+dy*f;const d=Math.hypot(pt.x-x,pt.y-y);if(d<best.d)best={i,f,d}}return best}
 // s: the snapshot (map); a: the activity; at: {x,y} where the token is now, or null; now: server seconds
 function buildTimeline(s,a,at,now){let t=0;const segs=[];let cur=(a.from&&s.map[a.from])?a.from:null;let base=a.started;let start=null;
  if(at&&at.x!=null){const from=cur?nodeXY(s.map,cur):null;if(!from||Math.hypot(from.x-at.x,from.y-at.y)>2){start={x:at.x,y:at.y};base=now}}
  for(const st of (a.stops||[])){if(!s.map[st.place])continue;
   if(start||(cur&&cur!==st.place)){const path=cur?pathBetween(s.map,cur,st.place):[st.place];let pts=path.map(p=>nodeXY(s.map,p)).filter(Boolean);
    if(start){if(pts.length>1){const n=nearest(pts,start);pts=[start].concat(pts.slice(n.i+1))}else pts=[start].concat(pts);start=null}
    if(pts.length<2)pts=pts.concat(pts);const hops=Math.max(1,pts.length-1);const dur=walkSeconds(hops,a.immediate);
    segs.push({kind:'walk',t0:t,t1:t+dur,pts,what:st.what});t+=dur}
   if(st.dur>0){segs.push({kind:'stay',t0:t,t1:t+st.dur,place:st.place,what:st.what});t+=st.dur}
   cur=st.place}
  return {segs,end:t,final:cur,what:a.what,state:a.state,base,provisional:!!a.provisional}}
 function posAt(tl,t,slotOf){for(const g of tl.segs){if(t>=g.t1)continue;const f=Math.max(0,(t-g.t0)/Math.max(.001,g.t1-g.t0));
   if(g.kind==='walk'){const n=g.pts.length-1;if(n<1)continue;const k=Math.min(n-1,Math.floor(f*n)),lf=f*n-k;const p=g.pts[k],q=g.pts[k+1];return {x:p.x+(q.x-p.x)*lf,y:p.y+(q.y-p.y)*lf,what:g.what,bar:null,walking:true}}
   const sl=slotOf(g.place);return {x:sl.x,y:sl.y,what:g.what,bar:f,walking:false}}
  return null}
 const keyOf=a=>a?`${a.started}|${a.state}|${a.what}|${a.provisional?'p':''}`:'';
 // One poll's worth of planning. prev: name -> {place, key, x, y} as the tokens stand; returns name -> {key, tl, place}
 // for everyone whose activity changed or whose place changed with no walk to carry them (that one gets a plain walk).
 function plan(s,prev,now){const out={};const acts=s.activities||{};
  for(const c of (s.characters||[])){if(!c.alive||c.gone||!s.map[c.location])continue;const p=prev[c.name]||null;const a=acts[c.name];const key=keyOf(a);const at=p&&p.x!=null?{x:p.x,y:p.y}:null;
   if(p&&key!==p.key&&a&&a.stops&&a.stops.length){out[c.name]={key,tl:buildTimeline(s,a,at,now),place:c.location};continue}
   if(!p&&a&&a.stops&&a.stops.length){out[c.name]={key,tl:buildTimeline(s,a,null,now),place:c.location};continue}
   if(p&&p.place&&p.place!==c.location&&s.map[p.place]){const walk={state:'moving',what:'',from:p.place,stops:[{place:c.location,what:'',dur:0}],started:now};out[c.name]={key:key||('move|'+now),tl:buildTimeline(s,walk,at,now),place:c.location};continue}
   if(p&&key!==p.key)out[c.name]={key,tl:null,place:c.location}}
  return out}
 const Walks={WALK,RUSH,MIN_WALK,pathBetween,nodeXY,walkSeconds,buildTimeline,posAt,plan,keyOf};
 if(typeof module!=='undefined'&&module.exports)module.exports=Walks;else root.Walks=Walks;
})(typeof window!=='undefined'?window:globalThis);
