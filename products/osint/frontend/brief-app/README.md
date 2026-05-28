# Boss's Morning Brief — local dev

Boss's frontend, copied here untouched. Lives at `http://localhost:5173` when running.

## Run it

**Double-click `start.bat`** → opens a terminal, server runs.
Then open **http://localhost:5173** in your browser.

Or from a terminal:
```
cd brief-app
py -3 -m http.server 5173
```

To stop: close the terminal window or press Ctrl+C.

## What's in here

| File | Purpose |
|---|---|
| `index.html` | Entry point (copy of `Morning Brief.html` renamed so `/` resolves to it) |
| `Morning Brief.html`, `Top Bar Exploration.html` | Boss's originals, untouched |
| `app.jsx`, `primitives.jsx` | React components (Babel-in-browser compiles on load) |
| `data.js` | Mock data — this is what we'll swap to real API calls one feature at a time |
| `styles.css` | 281 KB of boss's styling |
| `images/`, `debug/`, `uploads/` | Boss's assets |
| `image-slot.js` | Image-handling primitives |

## What's NEXT (Day 1)

1. Add `backend/routers/brief_router.py` on Hetzner with `GET /api/brief/dashboard`
2. Add `http://localhost:5173` to CORS allow-list on Hetzner backend
3. Change `data.js` to `fetch()` from Hetzner instead of declaring static objects
4. Refresh browser → same UI, real data plumbing proven

## What's NEVER touched

- `frontend/src/app/observe/*` (existing /observe console)
- `/api/observe/*` endpoints
- Production deployment
