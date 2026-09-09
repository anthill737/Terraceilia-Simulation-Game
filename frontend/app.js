// Terraceilia: the shell around the map. Gameplay sits in plain buttons; everything else lives behind the gear.
let S=null,editing=false,providers={},termKey='',sideTab='valley',centerTab='',openSheet='',tgBot='';
let T=[],lastTurn=-1,Tid=null,draftWas='';
function mergeTranscript(s){if(s.id!==Tid||s.transcript_total<T.length||(s.transcript&&s.transcript.length&&T.length&&s.transcript[0].turn<=lastTurn&&s.transcript_total!==T.length)){T=s.transcript?s.transcript.slice():[];Tid=s.id}else if(s.transcript)for(const e of s.transcript)if(e.turn>lastTurn)T.push(e);lastTurn=T.length?T[T.length-1].turn:-1;s.transcript=T}
const $=id=>document.getElementById(id);
async function api(p,b){const r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):null});return r.json()}
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const STATUS={idle:'Not started',running:'Running',paused:'Paused',done:'The year is over',stopped:'Stopped',draft:'Draft'};
const hhmm=t=>{const d=new Date((t||0)*1000);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')};
const mobile=()=>window.matchMedia('(max-width:820px),(max-height:520px)').matches;
// the poll redraws every sheet; never redraw the one someone is typing into
const typing=root=>!!root&&root.contains(document.activeElement)&&/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||'');
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
const FIRST='First model that answers';
function modelUI(pfx,val){const p=$(pfx+'_p'),m=$(pfx+'_m'),c=$(pfx+'_c');fillSel(p,Object.keys(providers),val.provider);const ms=[FIRST].concat((providers[val.provider]||{models:[]}).models,['Custom...']);const v=val.model||FIRST;const known=ms.includes(v);fillSel(m,ms,known?v:'Custom...');c.style.display=known?'none':'';if(!known)c.value=val.model}
function modelVal(pfx){const m=$(pfx+'_m').value;return {provider:$(pfx+'_p').value,model:m==='Custom...'?($(pfx+'_c').value.trim()||''):m===FIRST?'':m}}
const DRAMA=['nothing','a whisper','quiet','calm','ordinary','lively','eventful','hard','harsh','brutal','chaos'];
const STORES=['grain','meat','fish','wood','meals','tools','herbs'];
const NEEDW={food:['starving','hungry','fed'],warmth:['freezing','cold','warm'],rest:['exhausted','tired','rested'],spirit:['broken','low','in good spirits']};
const needWord=(k,v)=>NEEDW[k][v<=0?0:v<=4?1:2];

// ---------- setup screen (a game that has not started)
function renderSetup(s){$('title').value=s.title;$('world_text').value=s.world_text;$('players').value=s.players;$('max_days').value=s.max_days;$('max_minutes').value=s.max_minutes||'';$('repo').value=s.repo;$('drama').value=s.drama??6;$('dramaNote').textContent=($('drama').value)+' \u00b7 '+DRAMA[+$('drama').value];
 modelUI('wm',s.world_model);modelUI('ma',s.model_a);modelUI('mb',s.model_b);modelUI('mm',s.map_model||s.world_model);
 $('map_source').value=s.map_source||'builtin';$('mapModelRow').style.display=$('map_source').value==='generated'?'':'none'}

// ---------- the valley panel
const FEEL=['hates','despises','dislikes','is cold toward','is cool toward','is indifferent to','is warm toward','likes','is fond of','cares deeply for','loves'];
function relChips(s,name){const rs=(s.relations||{})[name]||{};const items=Object.entries(rs).filter(([b,r])=>r.type!=='none'||r.feeling||r.trust).sort((x,y)=>(Math.abs(y[1].feeling)+Math.abs(y[1].trust))-(Math.abs(x[1].feeling)+Math.abs(x[1].trust)));
 if(!items.length)return '';const chip=([b,r])=>{const hue=r.feeling>0?'var(--moss)':r.feeling<0?'var(--rust)':'var(--faint)';return `<span class="rel" data-a="${esc(name)}" data-b="${esc(b)}" title="${esc(name)} ${FEEL[r.feeling+5]} ${esc(b)}. Click for why." style="--h:${hue}"><span>${esc(b)}</span> ${r.type!=='none'?esc(r.type)+' \u00b7 ':''}<i>${r.feeling>=0?'+':''}${r.feeling}</i><i class="t">${r.trust>=0?'+':''}${r.trust}</i></span>`};return '<div class="rels">'+items.slice(0,6).map(chip).join('')+(items.length>6?`<details class="more" data-k="r:${esc(name)}"><summary>${items.length-6} more</summary>${items.slice(6).map(chip).join('')}</details>`:'')+'</div>'}
function renderValley(s){if(!s.created){$('valley').innerHTML='<div class="empty">The valley appears here once the World has rolled it.</div>';return}
 const wasOpen=new Set([...$('valley').querySelectorAll('details[open]')].map(d=>d.dataset.k));const scroll=$('valley').scrollTop;
 const L=s.ledger||{};const R=s.day_report||{};const ch=R.change||{};
 const store=k=>`<span class="stk ${(L[k]||0)<=(k==='tools'||k==='herbs'?2:4)?'low':''}">${k} <span>${L[k]??0}</span>${ch[k]?`<i>${ch[k]>0?'+':''}${ch[k]}</i>`:''}</span>`;
 const sick=(s.characters||[]).filter(c=>c.alive&&!c.gone&&c.sick).length;
 let h=`<div class="ledger"><span>Day ${s.day}</span> &middot; ${esc(R.season||'')} &middot; ${esc(s.weather||'')}<div class="stores">${STORES.map(store).join('')}</div>road ${L.road_safe?'safe':'unsafe'} after dark &middot; ${sick} sick &middot; ${Object.keys(s.bodies||{}).length} unburied<br>Built: ${esc((L.built||[]).join(', ')||'nothing yet')}${s.pending.length?`<br><span class="note">${s.pending.length} action(s) waiting for the World</span>`:''}</div>`;
 const byPlace={};s.characters.forEach(c=>{(byPlace[c.alive&&!c.gone?c.location:'Gone']=byPlace[c.alive&&!c.gone?c.location:'Gone']||[]).push(c)});
 const th=(s.threads||[]).filter(t=>t.status==='open');if(th.length)h+=`<div class="ledger"><span>Open situations</span> (${th.length})${th.map(t=>`<div class="thr">#${t.id} \u00b7 day ${t.day}${t.place?' \u00b7 '+esc(t.place):''}: ${esc(t.text)}</div>`).join('')}</div>`;
 h+=Object.entries(byPlace).map(([pl,cs])=>`<div class="place">${esc(pl)}</div>`+cs.map(c=>`<div class="card ${c.alive?'':'dead'}" style="--c:${esc(seatColor(c.name)||'var(--faint)')}"><span class="nm">${esc(c.name)}</span> <span class="st">${esc(c.trade)} &middot; ${esc(c.location)} &middot; ${esc(c.standing)}${c.gone?' &middot; gone':''}${c.alive?'':' &middot; dead: '+esc(c.cause_of_death)}</span>
  <div class="bar"><i style="width:${Math.round(100*c.hp/c.hp_max)}%"></i></div>HP ${c.hp}/${c.hp_max} &middot; STR ${c.str} SPD ${c.spd} &middot; gold ${c.gold} &middot; ${Object.keys(c.skills).length?Object.entries(c.skills).map(([k,v])=>k+' '+v).join(', '):'no skills'}
  ${relChips(s,c.name)}
  <details data-k="p:${esc(c.name)}"><summary>${esc(c.personality)}</summary>${c.traits?'Personality: '+Object.entries(c.traits).map(([k,v])=>k+' '+v).join(', ')+'<br>':''}Secret: ${esc(c.secret)}<br>Fear: ${esc(c.fear)}<br>Want: ${esc(c.want)}</details></div>`).join('')).join('');
 const html=h;if($('valley').dataset.html!==html){$('valley').innerHTML=html;$('valley').dataset.html=html;$('valley').querySelectorAll('details').forEach(d=>{if(wasOpen.has(d.dataset.k))d.open=true});$('valley').scrollTop=scroll;$('valley').querySelectorAll('.rel').forEach(ch=>ch.onclick=e=>{e.stopPropagation();showWhy(ch.dataset.a,ch.dataset.b)})}}
function renderTerms(s){if(!s.terms.length){$('terms').innerHTML='<div class="empty">Terminals appear after Start.</div>';termKey='';return}if(!wantTerms())return;
 const key=s.id+':'+s.terms.length;if(termKey!==key){termKey=key;$('terms').innerHTML=s.terms.map((t,i)=>`<div class="term" id="t${i}"><div class="tb"><span class="nm"></span><span class="st"></span></div><pre></pre></div>`).join('')}
 s.terms.forEach((t,i)=>{const el=$('t'+i);if(!el)return;const seat=s.seats[i]||{};el.style.setProperty('--c',seat.color||'var(--faint)');el.classList.toggle('speaking',t.state==='speaking');
  el.querySelector('.nm').innerHTML=`<b>${esc(seat.name)}</b> <span style="color:var(--faint)">${esc((seat.provider||'')+' \u00b7 '+(seat.model||''))}</span>`;el.querySelector('.st').textContent=t.state==='speaking'?'thinking':'';
  const pre=el.querySelector('pre');const atB=pre.scrollHeight-pre.scrollTop-pre.clientHeight<40;if(pre.dataset.count!=t.count&&t.lines.length){pre.textContent=t.lines.join('\n');pre.dataset.count=t.count;if(atB)pre.scrollTop=pre.scrollHeight}else if(!pre.textContent)pre.textContent='No live output yet.'})}
function renderRail(s){const live=new Set(s.live||[]);$('railCount').textContent=s.games.length;
 $('hlist').innerHTML=s.games.map(g=>`<div class="hitem ${g.id===s.id?'on':''}" data-id="${g.id}"><div class="t"><span>${live.has(g.id)?'<span class="livedot"></span>':''}${esc(g.title)}</span><button class="del" data-id="${g.id}" title="Delete">&times;</button></div><div class="m">${esc(g.created.replace('T',' '))} \u00b7 day ${g.day} \u00b7 ${esc(STATUS[g.status]||g.status)}</div></div>`).join('');
 document.querySelectorAll('.hitem').forEach(d=>d.onclick=async e=>{if(e.target.classList.contains('del')){if(confirm('Delete this game?'))render(await api('/game/delete',{id:e.target.dataset.id}));return}S=null;termKey='';render(await api('/game/open',{id:d.dataset.id}));if(mobile())showTab('map')})}

// ---------- the one render
function render(s){const first=!S||S.id!==s.id;if(first){T=[];lastTurn=-1}mergeTranscript(s);S=s;providers=s.providers;
 const busy=s.status==='running';const started=s.created||s.transcript.length>0||busy||s.status==='paused';
 $('hdrTitle').textContent=s.title||'';const who=s.current?s.current.split(', '):[];
 const tst=(s.testing&&s.testing.total)?s.testing:null;
 // a test at Start is never silent: the pill counts the seats, the banner names each one as it answers
 $('startTest').classList.toggle('on',!!tst);
 if(tst)$('startTest').innerHTML=`<span class="spin sm"></span><b>Testing seats: ${tst.done} of ${tst.total}</b>${tst.now?' \u00b7 testing '+esc(tst.now):''}${tst.names.length?`<div class="note">answered: ${esc(tst.names.join(', '))}</div>`:''}`;
 $('statusText').innerHTML=tst?`Testing seats: ${tst.done} of ${tst.total}`:s.current?(who.length>2?`<b>${who.length} people</b> are speaking`:`<b>${esc(s.current)}</b> ${who.length>1?'are':'is'} speaking`):`Day ${s.day}${s.status==='running'&&s.phase?' \u00b7 '+s.phase:''} \u00b7 ${STATUS[s.status]||s.status}`;
 $('status').classList.toggle('live',busy);
 const drafting=!!s.draft&&!started;const drafted=drafting&&(s.characters||[]).length>0;const gen=s.generating||'';
 const prim=$('primary');prim.textContent=busy?'Pause':s.status==='paused'?'Resume':started?(s.status==='done'?'Continue (6 more days)':'Continue'):(drafting&&!drafted)?'Generate':'Start';
 prim.className=busy?'btn':'primary';prim.disabled=!!(drafting&&(gen||(drafted&&!s.draft_ready)));
 $('start2').style.display=started?'none':'';$('sayBtn').disabled=!busy;
 $('start2').disabled=!!(drafting&&(gen||!s.draft_ready));$('start2').style.opacity=$('start2').disabled?'.45':'';
 $('draftBar').style.display=drafting?'':'none';
 if(drafting){$('generate').textContent=gen?(gen==='all'?'Rolling the valley...':gen==='map'?'Drawing the map...':gen==='people'?'Rerolling everyone...':gen.startsWith('reroll')?'Rerolling '+esc(gen.slice(7))+'...':gen.startsWith('add')?'Adding '+esc(gen.slice(4))+'...':'Working...'):(drafted?'Generate again':'Generate');
  $('generate').disabled=!!gen;['rerollAll','regenMap','openPeople','testSeats'].forEach(id=>{$(id).disabled=!!gen||!drafted;$(id).style.display=drafted?'':'none'});$('regenMap').style.display=(drafted&&s.map_source==='generated')?'':'none';
  $('testSeats').textContent=tst?`Testing ${tst.done} of ${tst.total}...`:s.draft_ready?'Seats tested':'Test seats';
  $('draftNote').textContent=s.draft_note||(drafted?(s.draft_ready?`${s.characters.length} people, every seat tested. Start when you are ready.`:`${s.characters.length} people. Test the seats before Start.`):'')}
 if(drafted&&!gen&&draftWas===gen+'x'){sheet('people')}draftWas=gen?gen+'x':'';
 const err=(s.blocked||s.start_error||'');$('startErr').classList.toggle('on',!!err);$('startErrText').textContent=err;
 if(first||!editing)renderSetup(s);renderRail(s);
 // a map that has been drawn can be looked at before the year starts, so Setup is a tab of its own until then
 const canMap=started||s.map_generated||drafted;
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
 $('making').style.display=((busy&&!s.created)||gen==='all'||gen==='map'||gen==='people')?'flex':'none';
 if((busy&&!s.created)||gen){const drawing=(s.map_source==='generated'&&!s.map_generated)||gen==='map';
  $('makingHead').textContent=drawing?'The map is being drawn from your description':'The World is making the valley';
  $('makingNote').textContent=drawing?'The ground, the water, the sky, the places and the names all come from what you wrote. Then the World rolls the people. Watch the World\u2019s terminal.':'Rolling every life, secret, and grudge. This takes a minute or two. Watch the World\u2019s terminal.'}
 $('chronEmpty').style.display=s.transcript.length?'none':'block';
 const part=e=>e.phase&&e.day?`Day ${e.day} · ${e.phase}`:'';
 // a crowded room is several conversations; each knot's lines sit under a header of their own
 const knot=e=>e.kind==='speech'&&e.cluster?e.cluster:'';
 const msgHtml=(e,i,arr)=>{const prev=i>0?arr[i-1]:null;const key=part(e);const div=key&&(!prev||part(prev)!==key)?`<div class="daypart">${esc(key)}</div>`:'';
  const ck=knot(e);const cdiv=ck&&(!prev||knot(prev)!==ck||part(prev)!==key)?`<div class="knot">${esc(ck)}</div>`:'';return div+cdiv+`<div class="msg ${e.kind}${/^\s*WHISPER\s+@/im.test(e.text)?' whisper':''}${e.kind==='convener'&&/@[A-Za-z]/.test(e.text)?' private':''}" style="${e.color?'--c:'+esc(e.color):''}"><div class="hd"><span class="who">${esc(e.speaker)}</span><span class="meta">Day ${e.day??0}, turn ${e.turn}${e.place?' \u00b7 '+esc(e.place):''}</span></div><div class="body">${rich(e.text)}</div>${e.kind==='speech'&&Array.isArray(e.heard)?`<div class="heard">heard by ${e.heard.length?esc(e.heard.join(', ')):'nobody'}</div>`:''}</div>`};
 const have=$('msgs').querySelectorAll('.msg').length;
 if(first||have>s.transcript.length){$('msgs').innerHTML=s.transcript.map(msgHtml).join('');chronBottom()}
 else if(have<s.transcript.length){const atB=$('chron').scrollHeight-$('chron').scrollTop-$('chron').clientHeight<120;$('msgs').insertAdjacentHTML('beforeend',s.transcript.slice(have).map((e,i)=>msgHtml(e,have+i,s.transcript)).join(''));if(atB)chronBottom()}
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
 else if(name==='fate')renderFate(s);
 else if(name==='connections'){renderConn(s);renderTg(s)}
 else if(name==='colony')renderColony(s)
 else if(name==='more')renderMore(s)}

// ---------- Colony: the day's work and who holds it, the ledger with today's change, the season and the weather
let colHtml='';
function renderColony(s){const R=s.day_report||{};const L=s.ledger||{};const ch=R.change||{};const defs=s.duty_defs||{};const roster=(s.roster||{}).duties||{};const st=s.duty_state||{};
 if(!s.created){$('colHead').innerHTML='<div class="empty">The colony appears here once the World has rolled it.</div>';$('colDuties').innerHTML='';$('colLedger').innerHTML='';$('colPlaces').innerHTML='';$('colMorning').innerHTML='';colHtml='';return}
 const living=(s.characters||[]).filter(c=>c.alive&&!c.gone);const sick=living.filter(c=>c.sick).map(c=>c.name);const bodies=Object.entries(s.bodies||{});
 const count=(label,names)=>names.length?`<span title="${esc(names.join(', '))}">${label}: ${names.length} of ${living.length}.</span> `:'';
 const head=`<p class="colsent">${esc(s.sentence||R.sentence||`Day ${s.day}.`)}</p>
  <p class="small">${count('Sick and cannot work',sick)}${bodies.length?`Unburied: ${bodies.map(([n,p])=>esc(n)+' at '+esc(p)).join(', ')}. `:''}${Object.keys(s.fires||{}).length?`Burning: ${Object.keys(s.fires).map(esc).join(', ')}. `:''}${count('Hungry',R.hungry||[])}${count('Freezing',R.freezing||[])}</p>`;
 const thead=cols=>`<thead><tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead>`;
 const duties=`<table class="ctab">${thead(['Job','Where','Who','Today'])}<tbody>`+Object.entries(defs).map(([k,d])=>{const r=roster[k]||{};const x=st[k]||{};const hs=living.filter(c=>(c.duties||[]).includes(k)).map(c=>c.name);
  const un=!hs.length;const done=x.done_day===s.day;const sickSet=new Set(sick);const dumped=r.dumped_on&&!hs.includes(r.dumped_on)?r.dumped_on:'';
  const who=hs.map(h=>esc(h)+(sickSet.has(h)?' (sick)':'')).concat(dumped?[esc(dumped)+' (covering)']:[]).join(', ')||'nobody';
  const since=x.unclaimed_day?Math.max(1,s.day-x.unclaimed_day+1):1;
  const today=x.nothing_day===s.day?['nothing to do','quiet']:done?['done','good']:dumped?[`${esc(dumped)} is covering it today`,'poor']:un?[`open for ${since} day${since>1?'s':''}`,'poor']:['not done today','poor'];
  return `<tr class="colduty ${un?'un':''} ${done?'done':''}"><td class="cdn">${esc(d.label)}</td><td class="cdp">${esc(r.place||'')}</td><td class="cdw ${un&&!dumped?'poor':''}">${who}</td><td class="cds ${today[1]}">${today[0]}</td></tr>`}).join('')+'</tbody></table>';
 const chg=v=>v?`<span class="chg ${v>0?'up':'down'}">${v>0?'+':''}${v}</span>`:'';
 const ledger=`<table class="ctab">${thead(['Good','Have','Change'])}<tbody>`+STORES.map(k=>`<tr><td class="cdn">${k}</td><td class="cdw ${(L[k]||0)<=(k==='tools'||k==='herbs'?2:4)?'poor':''}">${L[k]??0}</td><td>${chg(ch[k])}</td></tr>`).join('')
  +`<tr><td class="cdn">road after dark</td><td class="cdw ${L.road_safe?'good':'poor'}">${L.road_safe?'safe':'unsafe'}</td><td></td></tr><tr><td class="cdn">built</td><td class="cdw">${esc((L.built||[]).join(', ')||'nothing')}</td><td></td></tr></tbody></table>`;
 const pc=(R.places||{});const places=`<table class="ctab">${thead(['Place','Roof','Warmth','Filth'])}<tbody>`+Object.entries(s.upkeep||{}).map(([p,u])=>{const d=pc[p]||{};const cell=(k,v,bad)=>`<td class="cdw ${bad?'poor':''}">${v} ${chg(d[k])}</td>`;
  const roofed=!['forest','fields','water','road','cave','ruin'].includes(((s.map||{})[p]||{}).kind);
  return `<tr class="colplace"><td class="cdn">${esc(p)}</td>${roofed?cell('roof',u.roof,u.roof<4):'<td class="cdp">no roof</td>'}${cell('warmth',u.warmth,u.warmth<=2)}${cell('filth',u.filth,u.filth>=6)}</tr>`}).join('')+'</tbody></table>';
 const m=(s.transcript||[]).slice().reverse().find(e=>e.kind==='morning'&&e.day===s.day);
 const morning=m?`<div class="card2"><div class="ch">This morning</div><div class="colmorn">${rich(m.text)}</div></div>`:'';
 const html=head+'|'+duties+'|'+ledger+'|'+places+'|'+morning;if(html===colHtml)return;colHtml=html;
 $('colHead').innerHTML=head;$('colDuties').innerHTML=duties||'<div class="note">No jobs yet.</div>';$('colLedger').innerHTML=ledger;$('colPlaces').innerHTML=places;$('colMorning').innerHTML=morning}
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
 else if(g==='quit'){if(!confirm('Quit Terraceilia? Every CLI it started is killed. Games are kept.'))return;try{await api('/shutdown',{})}catch(e){}document.body.innerHTML='<div style="padding:40px;color:var(--muted)">Terraceilia is closed.</div>'}});

// ---------- People
function modelPick(pfx,val,selP,selM,inpC){fillSel(selP,Object.keys(providers),val.provider);const ms=[FIRST].concat((providers[val.provider]||{models:[]}).models,['Custom...']);const v=val.model||FIRST;const known=ms.includes(v);fillSel(selM,ms,known?v:'Custom...');inpC.style.display=known?'none':'';if(!known)inpC.value=val.model;
 selP.onchange=()=>{const m2=[FIRST].concat((providers[selP.value]||{models:[]}).models,['Custom...']);fillSel(selM,m2,FIRST);inpC.style.display='none'};selM.onchange=()=>{inpC.style.display=selM.value==='Custom...'?'':'none';if(selM.value==='Custom...')inpC.focus()}}
function pickVal(selP,selM,inpC){const m=selM.value;return {provider:selP.value,model:m==='Custom...'?inpC.value.trim():m===FIRST?'':m}}
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

function renderPeople(s){const pane=$('peoPane');const drafting=!!s.draft&&!s.created;
 $('peoAddTop').style.display=drafting?'':'none';
 if(!s.characters.length){$('peoStrip').innerHTML='';$('peoPick').innerHTML='';$('peoHead').innerHTML='';peoStripHtml='';peoPaneHtml='';
  pane.innerHTML=drafting?'<div class="empty">Nobody is in the draft yet. Press Generate under Setup and the engine rolls the valley.</div>':'<div class="empty">Nobody lives here yet. Press Start and the World rolls them.</div>';return}
 if(!s.characters.some(c=>c.name===peoSel))peoSel=s.characters[0].name;
 peoRenderStrip(s);
 // never rebuild the panel under someone's hands
 const busy=pane.contains(document.activeElement)&&/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||'');
 if(!busy)peoRenderPane(s)}

function peoRenderStrip(s){const q=peoFilter.trim().toLowerCase();
 const rows=s.characters.filter(c=>!q||`${c.name} ${c.trade||''} ${c.location}`.toLowerCase().includes(q))
  .sort((a,b)=>(a.alive?0:1)-(b.alive?0:1));      // the dead go to the end, still there, still dimmed
 const html=rows.map(c=>{const pct=Math.max(0,Math.min(100,Math.round(100*c.hp/Math.max(1,c.hp_max))));
  const band=(!c.alive||pct<30)?'low':pct<60?'mid':'';
  return `<button type="button" class="chip ${c.name===peoSel?'on':''} ${c.alive?'':'dead'}" data-n="${esc(c.name)}" style="--c:${esc(seatColor(c.name)||'var(--faint)')}" title="${esc(c.name)}, ${esc(c.trade||'no trade yet')}, at ${esc(c.location)}">
   <span class="cn"><span class="dot"></span>${esc(c.name)}</span><span class="cp">${(((s.titles||{})[c.name])||[]).length?esc(((s.titles||{})[c.name]).join(', '))+' · ':''}${esc(c.location)}${c.sick?' · sick':''}</span>
   <span class="chp ${band}"><i style="width:${c.alive?pct:0}%"></i></span>
   <span class="chhp">${c.alive?`hp ${c.hp}/${c.hp_max}`:'dead'}</span>${c.alive&&c.activity?`<span class="chact">${esc(c.activity)}</span>`:''}</button>`}).join('')
  ||'<div class="empty">Nobody matches that.</div>';
 const htmlAll=html+((s.draft&&!s.created)?`<button type="button" class="chip add" id="peoAdd" title="One more person in the draft"><span class="cn">+ Add person</span><span class="cp">rolled by the engine, given a life by the World</span></button>`:'');
 if(htmlAll!==peoStripHtml){$('peoStrip').innerHTML=htmlAll;peoStripHtml=htmlAll;
  $('peoStrip').querySelectorAll('.chip:not(.add)').forEach(b=>b.onclick=()=>{if(peoSel!==b.dataset.n){peoSel=b.dataset.n;peoNote='';peoPaneHtml=''}renderPeople(S)});
  const add=$('peoAdd');if(add)add.onclick=async()=>{peoNote='';const r=await api('/draft/add',{});peoNote=r.last_god||'';render(r)}}
 if(peoShown!==peoSel){peoShown=peoSel;const on=$('peoStrip').querySelector('.chip.on');
  if(on&&on.scrollIntoView)on.scrollIntoView({block:'nearest',inline:'nearest'})}
 const opts=rows.map(c=>`<option ${c.name===peoSel?'selected':''}>${esc(c.name)}</option>`).join('');
 const pick=$('peoPick');if(pick.innerHTML!==opts)pick.innerHTML=opts;
 if(pick.value!==peoSel)pick.value=peoSel}

function peoRenderPane(s){const c=s.characters.find(x=>x.name===peoSel);if(!c)return;
 const tt=((s.titles||{})[c.name]||[]);const title=tt[0]||'';const trade=(c.trade||'').trim();
 const showTrade=trade&&!(title&&title.replace(/^the /,'').toLowerCase()===trade.replace(/^the /,'').toLowerCase());
 $('peoHead').innerHTML=`<span class="nm">${esc(c.name)}</span>${title?`, <i class="ttl">${esc(title)}</i>`:''}${showTrade?`, ${esc(/^the /i.test(trade)?trade:'the '+trade)}`:''} \u00b7 ${esc(c.location)} \u00b7 ${c.alive?(c.gone?'gone':'alive'):'dead, '+esc(c.cause_of_death||'unknown')}${(()=>{const g=c.goal||{};const wp=((s.want_progress||{})[c.name])||[0,''];return g.text?` \u00b7 wants ${esc(g.text)}, ${wp[0]}%`:''})()}${(s.draft&&!s.created)?` \u00b7 <span class="${(s.seat_tests||{})[c.name]?'good':'poor'}">${(s.seat_tests||{})[c.name]?'seat tested':'seat not tested'}</span>`:''}`;
 document.querySelectorAll('.ptabs button').forEach(b=>b.classList.toggle('on',b.dataset.p===peoTab));
 const html=(peoTab==='bio'?paneBio(s,c):peoTab==='body'?paneBody(s,c):peoTab==='disp'?paneDisp(s,c):peoTab==='ties'?paneTies(s,c):peoTab==='duties'?paneDuties(s,c):paneLog(s,c))
  +(peoTab==='log'?'':`<p class="small">${esc(peoNote)}</p>`);
 if(html===peoPaneHtml)return;
 $('peoPane').innerHTML=html;peoPaneHtml=html;peoWire(s,c)}

async function peoApply(patch){peoNote='';const r=await api('/edit/character',{name:peoSel,...patch});
 peoNote=r.last_god||'no change';peoPaneHtml='';render(r)}

// ---- Bio. One form, two columns, label above value, every control the same height. Save sits bottom right.
function paneBio(s,c){const places=s.places||[];const f=(id,label,inner)=>`<div class="fld"><label for="${id}">${label}</label>${inner}</div>`;
 return `<div class="form2">
  ${f('b_name','Name',`<input id="b_name" value="${esc(c.name)}">`)}
  ${f('b_trade','Trade',`<input id="b_trade" value="${esc(c.trade)}">`)}
  ${f('b_home','Home',`<input id="b_home" value="${esc(c.home)}" list="b_places"><datalist id="b_places">${places.map(p=>`<option>${esc(p)}</option>`).join('')}</datalist>`)}
  ${f('b_loc','Where they are now',`<select id="b_loc">${places.map(p=>`<option ${p===c.location?'selected':''}>${esc(p)}</option>`).join('')}</select>`)}
  ${f('b_state','State',`<select id="b_state"><option value="alive" ${c.alive&&!c.gone?'selected':''}>alive</option><option value="gone" ${c.gone?'selected':''}>gone from the valley</option><option value="dead" ${!c.alive?'selected':''}>dead</option></select>`)}
  ${f('b_pastime','Pastime',`<select id="b_pastime">${Object.entries(s.pastime_defs||{}).map(([k,d])=>`<option value="${k}" ${k===c.pastime?'selected':''}>${esc(d.label)}</option>`).join('')}</select>`)}
  ${f('b_prov','Played by',`<select id="b_prov"></select>`)}
  ${f('b_model','Model',`<select id="b_model"></select><input id="b_custom" placeholder="custom model" style="display:none">`)}
  ${f('b_pers','Personality',`<textarea id="b_pers" rows="3">${esc(c.personality)}</textarea>`)}
  ${f('b_secret','Secret, known only to them',`<textarea id="b_secret" rows="3">${esc(c.secret)}</textarea>`)}
  ${f('b_fear','Fear',`<textarea id="b_fear" rows="3">${esc(c.fear)}</textarea>`)}
  ${f('b_want','What they want more than anything',`<textarea id="b_want" rows="3">${esc(c.want)}</textarea>`)}
 </div>
 <div class="ch" style="margin-top:8px">How they talk</div>
 <div class="form2">
  ${f('b_vlen','Sentence length',`<select id="b_vlen">${['clipped','plain','rambling'].map(v=>`<option value="${v}" ${v===((c.voice||{}).length||'plain')?'selected':''}>${v}</option>`).join('')}</select>`)}
  ${f('b_vhabit','One verbal habit',`<input id="b_vhabit" value="${esc((c.voice||{}).habit||'')}">`)}
  ${f('b_vex','Three lines they might say, one per line',`<textarea id="b_vex" rows="3">${esc(((c.voice||{}).examples||[]).join('\n'))}</textarea>`)}
  ${f('b_vnever','What they never talk about',`<textarea id="b_vnever" rows="3">${esc((c.voice||{}).never||'')}</textarea>`)}
 </div>
 <div class="row end">${(s.draft&&!s.created)?`<button type="button" class="btn" id="b_rr" title="A new name, trade, personality, secret, fear, want and way of speaking; the seat and the model stay">Reroll</button><button type="button" class="btn danger" id="b_rm">Remove</button>`:''}${(c.items||[]).length?`<span class="small" title="Things they made or found">Keeps: ${c.items.map(esc).join(', ')}</span>`:''}<button type="button" class="btn" id="b_reroll" title="Roll a new measured want for them">New want</button><span class="small">${(s.draft&&!s.created)?'Edits here go into the draft; the year starts with what you see.':'A changed life or model starts them fresh on their next turn.'}</span><button class="primary" id="b_save">Save</button></div>`}

// ---- Body, shown as Health. Condition and wounds, the four needs as equal bars, then the numbers as one aligned list. What a word means is in its tooltip.
const CONDITION=p=>p>=100?['Unhurt','good']:p>=75?['Scratched','good']:p>=50?['Hurt','fair']:p>=25?['Badly hurt','poor']:p>0?['Dying','poor']:['Dead','poor'];
const WOUNDS=p=>p>=100?'none':p>=75?'minor':p>=50?'serious':p>=25?'severe':p>0?'mortal':'past helping';
function row(label,value,cls,tip){return `<div class="srow" ${tip?`title="${esc(tip)}"`:''}><span class="lbl">${label}</span><span class="val ${cls||''}">${value}</span></div>`}
const NEEDTIP={food:'Falls every day. At zero it takes health each morning; a starving person eats before they work.',warmth:'Falls every day, faster in the cold. At zero it takes health; a freezing person goes home to the fire before they work.',rest:'Falls with work and drink, rises with a night under a roof. At zero, work is halved.',spirit:'Falls a little every day, rises on their pastime, good company and a good meal. Low, work is halved and refusing is easier; high, work is better.'};
function paneBody(s,c){const pct=Math.max(0,Math.min(100,Math.round(100*c.hp/Math.max(1,c.hp_max))));const [word,tone]=CONDITION(c.alive?pct:0);const sk=Object.entries(c.skills||{});
 const pip=(v,max)=>`<span class="pip" title="${v} of ${max}">${Array.from({length:max},(_,i)=>`<b class="${i<v?'on':''}"></b>`).join('')}</span>`;
 return `<div class="card2">
  <div class="cond" title="${esc(c.alive?c.hp:0)} of ${esc(c.hp_max)} health. One wound level; the word is read from it."><span class="cword ${tone}">${word}</span><span class="gbar ${tone}"><i style="width:${c.alive?pct:0}%"></i></span><span class="small">wounds ${c.alive?WOUNDS(pct):'past helping'}</span></div>
  <div class="needbars">${['food','warmth','rest','spirit'].map(k=>{const v=(c.needs||{})[k]??0;const t=v<=0?'poor':v<=4?'fair':'good';return `<div class="need" title="${esc(NEEDTIP[k])}"><span class="lbl">${k}</span><span class="gbar ${t}"><i style="width:${v*10}%"></i></span><span class="val ${t}">${needWord(k,v)}</span><input class="vin" type="number" id="h_${k}" min="0" max="10" value="${v}"></div>`}).join('')}</div>
  <div class="list">
   ${row('Health',`<input class="vin" type="number" id="h_hp" min="0" value="${c.hp}"><span class="small">of</span><input class="vin" type="number" id="h_hpm" min="1" value="${c.hp_max}">`,'','Health now, and the most they can have. Zero is death.')}
   ${row('Sick',`<select class="vin wide" id="h_sick"><option value="0" ${c.sick?'':'selected'}>no</option><option value="1" ${c.sick?'selected':''}>yes</option></select>`,c.sick?'poor':'good','The sick cannot work and get worse until someone tends them.')}
   ${row('Strength',`${pip(c.str,9)}<input class="vin" type="number" id="s_str" min="0" max="9" value="${c.str}">`,'','Fights, wood, and carrying. 2 to 9.')}
   ${row('Speed',`${pip(c.spd,9)}<input class="vin" type="number" id="s_spd" min="0" max="9" value="${c.spd}">`,'','Fires, running, and getting away. 2 to 9.')}
   ${row('Gold',`<input class="vin" type="number" id="s_gold" min="0" value="${c.gold}">`,'','Coin in hand. Moves by giving, stealing, trading and finding.')}
   ${row('Standing',`<select class="vin wide" id="s_stand">${['hated','shunned','nobody','known','respected','loved'].map(x=>`<option ${x===c.standing?'selected':''}>${x}</option>`).join('')}</select>`,'','What the valley thinks of them. Moves only from what they do and how others take it.')}
   <div class="srow skills" title="1 to 9. Set one to 0 to take it away. Skills rise from work and from being taught."><span class="lbl">Skills</span><span class="val col" id="s_skills">${sk.map(([k,v])=>`<span class="skillrow"><input class="sk" value="${esc(k)}">${pip(v,9)}<input class="sv vin" type="number" min="0" max="9" value="${v}"></span>`).join('')}<span class="skillrow new"><input class="sk" placeholder="a skill they have learned"><span></span><input class="sv vin" type="number" min="0" max="9" value="0"></span></span></div>
  </div>
  <div class="row end"><button class="primary" id="b2_save">Save</button></div></div>`}

// ---- Disposition, shown as Personality. The twelve dials keep their names.
let dialSel='',tieSel='';
function paneDisp(s,c){const t=c.traits||{};
 return `<p class="small">Their nature, which they play without softening. A step takes effect at once and starts them fresh on their next turn.</p><div class="dgrid">`
  +TRAITS.map(([k,label,lo,hi,words])=>{const v=Math.max(1,Math.min(5,+t[k]||3));
   return `<div class="dial ${dialSel===k?'sel':''}" data-k="${k}">
    <div class="dtop"><span class="dname">${label}</span><span class="dword">${esc(words[v-1])}</span></div>
    ${seg(1,5,v)}
    <div class="dends"><span>${esc(lo)}</span><span>${esc(hi)}</span></div></div>`}).join('')+`</div>`}

// ---- Relationships
function paneTies(s,c){const rs=(s.relations||{})[c.name]||{};
 const rows=s.characters.filter(o=>o.name!==c.name).map(o=>({o,r:rs[o.name]||{type:'none',feeling:0,trust:0}}));
 if(tieSort==='name')rows.sort((a,b)=>a.o.name.localeCompare(b.o.name));
 else if(tieSort==='type')rows.sort((a,b)=>(a.r.type||'none').localeCompare(b.r.type||'none')||a.o.name.localeCompare(b.o.name));
 else rows.sort((a,b)=>(Math.abs(b.r.feeling)+Math.abs(b.r.trust))-(Math.abs(a.r.feeling)+Math.abs(a.r.trust))||a.o.name.localeCompare(b.o.name));
 if(!rows.length)return '<div class="empty">There is nobody else left to have an opinion about.</div>';
 return `<div class="tieHead"><span class="small">How ${esc(c.name)} feels about everyone else. Both run from -5 to 5. Click a step to set it.</span>
   <label class="small" style="margin-left:auto">Sort <select id="t_sort">${[['strongest','strongest first'],['name','by name'],['type','by kind of relationship']].map(([v,l])=>`<option value="${v}" ${v===tieSort?'selected':''}>${l}</option>`).join('')}</select></label></div>`
  +rows.map(({o,r})=>`<div class="tie ${tieSel===o.name?'sel':''}" data-b="${esc(o.name)}">
   <span class="tn" style="color:${esc(seatColor(o.name)||'var(--ink)')}">${esc(o.name)}</span>
   <div class="cell"><select class="tt">${REL.map(t=>`<option ${t===r.type?'selected':''}>${t}</option>`).join('')}</select></div>
   <div class="cell"><div class="tlab">feeling <span>${r.feeling>=0?'+':''}${r.feeling}</span></div>${seg(-5,5,r.feeling)}</div>
   <div class="cell"><div class="tlab">trust <span>${r.trust>=0?'+':''}${r.trust}</span></div>${seg(-5,5,r.trust)}</div>
   <label class="mut" title="also set the same the other way"><input type="checkbox" class="tm"> both ways</label>
   <button class="btn twhy">Why</button></div>`).join('')}

// ---- Jobs. What the valley's work is, who holds each piece, and this person's share of it. Fate ticks and unticks.
function paneDuties(s,c){const defs=s.duty_defs||{};const mine=new Set(c.duties||[]);const dumped=new Set(c.dumped||[]);
 const holdersOf=k=>(s.characters||[]).filter(o=>o.alive&&!o.gone&&(o.duties||[]).includes(k)).map(o=>o.name);
 const made=d=>Object.entries(d.produces||{}).map(([k,v])=>v+' '+k).join(', ')||Object.entries(d.effect||{}).filter(([k])=>['roof','warmth','filth'].includes(k)).map(([k,v])=>k+' '+(v>0?'+':'')+v).join(', ')||'keeps things from getting worse';
 const uses=d=>Object.entries(d.consumes||{}).map(([k,v])=>v+' '+k).join(', ');
 const em=c.emergency;
 return `<div class="note" style="margin-bottom:12px">${esc(c.name)} holds ${mine.size} of a possible 3. Tick a job to give it to them, untick to take it away; it applies at once. A job nobody holds is covered each morning by whoever is nearest.</div>
  ${em?`<div class="hsit">Emergency today: ${esc(em.text)}${em.place&&!String(em.text||'').includes(em.place)?' at '+esc(em.place):''}</div>`:''}
  ${dumped.size?`<div class="hsit">Covering today: ${[...dumped].map(k=>esc((defs[k]||{}).label||k)).join(', ')}</div>`:''}
  <div class="dutylist">${Object.entries(defs).map(([k,d])=>{const hs=holdersOf(k);const un=!hs.length;const st=((s.duty_state||{})[k])||{};const since=st.unclaimed_day?Math.max(1,s.day-st.unclaimed_day+1):0;
   return `<label class="duty ${mine.has(k)?'on':''} ${un?'un':''}"><input type="checkbox" class="dk" data-k="${k}" ${mine.has(k)?'checked':''}>
    <span class="dl"><span>${esc(d.label)}</span> <i>${esc(d.verb)} · ${esc(d.skill)}${(c.skills||{})[d.skill]?' '+(c.skills||{})[d.skill]:''}</i></span>
    <span class="dm">makes ${esc(made(d))}${uses(d)?' · uses '+esc(uses(d)):''}</span>
    <span class="dh ${un?'poor':''}">${un?'open'+(since?` for ${since} day${since>1?'s':''}`:''):hs.map(esc).join(', ')}</span>
    <span class="db">${esc(d.breaks)}</span></label>`}).join('')}</div>`}

// ---- Log
function paneLog(s,c){const rx=rxName(c.name);
 const body=t=>{const i=(t||'').search(/\nPROSPERITY|\nSTANDINGS/);return i>0?t.slice(0,i):(t||'')};
 const rows=[];const wt=(f,t)=>`${f>=0?'+':''}${f} feeling${t?`, ${t>=0?'+':''}${t} trust`:''}`;
 for(const a of (s.social||[])){if(a.actor!==c.name&&a.target!==c.name)continue;const gave=a.actor===c.name;const other=gave?a.target:a.actor;
  const text=`<span class="sk">${gave?'gave':'got'}</span> ${esc(a.text)}${a.line?` <span class="sq">${esc(a.line)}</span>`:''} <span class="sw">${wt(a.fw,a.tw)}</span> <span class="st">${gave?`${esc(other)} now stands at`:`total from ${esc(other)}`} ${a.total_f}${a.tw||a.total_t?` / ${a.total_t}`:''}${a.stepped?', a step':''}</span>${a.cost?` <span class="sw">${esc(a.cost)}</span>`:''}${a.fight?` <span class="sw">${esc(a.fight)}</span>`:''}`;
  rows.push({e:{day:a.day,turn:0,kind:'social',speaker:a.actor,place:a.place},text,raw:true})}
 for(const e of (s.transcript||[])){
  if(e.speaker===c.name){rows.push({e,text:e.text});continue}
  if(!['world','system','fate','epilogue','convener','dawn','morning','afternoon','evening'].includes(e.kind))continue;
  const b=body(e.text);if(!rx.test(b))continue;
  const hits=b.split(/(?<=[.!?])\s+/).filter(x=>rx.test(x));
  rows.push({e,text:hits.length?hits.join(' '):b.slice(0,240)})}
 if(!rows.length)return '<div class="empty">Nothing about them yet. Their days appear here once the year begins.</div>';
 let out='',day=null;
 rows.sort((a,b)=>(a.e.day-b.e.day)||((a.e.turn||1e9)-(b.e.turn||1e9)));
 for(const {e,text,raw} of rows.slice(-250).reverse()){
  if(e.day!==day){day=e.day;out+=`<div class="logday">Day ${day}</div>`}
  out+=`<div class="logrow ${esc(e.kind)}" style="${e.speaker===c.name?'--c:'+esc(seatColor(c.name)||'var(--faint)'):''}"><div class="lm">${esc(e.speaker)} \u00b7 Day ${e.day??0}${e.turn?`, turn ${e.turn}`:''}${e.place?' \u00b7 '+esc(e.place):''}</div>${raw?text:rich(text)}</div>`}
 return out}

// ---- handlers for whichever tab is showing
function peoWire(s,c){const pane=$('peoPane');
 if(peoTab==='bio'){const seat=(s.seats||[]).find(x=>x.name===c.name)||{provider:Object.keys(providers)[0]||'',model:''};
  modelPick('b',seat,$('b_prov'),$('b_model'),$('b_custom'));
  if($('b_reroll'))$('b_reroll').onclick=()=>peoApply({reroll_want:true});
  if($('b_rr'))$('b_rr').onclick=async()=>{peoNote='';const r=await api('/draft/reroll',{name:peoSel});peoNote=r.last_god||'';peoPaneHtml='';render(r)};
  if($('b_rm'))$('b_rm').onclick=async()=>{if(!confirm(`Remove ${peoSel} from the draft?`))return;peoNote='';const r=await api('/draft/remove',{name:peoSel});peoNote=r.last_god||'';peoSel='';peoPaneHtml='';render(r)};
  $('b_save').onclick=async()=>{const st=$('b_state').value;
   const d={new_name:$('b_name').value.trim(),trade:$('b_trade').value,home:$('b_home').value,location:$('b_loc').value,
    personality:$('b_pers').value,secret:$('b_secret').value,fear:$('b_fear').value,want:$('b_want').value,pastime:$('b_pastime').value,
    voice:{length:$('b_vlen').value,habit:$('b_vhabit').value,examples:$('b_vex').value.split('\n').map(x=>x.trim()).filter(Boolean),never:$('b_vnever').value},
    ...pickVal($('b_prov'),$('b_model'),$('b_custom'))};
   if(st==='dead')d.hp=0;
   if(st==='gone')d.gone=true;
   if(st==='alive'){d.gone=false;d.alive=true;if(c.hp<=0)d.hp=1}
   const nn=d.new_name;peoNote='';const r=await api('/edit/character',{name:peoSel,...d});
   if(nn&&nn!==peoSel&&(r.characters||[]).some(x=>x.name===nn))peoSel=nn;
   peoNote=r.last_god||'no change';peoPaneHtml='';render(r)}}
 else if(peoTab==='body'){
   $('b2_save').onclick=async()=>{const skills={};
   pane.querySelectorAll('.skillrow').forEach(r=>{const k=r.querySelector('.sk').value.trim();if(k)skills[k]=+r.querySelector('.sv').value||0});
   await peoApply({hp:+$('h_hp').value,hp_max:+$('h_hpm').value,sick:$('h_sick').value==='1',needs:{food:+$('h_food').value,warmth:+$('h_warmth').value,rest:+$('h_rest').value,spirit:+$('h_spirit').value},
    str:+$('s_str').value,spd:+$('s_spd').value,gold:+$('s_gold').value,standing:$('s_stand').value,skills})}}
 else if(peoTab==='disp'){
  pane.querySelectorAll('.dial').forEach(d=>{d.onclick=()=>{if(dialSel!==d.dataset.k){dialSel=d.dataset.k;pane.querySelectorAll('.dial').forEach(x=>x.classList.toggle('sel',x===d))}};
   d.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>{dialSel=d.dataset.k;peoApply({traits:{[d.dataset.k]:+b.dataset.i}})})})}
 else if(peoTab==='duties'){
  pane.querySelectorAll('.dk').forEach(b=>b.onchange=()=>{const ks=[...pane.querySelectorAll('.dk')].filter(x=>x.checked).map(x=>x.dataset.k);
   if(ks.length>3){b.checked=false;peoNote='Three at most.';return}peoApply({duties:ks})})}
 else if(peoTab==='ties'){
  $('t_sort').onchange=e=>{tieSort=e.target.value;peoPaneHtml='';renderPeople(S)};
  pane.querySelectorAll('.tie').forEach(row=>{const segs=row.querySelectorAll('.seg');
   row.onclick=()=>{if(tieSel!==row.dataset.b){tieSel=row.dataset.b;pane.querySelectorAll('.tie').forEach(x=>x.classList.toggle('sel',x===row))}};
   const send=async()=>{peoNote='';tieSel=row.dataset.b;
    const r=await api('/edit/relation',{a:peoSel,b:row.dataset.b,type:row.querySelector('.tt').value,
     feeling:+segs[0].dataset.v,trust:+segs[1].dataset.v,mutual:row.querySelector('.tm').checked});
    peoNote='Saved '+new Date().toLocaleTimeString();peoPaneHtml='';render(r)};
   segs.forEach(sg=>sg.querySelectorAll('button').forEach(b=>b.onclick=()=>{sg.dataset.v=b.dataset.i;send()}));
   row.querySelector('.tt').onchange=send;
   row.querySelector('.twhy').onclick=()=>showWhy(peoSel,row.dataset.b)})}}

document.querySelectorAll('.ptabs button').forEach(b=>b.onclick=()=>{peoTab=b.dataset.p;peoNote='';peoPaneHtml='';if(S)renderPeople(S)});
$('peoFilter').oninput=()=>{peoFilter=$('peoFilter').value;peoStripHtml='';if(S)peoRenderStrip(S)};
$('peoStrip').addEventListener('wheel',e=>{      // a wheel or a two finger swipe moves the row sideways
 const strip=$('peoStrip');
 if(strip.scrollWidth<=strip.clientWidth+1)return;
 const d=Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:e.deltaY;
 if(!d)return;
 e.preventDefault();strip.scrollLeft+=d},{passive:false});
// drag to scroll the strip; a real drag swallows the click that would have picked a chip
(()=>{const strip=$('peoStrip');let down=null,moved=false;
 strip.addEventListener('pointerdown',e=>{if(e.button!==0)return;down={x:e.clientX,left:strip.scrollLeft};moved=false});
 strip.addEventListener('pointermove',e=>{if(!down)return;const dx=e.clientX-down.x;if(!moved&&Math.abs(dx)<5)return;if(!moved){moved=true;strip.classList.add('dragging');try{strip.setPointerCapture(e.pointerId)}catch(x){}}strip.scrollLeft=down.left-dx});
 const up=e=>{if(!down)return;down=null;if(moved){strip.classList.remove('dragging');const swallow=ev=>{ev.stopPropagation();ev.preventDefault();strip.removeEventListener('click',swallow,true)};strip.addEventListener('click',swallow,true);setTimeout(()=>strip.removeEventListener('click',swallow,true),0)}};
 strip.addEventListener('pointerup',up);strip.addEventListener('pointercancel',up);strip.addEventListener('pointerleave',up);
 const bar=document.querySelector('.stripbar');const paint=()=>{if(!bar)return;const w=strip.scrollWidth,c=strip.clientWidth;if(w<=c+1){bar.style.display='none';return}bar.style.display='';const i=bar.firstElementChild;const frac=c/w;i.style.width=(frac*100).toFixed(2)+'%';i.style.transform=`translateX(${(strip.scrollLeft/(w-c)*(1/frac-1)*100).toFixed(2)}%)`};
 strip.addEventListener('scroll',paint);window.addEventListener('resize',paint);new MutationObserver(paint).observe(strip,{childList:true})})();
$('peoPick').onchange=()=>{peoSel=$('peoPick').value;peoNote='';peoPaneHtml='';if(S)renderPeople(S)};

// ---------- World: the region. The valley, the season calendar, the weather, and every situation in order.
let worldReady=false,regionHtml='';
function renderWorld(s){if(!worldReady){$('g_drama').oninput=()=>{$('g_dramaNote').textContent=$('g_drama').value+' \u00b7 '+DRAMA[+$('g_drama').value]};
  $('g_map_source').onchange=()=>mapInfo(S);$('g_save').onclick=saveWorld;
  $('g_regen').onclick=async()=>{$('g_regen').disabled=true;$('g_regen').textContent='Drawing...';await saveWorld();const r=await api('/map/regenerate',{});$('g_state').textContent=r.last_god||'';render(r);mapInfo(S)};worldReady=true}
 renderRegion(s);
 if(document.activeElement&&$('sheet-world').contains(document.activeElement)&&document.activeElement.tagName!=='BUTTON'){mapInfo(s);return}
 $('g_title').value=s.title||'';$('g_world').value=s.world_text||'';$('g_days').value=s.max_days;$('g_mins').value=s.max_minutes||'';
 $('g_drama').value=s.drama??6;$('g_dramaNote').textContent=$('g_drama').value+' \u00b7 '+DRAMA[+$('g_drama').value];
 modelPick('g',s.world_model,$('g_wp'),$('g_wm'),$('g_wc'));$('g_map_source').value=s.map_source||'builtin';
 modelPick('gm',s.map_model||s.world_model,$('g_mp'),$('g_mm'),$('g_mc'));mapInfo(s)}
function mapInfo(s){const info=$('g_mapInfo');if(!s||!info)return;const started=!!(s.created||(s.seats&&s.seats.length>1)||s.status==='running'||s.status==='paused');
 $('g_mapBlock').style.display=started?'none':'';$('g_descBlock').style.display=started?'none':'';if(started)return;      // the description and the map are fixed once a game has started; the region card is the only copy
 const gen=$('g_map_source').value==='generated';$('g_mapModelRow').style.display=gen?'':'none';
 const names=Object.keys(s.map||{});const st=s.map_style||{};let t;
 if(s.map_generating)t='Drawing a new map from the description. Watch the World\u2019s terminal.';
 else if(s.map_generated)t=`This game plays on ${s.map_name}: ${names.length} places, ${(st.water||{}).type||'no'} water, ${st.sky||'day'} sky. ${names.join(', ')}.`;
 else if(s.map_source==='generated')t='A map will be drawn from the description when you press Start, or now with the button.';
 else t='This game plays on the built-in valley of Terraceilia.';
 info.textContent=t;const b=$('g_regen');b.style.display=gen?'':'none';b.disabled=!!(s.map_generating);b.textContent=s.map_generating?'Drawing...':(s.map_generated?'Regenerate the map':'Draw the map now')}
function gMapModelVal(){const v=pickVal($('g_mp'),$('g_mm'),$('g_mc')),w=pickVal($('g_wp'),$('g_wm'),$('g_wc'));return (v.provider===w.provider&&v.model===w.model)?null:v}
async function saveWorld(){const started=!!(S&&(S.created||(S.seats&&S.seats.length>1)));const d={title:$('g_title').value,max_days:+$('g_days').value,max_minutes:+($('g_mins').value||0),drama:+$('g_drama').value,world_model:pickVal($('g_wp'),$('g_wm'),$('g_wc'))};
 if(!started){d.world_text=$('g_world').value;d.map_source=$('g_map_source').value;d.map_model=gMapModelVal()}
 const r=await api('/edit/game',d);$('g_state').textContent='Saved '+new Date().toLocaleTimeString();render(r);mapInfo(S)}
function renderRegion(s){const box=$('g_region');if(!box)return;const R=s.day_report||{};const th=(s.threads||[]).slice();
 const open=th.filter(t=>t.status==='open').sort((a,b)=>a.day-b.day),done=th.filter(t=>t.status!=='open').sort((a,b)=>(b.resolved_day??0)-(a.resolved_day??0));
 const sit=t=>{const age=(s.day??0)-t.day;const left=t.expires!=null?t.expires-(s.day??0):null;
  return `<div class="sit ${t.status}"><span class="sitn">#${t.id}</span><span class="sitt">${esc(t.text)}${t.place?` <span class="small">at ${esc(t.place)}</span>`:''}</span>
   <span class="small">${t.status==='open'?`open ${age} day${age===1?'':'s'}${left!=null?`, ${left<=0?'ends today':`${left} day${left===1?'':'s'} left`}`:''}`:`ended day ${t.resolved_day??'?'}: ${esc(t.note||'resolved')}`}</span>
   ${t.status==='open'?`<span class="row"><input class="rnote" placeholder="how it ended"><button class="btn rdone" data-id="${t.id}">Resolve</button></span>`:''}</div>`};
 const html=`<div class="card2"><div class="ch">${esc(s.title||'The valley')}</div><p>${esc(s.world_text||'')}</p></div>
  <div class="card2"><div class="ch">The season calendar</div>${(s.calendar_rows||[]).map(r=>`<p>${esc(r)}</p>`).join('')}</div>
  <div class="card2"><div class="ch">Weather</div><p>${esc(s.sentence||'')}</p></div>
  <div class="card2"><div class="ch">Situations</div>${open.length?open.map(sit).join(''):'<p class="small">Nothing is open.</p>'}${done.length?`<div class="ch">Ended</div>`+done.slice(0,40).map(sit).join(''):''}</div>`;
 if(html===regionHtml||typing(box))return;regionHtml=html;box.innerHTML=html;
 box.querySelectorAll('.rdone').forEach(b=>b.onclick=async()=>{b.disabled=true;const note=b.closest('.sit').querySelector('.rnote').value;render(await api('/god/resolve',{id:+b.dataset.id,note}))})}

// ---------- Fate
function renderFate(s){const alive=(s.characters||[]).filter(c=>c.alive&&!c.gone).map(c=>c.name);
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
const CONN_LABEL={connected:'Connected',signed_in:'Signed in, not tested',not_installed:'Not installed',not_signed_in:'Not signed in',checking:'Checking',error:'Error'};
function renderConn(s){const root=$('connList');if(typing(root))return;const c=s.connections||{};const used=new Set((s.seats||[]).map(x=>x.provider).concat([(s.world_model||{}).provider,(s.model_a||{}).provider,(s.model_b||{}).provider]));
 root.innerHTML=Object.entries(c).map(([k,p])=>{const st=p.state==='connected'?'ok':(p.state==='checking'||p.state==='signed_in')?'unk':'bad';
  const job=p.job;const running=!!(job&&!job.done);
  const doing=running?(job.kind==='login'?'Waiting for you to sign in...':job.kind==='test'?((job.lines||[]).slice(-1)[0]||'Testing...'):'Installing...'):'';
  return `<div class="conn${running?' busy':''}" data-p="${esc(k)}">
   <div class="hd"><span><span>${esc(k)}</span>${used.has(k)?' <span class="note">\u00b7 this game uses it</span>':''}${p.version?` <span class="note">\u00b7 ${esc(p.version)}</span>`:''}</span>
    <span class="st ${st}">${running?'<span class="spin sm"></span>':''}${esc(CONN_LABEL[p.state]||p.state)}</span></div>
   <div class="note" style="margin-top:4px">${running?`<b>${esc(doing)}</b>`:esc(p.detail||'')}</div>
   <div class="row" style="margin-top:8px">
    ${p.state==='not_installed'&&p.can_install?`<button class="btn act" data-do="install">Install</button>`:''}
    ${p.state==='not_signed_in'&&p.can_login?`<button class="btn act" data-do="login">Sign in</button>`:''}
    ${(p.state==='connected'||p.state==='signed_in')&&!running?`<button class="btn act" data-do="probe">Test</button>`:''}
    ${p.shares?`<span class="note">Shares one account with ${esc(p.shares)}; a game uses only one of them.</span>`:''}
    ${p.docs?`<a class="note" href="${esc(p.docs)}" target="_blank" rel="noopener" style="margin-left:auto">docs</a>`:''}
   </div>
   ${Object.keys(p.probes||{}).length?`<div class="note" style="margin-top:6px">${Object.entries(p.probes).map(([m,r])=>r.ok?`${esc(m||'(default)')} answered at ${esc(hhmm(r.when))}`:`${esc(m||'(default)')} did not answer${r.message?': '+esc(r.message.slice(0,80)):''}`).join(' \u00b7 ')}</div>`:''}
   ${p.node_missing?`<div class="note" style="margin-top:6px">Node.js is needed first. <a href="https://nodejs.org" target="_blank" rel="noopener">Get Node.js</a>, then press Install.</div>`:''}
   ${job?`<div class="res">${job.note?esc(job.note)+'\n':''}${esc((job.lines||[]).join('\n'))}${!job.done&&job.kind==='login'?'\nWaiting for you to sign in... '+Math.round((job.waited||0))+'s':''}</div>
     ${job.done?`<div class="row"><button class="btn sm act" data-do="dismiss">Hide this</button></div>`:''}`:''}
  </div>`}).join('');
 root.querySelectorAll('.act').forEach(b=>b.onclick=async()=>{const box=b.closest('.conn'),k=box.dataset.p,d=b.dataset.do;
  b.disabled=true;
  if(d==='install')render(await api('/connect/install',{provider:k}));
  else if(d==='login')render(await api('/connect/login',{provider:k}));
  else if(d==='probe')render(await api('/connect/probe',{provider:k}))
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
 [['colony','Colony'],['world','World'],['fate','Fate'],['connections','Connections'],['display','Display']]
 .map(([k,l])=>`<button class="btn" style="width:100%;margin-bottom:8px;justify-content:flex-start" data-m="${k}">${l}</button>`).join('')
 +`<button class="btn" style="width:100%;margin-bottom:8px" data-m="x-chronicle">Export the chronicle</button>`
 +`<button class="danger" style="width:100%;margin-bottom:8px" data-m="stop">Stop this year</button>`
 +`<button class="danger" style="width:100%" data-m="quit">Quit Terraceilia</button>`;
 $('moreList').querySelectorAll('[data-m]').forEach(b=>b.onclick=async()=>{const m=b.dataset.m;
  if(m==='setup'){sheet('');showTab('setup');return}
  if(m==='x-chronicle'){window.location='/export?what=chronicle';return}
  if(m==='stop'){if(confirm('Stop this year here?'))render(await api('/stop',{}));return}
  if(m==='quit'){if(confirm('Quit Terraceilia?')){try{await api('/shutdown',{})}catch(e){}document.body.innerHTML='<div style="padding:40px;color:var(--muted)">Terraceilia is closed.</div>'}return}
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
['wm','ma','mb','mm'].forEach(p=>{$(p+'_p').onchange=()=>{const ms=[FIRST].concat((providers[$(p+'_p').value]||{models:[]}).models,['Custom...']);fillSel($(p+'_m'),ms,FIRST);$(p+'_c').style.display='none';save()};$(p+'_m').onchange=()=>{const cu=$(p+'_m').value==='Custom...';$(p+'_c').style.display=cu?'':'none';if(cu){editing=true;$(p+'_c').focus()}else save()};$(p+'_c').onfocus=()=>editing=true;$(p+'_c').onblur=()=>{editing=false;save()}});
$('primary').onclick=async()=>{const s=S||{};
 if(s.status==='running'){render(await api('/pause',{}));return}
 if(!(s.created))await save();
 if(s.draft&&!(s.characters||[]).length){render(await api('/draft/generate',{what:'all'}));return}
 render(await api('/start',{}));if(mobile())showTab('map')};
$('generate').onclick=async()=>{await save();render(await api('/draft/generate',{what:'all'}))};
$('rerollAll').onclick=async()=>{if(confirm('Reroll everyone? Every edit to the people is lost; the map stays.'))render(await api('/draft/generate',{what:'people'}))};
$('regenMap').onclick=async()=>{render(await api('/draft/generate',{what:'map'}))};
$('openPeople').onclick=()=>sheet('people');
$('testSeats').onclick=async()=>{render(await api('/draft/test',{}))};
$('deleteDraft').onclick=async()=>{if(!S)return;if(confirm('Delete this draft?')){S=null;termKey='';sheet('');render(await api('/game/delete',{id:S?S.id:''}))}};
$('peoAddTop').onclick=async()=>{peoNote='';const r=await api('/draft/add',{});peoNote=r.last_god||'';render(r)};
$('start2').onclick=()=>$('primary').click();
$('startErrLink').onclick=e=>{e.preventDefault();sheet('connections');api('/connect/refresh',{})};
$('newGame').onclick=async()=>{S=null;termKey='';sheet('');render(await api('/game/new',{}));if(mobile())showTab('map')};
$('sayBtn').onclick=async()=>{const t=$('sayText').value.trim();if(!t)return;$('sayText').value='';hlSync();render(await api('/say',{text:t}))};

// ---------- @ mentions in the composer
let acItems=[],acIdx=0,acStart=-1;
function people(){return (S&&S.characters||[]).filter(c=>c.alive&&!c.gone)}
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
