#!/usr/bin/env python3
import json, os, time, glob, re, subprocess, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.expanduser("~/.claude/projects")
PORT = 8765
ID_RE = re.compile(r"^[0-9a-f-]{36}$")
SONNET = "claude-sonnet-4-6"
MAX_MSG_BYTES = 50000

_meta_cache = {}

def session_meta(path, mtime):
    hit = _meta_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    cwd = branch = ai_title = first_user = last_user = last_text = last_tool = last_role = ""
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not cwd and d.get("cwd"):
                    cwd = d["cwd"]
                if not branch and d.get("gitBranch"):
                    branch = d["gitBranch"]
                if d.get("type") == "ai-title" and not ai_title:
                    ai_title = d.get("aiTitle", "")
                m = d.get("message")
                if not isinstance(m, dict):
                    continue
                role = m.get("role", "")
                c = m.get("content")
                text = ""
                tool = ""
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    for b in c:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and not text:
                            text = b.get("text", "")
                        elif b.get("type") == "tool_use" and not tool:
                            tool = b.get("name", "")
                text = text.strip()
                if text.startswith("<"):
                    text = ""
                if not text and not tool:
                    continue
                if role == "user" and text:
                    if not first_user:
                        first_user = text
                    last_user = text
                    last_role = "user"
                    last_tool = ""
                    last_text = ""
                elif role == "assistant":
                    last_role = "assistant"
                    if tool:
                        last_tool = tool
                    if text:
                        last_text = text
                    if not text and tool:
                        last_text = ""
    except OSError:
        return None
    info = {
        "cwd": cwd, "branch": branch, "ai_title": ai_title,
        "first_user": first_user[:240], "last_user": last_user[:240],
        "last_text": last_text[:240], "last_tool": last_tool, "last_role": last_role,
    }
    _meta_cache[path] = (mtime, info)
    return info

def short_path(p):
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home):]
    return p

def scan():
    now = time.time()
    out = []
    for path in glob.glob(os.path.join(ROOT, "*", "*.jsonl")):
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        info = session_meta(path, st.st_mtime)
        if info is None:
            continue
        age = now - st.st_mtime
        status = "busy" if age < 60 else "idle" if age < 1800 else "dead"
        title = info["ai_title"] or info["first_user"] or "(untitled)"
        if info["last_role"] == "assistant" and info["last_tool"]:
            activity = "running " + info["last_tool"]
        elif info["last_role"] == "assistant" and info["last_text"]:
            activity = "replied: " + info["last_text"]
        elif info["last_role"] == "user":
            activity = "waiting: " + info["last_user"]
        else:
            activity = ""
        out.append({
            "id": os.path.basename(path)[:-6],
            "project": os.path.basename(os.path.dirname(path)),
            "cwd": short_path(info["cwd"]) if info["cwd"] else "",
            "branch": info["branch"], "status": status,
            "mtime": st.st_mtime, "age": age,
            "title": title, "activity": activity,
        })
    out.sort(key=lambda x: -x["mtime"])
    return out

def parse_session(path):
    in_t = out_t = cache_r = cache_w = 0
    tools = {}
    msgs = []
    spark = []
    cwd = branch = ""
    first_ts = None
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not cwd and d.get("cwd"):
                cwd = d["cwd"]
            if not branch and d.get("gitBranch"):
                branch = d["gitBranch"]
            ts = d.get("timestamp") or ""
            if ts and not first_ts:
                first_ts = ts
            m = d.get("message")
            if not isinstance(m, dict):
                continue
            role = m.get("role", "")
            u = m.get("usage")
            if isinstance(u, dict):
                in_t += u.get("input_tokens", 0) or 0
                out_t += u.get("output_tokens", 0) or 0
                cache_r += u.get("cache_read_input_tokens", 0) or 0
                cache_w += u.get("cache_creation_input_tokens", 0) or 0
                spark.append({"ts": ts, "out": u.get("output_tokens", 0) or 0})
            c = m.get("content")
            text = ""
            if isinstance(c, str):
                text = c
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        nm = b.get("name", "")
                        tools[nm] = tools.get(nm, 0) + 1
                    elif b.get("type") == "text" and not text:
                        text = b.get("text", "")
            text = text.strip()
            if text and not text.startswith("<"):
                msgs.append({"role": role, "text": text[:MAX_MSG_BYTES], "ts": ts})
    return {
        "cwd": cwd, "branch": branch, "first_ts": first_ts,
        "in": in_t, "out": out_t, "cache_r": cache_r, "cache_w": cache_w,
        "tools": tools, "msgs": msgs, "spark": spark,
    }

def git_activity(cwd, since):
    if not cwd or not os.path.isdir(cwd) or not since:
        return None
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--git-dir"],
                           capture_output=True, text=True, timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        return {"error": "git unavailable"}
    if r.returncode != 0:
        return {"error": "not a git repo"}
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "log", "--since", since,
             "--pretty=format:%h %s", "--numstat"],
            capture_output=True, text=True, timeout=3,
        )
    except subprocess.TimeoutExpired:
        return {"error": "git log timed out"}
    if r.returncode != 0:
        return {"error": r.stderr[:120].strip()}
    commits = []
    cur = None
    add = rm = 0
    for line in r.stdout.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        if "\t" in line:
            parts = line.split("\t", 2)
            if len(parts) >= 2 and cur is not None:
                try: a = int(parts[0])
                except ValueError: a = 0
                try: d = int(parts[1])
                except ValueError: d = 0
                cur["add"] += a; cur["rm"] += d
                add += a; rm += d
        else:
            if cur is not None:
                commits.append(cur)
            sha, _, msg = line.partition(" ")
            cur = {"sha": sha, "msg": msg, "add": 0, "rm": 0}
    if cur is not None:
        commits.append(cur)
    return {"commits": commits[:10], "add": add, "rm": rm, "n": len(commits)}

TURN_CHARS = 480
TURN_LIMIT = 60

def trim_turn(m):
    t = m["text"]
    if len(t) > TURN_CHARS:
        t = t[:TURN_CHARS].rstrip() + "..."
    return {"role": m["role"], "text": t, "ts": m["ts"]}

def detail(sid):
    for path in glob.glob(os.path.join(ROOT, "*", sid + ".jsonl")):
        s = parse_session(path)
        return {
            "id": sid,
            "cwd": short_path(s["cwd"]) if s["cwd"] else "",
            "branch": s["branch"],
            "stats": {
                "in": s["in"], "out": s["out"],
                "cache_r": s["cache_r"], "cache_w": s["cache_w"],
                "msgs": len(s["msgs"]),
                "tools_total": sum(s["tools"].values()),
            },
            "tools": sorted(s["tools"].items(), key=lambda x: -x[1]),
            "spark": s["spark"],
            "git": git_activity(s["cwd"], s["first_ts"]),
            "messages": [trim_turn(m) for m in s["msgs"][-TURN_LIMIT:]],
        }
    return None

def call_sonnet(prompt):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"error": "ANTHROPIC_API_KEY not set"}
    body = json.dumps({
        "model": SONNET,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"{e.code} {e.read().decode()[:200]}"}
    except urllib.error.URLError as e:
        return {"error": str(e)[:200]}
    text = ""
    for b in d.get("content", []):
        if b.get("type") == "text":
            text = b.get("text", "")
            break
    return {"text": text}

def summarize(sid):
    for path in glob.glob(os.path.join(ROOT, "*", sid + ".jsonl")):
        s = parse_session(path)
        msgs = s["msgs"]
        cache = path[:-6] + ".summary.json"
        if os.path.exists(cache):
            try:
                with open(cache) as fh:
                    c = json.load(fh)
                if c.get("msg_count") == len(msgs):
                    return c
            except (OSError, json.JSONDecodeError):
                pass
        if not msgs:
            return {"summary": "(no transcript)", "msg_count": 0}
        recent = msgs[-60:]
        transcript = "\n\n".join(
            f"[{m['role']}] {m['text'][:2500]}" for m in recent
        )
        prompt = (
            "Summarize what this Claude Code session is doing in 3-5 sentences. "
            "Focus on the user's goal, what's been accomplished, and what's in progress. "
            "Be concrete; reference filenames or commands where relevant. "
            "No preamble, no markdown headers.\n\n"
            f"--- TRANSCRIPT ---\n{transcript}"
        )
        r = call_sonnet(prompt)
        if "error" in r:
            return r
        out = {"msg_count": len(msgs), "summary": r["text"]}
        try:
            with open(cache, "w") as fh:
                json.dump(out, fh)
        except OSError:
            pass
        return out
    return None

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
.title{color:#e5e5e5;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.s.dead .title{color:#888}
.age{color:#555;font-size:11px;text-align:right;white-space:nowrap}
.activity{grid-column:2/-1;color:#666;font-size:10.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.activity.tool{color:#fbbf24}
.activity.wait{color:#7dd3fc}
.dethead{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #1a1a1e}
.dethead .ttl{color:#e5e5e5;font-size:15px;flex:1;min-width:0;word-break:break-word}
.dethead .cwd{color:#7dd3fc;font-size:11px}
.dethead .br{color:#a78bfa;font-size:11px}
.dethead .age{color:#555;font-size:11px}
.dethead .st{font-size:10px}
.section{margin:18px 0}
.label{color:#555;font-size:10px;text-transform:uppercase;letter-spacing:.18em;margin-bottom:6px}
.btn{background:#1a1a1f;border:1px solid #2a2a30;color:#aaa;font:inherit;font-size:11px;padding:4px 10px;border-radius:3px;cursor:pointer}
.btn:hover{background:#23232a;color:#ddd}
.btn:disabled{opacity:.5;cursor:wait}
.summary{color:#ddd;white-space:pre-wrap;line-height:1.6;background:#111114;padding:10px 12px;border-radius:3px;border-left:2px solid #c4b5fd}
.err{color:#f87171;font-size:11px}
.statgrid{display:flex;gap:24px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:2px}
.stat .v{color:#ddd;font-size:14px}
.stat .k{color:#555;font-size:10px;text-transform:uppercase;letter-spacing:.12em}
.spark{display:block}
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
const rows = new Map();
const detailNodes = new Map();
const detailMtime = new Map();

function makeRow(s){
  const c = el('div');
  c.dataset.id = s.id;
  c._st = el('span','st');
  c._title = el('span','title');
  c._age = el('span','age');
  c._act = el('span','activity');
  c.append(c._st, c._title, c._age, c._act);
  c.onclick = () => selectSession(s.id);
  return c;
}

function updateRow(c, s){
  const cls = 's ' + s.status + (selected === s.id ? ' sel' : '');
  if (c.className !== cls) c.className = cls;
  if (c._st.textContent !== s.status) c._st.textContent = s.status;
  if (c._title.textContent !== s.title) { c._title.textContent = s.title; c._title.title = s.title; }
  const a = fmtAge(s.age);
  if (c._age.textContent !== a) c._age.textContent = a;
  const act = s.status === 'dead' ? '' : (s.activity || '');
  let actCls = 'activity';
  if (act.startsWith('running ')) actCls += ' tool';
  else if (act.startsWith('waiting')) actCls += ' wait';
  if (c._act.className !== actCls) c._act.className = actCls;
  if (c._act.textContent !== act) c._act.textContent = act;
  c._act.style.display = act ? '' : 'none';
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

function sparkline(spark){
  const W = 480, H = 36;
  const s = svg('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'spark'});
  if (!spark.length) return s;
  const max = Math.max(1, ...spark.map(p => p.out));
  const n = spark.length;
  const bw = Math.max(1, Math.floor(W / n) - 1);
  spark.forEach((p, i) => {
    const h = Math.max(1, Math.round(Math.sqrt(p.out / max) * (H - 2)));
    const x = Math.floor(i * (W / n));
    s.append(svg('rect', {x, y: H - h, width: bw, height: h, fill: '#c4b5fd'}));
  });
  return s;
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
  h.append(el('span','ttl', s.title));
  if (s.cwd) h.append(el('span','cwd', s.cwd));
  if (s.branch) h.append(el('span','br', s.branch));
  h.append(el('span','age', fmtAge(s.age)));
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

  node.append(section('stats', statBlock(d.stats)));
  node.append(section('tokens / turn', sparkline(d.spark || [])));
  node.append(section('tools', toolBlock(d.tools || [])));
  node.append(section('git', gitBlock(d.git)));
  node.append(section('transcript', transcriptBlock(d.messages || [])));
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

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _route_summary(self, sid, force):
        if force:
            for path in glob.glob(os.path.join(ROOT, "*", sid + ".jsonl")):
                cache = path[:-6] + ".summary.json"
                if os.path.exists(cache):
                    try: os.remove(cache)
                    except OSError: pass
        d = summarize(sid)
        if d is None:
            self._json({"error": "session not found"}, 404); return
        self._json(d)
    def do_GET(self):
        if self.path == "/data.json":
            self._json(scan()); return
        if self.path.startswith("/session/"):
            sid = self.path[len("/session/"):]
            if not ID_RE.match(sid):
                self.send_response(400); self.end_headers(); return
            d = detail(sid)
            if d is None:
                self.send_response(404); self.end_headers(); return
            self._json(d); return
        if self.path.startswith("/summary/"):
            sid = self.path[len("/summary/"):]
            if not ID_RE.match(sid):
                self.send_response(400); self.end_headers(); return
            self._route_summary(sid, force=False); return
        body = PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.path.startswith("/summary/"):
            sid = self.path[len("/summary/"):]
            if not ID_RE.match(sid):
                self.send_response(400); self.end_headers(); return
            self._route_summary(sid, force=True); return
        self.send_response(404); self.end_headers()

if __name__ == "__main__":
    print(f"http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
