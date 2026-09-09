// Checks for frontend/face.js, run by tests/test_portraits.py under node. Prints PASS lines, exits 1 on the first failure.
// The drawing half must be a pure function of the spec: the same spec always draws the same picture, and a different
// person always draws a different one.
const path=require('path');const Face=require(path.join(__dirname,'..','frontend','face.js'));
function ok(cond,msg){if(!cond){console.error('FAIL '+msg);process.exit(1)}console.log('PASS '+msg)}

const A={shape:'oval',skin:'#dcae86',hair:'long',haircol:'#3a2418',eyes:'wide',eyecol:'#3c2a1a',nose:1,mouth:2,brow:1,ears:1,
         beard:'full',hat:'hood',cloth:'#d0a92c',lines:2,scar:1,thin:1,pale:1,dead:false,gone:false,sick:false};
const B=Object.assign({},A,{shape:'round',hair:'braid',hat:'straw',beard:'none',lines:0,scar:0,thin:0,pale:0});

ok(Face.svg(A,60)===Face.svg(A,60),'the same spec draws the same picture, every time');
ok(Face.svg(A,60)!==Face.svg(B,60),'a different person draws a different picture');
ok(Face.svg(A,60)!==Face.svg(A,160),'and the same person draws at whatever size is asked for');

for(const size of [20,60,160]){const s=Face.svg(A,size);
 ok(s.startsWith('<svg')&&s.endsWith('</svg>'),`${size} gives one whole svg element`);
 ok(s.includes(`width="${size}" height="${size}"`)&&s.includes('viewBox="0 0 100 100"'),`${size} is drawn in the same 100 by 100 box`)}

// every part of the person reaches the picture
const parts=[['scar','#a4564a'],['cloth','#d0a92c'],['skin',null],['haircol',null]];
ok(Face.svg(A,60).includes('#a4564a'),'a scar is drawn');
ok(!Face.svg(B,60).includes('#a4564a'),'and only when they have one');
ok(Face.svg(A,60).includes('#d0a92c'),'the clothes are the seat colour');
ok(Face.svg(Object.assign({},A,{pale:0}),60)!==Face.svg(Object.assign({},A,{pale:2}),60),'health changes the face');
ok(Face.svg(Object.assign({},A,{lines:0}),60)!==Face.svg(Object.assign({},A,{lines:3}),60),'and so do the years');
ok(Face.svg(Object.assign({},A,{dead:true}),60)!==Face.svg(A,60),'the dead are drawn differently');

// the map token asks for the head alone: no plate behind it and no shoulders
const head=Face.svg(A,20,{head:true,plate:false});
ok(!head.includes('<rect x="0" y="0" width="100" height="100"'),'the head alone carries no plate behind it');
ok(head.includes('scale(1.42)'),'the head alone fills the box');
ok(Face.markup(A).length>0&&!Face.markup(A).startsWith('<svg'),'markup gives the inside of an svg, for embedding in one');

// a missing or half filled spec still draws something rather than throwing
ok(Face.svg({},40).length>0,'an empty spec still draws a face');
ok(Face.svg({hat:'nonesuch',hair:'nonesuch',eyes:'nonesuch'},40).length>0,'and so does one full of words it does not know');
console.log('ALL PASS');
