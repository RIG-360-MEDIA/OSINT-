# New-Chat Bootstrap Prompt

Copy everything in the box below into the first message of a new chat (in this
repo). It tells the assistant to load the full context pack and behave as a
continuation of the original session.

---

```
You are continuing work on ROBIN-OSINT, my per-persona political-intelligence
SPA (live at https://desk.rig360media.com). A complete context pack exists in
this repo — READ IT FIRST, in full, before doing anything:

    products/osint/ROBIN-OSINT-CONTEXT/   (read 00 → 10, in order)

Also skim these for page/feature detail:
    products/osint/design/night-desk/WALKTHROUGH.md
    products/osint/design/night-desk/ROBIN-OSINT-Team-Guide.pdf

After reading, confirm you've absorbed it by giving me a 6-8 line summary of:
the product, the AP persona, the architecture (incl. the .env vs .env.prod
landmine), what was done in the last session, and the top open issues — then
wait for my instruction.

Operating rules you must follow (they're detailed in 09 + 10, but the critical
ones):
- Deploy osint-backend with the DEFAULT .env, never --env-file .env.prod
  (different ANALYTICS_DB_PASSWORD; wrong one 500s the site).
- After editing backend Python: py_compile + run the in-container validation
  before saying it's done.
- Never print or commit secrets; never fabricate data; no Co-Authored-By in
  commits; only commit/push when I ask.
- Don't run raw yt-dlp from Hetzner (IP reputation).
- /root/rig on Hetzner may diverge from local — diff before overwriting files.
- Hetzner: ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 ;
  DB: docker exec -i rig-postgres psql -U rig -d rig

Primary persona for testing: andhrarig360@gmail.com (principal Chandrababu Naidu,
user_id 7343cb2f-4f13-46f8-aea8-dbdedfa385b5).

Treat me as if we're continuing the previous conversation — I have full history;
you have this pack. When in doubt about an open decision, ask me (several
roadmap items in 08 are intentionally left for me to choose).
```

---

## Tips
- Keep this pack updated: after any significant change, append to
  `06-WORK-LOG-...` and adjust `07-KNOWN-ISSUES` / `08-ROADMAP`.
- If you start the new chat and it *doesn't* read the folder, paste the contents
  of `00-START-HERE.md` directly.
