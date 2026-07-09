"""RIG Identity Footprint — one selector → PUBLIC account footprint (isolated service).

    GET /footprint?selector=&top_sites=&fresh=  -> JSON footprint (cached)
    GET /                                       -> paste-a-selector UI
    GET /health

PUBLIC account traces only. Off-limits (broker people-search / breach data / face search /
dark-web) are NOT built. Runs isolated in a container (rigident) on infrastructure_rig-network;
does NOT touch rig-backend.  uvicorn app:app --host 0.0.0.0 --port 8702
"""
from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

import cache
import verify_identity_footprint as vif

app = FastAPI(title="RIG Identity Footprint")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://desk.rig360media.com", "https://robin-osi.rig360media.com",
                   "http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/footprint")
def footprint(selector: str = Query(..., max_length=200),
              top_sites: int = Query(150, ge=10, le=500),
              fresh: bool = Query(False)) -> JSONResponse:
    kind = vif.detect_selector(selector)
    key_ts = top_sites if kind == "username" else 0   # phone/email don't depend on top_sites
    if not fresh:
        hit = cache.get(selector, key_ts)
        if hit is not None:
            return JSONResponse(hit)
    try:
        r = vif.footprint(selector, top_sites=top_sites)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"[:160]}, status_code=502)
    cache.put(selector, key_ts, r)
    return JSONResponse(r)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RIG Identity Footprint</title><style>
 :root{--bg:#0a0c11;--panel:#141924;--panel2:#0e131c;--line:#222c3a;--txt:#eaeef5;
  --dim:#8b98ad;--faint:#5a6779;--red:#ff6259;--ok:#46e0a0;--amber:#f4b02e;--sky:#54c7e8;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,Segoe UI,sans-serif}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5}
 .wrap{max-width:900px;margin:0 auto;padding:0 20px}
 .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--amber)}
 h1{font-size:26px;font-weight:800;letter-spacing:-.02em;margin:8px 0 2px}
 .sub{color:var(--dim);margin-bottom:14px;font-size:14px;max-width:60ch}
 header{padding:44px 0 18px;border-bottom:1px solid var(--line)}
 .ctl{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 8px}
 input{background:#0b1017;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:10px 12px;font-family:var(--mono);font-size:13px}
 #sel{flex:1;min-width:240px}
 .go{background:var(--amber);color:#1a1206;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer}
 .presets{font-size:12px;color:var(--dim)} .presets a{color:var(--amber);cursor:pointer;margin-right:14px;text-decoration:none}
 .caveat{margin:18px 0;padding:11px 14px;border-radius:9px;border:1px solid color-mix(in oklab,var(--amber) 40%,transparent);
   background:color-mix(in oklab,var(--amber) 10%,transparent);color:#f4d79a;font-size:13px}
 .kind{font-family:var(--mono);font-size:11px;color:var(--faint);text-transform:uppercase;letter-spacing:.14em;margin:20px 0 8px}
 .acct{display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid var(--line);border-radius:9px;background:var(--panel2);margin-bottom:7px;text-decoration:none}
 .acct:hover{border-color:color-mix(in oklab,var(--sky) 45%,var(--line))}
 .conf{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.06em;padding:2px 6px;border-radius:4px;flex:none}
 .c-high{color:var(--ok);border:1px solid color-mix(in oklab,var(--ok) 40%,transparent)}
 .c-medium{color:var(--sky);border:1px solid color-mix(in oklab,var(--sky) 40%,transparent)}
 .acct .s{color:var(--txt);font-size:14px;font-weight:600;flex:none;min-width:120px}
 .acct .u{font-family:var(--mono);font-size:11px;color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .acct .ex{font-family:var(--mono);font-size:10.5px;color:var(--amber);margin-left:auto;flex:none}
 .kv{display:flex;flex-wrap:wrap;gap:20px;margin:6px 0 4px}
 .kv .n{font-family:var(--mono);font-size:20px;font-weight:700;font-variant-numeric:tabular-nums} .kv .l{font-family:var(--mono);font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:.1em}
 .chips{display:flex;flex-wrap:wrap;gap:6px} .chip{font-family:var(--mono);font-size:11px;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:3px 8px}
 .muted{color:var(--faint);font-family:var(--mono);font-size:11.5px}
 .rej summary{color:var(--faint);font-family:var(--mono);font-size:11.5px;cursor:pointer}
 .note{color:var(--dim);font-size:12.5px;border-left:2px solid var(--line);padding-left:12px;margin:10px 0}
 .foot{padding:22px 0 50px;color:var(--faint);font-family:var(--mono);font-size:11px;border-top:1px solid var(--line);margin-top:24px}
 #spin{color:var(--dim);font-family:var(--mono);font-size:13px;padding:22px 0}
</style></head><body><div class="wrap">
 <header><div class="eyebrow">RIG Surveillance · Identity Footprint</div>
  <h1>One selector → public account footprint</h1>
  <div class="sub">A username, email, or phone → the PUBLIC accounts, registration traces, or line
  details tied to it. Public presence only — leads for an analyst, never a ruling on identity.</div>
  <div class="ctl"><input id="sel" placeholder="username · email · +country phone"><button class="go" onclick="run()">Map footprint</button></div>
  <div class="presets">Try:
   <a onclick="ex('mkbhd')">👤 mkbhd</a><a onclick="ex('+919820098200')">📞 phone</a><a onclick="ex('johnsmith')">⚠ johnsmith (the trap)</a></div>
 </header>
 <div id="out"></div>
 <div class="foot">maigret (username) · holehe (email registration) · phonenumbers (phone) · breach-boolean disabled (free) ·
  OFF-LIMITS: no people-search, no breach data, no face search</div>
</div><script>
 function ex(s){document.getElementById("sel").value=s;run();}
 function esc(s){return (s==null?"":String(s)).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c];});}
 function acct(c){return '<a class="acct" href="'+esc(c.url)+'" target="_blank" rel="noreferrer">'+
   '<span class="conf c-'+esc(c.confidence)+'">'+esc(c.confidence)+'</span>'+
   '<span class="s">'+esc(c.site)+'</span><span class="u">'+esc(c.url)+'</span>'+
   (c.extracted?'<span class="ex">'+esc(Object.values(c.extracted).join(" · ").slice(0,40))+'</span>':'')+'</a>';}
 function run(){
  var s=document.getElementById("sel").value.trim(); if(!s)return;
  var out=document.getElementById("out");
  out.innerHTML='<div id="spin">mapping… a username scans hundreds of sites (up to 1–3 min)</div>';
  fetch("footprint?selector="+encodeURIComponent(s)).then(function(r){return r.json();}).then(function(d){
   if(d.error){out.innerHTML='<div id="spin">error: '+esc(d.error)+'</div>';return;}
   var r=d.result||{}, h='';
   if(d.caveat) h+='<div class="caveat">⚠ '+esc(d.caveat)+'</div>';
   if(d.type==="username"){
     var conf=r.confirmed||[];
     h+='<div class="kv"><div><div class="n" style="color:var(--ok)">'+(r.confirmed_count||0)+'</div><div class="l">confirmed accounts</div></div>'+
        '<div><div class="n" style="color:var(--faint)">'+(r.rejected_count||0)+'</div><div class="l">rejected (false-pos)</div></div>'+
        '<div><div class="n">'+(r.checked||0)+'</div><div class="l">sites checked</div></div></div>';
     if(r.error) h+='<div class="note">maigret note: '+esc(r.error)+'</div>';
     h+='<div class="kind">Confirmed public accounts (confidence = reachability, not identity)</div>';
     h+= conf.length? conf.map(acct).join('') : '<div class="muted">none confirmed</div>';
     if(r.related_handles&&r.related_handles.length){h+='<div class="kind">Related handles / names maigret surfaced — LEADS to corroborate</div><div class="chips">'+r.related_handles.map(function(x){return '<span class="chip">'+esc(x)+'</span>';}).join('')+'</div>';}
     if(r.rejected&&r.rejected.length){h+='<details class="rej"><summary>'+r.rejected.length+' rejected as false positives (search/aggregate URLs, handle-absent pages)</summary><div class="chips" style="margin-top:8px">'+r.rejected.map(function(x){return '<span class="chip">'+esc(x.site)+'</span>';}).join('')+'</div></details>';}
   } else if(d.type==="phone"){
     h+='<div class="kind">Phone line details (owner NOT identified)</div>';
     h+='<div class="kv"><div><div class="n" style="color:'+(r.valid?"var(--ok)":"var(--red)")+'">'+(r.valid?"valid":"invalid")+'</div><div class="l">number</div></div>'+
        '<div><div class="n" style="font-size:15px">'+esc(r.region||"—")+'</div><div class="l">region</div></div>'+
        '<div><div class="n" style="font-size:15px">'+esc(r.carrier||"—")+'</div><div class="l">carrier</div></div>'+
        '<div><div class="n" style="font-size:15px">'+esc(r.line_type||"—")+'</div><div class="l">line type</div></div></div>';
     if(r.note)h+='<div class="note">'+esc(r.note)+'</div>';
   } else if(d.type==="email"){
     var sites=r.registered_sites||[];
     h+='<div class="kind">Public registration traces ('+(r.count||0)+' sites)</div>';
     h+= sites.length? '<div class="chips">'+sites.map(function(x){return '<span class="chip">'+esc(x)+'</span>';}).join('')+'</div>':'<div class="muted">none / all rate-limited</div>';
     if(r.caveat)h+='<div class="note">'+esc(r.caveat)+'</div>';
     if(r.breach)h+='<div class="note">breach status: '+esc(r.breach.note)+'</div>';
   }
   out.innerHTML=h;
  }).catch(function(){out.innerHTML='<div id="spin">request failed</div>';});
 }
</script></body></html>"""
