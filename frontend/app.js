
let S=null,editing=false,providers={},termKey='',sideTab='valley',centerTab='map';let T=[],lastTurn=-1,Tid=null;
function mergeTranscript(s){if(s.id!==Tid||s.transcript_total<T.length||(s.transcript&&s.transcript.length&&T.length&&s.transcript[0].turn<=lastTurn&&s.transcript_total!==T.length)){T=s.transcript?s.transcript.slice():[];Tid=s.id}else if(s.transcript)for(const e of s.transcript)if(e.turn>lastTurn)T.push(e);lastTurn=T.length?T[T.length-1].turn:-1;s.transcript=T}
const $=id=>document.getElementById(id);
async function api(p,b){const r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):null});return r.json()}
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const STATUS={idle:'Not started',running:'Running',paused:'Paused',done:'The year is over',stopped:'Stopped'};
const mobile=()=>window.matchMedia('(max-width:820px)').matches;
function seatColor(n){const x=(S&&S.seats||[]).find(y=>y.name===n);return x?x.color:''}
function rich(t){let h=esc(t);const hold=[];const keep=x=>{hold.push(x);return `\u0000${hold.length-1}\u0000`};
 h=h.replace(/^\s*ACTION:\s*(.+)$/gm,(m,a)=>keep(`<span class="act">ACTION: ${a}</span>`));
 h=h.replace(/@([A-Za-z][\w-]*)/g,(m,n)=>{const c=seatColor(n);return `<span class="men" style="${c?'--mc:'+esc(c):''}">@${n}</span>`});
 // markdown-ish tables from the engine
 h=h.replace(/((?:^\|.*\|\s*$\n?)+)/gm,tbl=>{const rows=tbl.trim().split('\n').filter(r=>!/^\|[-| ]+\|$/.test(r));return keep('<table class="st">'+rows.map((r,i)=>'<tr>'+r.split('|').slice(1,-1).map(c=>`<${i?'td':'th'}>${c.trim()}</${i?'td':'th'}>`).join('')+'</tr>').join('')+'</table>')});
 h=h.replace(/\u0000(\d+)\u0000/g,(m,i)=>hold[+i]);
 return h.split(/\n{2,}/).map(p=>`<p>${p.replace(/\n/g,'<br>')}</p>`).join('')}
function fillSel(sel,opts,val){const h=opts.map(o=>`<option ${o===val?'selected':''}>${esc(o)}</option>`).join('');if(sel.innerHTML!==h)sel.innerHTML=h;sel.value=val}
function modelUI(pfx,val){const p=$(pfx+'_p'),m=$(pfx+'_m'),c=$(pfx+'_c');fillSel(p,Object.keys(providers),val.provider);const ms=(providers[val.provider]||{models:[]}).models.concat(['Custom...']);const known=ms.includes(val.model);fillSel(m,ms,known?val.model:'Custom...');c.style.display=known?'none':'';if(!known)c.value=val.model}
function modelVal(pfx){const m=$(pfx+'_m').value;return {provider:$(pfx+'_p').value,model:m==='Custom...'?($(pfx+'_c').value.trim()||''):m}}
const DRAMA=['nothing','a whisper','quiet','calm','ordinary','lively','eventful','hard','harsh','brutal','chaos'];
function renderSetup(s){$('title').value=s.title;$('world_text').value=s.world_text;$('players').value=s.players;$('max_days').value=s.max_days;$('max_minutes').value=s.max_minutes||'';$('repo').value=s.repo;$('drama').value=s.drama??6;$('dramaNote').textContent=($('drama').value)+' · '+DRAMA[+$('drama').value];
 modelUI('wm',s.world_model);modelUI('ma',s.model_a);modelUI('mb',s.model_b);modelUI('mm',s.map_model||s.world_model);
 $('map_source').value=s.map_source||'builtin';$('mapModelRow').style.display=$('map_source').value==='generated'?'':'none';
 $('vers').innerHTML='';renderConn(s,$('connSetup'))}
const FEEL=['hates','despises','dislikes','is cold toward','is cool toward','is indifferent to','is warm toward','likes','is fond of','cares deeply for','loves'];
function relChips(s,name){const rs=(s.relations||{})[name]||{};const items=Object.entries(rs).filter(([b,r])=>r.type!=='none'||r.feeling||r.trust).sort((x,y)=>(Math.abs(y[1].feeling)+Math.abs(y[1].trust))-(Math.abs(x[1].feeling)+Math.abs(x[1].trust)));
 if(!items.length)return '';const chip=([b,r])=>{const hue=r.feeling>0?'var(--accent)':r.feeling<0?'var(--danger)':'var(--faint)';return `<span class="rel" data-a="${esc(name)}" data-b="${esc(b)}" title="${esc(name)} ${FEEL[r.feeling+5]} ${esc(b)}. Click for why." style="--h:${hue}"><b>${esc(b)}</b> ${r.type!=='none'?esc(r.type)+' · ':''}<i>${r.feeling>=0?'+':''}${r.feeling}</i><i class="t">${r.trust>=0?'+':''}${r.trust}</i></span>`};return '<div class="rels">'+items.slice(0,6).map(chip).join('')+(items.length>6?`<details class="more" data-k="r:${esc(name)}"><summary>${items.length-6} more</summary>${items.slice(6).map(chip).join('')}</details>`:'')+'</div>'}
function renderValley(s){if(!s.created){$('valley').innerHTML='<div class="empty">The valley appears here once the World has rolled it.</div>';return}
 const wasOpen=new Set([...$('valley').querySelectorAll('details[open]')].map(d=>d.dataset.k));const scroll=$('valley').scrollTop;
 const L=s.ledger;const pct=Math.min(100,Math.round(100*L.grain_weeks/L.grain_needed));
 let h=`<div class="ledger"><b>Day ${s.day}</b> &middot; grain for <b>${L.grain_weeks}</b> of ${L.grain_needed} weeks<div class="bar" style="--c:var(--accent)"><i style="width:${pct}%"></i></div>${L.roofs_broken} roofs broken &middot; road ${L.road_safe?'safe':'unsafe'} after dark &middot; ${L.sick} sick<br>Built: ${esc(L.built.join(', ')||'nothing yet')}${s.pending.length?`<br><span class="note">${s.pending.length} action(s) waiting for the World</span>`:''}</div>`;
 const byPlace={};s.characters.forEach(c=>{(byPlace[c.alive&&!c.banished?c.location:'Gone']=byPlace[c.alive&&!c.banished?c.location:'Gone']||[]).push(c)});
 const th=(s.threads||[]).filter(t=>t.status==='open');if(th.length)h+=`<div class="ledger"><b>Open situations</b> (${th.length})${th.map(t=>`<div class="thr">#${t.id} · day ${t.day}${t.place?' · '+esc(t.place):''}: ${esc(t.text)}</div>`).join('')}</div>`;
 h+=Object.entries(byPlace).map(([pl,cs])=>`<div class="place">${esc(pl)}</div>`+cs.map(c=>`<div class="card ${c.alive?'':'dead'}" style="--c:${esc(seatColor(c.name)||'#888')}"><span class="nm">${esc(c.name)}</span> <span class="st">${esc(c.trade)} &middot; ${esc(c.location)} &middot; ${esc(c.standing)}${c.banished?' &middot; banished':''}${c.alive?'':' &middot; dead: '+esc(c.cause_of_death)}</span>
  <div class="bar"><i style="width:${Math.round(100*c.hp/c.hp_max)}%"></i></div>HP ${c.hp}/${c.hp_max} &middot; STR ${c.str} SPD ${c.spd} &middot; gold ${c.gold} &middot; ${Object.keys(c.skills).length?Object.entries(c.skills).map(([k,v])=>k+' '+v).join(', '):'no skills'}
  ${relChips(s,c.name)}
  <details data-k="p:${esc(c.name)}"><summary>${esc(c.personality)}</summary>${c.traits?'Disposition: '+Object.entries(c.traits).map(([k,v])=>k+' '+v).join(', ')+'<br>':''}Secret: ${esc(c.secret)}<br>Fear: ${esc(c.fear)}<br>Want: ${esc(c.want)}</details></div>`).join('')).join('');
 const html=h;if($('valley').dataset.html!==html){$('valley').innerHTML=html;$('valley').dataset.html=html;$('valley').querySelectorAll('details').forEach(d=>{if(wasOpen.has(d.dataset.k))d.open=true});$('valley').scrollTop=scroll;$('valley').querySelectorAll('.rel').forEach(ch=>ch.onclick=e=>{e.stopPropagation();showWhy(ch.dataset.a,ch.dataset.b)})}}
function renderTerms(s){if(!s.terms.length){$('terms').innerHTML='<div class="empty">Terminals appear after Start.</div>';termKey='';return}if(!wantTerms())return;
 const key=s.id+':'+s.terms.length;if(termKey!==key){termKey=key;$('terms').innerHTML=s.terms.map((t,i)=>`<div class="term" id="t${i}"><div class="tb"><span class="nm"></span><span class="st"></span></div><pre></pre></div>`).join('')}
 s.terms.forEach((t,i)=>{const el=$('t'+i);if(!el)return;const seat=s.seats[i]||{};el.style.setProperty('--c',seat.color||'#888');el.classList.toggle('speaking',t.state==='speaking');
  el.querySelector('.nm').innerHTML=`<b>${esc(seat.name)}</b> <span style="color:var(--faint)">${esc((seat.provider||'')+' · '+(seat.model||''))}</span>`;el.querySelector('.st').textContent=t.state==='speaking'?'thinking':'';
  const pre=el.querySelector('pre');const atB=pre.scrollHeight-pre.scrollTop-pre.clientHeight<40;if(pre.dataset.count!=t.count&&t.lines.length){pre.textContent=t.lines.join('\n');pre.dataset.count=t.count;if(atB)pre.scrollTop=pre.scrollHeight}else if(!pre.textContent)pre.textContent='No live output yet.'})}
function renderRail(s){const live=new Set(s.live||[]);$('railCount').textContent=s.games.length;
 $('hlist').innerHTML=s.games.map(g=>`<div class="hitem ${g.id===s.id?'on':''}" data-id="${g.id}"><div class="t"><span>${live.has(g.id)?'<span class="livedot"></span>':''}${esc(g.title)}</span><button class="del" data-id="${g.id}" title="Delete">&times;</button></div><div class="m">${esc(g.created.replace('T',' '))} · day ${g.day} · ${esc(STATUS[g.status]||g.status)}</div></div>`).join('');
 document.querySelectorAll('.hitem').forEach(d=>d.onclick=async e=>{if(e.target.classList.contains('del')){if(confirm('Delete this game?'))render(await api('/game/delete',{id:e.target.dataset.id}));return}S=null;termKey='';render(await api('/game/open',{id:d.dataset.id}));if(mobile())showTab('map')})}
function render(s){const first=!S||S.id!==s.id;if(first){T=[];lastTurn=-1}mergeTranscript(s);S=s;providers=s.providers;
 const busy=s.status==='running';const started=s.created||s.transcript.length>0||busy||s.status==='paused';
 $('hdrTitle').textContent=s.title||'';const who=s.current?s.current.split(', '):[];$('statusText').innerHTML=s.current?(who.length>2?`<b>${who.length} people</b> are speaking`:`<b>${esc(s.current)}</b> ${who.length>1?'are':'is'} speaking`):`Day ${s.day} · ${STATUS[s.status]||s.status}`;$('status').classList.toggle('live',busy);
 $('start').textContent=s.status==='paused'?'Resume':(started?(s.status==='done'?'Continue (6 more days)':'Continue'):'Start');$('start').style.display=busy?'none':'';$('pause').style.display=busy?'':'none';$('stop').disabled=!busy&&s.status!=='paused';
 $('start2').style.display=started?'none':'';$('sayBtn').disabled=!busy;
 if(first||!editing)renderSetup(s);renderRail(s);
 if(!mobile()){$('setup').style.display=started?'none':'block';$('centerTabs').style.display=started?'':'none';$('map').classList.toggle('on',started&&centerTab==='map');$('chron').style.display=started&&centerTab==='chron'?'block':'none';$('composer').style.display=started?'':'none'}
 if(started)MapView.render(s);
 $('making').style.display=(busy&&!s.created)?'flex':'none';
 if(busy&&!s.created){const drawing=s.map_source==='generated'&&!s.map_generated;$('makingHead').textContent=drawing?'The map is being drawn from your description':'The World is making the valley';$('makingNote').textContent=drawing?'Places, paths, things, and names come from the map model first. Then the World rolls the people. Watch the World\'s terminal on the right.':'Rolling twenty lives, secrets, and grudges. This takes a minute or two. Watch the World\'s terminal on the right.'}
 if($('settings').classList.contains('open'))mapInfo(s);
 $('chronEmpty').style.display=s.transcript.length?'none':'block';
 const msgHtml=e=>`<div class="msg ${e.kind}${/^\s*WHISPER\s+@/im.test(e.text)?' whisper':''}${e.kind==='convener'&&/@[A-Za-z]/.test(e.text)?' private':''}" style="${e.color?'--c:'+esc(e.color):''}"><div class="hd"><span class="who">${esc(e.speaker)}</span><span class="meta">day ${e.day??0}${e.place?' · '+esc(e.place):''} · ${e.time}</span></div><div class="body">${rich(e.text)}</div></div>`;
 const have=$('msgs').children.length;
 if(first||have>s.transcript.length){$('msgs').innerHTML=s.transcript.map(msgHtml).join('');$('chron').scrollTop=$('chron').scrollHeight}
 else if(have<s.transcript.length){const atB=$('chron').scrollHeight-$('chron').scrollTop-$('chron').clientHeight<120;$('msgs').insertAdjacentHTML('beforeend',s.transcript.slice(have).map(msgHtml).join(''));if(atB)$('chron').scrollTop=$('chron').scrollHeight}
 $('typing').style.display=s.current?'block':'none';$('typing').textContent=s.current?(who.length>3?who.length+' people are':s.current+(who.length>1?' are':' is'))+' composing':'';
 renderValley(s);renderTerms(s)}
function showTab(t){['map','chron','side','rail','setup'].forEach(id=>$(id).classList.toggle('on',id===t));document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));if(mobile()){$('centerTabs').style.display='none';$('composer').style.display=t==='chron'?'':'none';$('chron').style.display=t==='chron'?'block':'none';$('setup').style.display=t==='setup'?'block':'none';$('map').style.display=t==='map'?'block':'none'}}
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>showTab(b.dataset.t));if(mobile())showTab('map');
document.querySelectorAll('#centerTabs button').forEach(b=>b.onclick=()=>{centerTab=b.dataset.c;document.querySelectorAll('#centerTabs button').forEach(x=>x.classList.toggle('on',x===b));if(S)render(S)});
document.querySelectorAll('#side .tabs button').forEach(b=>b.onclick=async()=>{sideTab=b.dataset.t;if(sideTab==='terms'){try{render(await api('/state?since='+lastTurn+'&terms=1'))}catch(e){}}document.querySelectorAll('#side .tabs button').forEach(x=>x.classList.toggle('on',x===b));$('valley').classList.toggle('on',sideTab==='valley');$('terms').classList.toggle('on',sideTab==='terms')});
$('railBtn').onclick=()=>document.body.classList.toggle('norail');$('expBtn').onclick=e=>{e.stopPropagation();$('expMenu').classList.toggle('open')};document.addEventListener('click',e=>{if(!$('expMenu').contains(e.target))$('expMenu').classList.remove('open')});document.querySelectorAll('#expMenu .list button').forEach(b=>b.onclick=()=>{$('expMenu').classList.remove('open');window.location='/export?what='+b.dataset.w});$('ppClose').onclick=e=>{e.stopPropagation();MapView.close()};$('sideBtn').onclick=()=>document.body.classList.toggle('noside');
async function save(){return render(await api('/config',{title:$('title').value,world_text:$('world_text').value,players:+$('players').value,max_days:+$('max_days').value,max_minutes:+($('max_minutes').value||0),repo:$('repo').value,
 drama:+$('drama').value,world_model:modelVal('wm'),model_a:modelVal('ma'),model_b:modelVal('mb'),map_source:$('map_source').value,map_model:mapModelVal()}))}
function mapModelVal(){const v=modelVal('mm'),w=modelVal('wm');return (v.provider===w.provider&&v.model===w.model)?null:v}
$('map_source').onchange=()=>{$('mapModelRow').style.display=$('map_source').value==='generated'?'':'none';save()};
$('drama').oninput=()=>{$('dramaNote').textContent=$('drama').value+' · '+DRAMA[+$('drama').value]};$('drama').onchange=save;
['title','world_text','players','max_days','max_minutes','repo'].forEach(id=>{const el=$(id);el.onfocus=()=>editing=true;el.onblur=()=>{editing=false;save()}});
['wm','ma','mb','mm'].forEach(p=>{$(p+'_p').onchange=()=>{const ms=(providers[$(p+'_p').value]||{models:['']}).models.concat(['Custom...']);fillSel($(p+'_m'),ms,ms[0]);$(p+'_c').style.display='none';save()};$(p+'_m').onchange=()=>{const cu=$(p+'_m').value==='Custom...';$(p+'_c').style.display=cu?'':'none';if(cu){editing=true;$(p+'_c').focus()}else save()};$(p+'_c').onfocus=()=>editing=true;$(p+'_c').onblur=()=>{editing=false;save()}});
$('start').onclick=async()=>{if(!(S&&S.created))await save();render(await api('/start',{}));if(mobile())showTab('map')};$('start2').onclick=()=>$('start').click();
$('pause').onclick=async()=>render(await api('/pause',{}));$('stop').onclick=async()=>{if(!confirm('Stop the year here? You can continue it later.'))return;$('statusText').textContent='Stopping...';render(await api('/stop',{}))};
$('newGame').onclick=async()=>{S=null;termKey='';render(await api('/game/new',{}));if(mobile())showTab('setup')};
$('quit').onclick=async()=>{if(!confirm('Quit Terraceilia? Every CLI it started is killed. Games are kept.'))return;try{await api('/shutdown',{})}catch(e){}document.body.innerHTML='<div style="padding:40px;color:#8B8B94">Terraceilia is closed.</div>'};
$('sayBtn').onclick=async()=>{const t=$('sayText').value.trim();if(!t)return;$('sayText').value='';hlSync();render(await api('/say',{text:t}))};// ---------- @ mentions: picker, colors in the box, private delivery
let acItems=[],acIdx=0,acStart=-1;
function people(){return (S&&S.characters||[]).filter(c=>c.alive&&!c.banished)}
function acClose(){$('ac').classList.remove('open');acItems=[]}
function acRender(){$('ac').innerHTML=acItems.map((x,i)=>`<div class="${i===acIdx?'on':''}" data-i="${i}"><span class="dot" style="background:${esc(seatColor(x.name))}"></span><span>${esc(x.name)}</span><small>${esc(x.trade)} · ${esc(x.location)}</small></div>`).join('');
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
let pk={path:''};async function openPk(p){const d=await api('/ls?path='+encodeURIComponent(p||$('repo').value));pk=d;$('pkPath').value=d.path;const sep=d.path.includes('\\')?'\\':'/';const base=d.path.replace(/[\\/]$/,'');
 $('pkList').innerHTML=d.drives.map(x=>`<li data-p="${esc(x)}">${esc(x)}</li>`).join('')+d.dirs.map(x=>`<li data-p="${esc(base+sep+x)}">${esc(x)}</li>`).join('');document.querySelectorAll('#pkList li').forEach(li=>li.onclick=()=>openPk(li.dataset.p));$('picker').style.display='flex'}
$('browse').onclick=()=>openPk();$('pkUp').onclick=()=>pk.parent&&openPk(pk.parent);$('pkPath').onchange=e=>openPk(e.target.value);$('pkCancel').onclick=()=>$('picker').style.display='none';$('pkUse').onclick=async()=>{$('repo').value=pk.path;$('picker').style.display='none';await save()};
function wantTerms(){return (sideTab==='terms'&&!document.body.classList.contains('noside'))||(mobile()&&$('side').classList.contains('on')&&sideTab==='terms')}
(async function poll(){try{render(await api('/state?since='+(S?lastTurn:-1)+'&terms='+(wantTerms()?1:0)))}catch(e){}setTimeout(poll,1500)})();

window.App={render,api};

// ---------- settings sheet: game + people, editable live
let sTab='game';
function modelPick(pfx,val,selP,selM,inpC){fillSel(selP,Object.keys(providers),val.provider);const ms=(providers[val.provider]||{models:[]}).models.concat(['Custom...']);const known=ms.includes(val.model);fillSel(selM,ms,known?val.model:'Custom...');inpC.style.display=known?'none':'';if(!known)inpC.value=val.model;
 selP.onchange=()=>{const m2=(providers[selP.value]||{models:['']}).models.concat(['Custom...']);fillSel(selM,m2,m2[0]);inpC.style.display='none'};selM.onchange=()=>{inpC.style.display=selM.value==='Custom...'?'':'none';if(selM.value==='Custom...')inpC.focus()}}
function pickVal(selP,selM,inpC){const m=selM.value;return {provider:selP.value,model:m==='Custom...'?inpC.value.trim():m}}
function openSettings(){if(!S)return;renderConn(S,$('connList'));$('g_title').value=S.title||'';$('g_world').value=S.world_text||'';$('g_days').value=S.max_days;$('g_mins').value=S.max_minutes||'';$('g_drama').value=S.drama??6;$('g_dramaNote').textContent=$('g_drama').value+' · '+DRAMA[+$('g_drama').value];$('g_drama').oninput=()=>{$('g_dramaNote').textContent=$('g_drama').value+' · '+DRAMA[+$('g_drama').value]};modelPick('g',S.world_model,$('g_wp'),$('g_wm'),$('g_wc'));
 $('g_map_source').value=S.map_source||'builtin';modelPick('gm',S.map_model||S.world_model,$('g_mp'),$('g_mm'),$('g_mc'));$('g_map_source').onchange=()=>mapInfo(S);mapInfo(S);renderPeople(S);$('settings').classList.add('open')}
function mapInfo(s){const info=$('g_mapInfo');if(!s||!info)return;const gen=$('g_map_source').value==='generated';const fixed=!!(s.created||(s.characters&&s.characters.length));
 $('g_mapModelRow').style.display=gen?'':'none';[$('g_map_source'),$('g_mp'),$('g_mm'),$('g_mc')].forEach(x=>x.disabled=fixed);
 const names=Object.keys(s.map||{});let t;
 if(s.map_generating)t='Drawing a new map from the description. Watch the World\'s terminal.';
 else if(s.map_generated)t=`This game plays on ${s.map_name}, a map generated from the description: ${names.length} places (${names.join(', ')}).`;
 else if(s.map_source==='generated')t='A map will be generated from the description when you press Start, or now with the button.';
 else t='This game plays on the built-in valley of Terraceilia.';
 if(fixed)t+=' The map is fixed for this game.';info.textContent=t;
 const b=$('g_regen');b.style.display=(gen||s.map_source==='generated')?'':'none';b.disabled=!!(fixed||s.map_generating||s.status==='running'||!gen);b.textContent=s.map_generating?'Drawing...':(s.map_generated?'Regenerate the map':'Generate the map now')}
function renderPeople(s){const list=$('peopleList');const openNames=new Set([...list.querySelectorAll('.pe.open')].map(x=>x.dataset.name));
 list.innerHTML=s.characters.map(c=>{const seat=(s.seats||[]).find(x=>x.name===c.name)||{};return `<div class="pe ${openNames.has(c.name)?'open':''}" data-name="${esc(c.name)}" style="--c:${esc(seat.color||'#888')}"><div class="hd"><span><b>${esc(c.name)}</b> <span class="note">${esc(c.trade)} · ${esc(c.location)} · ${esc(seat.provider||'')} ${esc(seat.model||'')}${c.alive?'':' · dead'}${c.banished?' · banished':''}</span></span><span class="note">edit</span></div>
  <form onsubmit="return false">
   <div class="g"><div><label>Name</label><input name="new_name" value="${esc(c.name)}"></div><div><label>Trade</label><input name="trade" value="${esc(c.trade)}"></div></div>
   <div class="g"><div><label>Provider</label><select name="provider"></select></div><div><label>Model</label><select name="model"></select><input name="custom" placeholder="custom model" style="display:none;margin-top:4px"></div></div>
   <div class="g g4"><div><label>Strength</label><input name="str" type="number" value="${c.str}"></div><div><label>Speed</label><input name="spd" type="number" value="${c.spd}"></div><div><label>Health</label><input name="hp" type="number" value="${c.hp}"></div><div><label>Max health</label><input name="hp_max" type="number" value="${c.hp_max}"></div></div>
   <div class="g g4"><div><label>Gold</label><input name="gold" type="number" value="${c.gold}"></div><div><label>Location</label><select name="location">${(s.places||[]).map(p=>`<option ${p===c.location?'selected':''}>${esc(p)}</option>`).join('')}</select></div><div><label>Standing</label><select name="standing">${['unknown','respected','feared','pitied','hated','loved'].map(x=>`<option ${x===c.standing?'selected':''}>${x}</option>`).join('')}</select></div><div><label>State</label><select name="state"><option value="alive" ${c.alive&&!c.banished?'selected':''}>alive</option><option value="banished" ${c.banished?'selected':''}>banished</option><option value="dead" ${!c.alive?'selected':''}>dead</option></select></div></div>
   <div class="g g3">${[['warmth','Warmth','cruel','kind'],['temper','Temper','calm','hot'],['honesty','Honesty','liar','honest'],['greed','Greed','giving','grasping'],['courage','Courage','coward','reckless'],['tongue','Tongue','crude','eloquent'],['desire','Desire','chaste','wanton'],['piety','Piety','godless','devout'],['ambition','Ambition','content','hungry'],['loyalty','Loyalty','turncoat','faithful'],['cunning','Cunning','simple','scheming'],['drink','Drink','sober','drunkard']].map(([k,l,lo,hi])=>`<div><label>${l}</label><select name="t_${k}">${[1,2,3,4,5].map(v=>`<option value="${v}" ${((c.traits||{})[k]||3)===v?'selected':''}>${v} · ${v===1?lo:v===5?hi:v===3?'middling':v===2?'leans '+lo:'leans '+hi}</option>`).join('')}</select></div>`).join('')}</div>
   <div class="g"><div><label>Personality</label><textarea name="personality">${esc(c.personality)}</textarea></div><div><label>Secret</label><textarea name="secret">${esc(c.secret)}</textarea></div></div>
   <div class="g"><div><label>Fear</label><textarea name="fear">${esc(c.fear)}</textarea></div><div><label>Want</label><textarea name="want">${esc(c.want)}</textarea></div></div>
   <div class="row"><button class="primary sv">Save ${esc(c.name)}</button><span class="note st"></span></div>
  </form>
  <details class="reledit"><summary>Ties: how ${esc(c.name)} feels about others (feeling and trust, -5 to 5)</summary><div class="rtable">${s.characters.filter(o=>o.name!==c.name).map(o=>{const r=((s.relations||{})[c.name]||{})[o.name]||{type:'none',feeling:0,trust:0};return `<div class="rrow" data-b="${esc(o.name)}"><b>${esc(o.name)}</b><select class="rt">${['none','spouse','lover','kin','friend','rival','enemy','creditor','debtor','master','servant'].map(t=>`<option ${t===r.type?'selected':''}>${t}</option>`).join('')}</select><label>feel <input class="rf" type="number" min="-5" max="5" value="${r.feeling}"></label><label>trust <input class="rr" type="number" min="-5" max="5" value="${r.trust}"></label><label title="also set the same the other way"><input class="rm" type="checkbox"> both ways</label><button class="btn rs">Set</button></div>`}).join('')}</div></details></div>`}).join('');
 list.querySelectorAll('.pe').forEach(pe=>{const name=pe.dataset.name;const c=s.characters.find(x=>x.name===name);const seat=(s.seats||[]).find(x=>x.name===name)||{provider:Object.keys(providers)[0],model:''};
  pe.querySelector('.hd').onclick=()=>pe.classList.toggle('open');const f=pe.querySelector('form');
  modelPick('p',seat,f.provider,f.model,f.custom);
  pe.querySelector('.sv').onclick=async()=>{const st=f.state.value;const d={name,new_name:f.new_name.value,trade:f.trade.value,str:+f.str.value,spd:+f.spd.value,hp:+f.hp.value,hp_max:+f.hp_max.value,gold:+f.gold.value,location:f.location.value,standing:f.standing.value,personality:f.personality.value,secret:f.secret.value,fear:f.fear.value,want:f.want.value,traits:Object.fromEntries(['warmth','temper','honesty','greed','courage','tongue','desire','piety','ambition','loyalty','cunning','drink'].map(k=>[k,+f['t_'+k].value])),...pickVal(f.provider,f.model,f.custom)};
   if(st==='dead')d.hp=0;if(st==='banished')d.banished=true;if(st==='alive'){d.banished=false;d.alive=true;if(d.hp<=0)d.hp=1}
   const r=await App.api('/edit/character',d);pe.querySelector('.st').textContent=r.last_god||'saved';App.render(r);renderPeople(r)};
  pe.querySelectorAll('.rrow .rs').forEach(btn=>btn.onclick=async()=>{const row=btn.closest('.rrow');const r=await App.api('/edit/relation',{a:name,b:row.dataset.b,type:row.querySelector('.rt').value,feeling:+row.querySelector('.rf').value,trust:+row.querySelector('.rr').value,mutual:row.querySelector('.rm').checked});btn.textContent='Set ✓';setTimeout(()=>btn.textContent='Set',1200);App.render(r)})})}
$('gearBtn').onclick=openSettings;$('settingsClose').onclick=()=>$('settings').classList.remove('open');
document.querySelectorAll('.stabs button').forEach(b=>b.onclick=()=>{sTab=b.dataset.s;document.querySelectorAll('.stabs button').forEach(x=>x.classList.toggle('on',x===b));$('sGame').style.display=sTab==='game'?'':'none';$('sPeople').style.display=sTab==='people'?'':'none';$('sConn').style.display=sTab==='conn'?'':'none';if(sTab==='conn')renderConn(S,$('connList'))});
function gMapModelVal(){const v=pickVal($('g_mp'),$('g_mm'),$('g_mc')),w=pickVal($('g_wp'),$('g_wm'),$('g_wc'));return (v.provider===w.provider&&v.model===w.model)?null:v}
async function saveGame(){const r=await App.api('/edit/game',{title:$('g_title').value,world_text:$('g_world').value,max_days:+$('g_days').value,max_minutes:+($('g_mins').value||0),drama:+$('g_drama').value,world_model:pickVal($('g_wp'),$('g_wm'),$('g_wc')),map_source:$('g_map_source').value,map_model:gMapModelVal()});$('g_state').textContent='Saved '+new Date().toLocaleTimeString();App.render(r);mapInfo(S)}
$('g_save').onclick=saveGame;
$('g_regen').onclick=async()=>{$('g_regen').disabled=true;$('g_regen').textContent='Drawing...';await saveGame();const r=await App.api('/map/regenerate',{});$('g_state').textContent=r.last_god||'';App.render(r);mapInfo(S)};
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('settings').classList.remove('open')});

// ---------- why does A feel that way about B
function showWhy(a,b){const r=((S.relations||{})[a]||{})[b];if(!r)return;const why=(r.why||[]).slice().reverse();
 const TRUST=['would knife in the dark','distrusts utterly','distrusts','is wary of','is unsure of','neither trusts nor distrusts','trusts a little','trusts','trusts well','trusts with secrets','trusts with their life'];
 let box=$('whyBox');if(!box){box=document.createElement('div');box.id='whyBox';document.body.appendChild(box);box.onclick=e=>{if(e.target===box)box.style.display='none'}}
 box.innerHTML=`<div class="whyPanel"><h3>${esc(a)} → ${esc(b)} <button class="icon" id="whyClose">&#10005;</button></h3>
  <div class="note" style="margin-bottom:8px">${esc(a)} ${FEEL[r.feeling+5]} ${esc(b)} (${r.feeling>=0?'+':''}${r.feeling}) and ${TRUST[r.trust+5]} them (${r.trust>=0?'+':''}${r.trust})${r.type!=='none'?' · '+esc(r.type):''}</div>
  ${why.length?why.map(w=>`<div class="whyRow"><span class="note">day ${w.day}</span><span>${esc(w.note)}</span><span class="note">${w.feeling>=0?'+':''}${w.feeling} / ${w.trust>=0?'+':''}${w.trust}</span></div>`).join(''):'<div class="note">No history recorded yet.</div>'}
  <div class="row" style="margin-top:10px"><button class="btn" id="whyRev">See it the other way</button></div></div>`;
 box.style.display='flex';$('whyClose').onclick=()=>box.style.display='none';$('whyRev').onclick=()=>showWhy(b,a)}

// ---------- connections: install, sign in, test each CLI
const testing={};
function renderConn(s,root){if(!root||!s)return;const os=s.os||'mac';const used=new Set([s.world_model.provider,s.model_a.provider,s.model_b.provider]);
 root.innerHTML=Object.entries(s.providers).map(([k,p])=>{const h=p.hints||{};const t=p.test;const st=!p.installed?'bad':t?(t.ok?'ok':'bad'):'unk';const label=!p.installed?'not installed':t?(t.ok?`works · replied in ${t.seconds}s`:`failed`):(p.version?p.version+' · untested':'installed · untested');
  return `<div class="conn" data-p="${esc(k)}"><div class="hd"><span><b>${esc(k)}</b>${used.has(k)?' <span class="note">· used by this game</span>':''}</span><span class="st ${st}">${esc(label)}</span><button class="btn tst" ${testing[k]?'disabled':''}>${testing[k]?'Testing…':'Test'}</button></div>
   ${!p.installed?`<div class="cmd"><span class="note">Install</span><code>${esc(os==='win'?h.install_win:h.install_mac)}</code><button class="btn sm cp2">Copy</button></div>`:''}
   <div class="cmd"><span class="note">Sign in</span><code>${esc(h.login||'')}</code><button class="btn sm cp2">Copy</button>${h.docs?`<a class="note" href="${esc(h.docs)}" target="_blank">docs</a>`:''}</div>
   ${t&&!t.ok?`<div class="res">${esc(t.detail||'')}</div>`:''}</div>`}).join('');
 root.querySelectorAll('.cp2').forEach(b=>b.onclick=async()=>{const c=b.parentElement.querySelector('code').textContent;try{await navigator.clipboard.writeText(c);b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1200)}catch(e){prompt('Copy this',c)}});
 root.querySelectorAll('.tst').forEach(b=>b.onclick=async()=>{const k=b.closest('.conn').dataset.p;testing[k]=true;renderConn(S,root);const model=k===S.world_model.provider?S.world_model.model:k===S.model_a.provider?S.model_a.model:k===S.model_b.provider?S.model_b.model:'';const r=await App.api('/provider/test',{provider:k,model});testing[k]=false;S=r;renderConn(S,root)})}
