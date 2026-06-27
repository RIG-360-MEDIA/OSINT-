import json, subprocess, urllib.request, urllib.error, time

URL = "http://172.30.0.1:5000/v1/chat/completions"
MODEL = "Qwen3-14B-exl3-4bpw"

SYS = (
 "Extract structured intel from this news article. Output JSON ONLY matching the schema.\n"
 "Fields: article_type (news|opinion|analysis|explainer|other); primary_subject (1 sentence);\n"
 "summaries {preview <=50 chars, snippet <=200 chars, executive <=1000 chars};\n"
 "locations [{text,country,region,city,is_primary}] max 5;\n"
 "events []; quotes []; actor_stances []; claims [{subject,predicate,object,text}] max 5; numbers [];\n"
 "register {rhetorical_style, primary_emotion, is_breaking}.\n"
 "Output ONLY the JSON object."
)
SCHEMA = {"type": "object", "properties": {
    "article_type": {"type": "string"},
    "primary_subject": {"type": "string"},
    "summaries": {"type": "object", "properties": {
        "preview": {"type": "string"}, "snippet": {"type": "string"}, "executive": {"type": "string"}},
        "required": ["preview", "snippet", "executive"]},
    "locations": {"type": "array", "items": {"type": "object"}},
    "claims": {"type": "array"}, "quotes": {"type": "array"}, "register": {"type": "object"}},
    "required": ["article_type", "primary_subject", "summaries", "locations", "claims", "quotes", "register"]}

SQL = (
    "SELECT json_agg(t) FROM (SELECT title, left(full_text_scraped,2000) AS body FROM articles "
    "WHERE substrate_status='ok' AND coalesce(summary_executive,'')='' "
    "AND coalesce(full_text_scraped,'')<>'' ORDER BY published_at DESC LIMIT 4) t;"
)
out = subprocess.run(
    ["docker", "exec", "rig-postgres", "psql", "-U", "rig", "-d", "rig", "-t", "-A", "-c", SQL],
    capture_output=True, text=True).stdout.strip()
arts = json.loads(out)


def call(title, body, enforce):
    msg = {"model": MODEL, "max_tokens": 3000, "temperature": 0.2,
           "chat_template_kwargs": {"enable_thinking": False},
           "messages": [{"role": "system", "content": SYS},
                        {"role": "user",
                         "content": f"TITLE: {title}\n\nBODY:\n{body}\n\nReturn ONLY the JSON object."}]}
    if enforce:
        msg["response_format"] = {"type": "json_schema",
                                  "json_schema": {"name": "extraction", "schema": SCHEMA}}
    else:
        msg["response_format"] = {"type": "json_object"}
    last = ""
    for _ in range(3):
        try:
            req = urllib.request.Request(URL, data=json.dumps(msg).encode(),
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=300).read())
            c = r["choices"][0]["message"].get("content") or ""
            try:
                return json.loads(c), c
            except Exception:
                return None, "UNPARSEABLE: " + c[:140]
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}: {e.read()[:200]}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(3)
    return None, "RETRIES_EXHAUSTED: " + last


for mode in ["LOOSE (json_object)", "ENFORCED (json_schema)"]:
    enforce = "ENFORCED" in mode
    print(f"\n===== {mode} =====", flush=True)
    summ = loc = claimc = 0
    for i, a in enumerate(arts):
        p, raw = call(a["title"], a["body"], enforce)
        if not p:
            print(f"[{i}] FAIL: {raw!r}", flush=True)
            continue
        execu = ((p.get("summaries") or {}).get("executive") or "").strip()
        locs = p.get("locations") or []
        claims = p.get("claims") or []
        summ += 1 if execu else 0
        loc += 1 if locs else 0
        claimc += 1 if claims else 0
        flag = "Y" if execu else "N"
        print(f"[{i}] summary={flag} locs={len(locs)} claims={len(claims)} exec='{execu[:80]}'",
              flush=True)
    print(f"--> summary {summ}/{len(arts)} | locations {loc}/{len(arts)} | claims {claimc}/{len(arts)}",
          flush=True)
print("\nDONE", flush=True)
