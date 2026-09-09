// Opens the served app in a private headless Chrome at each size given and reports, as one JSON line per size, whether every
// place label and every token sits inside the map's box, the box sits between the tabs and the fate box with the hint line
// below it, and the page does not scroll. Run by tests/test_desktop_fit.py.
//   node map_fit_check.js <url> <chrome.exe> 1366x768 1920x1080 ...
const {spawn} = require('child_process');
const [url, chromePath, ...sizes] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const CHECK = `(()=>{
  const R=e=>e.getBoundingClientRect();const box=R(document.getElementById('map'));
  const inside=r=>r.width>0&&r.left>=box.left-0.5&&r.right<=box.right+0.5&&r.top>=box.top-0.5&&r.bottom<=box.bottom+0.5;
  const labels=[...document.querySelectorAll('.node text.nm')].map(e=>({n:e.textContent,ok:inside(R(e))}));
  const toks=[...document.querySelectorAll('.tok')].map(e=>({n:e.dataset.name,ok:inside(R(e))}));
  const tabs=R(document.getElementById('centerTabs')),hint=R(document.getElementById('mapHint')),fate=R(document.getElementById('composer'));
  const de=document.documentElement;
  return JSON.stringify({w:innerWidth,h:innerHeight,box:[box.top,box.bottom,box.left,box.right],tabsBottom:tabs.bottom,hint:[hint.top,hint.bottom,hint.height,getComputedStyle(document.getElementById('mapHint')).display],fateTop:fate.top,
    labels,toks,badLabels:labels.filter(x=>!x.ok).map(x=>x.n),badToks:toks.filter(x=>!x.ok).map(x=>x.n),
    scroll:[de.scrollWidth,de.clientWidth,de.scrollHeight,de.clientHeight,scrollX,scrollY],view:MapView.view().k})})()`;
(async () => {
  for (const sz of sizes) {
    const [w, h] = sz.split('x').map(Number); const port = 9400 + Math.floor(Math.random() * 300);
    const chrome = spawn(chromePath, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${port}`, '--no-first-run', '--no-default-browser-check',
      `--user-data-dir=${process.env.TEMP || '/tmp'}/terra-fitcheck-${process.pid}-${w}`, `--window-size=${w},${h}`, 'about:blank'], {stdio: 'ignore'});
    try {
      let list = null;
      for (let i = 0; i < 80 && !list; i++) { try { list = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch (e) { await sleep(250); } }
      if (!list) throw new Error('chrome did not open its debugging port');
      const page = list.find(t => t.type === 'page'); const ws = new WebSocket(page.webSocketDebuggerUrl);
      let id = 0; const pending = {};
      ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending[m.id]) { pending[m.id](m.result || m.error); delete pending[m.id]; } };
      const send = (method, params = {}) => new Promise(r => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({id: i, method, params})); });
      await new Promise(r => ws.onopen = r);
      await send('Emulation.setDeviceMetricsOverride', {width: w, height: h, deviceScaleFactor: 1, mobile: false});
      await send('Runtime.enable'); await send('Page.enable'); await send('Page.navigate', {url}); await sleep(5000);
      const ev = async () => { const r = await send('Runtime.evaluate', {expression: CHECK, returnByValue: true}); return JSON.parse(r.result.value); };
      const first = await ev();
      // the left rail closes: the box widens and the fit is recomputed
      await send('Runtime.evaluate', {expression: "document.getElementById('railBtn').click();'ok'", returnByValue: true}); await sleep(700);
      const second = await ev();
      console.log(JSON.stringify({size: sz, open: first, railClosed: second}));
      ws.close();
    } finally { chrome.kill(); }
  }
})().catch(e => { console.error(e); process.exit(1); });
