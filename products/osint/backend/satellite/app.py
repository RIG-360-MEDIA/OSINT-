"""RIG Geospatial change desk — one location, three layers, analyst picks.

    GET /imagery?lat=&lon=&source=esri|sentinel2|sentinel1  -> image + X-* metadata
    GET /                                                    -> source-toggle UI
    GET /health

Run (in the satvenv, isolated — does NOT touch rig-backend):
    /root/satvenv/bin/uvicorn app:app --host 0.0.0.0 --port 8700
"""
from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

import render

app = FastAPI(title="RIG Geospatial")


@app.get("/imagery")
def imagery(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    source: str = Query("esri", pattern="^(esri|sentinel2|sentinel1)$"),
) -> Response:
    """Best-quality imagery for a point from the chosen source."""
    r = render.render(lat, lon, source=source)
    if not r.get("ok"):
        return JSONResponse({"error": r.get("error", "failed"), "source": source},
                            status_code=502)
    headers = {
        "X-Source": str(r.get("source", "")),
        "X-Date": str(r.get("date", "")),
        "X-Res-M": str(r.get("res_m", "")),
        "X-Cloud": str(r.get("cloud_pct", "")),
        "X-Attribution": str(r.get("attribution", "")),
        "Cache-Control": "no-store",
    }
    return Response(content=r["image"], media_type=r["mime"], headers=headers)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "sources": ["esri", "sentinel2", "sentinel1"]}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RIG Geospatial — Change Desk</title>
<style>
 :root{--bg:#090d13;--panel:#10161f;--line:#1e2a38;--txt:#e8eef5;--dim:#8496ab;
   --accent:#43e0cf;--amber:#f6b13e;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,sans-serif;
   background-image:radial-gradient(900px 500px at 80% -10%,#10202b,transparent 60%)}
 .wrap{max-width:900px;margin:0 auto;padding:26px 20px}
 .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
 h1{font-size:24px;font-weight:800;letter-spacing:-.02em;margin:8px 0 2px}
 .sub{color:var(--dim);font-size:14px;margin-bottom:18px}
 .ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
 input{background:#0b1017;border:1px solid var(--line);color:var(--txt);border-radius:8px;
   padding:9px 11px;font-family:var(--mono);font-size:13px;width:120px}
 .tabs{display:flex;gap:4px;background:#0a0f16;border:1px solid var(--line);border-radius:10px;padding:4px}
 .tabs button{font-family:var(--mono);font-size:12px;letter-spacing:.06em;background:transparent;
   color:var(--dim);border:0;border-radius:7px;padding:9px 14px;cursor:pointer}
 .tabs button.on{background:#16212d;color:var(--accent)}
 .tabs button.on[data-s=esri]{color:#fff;background:#1d2b39}
 .go{background:var(--accent);color:#08110f;border:0;border-radius:8px;padding:9px 16px;font-weight:700;cursor:pointer}
 .presets{margin:2px 0 16px;font-size:12px;color:var(--dim)}
 .presets a{color:var(--accent);cursor:pointer;margin-right:12px;text-decoration:none}
 .frame{position:relative;aspect-ratio:1/1;background:#05080c;border:1px solid var(--line);
   border-radius:12px;overflow:hidden;display:flex;align-items:center;justify-content:center}
 .frame img{width:100%;height:100%;object-fit:cover;display:none}
 .frame.loaded img{display:block}
 .spin{color:var(--dim);font-family:var(--mono);font-size:13px}
 .meta{display:flex;flex-wrap:wrap;gap:16px;margin-top:12px;font-family:var(--mono);font-size:12.5px}
 .meta b{color:var(--txt)} .meta span{color:var(--dim)}
 .att{margin-top:8px;color:#5a6b7e;font-size:11px;font-family:var(--mono)}
 .note{margin-top:14px;color:var(--dim);font-size:12.5px;border-left:2px solid var(--line);padding-left:12px}
</style></head><body><div class="wrap">
 <div class="eyebrow">RIG Surveillance · Geospatial</div>
 <h1>Change Desk — one place, three layers</h1>
 <div class="sub">Pick a source per need: sharp detail, current optical, or all-weather radar. All free.</div>
 <div class="ctl">
   <input id="lat" value="30.4165"> <input id="lon" value="77.9685">
   <div class="tabs">
     <button data-s="esri" class="on">🔍 Sharp · Esri ~0.5m</button>
     <button data-s="sentinel2">🛰️ Current · S2 10m</button>
     <button data-s="sentinel1">🌧️ Radar · S1 10m</button>
   </div>
   <button class="go" onclick="load()">Load</button>
 </div>
 <div class="presets">Try:
   <a onclick="preset(30.4165,77.9685)">UPES Dehradun</a>
   <a onclick="preset(28.16,77.53)">Jewar Airport</a>
   <a onclick="preset(26.73,67.65)">Sindh (flood)</a>
 </div>
 <div class="frame" id="frame"><span class="spin" id="spin">pick a source →</span><img id="img"></div>
 <div class="meta" id="meta"></div>
 <div class="att" id="att"></div>
 <div class="note">Sharp = ~0.5m (buildings, courts, vehicles) but months old · Current/Radar = 10m
   (extent + change) but days old. Detail + freshness together needs paid tasking — flagged, never faked.</div>
</div>
<script>
 var src="esri";
 document.querySelectorAll(".tabs button").forEach(function(b){
   b.addEventListener("click",function(){ src=b.getAttribute("data-s");
     document.querySelectorAll(".tabs button").forEach(function(x){x.classList.toggle("on",x===b)}); load(); });
 });
 function preset(la,lo){ document.getElementById("lat").value=la; document.getElementById("lon").value=lo; load(); }
 function load(){
   var la=document.getElementById("lat").value, lo=document.getElementById("lon").value;
   var fr=document.getElementById("frame"), sp=document.getElementById("spin");
   fr.classList.remove("loaded"); sp.style.display="block"; sp.textContent="fetching "+src+" imagery… (10-40s)";
   document.getElementById("meta").innerHTML=""; document.getElementById("att").textContent="";
   fetch("/imagery?lat="+la+"&lon="+lo+"&source="+src).then(function(r){
     if(!r.ok){ sp.textContent="no "+src+" imagery for this spot"; return null; }
     var h=r.headers;
     document.getElementById("meta").innerHTML=
       "<div><span>SOURCE</span> <b>"+(h.get("X-Source")||src)+"</b></div>"+
       "<div><span>DATE</span> <b>"+(h.get("X-Date")||"—")+"</b></div>"+
       "<div><span>RES</span> <b>"+(h.get("X-Res-M")||"—")+" m/px</b></div>"+
       (h.get("X-Cloud")&&h.get("X-Cloud")!=="" ? "<div><span>CLOUD</span> <b>"+h.get("X-Cloud")+"%</b></div>":"");
     document.getElementById("att").textContent=h.get("X-Attribution")||"";
     return r.blob();
   }).then(function(b){ if(!b)return; var u=URL.createObjectURL(b);
     document.getElementById("img").src=u; fr.classList.add("loaded"); sp.style.display="none";
   }).catch(function(){ sp.textContent="request failed"; });
 }
 load();
</script></body></html>"""
