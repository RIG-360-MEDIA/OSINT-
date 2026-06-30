# RIG Client Integration Guide — Building on the API

*For the client's backend/frontend engineers. Shows how to fetch data from RIG and render it on their site.*

---

## 1. Getting started

### Credentials
You'll receive:
- **API Key** (keep it secret, like a password)
- **API Host** (e.g., `https://api.rig360media.com`)
- **Org ID** (identifies your tenant; never send this in a request)

### Authentication
Every request includes your key in the `Authorization` header:
```
Authorization: Bearer YOUR_API_KEY_HERE
```

That's it — the server knows which org you are from the key. No need to send an `org_id` parameter.

---

## 2. Making your first request

### Get today's situation brief
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://api.rig360media.com/api/brief/home
```

Response:
```json
{
  "date": "2026-06-29",
  "summary": "Key developments in your watchlist this week...",
  "sections": [
    {
      "title": "Telangana CM — sentiment shift",
      "stories": [
        {
          "headline": "CM announces water policy",
          "entities": [{"name": "Revanth Reddy", "type": "person"}],
          "sentiment": {"supportive": 3, "critical": 1, "neutral": 2},
          "source": "The Hindu",
          "url": "https://...",
          "published_at": "2026-06-29T08:30:00Z"
        }
      ]
    }
  ]
}
```

---

## 3. Common endpoints (for your site)

### Brief & overview
- `GET /api/brief/home` — today's key developments
- `GET /api/brief/situation` — your current situation summary
- `GET /api/brief/daily` — full daily brief (all sections)

### Analytics (sentiment, coverage, etc.)
- `GET /api/analytics/coverage?window=7` — article count over last 7 days
- `GET /api/analytics/sentiment?entity=revanth&window=30` — sentiment toward an entity over 30 days
- `GET /api/analytics/outlets` — which outlets cover you most
- `GET /api/analytics/topics?limit=10` — top 10 topics this week

### Entities & dossiers
- `GET /api/entities` — your watchlist
- `GET /api/entities/{entity_id}` — profile of one person/org
- `GET /api/entities/{entity_id}/articles?limit=20` — articles about them

### Map & geography
- `GET /api/geo/coverage` — which states/districts mention you
- `GET /api/geo/district/{state}/{district}?limit=10` — coverage in a specific district

### "Show me the articles"
- `GET /api/sources?filter=sentiment:critical&limit=20` — all critical articles
- `GET /api/sources?entity=telangana&window=7&limit=50` — articles mentioning your entity, last 7 days

### AI assistant (streaming)
- `POST /api/chat` → `text/event-stream` — ask questions, get streamed answers + sources

---

## 4. Code examples (JavaScript / React)

### Fetch the brief and display it
```javascript
async function fetchBrief() {
  const res = await fetch('https://api.rig360media.com/api/brief/home', {
    headers: { 'Authorization': `Bearer ${API_KEY}` }
  });
  const data = await res.json();
  return data;
}

// Use in your React component
export function BriefCard() {
  const [brief, setBrief] = useState(null);
  useEffect(() => {
    fetchBrief().then(setBrief);
  }, []);
  
  if (!brief) return <div>Loading...</div>;
  return (
    <div className="brief">
      <h1>{brief.date}</h1>
      <p>{brief.summary}</p>
      {brief.sections.map(sec => (
        <div key={sec.title} className="section">
          <h2>{sec.title}</h2>
          {sec.stories.map(story => (
            <article key={story.headline}>
              <a href={story.url}>{story.headline}</a>
              <p>via {story.source}</p>
            </article>
          ))}
        </div>
      ))}
    </div>
  );
}
```

### Fetch sentiment over time and draw a chart
```javascript
async function fetchSentimentTrend(entityName, days = 30) {
  const res = await fetch(
    `https://api.rig360media.com/api/analytics/sentiment?entity=${entityName}&window=${days}`,
    { headers: { 'Authorization': `Bearer ${API_KEY}` } }
  );
  return res.json();
}

// Result: { positive: 15, neutral: 8, critical: 12, daily: [{date, pos, neg, neu}, ...] }
// Render with Chart.js or any charting library
import Chart from 'chart.js/auto';

const trend = await fetchSentimentTrend('Revanth');
const ctx = document.getElementById('myChart');
new Chart(ctx, {
  type: 'line',
  data: {
    labels: trend.daily.map(d => d.date),
    datasets: [
      { label: 'Supportive', data: trend.daily.map(d => d.pos), borderColor: 'green' },
      { label: 'Critical', data: trend.daily.map(d => d.neg), borderColor: 'red' },
      { label: 'Neutral', data: trend.daily.map(d => d.neu), borderColor: 'gray' }
    ]
  }
});
```

### Pagination (get more articles)
```javascript
async function fetchArticles(filters, limit = 20, cursor = null) {
  const params = new URLSearchParams(filters);
  if (cursor) params.append('cursor', cursor);
  params.append('limit', limit);
  
  const res = await fetch(
    `https://api.rig360media.com/api/sources?${params}`,
    { headers: { 'Authorization': `Bearer ${API_KEY}` } }
  );
  const data = await res.json();
  return data; // { articles: [...], next_cursor: "abc123" }
}

// Load more articles
const page1 = await fetchArticles({ entity: 'telangana', window: 7 });
const page2 = await fetchArticles({ entity: 'telangana', window: 7 }, 20, page1.next_cursor);
```

### Ask RIG a question (streaming)
```javascript
async function askRIG(query) {
  const res = await fetch('https://api.rig360media.com/api/chat', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ query, history: [] })
  });
  
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n').filter(l => l.startsWith('data:'));
    
    for (const line of lines) {
      const event = JSON.parse(line.slice(5)); // strip "data:" prefix
      if (event.type === 'token') console.log(event.text);      // stream the answer
      if (event.type === 'sources') console.log(event.articles); // sources used
      if (event.type === 'chart') drawChart(event);              // draw a chart if one came back
      if (event.type === 'done') console.log('answer complete');
    }
  }
}
```

---

## 5. Data structures — what you get back

### Article object
```json
{
  "id": "art_12345",
  "headline": "CM slams Opposition on water",
  "summary": "The Chief Minister dismissed...",
  "entities": [
    { "id": "ent_456", "name": "Revanth Reddy", "type": "person" },
    { "id": "ent_789", "name": "Congress", "type": "party" }
  ],
  "sentiment": {
    "toward_target": "critical",
    "intensity": 0.8,
    "breakdown": { "supportive": 2, "neutral": 1, "critical": 4 }
  },
  "topic": "water rights",
  "geo": { "state": "Telangana", "district": "Hyderabad" },
  "source": "The Hindu",
  "language": "en",
  "url": "https://thehindu.com/...",
  "published_at": "2026-06-29T09:15:00Z",
  "story_cluster_id": "saga_xyz" // part of a larger story
}
```

### Sentiment object
```json
{
  "entity": "Revanth Reddy",
  "window_days": 30,
  "total_articles": 45,
  "summary": "Supportive: 12 | Neutral: 18 | Critical: 15",
  "net_lean": -0.07,
  "daily": [
    { "date": "2026-06-29", "pos": 2, "neu": 3, "neg": 2 },
    { "date": "2026-06-28", "pos": 1, "neu": 4, "neg": 3 }
  ]
}
```

---

## 6. Error handling

If your key is wrong or expired:
```json
{ "error": "Unauthorized", "status": 401 }
```

If you exceed your rate limit:
```json
{ "error": "Too many requests", "status": 429, "retry_after": 60 }
```

Always check the HTTP status code before parsing JSON.

---

## 7. Best practices

1. **Cache results** — don't re-fetch the brief every 5 seconds. Cache for at least 1 hour.
2. **Handle errors gracefully** — show "data unavailable" rather than crashing.
3. **Use pagination** — don't try to fetch 10,000 articles at once; use `cursor` for the next page.
4. **Filter on your side where possible** — if you're rendering only "critical" sentiment, ask the API for that (`?sentiment=critical`) rather than filtering after.
5. **Use the Chat endpoint for complex questions** — don't try to build your own reasoning on top of raw data; the assistant is there to synthesize.

---

## 8. Support & testing

- **Sandbox key:** we'll give you a test key so you can build without affecting prod.
- **API docs:** full OpenAPI spec at `/api/docs` (interactive Swagger UI).
- **Questions?** contact integration@rig360media.com.
