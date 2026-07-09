"""RIG Media Verify — is an image real, old, or fake? (isolated service).

    GET /verify?image_url=&claimed_date=   -> JSON signals + verdict
    GET /ela?image_url=                    -> Error-Level-Analysis PNG
    GET /                                  -> paste-a-URL UI
    GET /health

Signals, NOT proof — leads for a human analyst. Free/no-paid. Runs isolated in a
container (rigmedia) on infrastructure_rig-network; does NOT touch rig-backend.
    uvicorn app:app --host 0.0.0.0 --port 8701
"""
from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

import cache
import verify_image as vi

app = FastAPI(title="RIG Media Verify")

# The night-desk dossier (desk.rig360media.com) calls /media/badge cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://desk.rig360media.com", "https://robin-osi.rig360media.com",
                   "http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _run(image_url: str, claimed_date: str | None, fresh: bool) -> dict:
    """Cache-first verification — a reverse-search runs once, every later view is free."""
    if not fresh:
        hit = cache.get(image_url)
        if hit is not None:
            if claimed_date and not hit.get("claimed_date"):
                hit["claimed_date"] = claimed_date
            return hit
    r = vi.verify(image_url, claimed_date)
    (r.get("ela") or {}).pop("ela_png", None)   # don't cache/leak local temp path
    cache.put(image_url, r)
    return r


def _badge(r: dict) -> dict:
    """Compact chip for a dossier post card — one status + a short label."""
    rev = r.get("reverse") or {}
    fc = rev.get("factcheck_hits") or []
    geo = r.get("geolocation") or {}
    n = rev.get("distinct_domains")
    if fc:
        status, label = "red", "Likely recycled / debunked"
    elif not rev.get("ok"):
        status, label = "unknown", "Reverse-search unavailable"
    elif n is not None and n <= 2:
        status, label = "clear", "No earlier appearances"
    elif rev.get("appears_widely"):
        status, label = "circulated", "Widely circulated"
    else:
        status, label = "circulated", "Some prior appearances"
    return {
        "status": status,                                  # red | circulated | clear | unknown
        "label": label,
        "factcheck_hits": fc,
        "sites": n,
        "has_exif": bool((r.get("exif") or {}).get("fields")),
        "gps": geo.get("place") if geo.get("has_gps") else None,
        "signals": r.get("signals", []),
        "cached": bool(r.get("_cached")),
    }


@app.get("/verify")
def verify(image_url: str = Query(..., max_length=2000),
           claimed_date: str | None = Query(None, max_length=40),
           fresh: bool = Query(False)) -> JSONResponse:
    try:
        return JSONResponse(_run(image_url, claimed_date, fresh))
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"[:140]}, status_code=502)


@app.get("/badge")
def badge(image_url: str = Query(..., max_length=2000),
          fresh: bool = Query(False)) -> JSONResponse:
    """Compact, cached chip for auto-display on dossier cards. Always 200 (degrades gracefully)."""
    try:
        return JSONResponse(_badge(_run(image_url, None, fresh)))
    except Exception as exc:
        return JSONResponse({"status": "unknown", "label": "verify unavailable",
                             "error": type(exc).__name__})


@app.get("/ela")
def ela(image_url: str = Query(..., max_length=2000)) -> Response:
    """The Error-Level-Analysis map (bright = different compression = possible edit)."""
    path = elap = None
    try:
        data = vi._get(image_url, binary=True)
        fd, path = tempfile.mkstemp(suffix=".img")
        os.write(fd, data)
        os.close(fd)
        res = vi.ela(path)
        if not res.get("ok"):
            return JSONResponse({"error": "ELA failed"}, status_code=502)
        elap = res["ela_png"]
        return Response(open(elap, "rb").read(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:120]}, status_code=502)
    finally:
        for p in (path, elap):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RIG Media Verify</title><style>
 :root{--bg:#0b0c10;--panel:#14161d;--panel2:#0e1015;--line:#242833;--txt:#eceef3;
  --dim:#8b93a3;--faint:#5c6472;--red:#ff5f56;--ok:#43e0a0;--amber:#f6b13e;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,Segoe UI,sans-serif}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5}
 .wrap{max-width:940px;margin:0 auto;padding:0 20px}
 .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--amber)}
 h1{font-size:26px;font-weight:800;letter-spacing:-.02em;margin:8px 0 2px} .sub{color:var(--dim);margin-bottom:18px;font-size:14px}
 header{padding:44px 0 20px;border-bottom:1px solid var(--line)}
 .ctl{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}
 input{background:#0b1017;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:10px 12px;font-family:var(--mono);font-size:13px}
 #url{flex:1;min-width:260px} #cd{width:140px}
 .go{background:var(--amber);color:#1a1206;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer}
 .presets{font-size:12px;color:var(--dim);margin-bottom:8px} .presets a{color:var(--amber);cursor:pointer;margin-right:14px;text-decoration:none}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0} @media(max-width:680px){.grid{grid-template-columns:1fr}}
 .imgcard{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
 .imgcard .lab{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);padding:9px 12px;border-bottom:1px solid var(--line)}
 .imgcard img{width:100%;display:block;background:#05070b;min-height:120px}
 .verdict{margin:18px 0 4px;font-size:22px;font-weight:800} .verdict.red{color:var(--red)} .verdict.ok{color:var(--ok)} .verdict.dim{color:var(--dim)}
 .sig{display:flex;flex-direction:column;gap:8px;margin:12px 0}
 .sig div{font-size:13.5px;color:#cdd3de;padding:9px 12px;background:var(--panel2);border:1px solid var(--line);border-radius:9px}
 .sig div.red{border-color:#4a1f1e;color:#ffbdb8} .sig div.ok{border-color:#1c4a35;color:#a9e9c9}
 .kv{font-family:var(--mono);font-size:12.5px;color:var(--dim);margin-top:14px} .kv b{color:var(--txt)}
 .foot{padding:20px 0 50px;color:var(--faint);font-family:var(--mono);font-size:11px;border-top:1px solid var(--line);margin-top:20px}
 #spin{color:var(--dim);font-family:var(--mono);font-size:13px;padding:24px 0}
</style></head><body><div class="wrap">
 <header><div class="eyebrow">RIG Surveillance · Media Verify</div>
  <h1>Is this image real, old, or fake?</h1>
  <div class="sub">Paste an image URL → where it appeared · fact-check hits · EXIF · location · edit signal. Leads, not proof.</div>
  <div class="presets">Try:
   <a onclick="ex('https://i.pinimg.com/originals/01/21/3c/01213c98815dcf54756d029204d87044.jpg','2024-10-10')">🦈 shark hoax</a>
   <a onclick="ex('https://upload.wikimedia.org/wikipedia/commons/a/a8/Tour_Eiffel_Wikimedia_Commons.jpg','')">🗼 legit control</a>
  </div>
  <div class="ctl"><input id="url" placeholder="https://…/image.jpg"><input id="cd" placeholder="claimed date (opt)"><button class="go" onclick="run()">Verify</button></div>
 </header>
 <div id="out"></div>
 <div class="foot">verify_image.py · Yandex reverse + fact-check heuristic + exiftool + Nominatim GPS + ELA · SIGNAL not proof · no free deepfake verdict</div>
</div><script>
 function ex(u,d){document.getElementById("url").value=u;document.getElementById("cd").value=d;run();}
 function esc(s){return (s==null?"":String(s)).replace(/[&<>]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c];});}
 function run(){
  var u=document.getElementById("url").value.trim(), d=document.getElementById("cd").value.trim();
  if(!u)return; var out=document.getElementById("out");
  out.innerHTML='<div id="spin">analysing… reverse-search can take 10–20s</div>';
  fetch("verify?image_url="+encodeURIComponent(u)+(d?"&claimed_date="+encodeURIComponent(d):"")).then(function(r){return r.json();}).then(function(j){
   if(j.error){out.innerHTML='<div id="spin">error: '+esc(j.error)+'</div>';return;}
   var rev=j.reverse||{}, geo=j.geolocation||{}, ela=j.ela||{}, ex=(j.exif||{}).fields;
   var fc=rev.factcheck_hits&&rev.factcheck_hits.length;
   var vclass=fc?"red":(rev.ok&&rev.distinct_domains<=2?"ok":"dim");
   var vtext=fc?"⚑ Likely recycled / debunked":(rev.ok&&rev.distinct_domains<=2?"✓ No earlier appearances":"Circulated — no debunk found");
   var h='<div class="verdict '+vclass+'">'+vtext+'</div>';
   h+='<div class="sig">';
   (j.signals||[]).forEach(function(s){var c=/RED FLAG/.test(s)?"red":(/original \/ fresh/.test(s)?"ok":"");h+='<div class="'+c+'">'+esc(s)+'</div>';});
   h+='</div>';
   h+='<div class="grid">';
   h+='<div class="imgcard"><div class="lab">Original</div><img src="'+esc(u)+'" onerror="this.style.display=\\'none\\'"></div>';
   h+='<div class="imgcard"><div class="lab">Error-Level Analysis (edit signal)</div><img src="ela?image_url='+encodeURIComponent(u)+'" onerror="this.style.display=\\'none\\'"></div>';
   h+='</div>';
   h+='<div class="kv">reverse: <b>'+(rev.distinct_domains!=null?rev.distinct_domains:"—")+'</b> sites'+(fc?' · fact-check: <b style="color:var(--red)">'+esc(rev.factcheck_hits.join(", "))+'</b>':' · fact-check: <b style="color:var(--ok)">none</b>')+'<br>';
   h+='EXIF: <b>'+(ex?"present":"none / stripped")+'</b> · location: <b>'+(geo.has_gps?esc(geo.place||(geo.lat+","+geo.lon)):"no GPS")+'</b> · ELA max-diff: <b>'+(ela.max_diff!=null?ela.max_diff:"—")+'</b></div>';
   out.innerHTML=h;
  }).catch(function(e){out.innerHTML='<div id="spin">request failed</div>';});
 }
</script></body></html>"""
