# YouTube IP-Block Bypass — DEPLOYED (2026-06-04)

Both layers live on Hetzner production box. Zero impact on rig-backend (no restart).

## Layer 2 — bgutil-pot (DEPLOYED ✓)

```
Container: rig-bgutil-pot
Image:     brainicism/bgutil-ytdlp-pot-provider:1.3.1
Port:      127.0.0.1:4416 (localhost-bound — only rig-backend can reach it)
Network:   infrastructure_rig-network (sibling to rig-backend)
Restart:   unless-stopped
Status:    Up; verified generating real PO tokens
Token TTL: 43,200s (12h) per integrity token, 6h provider cache
```

Verified probe: `POST /get_pot {"client_name":"WEB","video_id":"dQw4w9WgXcQ"}` returned a valid `poToken` (long base64 string) — bgutil ran a real BotGuard challenge, got an integrity token from Innertube, and minted the PoT.

## Layer 1 — IPv6 source pool (DEPLOYED ✓, safer variant)

Instead of the host-level `smart-ipv6-rotator` (which would rotate the host's default IPv6 route every N minutes — affects every container's outbound connections), we deployed the **per-call source-address rotation** variant. Same effect for yt-dlp, zero impact on other services.

```
Our Hetzner /64:   2a01:4f8:1c18:c8ba::/64
Addresses bound:   256 (from ::1000 to ::10ff)
Total eth0 IPv6:   257 (the 256 pool + the original ::1)
Persistence:       /etc/networkd-dispatcher/routable.d/50-rig-ipv6-pool.sh (re-binds on boot)
```

**Verified rotation probe:**
```
curl --interface 2a01:4f8:1c18:c8ba::10c1 https://www.youtube.com/
  → HTTP 200 from Google IPv6 edge (2a00:1450:4001:c0f::5d)
```

YouTube saw the request as coming from `::10c1`. Picking a different address from the pool for the next request rotates the origin IP YouTube sees — out of 256 we registered, expandable to 18 quintillion if the 256 ever burn (just change the seq range).

## Integration patch for backend/collectors/youtube_collector.py

Add at the top of the module:

```python
import ipaddress
import random

# IPv6 source-address pool — pre-bound to eth0 on the Hetzner host (mig: ipv6-pool-2026-06-04).
# We rotate per-call to spread YouTube's view of our origin IPs across the /64.
_IPV6_SUBNET_BASE = "2a01:4f8:1c18:c8ba"
_IPV6_POOL_RANGE = (0x1000, 0x10ff)   # 256 addresses bound on the host

def pick_outbound_ipv6() -> str:
    """Return a random IPv6 from our bound pool, for yt-dlp's --source-address."""
    suffix = random.randint(*_IPV6_POOL_RANGE)
    return f"{_IPV6_SUBNET_BASE}::{suffix:x}"

# bgutil PoT provider — running at rig-bgutil-pot:4416 (Docker network) or localhost:4416 (host).
# yt-dlp's bgutil-ytdlp-pot-provider plugin auto-fetches tokens; we pass the URL via env.
_BGUTIL_POT_URL = os.environ.get("BGUTIL_POT_URL", "http://rig-bgutil-pot:4416")
```

Modify both `yt-dlp` invocation sites (the `_fetch_channel_videos_ytdlp` and the audio-download path) to add:

```python
ydl_opts.setdefault("source_address", pick_outbound_ipv6())     # rotate per call
ydl_opts.setdefault("extractor_args", {}).setdefault("youtube", {})
ydl_opts["extractor_args"]["youtube"]["player_client"] = ["web"]
# bgutil plugin reads token via env or extractor_arg. The plugin auto-fetches from BGUTIL_POT_URL
# when "getpot_bgutil_baseurl" is provided as extractor-arg or set via PYTHONPATH plugin discovery.
ydl_opts["extractor_args"]["youtube"]["getpot_bgutil_baseurl"] = [_BGUTIL_POT_URL]
```

Same approach for the `youtube-transcript-api` path: it doesn't accept a source-address directly, but we can wrap it with `urllib3.util.connection.allowed_gai_family` or pass a proxy URL pointing to a small local SOCKS5 that binds the chosen IPv6. For now, keep the captions path on default routing (it's currently the working path) and rotate only on the yt-dlp audio download where the blocks happen.

## Install the yt-dlp PoT plugin (rig-backend Dockerfile)

Add to `infrastructure/Dockerfile.backend` near the pip block:

```dockerfile
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider==1.3.1
```

Plugin auto-discovers and registers itself with yt-dlp. With the `getpot_bgutil_baseurl` extractor-arg set, it hits our bgutil container every video and caches the result for 6h.

## docker-compose.yml entry (for persistence)

Add to `/root/rig/infrastructure/docker-compose.yml` (or compose.prod.yml):

```yaml
services:
  bgutil-pot:
    image: brainicism/bgutil-ytdlp-pot-provider:1.3.1
    container_name: rig-bgutil-pot
    restart: unless-stopped
    networks:
      - rig-network
    ports:
      - "127.0.0.1:4416:4416"
    environment:
      TOKEN_TTL: "6"
```

The standalone `docker run` is already persistent (`--restart unless-stopped`), so compose entry is for documentation + future rebuilds.

## What's needed to "flip on" the new path

The integration code above is documented but not yet wired. Two options:

**Option A — ship now (requires rig-backend rebuild):**
1. Apply the youtube_collector.py patch above.
2. Add the bgutil pip install to Dockerfile.backend.
3. `docker compose build rig-backend && docker compose up -d rig-backend` (this restarts rig-backend; per banked memory, watch for cold-start deadlock — warm the worker with ping tasks before invoking real load).

**Option B — env-only (no rebuild):**
1. Add `BGUTIL_POT_URL=http://rig-bgutil-pot:4416` to rig-backend env via `docker compose up -d --no-build`.
2. Without the pip-installed plugin yt-dlp can't use the URL, so this still needs at least a code change to manually attach the PoT token (the plugin is the clean path).

Recommended: Option A on the next planned rig-backend rebuild (don't trigger a special restart just for this).

## What got tested live, what didn't

| component | live verified | notes |
|---|---|---|
| bgutil-pot container running | ✓ | Up, /ping returns version |
| bgutil-pot generates PoT | ✓ | Real `poToken` returned; 12h TTL |
| IPv6 pool bound on eth0 | ✓ | 256 addresses live |
| Persistence on reboot | ✓ | networkd-dispatcher hook installed |
| YouTube reachable from a pool IPv6 | ✓ | HTTP 200 from `::10c1` |
| youtube_collector.py uses the pool | NOT YET | needs the integration patch + restart |
| youtube_collector.py uses bgutil PoT | NOT YET | needs the pip plugin + restart |

## Cost reality check

- bgutil-pot: ~50 MB RAM, negligible CPU. Free.
- IPv6 pool: zero additional cost (Hetzner /64 already on the contract).
- Total monthly cost added: **$0**.
- Total Hetzner contract change: **none**.
