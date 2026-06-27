"""Reproduce the production field-drop with the REAL GROQ_SYS + max_tokens,
then compare LOOSE (json_object) vs ENFORCED (json_schema) on local TabbyAPI.

Extracts GROQ_SYS / GROQ_SYS_NON_ENGLISH and the token/body constants straight
from the live module via AST (no import side effects), so the prompt is byte-faithful.
"""
import ast, json, subprocess, urllib.request, urllib.error, time

PROD = "/root/rig/backend/tasks/substrate/run_corpus_pass.py"
URL = "http://172.30.0.1:5000/v1/chat/completions"
MODEL = "Qwen3-14B-exl3-4bpw"

src = open(PROD, encoding="utf-8").read()
tree = ast.parse(src)
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        if name in ("GROQ_SYS", "MAX_TOKENS_ENGLISH", "MAX_TOKENS_NON_ENGLISH",
                    "MAX_BODY_FOR_GROQ_ENGLISH", "MAX_BODY_FOR_GROQ_CJK", "MAX_BODY_FOR_GROQ_INDIC"):
            try:
                consts[name] = ast.literal_eval(node.value)
            except Exception:
                pass
        # GROQ_SYS_NON_ENGLISH = GROQ_SYS + """..."""  -> BinOp
        if name == "GROQ_SYS_NON_ENGLISH" and isinstance(node.value, ast.BinOp):
            tail = node.value.right
            if isinstance(tail, ast.Constant):
                consts["GROQ_SYS_NON_ENGLISH"] = consts.get("GROQ_SYS", "") + tail.value

GROQ_SYS = consts["GROQ_SYS"]
GROQ_SYS_NE = consts.get("GROQ_SYS_NON_ENGLISH", GROQ_SYS)
MAX_TOK_EN = consts.get("MAX_TOKENS_ENGLISH", 3000)
MAX_TOK_NE = consts.get("MAX_TOKENS_NON_ENGLISH", 3500)
BODY_EN = consts.get("MAX_BODY_FOR_GROQ_ENGLISH", 2400)
print(f"prompt sizes: GROQ_SYS={len(GROQ_SYS)}ch  NON_ENG={len(GROQ_SYS_NE)}ch  "
      f"max_tok en/ne={MAX_TOK_EN}/{MAX_TOK_NE}", flush=True)

# Full-field schema for the ENFORCED run — forces summaries.executive to exist.
SCHEMA = {"type": "object", "properties": {
    "article_type": {"type": "string"},
    "primary_subject": {"type": "string"},
    "summaries": {"type": "object", "properties": {
        "preview": {"type": "string"}, "snippet": {"type": "string"}, "executive": {"type": "string"}},
        "required": ["preview", "snippet", "executive"]},
    "locations": {"type": "array", "items": {"type": "object"}},
    "events": {"type": "array"}, "quotes": {"type": "array"},
    "actor_stances": {"type": "array"}, "claims": {"type": "array"},
    "numbers": {"type": "array"}, "register": {"type": "object"}},
    "required": ["article_type", "primary_subject", "summaries", "locations",
                 "events", "quotes", "actor_stances", "claims", "numbers", "register"]}

SQL = (
    "SELECT json_agg(t) FROM (SELECT title, coalesce(language_iso,'en') AS lang, "
    "left(full_text_scraped,2400) AS body FROM articles "
    "WHERE substrate_status='ok' AND coalesce(summary_executive,'')='' "
    "AND coalesce(full_text_scraped,'')<>'' ORDER BY published_at DESC LIMIT 8) t;"
)
out = subprocess.run(
    ["docker", "exec", "rig-postgres", "psql", "-U", "rig", "-d", "rig", "-t", "-A", "-c", SQL],
    capture_output=True, text=True).stdout.strip()
arts = json.loads(out)

INDIC = {"hi", "te", "ta", "kn", "ml", "mr", "gu", "bn", "pa", "or", "as", "ur"}
CJK = {"ja", "zh", "ko", "zh-cn", "zh-tw"}


def ctx_for(lang):
    lang = (lang or "en").lower()
    if lang in INDIC or lang in CJK:
        return GROQ_SYS_NE, MAX_TOK_NE
    return GROQ_SYS, MAX_TOK_EN


def call(title, body, sys_p, max_tok, enforce):
    msg = {"model": MODEL, "max_tokens": max_tok, "temperature": 0.2,
           "chat_template_kwargs": {"enable_thinking": False},
           "messages": [{"role": "system", "content": sys_p},
                        {"role": "user",
                         "content": f"TITLE: {title}\n\nBODY:\n{body}\n\nReturn ONLY the JSON object."}]}
    msg["response_format"] = ({"type": "json_schema",
                               "json_schema": {"name": "extraction", "schema": SCHEMA}}
                              if enforce else {"type": "json_object"})
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
                return None, "UNPARSEABLE(len=%d): %s" % (len(c), c[-120:])
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}: {e.read()[:160]}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(3)
    return None, "RETRIES_EXHAUSTED: " + last


for mode in ["LOOSE (json_object)", "ENFORCED (json_schema)"]:
    enforce = "ENFORCED" in mode
    print(f"\n===== {mode} =====", flush=True)
    summ = loc = fail = 0
    for i, a in enumerate(arts):
        sys_p, max_tok = ctx_for(a["lang"])
        p, raw = call(a["title"], a["body"], sys_p, max_tok, enforce)
        if not p:
            fail += 1
            print(f"[{i}/{a['lang']}] FAIL: {raw!r}", flush=True)
            continue
        execu = ((p.get("summaries") or {}).get("executive") or "").strip()
        locs = p.get("locations") or []
        summ += 1 if execu else 0
        loc += 1 if locs else 0
        flag = "Y" if execu else "N"
        print(f"[{i}/{a['lang']}] summary={flag} locs={len(locs)} exec='{execu[:70]}'", flush=True)
    n = len(arts)
    print(f"--> summary {summ}/{n} | locations {loc}/{n} | hard_fail {fail}/{n}", flush=True)
print("\nDONE", flush=True)
