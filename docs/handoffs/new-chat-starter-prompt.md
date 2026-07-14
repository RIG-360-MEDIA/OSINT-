# Paste this into a new chat to continue exactly where we left off

---

You're picking up my RIG work — two products (the **OSINT / RIG Intelligence API** and **Rig Wire / DNL**
news platform + its **CMS**) plus their shared **database**. Before doing anything, load your context:

1. **Read `docs/handoffs/SESSION-HANDOFF-master.md`** in `C:/Users/Dell/Desktop/rig-surveillance` — it has
   the full map: both products, the box, the databases, access, what we built, and the gotchas.
2. **Read `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/MEMORY.md`** and open the
   per-topic memory files relevant to whatever I ask.
3. Skim `rig-surveillance/CLAUDE.md` for project rules.

**How I want you to work:**
- Be a hands-on staff engineer. **Do the thing, then prove it** — query the DB, `curl` the live URL, or
  run the dev server and read the page. Never say "done" without evidence. Report failures straight.
- You have full access on this machine: SSH to the box with `ssh -i ~/.ssh/rig_hetzner root@178.104.145.135`,
  query data with `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`, and run the DNL/CMS locally via
  `preview_start` (configs `dnl-dev`:3300 / `rig-cms`:3400; creds already in the `.env.local` files).
- **Which DB:** box `rig-postgres` is source of truth; the DNL *reader* reads Neon (a bounded mirror);
  **editorial + the OSINT API read the box.** Write to the box and let the sync propagate — never write app
  data directly to Neon.
- Frontend lives in `Desktop/rig-news` (DNL, deploys to Vercel `global.democracynewslive.com`) and
  `Desktop/rig-cms` (standalone CMS). Commit + push to deploy DNL; verify with `curl --resolve` against the
  live site.

**Fast facts to anchor you:**
- Box = `178.104.145.135` (NEW; ignore `.154`). Key containers: `rig-postgres`, `rig-backend` (DNL gen +
  Celery), `osint-backend` (the client API at `api.rig360media.com/v1`).
- Canonical CMS table = `editorial.decisions` (product-namespaced, audited/reversible; migration 005).
- Live API client = **Telangana CM & Government** (org `31ad3fa9`, healthy); `71589824`=your own QA sandbox.

Confirm you've read the handoff + memory, give me a 3-line status of both products, then ask what I want to
work on. From there, just do what I ask like the previous session did.
