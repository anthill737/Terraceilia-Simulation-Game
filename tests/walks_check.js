// Checks for frontend/walks.js, run by tests/test_movement.py under node. Prints PASS lines, exits 1 on the first failure.
const path=require('path');const Walks=require(path.join(__dirname,'..','frontend','walks.js'));
function ok(cond,msg){if(!cond){console.error('FAIL '+msg);process.exit(1)}console.log('PASS '+msg)}
// a chain of seven places, 100 apart
const names=['A','B','C','D','E','F','G'];const map={};names.forEach((n,i)=>map[n]={x:100+i*100,y:300,adj:[names[i-1],names[i+1]].filter(Boolean)});
const chars=(locs)=>Object.entries(locs).map(([name,location],i)=>({name,location,alive:true,gone:false,seat:i+1}));
// six moves arriving in one poll, with no activity to carry them
const before={P1:'A',P2:'A',P3:'B',P4:'C',P5:'D',P6:'E'},after={P1:'B',P2:'D',P3:'E',P4:'A',P5:'G',P6:'F'};
const prev={};for(const n in before)prev[n]={place:before[n],key:'',x:Walks.nodeXY(map,before[n]).x,y:Walks.nodeXY(map,before[n]).y};
const plan=Walks.plan({map,characters:chars(after),activities:{}},prev,1000);
const walks=Object.values(plan).filter(p=>p.tl&&p.tl.segs.some(g=>g.kind==='walk'));
ok(walks.length===6,'six position changes in one poll give six walk animations, got '+walks.length);
ok(walks.every(p=>p.tl.segs[0].t1-p.tl.segs[0].t0>=Walks.MIN_WALK),'every walk lasts at least two seconds');
const one=plan.P1.tl.segs[0],three=plan.P2.tl.segs[0];
ok(three.t1-three.t0>one.t1-one.t0,'a three hop walk lasts longer than a one hop walk');
ok(plan.P2.tl.segs[0].pts.length===4&&plan.P2.tl.segs[0].pts[3].x===Walks.nodeXY(map,'D').x,'the walk follows the path node by node to the new place');
ok(Object.values(plan).every(p=>p.tl.base===1000),'a walk with no activity behind it starts now');
// a provisional walk toward a far place, then the engine says they got only one hop: the walk is finished from where the token is
const prov={state:'acting',what:'walking to G',from:'A',stops:[{place:'G',what:'walking to G',dur:0}],started:1000,provisional:true};
const tl1=Walks.buildTimeline({map},prov,null,1000);ok(tl1.provisional&&tl1.final==='G'&&tl1.segs[0].pts.length===7,'a provisional walk heads for the destination along the whole path');
const mid=Walks.posAt(tl1,(tl1.end)*0.4,()=>({x:0,y:0}));ok(mid&&mid.walking&&mid.x>Walks.nodeXY(map,'B').x,'part way through the token is well along the path');
const settled={state:'acting',what:'walking to B',from:'A',stops:[{place:'B',what:'walking to B',dur:3}],started:1010};
const tl2=Walks.buildTimeline({map},settled,{x:mid.x,y:mid.y},1010);
ok(tl2.base===1010&&tl2.segs[0].kind==='walk'&&tl2.segs[0].pts[0].x===mid.x,'the settled walk starts from where the token is, not from the old place');
ok(tl2.segs[0].pts[tl2.segs[0].pts.length-1].x===Walks.nodeXY(map,'B').x&&tl2.final==='B','and ends where the engine says they got');
ok(tl2.segs[0].t1-tl2.segs[0].t0>=Walks.MIN_WALK,'even a short walk back takes two seconds');
// an activity whose key did not change and whose place did not change plans nothing
const same=Walks.plan({map,characters:chars({P1:'B'}),activities:{}},{P1:{place:'B',key:'',x:0,y:0}},1000);ok(Object.keys(same).length===0,'nothing to do when nothing changed');
// a rush (an emergency) still lasts two seconds
const rush={state:'emergency',what:'fire',from:'A',stops:[{place:'B',what:'fire',dur:0}],started:1000,immediate:true};
ok(Walks.buildTimeline({map},rush,null,1000).segs[0].t1>=Walks.MIN_WALK,'a rush is never under two seconds');
console.log('ALL PASS');
