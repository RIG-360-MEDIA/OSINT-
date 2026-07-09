"""RIG Geospatial change desk — one location, three layers, analyst picks.

    GET /imagery?lat=&lon=&source=esri|sentinel2|sentinel1  -> image + X-* metadata
    GET /                                                    -> source-toggle UI
    GET /health

Run (in the satvenv, isolated — does NOT touch rig-backend):
    /root/satvenv/bin/uvicorn app:app --host 0.0.0.0 --port 8700
"""
from __future__ import annotations

import base64
import os
import tempfile

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

import imagery
import render
import verify_satellite_change as vsc

app = FastAPI(title="RIG Geospatial")

# The night-desk media-verification flow corroborates a claim by calling /geo/change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://desk.rig360media.com", "https://robin-osi.rig360media.com",
                   "http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _rmtree(d: str) -> None:
    try:
        for f in os.listdir(d):
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
        os.rmdir(d)
    except OSError:
        pass


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

    def _hv(s: object) -> str:  # HTTP headers are latin-1; strip em/en-dashes etc.
        return (str(s).replace("—", "-").replace("–", "-")
                .encode("latin-1", "replace").decode("latin-1"))

    headers = {
        "X-Source": _hv(r.get("source", "")),
        "X-Date": _hv(r.get("date", "")),
        "X-Res-M": _hv(r.get("res_m", "")),
        "X-Cloud": _hv(r.get("cloud_pct", "")),
        "X-Attribution": _hv(r.get("attribution", "")),
        "Cache-Control": "no-store",
    }
    return Response(content=r["image"], media_type=r["mime"], headers=headers)


@app.get("/change")
def change(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    before: str = Query(..., max_length=40, description="STAC date range e.g. 2022-06-01/2022-06-30"),
    after: str = Query(..., max_length=40),
    km: float = Query(12.0, ge=1, le=40),
    mode: str = Query("optical", pattern="^(optical|radar)$"),
) -> JSONResponse:
    """Satellite change-detection between two date windows — corroborate a claim
    ('did something big physically change here?'). HEAVY / on-demand: STAC search +
    scene downloads + rendering take ~1-3 min. Returns a summary + before/after/change
    PNGs as data-URIs. ~10 m ceiling — extent & change, not vehicles."""
    bbox = imagery.bbox_from_point(lat, lon, km)
    out = tempfile.mkdtemp(prefix="chg_")
    label = "aoi"
    try:
        fn = vsc.run_radar if mode == "radar" else vsc.run_optical
        info = fn(bbox, before, after, out, label, km)
    except Exception as exc:
        _rmtree(out)
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"[:200]}, status_code=502)
    if info.get("error"):
        _rmtree(out)
        return JSONResponse({"error": info["error"], "mode": mode}, status_code=502)
    images = {}
    for fname in info.pop("outputs", []):
        p = os.path.join(out, fname)
        if os.path.exists(p):
            key = fname.replace(f"{label}_", "").replace(".png", "")
            images[key] = "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
    _rmtree(out)
    return JSONResponse({"lat": lat, "lon": lon, "km": km, "mode": mode,
                         "before": before, "after": after, "summary": info, "images": images})


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
   fetch("imagery?lat="+la+"&lon="+lo+"&source="+src).then(function(r){
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
