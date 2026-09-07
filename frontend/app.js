// Terraceilia: the shell around the map. Gameplay sits in plain buttons; everything else lives behind the gear.
let S=null,editing=false,providers={},termKey='',sideTab='valley',centerTab='',openSheet='',tgBot='';
let T=[],lastTurn=-1,Tid=null;
function mergeTranscript(s){if(s.id!==Tid||s.transcript_total<T.length||(s.transcript&&s.transcript.length&&T.length&&s.transcript[0].turn<=lastTurn&&s.transcript_total!==T.length)){T=s.transcript?s.transcript.slice():[];Tid=s.id}else if(s.transcript)for(const e of s.transcript)if(e.turn>lastTurn)T.push(e);lastTurn=T.length?T[T.length-1].turn:-1;s.transcript=T}
const $=id=>document.getElementById(id);
async function api(p,b){const r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):null});return r.json()}
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const STATUS={idle:'Not started',running:'Running',paused:'Paused',done:'The year is over',stopped:'Stopped'};
const mobile=()=>window.matchMedia('(max-width:820px)').matches;
let chronShown=false;
function chronBottom(){const c=$('chron');requestAnimationFrame(()=>{c.scrollTop=c.scrollHeight})}
function seatColor(n){const x=(S&&S.seats||[]).find(y=>y.name===n);return x?x.color:''}
function rich(t){let h=esc(t);const hold=[];const keep=x=>{hold.push(x);return `\u0000${hold.length-1}\u0000`};
 h=h.replace(/^\s*ACTION:\s*(.+)$/gm,(m,a)=>keep(`<span class="act">ACTION: ${a}</span>`));
 h=h.replace(/@([A-Za-z][\w-]*)/g,(m,n)=>{const c=seatColor(n);return `<span class="men" style="${c?'--mc:'+esc(c):''}">@${n}</span>`});
 h=h.replace(/((?:^\|.*\|\s*$\n?)+)/gm,tbl=>{const rows=tbl.trim().split('\n').filter(r=>!/^\|[-| ]+\|$/.test(r));return keep('<table class="st">'+rows.map((r,i)=>'<tr>'+r.split('|').slice(1,-1).map(c=>`<${i?'td':'th'}>${c.trim()}</${i?'td':'th'}>`).join('')+'</tr>').join('')+'</table>')});
 h=h.replace(/\u0000(\d+)\u0000/g,(m,i)=>hold[+i]);
 return h.split(/\n{2,}/).map(p=>`<p>${p.replace(/\n/g,'<br>')}</p>`).join('')}
function fillSel(sel,opts,val){const h=opts.map(o=>`<option ${o===val?'selected':''}>${esc(o)}</option>`).join('');if(sel.innerHTML!==h)sel.innerHTML=h;sel.value=val}
function modelUI(pfx,val){const p=$(pfx+'_p'),m=$(pfx+'_m'),c=$(pfx+'_c');fillSel(p,Object.keys(providers),val.provider);const ms=(providers[val.provider]||{models:[]}).models.concat(['Custom...']);const known=ms.includes(val.model);fillSel(m,ms,known?val.model:'Custom...');c.style.display=known?'none':'';if(!known)c.value=val.model}
function modelVal(pfx){const m=$(pfx+'_m').value;return {provider:$(pfx+'_p').value,model:m==='Custom...'?($(pfx+'_c').value.trim()||''):m}}
const DRAMA=['nothing','a whisper','quiet','calm','ordinary','lively','eventful','hard','harsh','brutal','chaos'];

// ---------- setup screen (a game that has not started)
function renderSetup(s){$('title').value=s.title;$('world_text').value=s.world_text;$('players').value=s.players;$('max_days').value=s.max_days;$('max_minutes').value=s.max_minutes||'';$('repo').value=s.repo;$('drama').value=s.drama??6;$('dramaNote').textContent=($('drama').value)+' \u00b7 '+DRAMA[+$('drama').value];
 modelUI('wm',s.world_model);modelUI('ma',s.model_a);modelUI('mb',s.model_b);modelUI('mm',s.map_model||s.world_model);
 $('map_source').value=s.map_source||'builtin';$('mapModelRow').style.display=$('map_source').value==='generated'?'':'none'}

// ---------- the valley panel
const FEEL=['hates','despises','dislikes','is cold toward','is cool toward','is indifferent to','is warm toward','likes','is fond of','cares deeply for','loves'];
function relChips(s,name){const rs=(s.relations||{})[name]||{};const items=Object.entries(rs).filter(([b,r])=>r.type!=='none'||r.feeling||r.trust).sort((x,y)=>(Math.abs(y[1].feeling)+Math.abs(y[1].trust))-(Math.abs(x[1].feeling)+Math.abs(x[1].trust)));
 if(!items.length)return '';const chip=([b,r])=>{const hue=r.feeling>0?'var(--accent)':r.feeling<0?'var(--danger)':'var(--faint)';return `<span class="rel" data-a="${esc(name)}" data-b="${esc(b)}" title="${esc(name)} ${FEEL[r.feeling+5]} ${esc(b)}. Click for why." style="--h:${hue}"><b>${esc(b)}</b> ${r.type!=='none'?esc(r.type)+' \u00b7 ':''}<i>${r.feeling>=0?'+':''}${r.feeling}</i><i class="t">${r.trust>=0?'+':''}${r.trust}</i></span>`};return '<div class="rels">'+items.slice(0,6).map(chip).join('')+(items.length>6?`<details class="more" data-k="r:${esc(name)}"><summary>${items.length-6} more</summary>${items.slice(6).map(chip).join('')}</details>`:'')+'</div>'}
function renderValley(s){if(!s.created){$('valley').innerHTML='<div class="empty">The valley appears here once the World has rolled it.</div>';return}
 const wasOpen=new Set([...$('valley').querySelectorAll('details[open]')].map(d=>d.dataset.k));const scroll=$('valley').scrollTop;
 const L=s.ledger;const pct=Math.min(100,Math.round(100*L.grain_weeks/L.grain_needed));
 let h=`<div class="ledger"><b>Day ${s.day}</b> &middot; grain for <b>${L.grain_weeks}</b> of ${L.grain_needed} weeks<div class="bar" style="--c:var(--accent)"><i style="width:${pct}%"></i></div>${L.roofs_broken} roofs broken &middot; road ${L.road_safe?'safe':'unsafe'} after dark &middot; ${L.sick} sick<br>Built: ${esc(L.built.join(', ')||'nothing yet')}${s.pending.length?`<br><span class="note">${s.pending.length} action(s) waiting for the World</span>`:''}</div>`;
 const byPlace={};s.characters.forEach(c=>{(byPlace[c.alive&&!c.banished?c.location:'Gone']=byPlace[c.alive&&!c.banished?c.location:'Gone']||[]).push(c)});
 const th=(s.threads||[]).filter(t=>t.status==='open');if(th.length)h+=`<div class="ledger"><b>Open situations</b> (${th.length})${th.map(t=>`<div class="thr">#${t.id} \u00b7 day ${t.day}${t.place?' \u00b7 '+esc(t.place):''}: ${esc(t.text)}</div>`).join('')}</div>`;
 h+=Object.entries(byPlace).map(([pl,cs])=>`<div class="place">${esc(pl)}</div>`+cs.map(c=>`<div class="card ${c.alive?'':'dead'}" style="--c:${esc(seatColor(c.name)||'#888')}"><span class="nm">${esc(c.name)}</span> <span class="st">${esc(c.trade)} &middot; ${esc(c.location)} &middot; ${esc(c.standing)}${c.banished?' &middot; banished':''}${c.alive?'':' &middot; dead: '+esc(c.cause_of_death)}</span>
  <div class="bar"><i style="width:${Math.round(100*c.hp/c.hp_max)}%"></i></div>HP ${c.hp}/${c.hp_max} &middot; STR ${c.str} SPD ${c.spd} &middot; gold ${c.gold} &middot; ${Object.keys(c.skills).length?Object.entries(c.skills).map(([k,v])=>k+' '+v).join(', '):'no skills'}
  ${relChips(s,c.name)}
  <details data-k="p:${esc(c.name)}"><summary>${esc(c.personality)}</summary>${c.traits?'Disposition: '+Object.entries(c.traits).map(([k,v])=>k+' '+v).join(', ')+'<br>':''}Secret: ${esc(c.secret)}<br>Fear: ${esc(c.fear)}<br>Want: ${esc(c.want)}</details></div>`).join('')).join('');
 const html=h;if($('valley').dataset.html!==html){$('valley').innerHTML=html;$('valley').dataset.html=html;$('valley').querySelectorAll('details').forEach(d=>{if(wasOpen.has(d.dataset.k))d.open=true});$('valley').scrollTop=scroll;$('valley').querySelectorAll('.rel').forEach(ch=>ch.onclick=e=>{e.stopPropagation();showWhy(ch.dataset.a,ch.dataset.b)})}}
function renderTerms(s){if(!s.terms.length){$('terms').innerHTML='<div class="empty">Terminals appear after Start.</div>';termKey='';return}if(!wantTerms())return;
 const key=s.id+':'+s.terms.length;if(termKey!==key){termKey=key;$('terms').innerHTML=s.terms.map((t,i)=>`<div class="term" id="t${i}"><div class="tb"><span class="nm"></span><span class="st"></span></div><pre></pre></div>`).join('')}
 s.terms.forEach((t,i)=>{const el=$('t'+i);if(!el)return;const seat=s.seats[i]||{};el.style.setProperty('--c',seat.color||'#888');el.classList.toggle('speaking',t.state==='speaking');
  el.querySelector('.nm').innerHTML=`<b>${esc(seat.name)}</b> <span style="color:var(--faint)">${esc((seat.provider||'')+' \u00b7 '+(seat.model||''))}</span>`;el.querySelector('.st').textContent=t.state==='speaking'?'thinking':'';
  const pre=el.querySelector('pre');const atB=pre.scrollHeight-pre.scrollTop-pre.clientHeight<40;if(pre.dataset.count!=t.count&&t.lines.length){pre.textContent=t.lines.join('\n');pre.dataset.count=t.count;if(atB)pre.scrollTop=pre.scrollHeight}else if(!pre.textContent)pre.textContent='No live output yet.'})}
function renderRail(s){const live=new Set(s.live||[]);$('railCount').textContent=s.games.length;
 $('hlist').innerHTML=s.games.map(g=>`<div class="hitem ${g.id===s.id?'on':''}" data-id="${g.id}"><div class="t"><span>${live.has(g.id)?'<span class="livedot"></span>':''}${esc(g.title)}</span><button class="del" data-id="${g.id}" title="Delete">&times;</button></div><div class="m">${esc(g.created.replace('T',' '))} \u00b7 day ${g.day} \u00b7 ${esc(STATUS[g.status]||g.status)}</div></div>`).join('');
 document.querySelectorAll('.hitem').forEach(d=>d.onclick=async e=>{if(e.target.classList.contains('del')){if(confirm('Delete this game?'))render(await api('/game/delete',{id:e.target.dataset.id}));return}S=null;termKey='';render(await api('/game/open',{id:d.dataset.id}));if(mobile())showTab('map')})}

// ---------- the one render
function render(s){const first=!S||S.id!==s.id;if(first){T=[];lastTurn=-1}mergeTranscript(s);S=s;providers=s.providers;
 const busy=s.status==='running';const started=s.created||s.transcript.length>0||busy||s.status==='paused';
 $('hdrTitle').textContent=s.title||'';const who=s.current?s.current.split(', '):[];
 $('statusText').innerHTML=s.current?(who.length>2?`<b>${who.length} people</b> are speaking`:`<b>${esc(s.current)}</b> ${who.length>1?'are':'is'} speaking`):`Day ${s.day} \u00b7 ${STATUS[s.status]||s.status}`;
 $('status').classList.toggle('live',busy);
 const prim=$('primary');prim.textContent=busy?'Pause':s.status==='paused'?'Resume':started?(s.status==='done'?'Continue (6 more days)':'Continue'):'Start';
 prim.className=busy?'btn':'primary';
 $('start2').style.display=started?'none':'';$('sayBtn').disabled=!busy;
 const err=(s.blocked||s.start_error||'');$('startErr').classList.toggle('on',!!err);$('startErrText').textContent=err;
 if(first||!editing)renderSetup(s);renderRail(s);
 // a map that has been drawn can be looked at before the year starts, so Setup is a tab of its own until then
 const canMap=started||s.map_generated;
 if(!centerTab||first)centerTab=started?'map':(s.map_generated?'map':'setup');
 if(started&&centerTab==='setup')centerTab='map';
 if(!canMap)centerTab='setup';
 document.querySelectorAll('#centerTabs button').forEach(b=>{b.classList.toggle('on',b.dataset.c===centerTab);if(b.dataset.c==='setup')b.style.display=started?'none':''});
 if(!mobile()){$('centerTabs').style.display=canMap?'':'none';
  $('setup').style.display=centerTab==='setup'?'block':'none';
  $('map').classList.toggle('on',canMap&&centerTab==='map');
  $('chron').style.display=centerTab==='chron'?'block':'none';
  $('composer').style.display=started?'':'none'}
 if(canMap)MapView.render(s);
 $('making').style.display=(busy&&!s.created)?'flex':'none';
 if(busy&&!s.created){const drawing=s.map_source==='generated'&&!s.map_generated;
  $('makingHead').textContent=drawing?'The map is being drawn from your description':'The World is making the valley';
  $('makingNote').textContent=drawing?'The ground, the water, the sky, the places and the names all come from what you wrote. Then the World rolls the people. Watch the World\u2019s terminal.':'Rolling every life, secret, and grudge. This takes a minute or two. Watch the World\u2019s terminal.'}
 $('chronEmpty').style.display=s.transcript.length?'none':'block';
 const msgHtml=e=>`<div class="msg ${e.kind}${/^\s*WHISPER\s+@/im.test(e.text)?' whisper':''}${e.kind==='convener'&&/@[A-Za-z]/.test(e.text)?' private':''}" style="${e.color?'--c:'+esc(e.color):''}"><div class="hd"><span class="who">${esc(e.speaker)}</span><span class="meta">day ${e.day??0}${e.place?' \u00b7 '+esc(e.place):''} \u00b7 ${e.time}</span></div><div class="body">${rich(e.text)}</div></div>`;
 const have=$('msgs').children.length;
 if(first||have>s.transcript.length){$('msgs').innerHTML=s.transcript.map(msgHtml).join('');chronBottom()}
 else if(have<s.transcript.length){const atB=$('chron').scrollHeight-$('chron').scrollTop-$('chron').clientHeight<120;$('msgs').insertAdjacentHTML('beforeend',s.transcript.slice(have).map(msgHtml).join(''));if(atB)chronBottom()}
 // a hidden panel has no height to scroll, so land on the newest day the moment it is shown
 const chronNow=getComputedStyle($('chron')).display!=='none';
 if(chronNow&&!chronShown)chronBottom();
 chronShown=chronNow;
 $('typing').style.display=s.current?'block':'none';$('typing').textContent=s.current?(who.length>3?who.length+' people are':s.current+(who.length>1?' are':' is'))+' composing':'';
 renderValley(s);renderTerms(s);
 if(openSheet)refreshSheet(openSheet,s)}

// ---------- sheets, one at a time
function sheet(name){document.querySelectorAll('.sheetwrap').forEach(w=>w.classList.remove('open'));
 if(!name){openSheet='';return}openSheet=name;const w=$('sheet-'+name);if(!w)return;w.classList.add('open');refreshSheet(name,S)}
function refreshSheet(name,s){if(!s)return;
 if(name==='people')renderPeople(s);
 else if(name==='world')renderWorld(s);
 else if(name==='situations')renderSituations(s);
 else if(name==='fate')renderFate(s);
 else if(name==='connections'){renderConn(s);renderTg(s)}
 else if(name==='more')renderMore(s)}
document.querySelectorAll('.sheetclose').forEach(b=>b.onclick=()=>sheet(''));
document.querySelectorAll('.sheetwrap').forEach(w=>w.onclick=e=>{if(e.target===w)sheet('')});
document.querySelectorAll('.sheetbtn').forEach(b=>b.onclick=()=>sheet(b.dataset.sheet));
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(openSheet)sheet('');$('gearMenu').classList.remove('open')}});

// ---------- the gear
$('gearBtn').onclick=e=>{e.stopPropagation();$('gearMenu').classList.toggle('open')};
document.addEventListener('click',e=>{if(!$('gearMenu').contains(e.target))$('gearMenu').classList.remove('open')});
document.querySelectorAll('#gearMenu .list button').forEach(b=>b.onclick=async()=>{const g=b.dataset.g;$('gearMenu').classList.remove('open');
 if(g==='connections'){sheet('connections');api('/connect/refresh',{})}
 else if(g==='display')sheet('display');
 else if(g&&g.startsWith('x-'))window.location='/export?what='+g.slice(2);
 else if(g==='stop'){if(!confirm('Stop this year here? You can continue it later.'))return;$('statusText').textContent='Stopping...';render(await api('/stop',{}))}
 else if(g==='quit'){if(!confirm('Quit Terraceilia? Every CLI it started is killed. Games are kept.'))return;try{await api('/shutdown',{})}catch(e){}document.body.innerHTML='<div style="padding:40px;color:#8B8B94">Terraceilia is closed.</div>'}});

// ---------- People
function modelPick(pfx,val,selP,selM,inpC){fillSel(selP,Object.keys(providers),val.provider);const ms=(providers[val.provider]||{models:[]}).models.concat(['Custom...']);const known=ms.includes(val.model);fillSel(selM,ms,known?val.model:'Custom...');inpC.style.display=known?'none':'';if(!known)inpC.value=val.model;
 selP.onchange=()=>{const m2=(providers[selP.value]||{models:['']}).models.concat(['Custom...']);fillSel(selM,m2,m2[0]);inpC.style.display='none'};selM.onchange=()=>{inpC.style.display=selM.value==='Custom...'?'':'none';if(selM.value==='Custom...')inpC.focus()}}
function pickVal(selP,selM,inpC){const m=selM.value;return {provider:selP.value,model:m==='Custom...'?inpC.value.trim():m}}
// ---------- People: the character screen. Everyone across the top, the chosen one below.
let peoSel='',peoTab='bio',peoFilter='',tieSort='strongest',peoNote='',peoStripHtml='',peoPaneHtml='',peoShown='';
const REL=['none','spouse','lover','kin','friend','rival','enemy','creditor','debtor','master','servant'];
// key, label, the word at each end, and the five words the dial can read
const TRAITS=[
 ['warmth','Warmth','cruel','kind',['cruel and enjoys it','hard and unkind','neither kind nor cruel','decent','kind to a fault']],
 ['temper','Temper','unmoved','violent',['nothing moves them','keeps it unless pushed','an ordinary temper','flares fast','violent when crossed']],
 ['honesty','Honesty','liar','honest',['lies as easily as breathing','lies when it suits','bends it when it pays','mostly honest','cannot lie without it showing']],
 ['greed','Greed','giving','grasping',['gives without counting','shares when asked','wants a fair share','wants more than their share','would sell a grave for coin']],
 ['courage','Courage','coward','reckless',['runs from anything','avoids danger','takes ordinary risks','brave, sometimes stupidly','reckless']],
 ['tongue','Tongue','silent','talkative',['barely talks','blunt and short','talks like anyone else','articulate and clear','talks a lot']],
 ['desire','Desire','chaste','wanton',['no interest in anyone','keeps desire private','notices, sometimes acts','flirts and takes lovers','wanton, and the valley talks']],
 ['piety','Piety','godless','devout',['thinks the chapel a fraud','goes for appearances','believes quietly','devout, and judges by it','preaches whether asked or not']],
 ['ambition','Ambition','content','hungry',['wants to be left alone','wants a quiet life','a little better than their father','means to rise','means to run the valley']],
 ['loyalty','Loyalty','turncoat','faithful',['sells out anyone','loyal while it pays','keeps faith with their own','stands by friends at a cost','would die for their people']],
 ['cunning','Cunning','simple','scheming',['simple, says what they think','straightforward','sees a trick coming','sly, plans two moves ahead','a schemer, every friendship a piece']],
 ['drink','Drink','sober','drunkard',['never touches it','a cup at feast days','drinks like anyone','drinks too much','a drunkard']]];
const rxName=n=>new RegExp('(?<![\\w@])'+n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\b','i');

// cells you click, rather than a slider you drag
function seg(min,max,v){let h='';
 for(let i=min;i<=max;i++){
  const on=min<0?((v>0&&i>0&&i<=v)||(v<0&&i<0&&i>=v)):(i<=v);
  const cls=[on?'on':'',on&&v<0?'neg':'',(min<0&&i===0)?'mid':''].filter(Boolean).join(' ');
  h+=`<button type="button" data-i="${i}"${cls?` class="${cls}"`:''}></button>`}
 return `<div class="seg" data-v="${v}">${h}</div>`}

function renderPeople(s){const pane=$('peoPane');
 if(!s.characters.length){$('peoStrip').innerHTML='';$('peoPick').innerHTML='';$('peoHead').innerHTML='';peoStripHtml='';peoPaneHtml='';
  pane.innerHTML='<div class="empty">Nobody lives here yet. Press Start and the World rolls them.</div>';return}
 if(!s.characters.some(c=>c.name===peoSel))peoSel=s.characters[0].name;
 peoRenderStrip(s);
 // never rebuild the panel under someone's hands
 const busy=pane.contains(document.activeElement)&&/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||'');
 if(!busy)peoRenderPane(s)}

function peoRenderStrip(s){const q=peoFilter.trim().toLowerCase();
 const rows=s.characters.filter(c=>!q||`${c.name} ${c.trade||''} ${c.location}`.toLowerCase().includes(q));
 const html=rows.map(c=>`<button type="button" class="chip ${c.name===peoSel?'on':''} ${c.alive?'':'dead'}" data-n="${esc(c.name)}" style="--c:${esc(seatColor(c.name)||'#888')}" title="${esc(c.name)}, ${esc(c.trade||'no trade yet')}, at ${esc(c.location)}">
  <span class="cn"><span class="dot"></span>${esc(c.name)}</span><span class="cp">${esc(c.location)}</span>
  <span class="chp"><i style="width:${Math.max(0,Math.min(100,Math.round(100*c.hp/Math.max(1,c.hp_max))))}%"></i></span></button>`).join('')
  ||'<div class="empty">Nobody matches that.</div>';
 if(html!==peoStripHtml){$('peoStrip').innerHTML=html;peoStripHtml=html;
  $('peoStrip').querySelectorAll('.chip').forEach(b=>b.onclick=()=>{if(peoSel!==b.dataset.n){peoSel=b.dataset.n;peoNote='';peoPaneHtml=''}renderPeople(S)})}
 if(peoShown!==peoSel){peoShown=peoSel;const on=$('peoStrip').querySelector('.chip.on');
  if(on&&on.scrollIntoView)on.scrollIntoView({block:'nearest',inline:'nearest'})}
 const opts=rows.map(c=>`<option ${c.name===peoSel?'selected':''}>${esc(c.name)}</option>`).join('');
 const pick=$('peoPick');if(pick.innerHTML!==opts)pick.innerHTML=opts;
 if(pick.value!==peoSel)pick.value=peoSel}

function peoRenderPane(s){const c=s.characters.find(x=>x.name===peoSel);if(!c)return;
 const seat=(s.seats||[]).find(x=>x.name===c.name)||{};
 $('peoHead').innerHTML=`<b style="--c:${esc(seatColor(c.name)||'#888')}">${esc(c.name)}</b><span class="note">${esc(c.trade||'no trade yet')} \u00b7 ${esc(c.location)} \u00b7 ${c.alive?(c.banished?'banished':'alive'):'dead: '+esc(c.cause_of_death||'unknown')}${seat.provider?' \u00b7 '+esc(seat.provider)+' '+esc(seat.model||''):''}</span>`;
 document.querySelectorAll('.ptabs button').forEach(b=>b.classList.toggle('on',b.dataset.p===peoTab));
 const html=(peoTab==='bio'?paneBio(s,c):peoTab==='stats'?paneStats(s,c):peoTab==='disp'?paneDisp(s,c):peoTab==='ties'?paneTies(s,c):paneLog(s,c))
  +(peoTab==='log'?'':`<div class="note" style="margin-top:10px">${esc(peoNote)}</div>`);
 if(html===peoPaneHtml)return;
 $('peoPane').innerHTML=html;peoPaneHtml=html;peoWire(s,c)}

async function peoApply(patch){peoNote='';const r=await api('/edit/character',{name:peoSel,...patch});
 peoNote=r.last_god||'no change';peoPaneHtml='';render(r)}

// ---- Bio
function paneBio(s,c){const places=s.places||[];
 return `<div class="pg"><div><label>Name</label><input id="b_name" value="${esc(c.name)}"></div><div><label>Trade</label><input id="b_trade" value="${esc(c.trade)}"></div></div>
 <div class="pg3"><div><label>Home</label><input id="b_home" value="${esc(c.home)}" list="b_places"><datalist id="b_places">${places.map(p=>`<option>${esc(p)}</option>`).join('')}</datalist></div>
  <div><label>Where they are now</label><select id="b_loc">${places.map(p=>`<option ${p===c.location?'selected':''}>${esc(p)}</option>`).join('')}</select></div>
  <div><label>State</label><select id="b_state"><option value="alive" ${c.alive&&!c.banished?'selected':''}>alive</option><option value="banished" ${c.banished?'selected':''}>banished</option><option value="dead" ${!c.alive?'selected':''}>dead</option></select></div></div>
 <div class="pg"><div><label>Played by</label><select id="b_prov"></select></div><div><label>Model</label><select id="b_model"></select><input id="b_custom" placeholder="custom model" style="display:none;margin-top:4px"></div></div>
 <div class="pg"><div><label>Personality</label><textarea id="b_pers">${esc(c.personality)}</textarea></div><div><label>Secret, known only to them</label><textarea id="b_secret">${esc(c.secret)}</textarea></div></div>
 <div class="pg"><div><label>Fear</label><textarea id="b_fear">${esc(c.fear)}</textarea></div><div><label>What they want more than anything</label><textarea id="b_want">${esc(c.want)}</textarea></div></div>
 <div class="row"><button class="primary" id="b_save">Save</button><span class="note">A changed life or model starts them fresh on their next turn.</span></div>`}

// ---- Stats
function paneStats(s,c){const sk=Object.entries(c.skills||{});
 return `<div class="pg4"><div><label>Strength</label><input type="number" id="s_str" min="0" value="${c.str}"></div>
  <div><label>Speed</label><input type="number" id="s_spd" min="0" value="${c.spd}"></div>
  <div><label>Health</label><input type="number" id="s_hp" min="0" value="${c.hp}"></div>
  <div><label>Max health</label><input type="number" id="s_hpm" min="1" value="${c.hp_max}"></div></div>
 <div class="pg"><div><label>Gold</label><input type="number" id="s_gold" min="0" value="${c.gold}"></div>
  <div><label>Standing in the valley</label><select id="s_stand">${['unknown','respected','feared','pitied','hated','loved'].map(x=>`<option ${x===c.standing?'selected':''}>${x}</option>`).join('')}</select></div></div>
 <label class="note" style="display:block;margin:14px 0 6px">Skills, 1 to 9. Set one to 0 to take it away.</label>
 <div id="s_skills">${sk.map(([k,v])=>`<div class="skillrow"><input class="sk" value="${esc(k)}"><input class="sv" type="number" min="0" max="9" value="${v}"><span class="note">of 9</span></div>`).join('')}
  <div class="skillrow"><input class="sk" placeholder="a skill they have learned"><input class="sv" type="number" min="0" max="9" value="0"><span class="note">of 9</span></div></div>
 <div class="row" style="margin-top:12px"><button class="primary" id="s_save">Save</button></div>`}

// ---- Disposition
function paneDisp(s,c){const t=c.traits||{};
 return `<div class="note" style="margin-bottom:14px">Their nature, which they play without softening. Clicking a step takes effect at once and starts them fresh on their next turn.</div><div class="dgrid">`
  +TRAITS.map(([k,label,lo,hi,words])=>{const v=Math.max(1,Math.min(5,+t[k]||3));
   return `<div class="dial" data-k="${k}">
    <div class="dtop"><span class="dname">${label}</span><span class="dword">${esc(words[v-1])}</span></div>
    ${seg(1,5,v)}
    <div class="dends"><span>${esc(lo)}</span><span>${esc(hi)}</span></div></div>`}).join('')+`</div>`}

// ---- Ties
function paneTies(s,c){const rs=(s.relations||{})[c.name]||{};
 const rows=s.characters.filter(o=>o.name!==c.name).map(o=>({o,r:rs[o.name]||{type:'none',feeling:0,trust:0}}));
 if(tieSort==='name')rows.sort((a,b)=>a.o.name.localeCompare(b.o.name));
 else if(tieSort==='type')rows.sort((a,b)=>(a.r.type||'none').localeCompare(b.r.type||'none')||a.o.name.localeCompare(b.o.name));
 else rows.sort((a,b)=>(Math.abs(b.r.feeling)+Math.abs(b.r.trust))-(Math.abs(a.r.feeling)+Math.abs(a.r.trust))||a.o.name.localeCompare(b.o.name));
 if(!rows.length)return '<div class="empty">There is nobody else left to have an opinion about.</div>';
 return `<div class="tieHead"><span class="note">How ${esc(c.name)} feels about everyone else. Both run from -5 to 5. Click a step to set it.</span>
   <label class="note" style="margin-left:auto">Sort <select id="t_sort">${[['strongest','strongest first'],['name','by name'],['type','by kind of tie']].map(([v,l])=>`<option value="${v}" ${v===tieSort?'selected':''}>${l}</option>`).join('')}</select></label></div>`
  +rows.map(({o,r})=>`<div class="tie" data-b="${esc(o.name)}">
   <b style="color:${esc(seatColor(o.name)||'var(--text)')}">${esc(o.name)}</b>
   <div class="cell"><select class="tt">${REL.map(t=>`<option ${t===r.type?'selected':''}>${t}</option>`).join('')}</select></div>
   <div class="cell"><div class="tlab">feeling <b>${r.feeling>=0?'+':''}${r.feeling}</b></div>${seg(-5,5,r.feeling)}</div>
   <div class="cell"><div class="tlab">trust <b>${r.trust>=0?'+':''}${r.trust}</b></div>${seg(-5,5,r.trust)}</div>
   <label class="mut" title="also set the same the other way"><input type="checkbox" class="tm"> both ways</label>
   <button class="btn twhy">Why</button></div>`).join('')}

// ---- Log
function paneLog(s,c){const rx=rxName(c.name);
 const body=t=>{const i=(t||'').search(/\nPROSPERITY|\nSTANDINGS/);return i>0?t.slice(0,i):(t||'')};
 const rows=[];
 for(const e of (s.transcript||[])){
  if(e.speaker===c.name){rows.push({e,text:e.text});continue}
  if(!['world','system','fate','epilogue','convener'].includes(e.kind))continue;
  const b=body(e.text);if(!rx.test(b))continue;
  const hits=b.split(/(?<=[.!?])\s+/).filter(x=>rx.test(x));
  rows.push({e,text:hits.length?hits.join(' '):b.slice(0,240)})}
 if(!rows.length)return '<div class="empty">Nothing about them yet. Their days appear here once the year begins.</div>';
 let out='',day=null;
 for(const {e,text} of rows.slice(-250).reverse()){
  if(e.day!==day){day=e.day;out+=`<div class="logday">Day ${day}</div>`}
  out+=`<div class="logrow ${esc(e.kind)}" style="${e.speaker===c.name?'--c:'+esc(seatColor(c.name)||'#888'):''}"><div class="lm">${esc(e.speaker)} \u00b7 ${esc(e.time)}${e.place?' \u00b7 '+esc(e.place):''}</div>${rich(text)}</div>`}
 return out}

// ---- handlers for whichever tab is showing
function peoWire(s,c){const pane=$('peoPane');
 if(peoTab==='bio'){const seat=(s.seats||[]).find(x=>x.name===c.name)||{provider:Object.keys(providers)[0]||'',model:''};
  modelPick('b',seat,$('b_prov'),$('b_model'),$('b_custom'));
  $('b_save').onclick=async()=>{const st=$('b_state').value;
   const d={new_name:$('b_name').value.trim(),trade:$('b_trade').value,home:$('b_home').value,location:$('b_loc').value,
    personality:$('b_pers').value,secret:$('b_secret').value,fear:$('b_fear').value,want:$('b_want').value,
    ...pickVal($('b_prov'),$('b_model'),$('b_custom'))};
   if(st==='dead')d.hp=0;
   if(st==='banished')d.banished=true;
   if(st==='alive'){d.banished=false;d.alive=true;if(c.hp<=0)d.hp=1}
   const nn=d.new_name;peoNote='';const r=await api('/edit/character',{name:peoSel,...d});
   if(nn&&nn!==peoSel&&(r.characters||[]).some(x=>x.name===nn))peoSel=nn;
   peoNote=r.last_god||'no change';peoPaneHtml='';render(r)}}
 else if(peoTab==='stats'){
  $('s_save').onclick=async()=>{const skills={};
   pane.querySelectorAll('.skillrow').forEach(row=>{const k=row.querySelector('.sk').value.trim();if(k)skills[k]=+row.querySelector('.sv').value||0});
   await peoApply({str:+$('s_str').value,spd:+$('s_spd').value,hp:+$('s_hp').value,hp_max:+$('s_hpm').value,
    gold:+$('s_gold').value,standing:$('s_stand').value,skills})}}
 else if(peoTab==='disp'){
  pane.querySelectorAll('.dial').forEach(d=>d.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>peoApply({traits:{[d.dataset.k]:+b.dataset.i}})))}
 else if(peoTab==='ties'){
  $('t_sort').onchange=e=>{tieSort=e.target.value;peoPaneHtml='';renderPeople(S)};
  pane.querySelectorAll('.tie').forEach(row=>{const segs=row.querySelectorAll('.seg');
   const send=async()=>{peoNote='';
    const r=await api('/edit/relation',{a:peoSel,b:row.dataset.b,type:row.querySelector('.tt').value,
     feeling:+segs[0].dataset.v,trust:+segs[1].dataset.v,mutual:row.querySelector('.tm').checked});
    peoNote='Saved '+new Date().toLocaleTimeString();peoPaneHtml='';render(r)};
   segs.forEach(sg=>sg.querySelectorAll('button').forEach(b=>b.onclick=()=>{sg.dataset.v=b.dataset.i;send()}));
   row.querySelector('.tt').onchange=send;
   row.querySelector('.twhy').onclick=()=>showWhy(peoSel,row.dataset.b)})}}

document.querySelectorAll('.ptabs button').forEach(b=>b.onclick=()=>{peoTab=b.dataset.p;peoNote='';peoPaneHtml='';if(S)renderPeople(S)});
$('peoFilter').oninput=()=>{peoFilter=$('peoFilter').value;peoStripHtml='';if(S)peoRenderStrip(S)};
$('peoPick').onchange=()=>{peoSel=$('peoPick').value;peoNote='';peoPaneHtml='';if(S)renderPeople(S)};

// ---------- World
let worldReady=false;
function renderWorld(s){if(!worldReady){$('g_drama').oninput=()=>{$('g_dramaNote').textContent=$('g_drama').value+' \u00b7 '+DRAMA[+$('g_drama').value]};
  $('g_map_source').onchange=()=>mapInfo(S);$('g_save').onclick=saveWorld;
  $('g_regen').onclick=async()=>{$('g_regen').disabled=true;$('g_regen').textContent='Drawing...';await saveWorld();const r=await api('/map/regenerate',{});$('g_state').textContent=r.last_god||'';render(r);mapInfo(S)};worldReady=true}
 if(document.activeElement&&$('sheet-world').contains(document.activeElement)&&document.activeElement.tagName!=='BUTTON'){mapInfo(s);return}
 $('g_title').value=s.title||'';$('g_world').value=s.world_text||'';$('g_days').value=s.max_days;$('g_mins').value=s.max_minutes||'';
 $('g_drama').value=s.drama??6;$('g_dramaNote').textContent=$('g_drama').value+' \u00b7 '+DRAMA[+$('g_drama').value];
 modelPick('g',s.world_model,$('g_wp'),$('g_wm'),$('g_wc'));$('g_map_source').value=s.map_source||'builtin';
 modelPick('gm',s.map_model||s.world_model,$('g_mp'),$('g_mm'),$('g_mc'));mapInfo(s)}
function mapInfo(s){const info=$('g_mapInfo');if(!s||!info)return;const gen=$('g_map_source').value==='generated';const fixed=!!(s.created||(s.characters&&s.characters.length));
 $('g_mapModelRow').style.display=gen?'':'none';[$('g_map_source'),$('g_mp'),$('g_mm'),$('g_mc')].forEach(x=>x.disabled=fixed);
 const names=Object.keys(s.map||{});const st=s.map_style||{};let t;
 if(s.map_generating)t='Drawing a new map from the description. Watch the World\u2019s terminal.';
 else if(s.map_generated)t=`This game plays on ${s.map_name}: ${names.length} places, ${(st.water||{}).type||'no'} water, ${st.sky||'day'} sky. ${names.join(', ')}.`;
 else if(s.map_source==='generated')t='A map will be drawn from the description when you press Start, or now with the button.';
 else t='This game plays on the built-in valley of Terraceilia.';
 if(fixed)t+=' The map is fixed for this game now that its people exist.';info.textContent=t;
 const b=$('g_regen');b.style.display=gen?'':'none';b.disabled=!!(fixed||s.map_generating||s.status==='running');b.textContent=s.map_generating?'Drawing...':(s.map_generated?'Regenerate the map':'Draw the map now')}
function gMapModelVal(){const v=pickVal($('g_mp'),$('g_mm'),$('g_mc')),w=pickVal($('g_wp'),$('g_wm'),$('g_wc'));return (v.provider===w.provider&&v.model===w.model)?null:v}
async function saveWorld(){const r=await api('/edit/game',{title:$('g_title').value,world_text:$('g_world').value,max_days:+$('g_days').value,max_minutes:+($('g_mins').value||0),drama:+$('g_drama').value,world_model:pickVal($('g_wp'),$('g_wm'),$('g_wc')),map_source:$('g_map_source').value,map_model:gMapModelVal()});
 $('g_state').textContent='Saved '+new Date().toLocaleTimeString();render(r);mapInfo(S)}

// ---------- Situations
function renderSituations(s){const box=$('sitList');const th=(s.threads||[]);const fires=Object.entries(s.fires||{});
 const pres=Object.entries(s.map||{}).filter(([n,d])=>(d.present||[]).length);
 if(!th.length&&!fires.length&&!pres.length){box.innerHTML='<div class="empty">Nothing is unresolved. The valley is quiet, for now.</div>';return}
 let h='';
 if(fires.length)h+=`<div class="ledger"><b>Burning now</b>${fires.map(([p,d])=>`<div class="thr">${esc(p)} \u00b7 day ${d+1} of burning <button class="btn sm" data-out="${esc(p)}">Put it out</button></div>`).join('')}</div>`;
 if(pres.length)h+=`<div class="ledger"><b>Standing there</b>${pres.map(([n,d])=>`<div class="thr">${esc(n)}: ${esc((d.present||[]).join(', '))}</div>`).join('')}</div>`;
 const open=th.filter(t=>t.status==='open'),done=th.filter(t=>t.status!=='open');
 h+=`<div class="place">Open (${open.length})</div>`+(open.map(t=>`<div class="card"><span class="nm">#${t.id}</span> <span class="st">day ${t.day}${t.place?' \u00b7 '+esc(t.place):''}${(t.who||[]).length?' \u00b7 '+esc(t.who.join(', ')):''}</span><div style="margin:6px 0">${esc(t.text)}</div><div class="row"><input class="rnote" placeholder="how it ended (optional)"><button class="btn rdone" data-id="${t.id}">Resolve</button></div></div>`).join('')||'<div class="empty">Nothing open.</div>');
 h+=`<div class="place">Resolved (${done.length})</div>`+(done.map(t=>`<div class="card dead"><span class="nm">#${t.id}</span> <span class="st">day ${t.day}${t.place?' \u00b7 '+esc(t.place):''} \u00b7 ended day ${t.resolved_day??'?'}</span><div style="margin:6px 0">${esc(t.text)}</div>${t.note?`<div class="note">${esc(t.note)}</div>`:''}</div>`).join('')||'<div class="empty">Nothing resolved yet.</div>');
 box.innerHTML=h;
 box.querySelectorAll('.rdone').forEach(b=>b.onclick=async()=>{b.disabled=true;const note=b.closest('.row').querySelector('.rnote').value;render(await api('/god/resolve',{id:+b.dataset.id,note}))});
 box.querySelectorAll('[data-out]').forEach(b=>b.onclick=async()=>{b.disabled=true;render(await api('/god/extinguish',{place:b.dataset.out}))})}

// ---------- Fate
function renderFate(s){const alive=(s.characters||[]).filter(c=>c.alive&&!c.banished).map(c=>c.name);
 const places=s.places||[];const put=(id,arr,keep)=>{const el=$(id);const v=keep&&arr.includes(el.value)?el.value:arr[0];el.innerHTML=arr.map(x=>`<option ${x===v?'selected':''}>${esc(x)}</option>`).join('');el.value=v};
 put('f_whisper_who',alive,true);put('f_move_who',alive,true);put('f_smite_who',alive,true);
 put('f_move_place',places,true);put('f_fire_place',places,true);put('f_dest_place',places,true);
 const d=(s.map||{})[$('f_dest_place').value]||{fixtures:[]};put('f_dest_fx',d.fixtures||[],true);
 const gone=new Set(d.destroyed||[]);$('f_dest').textContent=gone.has($('f_dest_fx').value)?'Restore it':'Destroy it';
 if(!renderFate.wired){renderFate.wired=true;
  const say=t=>{$('f_state').textContent=t||'';};
  $('f_dest_place').onchange=()=>renderFate(S);$('f_dest_fx').onchange=()=>renderFate(S);
  $('f_whisper').onclick=async()=>{const who=$('f_whisper_who').value,t=$('f_whisper_text').value.trim();if(!t)return;$('f_whisper_text').value='';render(await api('/say',{text:'@'+who+' '+t}));say('Said to '+who+' alone.')};
  $('f_move').onclick=async()=>{const r=await api('/god/move',{name:$('f_move_who').value,place:$('f_move_place').value});say(r.last_god);render(r)};
  $('f_fire').onclick=async()=>{const r=await api('/god/fire',{place:$('f_fire_place').value});say(r.last_god);render(r)};
  $('f_out').onclick=async()=>{const r=await api('/god/extinguish',{place:$('f_fire_place').value});say(r.last_god);render(r)};
  $('f_dest').onclick=async()=>{const r=await api('/god/destroy',{place:$('f_dest_place').value,fixture:$('f_dest_fx').value});say(r.last_god);render(r)};
  $('f_smite').onclick=async()=>{const n=$('f_smite_who').value;if(!confirm('Strike '+n+' down? They die at once.'))return;const r=await api('/god/smite',{name:n});say(r.last_god);render(r)}}}

// ---------- Connections
const CONN_LABEL={connected:'Connected',not_installed:'Not installed',not_signed_in:'Not signed in',checking:'Checking',error:'Error'};
function renderConn(s){const root=$('connList');const c=s.connections||{};const used=new Set((s.seats||[]).map(x=>x.provider).concat([(s.world_model||{}).provider,(s.model_a||{}).provider,(s.model_b||{}).provider]));
 const keep={};root.querySelectorAll('.keyin').forEach(i=>keep[i.dataset.p]=i.value);
 root.innerHTML=Object.entries(c).map(([k,p])=>{const st=p.state==='connected'?'ok':p.state==='checking'?'unk':'bad';
  const job=p.job;const showKey=p.key_env&&p.state!=='connected';
  return `<div class="conn" data-p="${esc(k)}">
   <div class="hd"><span><b>${esc(k)}</b>${used.has(k)?' <span class="note">\u00b7 this game uses it</span>':''}${p.version?` <span class="note">\u00b7 ${esc(p.version)}</span>`:''}</span>
    <span class="st ${st}">${esc(CONN_LABEL[p.state]||p.state)}</span></div>
   <div class="note" style="margin-top:4px">${esc(p.detail||'')}</div>
   <div class="row" style="margin-top:8px">
    ${p.state==='not_installed'&&p.can_install?`<button class="btn act" data-do="install">Install</button>`:''}
    ${p.state==='not_signed_in'&&p.can_login?`<button class="btn act" data-do="login">Sign in</button>`:''}
    ${p.state==='not_installed'&&!p.can_install?`<span class="note">Nothing to install: it is fetched fresh on every run.</span>`:''}
    ${showKey?`<input class="keyin" type="password" data-p="${esc(k)}" placeholder="${esc(p.key_env)} (this session only)" autocomplete="off"><button class="btn act" data-do="key">Use key</button>`:''}
    ${p.state==='connected'?`<span class="note">Nothing to do.</span>`:''}
    ${p.docs?`<a class="note" href="${esc(p.docs)}" target="_blank" rel="noopener" style="margin-left:auto">docs</a>`:''}
   </div>
   ${p.node_missing?`<div class="note" style="margin-top:6px">Node.js is needed first. <a href="https://nodejs.org" target="_blank" rel="noopener">Get Node.js</a>, then press Install.</div>`:''}
   ${job?`<div class="res">${job.note?esc(job.note)+'\n':''}${esc((job.lines||[]).join('\n'))}${!job.done&&job.kind==='login'?'\nWaiting for the sign in to finish... '+Math.round((job.waited||0))+'s':''}</div>
     ${job.done?`<div class="row"><button class="btn sm act" data-do="dismiss">Hide this</button></div>`:''}`:''}
  </div>`}).join('');
 root.querySelectorAll('.keyin').forEach(i=>{if(keep[i.dataset.p])i.value=keep[i.dataset.p]});
 root.querySelectorAll('.act').forEach(b=>b.onclick=async()=>{const box=b.closest('.conn'),k=box.dataset.p,d=b.dataset.do;
  b.disabled=true;
  if(d==='key'){const inp=box.querySelector('.keyin');const r=await api('/connect/key',{provider:k,key:inp.value});inp.value='';render(r)}
  else if(d==='install')render(await api('/connect/install',{provider:k}));
  else if(d==='login')render(await api('/connect/login',{provider:k}));
  else if(d==='dismiss')render(await api('/connect/dismiss',{provider:k}))})}

// ---------- Telegram: the row, and the three step wizard behind it
function renderTg(s){const t=s.telegram||{};const root=$('tgRow');
 root.innerHTML=`<div class="conn"><div class="hd"><span><b>Telegram</b>${t.bot?` <span class="note">\u00b7 @${esc(t.bot)}</span>`:''}</span><span class="st ${t.ready?'ok':'unk'}">${t.ready?'Connected':'Not connected'}</span></div>
  <div class="note" style="margin-top:4px">${t.ready?`Messages go to chat ${esc(t.chat)}. ${t.notify_on_finish?'You are told when a year ends.':'End of year messages are off.'}`:'Terraceilia can message you when a year ends. Three steps, about three minutes.'}</div>
  <div class="row" style="margin-top:8px">${t.ready?`<button class="btn" id="tgSend">Send me the phone link</button><button class="btn" id="tgAgain">Change</button><button class="danger" id="tgOff">Disconnect</button>`:`<button class="btn" id="tgConnect">Connect Telegram</button>`}<span class="note" id="tgRowState">${esc(s.last_tg||'')}</span></div></div>`;
 const open=()=>{tgReset(s);sheet('tgwiz')};
 if($('tgConnect'))$('tgConnect').onclick=open;          // never connected, or the link was removed: the tutorial opens
 if($('tgAgain'))$('tgAgain').onclick=open;
 if($('tgSend'))$('tgSend').onclick=async()=>{const r=await api('/telegram/send',{text:(S.phone_url||'')+(S.away_url?'\n'+S.away_url:'')||'Terraceilia says hello.'});$('tgRowState').textContent=r.last_tg||'';render(r)};
 if($('tgOff'))$('tgOff').onclick=async()=>{if(!confirm('Disconnect Telegram? Terraceilia forgets the bot token and the chat. The bot itself stays in Telegram; delete it with BotFather if you want.'))return;render(await api('/telegram/clear',{}))}}
function tgReset(s){const t=s.telegram||{};tgBot=t.bot||'';$('tgTok').value='';$('tgChat').value=t.chat||'';$('tgS1').textContent='';$('tgS2').textContent='';$('tgS3').textContent='';$('tgPick').innerHTML='';
 $('tgNotifyFinish').checked=t.notify_on_finish!==false;$('tgNotifyDeath').checked=!!t.notify_on_death;
 $('tgBotLink').textContent=tgBot?'@'+tgBot:'its link appears here after step 1';$('tgBotLink').href=tgBot?'https://t.me/'+tgBot:'#'}
$('tgCheck').onclick=async()=>{$('tgS1').textContent='Asking Telegram...';const r=await api('/telegram/check',{token:$('tgTok').value});
 if(!r.ok){$('tgS1').textContent=r.error;return}tgBot=r.bot||'';$('tgS1').textContent='That is your bot: '+(r.name||'')+' @'+tgBot+'. Now do step 2.';
 $('tgBotLink').textContent='@'+tgBot;$('tgBotLink').href='https://t.me/'+tgBot};
$('tgFind').onclick=async()=>{$('tgS2').textContent='Looking...';$('tgPick').innerHTML='';const r=await api('/telegram/find',{token:$('tgTok').value});
 if(!r.ok){$('tgS2').textContent=r.error;return}
 $('tgS2').textContent=r.chats.length===1?'Found you.':'Found '+r.chats.length+' chats. Pick yours.';
 $('tgPick').innerHTML=r.chats.map(c=>`<button class="btn sm" data-id="${esc(c.id)}" style="margin:4px 4px 0 0">${esc(c.name)} <span class="note">${esc(c.kind)}</span></button>`).join('');
 $('tgPick').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('tgChat').value=b.dataset.id;$('tgS2').textContent='Using '+b.textContent.trim()+'. Now do step 3.'});
 if(r.chats.length===1)$('tgChat').value=r.chats[0].id};
$('tgTest').onclick=async()=>{$('tgS3').textContent='Sending...';const r=await api('/telegram/test',{token:$('tgTok').value,chat_id:$('tgChat').value});$('tgS3').textContent=r.ok?'Sent. Look at Telegram, then press Save and finish.':r.error};
$('tgSave').onclick=async()=>{const r=await api('/telegram/save',{token:$('tgTok').value,chat_id:$('tgChat').value,notify_finish:$('tgNotifyFinish').checked,notify_death:$('tgNotifyDeath').checked,bot:tgBot});
 if(!r.ok){$('tgS3').textContent=r.error;return}sheet('connections');render(await api('/state?since=1000000000'))};

// ---------- Display
const DISP={font:14,rail:260,side:400,showSide:true,showRail:true};
function dispLoad(){try{return Object.assign({},DISP,JSON.parse(localStorage.getItem('terra.display')||'{}'))}catch(e){return {...DISP}}}
function dispApply(d){const r=document.documentElement;r.style.setProperty('--fs',d.font+'px');r.style.setProperty('--rail',d.showRail?d.rail+'px':'0px');r.style.setProperty('--side',d.showSide?d.side+'px':'0px');
 document.body.classList.toggle('norail',!d.showRail);document.body.classList.toggle('noside',!d.showSide);
 if($('d_fontNote')){$('d_fontNote').textContent=d.font+'px';$('d_railNote').textContent=d.rail+'px';$('d_sideNote').textContent=d.side+'px';
  $('d_font').value=d.font;$('d_rail').value=d.rail;$('d_side').value=d.side;$('d_showSide').checked=d.showSide;$('d_showRail').checked=d.showRail}}
function dispSave(d){localStorage.setItem('terra.display',JSON.stringify(d));dispApply(d)}
let disp=dispLoad();dispApply(disp);
['d_font','d_rail','d_side'].forEach(id=>$(id).oninput=()=>{disp[id.slice(2)]=+$(id).value;dispSave(disp)});
$('d_showSide').onchange=()=>{disp.showSide=$('d_showSide').checked;dispSave(disp)};
$('d_showRail').onchange=()=>{disp.showRail=$('d_showRail').checked;dispSave(disp)};
$('d_reset').onclick=()=>{disp={...DISP};dispSave(disp)};

// ---------- More (phone)
function renderMore(s){const started=s.created||s.transcript.length>0||s.status==='running'||s.status==='paused';
 $('moreList').innerHTML=(started?'':`<button class="btn" style="width:100%;margin-bottom:8px" data-m="setup">Set this game up</button>`)+
 [['world','World'],['situations','Situations'],['fate','Fate'],['connections','Connections'],['display','Display']]
 .map(([k,l])=>`<button class="btn" style="width:100%;margin-bottom:8px;justify-content:flex-start" data-m="${k}">${l}</button>`).join('')
 +`<button class="btn" style="width:100%;margin-bottom:8px" data-m="x-chronicle">Export the chronicle</button>`
 +`<button class="danger" style="width:100%;margin-bottom:8px" data-m="stop">Stop this year</button>`
 +`<button class="danger" style="width:100%" data-m="quit">Quit Terraceilia</button>`;
 $('moreList').querySelectorAll('[data-m]').forEach(b=>b.onclick=async()=>{const m=b.dataset.m;
  if(m==='setup'){sheet('');showTab('setup');return}
  if(m==='x-chronicle'){window.location='/export?what=chronicle';return}
  if(m==='stop'){if(confirm('Stop this year here?'))render(await api('/stop',{}));return}
  if(m==='quit'){if(confirm('Quit Terraceilia?')){try{await api('/shutdown',{})}catch(e){}document.body.innerHTML='<div style="padding:40px;color:#8B8B94">Terraceilia is closed.</div>'}return}
  sheet(m);if(m==='connections')api('/connect/refresh',{})})}

// ---------- tabs
function showTab(t){['map','chron','side'].forEach(id=>$(id).classList.toggle('on',id===t));
 document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));
 if(mobile()){$('centerTabs').style.display='none';$('composer').style.display=t==='chron'?'':'none';$('chron').style.display=t==='chron'?'block':'none';
  $('map').style.display=t==='map'?'block':'none';$('setup').style.display=t==='setup'?'block':'none'}}
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{const t=b.dataset.t;
 if(t==='people'){sheet('people');document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));return}
 if(t==='more'){sheet('more');document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));return}
 sheet('');showTab(t)});
if(mobile())showTab('map');
document.querySelectorAll('#centerTabs button').forEach(b=>b.onclick=()=>{centerTab=b.dataset.c;document.querySelectorAll('#centerTabs button').forEach(x=>x.classList.toggle('on',x===b));if(S)render(S)});
document.querySelectorAll('#side .tabs button').forEach(b=>b.onclick=async()=>{sideTab=b.dataset.t;if(sideTab==='terms'){try{render(await api('/state?since='+lastTurn+'&terms=1'))}catch(e){}}document.querySelectorAll('#side .tabs button').forEach(x=>x.classList.toggle('on',x===b));$('valley').classList.toggle('on',sideTab==='valley');$('terms').classList.toggle('on',sideTab==='terms')});
$('railBtn').onclick=()=>{disp.showRail=!disp.showRail;dispSave(disp)};
$('ppClose').onclick=e=>{e.stopPropagation();MapView.close()};

// ---------- setup, start, stop
async function save(){return render(await api('/config',{title:$('title').value,world_text:$('world_text').value,players:+$('players').value,max_days:+$('max_days').value,max_minutes:+($('max_minutes').value||0),repo:$('repo').value,
 drama:+$('drama').value,world_model:modelVal('wm'),model_a:modelVal('ma'),model_b:modelVal('mb'),map_source:$('map_source').value,map_model:mapModelVal()}))}
function mapModelVal(){const v=modelVal('mm'),w=modelVal('wm');return (v.provider===w.provider&&v.model===w.model)?null:v}
$('map_source').onchange=()=>{$('mapModelRow').style.display=$('map_source').value==='generated'?'':'none';save()};
$('drama').oninput=()=>{$('dramaNote').textContent=$('drama').value+' \u00b7 '+DRAMA[+$('drama').value]};$('drama').onchange=save;
['title','world_text','players','max_days','max_minutes','repo'].forEach(id=>{const el=$(id);el.onfocus=()=>editing=true;el.onblur=()=>{editing=false;save()}});
['wm','ma','mb','mm'].forEach(p=>{$(p+'_p').onchange=()=>{const ms=(providers[$(p+'_p').value]||{models:['']}).models.concat(['Custom...']);fillSel($(p+'_m'),ms,ms[0]);$(p+'_c').style.display='none';save()};$(p+'_m').onchange=()=>{const cu=$(p+'_m').value==='Custom...';$(p+'_c').style.display=cu?'':'none';if(cu){editing=true;$(p+'_c').focus()}else save()};$(p+'_c').onfocus=()=>editing=true;$(p+'_c').onblur=()=>{editing=false;save()}});
$('primary').onclick=async()=>{const s=S||{};
 if(s.status==='running'){render(await api('/pause',{}));return}
 if(!(s.created))await save();
 render(await api('/start',{}));if(mobile())showTab('map')};
$('start2').onclick=()=>$('primary').click();
$('startErrLink').onclick=e=>{e.preventDefault();sheet('connections');api('/connect/refresh',{})};
$('newGame').onclick=async()=>{S=null;termKey='';sheet('');render(await api('/game/new',{}));if(mobile())showTab('map')};
$('sayBtn').onclick=async()=>{const t=$('sayText').value.trim();if(!t)return;$('sayText').value='';hlSync();render(await api('/say',{text:t}))};

// ---------- @ mentions in the composer
let acItems=[],acIdx=0,acStart=-1;
function people(){return (S&&S.characters||[]).filter(c=>c.alive&&!c.banished)}
function acClose(){$('ac').classList.remove('open');acItems=[]}
function acRender(){$('ac').innerHTML=acItems.map((x,i)=>`<div class="${i===acIdx?'on':''}" data-i="${i}"><span class="dot" style="background:${esc(seatColor(x.name))}"></span><span>${esc(x.name)}</span><small>${esc(x.trade)} \u00b7 ${esc(x.location)}</small></div>`).join('');
 document.querySelectorAll('#ac div').forEach(d=>{d.onmousedown=e=>{e.preventDefault();acPick(+d.dataset.i)}});$('ac').classList.toggle('open',acItems.length>0)}
function acPick(i){const x=acItems[i];if(!x)return;const t=$('sayText');const v=t.value;const before=v.slice(0,acStart);const after=v.slice(t.selectionStart);t.value=before+'@'+x.name+' '+after;const pos=(before+'@'+x.name+' ').length;t.setSelectionRange(pos,pos);acClose();t.focus();hlSync()}
function acUpdate(){const t=$('sayText');const v=t.value.slice(0,t.selectionStart);const m=v.match(/(?:^|\s)@([\w-]*)$/);if(!m||!S){acClose();return}
 acStart=v.length-m[0].length+(m[0].startsWith('@')?0:1);const q=m[1].toLowerCase();acItems=people().filter(x=>x.name.toLowerCase().startsWith(q));acIdx=0;acRender()}
function hlSync(){const t=$('sayText');let h=esc(t.value);h=h.replace(/@([A-Za-z][\w-]*)/g,(m,n)=>{const c=people().find(x=>x.name.toLowerCase()===n.toLowerCase());return c?`<span class="men" style="--mc:${esc(seatColor(c.name))}">@${n}</span>`:`@${n}`});$('hl').innerHTML=h+(t.value.endsWith('\n')?'<br>':'');$('hl').scrollTop=t.scrollTop;
 t.placeholder=/@[A-Za-z]/.test(t.value)?'':'Speak as fate to everyone, or @Name to speak to one person alone.'}
$('sayText').oninput=()=>{acUpdate();hlSync()};$('sayText').onclick=acUpdate;$('sayText').onscroll=()=>{$('hl').scrollTop=$('sayText').scrollTop};$('sayText').onblur=()=>setTimeout(acClose,150);
$('sayText').onkeydown=e=>{const open=$('ac').classList.contains('open');
 if(open&&(e.key==='ArrowDown'||e.key==='ArrowUp')){e.preventDefault();acIdx=(acIdx+(e.key==='ArrowDown'?1:acItems.length-1))%acItems.length;acRender();return}
 if(open&&(e.key==='Enter'||e.key==='Tab')){e.preventDefault();acPick(acIdx);return}
 if(open&&e.key==='Escape'){acClose();return}
 if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('sayBtn').click()}};

// ---------- folder picker
let pk={path:''};async function openPk(p){const d=await api('/ls?path='+encodeURIComponent(p||$('repo').value));pk=d;$('pkPath').value=d.path;const sep=d.path.includes('\\')?'\\':'/';const base=d.path.replace(/[\\/]$/,'');
 $('pkList').innerHTML=d.drives.map(x=>`<li data-p="${esc(x)}">${esc(x)}</li>`).join('')+d.dirs.map(x=>`<li data-p="${esc(base+sep+x)}">${esc(x)}</li>`).join('');document.querySelectorAll('#pkList li').forEach(li=>li.onclick=()=>openPk(li.dataset.p));$('picker').style.display='flex'}
$('browse').onclick=()=>openPk();$('pkUp').onclick=()=>pk.parent&&openPk(pk.parent);$('pkPath').onchange=e=>openPk(e.target.value);$('pkCancel').onclick=()=>$('picker').style.display='none';$('pkUse').onclick=async()=>{$('repo').value=pk.path;$('picker').style.display='none';await save()};

// ---------- why does one person feel that way about another
function showWhy(a,b){const r=((S.relations||{})[a]||{})[b];if(!r)return;const why=(r.why||[]).slice().reverse();
 const TRUST=['would knife in the dark','distrusts utterly','distrusts','is wary of','is unsure of','neither trusts nor distrusts','trusts a little','trusts','trusts well','trusts with secrets','trusts with their life'];
 let box=$('whyBox');if(!box){box=document.createElement('div');box.id='whyBox';document.body.appendChild(box);box.onclick=e=>{if(e.target===box)box.style.display='none'}}
 box.innerHTML=`<div class="whyPanel"><h3>${esc(a)} \u2192 ${esc(b)} <button class="icon" id="whyClose">&#10005;</button></h3>
  <div class="note" style="margin-bottom:8px">${esc(a)} ${FEEL[r.feeling+5]} ${esc(b)} (${r.feeling>=0?'+':''}${r.feeling}) and ${TRUST[r.trust+5]} them (${r.trust>=0?'+':''}${r.trust})${r.type!=='none'?' \u00b7 '+esc(r.type):''}</div>
  ${why.length?why.map(w=>`<div class="whyRow"><span class="note">day ${w.day}</span><span>${esc(w.note)}</span><span class="note">${w.feeling>=0?'+':''}${w.feeling} / ${w.trust>=0?'+':''}${w.trust}</span></div>`).join(''):'<div class="note">No history recorded yet.</div>'}
  <div class="row" style="margin-top:10px"><button class="btn" id="whyRev">See it the other way</button></div></div>`;
 box.style.display='flex';$('whyClose').onclick=()=>box.style.display='none';$('whyRev').onclick=()=>showWhy(b,a)}

function wantTerms(){return (sideTab==='terms'&&disp.showSide)||(mobile()&&$('side').classList.contains('on')&&sideTab==='terms')}
(async function poll(){try{render(await api('/state?since='+(S?lastTurn:-1)+'&terms='+(wantTerms()?1:0)))}catch(e){}setTimeout(poll,1500)})();
window.App={render,api};
