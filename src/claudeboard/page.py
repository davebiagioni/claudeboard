"""The static HTML/CSS/JS page served at `/`."""

PAGE = b"""<!doctype html>
<meta charset=utf-8>
<title>claudeboard</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
html,body{height:100%}
body{background:#0b0b0d;color:#d4d4d4;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0;padding:0;display:grid;grid-template-rows:auto 1fr;grid-template-columns:340px 1fr;column-gap:0}
header{grid-column:1/-1;display:flex;align-items:baseline;gap:16px;padding:18px 24px 14px;border-bottom:1px solid #1a1a1e}
h1{font-size:12px;font-weight:600;letter-spacing:.3em;color:#777;margin:0}
.meta{color:#444;font-size:11px;margin-left:auto}
aside{border-right:1px solid #1a1a1e;overflow-y:auto;min-height:0;padding:6px 0}
main{overflow-y:auto;min-height:0;padding:20px 28px 40px}
.s{border-left:2px solid #2a2a2e;padding:7px 14px 7px 12px;cursor:pointer;display:grid;grid-template-columns:38px 1fr auto;column-gap:10px;row-gap:1px;align-items:baseline}
.s:hover{background:#131316}
.s.busy{border-left-color:#4ade80}
.s.idle{border-left-color:#fbbf24}
.s.dead{opacity:.45}
.s.sel{background:#16161a}
.st{text-transform:uppercase;font-size:10px;letter-spacing:.15em;color:#666}
.s.busy .st{color:#4ade80}.s.idle .st{color:#fbbf24}
.slug{color:#e5e5e5;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.s.dead .slug{color:#888}
.title{grid-column:2/-1;color:#888;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.age{color:#555;font-size:11px;text-align:right;white-space:nowrap}
.prompt{grid-column:2/-1;color:#7dd3fc;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.s.dead .prompt{color:#555}
.dethead .slug{color:#e5e5e5;font-size:14px}
.dethead .ttl{color:#888;font-size:12px}
.detprompt{flex-basis:100%;color:#7dd3fc;font-size:13px;line-height:1.5;margin-top:8px;white-space:pre-wrap;word-break:break-word}
.dethead{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #1a1a1e}
.dethead .ttl{color:#e5e5e5;font-size:15px;flex:1;min-width:0;word-break:break-word}
.dethead .cwd{color:#7dd3fc;font-size:11px}
.dethead .br{color:#a78bfa;font-size:11px}
.dethead .age{color:#555;font-size:11px}
.dethead .st{font-size:10px}
.section{margin:18px 0}
.label{color:#555;font-size:10px;text-transform:uppercase;letter-spacing:.18em;margin-bottom:6px}
.tabnav{display:flex;gap:22px;border-bottom:1px solid #1a1a1e;margin:18px 0 0}
.tab{color:#555;font-size:10px;letter-spacing:.18em;text-transform:uppercase;padding:10px 0;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;user-select:none}
.tab:hover{color:#aaa}
.tab.active{color:#ddd;border-bottom-color:#c4b5fd}
.tabpanel{padding-top:18px}
.btn{background:#1a1a1f;border:1px solid #2a2a30;color:#aaa;font:inherit;font-size:11px;padding:4px 10px;border-radius:3px;cursor:pointer}
.btn:hover{background:#23232a;color:#ddd}
.btn:disabled{opacity:.5;cursor:wait}
.summary{color:#ddd;white-space:pre-wrap;line-height:1.6;background:#111114;padding:10px 12px;border-radius:3px;border-left:2px solid #c4b5fd}
.err{color:#f87171;font-size:11px}
.statgrid{display:flex;gap:24px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:2px}
.stat .v{color:#ddd;font-size:14px}
.stat .k{color:#555;font-size:10px;text-transform:uppercase;letter-spacing:.12em}
.filerow{display:flex;justify-content:space-between;gap:14px;font-size:11px;padding:2px 0}
.filerow .filepath{color:#7dd3fc;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.filerow .filecounts{color:#888;font-size:10px;letter-spacing:.06em;white-space:nowrap}
.toolrow{display:flex;align-items:center;gap:10px;margin:3px 0;font-size:11px}
.toolrow .name{color:#fbbf24;min-width:90px}
.toolrow .bar{height:8px;background:#fbbf2444;border-radius:1px}
.toolrow .n{color:#888;min-width:36px;text-align:right}
.commit{display:flex;gap:10px;align-items:baseline;font-size:11px;margin:2px 0}
.commit .sha{color:#555;font-family:inherit;min-width:54px}
.commit .msg{color:#bbb;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.commit .add{color:#4ade80;min-width:36px;text-align:right}
.commit .rm{color:#f87171;min-width:36px;text-align:right}
.gtot{color:#888;font-size:11px;margin-top:6px}
.m{margin:8px 0;display:flex;gap:10px;align-items:flex-start}
.m .role{color:#555;font-size:10px;text-transform:uppercase;letter-spacing:.1em;min-width:48px;padding-top:2px}
.m.user .role{color:#7dd3fc}
.m.assistant .role{color:#c4b5fd}
.m .body{flex:1;white-space:pre-wrap;color:#bbb;word-break:break-word}
.empty{color:#444;text-align:center;padding:40px 20px;font-size:11px}
.muted{color:#555;font-size:11px}
.id{color:#333;font-size:10px}
.placeholder{color:#444;text-align:center;padding:80px 20px;font-size:11px;letter-spacing:.18em;text-transform:uppercase}
</style>
<header><h1>CLAUDEBOARD</h1><span class=meta id=meta></span></header>
<aside id=list></aside>
<main id=main><div class=placeholder>select a session</div></main>
<script>
const fmtAge = s => s<60?`${s|0}s`:s<3600?`${s/60|0}m`:s<86400?`${(s/3600).toFixed(1)}h`:`${(s/86400).toFixed(1)}d`;
const fmtN = n => { n = n|0; if (n<1000) return ''+n; if (n<1e6) return (n/1e3).toFixed(n<1e4?1:0)+'K'; if (n<1e9) return (n/1e6).toFixed(n<1e7?1:0)+'M'; return (n/1e9).toFixed(1)+'B'; };
const el = (tag, cls, txt) => { const n = document.createElement(tag); if(cls) n.className=cls; if(txt!=null) n.textContent=txt; return n; };
const svg = (tag, attrs) => { const n = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
let selected = null;
let activeTab = 'transcript';
const rows = new Map();
const detailNodes = new Map();
const detailMtime = new Map();

function setTab(tab){
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tabpanel').forEach(p => { p.style.display = p.dataset.tab === tab ? '' : 'none'; });
}

function makeRow(s){
  const c = el('div');
  c.dataset.id = s.id;
  c._st = el('span','st');
  c._slug = el('span','slug');
  c._age = el('span','age');
  c._title = el('span','title');
  c._prompt = el('span','prompt');
  c.append(c._st, c._slug, c._age, c._title, c._prompt);
  c.onclick = () => selectSession(s.id);
  return c;
}

function updateRow(c, s){
  const cls = 's ' + s.status + (selected === s.id ? ' sel' : '');
  if (c.className !== cls) c.className = cls;
  if (c._st.textContent !== s.status) c._st.textContent = s.status;
  const headline = s.slug || s.title;
  if (c._slug.textContent !== headline) { c._slug.textContent = headline; c._slug.title = headline; }
  const sub = s.slug ? s.title : '';
  if (c._title.textContent !== sub) c._title.textContent = sub;
  c._title.style.display = sub ? '' : 'none';
  const a = fmtAge(s.age);
  if (c._age.textContent !== a) c._age.textContent = a;
  const p = s.last_user ? '> ' + s.last_user : '';
  if (c._prompt.textContent !== p) { c._prompt.textContent = p; c._prompt.title = s.last_user || ''; }
  c._prompt.style.display = p ? '' : 'none';
}

function statBlock(stats){
  const wrap = el('div','statgrid');
  const items = [
    ['msgs', stats.msgs], ['tools', stats.tools_total],
    ['in', fmtN(stats.in)], ['out', fmtN(stats.out)],
    ['cache R', fmtN(stats.cache_r)], ['cache W', fmtN(stats.cache_w)],
  ];
  for (const [k, v] of items) {
    const s = el('div','stat');
    s.append(el('div','v', String(v)));
    s.append(el('div','k', k));
    wrap.append(s);
  }
  return wrap;
}

function fmtDur(secs){
  if (secs < 60) return (secs|0) + 's';
  if (secs < 3600) return (secs/60|0) + 'm';
  if (secs < 86400) return (secs/3600).toFixed(1) + 'h';
  return (secs/86400).toFixed(1) + 'd';
}

function workBlock(d){
  const w = el('div');
  const strip = el('div','statgrid');
  const stat = (k, v) => { const x = el('div','stat'); x.append(el('div','v', String(v))); x.append(el('div','k', k)); return x; };
  strip.append(stat('cost', '$' + (d.cost || 0).toFixed(2)));
  if (d.time) {
    strip.append(stat('active', fmtDur(d.time.active)));
    strip.append(stat('idle', fmtDur(d.time.idle)));
    strip.append(stat('elapsed', fmtDur(d.time.elapsed)));
  }
  if (d.session_diff) {
    strip.append(stat('+', '+' + d.session_diff.add));
    strip.append(stat('-', '-' + d.session_diff.rm));
    strip.append(stat('files', d.session_diff.files));
  }
  w.append(strip);

  const fl = el('div','section');
  fl.append(el('div','label','files touched'));
  if (d.files && d.files.length) {
    const flist = el('div');
    for (const f of d.files) {
      const r = el('div','filerow');
      const counts = el('span','filecounts');
      const parts = [];
      if (f.edit) parts.push('E:' + f.edit);
      if (f.write) parts.push('W:' + f.write);
      if (f.read) parts.push('R:' + f.read);
      counts.textContent = parts.join('  ');
      r.append(el('span','filepath', f.path), counts);
      flist.append(r);
    }
    fl.append(flist);
  } else {
    fl.append(el('div','muted','no file operations'));
  }
  w.append(fl);

  const tw = el('div','section');
  tw.append(el('div','label','tools'));
  tw.append(toolBlock(d.tools || []));
  w.append(tw);
  return w;
}

function toolBlock(tools){
  if (!tools.length) return el('div','muted','no tool calls');
  const wrap = el('div');
  const max = tools[0][1];
  for (const [name, n] of tools) {
    const r = el('div','toolrow');
    r.append(el('span','name', name));
    const bar = el('span','bar');
    bar.style.width = (Math.round((n / max) * 280)) + 'px';
    r.append(bar);
    r.append(el('span','n', String(n)));
    wrap.append(r);
  }
  return wrap;
}

function gitBlock(g){
  if (!g) return el('div','muted','no cwd');
  if (g.error) return el('div','muted', g.error);
  if (!g.commits || !g.commits.length) return el('div','muted','no commits since session start');
  const wrap = el('div');
  for (const c of g.commits) {
    const r = el('div','commit');
    r.append(el('span','sha', c.sha));
    r.append(el('span','msg', c.msg));
    r.append(el('span','add', '+' + c.add));
    r.append(el('span','rm', '-' + c.rm));
    wrap.append(r);
  }
  wrap.append(el('div','gtot', `${g.n} commits  +${g.add} / -${g.rm}`));
  return wrap;
}

function transcriptBlock(msgs){
  if (!msgs.length) return el('div','empty','(no transcript)');
  const wrap = el('div');
  for (const m of msgs) {
    const r = el('div', 'm ' + m.role);
    r.append(el('div','role', m.role));
    r.append(el('div','body', m.text));
    wrap.append(r);
  }
  return wrap;
}

function section(label, body){
  const s = el('div','section');
  s.append(el('div','label', label));
  s.append(body);
  return s;
}

async function loadSummary(id, container, force){
  const btn = container.querySelector('.btn');
  if (btn) btn.disabled = true;
  const out = container.querySelector('.summary-body');
  out.replaceChildren(el('div','muted', force ? 'regenerating...' : 'generating...'));
  try {
    const r = await fetch('/summary/' + id, {method: force ? 'POST' : 'GET'});
    const d = await r.json();
    if (d.error) out.replaceChildren(el('div','err', d.error));
    else out.replaceChildren(el('div','summary', d.summary || '(empty)'));
  } catch (e) {
    out.replaceChildren(el('div','err', String(e)));
  }
  if (btn) btn.disabled = false;
}

function detailHeader(s){
  const h = el('div','dethead');
  if (s.slug) h.append(el('span','slug', s.slug));
  h.append(el('span','ttl', s.title));
  if (s.cwd) h.append(el('span','cwd', s.cwd));
  if (s.branch) h.append(el('span','br', s.branch));
  h.append(el('span','age', fmtAge(s.age)));
  if (s.last_user) {
    const p = el('div','detprompt', '> ' + s.last_user);
    h.append(p);
  }
  return h;
}

async function loadDetail(id){
  const node = detailNodes.get(id);
  if (!node) return;
  let d;
  try { d = await (await fetch('/session/' + id)).json(); }
  catch (e) { node.replaceChildren(el('div','err', String(e))); return; }

  const s = latest.find(x => x.id === id) || {};
  node.replaceChildren();
  node.append(detailHeader({...s, cwd: d.cwd || s.cwd || '', branch: d.branch || s.branch || ''}));

  const sumWrap = el('div');
  const sumHead = el('div');
  sumHead.style.display = 'flex'; sumHead.style.alignItems = 'baseline'; sumHead.style.gap = '10px';
  sumHead.append(el('div','label','summary'));
  const btn = el('button','btn','generate');
  btn.onclick = () => loadSummary(id, sumWrap, true);
  sumHead.append(btn);
  sumWrap.append(sumHead);
  const sumBody = el('div','summary-body');
  sumBody.append(el('div','muted','click generate to summarize via Sonnet'));
  sumWrap.append(sumBody);
  node.append(sumWrap);

  const tabs = [
    ['stats', 'stats', () => statBlock(d.stats)],
    ['work', 'work', () => workBlock(d)],
    ['git', 'git', () => gitBlock(d.git)],
    ['transcript', 'transcript', () => transcriptBlock(d.messages || [])],
  ];
  const nav = el('nav','tabnav');
  const panels = el('div');
  for (const [key, label, build] of tabs) {
    const t = el('span','tab', label);
    t.dataset.tab = key;
    if (key === activeTab) t.classList.add('active');
    t.onclick = () => setTab(key);
    nav.append(t);
    const p = el('div','tabpanel');
    p.dataset.tab = key;
    if (key !== activeTab) p.style.display = 'none';
    p.append(build());
    panels.append(p);
  }
  node.append(nav);
  node.append(panels);
}

function showDetail(id){
  const main = document.getElementById('main');
  if (!id) { main.replaceChildren(el('div','placeholder','select a session')); return; }
  let node = detailNodes.get(id);
  if (!node) {
    node = el('div');
    node.dataset.id = id;
    node.append(el('div','muted','loading...'));
    detailNodes.set(id, node);
    loadDetail(id);
    const s = latest.find(x => x.id === id);
    if (s) detailMtime.set(id, s.mtime);
  }
  main.replaceChildren(node);
}

function selectSession(id){
  if (selected === id) return;
  selected = id;
  activeTab = 'transcript';
  if (id) location.hash = id;
  render();
  showDetail(id);
}

window.addEventListener('hashchange', () => {
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && id !== selected) selectSession(id);
});

function render(){
  const list = document.getElementById('list');
  if (!latest.length) { list.replaceChildren(el('div','empty','no sessions')); return; }
  const want = new Set(latest.map(s => s.id));
  for (const [id, n] of rows) if (!want.has(id)) { n.remove(); rows.delete(id); }
  for (const id of detailNodes.keys()) if (!want.has(id)) { detailNodes.delete(id); detailMtime.delete(id); }

  let cursor = null;
  for (const s of latest) {
    let r = rows.get(s.id);
    if (!r) { r = makeRow(s); rows.set(s.id, r); }
    updateRow(r, s);
    const next = cursor ? cursor.nextSibling : list.firstChild;
    if (r !== next) list.insertBefore(r, next);
    cursor = r;
  }

  if (selected && !want.has(selected)) {
    selected = null;
    showDetail(null);
  }
  if (selected) {
    const s = latest.find(x => x.id === selected);
    if (s && detailMtime.get(selected) !== s.mtime) {
      detailMtime.set(selected, s.mtime);
      if (detailNodes.has(selected)) loadDetail(selected);
    }
  }
}

let latest = [];
async function tick(){
  latest = await (await fetch('/data.json')).json();
  document.getElementById('meta').textContent = `${latest.length} sessions / ${latest.filter(x=>x.status!='dead').length} active`;
  render();
}
async function init(){
  await tick();
  const hashId = decodeURIComponent(location.hash.slice(1));
  if (hashId && latest.find(s => s.id === hashId)) selectSession(hashId);
  else if (latest.length) selectSession(latest[0].id);
  setInterval(tick, 3000);
}
init();
</script>
"""
